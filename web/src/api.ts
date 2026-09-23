export type Account = {
    role: "employee" | "hr";
    employee_id: string | null;
};
export type Employee = {
    id: string;
    name: string;
    role: string;
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
const errorLabels: Record<number, string> = {
    401: 'Сессия завершена. Войдите снова.',
    403: 'Нет доступа к этому действию. Проверьте роль и адрес приложения.',
    409: 'Данные изменились или запрос уже выполняется. Обновите данные.',
    413: 'Размер запроса превышает допустимые 5 МБ.',
    415: 'Неподдерживаемый формат импорта. Выберите исходные файлы.',
    422: 'Данные не прошли проверку. Проверьте выбранные файлы или обновите профиль.',
    429: 'Достигнут лимит запросов. Попробуйте позже.',
    503: 'Сервис временно недоступен. Попробуйте позже.',
};
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
            throw new ApiError(response.ok ? 'Сервер вернул неожиданный ответ. Попробуйте обновить данные.' : `Сервис временно недоступен (HTTP ${response.status}). Попробуйте ещё раз.`, response.status);
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
            const message = issues.length ? issues.map(issue => `${issue.source} · ${issue.path}: ${issue.reason}`).join('; ') : typeof detail === 'string' ? detail : errorLabels[response.status] ?? `Ошибка ${response.status}`;
            throw new ApiError(response.status === 401 ? errorLabels[401] : message, response.status, issues);
        }
        return data as T;
    }
    catch (error) {
        if (error instanceof ApiError)
            throw error;
        if (controller.signal.aborted)
            throw new ApiError('Сервер не ответил за 15 секунд. Обновите данные перед повторной отправкой: действие могло сохраниться.', 408);
        throw new ApiError('Нет соединения с сервером. Проверьте сеть и повторите запрос.', 0);
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

export function completeEvent(employeeId: string, event: Candidate): Promise<CompletionResult> {
    return api<CompletionResult>(`/employees/${encodeURIComponent(employeeId)}/events/${encodeURIComponent(event.id)}/complete`, {
        method: 'POST',
        ...(event.occurrence_id != null ? { body: JSON.stringify({ occurrence_id: event.occurrence_id }) } : {}),
    });
}
