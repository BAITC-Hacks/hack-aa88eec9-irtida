import { useState, type FormEvent, type ReactNode } from 'react';
import type { AuthMode, AuthRequest, AuthStatus } from '../api';
import { useI18n } from '../i18n';
import { isAccountRole, ROLES, roleLabel, type AccountRole } from '../roles';
import { Brand, Icon } from './Icons';

export function LanguageSelect({ disabled = false }: { disabled?: boolean }) {
    const { locale, setLocale, t } = useI18n();
    return <label className="language-select"><span className="sr-only">{t('Язык интерфейса', 'Interface language', 'Интерфейс тілі')}</span><select aria-label={t('Язык интерфейса', 'Interface language', 'Интерфейс тілі')} value={locale} disabled={disabled} onChange={event => setLocale(event.target.value === 'kk' ? 'kk' : event.target.value === 'en' ? 'en' : 'ru')}><option value="ru">RU · Русский</option><option value="en">EN · English</option><option value="kk">KK · Қазақша</option></select></label>;
}

export function AuthView({ status, busy, error, alerts, onSubmit, onRetry, initialMode = 'login', initialRole = 'employee' }: {
    status: AuthStatus | null;
    busy: boolean;
    error: string;
    alerts?: ReactNode;
    onSubmit: (mode: AuthMode, request: AuthRequest) => Promise<boolean>;
    onRetry: () => void;
    initialMode?: AuthMode;
    initialRole?: AccountRole;
}) {
    const { t, locale } = useI18n();
    const [mode, setMode] = useState<AuthMode>(initialMode);
    const [role, setRole] = useState<AccountRole>(initialRole);
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [displayName, setDisplayName] = useState('');
    const [invite, setInvite] = useState('');
    const [showPassword, setShowPassword] = useState(false);
    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (busy) return;
        await onSubmit(mode, { username: username.trim(), password, role: mode === 'setup' ? 'hr' : role,
            ...(mode === 'setup' || (mode === 'register' && role === 'client') ? { display_name: displayName.trim() } : {}),
            ...(mode === 'register' && role !== 'client' ? { invite_code: invite.trim() } : {}),
        });
    }
    const title = mode === 'setup' ? t('Создайте рабочее пространство', 'Create your workspace', 'Жұмыс кеңістігін құрыңыз') : mode === 'register' ? role === 'client' ? t('Создайте клиентский аккаунт', 'Create a client account', 'Клиенттік аккаунт құрыңыз') : t('Присоединитесь к команде', 'Join your team', 'Командаға қосылыңыз') : t('С возвращением', 'Welcome back', 'Қайта оралуыңызбен');
    return <div className="welcome-shell auth-shell">
        <header className="welcome-header"><a href="#welcome" aria-label="Career Quest"><Brand/></a><LanguageSelect disabled={busy}/></header>
        {alerts}
        <main className="welcome" id="welcome"><section className="welcome-copy"><span className="eyebrow">{t('РАЗВИТИЕ, В КОТОРОМ ЕСТЬ СМЫСЛ', 'GROWTH WITH A PURPOSE', 'МАҒЫНАЛЫ ДАМУ')}</span><h1>{t('Ваш рост.', 'Your growth.', 'Сіздің дамуыңыз.')}<br/>{t('Ваш маршрут.', 'Your journey.', 'Сіздің жолыңыз.')}<br/><em>{t('Ваш следующий шаг.', 'Your next step.', 'Сіздің келесі қадамыңыз.')}</em></h1><p>{t('Понятный путь от текущих навыков к следующему уровню. Персональные рекомендации, конкретные действия и заметный прогресс.', 'A clear path from today’s skills to your next level. Personal recommendations, practical steps and visible progress.', 'Қазіргі дағдылардан келесі деңгейге апаратын түсінікті жол. Жеке ұсыныстар, нақты қадамдар және көрінетін прогресс.')}</p>
            <div className="welcome-steps"><span><b>01</b>{t('Увидеть цель', 'Find your goal', 'Мақсатты көру')}</span><Icon name="arrow"/><span><b>02</b>{t('Выбрать шаг', 'Choose a step', 'Қадамды таңдау')}</span><Icon name="arrow"/><span><b>03</b>{t('Заметить рост', 'See your growth', 'Дамуды байқау')}</span></div>
            <div className="welcome-note"><Icon name="leaf"/>{t('Без гонки с коллегами. В своём ритме.', 'No race with colleagues. At your own pace.', 'Әріптестермен жарыссыз. Өз қарқыныңызбен.')}</div>
            <div className="role-diversity"><span>{t('Для разных карьерных путей', 'For different career paths', 'Әртүрлі мансап жолдары үшін')}</span><p>{t('Продажи · Поддержка клиентов · HR · Продукт · Аналитика · Разработка', 'Sales · Customer Support · HR · Product · Analytics · Engineering', 'Сату · Клиенттерді қолдау · HR · Өнім · Аналитика · Әзірлеу')}</p></div>
        </section>
        <section className="login-card auth-card" aria-labelledby="auth-title"><span className="large-icon"><Icon name={mode === 'setup' ? 'users' : 'compass'}/></span><h2 id="auth-title">{title}</h2><p className="muted">{mode === 'setup' ? t('Первый HR-аккаунт управляет каталогом, данными и приглашениями сотрудников.', 'The first HR account manages your catalog, data and employee invitations.', 'Алғашқы HR аккаунты каталогты, деректерді және қызметкерлерді шақыруды басқарады.') : mode === 'register' ? role === 'client' ? t('Клиентский аккаунт создаётся без приглашения и не открывает данные сотрудников.', 'Clients can register without an invitation. Employee data stays private.', 'Клиент шақырусыз тіркеле алады. Қызметкерлер деректеріне қолжетімділік берілмейді.') : t('Используйте одноразовое приглашение, которое выдал HR.', 'Use the one-time invitation provided by HR.', 'HR берген бір реттік шақыруды пайдаланыңыз.') : t('Войдите в своё пространство развития.', 'Sign in to your development workspace.', 'Өзіңіздің даму кеңістігіңізге кіріңіз.')}</p>
            {error && <div className="auth-error" role="alert"><Icon name="shield"/><span>{error}</span></div>}
            {!status ? <div className="empty-support"><p>{t('Не удалось проверить доступность входа.', 'Could not check sign-in availability.', 'Кіру мүмкіндігін тексеру мүмкін болмады.')}</p><button className="secondary" disabled={busy} onClick={onRetry}>{t('Повторить проверку', 'Try again', 'Қайта тексеру')}</button></div> : <form onSubmit={event => void submit(event)} className="auth-form">
                <fieldset disabled={busy}>
                    <legend className="sr-only">{t('Данные аккаунта', 'Account details', 'Есептік жазба деректері')}</legend>
                    {mode !== 'setup' && <label htmlFor="account-role">{t('Роль аккаунта', 'Account role', 'Есептік жазба рөлі')}<select id="account-role" name="role" value={role} onChange={event => { if (isAccountRole(event.target.value)) setRole(event.target.value); }}>{ROLES.map(value => <option key={value} value={value}>{roleLabel(value, locale)}</option>)}</select></label>}
                    {(mode === 'setup' || (mode === 'register' && role === 'client')) && <label>{t('Ваше имя', 'Your name', 'Сіздің атыңыз')}<input name="display_name" autoComplete="name" value={displayName} onChange={event => setDisplayName(event.target.value)} required minLength={1} maxLength={120}/></label>}
                    <label>{t('Логин', 'Username', 'Логин')}<input name="username" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={event => setUsername(event.target.value)} required minLength={3} maxLength={80} pattern="[A-Za-z0-9][A-Za-z0-9_.@\-]*" placeholder={t('Ваш логин', 'Your username', 'Сіздің логиніңіз')}/><small>{t('Латинские буквы, цифры и символы . _ @ -', 'Latin letters, digits and . _ @ -', 'Латын әріптері, сандар және . _ @ -')}</small></label>
                    <label>{t('Пароль', 'Password', 'Құпиясөз')}<div className="password-field"><input name="password" type={showPassword ? 'text' : 'password'} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={password} onChange={event => setPassword(event.target.value)} required minLength={12} maxLength={128}/><button type="button" className="text-button" aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>{showPassword ? t('Скрыть', 'Hide', 'Жасыру') : t('Показать', 'Show', 'Көрсету')}</button></div>{mode !== 'login' && <small>{t('Не менее 12 символов.', 'At least 12 characters.', 'Кемінде 12 таңба.')}</small>}</label>
                    {mode === 'register' && role !== 'client' && <label>{t('Код приглашения', 'Invitation code', 'Шақыру коды')}<input name="invite_code" autoComplete="off" value={invite} onChange={event => setInvite(event.target.value)} required minLength={32} maxLength={128}/><small>{t('Приглашение определяет роль и связанный профиль.', 'The invitation determines your role and linked profile.', 'Шақыру рөлді және байланыстырылған профильді анықтайды.')}</small></label>}
                    <button className="primary full" type="submit">{busy ? t('Подождите…', 'Please wait…', 'Күте тұрыңыз…') : mode === 'setup' ? t('Создать HR-аккаунт', 'Create HR account', 'HR аккаунтын құру') : mode === 'register' ? t('Создать аккаунт', 'Create account', 'Аккаунт құру') : t('Войти', 'Sign in', 'Кіру')}<Icon name="arrow"/></button>
                </fieldset>
            </form>}
            {status && mode !== 'setup' && <p className="auth-switch">{mode === 'login' ? t('Нет аккаунта?', 'Need an account?', 'Аккаунтыңыз жоқ па?') : t('Уже есть аккаунт?', 'Already have an account?', 'Аккаунтыңыз бар ма?')} <button className="text-button" disabled={busy} onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>{mode === 'login' ? t('Зарегистрироваться', 'Register', 'Тіркелу') : t('Войти', 'Sign in', 'Кіру')}</button></p>}
            {status?.setup_required && mode !== 'setup' && <button className="text-button" disabled={busy} onClick={() => { setMode('setup'); setRole('hr'); }}>{t('Первичная настройка HR', 'First HR setup', 'HR бастапқы баптауы')}</button>}
            {mode === 'setup' && <p className="auth-switch"><button className="text-button" disabled={busy} onClick={() => { setMode('login'); setRole('employee'); }}>{t('Вернуться ко входу', 'Back to sign in', 'Кіруге оралу')}</button></p>}
            <div className="login-foot"><Icon name="shield"/><span>{t('Доступ определяется ролью аккаунта. Пароль хранится на сервере в защищённом виде.', 'Your account role determines access. Passwords are stored securely on the server.', 'Қолжетімділік есептік жазба рөлімен анықталады. Құпиясөз серверде қорғалған түрде сақталады.')}</span></div>
        </section></main><footer className="welcome-footer">CAREER QUEST <span>{t('Ваше развитие начинается с понятного «зачем».', 'Growth starts with a clear reason why.', 'Даму түсінікті мақсаттан басталады.')}</span></footer>
    </div>;
}
