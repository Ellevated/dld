/**
 * Graph context hook (PreToolUse: Edit|Write|MultiEdit).
 *
 * Injects the blast radius of the file being edited — who imports it, who calls
 * its functions, which tests reach it — into the model's context BEFORE the
 * edit runs.
 *
 * Why a hook and not an instruction: a tool the agent *may* call is not called.
 * Measured here — 0 calls of mcp__codebase-memory__* across 143 autopilot runs
 * with the server connected and both planner.md and coder.md asking for it
 * (EXP-002). Injection is the only rung of the ladder that beats training
 * priors; see ai/experiments/2026-09-07-graph-injection-hook.md.
 *
 * Source of truth is the codebase-memory index (SQLite, read-only). No MCP
 * round-trip and no daemon: ~80 ms on this repo's 24k-node graph.
 *
 * Fail-open and fail-quiet by design (ADR-004): no index, no matching nodes,
 * unreadable DB, unknown project — exit 0 with no output, the edit proceeds.
 * Disable with DLD_GRAPH_HOOK=0.
 */

import { existsSync, statSync, mkdirSync, readFileSync, writeFileSync } from 'fs';
import { homedir, tmpdir } from 'os';
import { join } from 'path';
import { execFileSync } from 'child_process';
import { debugLog, debugTiming, getToolInput, logHookError, readHookInput } from './utils.mjs';

const CODE_EXTENSIONS = new Set([
  '.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx', '.go', '.rs', '.rb',
  '.java', '.kt', '.php', '.cs', '.swift', '.sh', '.bash', '.sql', '.vue', '.svelte',
]);

const CALL_EDGE_TYPES = ['CALLS', 'USAGE', 'HTTP_CALLS'];
const MAX_CHARS = 1400;
const STALE_DAYS = 7;

// Tests dominate the raw call counts (95 of them reach lifecycle.read_lifecycle
// here, mostly from test files). Keeping them in the caller list would push the
// production call sites — the ones that break — out of the budget, so they are
// counted separately instead.
const TEST_PATH_PATTERNS = [
  /(^|\/)tests?\//, /(^|\/)__tests__\//, /(^|\/)test_[^/]+$/,
  /_test\.[a-z]+$/, /\.test\.[a-z]+$/, /\.spec\.[a-z]+$/,
];

export function isTestPath(p) {
  return TEST_PATH_PATTERNS.some((re) => re.test(p));
}

function git(args) {
  return execFileSync('git', args, {
    encoding: 'utf-8', timeout: 3000, stdio: ['pipe', 'pipe', 'pipe'],
  });
}

/**
 * Two different roots, and mixing them yields an empty result every time.
 *
 * `main` — the canonical checkout the index is keyed by; an autopilot worktree
 * has no graph of its own, its blast radius lives in the main repo's DB.
 * `current` — the worktree the edited file actually sits in, which is what the
 * file path must be made relative to.
 */
function repoRoots() {
  let main;
  let current;
  try {
    main = git(['worktree', 'list', '--porcelain']).split('\n')[0].replace('worktree ', '').trim();
  } catch { /* not a repo, or git missing */ }
  try {
    current = git(['rev-parse', '--show-toplevel']).trim();
  } catch { /* same */ }
  return { main: main || current || process.cwd(), current: current || main || process.cwd() };
}

/** `/home/dld/projects/dld` -> `home-dld-projects-dld`; `D:\dev\dld` -> `D-dev-dld`. */
export function projectKeyFromRoot(root) {
  return root.replace(/:/g, '').replace(/[\\/]+/g, '-').replace(/^-+|-+$/g, '');
}

export function dbPathFor(root) {
  const cacheDir = process.env.CBM_CACHE_DIR || join(homedir(), '.cache', 'codebase-memory-mcp');
  const p = join(cacheDir, `${projectKeyFromRoot(root)}.db`);
  return existsSync(p) ? p : null;
}

