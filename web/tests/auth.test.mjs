import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const load = path => import(pathToFileURL(join(process.env.CQ_TEST_BUILD, path)));
const { AuthView } = await load('components/AuthView.mjs');
const { AccountView } = await load('components/AccountView.mjs');
const { AccountsView } = await load('components/AccountsView.mjs');
const { CatalogView } = await load('components/CatalogView.mjs');
const { I18nProvider } = await load('i18n.mjs');
const { authenticate, api } = await load('api.mjs');
const render = (component, props, locale = 'ru') => renderToStaticMarkup(createElement(I18nProvider, { initialLocale: locale }, createElement(component, props)));
const authProps = { status: { setup_required: false, registration: 'invite', demo_enabled: false }, busy: false, error: '', onSubmit: async () => true, onRetry() {} };

test('normal login uses credentials and role chooser instead of a list of demo accounts', () => {
  const html = render(AuthView, authProps);
  assert.match(html, /name="username"/);
  assert.match(html, /type="password" autoComplete="current-password"[^>]*name="password"/);
  assert.match(html, /Я сотрудник/); assert.match(html, /Я HR/);
  assert.match(html, /Зарегистрироваться/);
  assert.doesNotMatch(html, /account-option|Демо-сотрудник|DEMO/);
  assert.match(html, /aria-label="Язык интерфейса"/);
});

test('first HR setup requests identity and a strong password without employee selection', () => {
  const html = render(AuthView, { ...authProps, status: { ...authProps.status, setup_required: true } });
  assert.match(html, /Создать HR-аккаунт/);
  assert.match(html, /name="display_name"/);
  assert.match(html, /autoComplete="new-password"/);
  assert.match(html, /minLength="12" maxLength="128"/);
  assert.doesNotMatch(html, /name="invite_code"/);
});

test('authentication pages support English and Kazakh and expose backend errors accessibly', () => {
  const en = render(AuthView, { ...authProps, error: 'Invalid credentials' }, 'en');
  assert.match(en, /Welcome back/); assert.match(en, /Sign in/);
  assert.match(en, /role="alert"/); assert.match(en, /Invalid credentials/);
  assert.doesNotMatch(en, /С возвращением|Я сотрудник/);
  assert.match(en, /Sales · Customer Support · HR/);
  assert.match(en, /GROW AT YOUR OWN PACE/);
  const kk = render(AuthView, authProps, 'kk');
  assert.match(kk, /Қайта оралуыңызбен/); assert.match(kk, /Қызметкермін/);
  assert.match(kk, /ӨЗ ҚАРҚЫНЫҢМЕН ӨС/);
  assert.doesNotMatch(kk, /РАСТИ В СВОЁМ РИТМЕ/);
});

test('auth request bodies match server contracts and login failures preserve the request fields', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (path, options) => {
    calls.push({ path, body: JSON.parse(options.body) });
    return new Response(JSON.stringify({ role: 'hr', employee_id: null, username: 'synthetic', display_name: 'Synthetic HR' }));
  });
  const request = { username: 'synthetic', password: 'synthetic-test-password', role: 'hr', display_name: 'Synthetic HR', invite_code: 'synthetic-invite' };
  const before = structuredClone(request);
  await authenticate('setup', request);
  await authenticate('login', request);
  await authenticate('register', request);
  assert.deepEqual(calls, [
    { path: '/api/v1/auth/setup', body: { username: request.username, password: request.password, display_name: request.display_name } },
    { path: '/api/v1/auth/login', body: { username: request.username, password: request.password, role: 'hr' } },
    { path: '/api/v1/auth/register', body: { username: request.username, password: request.password, role: 'hr', invite_code: request.invite_code } },
  ]);
  globalThis.fetch = async () => new Response('{"detail":"Invalid username, password or role"}', { status: 401 });
  await assert.rejects(authenticate('login', request), /Invalid username, password or role/);
  assert.deepEqual(request, before);
});

test('API uses selected language for requests and localized connection errors', async t => {
  globalThis.window = { localStorage: { getItem: () => 'kk' } };
  t.after(() => { delete globalThis.window; });
  t.mock.method(globalThis, 'fetch', async (_path, options) => {
    assert.equal(options.headers.get('Accept-Language'), 'kk');
    assert.equal(options.headers.get('X-Requested-With'), 'CareerQuest');
    return new Response('{}');
  });
  await api('/auth/status');
  globalThis.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(api('/auth/status'), /Сервермен байланыс жоқ/);
});

test('account screen displays the signed-in HR identity, never the selected employee identity', () => {
  const html = render(AccountView, { account: { role: 'hr', employee_id: null, username: 'hr-user', display_name: 'Own HR Name' }, profile: { employee: { name: 'Another Employee' } }, onProfile() {}, onLogout() {}, busy: false }, 'en');
  assert.match(html, /Own HR Name/); assert.match(html, /hr-user/);
  assert.doesNotMatch(html, /Another Employee|Open my trajectory/);
  assert.match(html, /Sign out/);
});

test('catalog exposes every server event including mandatory entries and every skill', () => {
  const catalog = { counts: { events: 40, skills: 60, grade_rules: 0 }, grade_rules: [],
    events: Array.from({ length: 40 }, (_, i) => ({ id: `synthetic-event-${i}`, title: `Synthetic activity ${i}`, type: 'workshop', roles: ['Engineer', 'Analyst'], grades: ['Middle'], mandatory: i === 0, effects: {} })),
    skills: Array.from({ length: 60 }, (_, i) => ({ id: `synthetic-skill-${i}`, name: `Synthetic skill ${i}`, kind: i % 2 ? 'soft' : 'hard' })) };
  const events = render(CatalogView, { catalog, kind: 'events', busy: false, refresh() {} }, 'en');
  assert.equal((events.match(/class="panel catalog-event"/g) ?? []).length, 40);
  assert.match(events, /Mandatory HR assignment/); assert.match(events, /Synthetic activity 39/);
  const skills = render(CatalogView, { catalog, kind: 'skills', busy: false, refresh() {} }, 'kk');
  assert.match(skills, /Дағдылар каталогы/); assert.match(skills, /Synthetic skill 59/);
});

test('HR invitations require a selected employee and exclude already linked profiles', () => {
  const html = render(AccountsView, { accounts: [{ id: 'account-1', username: 'first', display_name: 'First', role: 'employee', employee_id: 'E1', created_at: 0 }], people: [{ id: 'E1', name: 'First', role: 'Engineer' }, { id: 'E2', name: 'Second', role: 'Analyst' }], busy: '', run: async () => true, refresh: async () => {} }, 'en');
  assert.doesNotMatch(html, /<option value="E1"/);
  assert.match(html, /<option value="E2"/);
  assert.match(html, /class="primary" disabled=""/);
  assert.match(html, /Create invitation/);
});
