import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
const { percent, projectedCoverage, milestones, recommendationLabel } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'view-model.mjs')));
const { api, ApiError } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'api.mjs')));
const profile = () => ({ employee: { skills: { design: 2, python: 3 } }, history: [], trajectory: { coverage: 63, skills: [{ id: 'design', level: 2, required: 4, gap: 2 }, { id: 'python', level: 3, required: 4, gap: 1 }] } });

test('preview computes weighted target coverage without mutating the profile', () => {
  const p = profile(); const before = structuredClone(p);
  assert.equal(projectedCoverage(p, { changes: { design: { after: 3 } } }), 75);
  assert.deepEqual(p, before);
});
test('unknown levels and absent targets never become zero in the UI', () => {
  assert.equal(percent(null), null); assert.equal(percent(undefined), null); assert.equal(percent(NaN), null);
  const p = profile(); p.trajectory.skills[0].level = null;
  assert.equal(projectedCoverage(p, { changes: { design: { after: 3 } } }), null);
  p.trajectory.skills = []; assert.equal(projectedCoverage(p, { changes: {} }), null);
});
test('preview respects target caps and ignores skills outside the target', () => {
  assert.equal(projectedCoverage(profile(), { changes: { design: { after: 5 }, extra: { after: 5 } } }), 88);
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
    assert.equal(options.headers['X-Requested-With'], 'CareerQuest');
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
