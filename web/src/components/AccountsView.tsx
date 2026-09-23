import { useState, type FormEvent } from 'react';
import { api, type Employee, type Invitation, type RegisteredAccount } from '../api';
import { useI18n } from '../i18n';
import { INTERNAL_ROLES, isAccountRole, isStaffRole, roleLabel, type InternalRole } from '../roles';
import { Icon } from './Icons';

export function AccountsView({ accounts, people, busy, run, refresh, initialRole = 'employee' }: {
    accounts: RegisteredAccount[]; people: Employee[]; busy: string;
    run: (label: string, action: () => Promise<void>) => Promise<boolean>; refresh: () => Promise<void>;
    initialRole?: InternalRole;
}) {
    const { t, locale } = useI18n();
    const [role, setRole] = useState<InternalRole>(initialRole);
    const [employeeId, setEmployeeId] = useState('');
    const [invitation, setInvitation] = useState<Invitation | null>(null);
    const [copyStatus, setCopyStatus] = useState('');
    const available = people.filter(person => !accounts.some(account => account.employee_id === person.id));
    async function create(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        if (isStaffRole(role) && !employeeId) return;
        await run('invite', async () => {
            const result = await api<Invitation>('/hr/invitations', { method: 'POST', body: JSON.stringify({ role, employee_id: isStaffRole(role) ? employeeId : null }) });
            setInvitation(result); setCopyStatus('');
        });
    }
    async function copyInvitation() {
        if (!invitation) return;
        try {
            if (!navigator.clipboard) throw new Error('Clipboard unavailable');
            await navigator.clipboard.writeText(invitation.invite_code);
            setCopyStatus(t('Код скопирован', 'Code copied', 'Код көшірілді'));
        } catch { setCopyStatus(t('Выделите код и скопируйте вручную.', 'Select and copy the code manually.', 'Кодты таңдап, қолмен көшіріңіз.')); }
    }
    return <><div className="page-heading"><div><span className="eyebrow">{t('HR · ДОСТУП К КОМАНДЕ', 'HR · TEAM ACCESS', 'HR · КОМАНДАҒА ҚОЛЖЕТІМДІЛІК')}</span><h1>{t('Аккаунты и приглашения', 'Accounts and invitations', 'Аккаунттар және шақырулар')}</h1><p className="muted">{t('Свяжите аккаунт сотрудника с его профилем через персональное приглашение.', 'Link an employee account to their profile with a personal invitation.', 'Жеке шақыру арқылы қызметкер аккаунтын оның профилімен байланыстырыңыз.')}</p></div><button className="secondary" disabled={!!busy} onClick={() => void run('refresh', refresh)}><Icon name="refresh"/>{t('Обновить', 'Refresh', 'Жаңарту')}</button></div>
        <section className="panel invitation-panel"><h2>{t('Пригласить в пространство', 'Invite to the workspace', 'Кеңістікке шақыру')}</h2><form className="invitation-form" onSubmit={event => void create(event)}><label htmlFor="invitation-role">{t('Роль аккаунта', 'Account role', 'Есептік жазба рөлі')}<select id="invitation-role" name="role" disabled={!!busy} value={role} onChange={event => { const value = event.target.value; if (isAccountRole(value) && value !== 'client') setRole(value); setEmployeeId(''); setInvitation(null); setCopyStatus(''); }}>{INTERNAL_ROLES.map(value => <option key={value} value={value}>{roleLabel(value, locale)}</option>)}</select></label>{isStaffRole(role) && <label htmlFor="invitation-employee">{t('Профиль сотрудника', 'Employee profile', 'Қызметкер профилі')}<select id="invitation-employee" name="employee_id" required disabled={!!busy} value={employeeId} onChange={event => setEmployeeId(event.target.value)}><option value="">{t('Выберите сотрудника', 'Select an employee', 'Қызметкерді таңдаңыз')}</option>{available.map(person => <option key={person.id} value={person.id}>{person.name} · {person.role_label ?? person.role} · {person.id}</option>)}</select></label>}<button className="primary" disabled={!!busy || (isStaffRole(role) && !employeeId)}><Icon name="users"/>{t('Создать приглашение', 'Create invitation', 'Шақыру жасау')}</button></form>{isStaffRole(role) && !available.length && <p className="small muted">{t('У всех загруженных сотрудников уже есть аккаунт. Для новых сотрудников сначала загрузите профили.', 'All imported employees already have an account. Import profiles for new employees first.', 'Жүктелген барлық қызметкерлердің аккаунты бар. Алдымен жаңа қызметкерлердің профильдерін жүктеңіз.')}</p>}
            {invitation && <div className="invitation-result" role="status"><strong>{t('Одноразовое приглашение готово', 'One-time invitation is ready', 'Бір реттік шақыру дайын')}</strong><p>{t('Передайте этот код лично приглашённому пользователю.', 'Share this code directly with the invited person.', 'Бұл кодты шақырылған пайдаланушыға жеке беріңіз.')}</p><code>{invitation.invite_code}</code><p className="small">{roleLabel(invitation.role, locale)}{invitation.employee_id && <>: {invitation.employee_id}</>} · {t('Действует до', 'Expires', 'Мерзімі')} {new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(invitation.expires_at * 1000))}</p><button className="secondary" onClick={() => void copyInvitation()}>{t('Скопировать код', 'Copy code', 'Кодты көшіру')}</button><span className="small">{copyStatus}</span></div>}
        </section>
        <section className="panel section-space"><div className="section-heading"><h2>{t('Аккаунты команды', 'Team accounts', 'Команда аккаунттары')}</h2><span className="count">{accounts.length}</span></div><div className="table-wrap" role="region" aria-label={t('Аккаунты команды', 'Team accounts', 'Команда аккаунттары')} tabIndex={0}><table><thead><tr><th>{t('Имя', 'Name', 'Аты')}</th><th>{t('Логин', 'Username', 'Логин')}</th><th>{t('Роль', 'Role', 'Рөл')}</th><th>{t('Профиль', 'Profile', 'Профиль')}</th></tr></thead><tbody>{accounts.map(account => <tr key={account.id}><th scope="row">{account.display_name}</th><td>{account.username}</td><td>{roleLabel(account.role, locale)}</td><td>{account.employee_id ?? '—'}</td></tr>)}</tbody></table></div></section>
    </>;
}
