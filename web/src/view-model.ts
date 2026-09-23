import type { Candidate, Profile, Recommendations } from './api';
export const statusLabels: Record<string, string> = { completed: 'Завершено', missed: 'Пропущено', declined: 'Отказ от участия' };
export const reasonLabels: Record<string, string> = {
    no_grade_rule: 'HR ещё не задал требования следующего грейда',
    missing_skills: 'Нужно уточнить текущий уровень навыков',
    no_eligible_activity: 'В каталоге пока нет подходящей активности',
};
export const typeLabels: Record<string, string> = {
    workshop: 'Практикум', course: 'Курс', mentoring: 'Менторство', speaking_club: 'Клуб выступлений',
    training: 'Обучение', project: 'Проект', assessment: 'Оценка навыков', webinar: 'Вебинар',
};
export const factorLabels: Record<string, string> = {
    grade: 'Карьерная цель', role_grade: 'Карьерная цель', skill_gap: 'Разрыв по навыкам',
    skills: 'Разрыв по навыкам', gap: 'Разрыв по навыкам', history: 'История участия',
    next_grade: 'Следующий уровень', requirements: 'Требования цели', benefit: 'Польза для цели',
};
export function percent(value: number | null | undefined) {
    return value == null || !Number.isFinite(value) ? null : Math.round(Math.max(0, Math.min(100, value)));
}
export function initials(name: string) {
    return name.trim().split(/\s+/).slice(0, 2).map(x => x[0]).join('').toUpperCase();
}
export function formatDate(value: string) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('ru', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}
export function recommendationLabel(result: Recommendations) {
    const label = result.mode === 'ai' ? 'AI-рекомендация' : result.mode === 'fallback' ? 'AI недоступен · подбор по правилам' : result.mode === 'no_candidates' ? 'Нет подходящего шага' : 'Подбор по правилам';
    return result.cached ? `Сохранённый результат · ${label}` : label;
}
// Preview only. Never changes server data or assumes an unknown skill is zero.
export function projectedCoverage(profile: Profile, candidate: Candidate): number | null {
    const skills = profile.trajectory.skills;
    if (!skills.length || skills.some(s => s.level === null) || profile.trajectory.coverage === null)
        return null;
    const required = skills.reduce((n, s) => n + s.required, 0);
    if (required <= 0)
        return null;
    return percent(100 * skills.reduce((n, s) => n + Math.min(s.required, candidate.changes[s.id]?.after ?? s.level!), 0) / required);
}
export function milestones(profile: Profile) {
    const completed = profile.history.filter(h => h.status === 'completed').length;
    const closed = profile.trajectory.skills.filter(s => s.gap === 0).length;
    return [
        { id: 'first', title: 'Первый шаг', description: 'Завершить одну активность', earned: completed >= 1, progress: `${Math.min(completed, 1)} / 1` },
        { id: 'explorer', title: 'В своём ритме', description: 'Завершить три активности', earned: completed >= 3, progress: `${Math.min(completed, 3)} / 3` },
        { id: 'skill', title: 'На уровне цели', description: 'Достичь требования по одному навыку', earned: closed >= 1, progress: `${Math.min(closed, 1)} / 1` },
    ];
}
