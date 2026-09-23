import { useReducer } from 'react';
import { api, importKit, type ImportSummary } from '../api';
import { importReducer, initialImportState } from '../import-state';
import { Icon } from './Icons';

export function ImportPanel({ busy, run, onImported }: {
    busy: string;
    run: (label: string, action: () => Promise<void>) => Promise<boolean>;
    onImported: () => Promise<void>;
}) {
    const [state, dispatch] = useReducer(importReducer, initialImportState);
    const { mode, files, replaceDemo, approved, summary, imported } = state;
    async function validate() {
        await run('import-check', async () => {
            dispatch({ type: 'reset-check' });
            if (!files.length) throw new Error('Сначала выберите файлы.');
            if (files.reduce((size, file) => size + file.size, 0) >= 5_000_000)
                throw new Error('Размер файлов должен быть меньше 5 МБ с учётом служебных данных запроса.');
            let body: string | null = null;
            let result: ImportSummary;
            if (mode === 'kit') {
                const names = files.map(file => file.name);
                if (files.length > 4 || new Set(names).size !== names.length || names.some(name => !['employees.json', 'skills.json', 'events.json', 'activity_history.csv'].includes(name)))
                    throw new Error('Выберите до четырёх исходных файлов: employees.json, skills.json, events.json, activity_history.csv, без повторов.');
                result = await importKit(files, true, replaceDemo);
            } else {
                body = await files[0].text();
                try { JSON.parse(body); }
                catch { throw new Error('Файл содержит некорректный JSON. Проверьте скобки и запятые. Данные не загружены.'); }
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
        <div><span className="eyebrow">ДОБАВИТЬ ДАННЫЕ</span><h2>Новые профили и история</h2><p className="muted">Сначала проверим файлы без изменений в базе. После успешной проверки вы сможете подтвердить загрузку.</p>
            <label className="import-format">Формат данных<select aria-label="Формат импорта" value={mode} disabled={!!busy} onChange={e => dispatch({ type: 'mode', mode: e.target.value === 'kit' ? 'kit' : 'demo' })}><option value="kit">Официальный Career Quest Kit</option><option value="demo">Демонстрационный JSON (demo-v1)</option></select></label>
            <p className="small muted">{mode === 'kit' ? 'Первый импорт: skills.json, employees.json, events.json и activity_history.csv. Для дополнений достаточно профилей и/или истории. Лимит запроса — 5 МБ.' : 'Один JSON-файл demo-v1, до 5 МБ. Для базы официального кита используйте формат Career Quest Kit.'}</p>
            {mode === 'kit' && <label className="replace-demo"><input type="checkbox" checked={replaceDemo} disabled={!!busy} onChange={e => dispatch({ type: 'replace', value: e.target.checked })}/><span>Заменить исходные демо-данные официальным китом<small>Только для нетронутого начального демо, нужны все четыре файла. Уже сохранённый прогресс сервер не удалит.</small></span></label>}
        </div>
        <div className="import-controls"><label className="file-input"><Icon name="upload"/><span>{files.length ? files.map(file => file.name).join(', ') : mode === 'kit' ? 'Выберите файлы кита' : 'Выберите JSON-файл'}</span><input key={mode} aria-label={mode === 'kit' ? 'Файлы официального кита' : 'Файл с профилями и историей'} type="file" multiple={mode === 'kit'} accept={mode === 'kit' ? '.json,.csv,application/json,text/csv' : '.json,application/json'} disabled={!!busy} onChange={e => dispatch({ type: 'files', files: Array.from(e.target.files ?? []) })}/></label>
            <div className="import-actions"><button className="secondary" disabled={!files.length || !!busy} onClick={() => void validate()}>{busy === 'import-check' ? 'Проверяем…' : '1. Проверить файлы'}</button><button className="primary" disabled={!approved || !!busy || imported} onClick={() => void submit()}>{busy === 'import-save' ? 'Загружаем…' : '2. Загрузить данные'}</button></div>
            {summary && <div className={`import-result ${imported ? 'saved' : ''}`} role="status"><strong>{imported ? '✓ Данные загружены' : '✓ Проверка пройдена · база не изменена'}</strong><span>{imported ? 'Добавлено' : 'Будет добавлено'} профилей: {summary.employees_added}, записей истории: {summary.history_added}.</span>
                {summary.schema === 'kit-v1' && <><span>Навыков: {summary.skills_added}, активностей: {summary.events_added}.</span><span>Завершений после оценки навыков во всём наборе: {summary.completed_after_review}. Срез: {summary.snapshot_date}.</span>{summary.demo_replaced && <span>Исходные демо-данные заменены.</span>}{summary.warnings.length > 0 && <div className="import-warnings"><strong>Предупреждения</strong><ul>{summary.warnings.map(warning => <li key={warning.code}><code>{warning.code}</code> — {warning.count}<p>{warning.reason}</p></li>)}</ul></div>}</>}
            </div>}
        </div>
    </section>;
}