export function relativeTo(root, filePath) {
  const norm = (s) => s.replace(/\\/g, '/').replace(/\/+$/, '');
  const r = norm(root);
  const f = norm(filePath);
  if (f.startsWith(`${r}/`)) return f.slice(r.length + 1);
  return f.replace(/^\.\//, '');
}

/** One line per callee: `write_lifecycle <- 10 вызовов · файлов: 4 — a.py, b.py ...` */
export function formatCallers(rows) {
  const byTarget = new Map();
  for (const r of rows) {
    if (isTestPath(r.caller_file)) continue;
    if (!byTarget.has(r.target)) byTarget.set(r.target, { places: 0, files: new Set() });
    const entry = byTarget.get(r.target);
    entry.places += 1;
    entry.files.add(r.caller_file);
  }
  return [...byTarget.entries()]
    .sort((a, b) => b[1].places - a[1].places)
    .slice(0, 6)
    .map(([target, e]) => {
      const files = [...e.files];
      const shown = files.slice(0, 3).join(', ');
      const rest = files.length > 3 ? ` +${files.length - 3}` : '';
      return `  ${target} <- вызовов: ${e.places} · файлов: ${files.length} — ${shown}${rest}`;
    });
}

function collect(db, relPath) {
  const callers = db.prepare(`
    SELECT tgt.name AS target, src.file_path AS caller_file
    FROM nodes tgt
    JOIN edges e ON e.target_id = tgt.id
    JOIN nodes src ON src.id = e.source_id
    WHERE tgt.file_path = ?
      AND tgt.label IN ('Function','Method','Class')
      AND e.type IN (${CALL_EDGE_TYPES.map(() => '?').join(',')})
      AND src.file_path <> ?
      AND src.file_path <> ''
    LIMIT 600
  `).all(relPath, ...CALL_EDGE_TYPES, relPath);

  const importers = db.prepare(`
    SELECT DISTINCT src.file_path AS caller_file
    FROM nodes tgt
    JOIN edges e ON e.target_id = tgt.id
    JOIN nodes src ON src.id = e.source_id
    WHERE tgt.file_path = ?
      AND e.type IN ('IMPORTS', 'DEPENDS_ON')
      AND src.file_path <> ?
      AND src.file_path <> ''
    LIMIT 60
  `).all(relPath, relPath);

  const tests = db.prepare(`
    SELECT DISTINCT src.file_path AS test_file
    FROM nodes tgt
    JOIN edges e ON e.target_id = tgt.id
    JOIN nodes src ON src.id = e.source_id
    WHERE tgt.file_path = ?
      AND e.type = 'TESTS'
      AND src.file_path <> ?
      AND src.file_path <> ''
    LIMIT 30
  `).all(relPath, relPath);

  return { callers, importers, tests };
}

export function buildMessage(relPath, data, indexAgeDays) {
  const { callers, importers, tests } = data;
  if (!callers.length && !importers.length && !tests.length) return null;

  const age = indexAgeDays === 0 ? 'сегодняшний' : `${indexAgeDays} дн. назад`;
  const lines = [`BLAST RADIUS — ${relPath} (граф кода, индекс ${age})`];

  const prodImporters = importers.map((r) => r.caller_file).filter((f) => !isTestPath(f));
  if (prodImporters.length) {
    const shown = prodImporters.slice(0, 5).join(', ');
    const rest = prodImporters.length > 5 ? ` +${prodImporters.length - 5}` : '';
    lines.push(`Импортируют файл (${prodImporters.length}): ${shown}${rest}`);
  }

  const callerLines = formatCallers(callers);
  if (callerLines.length) {
    lines.push('Вызывают отсюда:');
    lines.push(...callerLines);
  }

  // Every route into this file from a test — TESTS edges plus the test files
  // that call or import it — is one list; that is the set to re-run.
  const testFiles = [...new Set([
    ...tests.map((r) => r.test_file),
    ...callers.map((r) => r.caller_file).filter(isTestPath),
    ...importers.map((r) => r.caller_file).filter(isTestPath),
  ])];
  if (testFiles.length) {
    const shown = testFiles.slice(0, 4).join(', ');
    const rest = testFiles.length > 4 ? ` +${testFiles.length - 4}` : '';
    lines.push(`Тесты, дотягивающиеся сюда (${testFiles.length}): ${shown}${rest}`);
  }

  lines.push(
    'Меняешь сигнатуру или удаляешь символ — обнови перечисленных вызывающих в этой же задаче и прогони эти тесты.',
  );
  if (indexAgeDays > STALE_DAYS) {
    lines.push(`Индексу ${indexAgeDays} дней, он мог отстать — приёмка остаётся grep по рабочему дереву.`);
  }

  const text = lines.join('\n');
  return text.length > MAX_CHARS ? `${text.slice(0, MAX_CHARS)}\n…(обрезано)` : text;
}

/** Same file, same session — inject once. Repeated edits would burn context for nothing. */
export function alreadySeen(sessionId, relPath) {
  if (!sessionId) return false;
  const dir = join(tmpdir(), 'dld-graph-hook');
  const file = join(dir, `${String(sessionId).replace(/[^a-zA-Z0-9_-]/g, '')}.json`);
  let seen = [];
  try {
    if (existsSync(file)) seen = JSON.parse(readFileSync(file, 'utf-8'));
  } catch { /* corrupt cache — treat as empty */ }
  if (Array.isArray(seen) && seen.includes(relPath)) return true;
  try {
    mkdirSync(dir, { recursive: true });
    writeFileSync(file, JSON.stringify([...(Array.isArray(seen) ? seen : []), relPath].slice(-200)));
  } catch { /* the cache is an optimisation, never a blocker */ }
  return false;
}

function emit(text) {
  process.stdout.write(
    `${JSON.stringify({ hookSpecificOutput: { hookEventName: 'PreToolUse', additionalContext: text } })}\n`,
  );
}

async function main() {
  const timer = debugTiming('graph-context');
  try {
    if (process.env.DLD_GRAPH_HOOK === '0') { timer.end('disabled'); process.exit(0); }

    const data = readHookInput();
    const filePath = getToolInput(data, 'file_path') || '';
    if (!filePath) { timer.end('no-file'); process.exit(0); }

    const ext = filePath.slice(filePath.lastIndexOf('.')).toLowerCase();
    if (!CODE_EXTENSIONS.has(ext)) { timer.end('not-code'); process.exit(0); }

    const { main, current } = repoRoots();
    const relPath = relativeTo(current, filePath);
    const dbPath = dbPathFor(main);
    if (!dbPath) {
      debugLog('graph-context', 'skip', { reason: 'no_index', root: main });
      timer.end('no-index');
      process.exit(0);
    }

    if (alreadySeen(data.session_id, relPath)) { timer.end('cached'); process.exit(0); }

    const { DatabaseSync } = await import('node:sqlite');
    const db = new DatabaseSync(dbPath, { readOnly: true });
    let payload;
    try {
      payload = collect(db, relPath);
    } finally {
      db.close();
    }

    const ageDays = Math.floor((Date.now() - statSync(dbPath).mtimeMs) / 86_400_000);
    const message = buildMessage(relPath, payload, ageDays);
    if (!message) {
      debugLog('graph-context', 'skip', { reason: 'no_edges', file: relPath });
      timer.end('no-edges');
      process.exit(0);
    }

    debugLog('graph-context', 'inject', { file: relPath, chars: message.length });
    timer.end('inject');
    emit(message);
    process.exit(0);
  } catch (e) {
    debugLog('graph-context', 'error', { error: String(e) });
    timer.end('error');
    logHookError('graph_context', e);
    process.exit(0);
  }
}

// `import ... from 'graph-context.mjs'` in tests must not run the hook.
if (process.env.DLD_GRAPH_HOOK_IMPORT_ONLY !== '1') {
  await main();
}
