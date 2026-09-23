// Real browser + real FastAPI + isolated SQLite. No cloud, user browser or official data.
// Uses an installed Edge/Chrome, or CQ_BROWSER_CHANNEL for a Playwright browser.
import { chromium, expect } from '@playwright/test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join, dirname, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn } from 'node:child_process';
import { createServer } from 'node:net';
import { setTimeout as delay } from 'node:timers/promises';

const web = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const root = resolve(web, '..');
const buildRoot = join(web, '.test-build');
const results = join(web, 'test-results');
mkdirSync(buildRoot, { recursive: true }); mkdirSync(results, { recursive: true });
const temporary = mkdtempSync(join(buildRoot, 'browser-e2e-'));
const python = process.env.CQ_PYTHON ?? join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
assert.ok(existsSync(python), 'Create the repository .venv, or set CQ_PYTHON.');
const roles = ['Backend Engineer', 'Data Analyst', 'Product Manager'];
const employees = roles.map((role, i) => ({ id: `TEST_EMP_${i}`, name: `Synthetic employee ${i + 1}`, role, grade: 'Middle', tenure_months: 24, skills: { TEST_SKILL_0: 1 } }));
const bundle = {
  schema_version: 'demo-v1', employees,
  skills: Array.from({ length: 60 }, (_, i) => ({ id: `TEST_SKILL_${i}`, name: `Synthetic skill ${i}`, kind: i % 2 ? 'hard' : 'soft' })),
  events: Array.from({ length: 40 }, (_, i) => ({ id: `TEST_EVENT_${i}`, title: `Synthetic activity ${String(i).padStart(2, '0')}`, type: i % 2 ? 'course' : 'workshop', roles: [roles[i % 3]], grades: ['Middle'], effects: { TEST_SKILL_0: { gain: 1, max_level: 5 } } })),
  grade_rules: roles.map(role => ({ role, grade: 'Middle', next_grade: 'Senior', requirements: { TEST_SKILL_0: 4 } })), history: [],
};
const fixture = join(temporary, 'synthetic.json');
writeFileSync(fixture, JSON.stringify(bundle));
// The kit-shaped synthetic fixture also exercises scoped manager access.
const meta = { dataset: 'Career Quest', version: '1.0', as_of_date: '2026-10-01' };
const grades = ['Junior', 'Middle', 'Senior', 'Lead'];
const kit = {
  'skills.json': JSON.stringify({ meta, proficiency_scale: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i), `Level ${i}`])),
    skills: bundle.skills.map(skill => ({ skill_id: skill.id, name: skill.name, type: skill.kind, category: 'Synthetic', description: 'Synthetic test skill' })),
    role_profiles: roles.flatMap(role => grades.map((grade, i) => ({ role, grade, required_skills: { TEST_SKILL_0: [1, 2, 4, 5][i] }, critical_skills: ['TEST_SKILL_0'] }))) }),
  'employees.json': JSON.stringify({ meta, employees: employees.map((person, i) => ({ employee_id: person.id, full_name: person.name, department: 'Synthetic', role: person.role, grade: i > 0 ? 'Lead' : person.grade, manager_id: i === 0 ? 'TEST_EMP_1' : null,
    hire_date: '2024-10-01', tenure_months: person.tenure_months, work_format: 'remote', preferred_language: 'en', career_goal: i > 0 ? null : { target_role: person.role, target_grade: 'Senior' }, skills: person.skills, last_review_date: '2026-09-01' })) }),
  'events.json': JSON.stringify({ meta, events: bundle.events.map(event => ({ event_id: event.id, title: event.title, description: 'Synthetic event', type: event.type, format: 'online', duration_hours: 2, mandatory: false, target_roles: event.roles, target_grades: event.grades,
    develops_skills: [{ skill_id: 'TEST_SKILL_0', gain: 1, max_level: 5 }], prerequisites: {}, upcoming_sessions: ['2026-10-05'] })) }),
  'activity_history.csv': 'record_id,employee_id,event_id,date,due_date,status,completion_pct,score,feedback_rating,assigned_by\n',
};
const kitPaths = Object.entries(kit).map(([name, contents]) => { const file = join(temporary, name); writeFileSync(file, contents); return file; });
const password = 'Synthetic-e2e-password-2026'; // Non-secret fixture only; isolated temporary database.
const messages = [];
let backend; let browser; let page; let backendLogs = '';
const reservation = createServer();
await new Promise((done, reject) => { reservation.once('error', reject); reservation.listen(0, '127.0.0.1', done); });
const port = reservation.address().port;
await new Promise(done => reservation.close(done));
const origin = `http://127.0.0.1:${port}`;
async function stop() {
  if (!backend || backend.exitCode !== null) return;
  const stopped = new Promise(done => backend.once('exit', done));
  backend.stdin.end(); await Promise.race([stopped, delay(5000)]);
  if (backend.exitCode === null) { backend.kill('SIGKILL'); await stopped; }
}
const sideButton = name => page.locator('.sidebar nav').getByRole('link', { name, exact: true });
const idle = async () => { await expect(page.locator('.working')).toHaveCount(0); };
const language = async locale => { await page.locator('.language-select select').selectOption(locale); await idle(); await expect(page.locator('html')).toHaveAttribute('lang', locale); };
async function apiGet(path) { const response = await page.request.get(`${origin}/api/v1${path}`, { headers: { 'Accept-Language': 'en' } }); assert.equal(response.status(), 200); return response.json(); }

