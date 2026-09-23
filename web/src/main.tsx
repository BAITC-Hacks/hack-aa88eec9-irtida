import { useEffect, useRef, useState, type MouseEvent } from 'react';
import { createRoot } from 'react-dom/client';
import { api, ApiError, authenticate, completeEvent, type Account, type AuthMode, type AuthRequest, type AuthStatus, type Candidate, type Catalog, type Employee, type Metrics, type Personalization, type Profile, type Recommendations, type RegisteredAccount } from './api';
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
import { canOpenRoute, homeRoute, isProfilePage, parseRoute, routeHref, type Page, type ProfilePage, type Route } from './navigation';
import { isStaffRole, managesTeam, roleLabel } from './roles';
import './style.css';
import './styles/app-shell.css';

function App() {
    const { locale, t } = useI18n();
    const [account, setAccount] = useState<Account | null>(null);
    const [authStatus, setAuthStatus] = useState<AuthStatus | null>(null);
    const [booting, setBooting] = useState(true);
    const [busy, setBusy] = useState('');
    const busyRef = useRef(false);
    const [error, setError] = useState('');
    const [hash, setHash] = useState(window.location.hash);
    const [route, setRoute] = useState<Route>({ page: 'account' });
    const [routeFailed, setRouteFailed] = useState(false);
    const appliedRoute = useRef('');
    const page = route.page;
    const [people, setPeople] = useState<Employee[]>([]);
    const [profile, setProfile] = useState<Profile | null>(null);
    const [recommendation, setRecommendation] = useState<Recommendations | null>(null);
    const [personalization, setPersonalization] = useState<Personalization | null>(null);
    const [personalizationMode, setPersonalizationMode] = useState<'disabled' | 'mock' | 'nvidia'>('disabled');
    const [metrics, setMetrics] = useState<Metrics | null>(null);
    const [catalog, setCatalog] = useState<Catalog | null>(null);
    const [accounts, setAccounts] = useState<RegisteredAccount[]>([]);
    const [celebration, setCelebration] = useState<Celebration | null>(null);
    const [online, setOnline] = useState(navigator.onLine);
    const headingRef = useRef<HTMLElement>(null);
    const employeeNav: { id: ProfilePage; label: string; icon: IconName }[] = [
        { id: 'profile', label: t('Мой путь', 'My journey', 'Менің жолым'), icon: 'route' },
        { id: 'quests', label: t('Мои квесты', 'My quests', 'Менің квесттерім'), icon: 'compass' },
        { id: 'skills', label: t('Навыки', 'Skills', 'Дағдылар'), icon: 'chart' },
        { id: 'achievements', label: t('Достижения', 'Achievements', 'Жетістіктер'), icon: 'award' },
        { id: 'history', label: t('История', 'History', 'Тарих'), icon: 'clock' },
    ];
    const hrNav: { id: Page; label: string; icon: IconName }[] = [
        { id: 'team', label: t('Команда и аналитика', 'Team and analytics', 'Команда және аналитика'), icon: 'users' },
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
    const profilePage = isProfilePage(page);
    function clearSession() {
        setAccount(null); setProfile(null); setPeople([]); setMetrics(null); setCatalog(null); setAccounts([]);
        setRecommendation(null); setPersonalization(null); setCelebration(null); appliedRoute.current = ''; setRouteFailed(false);
    }
    function assignProfile(data: Profile) { setProfile(data); setRecommendation(data.recommendation); }
    async function loadProfile(id: string) { assignProfile(await api<Profile>(`/employees/${encodeURIComponent(id)}`)); }
    async function refreshTeam(who = account) {
        const manager = !!who && managesTeam(who.role);
        const [employees, overview] = await Promise.all([api<Employee[]>(manager ? '/team/employees' : '/employees'), api<Metrics>(manager ? '/team/overview' : '/hr/overview')]);
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
    async function loadRoute(who: Account, next: Route) {
        setRoute(next); setRouteFailed(false);
        try {
            if (!canOpenRoute(who, next)) throw new Error(t('Этот раздел недоступен для вашей роли.', 'This section is not available for your role.', 'Бұл бөлім сіздің рөліңізге қолжетімді емес.'));
            if (isProfilePage(next.page) && next.employeeId) {
                if (profile?.employee.id !== next.employeeId) { setProfile(null); setRecommendation(null); setPersonalization(null); setCelebration(null); }
                await Promise.all([
                    loadProfile(next.employeeId),
                    who.role === 'hr' || managesTeam(who.role)
                        ? api<Employee[]>(who.role === 'hr' ? '/employees' : '/team/employees').then(setPeople) : Promise.resolve(),
                ]);
            } else if (next.page === 'team') await refreshTeam(who);
            else if (next.page === 'catalog' || next.page === 'skill-catalog') await refreshCatalog();
            else if (next.page === 'accounts') await refreshAccounts();
            else if (next.page === 'account' && isStaffRole(who.role) && who.employee_id) await loadProfile(who.employee_id);
        } catch (reason) {
            setRouteFailed(true); setProfile(null); setRecommendation(null);
            throw reason;
        }
    }
    async function boot() {
        setBooting(true); setError('');
        try {
            const [status, health] = await Promise.all([api<AuthStatus>('/auth/status'), api<{ personalization_mode: 'disabled' | 'mock' | 'nvidia' }>('/health')]);
            setAuthStatus(status); setPersonalizationMode(health.personalization_mode);
            let who: Account | null = null;
            try { who = await api<Account>('/auth/me'); }
            catch (reason) { if (!(reason instanceof ApiError && reason.status === 401)) throw reason; }
            if (who) setAccount(who); else clearSession();
        } catch (reason) {
            if (reason instanceof ApiError && reason.status === 401) clearSession();
            setError((reason as Error).message);
        } finally { setBooting(false); }
    }
    useEffect(() => {
        void boot();
        const on = () => setOnline(true); const off = () => setOnline(false);
        const onHash = () => setHash(window.location.hash);
        window.addEventListener('hashchange', onHash);
        window.addEventListener('online', on); window.addEventListener('offline', off);
        return () => { window.removeEventListener('hashchange', onHash); window.removeEventListener('online', on); window.removeEventListener('offline', off); };
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
        await loadRoute(account, parseRoute(window.location.hash) ?? homeRoute(account));
    }
    // Native hash links preserve browser back/forward, reload and open-in-new-tab.
    // Navigation observed during a mutation is applied once that mutation finishes.
    useEffect(() => {
        if (!account || booting || busyRef.current) return;
        const next = parseRoute(hash) ?? homeRoute(account);
        const canonical = routeHref(next);
        if (hash !== canonical) { window.history.replaceState(null, '', canonical); setHash(canonical); }
        const key = `${account.role}:${account.employee_id}:${account.username}:${canonical}:${locale}`;
        if (appliedRoute.current === key) return;
        appliedRoute.current = key;
        void run('profile', async () => { await loadRoute(account, next); headingRef.current?.focus(); window.scrollTo({ top: 0, behavior: 'instant' }); });
    }, [hash, account, booting, busy, locale]);
    function navigate(next: Section | Page) {
        if (busyRef.current || !account) return;
        const target: Route = isProfilePage(next)
            ? { page: next, employeeId: route.employeeId ?? account.employee_id! }
            : { page: next === 'hr' ? 'team' : next };
        window.location.hash = routeHref(target);
    }
    function guardLink(event: MouseEvent<HTMLAnchorElement>) { if (busyRef.current) event.preventDefault(); }
    function openProfile(id: string) { if (!busyRef.current) window.location.hash = routeHref({ page: 'profile', employeeId: id }); }
    function logout() { void run('logout', async () => {
        await api('/auth/logout', { method: 'POST' }); clearSession();
        window.history.replaceState(null, '', '#/'); setHash('#/');
        setAuthStatus(await api<AuthStatus>('/auth/status'));
    }); }
    function login(mode: AuthMode, request: AuthRequest) {
        return run('login', async () => {
            const who = await authenticate(mode, request);
            setAccount(who); setAuthStatus(previous => previous ? { ...previous, setup_required: false } : previous);
        });
    }
    async function complete(event: Candidate) {
        if (!profile) return;
        const oldProfile = profile;
        await run('complete', async () => {
            const result = await completeEvent(oldProfile.employee.id, event); assignProfile(result.profile); setPersonalization(null);
            const completion = result.profile.history.find(item => !oldProfile.history.some(previous => previous.id === item.id));
            const gains = result.already_completed ? [] : Object.values(completion?.changes ?? {}).map(change => `${change.name}: ${change.before} → ${change.after}`);
            setCelebration({ title: event.title, before: percent(oldProfile.trajectory.coverage), after: percent(result.profile.trajectory.coverage), gains, already: result.already_completed });
            window.scrollTo({ top: 0, behavior: 'instant' });
        });
    }
    const who = account?.display_name || account?.username || (account ? roleLabel(account.role, locale) : '');
    const activeLabel = page === 'account' ? t('Мой аккаунт', 'My account', 'Менің аккаунтым') : [...hrNav, ...employeeNav].find(item => item.id === page)?.label;
    const offline = !online && <div className="message warning" role="status"><Icon name="shield"/>{t('Нет сети. Для загрузки и сохранения нужен сервер.', 'You are offline. Loading and saving require the server.', 'Желі жоқ. Жүктеу және сақтау үшін сервер қажет.')}</div>;
    const alerts = <>{offline}{error && <div className="message error" role="alert"><Icon name="shield"/><span>{error}</span><button className="text-button" disabled={!!busy} onClick={() => void run('refresh', refreshCurrent)}>{t('Обновить данные', 'Refresh data', 'Деректерді жаңарту')}</button><button className="icon-button" aria-label={t('Закрыть ошибку', 'Dismiss error', 'Қатені жабу')} onClick={() => setError('')}><Icon name="close"/></button></div>}</>;
    if (booting) return <div className="boot-screen"><Brand/><div className="skeleton"/><p role="status">{t('Открываем ваше пространство роста…', 'Opening your growth workspace…', 'Даму кеңістігіңіз ашылуда…')}</p></div>;
    if (!account) return <AuthView status={authStatus} busy={!!busy} error={error} alerts={offline} onSubmit={login} onRetry={() => void boot()}/>;

    let content;
    if (routeFailed) content = <div className="panel empty-support"><Icon name="shield"/><h1>{t('Не удалось открыть раздел', 'Unable to open this section', 'Бөлімді ашу мүмкін болмады')}</h1><a className="primary" href={routeHref(homeRoute(account))}>{t('На главную', 'Go home', 'Басты бетке')}</a></div>;
    else if (page === 'account') content = <AccountView account={account} profile={profile} busy={!!busy} onProfile={() => account.employee_id && openProfile(account.employee_id)} onLogout={logout}/>;
    else if (page === 'team' && (account.role === 'hr' || managesTeam(account.role)) && metrics) content = <><div className="team-role-summary" aria-label={t('Роли команды', 'Team roles', 'Команда рөлдері')}>{Array.from(new Set(people.map(person => person.role))).map(role => <span key={role}>{people.find(person => person.role === role)?.role_label ?? role} <b>{people.filter(person => person.role === role).length}</b></span>)}</div><HrView metrics={metrics} people={people} busy={busy} openProfile={openProfile} refresh={() => refreshTeam()} onImported={refreshAfterImport} run={run} hideImport viewerLabel={account.role === 'hr' ? undefined : roleLabel(account.role, locale)}/></>;
    else if ((page === 'catalog' || page === 'skill-catalog') && account.role === 'hr' && catalog) content = <CatalogView key={page} catalog={catalog} kind={page === 'catalog' ? 'events' : 'skills'} busy={!!busy} refresh={() => void run('refresh', refreshCatalog)}/>;
    else if (page === 'imports' && account.role === 'hr') content = <><div className="page-heading"><div><span className="eyebrow">{t('HR · ДАННЫЕ КОМАНДЫ', 'HR · TEAM DATA', 'HR · КОМАНДА ДЕРЕКТЕРІ')}</span><h1>{t('Импорт данных', 'Data import', 'Деректер импорты')}</h1><p className="muted">{t('Добавляйте профили, историю, навыки и активности из исходных файлов.', 'Add profiles, history, skills and activities from source files.', 'Бастапқы файлдардан профильдерді, тарихты, дағдыларды және іс-шараларды қосыңыз.')}</p></div></div><ImportPanel busy={busy} run={run} onImported={refreshAfterImport}/></>;
    else if (page === 'accounts' && account.role === 'hr') content = <AccountsView accounts={accounts} people={people} busy={busy} run={run} refresh={refreshAccounts}/>;
    else if (profilePage && profile && profile.employee.id === route.employeeId) content = <ProfileView profile={profile} recommendation={recommendation} personalization={personalization} personalizationMode={personalizationMode} section={page as Section} employee={isStaffRole(account.role) && profile.employee.id === account.employee_id} canRecommend={account.role === 'hr' || (isStaffRole(account.role) && profile.employee.id === account.employee_id)} busy={busy} onRecommend={() => void run('recommend', async () => setRecommendation(await api<Recommendations>(`/employees/${encodeURIComponent(profile.employee.id)}/recommendations`, { method: 'POST' })))} onPersonalize={() => void run('personalize', async () => setPersonalization(await api<Personalization>(`/employees/${encodeURIComponent(profile.employee.id)}/personalization`, { method: 'POST' })))} onComplete={event => void complete(event)} onNavigate={navigate} celebration={celebration} clearCelebration={() => setCelebration(null)}/>;
    else content = <div className="panel empty-support"><Icon name="compass"/><h1>{t('Данные ещё не загрузились', 'Data is not loaded yet', 'Деректер әлі жүктелмеді')}</h1><button className="primary" disabled={!!busy} onClick={() => void run('refresh', refreshCurrent)}>{t('Попробовать снова', 'Try again', 'Қайталап көру')}</button></div>;
    const homeHref = routeHref(homeRoute(account));
    const accountLabel = account.role === 'client' ? t('Личный кабинет', 'Personal account', 'Жеке кабинет') : t('Мой аккаунт', 'My account', 'Менің аккаунтым');
    const navigation = account.role === 'hr' ? hrNav : isStaffRole(account.role) ? [...employeeNav, ...(managesTeam(account.role) ? [hrNav[0]] : [])] : [{ id: 'account' as const, label: accountLabel, icon: 'users' as const }];
    const teamProfile = (account.role === 'hr' || managesTeam(account.role)) && profilePage && profile && profile.employee.id === route.employeeId && !routeFailed;
    const profilePeople = profile && !people.some(person => person.id === profile.employee.id) ? [profile.employee, ...people] : people;
    const pageHref = (next: Page, employeeId = account.employee_id) => routeHref(isProfilePage(next) ? { page: next, employeeId: employeeId! } : { page: next });
    return <div className="app-shell"><a href="#workspace" className="skip-link" onClick={event => { event.preventDefault(); headingRef.current?.focus(); }}>{t('К основному содержимому', 'Skip to content', 'Негізгі мазмұнға өту')}</a>
        <aside className="sidebar"><a href={homeHref} className="brand-link" onClick={guardLink} aria-label={t('Career Quest, главная', 'Career Quest, home', 'Career Quest, басты бет')}><Brand/></a><div className="workspace-label">{account.role === 'client' ? accountLabel : account.role === 'hr' ? t('РАЗВИТИЕ КОМАНДЫ', 'TEAM DEVELOPMENT', 'КОМАНДАНЫ ДАМЫТУ') : t('МОЁ РАЗВИТИЕ', 'MY DEVELOPMENT', 'МЕНІҢ ДАМУЫМ')}</div>
            <nav aria-label={t('Разделы Career Quest', 'Career Quest sections', 'Career Quest бөлімдері')}>{navigation.map(item => {
                const active = page === item.id && (!isProfilePage(item.id) || route.employeeId === account.employee_id);
                return <a key={item.id} href={pageHref(item.id)} aria-label={item.label} aria-disabled={!!busy} onClick={guardLink} className={active ? 'active' : ''} aria-current={active ? 'page' : undefined}><Icon name={item.icon}/><span>{item.label}</span>{item.id === 'catalog' && catalog && <small>{catalog.counts.events}</small>}{item.id === 'skill-catalog' && catalog && <small>{catalog.counts.skills}</small>}{item.id === 'quests' && profile?.employee.id === account.employee_id && !!profile?.available.length && <small>{profile.available.length}</small>}</a>;
            })}</nav>
            <div className="sidebar-bottom">{account.role !== 'client' && <div className="sidebar-note"><Icon name="leaf"/><strong>{t('Растите в своём темпе', 'Grow at your own pace', 'Өз қарқыныңызбен дамыңыз')}</strong><p>{t('Каждый полезный шаг имеет значение.', 'Every useful step matters.', 'Әр пайдалы қадам маңызды.')}</p></div>}<button className="logout" disabled={!!busy} onClick={logout}><Icon name="logout"/>{t('Выйти из аккаунта', 'Sign out', 'Аккаунттан шығу')}</button></div>
        </aside>
        <div className="main-shell"><header className="topbar"><nav className="breadcrumb" aria-label={t('Навигационная цепочка', 'Breadcrumb', 'Навигация жолы')}><a href={homeHref} onClick={guardLink} aria-disabled={!!busy}>{account.role === 'client' ? accountLabel : t('Пространство роста', 'Growth workspace', 'Даму кеңістігі')}</a><Icon name="chevron"/>{teamProfile && <><a href="#/team" onClick={guardLink} aria-disabled={!!busy}>{t('Команда', 'Team', 'Команда')}</a><Icon name="chevron"/><a href={pageHref('profile', profile.employee.id)} onClick={guardLink} aria-disabled={!!busy}>{profile.employee.name}</a><Icon name="chevron"/></>}<a href={routeHref(route)} aria-current="page" onClick={guardLink} aria-disabled={!!busy}>{page === 'account' ? accountLabel : activeLabel}</a></nav><div className="topbar-actions"><LanguageSelect disabled={!!busy}/><a href="#/account" className="topbar-user account-trigger" aria-label={t('Открыть мой аккаунт', 'Open my account', 'Менің аккаунтымды ашу')} aria-disabled={!!busy} onClick={guardLink}><span className="avatar small-avatar">{initials(who)}</span><span className="user-name">{who}<small>{roleLabel(account.role, locale)}</small></span><Icon name="chevron"/></a></div></header>
            <main id="workspace" className="workspace" ref={headingRef} tabIndex={-1}>{alerts}
                {teamProfile && <section className="hr-profile-navigation"><div className="hr-profile-toolbar"><a className="text-button" href="#/team" onClick={guardLink} aria-disabled={!!busy}>← {t('К команде', 'Back to team', 'Командаға оралу')}</a><label>{t('Сотрудник', 'Employee', 'Қызметкер')}<select value={profile.employee.id} disabled={!!busy} onChange={event => openProfile(event.target.value)}>{profilePeople.map(person => <option key={person.id} value={person.id}>{person.name} · {person.role_label ?? person.role} · {person.id}</option>)}</select></label></div><nav className="profile-tabs" aria-label={t('Разделы профиля сотрудника', 'Employee profile sections', 'Қызметкер профилінің бөлімдері')}>{employeeNav.map(item => <a key={item.id} href={pageHref(item.id, profile.employee.id)} className={page === item.id ? 'active' : ''} aria-current={page === item.id ? 'page' : undefined} aria-disabled={!!busy} onClick={guardLink}>{item.id === 'profile' ? t('Траектория', 'Trajectory', 'Даму жолы') : item.label}</a>)}</nav></section>}
                {content}<footer className="workspace-footer"><span>CAREER QUEST <span className="dot">/</span> {t('КАЖДЫЙ ШАГ ИМЕЕТ ЗНАЧЕНИЕ', 'EVERY STEP MATTERS', 'ӘР ҚАДАМ МАҢЫЗДЫ')}</span><span>{t('Создано для вашего роста', 'Built for your growth', 'Сіздің дамуыңыз үшін')} <Icon name="leaf"/></span></footer>
            </main>
        </div>{busy && busy !== 'recommend' && <div className="working" role="status"><span className="spinner"/>{busyLabels[busy] ?? t('Загрузка', 'Loading', 'Жүктелуде')}…</div>}
    </div>;
}
createRoot(document.getElementById('root')!).render(<I18nProvider><App/></I18nProvider>);
