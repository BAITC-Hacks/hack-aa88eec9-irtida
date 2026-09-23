// Live HTTP integration, not a browser/UI E2E test. Official Kit stays local.
// CAREER_QUEST_KIT_DIR=/absolute/path/to/kit npm run test:integration
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { File } from 'node:buffer';
import { randomBytes } from 'node:crypto';
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
let database = join(temporary, 'integration.db');
let realAccounts = false;
const nativeFetch = globalThis.fetch;
const originalWindow = globalThis.window;
let language = 'ru';
let responseLanguage;
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
    env: { ...process.env, DATABASE_URL: `sqlite:///${database.replaceAll('\\', '/')}`, AI_PROVIDER: provider, OPENAI_API_KEY: '', NVIDIA_API_KEY: '', DEMO_MODE: realAccounts ? 'false' : 'true', CAREER_QUEST_AUTO_IMPORT: realAccounts ? 'true' : 'false', CAREER_QUEST_KIT_DIR: resolve(kitDir), COOKIE_SECURE: 'false', AI_DATA_POLICY_APPROVED: provider === 'openai' ? 'true' : 'false', ALLOWED_ORIGINS: origin },
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
  // Supply only the browser locale storage used by the real getLocale helper.
  globalThis.window = { localStorage: { getItem: () => language } };
  const compiled = join(temporary, 'api.mjs');
  for (const filename of ['api.ts', 'i18n.tsx']) {
    const module = ts.transpileModule(readFileSync(join(web, 'src', filename), 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } });
    writeFileSync(join(temporary, filename.replace(/\.tsx?$/, '.mjs')), module.outputText.replace(/(from\s+['"])(\.\.?\/[^'"]+)(['"])/g, '$1$2.mjs$3'));
  }
  const { api, ApiError, importKit, completeEvent, authenticate } = await import(pathToFileURL(compiled).href);
  // Node lacks the browser origin and cookie jar. Preserve the real API helper's
  // request body, credentials, CSRF header and errors while supplying only those.
  globalThis.fetch = async (input, options = {}) => {
    assert.equal(options.credentials, 'same-origin');
    const headers = new Headers(options.headers);
    assert.equal(headers.get('X-Requested-With'), 'CareerQuest');
    assert.equal(headers.get('Accept-Language'), language);
    headers.set('Origin', origin);
    if (cookie) headers.set('Cookie', cookie);
    const response = await nativeFetch(new URL(input, origin), { ...options, headers });
    responseLanguage = response.headers.get('Content-Language');
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

  // A separate database verifies the actual, non-demo launch and account flow.
  // Bootstrap loads the local Kit once; no employee IDs or catalog data are copied.
  await stop();
  database = join(temporary, 'real-accounts.db');
  realAccounts = true;
  cookie = '';
  await start();
  const authStatus = capture('AuthStatus', await api('/auth/status'));
  assert.deepEqual({ ...authStatus }, { setup_required: true, registration: 'invite', demo_enabled: false });
  assert.deepEqual(await api('/auth/demo-accounts'), { enabled: false, accounts: [] });
  await expectStatus(() => login('hr'), 403);
  const clientCredentials = { username: 'http.integration.client', password: randomBytes(24).toString('base64url'), role: 'client', display_name: 'Contact centre client' };
  const clientAccount = capture('Account', await authenticate('register', clientCredentials));
  assert.equal(clientAccount.role, 'client');
  assert.equal(clientAccount.employee_id, null);
  assert.equal((await api('/auth/status')).setup_required, true, 'Public registration must not prevent the first HR from setting up');
  for (const path of ['/employees', '/catalog', '/hr/accounts', '/team/employees']) await expectStatus(() => api(path), 403);
  await api('/auth/logout', { method: 'POST' });
  const hrCredentials = { username: 'http.integration.hr', password: randomBytes(24).toString('base64url'), role: 'hr', display_name: 'HTTP integration HR' };
  const hrAccount = capture('Account', await authenticate('setup', hrCredentials));
  assert.equal(hrAccount.role, 'hr');
  assert.equal(hrAccount.employee_id, null);
  assert.equal((await api('/auth/status')).setup_required, false);
  await expectStatus(() => authenticate('setup', hrCredentials), 409);
  const fullCatalog = capture('Catalog', await api('/catalog'));
  assert.deepEqual(fullCatalog.counts, { skills: 60, events: 40, grade_rules: 24 });
  assert.equal(fullCatalog.skills.length, 60);
  assert.equal(fullCatalog.events.length, 40);
  const realEmployees = await api('/employees');
  assert.equal(realEmployees.length, 200);
  let businessProfile;
  for (const employee of realEmployees.filter(item => ['Sales Manager', 'Customer Support Specialist'].includes(item.role))) {
    const profile = await getProfile(employee.id);
    if (profile.available.length) { businessProfile = profile; break; }
  }
  assert.ok(businessProfile, 'A Sales or Customer Support employee must have a development step');
  const businessId = businessProfile.employee.id;
  const invite = capture('Invitation', await api('/hr/invitations', {
    method: 'POST', body: JSON.stringify({ role: 'employee', employee_id: businessId }),
  }));
  assert.ok(invite.invite_code.length >= 32 && invite.expires_at > Date.now() / 1000);
  const memberCredentials = { username: 'http.integration.member', password: randomBytes(24).toString('base64url'), role: 'employee', invite_code: invite.invite_code };
  await expectStatus(() => authenticate('register', { ...memberCredentials, role: 'hr' }), 403);
  const memberAccount = capture('Account', await authenticate('register', memberCredentials));
  assert.equal(memberAccount.employee_id, businessId);
  assert.equal(memberAccount.role, 'employee');
  await expectStatus(() => authenticate('register', { ...memberCredentials, username: 'http.integration.replay' }), 422);
  await expectStatus(() => authenticate('login', { ...memberCredentials, role: 'hr' }), 401);
  for (const path of ['/hr/overview', '/hr/accounts', '/catalog', '/employees']) await expectStatus(() => api(path), 403);
  await expectStatus(() => api(`/employees/${realEmployees.find(item => item.id !== businessId).id}`), 403);
  await expectStatus(() => api('/hr/invitations', { method: 'POST', body: JSON.stringify({ role: 'hr', employee_id: null }) }), 403);

  const numericCandidate = event => ({ id: event.id, occurrence_id: event.occurrence_id, projected_coverage: event.projected_coverage,
    critical_benefit: event.critical_benefit, changes: Object.fromEntries(Object.entries(event.changes).map(([id, change]) => [id, { before: change.before, after: change.after, gain: change.gain }])) });
  const numericProfile = profile => ({ id: profile.employee.id, role: profile.employee.role, grade: profile.employee.grade,
    levels: profile.employee.skills, coverage: profile.trajectory.coverage, next_grade: profile.trajectory.next_grade,
    critical_requirements_met: profile.trajectory.critical_requirements_met,
    requirements: profile.trajectory.skills.map(skill => ({ id: skill.id, level: skill.level, required: skill.required, gap: skill.gap, critical: skill.critical })),
    available: profile.available.map(numericCandidate),
    history: profile.history.map(item => ({ id: item.id, event_id: item.event_id, status: item.status, occurred_at: item.occurred_at })) });
  const localizedProfiles = [];
  const localizedRecommendations = [];
  for (const locale of ['ru', 'en', 'kk']) {
    language = locale;
    const profile = await getProfile(businessId);
    assert.equal(responseLanguage, locale);
    assert.equal(profile.skill_catalog.length, 60);
    assert.equal(new Set(profile.skill_catalog.map(item => item.id)).size, 60);
    for (const skill of profile.skill_catalog) assert.equal(skill.level, profile.employee.skills[skill.id]);
    localizedProfiles.push(profile);
    const recommended = capture('Recommendations', await api(`/employees/${businessId}/recommendations`, { method: 'POST' }));
    assert.equal(responseLanguage, locale);
    assert.equal(recommended.mode, 'rules');
    localizedRecommendations.push(recommended);
  }
  for (const profile of localizedProfiles.slice(1)) assert.deepEqual(numericProfile(profile), numericProfile(localizedProfiles[0]));
  for (const recommended of localizedRecommendations.slice(1)) assert.deepEqual(recommended.items.map(numericCandidate), localizedRecommendations[0].items.map(numericCandidate));
  assert.notDeepEqual(localizedProfiles[0].skill_catalog.map(item => item.name), localizedProfiles[1].skill_catalog.map(item => item.name));
  assert.notDeepEqual(localizedProfiles[1].skill_catalog.map(item => item.name), localizedProfiles[2].skill_catalog.map(item => item.name));
  assert.notEqual(localizedRecommendations[0].items[0].evidence[2].text, localizedRecommendations[1].items[0].evidence[2].text);
  assert.notEqual(localizedRecommendations[1].items[0].evidence[2].text, localizedRecommendations[2].items[0].evidence[2].text);
  language = 'ru';
  const businessBefore = await getProfile(businessId);
  const selected = localizedRecommendations[0].items[0];
  const businessDone = capture('CompletionResult', await completeEvent(businessId, selected));
  assert.equal(businessDone.already_completed, false);
  assert.equal(businessDone.profile.trajectory.coverage, selected.projected_coverage);
  assert.equal(businessDone.profile.employee.grade, businessBefore.employee.grade);
  assert.equal(businessDone.profile.history.length, businessBefore.history.length + 1);
  for (const [id, level] of Object.entries(businessBefore.employee.skills)) assert.equal(businessDone.profile.employee.skills[id], selected.changes[id]?.after ?? level);
  assert.equal((await completeEvent(businessId, selected)).already_completed, true);
  await stop();
  await start();
  assert.equal((await api('/auth/me')).employee_id, businessId);
  assert.deepEqual(numericProfile(await getProfile(businessId)), numericProfile(businessDone.profile));
  await api('/auth/logout', { method: 'POST' });
  await expectStatus(() => api('/auth/me'), 401);
  capture('Account', await authenticate('login', memberCredentials));
  assert.equal((await api('/auth/me')).employee_id, businessId);
  await api('/auth/logout', { method: 'POST' });
  capture('Account', await authenticate('login', hrCredentials));
  const registered = capture('RegisteredAccount[]', await api('/hr/accounts'));
  assert.equal(registered.length, 3);
  assert.ok(registered.some(account => account.employee_id === businessId && account.role === 'employee'));
  assert.ok(registered.every(account => !('password' in account) && !('password_hash' in account)));
  assert.equal((await api('/catalog')).counts.events, 40);

  // Use the original manager_id relationships, never role titles or a global
  // employee list as an authorization substitute. Leaders retain their own path.
  const usedProfiles = new Set([businessId]);
  for (const role of ['manager', 'supervisor', 'operator']) {
    if (role !== 'manager') capture('Account', await authenticate('login', hrCredentials));
    const person = realEmployees.find(employee => !usedProfiles.has(employee.id) && (role === 'operator'
      ? employee.role === 'Customer Support Specialist'
      : realEmployees.some(report => report.id !== employee.id && report.manager_id === employee.id)));
    assert.ok(person, `Kit must contain an unused profile suitable for the ${role} account scenario`);
    usedProfiles.add(person.id);
    const roleInvite = capture('Invitation', await api('/hr/invitations', {
      method: 'POST', body: JSON.stringify({ role, employee_id: person.id }),
    }));
    const credentials = { username: `http.integration.${role}`, password: randomBytes(24).toString('base64url'), role, invite_code: roleInvite.invite_code };
    const account = capture('Account', await authenticate('register', credentials));
    assert.equal(account.role, role);
    assert.equal(account.employee_id, person.id);
    assert.equal((await getProfile(person.id)).employee.role, person.role, 'Account permissions must not change the Kit career role');
    for (const path of ['/hr/overview', '/hr/accounts', '/employees', '/catalog']) await expectStatus(() => api(path), 403);
    if (role === 'operator') {
      await expectStatus(() => api('/team/employees'), 403);
      await expectStatus(() => api('/team/overview'), 403);
      await expectStatus(() => api(`/employees/${businessId}`), 403);
    } else {
      const expectedReports = realEmployees.filter(report => report.id !== person.id && report.manager_id === person.id);
      const reports = capture('Employee[]', await api('/team/employees'));
      assert.deepEqual(reports.map(report => report.id).sort(), expectedReports.map(report => report.id).sort());
      const metrics = capture('Metrics', await api('/team/overview'));
      assert.equal(metrics.employee_count, reports.length);
      assert.ok(metrics.no_step.every(report => reports.some(item => item.id === report.id)));
      assert.ok(metrics.gaps.every(gap => gap.eligible <= reports.length && gap.affected <= reports.length));
      const scopedHistory = [];
      for (const report of reports) scopedHistory.push(...(await getProfile(report.id)).history);
      assert.deepEqual(metrics.participation.map(event => event.id).sort(), [...new Set(scopedHistory.map(item => item.event_id))].sort());
      for (const event of metrics.participation) {
        for (const status of ['completed', 'in_progress', 'dropped', 'no_show', 'declined', 'overdue']) {
          assert.equal(event[status], scopedHistory.filter(item => item.event_id === event.id && item.status === status).length);
        }
      }
      const reportId = reports[0].id;
      await expectStatus(() => api(`/employees/${reportId}/recommendations`, { method: 'POST' }), 403);
      await expectStatus(() => api(`/employees/${reportId}/events/EV_001/complete`, { method: 'POST' }), 403);
      const outsider = realEmployees.find(employee => employee.id !== person.id && !reports.some(report => report.id === employee.id));
      await expectStatus(() => api(`/employees/${outsider.id}`), 403);
    }
    await api('/auth/logout', { method: 'POST' });
  }
  capture('Account', await authenticate('login', clientCredentials));
  for (const path of ['/employees', `/employees/${businessId}`, '/catalog', '/hr/overview', '/hr/accounts', '/team/employees', '/team/overview']) await expectStatus(() => api(path), 403);
  await expectStatus(() => api(`/employees/${businessId}/recommendations`, { method: 'POST' }), 403);
  await expectStatus(() => api(`/employees/${businessId}/events/EV_001/complete`, { method: 'POST' }), 403);

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
  const typecheck = spawnSync(process.execPath, [join(web, 'node_modules/typescript/bin/tsc'), '--noEmit', '--skipLibCheck', '--strict', '--target', 'ES2022', '--module', 'ESNext', '--jsx', 'react-jsx', '--moduleResolution', 'Bundler', '--lib', 'ES2022,DOM', contractFile], { cwd: web, encoding: 'utf8', windowsHide: true });
  if (typecheck.status !== 0) writeFileSync(join(temporary, 'type-errors.log'), `${typecheck.stdout}\n${typecheck.stderr}`);
  assert.equal(typecheck.status, 0, 'Actual HTTP JSON does not satisfy frontend DTOs; see private type-errors.log.');
  passed = true;
  console.log(`PASS live HTTP integration: ${contracts.length} typed response snapshots; Kit import/reimport/422, rules/fallback, ordinary and two EV_036 completions, HR totals, persistence; six account roles, client before HR setup, direct-report scope/read-only access, Sales/Support development and ru/en/kk ID/progress invariance.`);
} catch (error) {
  // Assertion and compiler diagnostics may contain real Kit values. Keep them
  // only in this ignored local run directory, never in console/CI output.
  writeFileSync(join(temporary, 'failure.log'), error instanceof Error ? error.stack ?? error.message : String(error));
  console.error('FAIL live HTTP integration; inspect the ignored local diagnostics directory.');
  process.exitCode = 1;
} finally {
  globalThis.fetch = nativeFetch;
  if (originalWindow === undefined) delete globalThis.window;
  else globalThis.window = originalWindow;
  await stop();
  // Only remove this run's generated directory, never a configured dataset/DB.
  assert.ok(temporary.startsWith(buildRoot + (process.platform === 'win32' ? '\\' : '/')));
  if (passed) rmSync(temporary, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
  else console.error(`Integration diagnostics retained in ignored directory: ${temporary}`);
}
