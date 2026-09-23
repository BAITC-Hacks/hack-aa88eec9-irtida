import type { Account } from './api';
import { isStaffRole, managesTeam } from './roles';

export const PROFILE_PAGES = ['profile', 'quests', 'skills', 'history', 'achievements'] as const;
export type ProfilePage = typeof PROFILE_PAGES[number];
export type Page = ProfilePage | 'team' | 'catalog' | 'skill-catalog' | 'imports' | 'accounts' | 'account';
export type Route = { page: ProfilePage; employeeId: string } | { page: Exclude<Page, ProfilePage>; employeeId?: never };
const workspacePages = new Set(['team', 'catalog', 'skill-catalog', 'imports', 'accounts', 'account']);
export function isProfilePage(page: string): page is ProfilePage { return (PROFILE_PAGES as readonly string[]).includes(page); }

export function parseRoute(hash: string): Route | null {
    const parts = hash.replace(/^#\//, '').split('/');
    if (!hash.startsWith('#/')) return null;
    if (parts.length === 1 && workspacePages.has(parts[0])) return { page: parts[0] as Exclude<Page, ProfilePage> };
    if (parts.length === 3 && parts[0] === 'employees' && isProfilePage(parts[2])) {
        try {
            const employeeId = decodeURIComponent(parts[1]);
            if (/^[A-Za-z0-9_-]{1,80}$/.test(employeeId)) return { page: parts[2], employeeId };
        } catch { /* Malformed URI escapes are an invalid route, not an app crash. */ }
    }
    return null;
}
export function routeHref(route: Route): string {
    return 'employeeId' in route && route.employeeId
        ? `#/employees/${encodeURIComponent(route.employeeId)}/${route.page}` : `#/${route.page}`;
}
export function homeRoute(account: Account): Route {
    if (account.role === 'hr') return { page: 'team' };
    if (isStaffRole(account.role) && account.employee_id) return { page: 'profile', employeeId: account.employee_id };
    return { page: 'account' };
}
// Client-side routing avoids sending clearly forbidden requests. The API remains
// responsible for employee ownership and the manager's exact direct-report scope.
export function canOpenRoute(account: Account, route: Route): boolean {
    if (route.page === 'account') return true;
    if (isProfilePage(route.page)) return account.role === 'hr' || managesTeam(account.role)
        || (isStaffRole(account.role) && route.employeeId === account.employee_id);
    if (route.page === 'team') return account.role === 'hr' || managesTeam(account.role);
    return account.role === 'hr';
}
