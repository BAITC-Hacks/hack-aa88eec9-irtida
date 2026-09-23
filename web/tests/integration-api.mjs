// Live HTTP integration, not a browser/UI E2E test. Official Kit stays local.
// CAREER_QUEST_KIT_DIR=/absolute/path/to/kit npm run test:integration
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { File } from 'node:buffer';
import { setTimeout as delay } from 'node:timers/promises';
import ts from 'typescript';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(web, '..');
const kitDir = process.env.CAREER_QUEST_KIT_DIR;
if (!kitDir) {
  console.log('SKIP live HTTP integration: set CAREER_QUEST_KIT_DIR to the four original Kit files.');
  process.exit(0);
}
const names = ['employees.json', 'skills.json', 'events.json', 'activity_history.csv'];
for (const name of names) assert.ok(existsSync(join(kitDir, name)), `Missing Kit file: ${name}`);
const python = process.env.CQ_PYTHON ?? join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
assert.ok(existsSync(python), 'Create the repository .venv first, or set CQ_PYTHON.');
const buildRoot = join(web, '.test-build');
mkdirSync(buildRoot, { recursive: true });
const temporary = mkdtempSync(join(buildRoot, 'live-http-'));
const database = join(temporary, 'integration.db');
const nativeFetch = globalThis.fetch;
let server;
let origin;
let cookie = '';
let logs = '';
let passed = false;
const contracts = [];
const capture = (type, value) => { contracts.push({ type, value }); return value; };

async function freePort() {
  const reservation = createServer();
  await new Promise((done, reject) => { reservation.once('error', reject); reservation.listen(0, '127.0.0.1', done); });
  const port = reservation.address().port;
  await new Promise(done => reservation.close(done));
  return port;
}

async function start(provider = 'rules') {
  const port = await freePort();
  origin = `http://127.0.0.1:${port}`;
  // Close stdin to shut down Uvicorn gracefully. On Windows the .venv launcher
  // can spawn a child interpreter, so killing only the launcher leaks the server.
  const launcher = "import sys,threading,uvicorn; server=uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=int(sys.argv[1]),access_log=False,log_level='warning')); threading.Thread(target=lambda:(sys.stdin.read(),setattr(server,'should_exit',True)),daemon=True).start(); server.run()";
  server = spawn(python, ['-c', launcher, String(port)], {
    cwd: join(root, 'server'), windowsHide: true,
    env: { ...process.env, DATABASE_URL: `sqlite:///${database.replaceAll('\\', '/')}`, AI_PROVIDER: provider, OPENAI_API_KEY: '', NVIDIA_API_KEY: '', DEMO_MODE: 'true', COOKIE_SECURE: 'false', AI_DATA_POLICY_APPROVED: provider === 'openai' ? 'true' : 'false', ALLOWED_ORIGINS: origin },
    stdio: ['pipe', 'pipe', 'pipe'],
  });
  server.on('error', error => { logs += String(error); });
  for (const stream of [server.stdout, server.stderr]) stream.on('data', chunk => { logs = (logs + chunk).slice(-8000); });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (server.exitCode !== null) throw new Error(`Test backend exited: ${logs}`);
    try {
      const response = await nativeFetch(`${origin}/api/v1/health`);
      if (response.ok) { assert.equal((await response.json()).ai_provider, provider); return; }
    } catch { /* Wait only for the server owned by this test. */ }
    await delay(100);
  }
  throw new Error(`Test backend did not become ready: ${logs}`);
}

async function stop() {
  if (!server || server.exitCode !== null) return;
  const stopped = new Promise(done => server.once('exit', done));
  server.stdin.end();
  await Promise.race([stopped, delay(5000)]);
  if (server.exitCode === null) { server.kill('SIGKILL'); await stopped; }
}

function candidateShape(event) {
  assert.equal(typeof event.id, 'string');
  assert.equal(event.mandatory, false);
  assert.ok(event.projected_coverage === null || Number.isInteger(event.projected_coverage));
  assert.equal(typeof event.critical_benefit, 'number');
  assert.ok(event.occurrence_id === null || typeof event.occurrence_id === 'string');
  assert.deepEqual(new Set(event.evidence.map(item => item.factor)), new Set(['grade', 'skill_gap', 'next_level', 'history']));
  for (const change of Object.values(event.changes)) {
    assert.equal(change.after - change.before, change.gain);
    assert.ok(change.after <= 5 && change.gain > 0);
  }
}

