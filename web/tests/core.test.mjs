import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
const { percent, milestones, recommendationLabel, participationCounts } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'view-model.mjs')));
const { api, ApiError, importKit, completeEvent } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'api.mjs')));
const { importReducer, initialImportState } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'import-state.mjs')));
const profile = () => ({ employee: { skills: { design: 2, python: 3 } }, history: [], trajectory: { coverage: 63, skills: [{ id: 'design', level: 2, required: 4, gap: 2 }, { id: 'python', level: 3, required: 4, gap: 1 }] } });

test('unknown percentages never become zero, valid display percentages remain bounded', () => {
  assert.equal(percent(null), null); assert.equal(percent(undefined), null); assert.equal(percent(NaN), null);
  assert.equal(percent(-3), 0); assert.equal(percent(101), 100);
});
test('badges count completed participation only and require a known closed gap', () => {
  const p = profile(); p.history = [{ status: 'missed' }, { status: 'declined' }];
  assert.ok(milestones(p).every(b => !b.earned));
  p.history.push({ status: 'completed' }); assert.equal(milestones(p)[0].earned, true);
  assert.equal(milestones(p)[1].earned, false);
  p.trajectory.skills[0].gap = null; assert.equal(milestones(p)[2].earned, false);
  p.trajectory.skills[0].gap = 0; assert.equal(milestones(p)[2].earned, true);
});
test('AI, rules, fallback, cache and no candidates have distinct labels', () => {
  assert.equal(recommendationLabel({ mode: 'ai', cached: false }), 'AI-рекомендация');
  assert.match(recommendationLabel({ mode: 'fallback' }), /AI недоступен/);
  assert.equal(recommendationLabel({ mode: 'rules' }), 'Подбор по правилам');
  assert.match(recommendationLabel({ mode: 'ai', cached: true }), /Сохранённый результат/);
  assert.equal(recommendationLabel({ mode: 'no_candidates' }), 'Нет подходящего шага');
});
test('API preserves cookie auth, endpoint prefix and CSRF header', async t => {
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.equal(url, '/api/v1/employees/E1/recommendations');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.get('X-Requested-With'), 'CareerQuest');
    assert.equal(options.method, 'POST');
    return new Response(JSON.stringify({ mode: 'rules' }));
  });
  assert.deepEqual(await api('/employees/E1/recommendations', { method: 'POST' }), { mode: 'rules' });
});
test('API renders field validation and does not retry mutations', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response(JSON.stringify({ detail: [{ loc: ['body', 'skills'], msg: 'Expected level 0–5' }] }), { status: 422 }); });
  await assert.rejects(api('/imports', { method: 'POST' }), /body.skills: Expected level/);
  assert.equal(calls, 1);
});
test('API handles expired sessions, empty success and non-JSON errors', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response('{"detail":"expired"}', { status: 401 }));
  await assert.rejects(api('/auth/me'), e => e instanceof ApiError && e.status === 401);
  globalThis.fetch = async () => new Response(null, { status: 204 });
  assert.equal(await api('/auth/logout', { method: 'POST' }), null);
  globalThis.fetch = async () => new Response('<html>Bad gateway</html>', { status: 502 });
  await assert.rejects(api('/hr/overview'), /HTTP 502/);
});
test('API network failure and abort do not trigger an automatic retry', async t => {
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; throw new TypeError('network'); });
  await assert.rejects(api('/employees/E1'), /Нет соединения/); assert.equal(calls, 1);
  const controller = new AbortController(); controller.abort();
  await assert.rejects(api('/employees/E1', { signal: controller.signal }), /Обновите данные перед повторной отправкой/);
});
test('a stalled request times out at 15 seconds and does not retry', async t => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    calls++;
    return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true }));
  });
  const pending = api('/employees/E1/events/event/complete', { method: 'POST' });
  const check = assert.rejects(pending, e => e instanceof ApiError && e.status === 408 && e.message.includes('действие могло сохраниться'));
  t.mock.timers.tick(15000);
  await check;
  assert.equal(calls, 1);
});

