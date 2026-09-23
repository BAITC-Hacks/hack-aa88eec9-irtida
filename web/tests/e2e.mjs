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
const sideButton = name => page.locator('.sidebar nav').getByRole('button', { name, exact: true });
const idle = async () => { await expect(page.locator('.working')).toHaveCount(0); };
const language = async locale => { await page.locator('.language-select select').selectOption(locale); await idle(); await expect(page.locator('html')).toHaveAttribute('lang', locale); };
async function apiGet(path) { const response = await page.request.get(`${origin}/api/v1${path}`, { headers: { 'Accept-Language': 'en' } }); assert.equal(response.status(), 200); return response.json(); }

try {
  const launcher = "import sys,threading,uvicorn; server=uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port=int(sys.argv[1]),access_log=False,log_level='warning')); threading.Thread(target=lambda:(sys.stdin.read(),setattr(server,'should_exit',True)),daemon=True).start(); server.run()";
  backend = spawn(python, ['-c', launcher, String(port)], { cwd: join(root, 'server'), windowsHide: true,
    env: { ...process.env, DATABASE_URL: `sqlite:///${join(temporary, 'e2e.db').replaceAll('\\', '/')}`, CAREER_QUEST_AUTO_IMPORT: 'false', CAREER_QUEST_KIT_DIR: '', DEMO_MODE: 'false', AI_PROVIDER: 'rules', OPENAI_API_KEY: '', NVIDIA_API_KEY: '', AI_DATA_POLICY_APPROVED: 'false', ALLOWED_ORIGINS: origin, COOKIE_SECURE: 'false' }, stdio: ['pipe', 'pipe', 'pipe'] });
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
  await expect(page.locator('.profile-tabs button')).toHaveCount(5);
  await page.locator('.profile-tabs').getByRole('button', { name: 'История', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'История вашего пути' })).toBeVisible();
  await page.getByRole('button', { name: 'Открыть мой аккаунт' }).click();
  await expect(page.getByRole('heading', { name: 'Synthetic HR', exact: true })).toBeVisible();
  await page.locator('.breadcrumb').getByRole('button').first().click();
  await sideButton('Аккаунты и доступ').click();
  await page.locator('.invitation-form select').nth(1).selectOption('TEST_EMP_0');
  await page.getByRole('button', { name: 'Создать приглашение' }).click(); await idle();
  const invite = (await page.locator('.invitation-result > code').textContent()).trim();
  assert.ok(invite.length >= 32);
  await page.locator('.sidebar').getByRole('button', { name: 'Выйти из аккаунта' }).click(); await idle();

  await page.getByRole('button', { name: 'Зарегистрироваться', exact: true }).click();
  await page.locator('[name=username]').fill('synthetic-employee');
  await page.locator('[name=password]').fill(password);
  await page.locator('[name=invite_code]').fill(invite);
  await page.getByRole('button', { name: 'Создать аккаунт', exact: true }).click(); await idle();
  await expect(sideButton('Мой путь')).toBeVisible();
  const before = await apiGet('/employees/TEST_EMP_0');
  await sideButton('Мои квесты').click();
  await page.getByRole('button', { name: 'Подобрать квесты', exact: true }).click(); await idle();
  await expect(page.locator('.mode-banner')).toContainText('Подбор по правилам');
  await page.locator('.quest-list').getByRole('button', { name: 'Отметить выполненным', exact: true }).first().click();
  await page.getByRole('button', { name: 'Да, завершить', exact: true }).click(); await idle();
  await expect(page.locator('.celebration')).toBeVisible();
  const after = await apiGet('/employees/TEST_EMP_0');
  assert.equal(after.employee.skills.TEST_SKILL_0, before.employee.skills.TEST_SKILL_0 + 1);
  assert.equal(after.employee.grade, 'Middle');
  assert.equal(after.history.length, before.history.length + 1);
  await page.reload(); await idle();
  await expect(page.locator('.grade-chip')).toContainText('Middle');
  await language('en');
  await expect(sideButton('My journey')).toBeVisible();
  await page.getByRole('button', { name: 'Open my account' }).click();
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
  assert.deepEqual(messages, []);
  console.log('PASS browser E2E: setup, two-step import, 5 HR pages, 40 events, 60 skills, role diversity, invitation, registration, password login, own account, completion persistence, ru/en/kk, desktop + phone, no JavaScript errors.');
  console.log(`Screenshots: ${results}`);
} catch (error) {
  if (page) await page.screenshot({ path: join(results, 'failure.png'), fullPage: true }).catch(() => {});
  console.error(error); process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  await stop();
  const resolved = resolve(temporary);
  if (!resolved.startsWith(resolve(buildRoot) + sep)) throw new Error('Unsafe test cleanup path');
  rmSync(resolved, { recursive: true, force: true });
}
