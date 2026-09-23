import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, type Account, type Candidate, type DemoAccount, type Employee, type Metrics, type Profile, type Recommendations } from './api';
import { Brand, Icon, type IconName } from './components/Icons';
import { ProfileView, type Section, type Celebration } from './components/ProfileView';
import { HrView } from './components/HrView';
import { initials, percent } from './view-model';
import './style.css';
const nav: {
    id: Section;
    label: string;
    icon: IconName;
}[] = [
    { id: 'profile', label: 'Мой путь', icon: 'route' }, { id: 'quests', label: 'Мои квесты', icon: 'compass' },
    { id: 'skills', label: 'Навыки', icon: 'chart' }, { id: 'achievements', label: 'Достижения', icon: 'award' }, { id: 'history', label: 'История', icon: 'clock' },
];
const busyLabels: Record<string, string> = { login: 'Открываем пространство', profile: 'Загружаем профиль', logout: 'Завершаем сессию', complete: 'Сохраняем результат квеста', refresh: 'Обновляем данные', 'import-check': 'Проверяем файл', 'import-save': 'Сохраняем данные' };
function App() {
    const [account, setAccount] = useState<Account | null>(null);
    const [demo, setDemo] = useState<DemoAccount[]>([]);
    const [booting, setBooting] = useState(true);
    const [busy, setBusy] = useState('');
    const busyRef = useRef(false);
    const [error, setError] = useState('');
    const [section, setSection] = useState<Section>('profile');
    const [people, setPeople] = useState<Employee[]>([]);
    const [profile, setProfile] = useState<Profile | null>(null);
    const [recommendation, setRecommendation] = useState<Recommendations | null>(null);
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [celebration, setCelebration] = useState<Celebration | null>(null);
    const [online, setOnline] = useState(navigator.onLine);
    const [loginRole, setLoginRole] = useState('employee');
    const headingRef = useRef<HTMLElement>(null);
    function clearSession() { setAccount(null); setProfile(null); setPeople([]); setMetrics(null); setRecommendation(null); setCelebration(null); setSection('profile'); }
    function assignProfile(data: Profile) { setProfile(data); setRecommendation(data.recommendation ?? null); }
    async function loadProfile(id: string) { assignProfile(await api<Profile>(`/employees/${encodeURIComponent(id)}`)); }
    async function refreshHr() { const [employees, overview] = await Promise.all([api<Employee[]>('/employees'), api<Metrics>('/hr/overview')]); setPeople(employees); setMetrics(overview); }
    async function loadWorkspace(who: Account) {
        if (who.role === 'hr') {
            setSection('hr');
            await refreshHr();
        }
        else if (who.employee_id) {
            setSection('profile');
            await loadProfile(who.employee_id);
        }
    }
    async function boot() {
        setBooting(true);
        setError('');
        try {
            // Existing sessions remain usable when demo login is disabled.
            let who: Account | null = null;
            try {
                who = await api<Account>('/auth/me');
            }
            catch (e) {
                if (!(e instanceof ApiError && e.status === 401))
                    throw e;
            }
            if (who) {
                setAccount(who);
                await loadWorkspace(who);
            }
            else {
                clearSession();
                const result = await api<{
                    enabled: boolean;
                    accounts: DemoAccount[];
                }>('/auth/demo-accounts');
                setDemo(result.enabled === false ? [] : result.accounts);
            }
        }
        catch (e) {
            setError((e as Error).message);
        }
        finally {
            setBooting(false);
        }
    }
    useEffect(() => { void boot(); const on = () => setOnline(true); const off = () => setOnline(false); window.addEventListener('online', on); window.addEventListener('offline', off); return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); }; }, []);
    async function run(label: string, action: () => Promise<void>) {
        if (busyRef.current)
            return false;
        busyRef.current = true;
        setBusy(label);
        setError('');
        try {
            await action();
            return true;
        }
        catch (e) {
            if (e instanceof ApiError && e.status === 401) {
                clearSession();
                try {
                    setDemo((await api<{
                        accounts: DemoAccount[];
                    }>('/auth/demo-accounts')).accounts);
                }
                catch {
                    setDemo([]);
                }
            }
            setError((e as Error).message);
            return false;
        }
        finally {
            busyRef.current = false;
            setBusy('');
        }
    }
    function navigate(s: Section) { setSection(s); setError(''); headingRef.current?.focus(); window.scrollTo({ top: 0, behavior: 'instant' }); }
    function openProfile(id: string) { void run('profile', async () => { await loadProfile(id); setCelebration(null); navigate('profile'); }); }
    async function complete(event: Candidate) {
        if (!profile)
            return;
        const oldProfile = profile;
        await run('complete', async () => {
            const result = await api<{
                profile: Profile;
                already_completed: boolean;
            }>(`/employees/${encodeURIComponent(oldProfile.employee.id)}/events/${encodeURIComponent(event.id)}/complete`, { method: 'POST' });
            assignProfile(result.profile);
            const gains = Object.entries(event.changes).flatMap(([id, c]) => { const before = oldProfile.employee.skills[id]; const after = result.profile.employee.skills[id]; return before !== undefined && after !== undefined && after > before ? [`${c.name}: ${before} → ${after}`] : []; });
            setCelebration({ title: event.title, before: percent(oldProfile.trajectory.coverage), after: percent(result.profile.trajectory.coverage), gains, already: result.already_completed });
            window.scrollTo({ top: 0, behavior: 'instant' });
        });
    }
    const who = account?.role === 'hr' ? 'HR-специалист' : profile?.employee.name ?? 'Сотрудник';
    const activeLabel = section === 'hr' ? 'Обзор команды' : nav.find(n => n.id === section)?.label;
    const alerts = <>{!online && <div className="message warning" role="status"><Icon name="shield"/>Нет сети. Загруженные данные остаются на экране; для сохранения нужен сервер.</div>}{error && <div className="message error" role="alert"><Icon name="shield"/><span>{error}</span><button className="text-button" disabled={!!busy || booting} onClick={() => account ? void run('refresh', () => account.role === 'hr' && section === 'hr' ? refreshHr() : profile ? loadProfile(profile.employee.id) : loadWorkspace(account)) : void boot()}>Обновить данные</button><button className="icon-button" aria-label="Закрыть ошибку" onClick={() => setError('')}><Icon name="close"/></button></div>}</>;
    if (booting)
        return <div className="boot-screen"><Brand /><div className="skeleton"/><p role="status">Открываем ваше пространство роста…</p></div>;
    if (!account)
        return <div className="welcome-shell"><header className="welcome-header"><Brand /><span className="demo-tag"><span /> HACKALEM · DEMO</span></header>{alerts}<main className="welcome"><section className="welcome-copy"><span className="eyebrow">РАЗВИТИЕ, В КОТОРОМ ЕСТЬ СМЫСЛ</span><h1>Ваш рост.<br />Ваш маршрут.<br /><em>Ваш следующий шаг.</em></h1><p>Превратите разрозненное обучение в понятный путь к следующему уровню. Один полезный квест за раз.</p><div className="welcome-steps"><span><b>01</b>Увидеть цель</span><Icon name="arrow"/><span><b>02</b>Выбрать квест</span><Icon name="arrow"/><span><b>03</b>Заметить рост</span></div><div className="welcome-note"><Icon name="leaf"/>Без гонки с коллегами. В своём ритме.</div></section><section className="login-card"><span className="large-icon"><Icon name="compass"/></span><h2>Начнём ваше путешествие</h2><p className="muted">Выберите профиль для знакомства с Career Quest.</p><div className="role-toggle" aria-label="Роль для демонстрации"><button aria-pressed={loginRole === 'employee'} onClick={() => setLoginRole('employee')}>Я сотрудник</button><button aria-pressed={loginRole === 'hr'} onClick={() => setLoginRole('hr')}>Я HR</button></div><div className="account-list">{demo.filter(d => d.role === loginRole).map(item => <button className="account-option" disabled={!!busy} key={item.id} onClick={() => void run('login', async () => { const who = await api<Account>('/auth/demo', { method: 'POST', body: JSON.stringify({ account: item.id }) }); setAccount(who); await loadWorkspace(who); })}><span className="avatar">{item.role === 'hr' ? 'HR' : initials(item.label)}</span><span><strong>{item.label}</strong><small>{item.role === 'hr' ? 'Помогать развитию команды' : 'Открыть личную траекторию'}</small></span><Icon name="arrow"/></button>)}</div>{!demo.filter(d => d.role === loginRole).length && <p className="empty-text">{error ? 'Профили пока не загрузились. Попробуйте обновить данные.' : 'Демонстрационные профили недоступны. Обратитесь к администратору за доступом.'}</p>}<div className="login-foot"><Icon name="shield"/><span>Демо на синтетических данных.<br />Реальные персональные данные не используются.</span></div></section></main><footer className="welcome-footer">CAREER QUEST <span>Ваше развитие начинается с понятного «зачем».</span></footer>{busy && <div className="working" role="status">{busyLabels[busy]}…</div>}</div>;
    return <div className="app-shell"><a href="#workspace" className="skip-link">К основному содержимому</a><aside className="sidebar"><a href="#workspace" className="brand-link" onClick={() => navigate(account.role === 'hr' ? 'hr' : 'profile')} aria-label="Career Quest, главная"><Brand /></a><div className="workspace-label">{account.role === 'hr' ? 'РАЗВИТИЕ КОМАНДЫ' : 'МОЁ РАЗВИТИЕ'}</div><nav aria-label="Разделы Career Quest">{account.role === 'hr' && <button aria-label="Обзор команды" disabled={!!busy} className={section === 'hr' ? 'active' : ''} aria-current={section === 'hr' ? 'page' : undefined} onClick={() => void run('refresh', async () => { await refreshHr(); navigate('hr'); })}><Icon name="users"/><span>Обзор команды</span></button>}{nav.map(n => <button aria-label={account.role === 'hr' && n.id === 'profile' ? 'Профиль сотрудника' : n.label} title={n.label} disabled={!!busy || (account.role === 'hr' && !profile)} key={n.id} className={section === n.id ? 'active' : ''} aria-current={section === n.id ? 'page' : undefined} onClick={() => navigate(n.id)}><Icon name={n.icon}/><span>{account.role === 'hr' && n.id === 'profile' ? 'Профиль сотрудника' : n.label}</span>{n.id === 'quests' && !!profile?.available.length && <small>{profile.available.length}</small>}</button>)}</nav><div className="sidebar-bottom"><div className="sidebar-note"><Icon name="leaf"/><strong>Растите в своём темпе</strong><p>Ваш путь уникален.<br />Каждый шаг имеет значение.</p></div><span className="demo-tag"><span />Синтетические демо-данные</span><button className="logout" aria-label="Выйти из профиля" disabled={!!busy} onClick={() => void run('logout', async () => { await api('/auth/logout', { method: 'POST' }); clearSession(); const result = await api<{
        accounts: DemoAccount[];
    }>('/auth/demo-accounts'); setDemo(result.accounts); })}><Icon name="logout"/>Выйти из профиля</button></div></aside><div className="main-shell"><header className="topbar"><div className="breadcrumb">Пространство роста<Icon name="chevron"/><strong>{activeLabel}</strong></div><div className="topbar-user"><span className="private-label"><Icon name="shield"/>{account.role === 'hr' ? 'Доступ HR' : 'Личный прогресс'}</span><span className="avatar small-avatar">{initials(who)}</span><span className="user-name">{who}<small>{account.role === 'hr' ? 'Развитие команды' : profile?.employee.grade}</small></span></div></header><main id="workspace" className="workspace" ref={headingRef} tabIndex={-1}>{alerts}{account.role === 'hr' && section !== 'hr' && <div className="hr-profile-toolbar"><button className="text-button" disabled={!!busy} onClick={() => void run('refresh', async () => { await refreshHr(); navigate('hr'); })}>← Назад к HR-обзору</button><label>Сотрудник<select value={profile?.employee.id ?? ''} disabled={!!busy} onChange={e => openProfile(e.target.value)}>{people.map(p => <option key={p.id} value={p.id}>{p.name} · {p.id}</option>)}</select></label></div>}{section === 'hr' && metrics ? <HrView metrics={metrics} people={people} busy={busy} openProfile={openProfile} refresh={refreshHr} run={run}/> : section !== 'hr' && profile ? <ProfileView profile={profile} recommendation={recommendation} section={section} employee={account.role === 'employee'} busy={busy} onRecommend={() => void run('recommend', async () => setRecommendation(await api<Recommendations>(`/employees/${encodeURIComponent(profile.employee.id)}/recommendations`, { method: 'POST' })))} onComplete={c => void complete(c)} onNavigate={navigate} celebration={celebration} clearCelebration={() => setCelebration(null)}/> : <div className="panel empty-quest"><Icon name="compass"/><h1>Пространство ещё не загрузилось</h1><p>Обновите данные, чтобы продолжить.</p><button className="primary" disabled={!!busy} onClick={() => void run('refresh', () => loadWorkspace(account))}>Попробовать снова</button></div>}<footer className="workspace-footer"><span>CAREER QUEST <span className="dot">/</span> МАЛЕНЬКИЕ ШАГИ. БОЛЬШИЕ ВОЗМОЖНОСТИ.</span><span>Создано для вашего роста <Icon name="leaf"/></span></footer></main></div>{busy && busy !== 'recommend' && <div className="working" role="status"><span className="spinner"/>{busyLabels[busy] ?? 'Загрузка'}…</div>}</div>;
}
createRoot(document.getElementById('root')!).render(<App />);
