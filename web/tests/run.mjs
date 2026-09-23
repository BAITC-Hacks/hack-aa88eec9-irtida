// Node's built-in runner: no network, browser dependency, or API credits.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import ts from 'typescript';
const root = resolve('.test-build');
mkdirSync(root, { recursive: true });
const target = mkdtempSync(join(root, 'run-'));
try {
  mkdirSync(join(target, 'components'));
  for (const name of ['api.ts', 'view-model.ts', 'import-state.ts', 'components/Icons.tsx', 'components/ProfileView.tsx', 'components/HrView.tsx', 'components/ImportPanel.tsx']) {
    const result = ts.transpileModule(readFileSync(`src/${name}`, 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } });
    const output = result.outputText.replace(/(from\s+['"])(\.\.?\/[^'"]+)(['"])/g, '$1$2.mjs$3');
    writeFileSync(join(target, name.replace(/\.tsx?$/, '.mjs')), output);
  }
  const result = spawnSync(process.execPath, ['--test', 'tests/core.test.mjs', 'tests/views.test.mjs'], { stdio: 'inherit', env: { ...process.env, CQ_TEST_BUILD: target } });
  process.exitCode = result.status ?? 1;
} finally { rmSync(target, { recursive: true, force: true }); }
