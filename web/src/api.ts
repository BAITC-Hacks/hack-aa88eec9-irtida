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
};
export type Candidate = {
    id: string;
    title: string;
    type: string;
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
        status: string;
        skills: {
            id: string;
            name: string;
            level: number | null;
            required: number;
            gap: number | null;
        }[];
    };
    history: {
        id: string;
        title: string;
        status: string;
        occurred_at: string;
    }[];
    available: Candidate[];
    recommendation?: Recommendations | null;
};
export type Metrics = {
    employee_count: number;
    gaps: {
        name: string;
        affected: number;
        eligible: number;
        unknown: number;
        percent: number | null;
    }[];
    no_step: {
        id: string;
        name: string;
        reason: string;
    }[];
    participation: {
        id: string;
        title: string;
        completed: number;
        missed: number;
        declined: number;
    }[];
};
export type DemoAccount = {
    id: string;
    label: string;
    role: string;
};
export type ImportSummary = {
    employees_added: number;
    history_added: number;
    [key: string]: unknown;
};
export class ApiError extends Error {
    constructor(message: string, public status: number) { super(message); this.name = 'ApiError'; }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    const abort = () => controller.abort();
    if (options.signal?.aborted)
        controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    try {
        const response = await fetch(`/api/v1${path}`, {
            ...options,
            credentials: "same-origin",
            signal: controller.signal,
            headers: {
                "Content-Type": "application/json",
                "X-Requested-With": "CareerQuest",
                ...options.headers,
            },
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
            throw new ApiError(response.status === 401 ? 'Сессия завершена. Войдите снова.' : typeof detail === 'string' ? detail : `Ошибка ${response.status}`, response.status);
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
