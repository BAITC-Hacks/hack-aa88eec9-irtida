export type Account = { role: "employee" | "hr"; employee_id: string | null };
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
  changes: Record<
    string,
    { name: string; before: number; after: number; gain: number }
  >;
  evidence: { factor: string; text: string }[];
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
  history: { id: string; title: string; status: string; occurred_at: string }[];
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
  no_step: { id: string; name: string; reason: string }[];
  participation: {
    id: string;
    title: string;
    completed: number;
    missed: number;
    declined: number;
  }[];
};

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      "X-Requested-With": "CareerQuest",
      ...options.headers,
    },
  });
  const data = await response.json();
  if (!response.ok) {
    const detail = Array.isArray(data.detail)
      ? data.detail
          .map(
            (x: { loc: string[]; msg: string }) =>
              `${x.loc.join(".")}: ${x.msg}`,
          )
          .join("; ")
      : data.detail;
    throw new Error(detail || `Ошибка ${response.status}`);
  }
  return data as T;
}
