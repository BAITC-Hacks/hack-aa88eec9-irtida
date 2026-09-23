import { getLocale, translate } from './i18n';

export type Account = {
    role: "employee" | "hr";
    employee_id: string | null;
    username?: string;
    display_name?: string;
};
export type AuthStatus = { setup_required: boolean; registration: 'invite'; demo_enabled: boolean };
export type AuthRequest = { username: string; password: string; role: 'employee' | 'hr'; invite_code?: string; display_name?: string };
export type AuthMode = 'login' | 'register' | 'setup';
export type RegisteredAccount = Account & { id: string; username: string; display_name: string; created_at: number };
export type Invitation = { invite_code: string; role: Account['role']; employee_id: string | null; expires_at: number };
export type CatalogSkill = { id: string; name: string; kind: 'hard' | 'soft'; category?: string; description?: string };
export type CatalogEvent = {
    id: string; title: string; type: string; roles: string[]; grades: string[];
    effects: Record<string, { gain: number; max_level: number }>;
    description?: string; format?: string; mandatory?: boolean; duration_hours?: number;
    prerequisites?: Record<string, number>; upcoming_sessions?: string[];
};
export type Catalog = {
    role_labels?: Record<string, string>;
    skills: CatalogSkill[];
    events: CatalogEvent[];
    grade_rules: { role: string; grade: string; next_grade: string; requirements: Record<string, number>; critical_skills?: string[] }[];
    counts: { skills: number; events: number; grade_rules: number };
};
export type Employee = {
    id: string;
    name: string;
    role: string;
    role_label?: string;
    grade: string;
    tenure_months: number;
    skills: Record<string, number>;
    source_format?: 'kit-v1';
    snapshot_date?: string;
    last_review_date?: string;
    department?: string;
    work_format?: 'office' | 'hybrid' | 'remote';
    preferred_language?: 'kk' | 'ru' | 'en';
    career_goal?: { target_role: string; target_grade: string } | null;
};
export type Candidate = {
    id: string;
    title: string;
    type: string;
    projected_coverage: number | null;
    critical_benefit: number;
    session_date?: string | null;
    occurrence_id?: string | null;
    changes: Record<string, {
        name: string;
        before: number;
        after: number;
        gain: number;
    }>;
    evidence: {
        factor: string;
        text: string;
    }[];
};
export type Recommendations = {
    items: Candidate[];
    mode: "rules" | "ai" | "fallback" | "no_candidates";
    reason: string | null;
    cached: boolean;
    provider: string | null;
    model: string | null;
    elapsed_ms: number;
};
export type Profile = {
    employee: Employee;
    skill_catalog?: (CatalogSkill & { level: number | null })[];
    trajectory: {
        next_grade: string | null;
        coverage: number | null;
        status: 'ready' | 'missing_skills' | 'no_grade_rule' | 'highest_grade';
        critical_requirements_met: boolean | null;
        skills: {
            id: string;
            name: string;
            level: number | null;
            required: number;
            gap: number | null;
            critical: boolean;
        }[];
    };
    history: {
        id: string;
        event_id: string;
        title: string;
        status: string;
        occurred_at: string;
        changes: Candidate['changes'] | null;
    }[];
    available: Candidate[];
    recommendation: Recommendations | null;
};
export type Metrics = {
    employee_count: number;
    gaps: {
        id: string;
        name: string;
        affected: number;
        eligible: number;
        unknown: number;
        percent: number | null;
        total_gap: number;
    }[];
    no_step: {
        id: string;
        name: string;
        reason: string;
        reason_detail: string;
        blockers: Record<string, number>;
    }[];
    participation: {
        id: string;
        title: string;
        completed: number;
        missed: number;
        declined: number;
        no_show: number;
        dropped: number;
        in_progress: number;
        overdue: number;
    }[];
};
export type DemoAccount = {
    id: string;
    label: string;
    role: string;
};
export type ImportIssue = { source: string; path: string; reason: string };
export type ImportWarning = { code: string; count: number; reason: string };
export type ImportSummary = {
    employees_added: number;
    history_added: number;
    dry_run: boolean;
} & ({ schema: 'demo-v1' } | {
    schema: 'kit-v1';
    snapshot_date: string;
    skills_added: number;
    events_added: number;
    completed_after_review: number;
    demo_replaced: boolean;
    warnings: ImportWarning[];
});
export type CompletionResult = { profile: Profile; already_completed: boolean };
export type DemoAccounts = { enabled: boolean; accounts: DemoAccount[] };
export class ApiError extends Error {
    constructor(message: string, public status: number, public issues: ImportIssue[] = []) { super(message); this.name = 'ApiError'; }
}
function message(ru: string, en: string, kk: string) { return translate(getLocale(), ru, en, kk); }
function errorLabel(status: number) {
    const labels: Record<number, string> = {
        401: message('Сессия завершена. Войдите снова.', 'Your session has expired. Please sign in again.', 'Сессия аяқталды. Қайта кіріңіз.'),
        403: message('Нет доступа к этому действию. Проверьте роль и адрес приложения.', 'Access denied. Check your role and the application address.', 'Бұл әрекетке рұқсат жоқ. Рөліңізді және қолданба мекенжайын тексеріңіз.'),
        409: message('Данные изменились или запрос уже выполняется. Обновите данные.', 'Data has changed or a request is already running. Refresh your data.', 'Деректер өзгерді немесе сұрау орындалуда. Деректерді жаңартыңыз.'),
        413: message('Размер запроса превышает допустимые 5 МБ.', 'The request exceeds the 5 MB limit.', 'Сұрау өлшемі 5 МБ шегінен асты.'),
        415: message('Неподдерживаемый формат импорта. Выберите исходные файлы.', 'Unsupported import format. Select the original files.', 'Импорт пішімі қолдау таппайды. Бастапқы файлдарды таңдаңыз.'),
        422: message('Данные не прошли проверку. Проверьте выбранные файлы или обновите профиль.', 'Validation failed. Check your files or refresh the profile.', 'Деректер тексеруден өтпеді. Файлдарды тексеріңіз немесе профильді жаңартыңыз.'),
        429: message('Достигнут лимит запросов. Попробуйте позже.', 'Request limit reached. Try again later.', 'Сұрау шегіне жетті. Кейінірек қайталаңыз.'),
        503: message('Сервис временно недоступен. Попробуйте позже.', 'The service is temporarily unavailable. Try again later.', 'Сервис уақытша қолжетімсіз. Кейінірек қайталаңыз.'),
    };
    return labels[status] ?? message(`Ошибка ${status}`, `Error ${status}`, `${status} қатесі`);
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const abort = () => controller.abort();
    if (options.signal?.aborted)
        controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    try {
        const headers = new Headers(options.headers);
        headers.set('X-Requested-With', 'CareerQuest');
        headers.set('Accept-Language', getLocale());
        if (options.body instanceof FormData)
            headers.delete('Content-Type'); // The browser must generate the multipart boundary.
        else if (options.body != null && !headers.has('Content-Type'))
            headers.set('Content-Type', 'application/json');
        const response = await fetch(`/api/v1${path}`, {
            ...options,
            credentials: "same-origin",
            signal: controller.signal,
            headers,
        });
        const text = await response.text();
        let data;
        try {
            data = text ? JSON.parse(text) : null;
        }
        catch {
            throw new ApiError(response.ok ? message('Сервер вернул неожиданный ответ. Попробуйте обновить данные.', 'The server returned an unexpected response. Refresh your data.', 'Сервер күтпеген жауап берді. Деректерді жаңартыңыз.') : message(`Сервис временно недоступен (HTTP ${response.status}). Попробуйте ещё раз.`, `The service is temporarily unavailable (HTTP ${response.status}). Please try again.`, `Сервис уақытша қолжетімсіз (HTTP ${response.status}). Қайталап көріңіз.`), response.status);
        }
        if (!response.ok) {
            const detail = Array.isArray(data?.detail)
                ? data.detail
                    .map((x: {
                    loc: string[];
                    msg: string;
                }) => `${(x.loc ?? []).join(".")}: ${x.msg}`)
                    .join("; ")
                : data?.detail;
            const issues: ImportIssue[] = Array.isArray(data?.errors) ? data.errors.filter((item: ImportIssue) => item && typeof item.source === 'string' && typeof item.path === 'string' && typeof item.reason === 'string') : [];
            const explanation = issues.length ? issues.map(issue => `${issue.source} · ${issue.path}: ${issue.reason}`).join('; ') : typeof detail === 'string' ? detail : errorLabel(response.status);
            throw new ApiError(response.status === 401 && path !== '/auth/login' ? errorLabel(401) : explanation, response.status, issues);
        }
        return data as T;
    }
    catch (error) {
        if (error instanceof ApiError)
            throw error;
        if (controller.signal.aborted)
            throw new ApiError(message('Сервер не ответил за 15 секунд. Обновите данные перед повторной отправкой: действие могло сохраниться.', 'The server did not respond in 15 seconds. Refresh before sending again: the action may have been saved.', 'Сервер 15 секундта жауап бермеді. Қайта жібермес бұрын жаңартыңыз: әрекет сақталған болуы мүмкін.'), 408);
        throw new ApiError(message('Нет соединения с сервером. Проверьте сеть и повторите запрос.', 'Cannot connect to the server. Check your network and try again.', 'Сервермен байланыс жоқ. Желіні тексеріп, қайталаңыз.'), 0);
    }
    finally {
        clearTimeout(timeout);
        options.signal?.removeEventListener('abort', abort);
    }
}

export function importKit(files: readonly File[], dryRun: boolean, replaceDemo: boolean): Promise<ImportSummary> {
    const body = new FormData();
    for (const file of files) body.append('files', file, file.name);
    return api<ImportSummary>(`/imports/kit?dry_run=${dryRun}&replace_demo=${replaceDemo}`, { method: 'POST', body });
}

export function authenticate(mode: AuthMode, request: AuthRequest): Promise<Account> {
    const { username, password, role, display_name, invite_code } = request;
    const body = mode === 'setup' ? { username, password, display_name }
        : mode === 'register' ? { username, password, role, invite_code } : { username, password, role };
    return api<Account>(`/auth/${mode}`, { method: 'POST', body: JSON.stringify(body) });
}

export function completeEvent(employeeId: string, event: Candidate): Promise<CompletionResult> {
    return api<CompletionResult>(`/employees/${encodeURIComponent(employeeId)}/events/${encodeURIComponent(event.id)}/complete`, {
        method: 'POST',
        ...(event.occurrence_id != null ? { body: JSON.stringify({ occurrence_id: event.occurrence_id }) } : {}),
    });
}
