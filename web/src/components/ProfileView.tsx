import { useEffect, useRef, useState } from 'react';
import type { Candidate, Profile, Recommendations } from '../api';
import { factorLabels, formatDate, milestones, percent, projectedCoverage, recommendationLabel, statusLabels, typeLabels } from '../view-model';
import { Icon } from './Icons';
export type Section = 'profile' | 'quests' | 'skills' | 'history' | 'achievements' | 'hr';
export type Celebration = {
    title: string;
    before: number | null;
    after: number | null;
    gains: string[];
    already: boolean;
};
function Meter({ value, label }: {
    value: number | null;
    label: string;
}) {
    return value === null ? <div className="unknown-meter">Уровень ещё не определён</div> : <div className="meter" role="progressbar" aria-label={label} aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${value}%` }}/></div>;
}
function QuestCard({ event, index, profile, disabled, employee, onComplete }: {
    event: Candidate;
    index: number;
    profile: Profile;
    disabled: boolean;
    employee: boolean;
    onComplete: (c: Candidate) => void;
}) {
    const projection = projectedCoverage(profile, event);
    const delta = projection === null || profile.trajectory.coverage === null ? null : projection - profile.trajectory.coverage;
    return <article className={`quest-card ${index === 0 ? 'featured' : ''}`}>
    <div className="quest-top"><span className={`quest-icon tone-${index % 3}`}><Icon name={event.type === 'mentoring' ? 'users' : event.type === 'course' ? 'book' : 'compass'}/></span><span className="tag">{typeLabels[event.type] ?? event.type}</span>{index === 0 && <span className="recommended"><Icon name="spark"/> Лучший следующий шаг</span>}</div>
    <h3>{event.title}</h3>
    <div className="quest-gains">{Object.entries(event.changes).map(([id, c]) => <span key={id}>{c.name} <b>{c.before} <span aria-hidden="true">→</span> {c.after}</b></span>)}</div>
    {delta !== null && delta > 0 && <p className="quest-impact"><Icon name="route"/><span><b>+{Math.round(delta)} п. п. к цели {profile.trajectory.next_grade}</b><small>Прогноз покрытия: {percent(profile.trajectory.coverage)}% → {projection}%</small></span></p>}
    <details className="why" open={index === 0}><summary>Почему это подходит именно вам <Icon name="chevron"/></summary><ul>{event.evidence.map((f, i) => <li key={`${f.factor}-${i}`}><Icon name="check"/><div><strong>{factorLabels[f.factor] ?? 'Основание рекомендации'}</strong><span>{f.text}</span></div></li>)}</ul>{!event.evidence.length && <p className="muted">Обоснование ещё не получено от сервера.</p>}</details>
    {employee ? <button className={index === 0 ? 'primary full' : 'secondary full'} disabled={disabled} onClick={() => onComplete(event)}>Отметить выполненным <Icon name="check"/></button> : <p className="small muted">Выполнение отмечает сам сотрудник.</p>}
  </article>;
}
export function ProfileView({ profile, recommendation, section, employee, busy, onRecommend, onComplete, onNavigate, celebration, clearCelebration }: {
    profile: Profile;
    recommendation: Recommendations | null;
    section: Section;
    employee: boolean;
    busy: string;
    onRecommend: () => void;
    onComplete: (c: Candidate) => void;
    onNavigate: (s: Section) => void;
    celebration: Celebration | null;
    clearCelebration: () => void;
}) {
    const { employee: person, trajectory } = profile;
    const coverage = percent(trajectory.coverage);
    const completed = profile.history.filter(h => h.status === 'completed').length;
    const closed = trajectory.skills.filter(s => s.gap === 0).length;
    const [historyFilter, setHistoryFilter] = useState('all');
    const [elapsed, setElapsed] = useState(0);
    const [confirm, setConfirm] = useState<Candidate | null>(null);
    const dialog = useRef<HTMLDialogElement>(null);
    const recommending = busy === 'recommend';
    useEffect(() => { if (!recommending) {
        setElapsed(0);
        return;
    } const t = setInterval(() => setElapsed(s => s + 1), 1000); return () => clearInterval(t); }, [recommending]);
    useEffect(() => { if (confirm)
        dialog.current?.showModal();
    else
        dialog.current?.close(); }, [confirm]);
    useEffect(() => { setConfirm(null); setHistoryFilter('all'); }, [person.id]);
    const title = section === 'quests' ? 'Каждый квест — шаг вперёд' : section === 'skills' ? 'Ваши навыки, ваша опора' : section === 'history' ? 'Путь складывается из шагов' : section === 'achievements' ? 'Маленькие победы. Большой путь.' : `${employee ? 'Ваш следующий уровень' : 'Траектория сотрудника'}`;
    const show = (s: Section) => section === 'profile' || section === s;
    const badges = milestones(profile);
    const filteredHistory = profile.history.filter(h => historyFilter === 'all' || h.status === historyFilter);
    return <>
    <div className="page-heading"><div><div className="eyebrow">{employee ? 'ЛИЧНОЕ ПРОСТРАНСТВО РОСТА' : 'ПРОФИЛЬ СОТРУДНИКА'}</div><h1>{title}<span className="heading-dot">.</span></h1><p className="muted">{person.name} <span className="dot">·</span> {person.role} <span className="dot">·</span> {person.tenure_months} мес. в команде</p></div><span className="grade-chip"><Icon name="leaf"/>{person.grade}</span></div>
    {celebration && <div className="celebration" role="status"><span className="celebration-icon"><Icon name="award"/></span><div><h2>{celebration.already ? 'Этот шаг уже учтён' : 'Ещё один шаг к вашей цели!'}</h2><p>{celebration.title}</p>{!celebration.already && <><strong>{celebration.gains.join(' · ') || 'Активность добавлена в историю'}</strong>{celebration.before !== null && celebration.after !== null && <p>Покрытие требований: {celebration.before}% → {celebration.after}%</p>}</>}</div><button className="icon-button" onClick={clearCelebration} aria-label="Закрыть результат"><Icon name="close"/></button></div>}
    {section === 'profile' && <>
      <section className="journey-hero" aria-label="Путь к следующему грейду">
        <div className="hero-content"><span className="hero-label"><span />ВАША КАРЬЕРНАЯ ЭКСПЕДИЦИЯ</span><h2>{trajectory.next_grade ? <>Курс на <em>{trajectory.next_grade}</em></> : <>Ваш путь <em>продолжается</em></>}</h2><p>{trajectory.next_grade ? 'Не просто пройти обучение. Получить навыки, которые открывают следующий уровень.' : 'Требования следующего грейда пока не заданы. HR поможет уточнить вашу траекторию.'}</p><button className="lime-button" onClick={() => onNavigate('quests')}>Выбрать следующий квест <Icon name="arrow"/></button><div className="hero-caption"><Icon name="shield"/> Свой темп. Добровольные шаги. Реальный прогресс.</div></div>
        <div className="journey-map" aria-hidden="true"><div className="map-grid"/><svg viewBox="0 0 430 250" className="map-route"><path d="M48 202C110 235 112 83 187 118S251 239 302 135 311 40 374 46" fill="none" stroke="#426755" strokeWidth="2" strokeDasharray="5 7"/><path d="M48 202C110 235 112 83 187 118" fill="none" stroke="#c4eb8c" strokeWidth="3"/></svg><div className="map-node start"><Icon name="check"/><span>{person.grade}<small>Ваш текущий грейд</small></span></div><div className="map-node current"><Icon name="compass"/><span>Следующий квест<small>Вы здесь</small></span></div><div className="map-node middle"><Icon name="spark"/></div><div className="map-node finish"><Icon name="flag"/><span>{trajectory.next_grade ?? 'Новая цель'}<small>Ваш ориентир</small></span></div><span className="map-note">МАЛЕНЬКИЕ ШАГИ → БОЛЬШИЕ ВОЗМОЖНОСТИ</span></div>
      </section>
      <div className="stat-grid"><div className="stat"><span className="stat-icon mint"><Icon name="route"/></span><div><strong>{coverage === null ? '—' : `${coverage}%`}</strong><span>покрытие требований цели</span></div></div><div className="stat"><span className="stat-icon peach"><Icon name="check"/></span><div><strong>{completed}</strong><span>завершённых активностей</span></div></div><div className="stat"><span className="stat-icon lavender"><Icon name="flag"/></span><div><strong>{closed}<small> / {trajectory.skills.length}</small></strong><span>навыков на уровне цели</span></div></div></div>
    </>}
    <div className={section === 'profile' ? 'growth-grid' : ''}>
      {show('quests') && <section className="quests-section" id="quests"><div className="section-heading"><div><span className="eyebrow">ВАШ ПЕРСОНАЛЬНЫЙ МАРШРУТ</span><h2>Следующие квесты <span className="count">{recommendation?.items.length ?? '—'}</span></h2></div><button className="secondary compact" disabled={!!busy} onClick={onRecommend}><Icon name={recommending ? 'clock' : 'spark'}/>{recommending ? 'Подбираем…' : recommendation ? 'Обновить подбор' : 'Подобрать квесты'}</button></div>
        {recommending && <div className="ai-loading" role="status"><span className="orb"><Icon name="spark"/></span><div><strong>{elapsed >= 8 ? 'Нужно чуть больше времени…' : 'Собираем маршрут под ваш контекст'}</strong><p>Учитываем грейд, навыки, цель и историю участия.</p><small>{elapsed} сек. · Обычно до 10 секунд</small></div></div>}
        {!recommendation && !recommending && <div className="empty-quest"><span className="large-icon"><Icon name="compass"/></span><h3>Большой путь начинается<br />с подходящего шага</h3><p>Подберём до трёх активностей и объясним,<br />как каждая приближает вас к цели.</p><div className="context-chips"><span>Грейд</span><span>Навыки</span><span>История</span></div><button className="primary" disabled={!!busy} onClick={onRecommend}>Построить мой маршрут <Icon name="arrow"/></button><small>{profile.available.length} доступных активностей в каталоге</small></div>}
        {recommendation && <><div className={`mode-banner ${recommendation.mode === 'ai' ? 'ai' : ''}`}><Icon name={recommendation.cached ? 'clock' : recommendation.mode === 'ai' ? 'spark' : 'compass'}/><div><strong>{recommendationLabel(recommendation)}</strong>{recommendation.mode === 'ai' && <small>{recommendation.provider} · {recommendation.model}</small>}</div></div>{recommendation.reason && <p className="reason-note">{recommendation.reason}</p>}{!recommendation.items.length && <div className="empty-quest small-empty"><Icon name="leaf"/><h3>Сейчас подходящих квестов нет</h3><p>Это не оценка вашего прогресса. Возможно, нужно уточнить навыки или дополнить каталог с HR.</p></div>}<div className="quest-list" aria-busy={recommending}>{recommendation.items.map((event, index) => <QuestCard key={event.id} event={event} index={index} profile={profile} disabled={!!busy} employee={employee} onComplete={setConfirm}/>)}</div></>}
        <details className="catalog"><summary>Все доступные активности <span>{profile.available.length}</span></summary>{profile.available.length ? profile.available.map(c => <div key={c.id}><Icon name="book"/><span><strong>{c.title}</strong><small>{typeLabels[c.type] ?? c.type} · {Object.values(c.changes).map(s => `${s.name}: ${s.before} → ${s.after}`).join(' · ')}</small></span></div>) : <p className="muted">Каталог не содержит доступных шагов для этого профиля.</p>}</details>
      </section>}
      {show('skills') && <aside className="skills-column"><section className="panel skill-panel"><div className="section-heading"><h2>Навыки для роста</h2><Icon name="chart"/></div><p className="muted small">{person.grade} <span aria-hidden="true">→</span> {trajectory.next_grade ?? 'Цель уточняется'}</p><div className="coverage-row"><strong>{coverage === null ? '—' : `${coverage}%`}</strong><span>покрытие требований<br />следующего грейда</span></div><Meter value={coverage} label="Покрытие требований следующего грейда"/><p className="fine-print">Покрытие навыков не означает автоматическое повышение.</p><div className="skill-list">{trajectory.skills.map(s => <div className="skill" key={s.id}><div className="skill-heading"><strong>{s.name}</strong><span>{s.level ?? '?'} <small>/ {s.required}</small></span></div><Meter value={s.level === null ? null : percent(s.level / Math.max(1, s.required) * 100)} label={`${s.name}: ${s.level ?? 'неизвестно'} из ${s.required}`}/><small className={s.gap === 0 ? 'skill-done' : ''}>{s.gap === null ? 'Нужно уточнить уровень' : s.gap === 0 ? '✓ На уровне цели' : `До цели ещё ${s.gap} ур.`}</small></div>)}</div>{!trajectory.skills.length && <p className="empty-text">HR ещё не добавил требования следующего уровня.</p>}<details className="all-skills"><summary>Все текущие навыки</summary><ul>{Object.entries(person.skills).map(([id, level]) => <li key={id}><span>{trajectory.skills.find(s => s.id === id)?.name ?? id.replace(/^SK_/, '').replaceAll('_', ' ')}</span><b>{level} / 5</b></li>)}</ul></details></section>
        {section === 'profile' && <section className="pace-card"><Icon name="leaf"/><h3>Ваш рост — не гонка</h3><p>Выбирайте то, что помогает именно вам. Здесь нет публичных рейтингов и обязательных серий.</p></section>}
      </aside>}
    </div>
    {show('achievements') && <section className="achievements-section"><div className="section-heading"><div><span className="eyebrow">ЗАМЕЧАЙТЕ СВОЙ ПРОГРЕСС</span><h2>Личные достижения</h2></div><span className="small muted">{badges.filter(b => b.earned).length} из {badges.length} открыто</span></div><div className="badge-grid">{badges.map((b, i) => <article className={`achievement ${b.earned ? 'earned' : ''}`} key={b.id}><span className={`badge-art badge-${i}`}><Icon name={i === 0 ? 'flag' : i === 1 ? 'route' : 'award'}/></span><div><h3>{b.title}</h3><p>{b.description}</p><span className="badge-state">{b.earned ? '✓ Открыто' : b.progress}</span></div></article>)}</div><p className="fine-print">Достижения видны в вашем профиле и рассчитываются по истории и навыкам. Баллы не начисляются.</p></section>}
    {show('history') && <section className="panel history-section"><div className="section-heading"><div><span className="eyebrow">КАЖДЫЙ ШАГ ИМЕЕТ ЗНАЧЕНИЕ</span><h2>История вашего пути</h2></div><label className="filter-label">Показать<select value={historyFilter} onChange={e => setHistoryFilter(e.target.value)}><option value="all">Все активности</option><option value="completed">Завершённые</option><option value="missed">Пропущенные</option><option value="declined">Отказы</option></select></label></div>{filteredHistory.length ? <ul className="timeline">{filteredHistory.map(h => <li key={h.id}><span className={`timeline-icon ${h.status === 'completed' ? 'done' : ''}`}><Icon name={h.status === 'completed' ? 'check' : 'clock'}/></span><div><h3>{h.title}</h3><time dateTime={h.occurred_at}>{formatDate(h.occurred_at)}</time></div><span className={`status ${h.status === 'completed' ? 'completed' : ''}`}>{statusLabels[h.status] ?? h.status}</span></li>)}</ul> : <p className="empty-text">{profile.history.length ? 'Нет активностей с выбранным статусом.' : 'Здесь появятся ваши активности. Начните с первого квеста.'}</p>}</section>}
    <dialog ref={dialog} className="complete-dialog" onCancel={() => setConfirm(null)} onClose={() => setConfirm(null)} aria-labelledby="complete-title"><span className="large-icon"><Icon name="flag"/></span><h2 id="complete-title">Квест действительно пройден?</h2><p>{confirm?.title}</p><p className="muted">Отмечайте только завершённую активность. Сервер обновит навыки и сохранит результат в истории.</p><div className="dialog-actions"><button className="secondary" autoFocus onClick={() => setConfirm(null)}>Ещё прохожу</button><button className="primary" disabled={!!busy} onClick={() => { if (confirm)
        onComplete(confirm); setConfirm(null); }}>Да, завершить <Icon name="check"/></button></div></dialog>
  </>;
}
