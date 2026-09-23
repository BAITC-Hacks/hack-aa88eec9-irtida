// Isolated UI fixture server. No real backend, keys or employee data; never imported by production.
// npm run build && npm run test:preview -> http://127.0.0.1:8011
import http from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
const root = resolve('dist');
const accounts = [
  { id: 'rules', label: 'Демо: подбор по правилам', role: 'employee' },
  { id: 'ai', label: 'Демо: AI (имитация ответа)', role: 'employee' },
  { id: 'fallback', label: 'Демо: резервный алгоритм', role: 'employee' },
  { id: 'empty', label: 'Демо: нет доступных квестов', role: 'employee' },
  { id: 'unknown', label: 'Демо: неизвестные навыки', role: 'employee' },
  { id: 'slow', label: 'Демо: медленный ответ', role: 'employee' },
  { id: 'error', label: 'Демо: ошибка сервера', role: 'employee' },
  { id: 'hr', label: 'Демо: HR-специалист', role: 'hr' },
];
const states = new Map();
function state(id) { if (!states.has(id)) states.set(id, { done: false, recommendation: null }); return states.get(id); }
function profile(id) {
  const s = state(id); const level = s.done ? 3 : 2;
  const unknown = id === 'unknown';
  const employee = { id, name: 'Демо-сотрудник', role: 'Backend Engineer', grade: 'Middle', tenure_months: 36, skills: { design: level, python: 3, speaking: 1 } };
  const event = { id: 'design-lab', title: 'Архитектура сервиса: от идеи до решения', type: 'workshop', projected_coverage: unknown ? null : Math.round((Math.min(4, level + 1) + 4) / 11 * 100), critical_benefit: 1, changes: { design: { name: 'System Design', before: level, after: Math.min(4, level + 1), gain: 1 } }, evidence: [
    { factor: 'grade', text: 'Ваш текущий грейд Middle, следующая цель — Senior.' },
    { factor: 'skill_gap', text: `System Design: ${level} при требуемых 4 для Senior.` },
    { factor: 'requirements', text: 'Практикум закрывает один уровень разрыва по требованиям Senior.' },
    { factor: 'history', text: 'В истории есть пропуск клуба выступлений. Практикум предлагает другой формат.' },
  ] };
  return { employee, trajectory: { next_grade: id === 'empty' ? null : 'Senior', coverage: unknown || id === 'empty' ? null : Math.round((level + 4) / 11 * 100), status: id === 'empty' ? 'no_grade_rule' : unknown ? 'missing_skills' : 'ready', critical_requirements_met: unknown || id === 'empty' ? null : false, skills: id === 'empty' ? [] : [
    { id: 'design', name: 'System Design', level: unknown ? null : level, required: 4, gap: unknown ? null : 4 - level, critical: true },
    { id: 'python', name: 'Python', level: 3, required: 4, gap: 1, critical: false },
    { id: 'speaking', name: 'Public Speaking', level: 1, required: 3, gap: 2, critical: false },
  ] }, history: [...(s.done ? [{ id: 'done', event_id: event.id, title: event.title, status: 'completed', occurred_at: '2026-09-23', changes: { design: { name: 'System Design', before: 2, after: 3, gain: 1 } } }] : []), { id: 'miss', event_id: 'speaking-club', changes: null, title: 'Клуб публичных выступлений', status: 'missed', occurred_at: '2026-08-01' }], available: s.done || ['empty', 'unknown'].includes(id) ? [] : [event], recommendation: s.recommendation ? { ...s.recommendation, cached: true } : null };
}
const send = (res, code, data, headers = {}) => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', ...headers }); res.end(JSON.stringify(data)); };
http.createServer(async (req, res) => {
  try {
    const url = new URL(req.url, 'http://localhost');
    const path = url.pathname;
    if (!path.startsWith('/api/')) {
      const file = resolve(root, '.' + (path === '/' ? '/index.html' : path));
      if (!file.startsWith(root + sep)) return send(res, 403, { detail: 'Forbidden' });
      const content = await readFile(file);
      res.writeHead(200, { 'Content-Type': ({ '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml' })[extname(file)] ?? 'application/octet-stream' }); return res.end(content);
    }
    let body = ''; for await (const chunk of req) { body += chunk; if (body.length > 5_000_000) return send(res, 413, { detail: 'Too large' }); }
    const id = /cq_fixture=([^;]+)/.exec(req.headers.cookie ?? '')?.[1];
    if (path === '/api/v1/auth/demo-accounts') return send(res, 200, { enabled: true, accounts });
    if (path === '/api/v1/auth/demo') { const account = JSON.parse(body).account; if (!accounts.find(a => a.id === account)) return send(res, 400, { detail: 'Unknown test account' }); return send(res, 200, { role: account === 'hr' ? 'hr' : 'employee', employee_id: account === 'hr' ? null : account }, { 'Set-Cookie': `cq_fixture=${account}; HttpOnly; Path=/; SameSite=Lax` }); }
    if (!id) return send(res, 401, { detail: 'Sign in' });
    if (path === '/api/v1/auth/me') return send(res, 200, { role: id === 'hr' ? 'hr' : 'employee', employee_id: id === 'hr' ? null : id });
    if (path === '/api/v1/auth/logout') return send(res, 200, { ok: true }, { 'Set-Cookie': 'cq_fixture=; Max-Age=0; Path=/' });
    if (path === '/api/v1/employees') return send(res, 200, ['rules', 'empty', 'unknown'].map(i => ({ ...profile(i).employee, name: i === 'rules' ? 'Демо-сотрудник' : i === 'empty' ? 'Демо: нет требований' : 'Демо: неизвестный уровень' })));
    if (path === '/api/v1/hr/overview') return send(res, 200, { employee_count: 3, gaps: [{ id: 'design', total_gap: 2, name: 'System Design', affected: 1, eligible: 1, unknown: 1, percent: 100 }, { id: 'unknown', total_gap: 0, name: 'Навык без оценки', affected: 0, eligible: 0, unknown: 3, percent: null }], no_step: [{ id: 'empty', name: 'Демо: нет требований', reason: 'no_grade_rule', reason_detail: 'Не заданы требования следующего грейда.', blockers: {} }], participation: [{ id: 'lab', title: 'Архитектура сервиса: от идеи до решения', completed: state('rules').done ? 1 : 0, missed: 1, declined: 1, no_show: 0, dropped: 0, in_progress: 0, overdue: 0 }] });
    if (path === '/api/v1/imports') { if (id !== 'hr') return send(res, 403, { detail: 'HR only' }); const payload = JSON.parse(body); if (!payload.employees) return send(res, 422, { detail: [{ loc: ['body', 'employees'], msg: 'Отсутствует список профилей' }] }); return send(res, 200, { schema: 'demo-v1', dry_run: url.searchParams.get('dry_run') === 'true', employees_added: payload.employees.length, history_added: (payload.history ?? []).length }); }
    const m = path.match(/^\/api\/v1\/employees\/([^/]+)(.*)$/);
    if (m) {
      const [, person, suffix] = m;
      if (id !== 'hr' && id !== person) return send(res, 403, { detail: 'Forbidden' });
      const s = state(person);
      if (!suffix) return send(res, 200, profile(person));
      if (suffix === '/recommendations') {
        if (person === 'slow') await new Promise(r => setTimeout(r, 9000));
        if (person === 'error') return send(res, 503, { detail: 'Тестовая ошибка: сервис рекомендаций недоступен.' });
        const p = profile(person);
        const result = { items: p.available, mode: !p.available.length ? 'no_candidates' : person === 'ai' ? 'ai' : person === 'fallback' ? 'fallback' : 'rules', cached: !!s.recommendation, reason: person === 'fallback' ? 'Тестовая имитация тайм-аута провайдера.' : null, provider: person === 'ai' ? 'test-fixture' : null, model: person === 'ai' ? 'simulated-response' : null, elapsed_ms: 30 };
        s.recommendation = result; return send(res, 200, result);
      }
      if (suffix === '/events/design-lab/complete') { const already = s.done; s.done = true; s.recommendation = null; return send(res, 200, { profile: profile(person), already_completed: already }); }
    }
    send(res, 404, { detail: 'Not found in fixture server' });
  } catch { send(res, 400, { detail: 'Invalid test request' }); }
}).listen(8011, '127.0.0.1', () => console.log('FRONTEND TEST FIXTURES ONLY: http://127.0.0.1:8011 — no real AI or persistence'));
