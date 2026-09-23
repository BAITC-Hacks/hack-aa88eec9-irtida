import type { ImportSummary } from './api';

export type ImportMode = 'kit' | 'demo';
export type ImportState = {
    mode: ImportMode;
    files: File[];
    replaceDemo: boolean;
    approved: boolean;
    checkedBody: string | null;
    summary: ImportSummary | null;
    imported: boolean;
};
export const initialImportState: ImportState = {
    mode: 'kit', files: [], replaceDemo: false, approved: false, checkedBody: null, summary: null, imported: false,
};
type Action = { type: 'files'; files: File[] } | { type: 'mode'; mode: ImportMode }
    | { type: 'replace'; value: boolean } | { type: 'reset-check' }
    | { type: 'checked'; summary: ImportSummary; body: string | null }
    | { type: 'saved'; summary: ImportSummary };
export function importReducer(state: ImportState, action: Action): ImportState {
    const unchecked = { ...state, approved: false, checkedBody: null, summary: null, imported: false };
    switch (action.type) {
        case 'files': return { ...unchecked, files: action.files };
        case 'mode': return { ...unchecked, mode: action.mode, files: [], replaceDemo: false };
        case 'replace': return { ...unchecked, replaceDemo: action.value };
        case 'reset-check': return unchecked;
        case 'checked': return { ...state, summary: action.summary, approved: action.summary.dry_run, checkedBody: action.body, imported: false };
        case 'saved': return { ...state, summary: action.summary, approved: false, checkedBody: null, imported: true,
            replaceDemo: action.summary.schema === 'kit-v1' && action.summary.demo_replaced ? false : state.replaceDemo };
    }
}