test('kit dry-run and commit transmit untouched files with browser multipart boundary', async t => {
  const files = [new File(['{"employees":[]}'], 'employees.json'), new File(['record_id\n'], 'activity_history.csv')];
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push(url);
    assert.equal(options.method, 'POST');
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers.get('X-Requested-With'), 'CareerQuest');
    assert.equal(options.headers.has('Content-Type'), false);
    assert.ok(options.body instanceof FormData);
    assert.deepEqual([...options.body.keys()], ['files', 'files']);
    const uploads = options.body.getAll('files');
    assert.deepEqual(uploads.map(file => file.name), files.map(file => file.name));
    assert.equal(await uploads[0].text(), await files[0].text());
    return new Response('{"schema":"kit-v1","employees_added":0,"history_added":0}');
  });
  await importKit(files, true, true);
  await importKit(files, false, true);
  assert.deepEqual(requests, ['/api/v1/imports/kit?dry_run=true&replace_demo=true', '/api/v1/imports/kit?dry_run=false&replace_demo=true']);
});

test('completing a session sends occurrence_id, ordinary demo completion remains bodyless', async t => {
  const requests = [];
  const serverProfile = { employee: { grade: 'Middle', skills: { design: 3 } }, recommendation: null };
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    requests.push({ url, body: options.body });
    return new Response(JSON.stringify({ profile: serverProfile, already_completed: requests.length === 3 }));
  });
  await completeEvent('E/1', { id: 'demo', occurrence_id: null });
  const event = { id: 'EV_036', occurrence_id: '2026-10-02' };
  const first = await completeEvent('E/1', event);
  const second = await completeEvent('E/1', event);
  assert.equal(requests[0].body, undefined);
  assert.equal(requests[1].url, '/api/v1/employees/E%2F1/events/EV_036/complete');
  assert.deepEqual(JSON.parse(requests[1].body), { occurrence_id: '2026-10-02' });
  assert.equal(requests[1].body, requests[2].body);
  assert.deepEqual(first.profile, serverProfile);
  assert.equal(second.already_completed, true);
});

test('kit import errors preserve source, path and reason alongside old Pydantic support', async t => {
  const issues = [{ source: 'activity_history.csv', path: 'line 2.event_id', reason: 'Unknown event reference' }];
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ detail: 'Invalid import', errors: issues }), { status: 422 }));
  await assert.rejects(importKit([], true, false), error => {
    assert.deepEqual(error.issues, issues);
    assert.match(error.message, /activity_history.csv · line 2.event_id: Unknown event reference/);
    return error.status === 422;
  });
});

test('HTTP failures stay actionable and never retry an import mutation', async t => {
  let status = 403;
  let calls = 0;
  t.mock.method(globalThis, 'fetch', async () => { calls++; return new Response('{}', { status }); });
  for (status of [401, 403, 409, 413, 415, 422, 429, 503]) {
    await assert.rejects(api('/imports', { method: 'POST', body: '{}' }), error => error instanceof ApiError && error.status === status && error.message.length > 15);
  }
  assert.equal(calls, 8);
});

test('changing files, format or replace flag invalidates successful dry-run approval', () => {
  const files = [new File(['{}'], 'employees.json')];
  const summary = { schema: 'kit-v1', dry_run: true, employees_added: 1, history_added: 0 };
  const selected = importReducer(initialImportState, { type: 'files', files });
  const checked = importReducer(selected, { type: 'checked', summary, body: null });
  assert.equal(checked.approved, true);
  for (const action of [{ type: 'files', files }, { type: 'replace', value: true }, { type: 'mode', mode: 'demo' }, { type: 'reset-check' }]) {
    const changed = importReducer(checked, action);
    assert.equal(changed.approved, false);
    assert.equal(changed.summary, null);
  }
  const saved = importReducer(checked, { type: 'saved', summary: { ...summary, dry_run: false } });
  assert.equal(saved.approved, false);
  assert.equal(saved.imported, true);
  assert.equal(importReducer(selected, { type: 'checked', summary: { ...summary, dry_run: false }, body: null }).approved, false);
  const replaced = importReducer({ ...checked, replaceDemo: true }, { type: 'saved', summary: { ...summary, dry_run: false, demo_replaced: true } });
  assert.equal(replaced.replaceDemo, false); // Subsequent imports add/revalidate; they must not try replacing kit data.
});

test('HR exact status counts do not count no_show twice via missed compatibility aggregate', () => {
  const counts = participationCounts({ completed: 5, missed: 7, no_show: 6, declined: 2, dropped: 3, in_progress: 4, overdue: 1 });
  assert.deepEqual(counts, { completed: 5, missed: 1, no_show: 6, declined: 2, dropped: 3, in_progress: 4, overdue: 1 });
  assert.equal(Object.values(counts).reduce((sum, value) => sum + value, 0), 22);
});