try {
  const launcher = "import sys,threading,uvicorn; server=uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=int(sys.argv[1]),access_log=False,log_level='warning')); threading.Thread(target=lambda:(sys.stdin.read(),setattr(server,'should_exit',True)),daemon=True).start(); server.run()";
  backend = spawn(python, ['-c', launcher, String(port)], { cwd: join(root, 'server'), windowsHide: true,
    env: { ...process.env, DATABASE_URL: `sqlite:///${join(temporary, 'e2e.db').replaceAll('\\', '/')}`, CAREER_QUEST_AUTO_IMPORT: 'false', CAREER_QUEST_KIT_DIR: '', DEMO_MODE: 'false', AI_PROVIDER: 'rules', OPENAI_API_KEY: '', NVIDIA_API_KEY: '', NVIDIA_AI_MOCK: 'true', AI_DATA_POLICY_APPROVED: 'false', ALLOWED_ORIGINS: origin, COOKIE_SECURE: 'false' }, stdio: ['pipe', 'pipe', 'pipe'] });
  for (const stream of [backend.stdout, backend.stderr]) stream.on('data', chunk => { backendLogs = (backendLogs + chunk).slice(-5000); });
  for (let attempt = 0; attempt < 100; attempt++) {
    if (backend.exitCode !== null) throw new Error(`Backend exited: ${backendLogs}`);
    try { if ((await fetch(`${origin}/api/v1/health`)).ok) break; } catch { /* Await this test's backend only. */ }
    if (attempt === 99) throw new Error(`Backend not ready: ${backendLogs}`);
    await delay(100);
  }
  const channel = process.env.CQ_BROWSER_CHANNEL ?? (process.platform === 'win32' ? 'msedge' : 'chrome');
  browser = await chromium.launch({ channel, headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, locale: 'ru-RU' });
  page = await context.newPage();
  page.on('pageerror', error => messages.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error' && !/Failed to load resource.*(?:401|404)/.test(message.text())) messages.push(`console: ${message.text()}`); });
  await page.goto(origin);
  await expect(page.getByRole('heading', { name: 'С возвращением' })).toBeVisible();
  await expect(page.locator('[name=role] option')).toHaveCount(6);
  await expect(page.locator('[name=role]')).toHaveValue('employee');
  await page.screenshot({ path: join(results, '00-login-roles.png'), fullPage: true });
  await page.getByRole('button', { name: 'Первичная настройка HR', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Создайте рабочее пространство' })).toBeVisible();
  await page.screenshot({ path: join(results, '01-setup-desktop.png'), fullPage: true });
  await page.locator('[name=display_name]').fill('Synthetic HR');
  await page.locator('[name=username]').fill('synthetic-hr');
  await page.locator('[name=password]').fill(password);
  await page.getByRole('button', { name: 'Создать HR-аккаунт', exact: true }).click(); await idle();
  await expect(sideButton('Команда и аналитика')).toBeVisible();

  // UI import remains a two-step transaction, and populates all workspace routes.
  await sideButton('Импорт данных').click();
  await page.getByLabel('Формат импорта').selectOption('demo');
  await page.getByLabel('Файл с профилями и историей').setInputFiles(fixture);
  await expect(page.getByRole('button', { name: '2. Загрузить данные' })).toBeDisabled();
  await page.getByRole('button', { name: '1. Проверить файлы' }).click(); await idle();
  assert.equal((await apiGet('/employees')).length, 0);
  await expect(page.getByRole('button', { name: '2. Загрузить данные' })).toBeEnabled();
  // Changing source format invalidates the approved demo preview.
  await page.getByLabel('Формат импорта').selectOption('kit');
  await expect(page.getByRole('button', { name: '2. Загрузить данные' })).toBeDisabled();
  await page.getByLabel('Файлы официального кита').setInputFiles(kitPaths);
  await page.getByRole('button', { name: '1. Проверить файлы' }).click(); await idle();
  await expect(page.getByRole('button', { name: '2. Загрузить данные' })).toBeEnabled();
  await page.getByRole('button', { name: '2. Загрузить данные' }).click(); await idle();
  assert.equal((await apiGet('/employees')).length, 3);
  await sideButton('Каталог активностей').click();
  await expect(page.locator('.catalog-event')).toHaveCount(40);
  await page.locator('.catalog-filters input').fill('Synthetic activity 00');
  await expect(page.locator('.catalog-event')).toHaveCount(1);
  await page.locator('.catalog-filters input').fill('');
  await expect(page.locator('.catalog-event')).toHaveCount(40);
  await page.screenshot({ path: join(results, '02-catalog-desktop.png'), fullPage: false });
  await sideButton('Каталог навыков').click();
  await expect(page.locator('.skills-catalog > article')).toHaveCount(60);
  await sideButton('Команда и аналитика').click();
  await expect(page.locator('.team-role-summary > span')).toHaveCount(3);
  await page.locator('.people-grid').getByRole('button').first().click(); await idle();
  await expect(page.locator('.profile-tabs a')).toHaveCount(5);
  await page.locator('.profile-tabs').getByRole('link', { name: 'История', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'История вашего пути' })).toBeVisible();
  await expect(page).toHaveURL(/#\/employees\/TEST_EMP_0\/history$/);
  await expect(page.locator('.breadcrumb a[aria-current=page]')).toHaveAttribute('href', '#/employees/TEST_EMP_0/history');
  const selectedHref = await page.locator('.breadcrumb a[aria-current=page]').getAttribute('href');
  assert.equal(selectedHref, '#/employees/TEST_EMP_0/history');
  await page.locator('.breadcrumb a[aria-current=page]').click();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'История вашего пути' })).toBeVisible();
  await expect(page.locator('.hr-profile-toolbar select')).toHaveValue('TEST_EMP_0');
  await page.locator('.profile-tabs').getByRole('link', { name: 'Навыки', exact: true }).click();
  await expect(page).toHaveURL(/#\/employees\/TEST_EMP_0\/skills$/); await idle();
  await page.goBack(); await expect(page.getByRole('heading', { name: 'История вашего пути' })).toBeVisible();
  await page.goForward(); await expect(page).toHaveURL(/#\/employees\/TEST_EMP_0\/skills$/); await idle();
  const directPage = await context.newPage();
  await directPage.goto(`${origin}/${selectedHref}`);
  await expect(directPage.getByRole('heading', { name: 'История вашего пути' })).toBeVisible();
  await expect(directPage.locator('.hr-profile-toolbar select')).toHaveValue('TEST_EMP_0');
  await directPage.close();

  await page.getByRole('link', { name: 'Открыть мой аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic HR', exact: true })).toBeVisible();
  await page.locator('.breadcrumb').getByRole('link').first().click();
  await sideButton('Аккаунты и доступ').click();
  await page.locator('.invitation-form select').nth(1).selectOption('TEST_EMP_0');
  await page.getByRole('button', { name: 'Создать приглашение' }).click(); await idle();
  const invite = (await page.locator('.invitation-result > code').textContent()).trim();
  assert.ok(invite.length >= 32);
  // Synthetic management relationship was imported through the real kit API.
  const managerInviteResponse = await page.request.post(`${origin}/api/v1/hr/invitations`, { headers: { 'X-Requested-With': 'CareerQuest' }, data: { role: 'manager', employee_id: 'TEST_EMP_1' } });
  assert.equal(managerInviteResponse.status(), 200);
  const managerInvite = (await managerInviteResponse.json()).invite_code;
  await page.locator('.sidebar').getByRole('button', { name: 'Выйти из аккаунта' }).click(); await idle();

  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click();
  await page.locator('[name=username]').fill('synthetic-employee');
  await page.locator('[name=password]').fill(password);
  await page.locator('[name=invite_code]').fill(invite);
  await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click(); await idle();
  await expect(sideButton('Мой путь')).toBeVisible();
  const beforePractice = await apiGet('/employees/TEST_EMP_0');
  await page.locator('.personalization-panel').getByRole('button', { name: 'Создать персональную практику' }).click(); await idle();
  await expect(page.locator('.personalization-panel')).toContainText('Локальный пример без запроса к NVIDIA');
  await expect(page.locator('.personalization-panel .quest-card')).toHaveCount(3);
  assert.deepEqual((await apiGet('/employees/TEST_EMP_0')).employee.skills, beforePractice.employee.skills);
  const before = await apiGet('/employees/TEST_EMP_0');
  await sideButton('Мои квесты').click();
  await page.getByRole('button', { name: 'Подобрать квесты', exact: true }).click(); await idle();
  await expect(page.locator('.quests-section .mode-banner')).toContainText('Подбор по правилам');
  await sideButton('Мой путь').click();
  await expect(page.locator('.hero-next-step')).toBeVisible();
  await page.screenshot({ path: join(results, '04-next-step-benefit.png'), fullPage: false });
  await sideButton('Мои квесты').click();
  await page.locator('.quest-list').getByRole('button', { name: 'Отметить выполненным', exact: true }).first().click();
  // A browser Back while a real mutation response is pending must queue only GETs.
  let releaseCompletion; let completionReceived; let completionPosts = 0;
  const release = new Promise(resolve => { releaseCompletion = resolve; });
  const received = new Promise(resolve => { completionReceived = resolve; });
  const completionUrl = '**/api/v1/employees/TEST_EMP_0/events/*/complete';
  await page.route(completionUrl, async route => {
    completionPosts++;
    const response = await route.fetch();
    completionReceived(); await release;
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: 'Да, завершить', exact: true }).click();
  await received;
  await page.goBack(); await expect(page).toHaveURL(/#\/employees\/TEST_EMP_0\/profile$/);
  releaseCompletion();
  await expect(page.locator('.journey-hero')).toBeVisible(); await idle();
  await expect(page.locator('.celebration')).toBeVisible();
  assert.equal(completionPosts, 1, 'Back must never repeat a completion POST');
  await page.unroute(completionUrl);
  await sideButton('Мои квесты').click();

  const after = await apiGet('/employees/TEST_EMP_0');
  assert.equal(after.employee.skills.TEST_SKILL_0, before.employee.skills.TEST_SKILL_0 + 1);
  assert.equal(after.employee.grade, 'Middle');
  assert.equal(after.history.length, before.history.length + 1);
  await page.reload(); await idle();
  await expect(page).toHaveURL(/#\/employees\/TEST_EMP_0\/quests$/);
  await expect(page.locator('.grade-chip')).toContainText('Middle');
  await language('en');
  await expect(sideButton('My journey')).toBeVisible();
  await page.getByRole('link', { name: 'Open my account' }).click();
  await expect(page.getByRole('heading', { name: 'My account', exact: true })).toBeVisible();
  await language('kk');
  await expect(page.getByRole('heading', { name: 'Менің аккаунтым', exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: join(results, '03-account-phone-kk.png'), fullPage: true });
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1), 'Phone viewport must not overflow horizontally');
  await language('ru'); await page.setViewportSize({ width: 1440, height: 1000 });
  await sideButton('Мой путь').click();
  await page.screenshot({ path: join(results, '04-employee-desktop.png'), fullPage: false });
  await page.locator('.sidebar').getByRole('button', { name: 'Выйти из аккаунта' }).click(); await idle();
  // Invalid credentials preserve form fields; the existing account still logs in.
  await page.locator('[name=username]').fill('synthetic-employee');
  await page.locator('[name=password]').fill('Incorrect-synthetic-password');
  await page.getByRole('button', { name: 'Войти', exact: true }).click(); await idle();
  await expect(page.locator('.auth-error')).toBeVisible();
  await expect(page.locator('[name=username]')).toHaveValue('synthetic-employee');
  await expect(page.locator('[name=password]')).toHaveValue('Incorrect-synthetic-password');
  await page.locator('[name=password]').fill(password);
  await page.getByRole('button', { name: 'Войти', exact: true }).click(); await idle();
  await expect(sideButton('Мой путь')).toBeVisible();
  await page.locator('.sidebar').getByRole('button', { name: 'Выйти из аккаунта' }).click(); await idle();
  await page.locator('[name=role]').selectOption('manager');
  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click();
  await page.locator('[name=username]').fill('synthetic-manager');
  await page.locator('[name=password]').fill(password);
  await page.locator('[name=invite_code]').fill(managerInvite);
  await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click();
  await expect(sideButton('Мой путь')).toBeVisible();
  await expect(page).toHaveURL(/#\/employees\/TEST_EMP_1\/profile$/);
  await sideButton('Команда и аналитика').click();
  await expect(page.locator('.people-grid > button')).toHaveCount(1);
  await expect(page.locator('.page-heading .eyebrow')).toContainText('Руководитель');
  await expect(sideButton('Импорт данных')).toHaveCount(0);
  await page.locator('.people-grid > button').click();
  await expect(page.locator('.hr-profile-toolbar select')).toHaveValue('TEST_EMP_0');
  await page.locator('.profile-tabs').getByRole('link', { name: 'Мои квесты', exact: true }).click();
  await expect(page.locator('.quest-catalog')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Подобрать квесты', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Отметить выполненным', exact: true })).toHaveCount(0);
  await page.reload();
  await expect(page.locator('.hr-profile-toolbar select')).toHaveValue('TEST_EMP_0');
  await page.screenshot({ path: join(results, '05-manager-report-readonly.png'), fullPage: false });
  await sideButton('Мой путь').click();
  await expect(page).toHaveURL(/#\/employees\/TEST_EMP_1\/profile$/);
  await page.locator('.sidebar').getByRole('button', { name: 'Выйти из аккаунта' }).click(); await idle();
  // Public client registration creates an account only, with no staff data requests.
  const clientRequests = [];
  const watchClient = request => { if (/\/api\/v1\/(employees|team|hr|catalog)(?:\/|$)/.test(new URL(request.url()).pathname)) clientRequests.push(request.url()); };
  page.on('request', watchClient);
  await page.locator('[name=role]').selectOption('client');
  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click();
  await expect(page.locator('[name=invite_code]')).toHaveCount(0);
  await page.locator('[name=display_name]').fill('Synthetic client');
  await page.locator('[name=username]').fill('synthetic-client');
  await page.locator('[name=password]').fill(password);
  await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic client', exact: true })).toBeVisible();
  await expect(page).toHaveURL(/#\/account$/);
  await expect(page.locator('.sidebar nav a')).toHaveCount(1);
  await expect(sideButton('Личный кабинет')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Открыть мою траекторию' })).toHaveCount(0);
  await page.evaluate(() => { window.location.hash = '#/catalog'; });
  await expect(page.getByRole('alert')).toContainText('Этот раздел недоступен');
  await expect(page.locator('.catalog-event')).toHaveCount(0);
  await page.getByRole('link', { name: 'На главную', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic client', exact: true })).toBeVisible();
  await page.reload();
  await expect(sideButton('Личный кабинет')).toBeVisible();
  assert.deepEqual(clientRequests, []);
  page.off('request', watchClient);
  await page.screenshot({ path: join(results, '06-client-cabinet.png'), fullPage: false });
  assert.deepEqual(messages, []);
  console.log('PASS browser E2E: explicit HR setup, demo preview + kit import, 5 HR pages, 40 events, 60 skills, 6 roles, invitation, registration, password login, NVIDIA mock practice without skill mutation, real breadcrumb links, selected profile reload/direct URL/back/forward, own account, completion persistence + Back during POST without replay, manager scoped team + read-only report, public client isolation, ru/en/kk, desktop + phone, no JavaScript errors.');
  console.log(`Screenshots: ${results}`);
} catch (error) {
  if (page) await page.screenshot({ path: join(results, 'failure.png'), fullPage: true }).catch(() => {});
  if (page) console.error('Visible alerts:', await page.getByRole('alert').allTextContents().catch(() => []));
  console.error(error); process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stop();
  const resolved = resolve(temporary);
  if (!resolved.startsWith(resolve(buildRoot) + sep)) throw new Error('Unsafe test cleanup path');
  rmSync(resolved, { recursive: true, force: true });
}
