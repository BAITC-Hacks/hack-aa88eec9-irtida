import type { CSSProperties } from 'react';
import { useI18n } from '../i18n';
export type IconName = 'route' | 'compass' | 'spark' | 'arrow' | 'check' | 'flag' | 'book' | 'award' | 'chart' | 'logout' | 'clock' | 'shield' | 'upload' | 'close' | 'users' | 'chevron' | 'refresh' | 'leaf';
const paths: Record<IconName, string> = {
    route: 'M5 19a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm14-10a2 2 0 1 0 0-4 2 2 0 0 0 0 4ZM5 15V9a4 4 0 0 1 4-4h2m8 4v6a4 4 0 0 1-4 4h-2M9 5l2-2m0 2L9 7',
    compass: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm5-15-3 7-7 3 3-7 7-3Z',
    spark: 'm12 2 2.7 7.3L22 12l-7.3 2.7L12 22l-2.7-7.3L2 12l7.3-2.7L12 2Z',
    arrow: 'M4 12h16m-6-6 6 6-6 6', check: 'm5 12 4 4L19 6',
    flag: 'M5 21V3m0 1c5-4 8 4 14 0v9c-6 4-9-4-14 0',
    book: 'M12 6c-4-3-8-2-10-1v15c3-2 7-2 10 0m0-14c4-3 8-2 10-1v15c-3-2-7-2-10 0V6Z',
    award: 'M12 14a6 6 0 1 0 0-12 6 6 0 0 0 0 12Zm-4-1-2 9 6-3 6 3-2-9',
    chart: 'M4 3v17h17M8 15v-4m5 4V7m5 8v-6', logout: 'M9 4H3v16h6m-1-8h13m-5-5 5 5-5 5',
    clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-16v6l4 2',
    shield: 'M12 2 3 6v6c0 6 9 10 9 10s9-4 9-10V6l-9-4Zm-5 9 3 3 6-6',
    upload: 'M12 16V3m-5 5 5-5 5 5M3 16v5h18v-5', close: 'm6 6 12 12M6 18 18 6',
    users: 'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm-7 9v-2a7 7 0 0 1 14 0v2m1-17a4 4 0 0 1 0 8m2 3a6 6 0 0 1 3 6',
    chevron: 'm9 5 7 7-7 7', refresh: 'M20 8a9 9 0 1 0 1 7M20 2v6h-6',
    leaf: 'M20 3C9 2 2 7 5 14s13 4 15-11ZM4 21 15 10',
};
export function Icon({ name, className = '', style }: {
    name: IconName;
    className?: string;
    style?: CSSProperties;
}) {
    return <svg className={`icon ${className}`} style={style} width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]}/></svg>;
}
export function Brand() {
    const { t } = useI18n();
    return <span className="brand"><span className="brand-mark"><Icon name="route"/></span><span>career<span className="brand-light">quest</span><small>{t('РАСТИ В СВОЁМ РИТМЕ', 'GROW AT YOUR OWN PACE', 'ӨЗ ҚАРҚЫНЫҢМЕН ӨС')}</small></span></span>;
}
