// Career Quest — фронтенд без сборки и внешних зависимостей.

async function api(path, { role = 'hr', employeeId = null, method = 'GET', body = null } = {}) {
  const headers = { 'X-Role': role };
  if (employeeId) headers['X-Employee-Id'] = employeeId;
  if (body) headers['Content-Type'] = 'application/json';
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : null });
  let data = null;
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) {
    const msg = (data && data.error) ? data.error : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === 'class') node.className = v;
    else if (k === 'html') node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child == null) continue;
    node.appendChild(typeof child === 'string' ? document.createTextNode(child) : child);
  }
  return node;
}

const GRADE_ORDER = ['Junior', 'Middle', 'Senior', 'Lead'];

// ---------------------------------------------------------------------------
// СОТРУДНИК
// ---------------------------------------------------------------------------
async function loadEmployeeView(employeeId) {
  const content = document.getElementById('content');
  content.innerHTML = '';
  content.appendChild(el('div', { class: 'loading' }, 'Загрузка профиля…'));

  try {
    const [profile, recs] = await Promise.all([
      api(`/api/employees/${employeeId}`, { role: 'employee', employeeId }),
      api(`/api/employees/${employeeId}/recommendations`, { role: 'employee', employeeId }),
    ]);
    renderEmployeeView(employeeId, profile, recs);
  } catch (e) {
    content.innerHTML = '';
    content.appendChild(el('div', { class: 'card' }, el('div', { class: 'error' }, 'Не удалось загрузить профиль: ' + e.message)));
  }
}

function renderEmployeeView(employeeId, profile, recs) {
  const content = document.getElementById('content');
  content.innerHTML = '';
  const emp = profile.employee;

  // --- карточка профиля ---
  const head = el('div', { class: 'profile-head' }, [
    el('div', {}, [
      el('h1', {}, emp.name),
      el('div', { class: 'meta' }, [
        el('span', { class: 'badge' }, emp.role),
        el('span', { class: 'badge grade' }, emp.grade),
        el('span', { class: 'badge' }, `стаж: ${emp.tenure_months} мес.`),
        profile.target_grade ? el('span', { class: 'badge' }, `цель: ${profile.target_grade}`) : null,
      ]),
    ]),
  ]);
  content.appendChild(el('div', { class: 'card' }, head));

  // --- разрывы по навыкам (траектория к следующему грейду) ---
  const gapsCard = el('div', { class: 'card' });
  gapsCard.appendChild(el('h2', {}, profile.target_grade
    ? `Разрывы навыков до грейда ${profile.target_grade}`
    : 'Максимальный грейд — разрывов до следующего уровня нет'));
  if (profile.skill_gaps.length === 0) {
    gapsCard.appendChild(el('div', { class: 'empty' }, 'Все требования текущего трека закрыты.'));
  } else {
    profile.skill_gaps.slice(0, 12).forEach((g) => {
      const pct = g.required_level ? Math.min(100, (g.current_level / g.required_level) * 100) : 0;
      const row = el('div', { class: 'skill-bar-row' }, [
        el('div', {}, g.skill_name),
        el('div', { class: 'skill-bar-track' }, [
          el('div', { class: 'skill-bar-fill', style: `width:${pct}%` }),
        ]),
        el('div', { class: 'skill-gap-val' }, `${g.current_level}/${g.required_level}`),
      ]);
      gapsCard.appendChild(row);
    });
  }
  content.appendChild(gapsCard);

  // --- рекомендации ---
  const recCard = el('div', { class: 'card' });
  recCard.appendChild(el('h2', {}, 'Рекомендованные следующие шаги'));
  if (!recs.recommendations || recs.recommendations.length === 0) {
    recCard.appendChild(el('div', { class: 'empty' }, recs.message || 'Нет активных рекомендаций.'));
  } else {
    recs.recommendations.forEach((r) => {
      const card = el('div', { class: 'rec-card' });
      card.appendChild(el('div', { class: 'title-row' }, [
        el('strong', {}, r.event_name),
        el('button', { 'data-event': r.event_id }, 'Отметить выполненным'),
      ]));
      card.appendChild(el('div', { class: 'factors' }, [
        el('span', { class: 'badge' }, r.event_type),
        el('span', { class: 'badge' }, `навык: ${r.skill_name}`),
        el('span', { class: 'badge' }, `разрыв: ${r.gap}`),
        el('span', { class: 'badge' }, `score: ${r.score}`),
      ]));
      card.appendChild(el('div', { class: 'rationale' }, 'Почему: ' + r.rationale));
      card.querySelector('button').addEventListener('click', async (ev) => {
        ev.target.disabled = true;
        ev.target.textContent = 'Сохраняем…';
        try {
          await api(`/api/employees/${employeeId}/complete`, {
            role: 'employee', employeeId, method: 'POST', body: { event_id: r.event_id },
          });
          await loadEmployeeView(employeeId);
        } catch (e) {
          ev.target.disabled = false;
          ev.target.textContent = 'Ошибка, повторить';
        }
      });
      recCard.appendChild(card);
    });
  }
  content.appendChild(recCard);

  // --- пройденные активности ---
  const histCard = el('div', { class: 'card' });
  histCard.appendChild(el('h2', {}, 'Пройденные активности'));
  if (profile.completed_activities.length === 0) {
    histCard.appendChild(el('div', { class: 'empty' }, 'Пока нет завершённых активностей.'));
  } else {
    profile.completed_activities.slice().reverse().forEach((a) => {
      histCard.appendChild(el('div', { class: 'timeline-item' }, [
        el('span', {}, a.event_name),
        el('span', { class: 'month' }, `мес. ${a.month}`),
      ]));
    });
  }
  content.appendChild(histCard);
}

