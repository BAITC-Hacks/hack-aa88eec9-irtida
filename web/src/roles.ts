import { translate, type Locale } from './i18n';

export const ROLES = ['employee', 'hr', 'manager', 'operator', 'supervisor', 'client'] as const;
export type AccountRole = typeof ROLES[number];
export const STAFF_ROLES = ['employee', 'manager', 'operator', 'supervisor'] as const;
export type StaffRole = typeof STAFF_ROLES[number];
export const INTERNAL_ROLES = ['employee', 'hr', 'manager', 'operator', 'supervisor'] as const;
export type InternalRole = typeof INTERNAL_ROLES[number];
export function isAccountRole(role: string): role is AccountRole { return (ROLES as readonly string[]).includes(role); }
export function isStaffRole(role: AccountRole): role is StaffRole { return (STAFF_ROLES as readonly string[]).includes(role); }
export function isHr(role: AccountRole) { return role === 'hr'; }
export function managesTeam(role: AccountRole) { return role === 'manager' || role === 'supervisor'; }
export const canViewTeam = managesTeam;
export function roleLabel(role: AccountRole, locale: Locale = 'ru') {
    const labels: Record<AccountRole, [string, string, string]> = {
        employee: ['Сотрудник', 'Employee', 'Қызметкер'],
        hr: ['HR-специалист', 'HR specialist', 'HR маманы'],
        manager: ['Руководитель', 'Manager', 'Басшы'],
        operator: ['Оператор', 'Operator', 'Оператор'],
        supervisor: ['Супервизор', 'Supervisor', 'Супервизор'],
        client: ['Клиент', 'Client', 'Клиент'],
    };
    return translate(locale, ...labels[role]);
}
