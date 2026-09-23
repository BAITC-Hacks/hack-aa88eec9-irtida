import type { Metrics, Profile, Recommendations } from './api';
import { translate, type Locale } from './i18n';
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
    workshop: 'Практикум', course: 'Курс', mentoring: 'Менторство', speaking_club: 'Клуб выступлений', speaking: 'Выступления',
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
export function formatDate(value: string, locale: Locale = 'ru') {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}
export function recommendationLabel(result: Recommendations, locale: Locale = 'ru') {
    const t = (ru: string, en: string, kk: string) => translate(locale, ru, en, kk);
    const label = result.mode === 'ai' ? t('AI-рекомендация', 'AI recommendation', 'AI ұсынысы') : result.mode === 'fallback' ? t('AI недоступен · подбор по правилам', 'AI unavailable · rule-based selection', 'AI қолжетімсіз · ережелер бойынша іріктеу') : result.mode === 'no_candidates' ? t('Нет подходящего шага', 'No eligible next step', 'Сәйкес келесі қадам жоқ') : t('Подбор по правилам', 'Rule-based selection', 'Ережелер бойынша іріктеу');
    return result.cached ? `${t('Сохранённый результат', 'Saved result', 'Сақталған нәтиже')} · ${label}` : label;
}
export function participationCounts(row: Metrics['participation'][number]) {
    // The API's legacy missed aggregate already includes every no_show.
    return { completed: row.completed, in_progress: row.in_progress, dropped: row.dropped,
        no_show: row.no_show, declined: row.declined, overdue: row.overdue,
        missed: row.missed - row.no_show };
}
export function milestones(profile: Profile, locale: Locale = 'ru') {
    const t = (ru: string, en: string, kk: string) => translate(locale, ru, en, kk);
    const completed = profile.history.filter(h => h.status === 'completed').length;
    const closed = profile.trajectory.skills.filter(s => s.gap === 0).length;
    return [
        { id: 'first', title: t('Первый шаг', 'First step', 'Алғашқы қадам'), description: t('Завершить одну активность', 'Complete one activity', 'Бір іс-шараны аяқтау'), earned: completed >= 1, progress: `${Math.min(completed, 1)} / 1` },
        { id: 'explorer', title: t('В своём ритме', 'At your own pace', 'Өз қарқыныңызбен'), description: t('Завершить три активности', 'Complete three activities', 'Үш іс-шараны аяқтау'), earned: completed >= 3, progress: `${Math.min(completed, 3)} / 3` },
        { id: 'skill', title: t('На уровне цели', 'Target reached', 'Мақсатқа жеттіңіз'), description: t('Достичь требования по одному навыку', 'Meet the target for one skill', 'Бір дағды бойынша талапқа жету'), earned: closed >= 1, progress: `${Math.min(closed, 1)} / 1` },
    ];
}

function labels(base: Record<string, string>, translations: Record<string, [string, string]>, locale: Locale) {
    return Object.fromEntries(Object.entries(base).map(([key, ru]) => [key, translate(locale, ru, translations[key][0], translations[key][1])]));
}
export function localizedLabels(locale: Locale) {
    return {
        statusLabels: labels(statusLabels, {
            completed: ['Completed', 'Аяқталды'], in_progress: ['In progress', 'Орындалуда'], dropped: ['Discontinued', 'Тоқтатылды'], no_show: ['Did not attend', 'Қатыспады'],
            declined: ['Declined', 'Қатысудан бас тартты'], overdue: ['Overdue', 'Мерзімі өтті'], missed: ['Missed', 'Өткізіп алды'],
        }, locale),
        reasonLabels: labels(reasonLabels, {
            no_grade_rule: ['Next-grade requirements are not defined', 'Келесі деңгей талаптары белгіленбеген'], missing_skills: ['Current skill levels need assessment', 'Қазіргі дағды деңгейлерін бағалау қажет'],
            no_eligible_activity: ['No suitable activity in the catalog yet', 'Каталогта сәйкес іс-шара әзірге жоқ'], highest_grade: ['Highest grade reached', 'Ең жоғары деңгейге жеттіңіз'],
        }, locale),
        typeLabels: labels(typeLabels, {
            workshop: ['Workshop', 'Практикум'], course: ['Course', 'Курс'], mentoring: ['Mentoring', 'Тәлімгерлік'], speaking_club: ['Speaking club', 'Шешендік клубы'], speaking: ['Public speaking', 'Көпшілік алдында сөйлеу'],
            training: ['Training', 'Оқу'], project: ['Project', 'Жоба'], assessment: ['Skill assessment', 'Дағдыларды бағалау'], webinar: ['Webinar', 'Вебинар'],
            certification: ['Certification', 'Сертификаттау'], meetup: ['Meetup', 'Кездесу'], compliance: ['Mandatory training', 'Міндетті оқу'], onboarding: ['Onboarding', 'Бейімделу'],
        }, locale),
        factorLabels: labels(factorLabels, {
            grade: ['Career target', 'Мансап мақсаты'], role_grade: ['Career target', 'Мансап мақсаты'], skill_gap: ['Skill gap', 'Дағдыдағы алшақтық'],
            skills: ['Skill gap', 'Дағдыдағы алшақтық'], gap: ['Skill gap', 'Дағдыдағы алшақтық'], history: ['Participation history', 'Қатысу тарихы'],
            next_grade: ['Next level', 'Келесі деңгей'], next_level: ['Next level', 'Келесі деңгей'], requirements: ['Target requirements', 'Мақсат талаптары'], benefit: ['Benefit for your target', 'Мақсатқа пайдасы'],
        }, locale),
    };
}
