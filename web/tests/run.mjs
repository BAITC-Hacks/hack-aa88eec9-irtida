// Node's built-in runner: no network, browser dependency, or API credits.
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { spawnSync } from 'node:child_process';
import ts from 'typescript';
const root = resolve('.test-build');
mkdirSync(root, { recursive: true });
const target = mkdtempSync(join(root, 'run-'));
try {
  for (const name of ['api', 'view-model']) {
    const result = ts.transpileModule(readFileSync(`src/${name}.ts`, 'utf8'), { compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 } });
    writeFileSync(join(target, `${name}.mjs`), result.outputText);
  }
  const result = spawnSync(process.execPath, ['--test', 'tests/core.test.mjs'], { stdio: 'inherit', env: { ...process.env, CQ_TEST_BUILD: target } });
  process.exitCode = result.status ?? 1;
} finally { rmSync(target, { recursive: true, force: true }); }
