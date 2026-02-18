/**
 * Unit tests for utils.mjs
 *
 * Covers: extractAllowedFiles, isFileAllowed, getProjectDir
 * Glob matching is tested indirectly via isFileAllowed (minimatch is not exported).
 *
 * Run: node --test __tests__/utils.test.mjs
 */

import { describe, it, before, after } from 'node:test';
import { strictEqual, deepStrictEqual, ok } from 'node:assert';
import { writeFileSync, mkdtempSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir, homedir } from 'node:os';

import { extractAllowedFiles, isFileAllowed, getProjectDir } from '../utils.mjs';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let tmpDir;

function mkSpec(content) {
  const path = join(tmpDir, `spec-${Math.random().toString(36).slice(2)}.md`);
  writeFileSync(path, content, 'utf-8');
  return path;
}

// ---------------------------------------------------------------------------
// Setup / teardown
// ---------------------------------------------------------------------------

before(() => {
  tmpDir = mkdtempSync(join(tmpdir(), 'utils-test-'));
});

after(() => {
  rmSync(tmpDir, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------
// extractAllowedFiles
// ---------------------------------------------------------------------------

describe('extractAllowedFiles', () => {
  it('returns files from backtick-wrapped paths', () => {
    const spec = mkSpec('## Allowed Files\n`src/foo.py`\n`src/bar.py`\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    ok(files.includes('src/foo.py'), 'should include src/foo.py');
    ok(files.includes('src/bar.py'), 'should include src/bar.py');
  });

  it('returns files from bold-wrapped paths (leading ** stripped, trailing ** kept in raw)', () => {
    // The extractor regex strips leading ** but the trailing ** is included in the raw match.
    // The file is still usable — isFileAllowed uses direct match and glob match.
    const spec = mkSpec('## Allowed Files\n**src/bold.py**\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    // At least one entry is extracted (may have trailing ** artifact)
    ok(files.length > 0, 'should extract at least one entry');
    ok(files.some(f => f.includes('src/bold')), 'should include src/bold in some form');
  });

  it('returns files from "path - description" format', () => {
    const spec = mkSpec('## Allowed Files\nsrc/main.py - the entry point\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    ok(files.includes('src/main.py'), 'should include src/main.py');
  });

  it('strips line number suffixes like :10-20', () => {
    const spec = mkSpec('## Allowed Files\n`src/utils.py:10-20`\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    ok(files.includes('src/utils.py'), 'should strip line range and include src/utils.py');
    ok(!files.some(f => f.includes(':')), 'should not have colon in path');
  });

  it('returns empty files array when section has no parseable paths', () => {
    // A section with only whitespace and comments produces no entries.
    const spec = mkSpec('## Allowed Files\n# just a comment\n\n## Next Section\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    deepStrictEqual(files, []);
  });

  it('returns empty files array when no Allowed Files section exists', () => {
    const spec = mkSpec('## Some Other Section\n`src/foo.py`\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    deepStrictEqual(files, []);
  });

  it('returns error:true for non-existent file', () => {
    const { files, error } = extractAllowedFiles('/nonexistent/path/spec.md');
    deepStrictEqual(files, []);
    strictEqual(error, true);
  });

  it('stops parsing at the next ## heading', () => {
    const spec = mkSpec(
      '## Allowed Files\n`src/a.py`\n\n## Other Section\n`src/b.py`\n'
    );
    const { files } = extractAllowedFiles(spec);
    ok(files.includes('src/a.py'), 'should include a.py');
    ok(!files.includes('src/b.py'), 'should not include b.py from next section');
  });

  it('handles glob patterns in allowed files', () => {
    const spec = mkSpec('## Allowed Files\n`src/**/*.py`\n');
    const { files, error } = extractAllowedFiles(spec);
    strictEqual(error, false);
    ok(files.includes('src/**/*.py'), 'should include glob pattern as-is');
  });
});

// ---------------------------------------------------------------------------
// isFileAllowed — no spec (null)
// ---------------------------------------------------------------------------

describe('isFileAllowed — no spec', () => {
  it('allows any file when specPath is null', () => {
    const result = isFileAllowed('src/anything.py', null);
    strictEqual(result.allowed, true);
  });

  it('allows deeply nested file when specPath is null', () => {
    const result = isFileAllowed('a/b/c/d/e.py', null);
    strictEqual(result.allowed, true);
  });
});

// ---------------------------------------------------------------------------
// isFileAllowed — ALWAYS_ALLOWED_PATTERNS
// ---------------------------------------------------------------------------

describe('isFileAllowed — ALWAYS_ALLOWED_PATTERNS', () => {
  // These should be allowed even when a spec exists with no matching entries.

  it('always allows ai/features/*.md pattern', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('ai/features/BUG-001-fix.md', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows ai/backlog.md', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('ai/backlog.md', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows files under ai/diary/**', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('ai/diary/2026-02-17.md', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows .gitignore', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('.gitignore', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows pyproject.toml', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('pyproject.toml', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows .claude/ files', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('.claude/settings.json', spec);
    strictEqual(result.allowed, true);
  });

  it('always allows nested .claude/ files', () => {
    const spec = mkSpec('## Allowed Files\n`src/other.py`\n');
    const result = isFileAllowed('.claude/hooks/pre-edit.mjs', spec);
    strictEqual(result.allowed, true);
  });
});

// ---------------------------------------------------------------------------
// isFileAllowed — spec-based checks
// ---------------------------------------------------------------------------

describe('isFileAllowed — spec allowlist', () => {
  it('allows file explicitly listed in spec', () => {
    const spec = mkSpec('## Allowed Files\n`src/models.py`\n');
    const result = isFileAllowed('src/models.py', spec);
    strictEqual(result.allowed, true);
  });

  it('denies file not in spec allowlist', () => {
    const spec = mkSpec('## Allowed Files\n`src/models.py`\n');
    const result = isFileAllowed('src/views.py', spec);
    strictEqual(result.allowed, false);
  });

  it('allows file when spec has no Allowed Files section (open spec)', () => {
    const spec = mkSpec('## Task\nDo something\n');
    const result = isFileAllowed('src/anything.py', spec);
    strictEqual(result.allowed, true);
  });

  it('returns error when spec file is unreadable', () => {
    const result = isFileAllowed('src/foo.py', '/no/such/spec.md');
    strictEqual(result.allowed, false);
    ok('error' in result, 'should have error property');
  });

  it('returns allowedFiles list from spec on deny', () => {
    const spec = mkSpec('## Allowed Files\n`src/a.py`\n`src/b.py`\n');
    const result = isFileAllowed('src/c.py', spec);
    strictEqual(result.allowed, false);
    ok(Array.isArray(result.allowedFiles), 'allowedFiles should be an array');
    ok(result.allowedFiles.length >= 2, 'should have at least 2 entries');
  });

  it('normalizes leading ./ before checking', () => {
    const spec = mkSpec('## Allowed Files\n`src/main.py`\n');
    const result = isFileAllowed('./src/main.py', spec);
    strictEqual(result.allowed, true);
  });
});

// ---------------------------------------------------------------------------
// isFileAllowed — glob patterns via minimatch (indirect)
// ---------------------------------------------------------------------------

describe('isFileAllowed — glob patterns (minimatch indirect)', () => {
  it('* matches files in a directory (not subdirs)', () => {
    const spec = mkSpec('## Allowed Files\n`src/*.py`\n');
    strictEqual(isFileAllowed('src/foo.py', spec).allowed, true);
    strictEqual(isFileAllowed('src/bar.py', spec).allowed, true);
  });

  it('* does not match path separator', () => {
    const spec = mkSpec('## Allowed Files\n`src/*.py`\n');
    strictEqual(isFileAllowed('src/sub/foo.py', spec).allowed, false);
  });

  it('** matches any depth', () => {
    const spec = mkSpec('## Allowed Files\n`src/**/*.py`\n');
    strictEqual(isFileAllowed('src/a/b/c/deep.py', spec).allowed, true);
  });

  it('** requires at least one intermediate segment (regex is .*/)', () => {
    // The minimatch impl converts ** to .* but the pattern src/**/*.py becomes
    // ^src/.*/[^/]*\.py$ which requires a / before the filename segment.
    // Therefore src/foo.py does NOT match — an intermediate dir is required.
    const spec = mkSpec('## Allowed Files\n`src/**/*.py`\n');
    strictEqual(isFileAllowed('src/foo.py', spec).allowed, false);
    strictEqual(isFileAllowed('src/sub/foo.py', spec).allowed, true);
    strictEqual(isFileAllowed('src/a/b/c.py', spec).allowed, true);
  });

  it('? in path is not extracted by extractAllowedFiles (regex limitation)', () => {
    // The path extractor regex only allows [a-zA-Z0-9_./@*-] so ? is truncated.
    // src/fo?.py -> extracted as 'src/fo', which won't match real files.
    const spec = mkSpec('## Allowed Files\n`src/fo?.py`\n');
    const { files } = extractAllowedFiles(spec);
    strictEqual(files[0], 'src/fo', 'extractor stops at ? character');
    // Neither src/foo.py nor src/fo.py matches the truncated 'src/fo' pattern
    strictEqual(isFileAllowed('src/foo.py', spec).allowed, false);
    strictEqual(isFileAllowed('src/fo.py', spec).allowed, false);
  });

  it('? does not match path separator', () => {
    const spec = mkSpec('## Allowed Files\n`src/f?o.py`\n');
    strictEqual(isFileAllowed('src/f/o.py', spec).allowed, false);
  });

  it('exact match works without globs', () => {
    const spec = mkSpec('## Allowed Files\n`src/exact.py`\n');
    strictEqual(isFileAllowed('src/exact.py', spec).allowed, true);
    strictEqual(isFileAllowed('src/exact_other.py', spec).allowed, false);
  });

  it('character class [abc] is not extracted by extractAllowedFiles (regex limitation)', () => {
    // The path extractor regex only allows [a-zA-Z0-9_./@*-] so [ is a stop character.
    // src/[abc].py -> extracted as 'src/', which won't match real files.
    const spec = mkSpec('## Allowed Files\n`src/[abc].py`\n');
    const { files } = extractAllowedFiles(spec);
    strictEqual(files[0], 'src/', 'extractor stops at [ character');
    // src/a.py does not match the truncated 'src/' pattern
    strictEqual(isFileAllowed('src/a.py', spec).allowed, false);
    strictEqual(isFileAllowed('src/d.py', spec).allowed, false);
  });

  it('pattern with no glob matches only exact path', () => {
    const spec = mkSpec('## Allowed Files\n`tests/test_main.py`\n');
    strictEqual(isFileAllowed('tests/test_main.py', spec).allowed, true);
    strictEqual(isFileAllowed('tests/test_other.py', spec).allowed, false);
  });

  it('** without file extension matches any file under dir', () => {
    const spec = mkSpec('## Allowed Files\n`ai/diary/**`\n');
    strictEqual(isFileAllowed('ai/diary/entry.md', spec).allowed, true);
    strictEqual(isFileAllowed('ai/diary/2026/jan.md', spec).allowed, true);
  });

  it('multiple patterns: first match wins (allow)', () => {
    const spec = mkSpec('## Allowed Files\n`src/*.py`\n`tests/*.py`\n');
    strictEqual(isFileAllowed('src/foo.py', spec).allowed, true);
    strictEqual(isFileAllowed('tests/foo.py', spec).allowed, true);
    strictEqual(isFileAllowed('docs/foo.py', spec).allowed, false);
  });

  it('dot files are matched literally (no special treatment)', () => {
    const spec = mkSpec('## Allowed Files\n`.env.example`\n');
    strictEqual(isFileAllowed('.env.example', spec).allowed, true);
    strictEqual(isFileAllowed('.env', spec).allowed, false);
  });

  it('pattern with extension wildcard: *.mjs matches .mjs files', () => {
    const spec = mkSpec('## Allowed Files\n`hooks/*.mjs`\n');
    strictEqual(isFileAllowed('hooks/pre-edit.mjs', spec).allowed, true);
    strictEqual(isFileAllowed('hooks/pre-edit.py', spec).allowed, false);
  });

  it('single * does not cross directory boundary in nested path', () => {
    const spec = mkSpec('## Allowed Files\n`src/domain/*/models.py`\n');
    strictEqual(isFileAllowed('src/domain/users/models.py', spec).allowed, true);
    strictEqual(isFileAllowed('src/domain/users/deep/models.py', spec).allowed, false);
  });
});

// ---------------------------------------------------------------------------
// getProjectDir
// ---------------------------------------------------------------------------

describe('getProjectDir', () => {
  const originalEnv = process.env.CLAUDE_PROJECT_DIR;

  after(() => {
    if (originalEnv === undefined) {
      delete process.env.CLAUDE_PROJECT_DIR;
    } else {
      process.env.CLAUDE_PROJECT_DIR = originalEnv;
    }
  });

  it('returns resolved path when CLAUDE_PROJECT_DIR is under home', () => {
    const safeDir = join(homedir(), 'my-project');
    process.env.CLAUDE_PROJECT_DIR = safeDir;
    const result = getProjectDir();
    strictEqual(result, safeDir);
  });

  it('returns resolved /tmp path when CLAUDE_PROJECT_DIR is under /tmp', () => {
    process.env.CLAUDE_PROJECT_DIR = '/tmp/test-project';
    const result = getProjectDir();
    strictEqual(result, '/tmp/test-project');
  });

  it('falls back to cwd when CLAUDE_PROJECT_DIR escapes home (/etc/passwd)', () => {
    process.env.CLAUDE_PROJECT_DIR = '/etc/passwd';
    const result = getProjectDir();
    strictEqual(result, process.cwd());
  });

  it('falls back to cwd when CLAUDE_PROJECT_DIR is /root (not under user home)', () => {
    // /root is root's home — typical user's home is /Users/... or /home/...
    // It won't start with homedir() unless we are root
    if (!homedir().startsWith('/root')) {
      process.env.CLAUDE_PROJECT_DIR = '/root/secret';
      const result = getProjectDir();
      strictEqual(result, process.cwd());
    }
  });

  it('falls back to cwd when CLAUDE_PROJECT_DIR is not set', () => {
    delete process.env.CLAUDE_PROJECT_DIR;
    const result = getProjectDir();
    // cwd() is not necessarily under home in CI, but function returns cwd or resolved dir
    ok(typeof result === 'string' && result.length > 0, 'should return a non-empty string');
  });
});
