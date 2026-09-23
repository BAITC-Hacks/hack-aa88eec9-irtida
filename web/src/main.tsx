import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  api,
  type Account,
  type Employee,
  type Metrics,
  type Profile,
  type Recommendations,
} from "./api";
import "./style.css";

type DemoAccount = { id: string; label: string; role: string };
const statusLabels: Record<string, string> = {
  completed: "Завершено",
  missed: "Пропуск",
  declined: "Отказ",
};
const reasonLabels: Record<string, string> = {
  no_grade_rule: "Не заданы требования следующего грейда",
  missing_skills: "Недостаточно данных о навыках",
  no_eligible_activity: "Нет подходящей активности в каталоге",
};

function App() {
  const [account, setAccount] = useState<Account | null>(null);
  const [demo, setDemo] = useState<DemoAccount[]>([]);
  const [booting, setBooting] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [screen, setScreen] = useState<"profile" | "hr">("profile");
  const [people, setPeople] = useState<Employee[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendations | null>(
    null,
  );
  const [metrics, setMetrics] = useState<Metrics | null>(null);

  async function loadProfile(id: string) {
    const data = await api<Profile>(`/employees/${id}`);
    setProfile(data);
    setRecommendation(data.recommendation || null);
  }

  async function loadWorkspace(who: Account) {
    if (who.role === "hr") {
      const [employees, overview] = await Promise.all([
        api<Employee[]>("/employees"),
        api<Metrics>("/hr/overview"),
      ]);
      setPeople(employees);
      setMetrics(overview);
      setScreen("hr");
      if (employees.length) await loadProfile(employees[0].id);
    } else if (who.employee_id) {
      setScreen("profile");
      await loadProfile(who.employee_id);
    }
  }

  useEffect(() => {
    void (async () => {
      try {
        const accounts = await api<{ accounts: DemoAccount[] }>(
          "/auth/demo-accounts",
        );
        setDemo(accounts.accounts);
        const response = await fetch("/api/v1/auth/me");
        if (response.ok) {
          const who = (await response.json()) as Account;
          setAccount(who);
          await loadWorkspace(who);
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setBooting(false);
      }
    })();
  }, []);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function login(id: string) {
    const who = await api<Account>("/auth/demo", {
      method: "POST",
      body: JSON.stringify({ account: id }),
    });
    setAccount(who);
    await loadWorkspace(who);
  }

  async function importFile(file: File) {
    if (file.size > 5_000_000) throw new Error("Файл должен быть меньше 5 МБ");
    const body = await file.text();
    JSON.parse(body);
    await api("/imports?dry_run=true", { method: "POST", body });
    const result = await api<{
      employees_added: number;
      history_added: number;
    }>("/imports", { method: "POST", body });
    await loadWorkspace(account!);
    const accounts = await api<{ accounts: DemoAccount[] }>(
      "/auth/demo-accounts",
    );
    setDemo(accounts.accounts);
    setNotice(
      `Импорт завершён: новых профилей — ${result.employees_added}, записей истории — ${result.history_added}.`,
    );
  }

  const employee = profile?.employee;

  return (
    <div className="app">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Career Quest, главная">
          <span className="brand-mark">cq</span>
          <span>
            career<span className="brand-light">quest</span>
          </span>
        </a>
        <div className="header-right">
          <span className="demo-tag">HACKALEM · DEMO</span>
          {account && (
            <button
              className="text-button"
              disabled={!!busy}
              onClick={() =>
                void run("Выход", async () => {
                  await api("/auth/logout", { method: "POST" });
                  setAccount(null);
                  setProfile(null);
                  setMetrics(null);
                  setRecommendation(null);
                })
              }
            >
              Выйти
            </button>
          )}
        </div>
      </header>

      {error && (
        <div className="message error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="message success" role="status">
          {notice}
        </div>
      )}
      {busy && (
        <div className="working" role="status">
          {busy}…
        </div>
      )}

      {booting ? (
        <main>
          <p>Загружаем Career Quest…</p>
        </main>
      ) : !account ? (
        <main className="welcome">
          <section className="welcome-copy">
            <div className="eyebrow">ВАШ СЛЕДУЮЩИЙ ШАГ</div>
            <h1>
              Развитие,
              <br />в котором
              <br />
              <em>виден смысл.</em>
            </h1>
            <p>
              Свяжите сегодняшнее обучение с навыками, которые нужны для
              следующего уровня.
            </p>
            <div className="welcome-path">
              <span>Профиль</span>
              <b>→</b>
              <span>Следующий шаг</span>
              <b>→</b>
              <span>Прогресс</span>
            </div>
          </section>
          <section className="panel login-panel">
            <div className="eyebrow">ПОПРОБОВАТЬ СЦЕНАРИЙ</div>
            <h2>Выберите роль</h2>
            <p className="muted">
              Локальная демонстрация на синтетических данных. Пароли и
              корпоративный вход подключаются отдельно.
            </p>
            <div className="account-list">
              {demo.map((item) => (
                <button
                  className="account-option"
                  key={item.id}
                  disabled={!!busy}
                  onClick={() =>
                    void run("Открываем профиль", () => login(item.id))
                  }
                >
                  <span className="avatar">
                    {item.role === "hr" ? "HR" : item.id.slice(-2)}
                  </span>
                  <span>
                    <strong>{item.label}</strong>
                    <small>
                      {item.role === "hr"
                        ? "Обзор развития команды"
                        : "Личная траектория развития"}
                    </small>
                  </span>
                  <span className="arrow">↗</span>
                </button>
              ))}
            </div>
            {!demo.length && (
              <p>
                Демонстрационный вход отключён. Настройте авторизацию или
                включите DEMO_MODE для локальной проверки.
              </p>
            )}
          </section>
        </main>
      ) : (
        <main>
          <nav className="tabs" aria-label="Разделы">
            <button
              className={screen === "profile" ? "active" : ""}
              onClick={() => setScreen("profile")}
            >
              {account.role === "hr" ? "Профиль сотрудника" : "Моя траектория"}
            </button>
            {account.role === "hr" && (
              <button
                className={screen === "hr" ? "active" : ""}
                onClick={() =>
                  void run("Обновляем HR-срез", async () => {
                    setMetrics(await api<Metrics>("/hr/overview"));
                    setScreen("hr");
                  })
                }
              >
                HR-обзор
              </button>
            )}
          </nav>

          {screen === "profile" && profile && (
            <>
              {account.role === "hr" && (
                <label className="profile-selector">
                  Сотрудник{" "}
                  <select
                    value={employee!.id}
                    disabled={!!busy}
                    onChange={(e) =>
                      void run("Загружаем профиль", () =>
                        loadProfile(e.target.value),
                      )
                    }
                  >
                    {people.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.id} · {p.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <div className="page-heading">
                <div>
                  <div className="eyebrow">ЛИЧНАЯ ТРАЕКТОРИЯ</div>
                  <h1>{employee!.name}</h1>
                  <p className="muted">
                    {employee!.role} <span className="dot">·</span>{" "}
                    {employee!.grade} <span className="dot">·</span>{" "}
                    {employee!.tenure_months} мес. в компании
                  </p>
                </div>
                <span className="pill">{employee!.id}</span>
              </div>
              <div className="profile-grid">
                <section className="panel trajectory">
                  <div className="section-top">
                    <h2>Путь к следующему уровню</h2>
                    <span className="step-number">01</span>
                  </div>
                  <div className="grade-path">
                    <span>{employee!.grade}</span>
                    <span className="path-line" />
                    <strong>
                      {profile.trajectory.next_grade ||
                        "Следующий уровень не задан"}
                    </strong>
                  </div>
                  <div className="coverage">
                    <strong>
                      {profile.trajectory.coverage ?? "—"}
                      <small>
                        {profile.trajectory.coverage !== null ? "%" : ""}
                      </small>
                    </strong>
                    <span>
                      требований по навыкам
                      <br />
                      уже выполнено
                    </span>
                  </div>
                  <p className="caption">
                    Покрытие навыков не означает автоматическое повышение
                    грейда.
                  </p>
                  <div className="skill-list">
                    {profile.trajectory.skills.map((s) => (
                      <div className="skill" key={s.id}>
                        <div>
                          <strong>{s.name}</strong>
                          <span>
                            {s.level ?? "?"} <small>/ {s.required}</small>
                          </span>
                        </div>
                        <div className="skill-track">
                          <span
                            style={{
                              width: `${Math.min(100, ((s.level || 0) / Math.max(1, s.required)) * 100)}%`,
                            }}
                          />
                        </div>
                        <small>
                          {s.gap === null
                            ? "Уровень неизвестен"
                            : s.gap > 0
                              ? `До цели: ${s.gap} ур.`
                              : "Требование выполнено"}
                        </small>
                      </div>
                    ))}
                  </div>
                  {!profile.trajectory.next_grade && (
                    <p className="empty">
                      В каталоге нет правил следующего грейда. HR может уточнить
                      траекторию.
                    </p>
                  )}
                  <details>
                    <summary>Все текущие навыки</summary>
                    <ul className="plain-list">
                      {Object.entries(employee!.skills).map(([id, value]) => (
                        <li key={id}>
                          {id.replace("SK_", "").replaceAll("_", " ")}{" "}
                          <strong>{value}/5</strong>
                        </li>
                      ))}
                    </ul>
                  </details>
                </section>

                <section className="recommendations">
                  <div className="section-top">
                    <div>
                      <div className="eyebrow">ПОДОБРАНО ПОД ВАШ КОНТЕКСТ</div>
                      <h2>Следующие шаги</h2>
                    </div>
                    <button
                      className="primary"
                      disabled={!!busy}
                      onClick={() =>
                        void run("Подбираем следующие шаги", async () =>
                          setRecommendation(
                            await api<Recommendations>(
                              `/employees/${employee!.id}/recommendations`,
                              { method: "POST" },
                            ),
                          ),
                        )
                      }
                    >
                      {recommendation ? "Обновить" : "Подобрать шаги"}{" "}
                      <span>↗</span>
                    </button>
                  </div>
                  {!recommendation && (
                    <div className="panel empty-state">
                      <span className="compass">↗</span>
                      <h3>Начните с одного полезного шага</h3>
                      <p>
                        Учтём ваш грейд, разрывы по навыкам и историю участия.
                      </p>
                      <small>
                        Доступных активностей: {profile.available.length}
                      </small>
                    </div>
                  )}
                  {recommendation && (
                    <>
                      <div
                        className={`mode-label ${recommendation.mode === "ai" ? "ai" : ""}`}
                      >
                        {recommendation.mode === "ai"
                          ? `AI · ${recommendation.model}`
                          : recommendation.mode === "fallback"
                            ? "AI недоступен · подбор по правилам"
                            : recommendation.mode === "no_candidates"
                              ? "Нет подходящего шага"
                              : "Подбор по правилам · AI не подключён"}
                        {recommendation.cached && " · сохранённый результат"}
                      </div>
                      {recommendation.reason && (
                        <p className="muted">{recommendation.reason}</p>
                      )}
                      {recommendation.items.map((event, index) => (
                        <article
                          className="panel recommendation-card"
                          key={event.id}
                        >
                          <div className="card-meta">
                            <span>
                              {index === 0
                                ? "РЕКОМЕНДУЕМ НАЧАТЬ ЗДЕСЬ"
                                : `ВАРИАНТ ${index + 1}`}
                            </span>
                            <span>{event.type}</span>
                          </div>
                          <h3>{event.title}</h3>
                          <div className="gains">
                            {Object.entries(event.changes).map(
                              ([key, change]) => (
                                <span className="gain" key={key}>
                                  {change.name}{" "}
                                  <strong>
                                    {change.before} → {change.after}
                                  </strong>
                                </span>
                              ),
                            )}
                          </div>
                          <details open={index === 0}>
                            <summary>Почему этот шаг подходит</summary>
                            <ul className="evidence">
                              {event.evidence.map((f) => (
                                <li key={f.factor}>{f.text}</li>
                              ))}
                            </ul>
                          </details>
                          {account.role === "employee" && (
                            <button
                              className="complete-button"
                              disabled={!!busy}
                              onClick={() =>
                                void run("Сохраняем прогресс", async () => {
                                  const result = await api<{
                                    profile: Profile;
                                    already_completed: boolean;
                                  }>(
                                    `/employees/${employee!.id}/events/${event.id}/complete`,
                                    { method: "POST" },
                                  );
                                  setProfile(result.profile);
                                  setRecommendation(null);
                                  setNotice(
                                    result.already_completed
                                      ? "Это прохождение уже учтено."
                                      : "Активность завершена. Навыки и траектория обновлены.",
                                  );
                                })
                              }
                            >
                              Отметить выполненной <span>✓</span>
                            </button>
                          )}
                        </article>
                      ))}
                    </>
                  )}
                </section>
              </div>
              <section className="panel history">
                <div className="section-top">
                  <h2>История участия</h2>
                  <span className="muted">
                    {profile.history.length} записей
                  </span>
                </div>
                {profile.history.length ? (
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Активность</th>
                          <th>Дата</th>
                          <th>Результат</th>
                        </tr>
                      </thead>
                      <tbody>
                        {profile.history.map((h) => (
                          <tr key={h.id}>
                            <td>{h.title}</td>
                            <td>{h.occurred_at}</td>
                            <td>
                              <span className={`status ${h.status}`}>
                                {statusLabels[h.status]}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="muted">
                    Истории пока нет. Начать можно с любой подходящей
                    активности.
                  </p>
                )}
              </section>
            </>
          )}

          {screen === "hr" && metrics && (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">РАЗВИТИЕ КОМАНДЫ</div>
                  <h1>Потребности в развитии</h1>
                  <p className="muted">
                    Компетенции, доступные шаги и участие в активностях.
                  </p>
                </div>
                <span className="pill">
                  {metrics.employee_count} сотрудников
                </span>
              </div>
              <div className="hr-grid">
                <section className="panel">
                  <h2>Где есть разрыв</h2>
                  <p className="caption">
                    Среди сотрудников с известным уровнем, которым навык
                    требуется для следующего грейда.
                  </p>
                  {metrics.gaps.map((g) => (
                    <div className="hr-gap" key={g.name}>
                      <div>
                        <strong>{g.name}</strong>
                        <span>
                          {g.affected} из {g.eligible}
                        </span>
                      </div>
                      <div className="skill-track">
                        <span style={{ width: `${g.percent || 0}%` }} />
                      </div>
                      {g.unknown > 0 && (
                        <small>Неизвестный уровень: {g.unknown}</small>
                      )}
                    </div>
                  ))}
                </section>
                <section className="panel">
                  <h2>Без доступного шага</h2>
                  <p className="caption">
                    Проверяется наличие подходящих активностей, независимо от
                    генерации AI-рекомендации.
                  </p>
                  {metrics.no_step.length ? (
                    metrics.no_step.map((p) => (
                      <button
                        className="no-step"
                        disabled={!!busy}
                        key={p.id}
                        onClick={() =>
                          void run("Открываем профиль", async () => {
                            await loadProfile(p.id);
                            setScreen("profile");
                          })
                        }
                      >
                        <strong>{p.name} ↗</strong>
                        <span>{reasonLabels[p.reason] || p.reason}</span>
                      </button>
                    ))
                  ) : (
                    <p className="empty">
                      Для каждого сотрудника есть подходящий шаг.
                    </p>
                  )}
                </section>
              </div>
              <section className="panel history">
                <h2>Участие по активностям</h2>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Активность</th>
                        <th>Завершено</th>
                        <th>Пропущено</th>
                        <th>Отказы</th>
                      </tr>
                    </thead>
                    <tbody>
                      {metrics.participation.map((p) => (
                        <tr key={p.id}>
                          <td>{p.title}</td>
                          <td>{p.completed}</td>
                          <td>{p.missed}</td>
                          <td>{p.declined}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
              <section className="panel import-panel">
                <div>
                  <div className="eyebrow">ДАННЫЕ ДЛЯ ПРОВЕРКИ</div>
                  <h2>Загрузить дополнительные профили</h2>
                  <p className="muted">
                    Сейчас поддерживается внутренний формат demo-v1 из
                    examples/additional-profile.json. Адаптер JSON/CSV
                    стартового кита ещё нужно реализовать.
                  </p>
                </div>
                <label className={`primary upload ${busy ? "disabled" : ""}`}>
                  Выбрать JSON
                  <input
                    aria-label="Загрузить JSON-профили"
                    type="file"
                    accept=".json,application/json"
                    disabled={!!busy}
                    onChange={(e) => {
                      const file = e.target.files?.[0];
                      e.target.value = "";
                      if (file)
                        void run("Проверяем и импортируем данные", () =>
                          importFile(file),
                        );
                    }}
                  />
                </label>
              </section>
            </>
          )}
        </main>
      )}
      <footer>
        <span>Career Quest</span>
        <span>Добровольное развитие. Понятный следующий шаг.</span>
        <span>Синтетические демо-данные</span>
      </footer>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<App />);
