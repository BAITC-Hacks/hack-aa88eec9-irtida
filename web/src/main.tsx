import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, authenticate, completeEvent, type Account, type AuthMode, type AuthRequest, type AuthStatus, type Candidate, type Catalog, type Employee, type Metrics, type Profile, type Recommendations, type RegisteredAccount } from './api';
import { I18nProvider, useI18n } from './i18n';
import { Brand, Icon, type IconName } from './components/Icons';
import { ProfileView, type Section, type Celebration } from './components/ProfileView';
import { HrView } from './components/HrView';
import { ImportPanel } from './components/ImportPanel';
import { AuthView, LanguageSelect } from './components/AuthView';
import { AccountView } from './components/AccountView';
import { CatalogView } from './components/CatalogView';
import { AccountsView } from './components/AccountsView';
import { initials, percent } from './view-model';
import './style.css';
import './styles/app-shell.css';

type Page = Section | 'catalog' | 'skill-catalog' | 'imports' | 'accounts' | 'account';
function App() {
    const { locale, t } = useI18n();
    const [account, setAccount] = useState<Account | null>(null);
    const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
    const [booting, setBooting] = useState(true);
    const [busy, setBusy] = useState('');
    const busyRef = useRef(false);
    const [error, setError] = useState('');
    const [page, setPage] = useState<Page>('profile');
    const [people, setPeople] = useState<Employee[]>([]);
    const [profile, setProfile] = useState<Profile | null>(null);
    const [recommendation, setRecommendation] = useState<Recommendations | null>(null);
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [catalog, setCatalog] = useState<Catalog | null>(null);
    const [accounts, setAccounts] = useState<RegisteredAccount[]>([]);
    const [celebration, setCelebration] = useState<Celebration | null>(null);
    const [online, setOnline] = useState(navigator.onLine);
    const previousLocale = useRef(locale);
    const headingRef = useRef<HTMLElement>(null);
    const employeeNav: { id: Section; label: string; icon: IconName }[] = [
        { id: 'profile', label: t('Мой путь', 'My journey', 'Менің жолым'), icon: 'route' },
        { id: 'quests', label: t('Мои квесты', 'My quests', 'Менің квесттерім'), icon: 'compass' },
        { id: 'skills', label: t('Навыки', 'Skills', 'Дағдылар'), icon: 'chart' },
        { id: 'achievements', label: t('Достижения', 'Achievements', 'Жетістіктер'), icon: 'award' },
        { id: 'history', label: t('История', 'History', 'Тарих'), icon: 'clock' },
    ];
    const hrNav: { id: Page; label: string; icon: IconName }[] = [
        { id: 'hr', label: t('Команда и аналитика', 'Team and analytics', 'Команда және аналитика'), icon: 'users' },
        { id: 'catalog', label: t('Каталог активностей', 'Activity catalog', 'Іс-шаралар каталогы'), icon: 'book' },
        { id: 'skill-catalog', label: t('Каталог навыков', 'Skill catalog', 'Дағдылар каталогы'), icon: 'chart' },
        { id: 'imports', label: t('Импорт данных', 'Data import', 'Деректер импорты'), icon: 'upload' },
        { id: 'accounts', label: t('Аккаунты и доступ', 'Accounts and access', 'Аккаунттар және қолжетімділік'), icon: 'shield' },
    ];
    const busyLabels: Record<string, string> = {
        login: t('Открываем пространство', 'Opening workspace', 'Кеңістік ашылуда'),
        profile: t('Загружаем профиль', 'Loading profile', 'Профиль жүктелуде'),
        logout: t('Завершаем сессию', 'Signing out', 'Сессия аяқталуда'),
        complete: t('Сохраняем результат', 'Saving progress', 'Нәтиже сақталуда'),
        refresh: t('Обновляем данные', 'Refreshing data', 'Деректер жаңартылуда'),
        invite: t('Создаём приглашение', 'Creating invitation', 'Шақыру жасалуда'),
        'import-check': t('Проверяем файлы', 'Checking files', 'Файлдар тексерілуде'),
        'import-save': t('Сохраняем данные', 'Saving data', 'Деректер сақталуда'),
    };
    const isProfilePage = employeeNav.some(item => item.id === page);
    function clearSession() {
        setAccount(null); setProfile(null); setPeople([]); setMetrics(null); setCatalog(null); setAccounts([]);
        setRecommendation(null); setCelebration(null); setPage('profile');
    }
    function assignProfile(data: Profile) { setProfile(data); setRecommendation(data.recommendation); }
    async function loadProfile(id: string) { assignProfile(await api<Profile>(`/employees/${encodeURIComponent(id)}`)); }
    async function refreshHr() {
        const [employees, overview] = await Promise.all([api<Employee[]>('/employees'), api<Metrics>('/hr/overview')]);
        setPeople(employees); setMetrics(overview);
    }
    async function refreshAccounts() {
        const [list, employees] = await Promise.all([api<RegisteredAccount[]>('/hr/accounts'), api<Employee[]>('/employees')]);
        setAccounts(list); setPeople(employees);
    }
    async function refreshCatalog() { setCatalog(await api<Catalog>('/catalog')); }
    async function refreshAfterImport() {
        const [employees, overview, nextCatalog, list, status] = await Promise.all([
            api<Employee[]>('/employees'), api<Metrics>('/hr/overview'), api<Catalog>('/catalog'),
            api<RegisteredAccount[]>('/hr/accounts'), api<AuthStatus>('/auth/status'),
        ]);
        setPeople(employees); setMetrics(overview); setCatalog(nextCatalog); setAccounts(list); setAuthStatus(status);
        setCelebration(null); setRecommendation(null);
        const currentId = profile?.employee.id;
        setProfile(null);
        if (currentId && employees.some(person => person.id === currentId)) await loadProfile(currentId);
    }
    async function loadWorkspace(who: Account) {
        if (who.role === 'hr') {
            setPage('hr');
            await Promise.all([refreshHr(), refreshCatalog(), refreshAccounts()]);
        } else if (who.employee_id) {
            setPage('profile'); await loadProfile(who.employee_id);
        }
    }
    async function boot() {
        setBooting(true); setError('');
        try {
            setAuthStatus(await api<AuthStatus>('/auth/status'));
            let who: Account | null = null;
            try { who = await api<Account>('/auth/me'); }
            catch (reason) { if (!(reason instanceof ApiError && reason.status === 401)) throw reason; }
            if (who) { setAccount(who); await loadWorkspace(who); } else clearSession();
        } catch (reason) {
            if (reason instanceof ApiError && reason.status === 401) clearSession();
            setError((reason as Error).message);
        } finally { setBooting(false); }
    }
    useEffect(() => {
        void boot();
        const on = () => setOnline(true); const off = () => setOnline(false);
        window.addEventListener('online', on); window.addEventListener('offline', off);
        return () => { window.removeEventListener('online', on); window.removeEventListener('offline', off); };
    }, []);
    async function run(label: string, action: () => Promise<void>) {
        if (busyRef.current) return false;
        busyRef.current = true; setBusy(label); setError('');
        try { await action(); return true; }
        catch (reason) {
            if (reason instanceof ApiError && reason.status === 401 && account) clearSession();
            setError((reason as Error).message); return false;
        } finally { busyRef.current = false; setBusy(''); }
    }
    async function refreshCurrent() {
        if (!account) { setAuthStatus(await api<AuthStatus>('/auth/status')); return; }
        if (account.role === 'hr') {
            await Promise.all([refreshHr(), refreshCatalog(), refreshAccounts()]);
            if (profile) await loadProfile(profile.employee.id);
        } else if (account.employee_id) await loadProfile(account.employee_id);
    }
    useEffect(() => {
        if (previousLocale.current === locale) return;
        previousLocale.current = locale;
        if (!booting) void run('refresh', refreshCurrent);
    }, [locale]);
    function navigate(next: Page) { setPage(next); setError(''); headingRef.current?.focus(); window.scrollTo({ top: 0, behavior: 'instant' }); }
    function goHome() { navigate(account?.role === 'hr' ? 'hr' : 'profile'); }
    function openProfile(id: string) { void run('profile', async () => { await loadProfile(id); setCelebration(null); navigate('profile'); }); }
    function logout() { void run('logout', async () => { await api('/auth/logout', { method: 'POST' }); clearSession(); setAuthStatus(await api<AuthStatus>('/auth/status')); }); }
    function login(mode: AuthMode, request: AuthRequest) {
        return run('login', async () => {
            const who = await authenticate(mode, request);
            setAccount(who); setAuthStatus(previous => previous ? { ...previous, setup_required: false } : previous);
            await loadWorkspace(who);
        });
    }
    async function complete(event: Candidate) {
        if (!profile) return;
        const oldProfile = profile;
        await run('complete', async () => {
            const result = await completeEvent(oldProfile.employee.id, event); assignProfile(result.profile);
            const completion = result.profile.history.find(item => !oldProfile.history.some(previous => previous.id === item.id));
            const gains = result.already_completed ? [] : Object.values(completion?.changes ?? {}).map(change => `${change.name}: ${change.before} → ${change.after}`);
            setCelebration({ title: event.title, before: percent(oldProfile.trajectory.coverage), after: percent(result.profile.trajectory.coverage), gains, already: result.already_completed });
            window.scrollTo({ top: 0, behavior: 'instant' });
        });
    }
    const who = account?.display_name || (account?.role === 'employee' ? profile?.employee.name : null) || t('HR-специалист', 'HR specialist', 'HR маманы');
    const activeLabel = page === 'account' ? t('Мой аккаунт', 'My account', 'Менің аккаунтым') : [...hrNav, ...employeeNav].find(item => item.id === page)?.label;
    const offline = !online && <div className="message warning" role="status"><Icon name="shield"/>{t('Нет сети. Для загрузки и сохранения нужен сервер.', 'You are offline. Loading and saving require the server.', 'Желі жоқ. Жүктеу және сақтау үшін сервер қажет.')}</div>;
    const alerts = <>{offline}{error && <div className="message error" role="alert"><Icon name="shield"/><span>{error}</span><button className="text-button" disabled={!!busy} onClick={() => void run('refresh', refreshCurrent)}>{t('Обновить данные', 'Refresh data', 'Деректерді жаңарту')}</button><button className="icon-button" aria-label={t('Закрыть ошибку', 'Dismiss error', 'Қатені жабу')} onClick={() => setError('')}><Icon name="close"/></button></div>}</>;
    if (booting) return <div className="boot-screen"><Brand/><div className="skeleton"/><p role="status">{t('Открываем ваше пространство роста…', 'Opening your growth workspace…', 'Даму кеңістігіңіз ашылуда…')}</p></div>;
    if (!account) return <AuthView status={authStatus} busy={!!busy} error={error} alerts={offline} onSubmit={login} onRetry={() => void boot()}/>;

    let content;
    if (page === 'account') content = <AccountView account={account} profile={profile} busy={!!busy} onProfile={() => account.employee_id && openProfile(account.employee_id)} onLogout={logout}/>;
    else if (page === 'hr' && account.role === 'hr' && metrics) content = <><div className="team-role-summary" aria-label={t('Роли команды', 'Team roles', 'Команда рөлдері')}>{Array.from(new Set(people.map(person => person.role))).map(role => <span key={role}>{people.find(person => person.role === role)?.role_label ?? role} <b>{people.filter(person => person.role === role).length}</b></span>)}</div><HrView metrics={metrics} people={people} busy={busy} openProfile={openProfile} refresh={refreshHr} onImported={refreshAfterImport} run={run} hideImport/></>;
    else if ((page === 'catalog' || page === 'skill-catalog') && account.role === 'hr' && catalog) content = <CatalogView key={page} catalog={catalog} kind={page === 'catalog' ? 'events' : 'skills'} busy={!!busy} refresh={() => void run('refresh', refreshCatalog)}/>;
    else if (page === 'imports' && account.role === 'hr') content = <><div className="page-heading"><div><span className="eyebrow">{t('HR · ДАННЫЕ КОМАНДЫ', 'HR · TEAM DATA', 'HR · КОМАНДА ДЕРЕКТЕРІ')}</span><h1>{t('Импорт данных', 'Data import', 'Деректер импорты')}</h1><p className="muted">{t('Добавляйте профили, историю, навыки и активности из исходных файлов.', 'Add profiles, history, skills and activities from source files.', 'Бастапқы файлдардан профильдерді, тарихты, дағдыларды және іс-шараларды қосыңыз.')}</p></div></div><ImportPanel busy={busy} run={run} onImported={refreshAfterImport}/></>;
    else if (page === 'accounts' && account.role === 'hr') content = <AccountsView accounts={accounts} people={people} busy={busy} run={run} refresh={refreshAccounts}/>;
    else if (isProfilePage && profile) content = <ProfileView profile={profile} recommendation={recommendation} section={page as Section} employee={account.role === 'employee'} busy={busy} onRecommend={() => void run('recommend', async () => setRecommendation(await api<Recommendations>(`/employees/${encodeURIComponent(profile.employee.id)}/recommendations`, { method: 'POST' })))} onComplete={event => void complete(event)} onNavigate={navigate} celebration={celebration} clearCelebration={() => setCelebration(null)}/>;
    else content = <div className="panel empty-support"><Icon name="compass"/><h1>{t('Данные ещё не загрузились', 'Data is not loaded yet', 'Деректер әлі жүктелмеді')}</h1><button className="primary" disabled={!!busy} onClick={() => void run('refresh', refreshCurrent)}>{t('Попробовать снова', 'Try again', 'Қайталап көру')}</button></div>;
    return <div className="app-shell"><a href="#workspace" className="skip-link">{t('К основному содержимому', 'Skip to content', 'Негізгі мазмұнға өту')}</a>
        <aside className="sidebar"><a href="#workspace" className="brand-link" onClick={goHome} aria-label={t('Career Quest, главная', 'Career Quest, home', 'Career Quest, басты бет')}><Brand/></a><div className="workspace-label">{account.role === 'hr' ? t('РАЗВИТИЕ КОМАНДЫ', 'TEAM DEVELOPMENT', 'КОМАНДАНЫ ДАМЫТУ') : t('МОЁ РАЗВИТИЕ', 'MY DEVELOPMENT', 'МЕНІҢ ДАМУЫМ')}</div>
            <nav aria-label={t('Разделы Career Quest', 'Career Quest sections', 'Career Quest бөлімдері')}>{(account.role === 'hr' ? hrNav : employeeNav).map(item => <button key={item.id} aria-label={item.label} disabled={!!busy} className={page === item.id ? 'active' : ''} aria-current={page === item.id ? 'page' : undefined} onClick={() => navigate(item.id)}><Icon name={item.icon}/><span>{item.label}</span>{item.id === 'catalog' && catalog && <small>{catalog.counts.events}</small>}{item.id === 'skill-catalog' && catalog && <small>{catalog.counts.skills}</small>}{item.id === 'quests' && !!profile?.available.length && <small>{profile.available.length}</small>}</button>)}</nav>
            <div className="sidebar-bottom"><div className="sidebar-note"><Icon name="leaf"/><strong>{t('Растите в своём темпе', 'Grow at your own pace', 'Өз қарқыныңызбен дамыңыз')}</strong><p>{t('Каждый полезный шаг имеет значение.', 'Every useful step matters.', 'Әр пайдалы қадам маңызды.')}</p></div><button className="logout" disabled={!!busy} onClick={logout}><Icon name="logout"/>{t('Выйти из аккаунта', 'Sign out', 'Аккаунттан шығу')}</button></div>
        </aside>
        <div className="main-shell"><header className="topbar"><nav className="breadcrumb" aria-label={t('Навигационная цепочка', 'Breadcrumb', 'Навигация жолы')}><button className="text-button" disabled={!!busy} onClick={goHome}>{t('Пространство роста', 'Growth workspace', 'Даму кеңістігі')}</button><Icon name="chevron"/>{account.role === 'hr' && isProfilePage && profile && <><button className="text-button" disabled={!!busy} onClick={() => navigate('profile')}>{profile.employee.name}</button><Icon name="chevron"/></>}<strong aria-current="page">{activeLabel}</strong></nav><div className="topbar-actions"><LanguageSelect disabled={!!busy}/><button className="topbar-user account-trigger" aria-label={t('Открыть мой аккаунт', 'Open my account', 'Менің аккаунтымды ашу')} disabled={!!busy} onClick={() => navigate('account')}><span className="avatar small-avatar">{initials(who)}</span><span className="user-name">{who}<small>{account.role === 'hr' ? t('HR-специалист', 'HR specialist', 'HR маманы') : t('Личный прогресс', 'Personal progress', 'Жеке прогресс')}</small></span><Icon name="chevron"/></button></div></header>
            <main id="workspace" className="workspace" ref={headingRef} tabIndex={-1}>{alerts}
                {account.role === 'hr' && isProfilePage && profile && <section className="hr-profile-navigation"><div className="hr-profile-toolbar"><button className="text-button" disabled={!!busy} onClick={() => navigate('hr')}>← {t('К команде', 'Back to team', 'Командаға оралу')}</button><label>{t('Сотрудник', 'Employee', 'Қызметкер')}<select value={profile.employee.id} disabled={!!busy} onChange={event => openProfile(event.target.value)}>{people.map(person => <option key={person.id} value={person.id}>{person.name} · {person.role_label ?? person.role} · {person.id}</option>)}</select></label></div><nav className="profile-tabs" aria-label={t('Разделы профиля сотрудника', 'Employee profile sections', 'Қызметкер профилінің бөлімдері')}>{employeeNav.map(item => <button key={item.id} className={page === item.id ? 'active' : ''} aria-current={page === item.id ? 'page' : undefined} disabled={!!busy} onClick={() => navigate(item.id)}>{item.id === 'profile' ? t('Траектория', 'Trajectory', 'Даму жолы') : item.label}</button>)}</nav></section>}
                {content}<footer className="workspace-footer"><span>CAREER QUEST <span className="dot">/</span> {t('КАЖДЫЙ ШАГ ИМЕЕТ ЗНАЧЕНИЕ', 'EVERY STEP MATTERS', 'ӘР ҚАДАМ МАҢЫЗДЫ')}</span><span>{t('Создано для вашего роста', 'Built for your growth', 'Сіздің дамуыңыз үшін')} <Icon name="leaf"/></span></footer>
            </main>
        </div>{busy && busy !== 'recommend' && <div className="working" role="status"><span className="spinner"/>{busyLabels[busy] ?? t('Загрузка', 'Loading', 'Жүктелуде')}…</div>}
    </div>;
}
createRoot(document.getElementById('root')!).render(<I18nProvider><App/></I18nProvider>);
