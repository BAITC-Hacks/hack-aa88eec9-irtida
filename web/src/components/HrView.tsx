import { useState } from 'react';
import type { Employee, Metrics } from '../api';
import { participationCounts, percent, reasonLabels, statusLabels } from '../view-model';
import { ImportPanel } from './ImportPanel';
import { Icon } from './Icons';
export function HrView({ metrics, people, busy, openProfile, refresh, onImported, run }: {
    metrics: Metrics;
    people: Employee[];
    busy: string;
    openProfile: (id: string) => void;
    refresh: () => Promise<void>;
    onImported: () => Promise<void>;
    run: (label: string, action: () => Promise<void>) => Promise<boolean>;
}) {
    const [query, setQuery] = useState('');
    const total = metrics.participation.reduce((n, p) => n + p.completed, 0);
    const filtered = people.filter(p => `${p.name} ${p.role} ${p.id}`.toLocaleLowerCase().includes(query.toLocaleLowerCase()));
    return <>
    <div className="page-heading"><div><div className="eyebrow">HR · ПРОСТРАНСТВО КОМАНДЫ</div><h1>Помогайте росту случаться<span className="heading-dot">.</span></h1><p className="muted">Где нужна поддержка, какие навыки развивать и как проходит обучение.</p></div><button className="secondary" disabled={!!busy} onClick={() => void run('refresh', refresh)}><Icon name="refresh"/>Обновить</button></div>
    <div className="stat-grid"><div className="stat"><span className="stat-icon mint"><Icon name="users"/></span><div><strong>{metrics.employee_count}</strong><span>сотрудников в обзоре</span></div></div><div className="stat"><span className="stat-icon peach"><Icon name="compass"/></span><div><strong>{metrics.no_step.length}</strong><span>нужен доступный следующий шаг</span></div></div><div className="stat"><span className="stat-icon lavender"><Icon name="check"/></span><div><strong>{total}</strong><span>завершений активностей</span></div></div></div>
    <div className="hr-grid"><section className="panel"><div className="section-heading"><h2>Навыки, которым нужна поддержка</h2><Icon name="chart"/></div><p className="small muted">Разрывы относительно следующего грейда среди сотрудников с известным уровнем.</p>{metrics.gaps.length ? metrics.gaps.map(g => <div className="hr-gap" key={g.id}><div><strong>{g.name}</strong><span>{g.affected} из {g.eligible}</span></div>{g.percent === null ? <div className="unknown-meter">Недостаточно данных для доли</div> : <div className="meter" role="progressbar" aria-label={`Доля разрыва: ${g.name}`} aria-valuenow={percent(g.percent)!} aria-valuemin={0} aria-valuemax={100}><span style={{ width: `${percent(g.percent)}%` }}/></div>}{g.unknown > 0 && <small className="muted">Уровень не определён: {g.unknown}</small>}</div>) : <p className="empty-text">Данных о разрывах пока нет.</p>}</section>
    <section className="panel"><div className="section-heading"><h2>Без доступного шага</h2><span className="count">{metrics.no_step.length}</span></div><p className="small muted">Помогите уточнить цель или найти активность. Это не рейтинг вовлечённости.</p>{metrics.no_step.length ? metrics.no_step.map(p => <button className="person-row" key={p.id} disabled={!!busy} onClick={() => openProfile(p.id)}><span className="avatar">{p.name.slice(0, 1)}</span><span><strong>{p.name}</strong><small>{p.reason_detail || reasonLabels[p.reason] || p.reason}</small></span><Icon name="chevron"/></button>) : <div className="empty-support"><Icon name="check"/><h3>У каждого есть следующий шаг</h3><p>Для всех профилей доступны активности.</p></div>}</section></div>
    <section className="panel section-space"><div className="section-heading"><h2>Участие по активностям</h2><Icon name="book"/></div><p className="small muted">Количество записей участия. «Пропущено» показывает старые демо-записи; неявки кита учтены отдельно.</p>{metrics.participation.length ? <div className="table-wrap" role="region" aria-label="Участие по активностям, таблица с горизонтальной прокруткой" tabIndex={0}><table><thead><tr><th scope="col">Активность</th>{Object.entries(statusLabels).map(([status, label]) => <th key={status} scope="col">{label}</th>)}</tr></thead><tbody>{metrics.participation.map(p => <tr key={p.id}><th scope="row">{p.title}</th>{Object.keys(statusLabels).map(status => <td key={status}><span className={status === 'completed' ? 'completion-count' : undefined}>{participationCounts(p)[status as keyof ReturnType<typeof participationCounts>]}</span></td>)}</tr>)}</tbody></table></div> : <p className="empty-text">Истории участия пока нет.</p>}</section>
    <section className="panel section-space"><div className="section-heading"><div><span className="eyebrow">ЛИЧНЫЕ ТРАЕКТОРИИ</span><h2>Профили команды</h2></div><label className="search-label"><span className="sr-only">Найти сотрудника</span><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Имя, роль или ID"/></label></div><div className="people-grid">{filtered.map(p => <button className="person-row" disabled={!!busy} key={p.id} onClick={() => openProfile(p.id)}><span className="avatar">{p.name.slice(0, 1)}</span><span><strong>{p.name}</strong><small>{p.role} · {p.grade}</small></span><Icon name="chevron"/></button>)}</div>{!filtered.length && <p className="empty-text">{people.length ? 'Никого не нашли. Попробуйте другое имя или роль.' : 'Профилей пока нет. Загрузите данные ниже.'}</p>}</section>
    <ImportPanel busy={busy} run={run} onImported={onImported}/>
  </>;
}
