import { useReducer } from 'react';
import { api, importKit, type ImportSummary } from '../api';
import { importReducer, initialImportState } from '../import-state';
import { Icon } from './Icons';
import { useI18n } from '../i18n';

export function ImportPanel({ busy, run, onImported }: {
    busy: string;
    run: (label: string, action: () => Promise<void>) => Promise<boolean>;
    onImported: () => Promise<void>;
}) {
    const { t } = useI18n();
    const [state, dispatch] = useReducer(importReducer, initialImportState);
    const { mode, files, replaceDemo, approved, summary, imported } = state;
    async function validate() {
        await run('import-check', async () => {
            dispatch({ type: 'reset-check' });
            if (!files.length) throw new Error(t("Сначала выберите файлы.", "Select files first.", "Алдымен файлдарды таңдаңыз."));
            if (files.reduce((size, file) => size + file.size, 0) >= 5_000_000)
                throw new Error(t("Размер файлов должен быть меньше 5 МБ с учётом служебных данных запроса.", "Files must total less than 5 MB including request overhead.", "Сұраудың қызметтік деректерін қоса алғанда, файлдар 5 МБ-тан кіші болуы керек."));
            let body: string | null = null;
            let result: ImportSummary;
            if (mode === 'kit') {
                const names = files.map(file => file.name);
                if (files.length > 4 || new Set(names).size !== names.length || names.some(name => !['employees.json', 'skills.json', 'events.json', 'activity_history.csv'].includes(name)))
                    throw new Error(t("Выберите до четырёх исходных файлов: employees.json, skills.json, events.json, activity_history.csv, без повторов.", "Select up to four original files: employees.json, skills.json, events.json, activity_history.csv, without duplicates.", "Төрт бастапқы файлға дейін таңдаңыз: employees.json, skills.json, events.json, activity_history.csv. Қайталанбауы керек."));
                result = await importKit(files, true, replaceDemo);
            } else {
                body = await files[0].text();
                try { JSON.parse(body); }
                catch { throw new Error(t("Файл содержит некорректный JSON. Проверьте скобки и запятые. Данные не загружены.", "Invalid JSON. Check brackets and commas. No data was imported.", "JSON жарамсыз. Жақшалар мен үтірлерді тексеріңіз. Деректер жүктелмеді.")); }
                result = await api<ImportSummary>('/imports?dry_run=true', { method: 'POST', body });
            }
            dispatch({ type: 'checked', summary: result, body });
        });
    }
    async function submit() {
        if (!approved) return;
        const success = await run('import-save', async () => {
            // Revoke approval even after a failed/ambiguous POST; a new dry-run is required.
            dispatch({ type: 'reset-check' });
            const result = mode === 'kit'
                ? await importKit(files, false, replaceDemo)
                : await api<ImportSummary>('/imports?dry_run=false', { method: 'POST', body: state.checkedBody });
            dispatch({ type: 'saved', summary: result });
        });
        if (success) await run('refresh', onImported);
    }
    return <section className="panel import-panel section-space">
        <div><span className="eyebrow">{t("ДОБАВИТЬ ДАННЫЕ", "ADD DATA", "ДЕРЕКТЕРДІ ҚОСУ")}</span><h2>{t("Новые профили и история", "New profiles and history", "Жаңа профильдер мен тарих")}</h2><p className="muted">{t("Сначала проверим файлы без изменений в базе. После успешной проверки вы сможете подтвердить загрузку.", "First validate the files without changing the database. Then confirm the import.", "Алдымен файлдар базаға өзгеріссіз тексеріледі. Сәтті тексеруден кейін импортты растаңыз.")}</p>
            <label className="import-format">{t("Формат данных", "Data format", "Деректер пішімі")}<select aria-label={t("Формат импорта", "Import format", "Импорт пішімі")} value={mode} disabled={!!busy} onChange={e => dispatch({ type: 'mode', mode: e.target.value === 'kit' ? 'kit' : 'demo' })}><option value="kit">{t("Официальный Career Quest Kit", "Official Career Quest Kit", "Ресми Career Quest Kit")}</option><option value="demo">{t("Демонстрационный JSON (demo-v1)", "Demo JSON (demo-v1)", "Демо JSON (demo-v1)")}</option></select></label>
            <p className="small muted">{mode === 'kit' ? t("Первый импорт: skills.json, employees.json, events.json и activity_history.csv. Для дополнений достаточно профилей и/или истории. Лимит запроса — 5 МБ.", "First import: skills.json, employees.json, events.json and activity_history.csv. Additions need only profiles and/or history. Request limit: 5 MB.", "Алғашқы импорт: skills.json, employees.json, events.json және activity_history.csv. Толықтыруға профильдер және/немесе тарих жеткілікті. Сұрау шегі — 5 МБ.") : t("Один JSON-файл demo-v1, до 5 МБ. Для базы официального кита используйте формат Career Quest Kit.", "One demo-v1 JSON file, up to 5 MB. Use Career Quest Kit format for an official-kit database.", "Бір demo-v1 JSON файлы, 5 МБ-қа дейін. Ресми кит базасы үшін Career Quest Kit пішімін пайдаланыңыз.")}</p>
            {mode === 'kit' && <label className="replace-demo"><input type="checkbox" checked={replaceDemo} disabled={!!busy} onChange={e => dispatch({ type: 'replace', value: e.target.checked })}/><span>{t("Заменить исходные демо-данные официальным китом", "Replace starter demo data with the official kit", "Бастапқы демо деректерін ресми китпен ауыстыру")}<small>{t("Только для нетронутого начального демо, нужны все четыре файла. Уже сохранённый прогресс сервер не удалит.", "Only for an unchanged starter demo, with all four files. Existing progress is protected.", "Тек өзгертілмеген бастапқы демо үшін, төрт файл да қажет. Сақталған ілгерілеу қорғалады.")}</small></span></label>}
        </div>
        <div className="import-controls"><label className="file-input"><Icon name="upload"/><span>{files.length ? files.map(file => file.name).join(', ') : mode === 'kit' ? t("Выберите файлы кита", "Select kit files", "Кит файлдарын таңдаңыз") : t("Выберите JSON-файл", "Select a JSON file", "JSON файлын таңдаңыз")}</span><input key={mode} aria-label={mode === 'kit' ? t("Файлы официального кита", "Official kit files", "Ресми кит файлдары") : t("Файл с профилями и историей", "Profiles and history file", "Профильдер мен тарих файлы")} type="file" multiple={mode === 'kit'} accept={mode === 'kit' ? '.json,.csv,application/json,text/csv' : '.json,application/json'} disabled={!!busy} onChange={e => dispatch({ type: 'files', files: Array.from(e.target.files ?? []) })}/></label>
            <div className="import-actions"><button className="secondary" disabled={!files.length || !!busy} onClick={() => void validate()}>{busy === 'import-check' ? t("Проверяем…", "Validating…", "Тексерілуде…") : t("1. Проверить файлы", "1. Validate files", "1. Файлдарды тексеру")}</button><button className="primary" disabled={!approved || !!busy || imported} onClick={() => void submit()}>{busy === 'import-save' ? t("Загружаем…", "Importing…", "Жүктелуде…") : t("2. Загрузить данные", "2. Import data", "2. Деректерді жүктеу")}</button></div>
            {summary && <div className={`import-result ${imported ? 'saved' : ''}`} role="status"><strong>{imported ? t("✓ Данные загружены", "✓ Data imported", "✓ Деректер жүктелді") : t("✓ Проверка пройдена · база не изменена", "✓ Validation passed · database unchanged", "✓ Тексеру сәтті · база өзгермеді")}</strong><span>{imported ? t("Добавлено", "Added", "Қосылды") : t("Будет добавлено", "To be added", "Қосылады")} · {t('Профилей:', 'Profiles:', 'Профильдер:')} {summary.employees_added}, {t('истории:', 'history:', 'тарих:')} {summary.history_added}.</span>
                {summary.schema === 'kit-v1' && <><span>{t('Навыков:', 'Skills:', 'Дағдылар:')} {summary.skills_added}, {t('активностей:', 'activities:', 'іс-шаралар:')} {summary.events_added}.</span><span>{t('Завершений после оценки навыков во всём наборе:', 'Completions after skill review in the whole dataset:', 'Барлық деректегі дағдыны бағалаудан кейінгі аяқтаулар:')} {summary.completed_after_review}. {t('Срез:', 'Snapshot:', 'Дерек күні:')} {summary.snapshot_date}.</span>{summary.demo_replaced && <span>{t("Исходные демо-данные заменены.", "Starter demo data replaced.", "Бастапқы демо деректері ауыстырылды.")}</span>}{summary.warnings.length > 0 && <div className="import-warnings"><strong>{t("Предупреждения", "Warnings", "Ескертулер")}</strong><ul>{summary.warnings.map(warning => <li key={warning.code}><code>{warning.code}</code> — {warning.count}<p>{warning.code === 'mandatory_history_repeated_after_completion' ? t('В исходной истории повторяются обязательные мероприятия после завершения. Записи сохранены без повторного прироста навыков.', 'Source history repeats mandatory activities after completion. Records are preserved without awarding skill gains again.', 'Бастапқы тарихта аяқталған міндетті іс-шаралар қайталанады. Жазбалар сақталды, дағды өсімі қайта есептелмейді.') : warning.reason}</p></li>)}</ul></div>}</>}
            </div>}
        </div>
    </section>;
}
