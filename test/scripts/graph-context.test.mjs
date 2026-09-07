/**
 * Tests for .claude/hooks/graph-context.mjs
 *
 * The hook injects a file's blast radius (importers, callers, tests) into the
 * model's context before an Edit/Write runs, reading the codebase-memory index
 * directly over SQLite.
 *
 * Verifies:
 * - projectKeyFromRoot maps both POSIX and Windows roots to the index filename
 * - relativeTo resolves the edited file against the worktree it lives in
 * - isTestPath / formatCallers keep production call sites from being crowded
 *   out by test call sites
 * - buildMessage renders sections, merges every test route into one list,
 *   flags a stale index, and truncates
 * - alreadySeen injects once per file per session
 * - end-to-end: a real SQLite index in a real git repo produces a PreToolUse
 *   additionalContext payload; a non-code file, a missing index and the kill
 *   switch each produce nothing (fail-quiet, ADR-004)
 */

import { execFileSync } from 'child_process';
import { mkdirSync, rmSync, writeFileSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';
import { strict as assert } from 'assert';

process.env.DLD_GRAPH_HOOK_IMPORT_ONLY = '1';

const HOOK_PATH = join(process.cwd(), '.claude/hooks/graph-context.mjs');
const mod = await import(`file://${HOOK_PATH}`);
const { projectKeyFromRoot, relativeTo, isTestPath, formatCallers, buildMessage, alreadySeen } = mod;

const TEST_DIR = join(process.cwd(), 'test/scripts/.tmp-graph-context');

let sqlite = null;
try {
  sqlite = await import('node:sqlite');
} catch {
  sqlite = null;
}
const hasNodeSqlite = sqlite !== null;

function setup() {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(TEST_DIR, { recursive: true });
}

function cleanup() {
  try { rmSync(TEST_DIR, { recursive: true, force: true }); } catch { /* best effort */ }
}

// --- Pure functions ---

function testProjectKeyFromRoot() {
  assert.equal(projectKeyFromRoot('/home/dld/projects/dld'), 'home-dld-projects-dld');
  assert.equal(projectKeyFromRoot('D:\\dev\\dld'), 'D-dev-dld');
  assert.equal(projectKeyFromRoot('D:/dev/Dowry-mc'), 'D-dev-Dowry-mc');
  assert.equal(projectKeyFromRoot('/home/dld/projects/dld/'), 'home-dld-projects-dld');
  console.log('  PASS: testProjectKeyFromRoot');
}

function testRelativeTo() {
  assert.equal(relativeTo('/repo', '/repo/src/app.py'), 'src/app.py');
  assert.equal(relativeTo('D:\\dev\\dld', 'D:\\dev\\dld\\scripts\\vps\\lifecycle.py'), 'scripts/vps/lifecycle.py');
  // Autopilot worktree: the path is relative to the worktree, not the main checkout.
  assert.equal(relativeTo('/home/dld/projects/awardybot-FTR-1', '/home/dld/projects/awardybot-FTR-1/src/x.py'), 'src/x.py');
  // Outside the root — left as-is rather than mangled into a wrong lookup.
  assert.equal(relativeTo('/repo', '/elsewhere/x.py'), '/elsewhere/x.py');
  console.log('  PASS: testRelativeTo');
}

function testIsTestPath() {
  assert.equal(isTestPath('tests/integration/test_callback.py'), true);
  assert.equal(isTestPath('scripts/vps/tests/test_lifecycle.py'), true);
  assert.equal(isTestPath('src/infra/llm/routing_test.py'), true);
  assert.equal(isTestPath('miniapp/src/app.test.ts'), true);
  assert.equal(isTestPath('miniapp/src/app.spec.ts'), true);
  assert.equal(isTestPath('scripts/vps/lifecycle.py'), false);
  assert.equal(isTestPath('src/latest/protest.py'), false);
  console.log('  PASS: testIsTestPath');
}

function testFormatCallersDropsTests() {
  const rows = [
    { target: 'write_lifecycle', caller_file: 'scripts/vps/callback.py' },
    { target: 'write_lifecycle', caller_file: 'scripts/vps/orchestrator.py' },
    { target: 'write_lifecycle', caller_file: 'tests/test_lifecycle.py' },
    { target: 'read_lifecycle', caller_file: 'scripts/vps/callback.py' },
  ];
  const lines = formatCallers(rows);
  assert.equal(lines.length, 2, 'one line per callee');
  assert.ok(lines[0].startsWith('  write_lifecycle'), 'busiest callee first');
  assert.ok(lines[0].includes('вызовов: 2'), 'test call sites are not counted here');
  assert.ok(!lines.join('\n').includes('tests/test_lifecycle.py'), 'test files stay out of the caller list');
  console.log('  PASS: testFormatCallersDropsTests');
}

function testFormatCallersCaps() {
  const rows = Array.from({ length: 12 }, (_, i) => ({ target: `fn${i}`, caller_file: `src/f${i}.py` }));
  assert.equal(formatCallers(rows).length, 6, 'at most 6 callees are listed');
  console.log('  PASS: testFormatCallersCaps');
}

function testBuildMessageEmpty() {
  assert.equal(buildMessage('src/x.py', { callers: [], importers: [], tests: [] }, 0), null);
  console.log('  PASS: testBuildMessageEmpty');
}

function testBuildMessageSections() {
  const msg = buildMessage('scripts/vps/lifecycle.py', {
    callers: [
      { target: 'write_lifecycle', caller_file: 'scripts/vps/callback.py' },
      { target: 'write_lifecycle', caller_file: 'tests/test_lifecycle.py' },
    ],
    importers: [
      { caller_file: 'scripts/vps/orchestrator.py' },
      { caller_file: 'tests/test_orchestrator.py' },
    ],
    tests: [{ test_file: 'scripts/vps/tests/test_lifecycle.py' }],
  }, 0);

  assert.ok(msg.startsWith('BLAST RADIUS — scripts/vps/lifecycle.py'), 'names the file first');
  assert.ok(msg.includes('Импортируют файл (1): scripts/vps/orchestrator.py'), 'test importers are not counted as importers');
  assert.ok(msg.includes('write_lifecycle'), 'lists callees');
  // Three different routes in from tests collapse into one list of files to re-run.
  assert.ok(msg.includes('Тесты, дотягивающиеся сюда (3)'), `expected 3 test files, got: ${msg}`);
  assert.ok(!msg.includes('он мог отстать'), 'a fresh index carries no staleness caveat');
  console.log('  PASS: testBuildMessageSections');
}

function testBuildMessageStaleIndex() {
  const msg = buildMessage('src/x.py', { callers: [], importers: [{ caller_file: 'src/y.py' }], tests: [] }, 30);
  assert.ok(msg.includes('30 дн. назад'), 'states the index age');
  assert.ok(msg.includes('он мог отстать'), 'warns when the index is older than a week');
  console.log('  PASS: testBuildMessageStaleIndex');
}

function testBuildMessageTruncates() {
  // Per-section caps normally keep the message near 900 chars; truncation is the
  // backstop for pathological path lengths, so the fixture uses those.
  const longPath = (i) => `src/${'nested/'.repeat(40)}module_${i}.py`;
  const importers = Array.from({ length: 60 }, (_, i) => ({ caller_file: longPath(i) }));
  const callers = Array.from({ length: 6 }, (_, i) => ({ target: `function_with_a_long_name_${i}`, caller_file: longPath(100 + i) }));
  const msg = buildMessage('src/x.py', { callers, importers, tests: [] }, 0);
  assert.ok(msg.length <= 1420, `message stays within budget, got ${msg.length}`);
  assert.ok(msg.endsWith('…(обрезано)'), 'truncation is visible');
  console.log('  PASS: testBuildMessageTruncates');
}

function testAlreadySeen() {
  const session = `test-${Date.now()}`;
  assert.equal(alreadySeen(session, 'src/a.py'), false, 'first edit of a file injects');
  assert.equal(alreadySeen(session, 'src/a.py'), true, 'second edit of the same file stays quiet');
  assert.equal(alreadySeen(session, 'src/b.py'), false, 'a different file injects again');
  assert.equal(alreadySeen(`${session}-other`, 'src/a.py'), false, 'a different session injects again');
  assert.equal(alreadySeen('', 'src/a.py'), false, 'no session id — never suppress');
  try { rmSync(join(tmpdir(), 'dld-graph-hook'), { recursive: true, force: true }); } catch { /* best effort */ }
  console.log('  PASS: testAlreadySeen');
}

// --- End-to-end against a real index ---

function makeIndex(dbPath, rows) {
  const { DatabaseSync } = sqlite;
  const db = new DatabaseSync(dbPath);
  db.exec(`
    CREATE TABLE nodes (id INTEGER PRIMARY KEY, project TEXT NOT NULL, label TEXT NOT NULL,
      name TEXT NOT NULL, qualified_name TEXT NOT NULL, file_path TEXT DEFAULT '',
      start_line INTEGER DEFAULT 0, end_line INTEGER DEFAULT 0, properties TEXT DEFAULT '{}');
    CREATE TABLE edges (id INTEGER PRIMARY KEY, project TEXT NOT NULL, source_id INTEGER NOT NULL,
      target_id INTEGER NOT NULL, type TEXT NOT NULL, properties TEXT DEFAULT '{}');
  `);
  const node = db.prepare('INSERT INTO nodes (id, project, label, name, qualified_name, file_path) VALUES (?,?,?,?,?,?)');
  const edge = db.prepare('INSERT INTO edges (project, source_id, target_id, type) VALUES (?,?,?,?)');
  for (const n of rows.nodes) node.run(n.id, 'p', n.label, n.name, `p.${n.name}`, n.file_path);
  for (const e of rows.edges) edge.run('p', e.source, e.target, e.type);
  db.close();
}

function runHookIn(cwd, stdinData, env = {}) {
  try {
    const raw = execFileSync('node', [HOOK_PATH], {
      cwd,
      input: JSON.stringify(stdinData),
      encoding: 'utf-8',
      timeout: 20000,
      env: { ...process.env, DLD_GRAPH_HOOK_IMPORT_ONLY: '0', ...env },
    }).trim();
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    const raw = (e.stdout || '').trim();
    return raw ? JSON.parse(raw) : null;
  }
}

function makeRepo(name) {
  const repo = join(TEST_DIR, name);
  mkdirSync(join(repo, 'src'), { recursive: true });
  writeFileSync(join(repo, 'src/target.py'), 'def handler():\n    return 1\n');
  execFileSync('git', ['init', '-q'], { cwd: repo });
  return repo;
}

function testEndToEndInjects() {
  const repo = makeRepo('repo-inject');
  const cacheDir = join(TEST_DIR, 'cache');
  mkdirSync(cacheDir, { recursive: true });
  makeIndex(join(cacheDir, `${projectKeyFromRoot(repo)}.db`), {
    nodes: [
      { id: 1, label: 'Function', name: 'handler', file_path: 'src/target.py' },
      { id: 2, label: 'Function', name: 'caller', file_path: 'src/other.py' },
      { id: 3, label: 'File', name: 'other.py', file_path: 'src/other.py' },
      { id: 4, label: 'Function', name: 'test_handler', file_path: 'tests/test_target.py' },
      { id: 5, label: 'File', name: 'target.py', file_path: 'src/target.py' },
    ],
    edges: [
      { source: 2, target: 1, type: 'CALLS' },
      { source: 3, target: 5, type: 'IMPORTS' },
      { source: 4, target: 1, type: 'TESTS' },
    ],
  });

  const out = runHookIn(repo, { session_id: 'e2e-1', tool_input: { file_path: join(repo, 'src/target.py') } }, { CBM_CACHE_DIR: cacheDir });
  assert.ok(out, 'hook produced output');
  assert.equal(out.hookSpecificOutput.hookEventName, 'PreToolUse');
  assert.equal(out.hookSpecificOutput.permissionDecision, undefined, 'the hook injects context, it does not decide permissions');
  const ctx = out.hookSpecificOutput.additionalContext;
  assert.ok(ctx.includes('src/target.py'), 'names the edited file');
  assert.ok(ctx.includes('handler'), 'names the called function');
  assert.ok(ctx.includes('src/other.py'), 'names the caller file');
  assert.ok(ctx.includes('tests/test_target.py'), 'names the test that reaches it');
  console.log('  PASS: testEndToEndInjects');
}

function testEndToEndQuietCases() {
  const repo = makeRepo('repo-quiet');
  const cacheDir = join(TEST_DIR, 'cache');

  const doc = runHookIn(repo, { session_id: 'e2e-2', tool_input: { file_path: join(repo, 'README.md') } }, { CBM_CACHE_DIR: cacheDir });
  assert.equal(doc, null, 'a non-code file produces nothing');

  const noIndex = runHookIn(repo, { session_id: 'e2e-3', tool_input: { file_path: join(repo, 'src/target.py') } }, { CBM_CACHE_DIR: join(TEST_DIR, 'empty-cache') });
  assert.equal(noIndex, null, 'a missing index produces nothing');

  const off = runHookIn(repo, { session_id: 'e2e-4', tool_input: { file_path: join(repo, 'src/target.py') } }, { CBM_CACHE_DIR: cacheDir, DLD_GRAPH_HOOK: '0' });
  assert.equal(off, null, 'the kill switch silences the hook');
  console.log('  PASS: testEndToEndQuietCases');
}

// --- Runner ---

function main() {
  setup();
  let passed = 0;
  const total = hasNodeSqlite ? 12 : 10;
  try {
    testProjectKeyFromRoot(); passed++;
    testRelativeTo(); passed++;
    testIsTestPath(); passed++;
    testFormatCallersDropsTests(); passed++;
    testFormatCallersCaps(); passed++;
    testBuildMessageEmpty(); passed++;
    testBuildMessageSections(); passed++;
    testBuildMessageStaleIndex(); passed++;
    testBuildMessageTruncates(); passed++;
    testAlreadySeen(); passed++;

    if (hasNodeSqlite) {
      testEndToEndInjects(); passed++;
      testEndToEndQuietCases(); passed++;
    } else {
      // Node 20 has no node:sqlite; the hook degrades to silence there and so
      // does this suite. Saying so beats a green run that measured nothing.
      console.log('  SKIP: end-to-end (node:sqlite unavailable — Node < 22)');
    }
    console.log(`\n${passed}/${total} tests passed`);
  } finally {
    cleanup();
  }
}

main();
