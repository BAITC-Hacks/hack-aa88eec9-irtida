import type { Account, Profile } from '../api';
import { useI18n } from '../i18n';
import { isStaffRole, managesTeam, roleLabel } from '../roles';
import { initials } from '../view-model';
import { Icon } from './Icons';

export function AccountView({ account, profile, onProfile, onLogout, busy }: {
    account: Account; profile: Profile | null; onProfile: () => void; onLogout: () => void; busy: boolean;
}) {
    const { t, locale } = useI18n();
    const name = account.display_name || (isStaffRole(account.role) && profile?.employee.id === account.employee_id ? profile.employee.name : null) || t('Мой аккаунт', 'My account', 'Менің аккаунтым');
    const access = account.role === 'hr' ? t('Профили команды, каталог, аналитика и приглашения', 'Team profiles, catalog, analytics and invitations', 'Команда профильдері, каталог, аналитика және шақырулар')
        : account.role === 'client' ? t('Собственный клиентский аккаунт. Данные сотрудников недоступны.', 'Your own client account. Employee data is not accessible.', 'Жеке клиенттік аккаунт. Қызметкерлер деректері қолжетімсіз.')
        : managesTeam(account.role) ? t('Личная траектория и просмотр профилей прямых подчинённых', 'Personal development and read-only profiles of direct reports', 'Жеке даму жолы және тікелей бағыныштылардың профильдерін тек қарау')
        : t('Личная траектория, навыки и активности', 'Personal trajectory, skills and activities', 'Жеке даму жолы, дағдылар және іс-шаралар');
    return <><div className="page-heading"><div><span className="eyebrow">{t('ВАШЕ ПРОСТРАНСТВО', 'YOUR WORKSPACE', 'СІЗДІҢ КЕҢІСТІГІҢІЗ')}</span><h1>{t('Мой аккаунт', 'My account', 'Менің аккаунтым')}</h1><p className="muted">{t('Данные входа и доступ к вашему рабочему пространству.', 'Your sign-in information and workspace access.', 'Кіру деректері және жұмыс кеңістігіне қолжетімділік.')}</p></div></div>
        <section className="panel account-panel"><span className="avatar account-avatar">{initials(name)}</span><div><h2>{name}</h2><span className="grade-chip">{roleLabel(account.role, locale)}</span></div>
            <dl className="account-details"><div><dt>{t('Логин', 'Username', 'Логин')}</dt><dd>{account.username || t('Демонстрационная сессия', 'Demo session', 'Демо сессия')}</dd></div><div><dt>{t('Права доступа', 'Access', 'Қолжетімділік')}</dt><dd>{access}</dd></div>{account.employee_id && <div><dt>{t('Профиль сотрудника', 'Employee profile', 'Қызметкер профилі')}</dt><dd>{account.employee_id}</dd></div>}</dl>
            <div className="account-actions">{isStaffRole(account.role) && <button className="primary" disabled={busy} onClick={onProfile}>{t('Открыть мою траекторию', 'Open my trajectory', 'Менің даму жолымды ашу')}<Icon name="route"/></button>}<button className="secondary" disabled={busy} onClick={onLogout}><Icon name="logout"/>{t('Выйти из аккаунта', 'Sign out', 'Аккаунттан шығу')}</button></div>
        </section></>;
}