function profileShape(profile) {
  assert.equal(profile.employee.source_format, 'kit-v1');
  assert.equal(profile.employee.snapshot_date, '2026-10-01');
  assert.equal(Object.keys(profile.employee.skills).length, 60);
  for (const skill of profile.trajectory.skills) {
    assert.equal(typeof skill.critical, 'boolean');
    assert.equal(typeof skill.level, 'number');
    assert.equal(skill.gap, Math.max(0, skill.required - skill.level));
  }
  profile.available.forEach(candidateShape);
  return capture('Profile', profile);
}

function importShape(summary, dryRun, added) {
  assert.equal(summary.schema, 'kit-v1');
  assert.equal(summary.snapshot_date, '2026-10-01');
  assert.equal(summary.dry_run, dryRun);
  assert.equal(summary.employees_added, added ? 200 : 0);
  assert.equal(summary.skills_added, added ? 60 : 0);
  assert.equal(summary.events_added, added ? 40 : 0);
  assert.equal(summary.history_added, added ? 2743 : 0);
  assert.equal(summary.completed_after_review, 318);
  assert.equal(summary.warnings.find(item => item.code === 'mandatory_history_repeated_after_completion')?.count, 544);
  return capture('ImportSummary', summary);
}

try {
  const module = ts.transpileModule(readFileSync(join(web, 'src/api.ts'), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
  const compiled = join(temporary, 'api.mjs');
  writeFileSync(compiled, module.outputText);
  const { api, ApiError, importKit, completeEvent } = await import(pathToFileURL(compiled).href);
  // Node lacks the browser origin and cookie jar. Preserve the real API helper's
  // request body, credentials, CSRF header and errors while supplying only those.
  globalThis.fetch = async (input, options = {}) => {
    assert.equal(options.credentials, 'same-origin');
    const headers = new Headers(options.headers);
    assert.equal(headers.get('X-Requested-With'), 'CareerQuest');
    headers.set('Origin', origin);
    if (cookie) headers.set('Cookie', cookie);
    const response = await nativeFetch(new URL(input, origin), { ...options, headers });
    for (const value of response.headers.getSetCookie()) if (value.startsWith('cq_session=')) cookie = value.split(';', 1)[0];
    return response;
  };
  const login = async account => capture('Account', await api('/auth/demo', { method: 'POST', body: JSON.stringify({ account }) }));
  const getProfile = async id => profileShape(await api(`/employees/${encodeURIComponent(id)}`));
  const expectStatus = async (operation, status) => assert.rejects(operation, error => error instanceof ApiError && error.status === status);
  const files = names.map(name => new File([readFileSync(join(kitDir, name))], name, { type: name.endsWith('.csv') ? 'text/csv' : 'application/json' }));
  await start();
  await expectStatus(() => api('/auth/me'), 401);
  assert.equal((await login('hr')).role, 'hr');
  capture('DemoAccounts', await api('/auth/demo-accounts'));
  const demoBefore = await api('/employees');
  assert.equal(demoBefore.length, 3);
  const preview = importShape(await importKit(files, true, true), true, true);
  assert.equal(preview.demo_replaced, false);
  assert.deepEqual(await api('/employees'), demoBefore);
  const imported = importShape(await importKit(files, false, true), false, true);
  assert.equal(imported.demo_replaced, true);
  const employees = capture('Employee[]', await api('/employees'));
  assert.equal(employees.length, 200);
  importShape(await importKit(files, false, false), false, false);
  const invalidEmployees = JSON.parse(readFileSync(join(kitDir, 'employees.json'), 'utf8').replace(/^\uFEFF/, ''));
  invalidEmployees.employees[0].skills.UNKNOWN_INTEGRATION_SKILL = 1;
  await assert.rejects(() => importKit([new File([JSON.stringify(invalidEmployees)], 'employees.json', { type: 'application/json' })], true, false), error => error instanceof ApiError && error.status === 422 && error.issues.length > 0);
  assert.equal((await api('/employees')).length, 200);

  const initialMetrics = capture('Metrics', await api('/hr/overview'));
  assert.equal(initialMetrics.employee_count, 200);
  assert.equal(initialMetrics.participation.length, 40);
  const statuses = ['completed', 'in_progress', 'dropped', 'no_show', 'declined', 'overdue'];
  const totals = Object.fromEntries(statuses.map(status => [status, initialMetrics.participation.reduce((total, event) => total + event[status], 0)]));
  assert.deepEqual(totals, { completed: 2178, in_progress: 16, dropped: 160, no_show: 195, declined: 104, overdue: 90 });
  assert.equal(Object.values(totals).reduce((a, b) => a + b, 0), 2743);
  for (const row of initialMetrics.participation) assert.equal(row.missed, row.no_show, 'missed aliases no_show; never add both to the participation total');
  for (const row of initialMetrics.no_step) assert.ok(row.reason && row.reason_detail);
  assert.ok(initialMetrics.gaps.every(row => row.unknown === 0));

  let ordinary;
  let recurring;
  const seenStatuses = new Set();
  for (const employee of employees) {
    const profile = await getProfile(employee.id);
    profile.history.forEach(item => seenStatuses.add(item.status));
    if (!ordinary) {
      const event = profile.available.find(item => item.id !== 'EV_036' && item.format === 'self_paced');
      if (event) ordinary = { profile, event };
    }
    if (!recurring) {
      const event = profile.available.find(item => item.id === 'EV_036' && item.upcoming_sessions.length >= 2 && Object.keys(item.changes).some(id => profile.trajectory.skills.some(skill => skill.id === id && skill.gap >= 2 * item.changes[id].gain)));
      if (event) recurring = { profile, event };
    }
    if (ordinary && recurring && statuses.every(status => seenStatuses.has(status))) break;
  }
  assert.ok(ordinary && recurring, 'Official Kit must provide ordinary and recurring completion scenarios');
  assert.deepEqual(seenStatuses, new Set(statuses));
  const highest = await getProfile(employees.find(employee => employee.grade === 'Lead').id);
  assert.equal(highest.trajectory.status, 'highest_grade');
  assert.equal(highest.trajectory.next_grade, null);
  assert.equal(highest.trajectory.coverage, null);
  assert.equal(highest.available.length, 0);

  const employeeId = ordinary.profile.employee.id;
  await login(employeeId);
  await expectStatus(() => api('/hr/overview'), 403);
  await expectStatus(() => importKit(files, true, false), 403);
  const before = await getProfile(employeeId);
  assert.ok(before.trajectory.skills.some(skill => skill.critical));
  const recommendation = capture('Recommendations', await api(`/employees/${employeeId}/recommendations`, { method: 'POST' }));
  assert.equal(recommendation.mode, 'rules');
  assert.ok(recommendation.items.length >= 1 && recommendation.items.length <= 3);
  assert.equal(recommendation.provider, null);
  assert.equal(recommendation.model, null);
  assert.equal(typeof recommendation.elapsed_ms, 'number');
  recommendation.items.forEach(candidateShape);
  assert.equal((await api(`/employees/${employeeId}/recommendations`, { method: 'POST' })).cached, true);
  const ordinaryEvent = before.available.find(event => event.id === ordinary.event.id);
  const completion = capture('CompletionResult', await completeEvent(employeeId, ordinaryEvent));
  assert.equal(completion.already_completed, false);
  assert.equal(completion.profile.trajectory.coverage, ordinaryEvent.projected_coverage);
  assert.equal(completion.profile.employee.grade, before.employee.grade);
  assert.equal(completion.profile.history.length, before.history.length + 1);
  assert.equal(completion.profile.recommendation, null);
  for (const [id, level] of Object.entries(before.employee.skills)) assert.equal(completion.profile.employee.skills[id], ordinaryEvent.changes[id]?.after ?? level);
  const duplicate = await completeEvent(employeeId, ordinaryEvent);
  assert.equal(duplicate.already_completed, true);
  assert.deepEqual(duplicate.profile.employee, completion.profile.employee);
  assert.deepEqual((await getProfile(employeeId)).employee, completion.profile.employee);
  assert.equal((await api(`/employees/${employeeId}/recommendations`, { method: 'POST' })).cached, false);

  const recurringId = recurring.profile.employee.id;
  await login(recurringId);
  const clubBefore = await getProfile(recurringId);
  const firstEvent = clubBefore.available.find(event => event.id === 'EV_036');
  assert.ok(firstEvent?.occurrence_id);
  const first = capture('CompletionResult', await completeEvent(recurringId, firstEvent));
  assert.equal(first.already_completed, false);
  assert.equal(first.profile.trajectory.coverage, firstEvent.projected_coverage);
  const firstRetry = await completeEvent(recurringId, firstEvent);
  assert.equal(firstRetry.already_completed, true);
  assert.deepEqual(firstRetry.profile.employee, first.profile.employee);
  const secondEvent = first.profile.available.find(event => event.id === 'EV_036');
  assert.ok(secondEvent?.occurrence_id && secondEvent.occurrence_id !== firstEvent.occurrence_id);
  const second = capture('CompletionResult', await completeEvent(recurringId, secondEvent));
  assert.equal(second.already_completed, false);
  assert.equal(second.profile.trajectory.coverage, secondEvent.projected_coverage);
  assert.equal(second.profile.history.length, clubBefore.history.length + 2);
  assert.equal(second.profile.employee.grade, clubBefore.employee.grade);
  const secondRetry = await completeEvent(recurringId, secondEvent);
  assert.equal(secondRetry.already_completed, true);
  assert.deepEqual(secondRetry.profile.employee, second.profile.employee);
  assert.equal((await completeEvent(recurringId, firstEvent)).already_completed, true);
  await stop();
  await start();
  assert.equal((await api('/auth/me')).employee_id, recurringId);
  assert.deepEqual((await getProfile(recurringId)).employee, second.profile.employee);
  await login('hr');
  const afterMetrics = capture('Metrics', await api('/hr/overview'));
  assert.equal(afterMetrics.participation.reduce((sum, event) => sum + event.completed, 0), totals.completed + 3);
  await login(employeeId);
  await stop();
  // Explicitly empty credentials guarantee the provider fails before any network
  // request; this exercises the real HTTP fallback without sending Kit data out.
  await start('openai');
  const fallback = capture('Recommendations', await api(`/employees/${employeeId}/recommendations`, { method: 'POST' }));
  assert.equal(fallback.mode, 'fallback');
  assert.ok(fallback.reason && fallback.items.length > 0);
  assert.equal(fallback.provider, null);
  assert.equal(fallback.model, null);
  await api('/auth/logout', { method: 'POST' });
  await expectStatus(() => api('/auth/me'), 401);

  // Generic constraints validate required DTO fields against real JSON while
  // allowing harmless additional backend fields (plain satisfies rejects extras).
  const typeNames = [...new Set(contracts.map(item => item.type.replace('[]', '')))];
  const source = [`import type { ${typeNames.join(', ')} } from '../../src/api';`,
    'type Mutable<T> = T extends object ? { -readonly [P in keyof T]: Mutable<T[P]> } : T;',
    ...contracts.flatMap(({ type, value }, index) => [
    `const response${index} = ${JSON.stringify(value)} as const;`,
    `type Assert${index}<T extends ${type}> = T;`,
    `type Contract${index} = Assert${index}<Mutable<typeof response${index}>>;`,
  ])].join('\n');
  const contractFile = join(temporary, 'contracts.ts');
  writeFileSync(contractFile, source);
  const typecheck = spawnSync(process.execPath, [join(web, 'node_modules/typescript/bin/tsc'), '--noEmit', '--skipLibCheck', '--strict', '--target', 'ES2022', '--module', 'ESNext', '--moduleResolution', 'Bundler', '--lib', 'ES2022,DOM', contractFile], { cwd: web, encoding: 'utf8', windowsHide: true });
  assert.equal(typecheck.status, 0, `Actual HTTP JSON does not satisfy frontend DTOs:\n${typecheck.stdout}\n${typecheck.stderr}`);
  passed = true;
  console.log(`PASS live HTTP integration: Kit import/reimport/422, ${contracts.length} typed response snapshots, rules/fallback recommendations, ordinary completion, two EV_036 occurrences/retries, RBAC, six statuses, HR totals, restart persistence and logout.`);
} finally {
  globalThis.fetch = nativeFetch;
  await stop();
  // Only remove this run's generated directory, never a configured dataset/DB.
  assert.ok(temporary.startsWith(buildRoot + (process.platform === 'win32' ? '\\' : '/')));
  if (passed) rmSync(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  else console.error(`Integration diagnostics retained in ignored directory: ${temporary}`);
}