// ---------------------------------------------------------------------------
// HR
// ---------------------------------------------------------------------------
async function loadHrView() {
  await Promise.all([
    loadOverview(),
    loadLaggingSkills(),
    loadNoStep(),
    loadParticipation(),
  ]);
  document.getElementById('importBtn').addEventListener('click', handleImport);
}

async function loadOverview() {
  const body = document.getElementById('overviewBody');
  try {
    const data = await api('/api/hr/overview', { role: 'hr' });
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'row' }, [
      el('span', { class: 'badge' }, `сотрудников: ${data.total_employees}`),
      el('span', { class: 'badge' }, `событий: ${data.total_events}`),
      el('span', { class: 'badge' }, `записей истории: ${data.total_history_rows}`),
      ...Object.entries(data.by_grade).map(([g, c]) => el('span', { class: 'badge grade' }, `${g}: ${c}`)),
    ]));
  } catch (e) {
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'error' }, e.message));
  }
}

async function loadLaggingSkills() {
  const body = document.getElementById('laggingBody');
  try {
    const data = await api('/api/hr/lagging-skills', { role: 'hr' });
    body.innerHTML = '';
    const table = el('table', {}, [
      el('thead', {}, el('tr', {}, [el('th', {}, 'Навык'), el('th', {}, 'Ниже требования'), el('th', {}, '%')])),
    ]);
    const tbody = el('tbody');
    data.slice(0, 12).forEach((r) => {
      tbody.appendChild(el('tr', {}, [
        el('td', {}, r.skill_name),
        el('td', {}, `${r.below_requirement} / ${r.total_applicable}`),
        el('td', {}, `${Math.round(r.lagging_share * 100)}%`),
      ]));
    });
    table.appendChild(tbody);
    body.appendChild(table);
  } catch (e) {
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'error' }, e.message));
  }
}

async function loadNoStep() {
  const body = document.getElementById('noStepBody');
  try {
    const data = await api('/api/hr/no-next-step', { role: 'hr' });
    body.innerHTML = '';
    if (data.length === 0) {
      body.appendChild(el('div', { class: 'empty' }, 'У всех сотрудников есть рекомендованный шаг.'));
      return;
    }
    const table = el('table', {}, [
      el('thead', {}, el('tr', {}, [el('th', {}, 'Сотрудник'), el('th', {}, 'Роль / грейд'), el('th', {}, 'Причина')])),
    ]);
    const tbody = el('tbody');
    data.slice(0, 15).forEach((r) => {
      tbody.appendChild(el('tr', {}, [
        el('td', {}, `${r.name} (${r.employee_id})`),
        el('td', {}, `${r.role} / ${r.grade}`),
        el('td', {}, r.reason),
      ]));
    });
    table.appendChild(tbody);
    body.appendChild(table);
    if (data.length > 15) body.appendChild(el('p', { class: 'hint' }, `и ещё ${data.length - 15}…`));
  } catch (e) {
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'error' }, e.message));
  }
}

async function loadParticipation() {
  const body = document.getElementById('participationBody');
  try {
    const data = await api('/api/hr/participation', { role: 'hr' });
    body.innerHTML = '';
    const table = el('table', {}, [
      el('thead', {}, el('tr', {}, [el('th', {}, 'Активность'), el('th', {}, 'Тип'), el('th', {}, 'Завершили'), el('th', {}, 'Пропустили'), el('th', {}, 'Отказались'), el('th', {}, '% завершения')])),
    ]);
    const tbody = el('tbody');
    data.forEach((r) => {
      tbody.appendChild(el('tr', {}, [
        el('td', {}, r.name),
        el('td', {}, r.type),
        el('td', {}, String(r.completed)),
        el('td', {}, String(r.skipped)),
        el('td', {}, String(r.declined)),
        el('td', {}, r.completion_rate == null ? '—' : `${Math.round(r.completion_rate * 100)}%`),
      ]));
    });
    table.appendChild(tbody);
    body.appendChild(table);
  } catch (e) {
    body.innerHTML = '';
    body.appendChild(el('div', { class: 'error' }, e.message));
  }
}

async function handleImport() {
  const fileInput = document.getElementById('importFile');
  const resultBox = document.getElementById('importResult');
  if (!fileInput.files.length) {
    resultBox.textContent = 'Выберите файл.';
    return;
  }
  try {
    const text = await fileInput.files[0].text();
    const parsed = JSON.parse(text);
    const data = await api('/api/import', {
      role: 'hr', method: 'POST',
      body: { employees: parsed.employees || [], history: parsed.history || [] },
    });
    resultBox.textContent = `Импортировано: добавлено ${data.employees_added}, обновлено ${data.employees_updated}, записей истории +${data.history_rows_added}.`;
    await Promise.all([loadOverview(), loadLaggingSkills(), loadNoStep(), loadParticipation()]);
  } catch (e) {
    resultBox.textContent = 'Ошибка импорта: ' + e.message;
  }
}
