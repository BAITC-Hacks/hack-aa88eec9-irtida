import type { Metrics, Profile, Recommendations } from './api';
export const statusLabels: Record<string, string> = {
    completed: 'Завершено', in_progress: 'В процессе', dropped: 'Прекращено', no_show: 'Неявка',
    declined: 'Отказ от участия', overdue: 'Просрочено', missed: 'Пропущено',
};
export const reasonLabels: Record<string, string> = {
    no_grade_rule: 'HR ещё не задал требования следующего грейда',
    missing_skills: 'Нужно уточнить текущий уровень навыков',
    no_eligible_activity: 'В каталоге пока нет подходящей активности',
    highest_grade: 'Достигнут максимальный грейд',
};
export const typeLabels: Record<string, string> = {
    workshop: 'Практикум', course: 'Курс', mentoring: 'Менторство', speaking_club: 'Клуб выступлений',
    training: 'Обучение', project: 'Проект', assessment: 'Оценка навыков', webinar: 'Вебинар',
    certification: 'Сертификация', meetup: 'Встреча', compliance: 'Обязательное обучение', onboarding: 'Онбординг',
};
export const factorLabels: Record<string, string> = {
    grade: 'Карьерная цель', role_grade: 'Карьерная цель', skill_gap: 'Разрыв по навыкам',
    skills: 'Разрыв по навыкам', gap: 'Разрыв по навыкам', history: 'История участия',
    next_grade: 'Следующий уровень', next_level: 'Следующий уровень', requirements: 'Требования цели', benefit: 'Польза для цели',
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
export function participationCounts(row: Metrics['participation'][number]) {
    // The API's legacy missed aggregate already includes every no_show.
    return { completed: row.completed, in_progress: row.in_progress, dropped: row.dropped,
        no_show: row.no_show, declined: row.declined, overdue: row.overdue,
        missed: row.missed - row.no_show };
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
