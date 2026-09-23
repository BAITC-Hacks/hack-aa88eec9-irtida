import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type Locale = 'ru' | 'en' | 'kk';
export type Translate = (ru: string, en: string, kk: string) => string;
const storageKey = 'cq_locale';
let activeLocale: Locale | undefined;
export function isLocale(value: unknown): value is Locale { return value === 'ru' || value === 'en' || value === 'kk'; }
export function translate(locale: Locale, ru: string, en: string, kk: string): string {
    return locale === 'en' ? en : locale === 'kk' ? kk : ru;
}
export function getLocale(): Locale {
    if (activeLocale) return activeLocale;
    try {
        const saved = typeof window !== 'undefined' ? window.localStorage.getItem(storageKey) : null;
        return isLocale(saved) ? saved : 'ru';
    } catch { return 'ru'; }
}
type I18n = { locale: Locale; setLocale: (locale: Locale) => void; t: Translate };
const I18nContext = createContext<I18n>({ locale: 'ru', setLocale: () => {}, t: (ru) => ru });
export function I18nProvider({ children, initialLocale }: { children: ReactNode; initialLocale?: Locale }) {
    const [locale, updateLocale] = useState<Locale>(() => initialLocale ?? getLocale());
    useEffect(() => {
        activeLocale = locale;
        document.documentElement.lang = locale;
        try { window.localStorage.setItem(storageKey, locale); } catch { /* Storage can be disabled. */ }
    }, [locale]);
    const value = useMemo<I18n>(() => ({ locale, setLocale(next) {
        if (!isLocale(next)) return;
        activeLocale = next;
        updateLocale(next);
    }, t: (ru, en, kk) => translate(locale, ru, en, kk) }), [locale]);
    return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}
export function useI18n() { return useContext(I18nContext); }
