import { test } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { join } from 'node:path';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
const { ProfileView } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'components/ProfileView.mjs')));
const { HrView } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'components/HrView.mjs')));
const { ImportPanel } = await import(pathToFileURL(join(process.env.CQ_TEST_BUILD, 'components/ImportPanel.mjs')));

function profile() {
  return { employee: { id: 'SYNTHETIC', name: 'Synthetic employee', role: 'Engineer', grade: 'Middle', tenure_months: 24, skills: { design: 0 } },
    trajectory: { status: 'ready', coverage: 0, next_grade: 'Senior', critical_requirements_met: false,
      skills: [{ id: 'design', name: 'System Design', level: 0, required: 4, gap: 4, critical: true }] },
    history: [], available: [], recommendation: null };
}
function candidate() {
  return { id: 'EV_036', title: 'Synthetic session', type: 'meetup', changes: { design: { name: 'System Design', before: 0, after: 1, gain: 1 } },
    critical_benefit: 1, projected_coverage: 12, occurrence_id: '2026-10-02', session_date: '2026-10-02', evidence: [{ factor: 'next_level', text: 'Requirement gap' }] };
}
function renderProfile(p, overrides = {}) {
  return renderToStaticMarkup(createElement(ProfileView, { profile: p, recommendation: p.recommendation, section: 'profile', employee: true, busy: '', onRecommend() {}, onComplete() {}, onNavigate() {}, celebration: null, clearCelebration() {}, ...overrides }));
}

test('profile renders server critical flags and kit zero level without promoting at 100% coverage', () => {
  const p = profile();
  p.trajectory.coverage = 100; // Rounded coverage alone must never erase critical blockers.
  const html = renderProfile(p);
  assert.match(html, /critical-skill/);
  assert.match(html, /Критический/);
  assert.match(html, /Есть разрывы по критическим навыкам/);
  assert.match(html, /System Design: 0 из 4/);
  assert.match(html, /Покрытие навыков не означает автоматическое повышение/);
  assert.match(html, /Middle/);
  assert.doesNotMatch(html, /Вы повышены/);
  p.trajectory.critical_requirements_met = true;
  assert.match(renderProfile(p), /Требования по критическим навыкам выполнены/);
});

test('highest grade is a terminal trajectory without a broken recommendation or missing HR-rule warning', () => {
  const p = profile();
  p.employee.grade = 'Lead';
  p.trajectory = { status: 'highest_grade', coverage: null, next_grade: null, critical_requirements_met: null, skills: [] };
  const html = renderProfile(p);
  assert.match(html, /Достигнут максимальный грейд/);
  assert.doesNotMatch(html, /Подобрать квесты|Требования следующего грейда пока не заданы|HR ещё не добавил требования|Новая цель/);
  assert.match(renderProfile(p, { section: 'quests' }), /Следующий грейд в текущем каталоге не предусмотрен/);
});

test('quest renders occurrence date, critical benefit and server-calculated projection without recalculating', () => {
  const p = profile(); const event = candidate(); p.available = [event];
  p.recommendation = { items: [event], mode: 'rules', reason: null, cached: false, provider: null, model: null, elapsed_ms: 13 };
  const html = renderProfile(p);
  assert.match(html, /datetime="2026-10-02"/i);
  assert.match(html, /Критические навыки: закрывает 1 ур. разрыва/);
  assert.match(html, /Прогноз покрытия: 0% → 12%/); // UI's old formula would yield 25%.
  assert.match(html, /Время подбора: 13 мс/);
  assert.match(html, /Следующий уровень/);
  event.projected_coverage = null;
  assert.doesNotMatch(renderProfile(p), /Прогноз покрытия:/);
});

test('history keeps all kit statuses and renders an unknown future status verbatim', () => {
  const p = profile();
  const statuses = ['completed', 'in_progress', 'dropped', 'no_show', 'declined', 'overdue', 'missed', 'future_status'];
  p.history = statuses.map((status, i) => ({ id: String(i), event_id: 'event', title: `History ${i}`, status, occurred_at: '2026-09-01', changes: null }));
  const html = renderProfile(p, { section: 'history' });
  for (const status of statuses) assert.match(html, new RegExp(`value="${status}"`));
  assert.match(html, /Неявка/); assert.match(html, /Прекращено/); assert.match(html, /Просрочено/);
  assert.match(html, /class="status ">future_status/);
});

test('fallback and cached recommendation do not show AI provider/model as a live AI result', () => {
  const p = profile();
  p.recommendation = { items: [], mode: 'fallback', reason: 'AI unavailable', cached: true, provider: 'hidden-provider', model: 'hidden-model', elapsed_ms: 14 };
  const html = renderProfile(p);
  assert.match(html, /Сохранённый результат · AI недоступен · подбор по правилам/);
  assert.match(html, /AI unavailable/);
  assert.doesNotMatch(html, /hidden-provider|hidden-model/);
});

test('HR uses server no-step reason and shows seven nonoverlapping status columns', () => {
  const metrics = { employee_count: 1, gaps: [], no_step: [{ id: 'SYNTHETIC', name: 'Synthetic employee', reason: 'highest_grade', reason_detail: 'Server final grade explanation', blockers: {} }],
    participation: [{ id: 'event', title: 'Synthetic activity', completed: 1, in_progress: 2, dropped: 3, no_show: 4, declined: 5, overdue: 6, missed: 11 }] };
  const html = renderToStaticMarkup(createElement(HrView, { metrics, people: [], busy: '', openProfile() {}, refresh: async () => {}, onImported: async () => {}, run: async () => true }));
  assert.match(html, /Server final grade explanation/);
  for (const name of ['Завершено', 'В процессе', 'Прекращено', 'Неявка', 'Отказ от участия', 'Просрочено', 'Пропущено']) assert.ok(html.includes(`<th scope="col">${name}</th>`));
  assert.match(html, /<td><span>7<\/span><\/td>/); // missed excludes the four no_show rows.
});

test('initial import UI selects kit and keeps save disabled until validation', () => {
  const html = renderToStaticMarkup(createElement(ImportPanel, { busy: '', run: async () => true, onImported: async () => {} }));
  assert.match(html, /value="kit" selected/);
  assert.match(html, /aria-label="Файлы официального кита"/);
  assert.match(html, /type="file" multiple/);
  assert.match(html, /class="primary" disabled="">2. Загрузить данные/);
  assert.match(html, /Заменить исходные демо-данные официальным китом/);
});
