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
const { ROLES, INTERNAL_ROLES, isStaffRole, managesTeam, isHr, roleLabel } = await load('roles.mjs');
const render = (component, props, locale = 'ru') => renderToStaticMarkup(createElement(I18nProvider, { initialLocale: locale }, createElement(component, props)));
const authProps = { status: { setup_required: false, registration: 'invite', demo_enabled: false }, busy: false, error: '', onSubmit: async () => true, onRetry() {} };

test('normal login uses credentials and role chooser instead of a list of demo accounts', () => {
  const html = render(AuthView, authProps);
  assert.match(html, /name="username"/);
  assert.match(html, /type="password" autoComplete="current-password"[^>]*name="password"/);
  assert.match(html, /<select id="account-role" name="role">/);
  assert.match(html, /for="account-role">Роль аккаунта/);
  for (const role of ROLES) assert.match(html, new RegExp(`<option value="${role}"`));
  assert.match(html, /value="employee" selected/);
  assert.match(html, /Зарегистрироваться/);
  assert.doesNotMatch(html, /account-option|Демо-сотрудник|DEMO/);
  assert.match(html, /aria-label="Язык интерфейса"/);
});

test('first HR setup requests identity and a strong password without employee selection', () => {
  const html = render(AuthView, { ...authProps, initialMode: 'setup', status: { ...authProps.status, setup_required: true } });
  assert.match(html, /Создать HR-аккаунт/);
  assert.match(html, /name="display_name"/);
  assert.match(html, /autoComplete="new-password"/);
  assert.match(html, /minLength="12" maxLength="128"/);
  assert.doesNotMatch(html, /name="invite_code"/);
  assert.match(html, /Вернуться ко входу/);
});

test('uninitialized workspace still opens employee login with all roles and discoverable HR setup', () => {
  const html = render(AuthView, { ...authProps, status: { ...authProps.status, setup_required: true } });
  assert.match(html, /Первичная настройка HR/);
  assert.match(html, /value="employee" selected/);
  assert.doesNotMatch(html, /name="display_name"/);
  for (const role of ROLES) assert.match(html, new RegExp(`<option value="${role}"`));
});

test('registration selects all six roles, public clients supply a name and internal roles require an invitation', () => {
  for (const role of ROLES) {
    const html = render(AuthView, { ...authProps, initialMode: 'register', initialRole: role }, 'en');
    assert.match(html, new RegExp(`<option value="${role}" selected`));
    for (const option of ROLES) assert.match(html, new RegExp(`<option value="${option}"`));
    assert.match(html, /<fieldset>/);
    if (role === 'client') {
      assert.match(html, /<input(?=[^>]*name="display_name")(?=[^>]*required)[^>]*>/);
      assert.doesNotMatch(html, /name="invite_code"/);
      assert.match(html, /Clients can register without an invitation/);
    } else {
      assert.match(html, /<input(?=[^>]*name="invite_code")(?=[^>]*required)[^>]*>/);
      assert.doesNotMatch(html, /name="display_name"/);
    }
  }
});

test('authentication pages support English and Kazakh and expose backend errors accessibly', () => {
  const en = render(AuthView, { ...authProps, error: 'Invalid credentials' }, 'en');
  assert.match(en, /Welcome back/); assert.match(en, /Sign in/);
  assert.match(en, /role="alert"/); assert.match(en, /Invalid credentials/);
  assert.doesNotMatch(en, /С возвращением|Я сотрудник/);
  assert.match(en, /Sales · Customer Support · HR/);
  assert.match(en, /GROW AT YOUR OWN PACE/);
  const kk = render(AuthView, authProps, 'kk');
  assert.match(kk, /Қайта оралуыңызбен/); assert.match(kk, /Қызметкер/);
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

test('auth request serialization sends client identity without stale invitation and preserves exact internal role values', async t => {
  const calls = [];
  t.mock.method(globalThis, 'fetch', async (_path, options) => {
    const body = JSON.parse(options.body); calls.push(body);
    return new Response(JSON.stringify({ role: body.role, employee_id: null }));
  });
  const base = { username: 'synthetic', password: 'synthetic-test-password', display_name: 'Synthetic client', invite_code: 'do-not-send-for-client' };
  await authenticate('register', { ...base, role: 'client' });
  assert.deepEqual(calls[0], { username: base.username, password: base.password, role: 'client', display_name: base.display_name });
  for (const role of INTERNAL_ROLES) {
    await authenticate('register', { ...base, role });
    assert.deepEqual(calls.at(-1), { username: base.username, password: base.password, role, invite_code: base.invite_code });
    await authenticate('login', { ...base, role });
    assert.deepEqual(calls.at(-1), { username: base.username, password: base.password, role });
  }
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

test('role labels and personal access remain distinct in all languages, including clients and team readers', () => {
  const expected = { ru: ['Сотрудник', 'HR-специалист', 'Руководитель', 'Оператор', 'Супервизор', 'Клиент'], en: ['Employee', 'HR specialist', 'Manager', 'Operator', 'Supervisor', 'Client'], kk: ['Қызметкер', 'HR маманы', 'Басшы', 'Оператор', 'Супервизор', 'Клиент'] };
  for (const [locale, labels] of Object.entries(expected)) {
    assert.deepEqual(ROLES.map(role => roleLabel(role, locale)), labels);
    for (const role of ROLES) {
      const html = render(AccountView, { account: { role, employee_id: isStaffRole(role) ? 'OWN' : null, username: role, display_name: `Own ${role}` }, profile: { employee: { id: 'REPORT', name: 'Someone else' } }, onProfile() {}, onLogout() {}, busy: false }, locale);
      assert.ok(html.includes(`<span class="grade-chip">${roleLabel(role, locale)}</span>`));
      assert.doesNotMatch(html, /Someone else/);
      if (role === 'client') assert.doesNotMatch(html, /Open my trajectory|Открыть мою траекторию|Менің даму жолымды ашу/);
      if (locale === 'en' && managesTeam(role)) assert.match(html, /read-only profiles of direct reports/);
      if (locale === 'en' && role === 'client') assert.match(html, /Employee data is not accessible/);
    }
  }
  assert.deepEqual(ROLES.filter(isStaffRole), ['employee', 'manager', 'operator', 'supervisor']);
  assert.deepEqual(ROLES.filter(managesTeam), ['manager', 'supervisor']);
  assert.deepEqual(ROLES.filter(isHr), ['hr']);
});

test('HR invitation dropdown contains five internal roles and every staff role needs a profile', () => {
  for (const role of INTERNAL_ROLES) {
    const html = render(AccountsView, { accounts: [], people: [{ id: 'E1', name: 'Synthetic', role: 'Engineer' }], busy: '', run: async () => true, refresh: async () => {}, initialRole: role });
    for (const option of INTERNAL_ROLES) assert.match(html, new RegExp(`<option value="${option}"`));
    assert.doesNotMatch(html, /<option value="client"/);
    if (isStaffRole(role)) {
      assert.match(html, /name="employee_id" required/);
      assert.match(html, /class="primary" disabled/);
    } else assert.doesNotMatch(html, /name="employee_id"/);
  }
});
