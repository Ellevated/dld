/**
 * Tests for pre-bash.mjs hook.
 *
 * Uses node:test + node:assert (no external deps).
 * Spawns the hook as a child process via runHook() helper.
 *
 * Decision outcomes:
 *   ALLOW — exitCode=0, stdout=null (silent exit)
 *   DENY  — exitCode=0, stdout.hookSpecificOutput.permissionDecision='deny'
 *   ASK   — exitCode=0, stdout.hookSpecificOutput.permissionDecision='ask'
 */

import { describe, it } from 'node:test';
import { strictEqual, ok } from 'node:assert';
import { runHook, makePreToolInput } from './helpers.mjs';

// --- Helpers ---

function run(command) {
  const input = makePreToolInput('Bash', { command });
  return runHook('pre-bash.mjs', input);
}

function assertAllow(result, label) {
  strictEqual(result.exitCode, 0, `${label}: expected exitCode 0`);
  strictEqual(result.stdout, null, `${label}: expected null stdout (silent allow)`);
}

function assertDeny(result, label) {
  strictEqual(result.exitCode, 0, `${label}: expected exitCode 0`);
  ok(result.stdout, `${label}: expected non-null stdout`);
  strictEqual(
    result.stdout.hookSpecificOutput?.permissionDecision,
    'deny',
    `${label}: expected decision=deny`
  );
}

function assertAsk(result, label) {
  strictEqual(result.exitCode, 0, `${label}: expected exitCode 0`);
  ok(result.stdout, `${label}: expected non-null stdout`);
  strictEqual(
    result.stdout.hookSpecificOutput?.permissionDecision,
    'ask',
    `${label}: expected decision=ask`
  );
}

// --- isDestructiveClean tests (via BLOCKED_PATTERNS integration) ---

describe('isDestructiveClean — blocked (destructive combinations)', () => {
  it('blocks git clean -fd', () => {
    assertDeny(run('git clean -fd'), 'git clean -fd');
  });

  it('blocks git clean -df (reversed flags)', () => {
    assertDeny(run('git clean -df'), 'git clean -df');
  });

  it('blocks git clean --force -d', () => {
    assertDeny(run('git clean --force -d'), 'git clean --force -d');
  });

  it('blocks git clean -f -d (separated flags)', () => {
    assertDeny(run('git clean -f -d'), 'git clean -f -d');
  });

  it('blocks git clean -fdx (extra flags with force+dir)', () => {
    assertDeny(run('git clean -fdx'), 'git clean -fdx');
  });

  it('blocks git clean -fde .gitignore', () => {
    assertDeny(run('git clean -fde .gitignore'), 'git clean -fde .gitignore');
  });
});

describe('isDestructiveClean — allowed (safe variants)', () => {
  it('allows git clean -fdn (dry-run flag n)', () => {
    assertAllow(run('git clean -fdn'), 'git clean -fdn');
  });

  it('allows git clean --dry-run -fd', () => {
    assertAllow(run('git clean --dry-run -fd'), 'git clean --dry-run -fd');
  });

  it('allows git clean -n (no force, no dir)', () => {
    assertAllow(run('git clean -n'), 'git clean -n');
  });

  it('allows git clean without -f or -d', () => {
    assertAllow(run('git clean'), 'git clean (bare)');
  });

  it('allows git clean -f alone (no -d)', () => {
    assertAllow(run('git clean -f'), 'git clean -f (no dir)');
  });

  it('allows git clean -d alone (no -f)', () => {
    assertAllow(run('git clean -d'), 'git clean -d (no force)');
  });
});

// --- BLOCKED_PATTERNS — push to main ---

describe('BLOCKED_PATTERNS — push to main branch', () => {
  it('blocks git push origin main', () => {
    assertDeny(run('git push origin main'), 'push to main');
  });

  it('blocks git push origin main (with upstream flags)', () => {
    assertDeny(run('git push -u origin main'), 'push -u to main');
  });

  it('allows git push origin develop', () => {
    assertAllow(run('git push origin develop'), 'push to develop');
  });

  it('allows git push origin feature/foo (branch contains main substring)', () => {
    // "fix-main-menu" must not be caught by the main pattern (word boundary)
    assertAllow(run('git push origin fix-main-menu'), 'push to fix-main-menu');
  });

  it('allows git push origin main-feature (main as prefix, not standalone)', () => {
    assertAllow(run('git push origin main-feature'), 'push to main-feature');
  });

  it('allows git push origin feature/add-main-button (main in path)', () => {
    assertAllow(run('git push origin feature/add-main-button'), 'push to feature/add-main-button');
  });
});

// --- BLOCKED_PATTERNS — git reset --hard ---

describe('BLOCKED_PATTERNS — git reset --hard', () => {
  it('blocks git reset --hard', () => {
    assertDeny(run('git reset --hard'), 'reset --hard bare');
  });

  it('blocks git reset --hard HEAD~1', () => {
    assertDeny(run('git reset --hard HEAD~1'), 'reset --hard HEAD~1');
  });

  it('blocks git reset --hard origin/develop', () => {
    assertDeny(run('git reset --hard origin/develop'), 'reset --hard origin/develop');
  });

  it('allows git reset --soft HEAD~1', () => {
    assertAllow(run('git reset --soft HEAD~1'), 'reset --soft');
  });

  it('allows git reset HEAD (unstage)', () => {
    assertAllow(run('git reset HEAD'), 'reset HEAD unstage');
  });

  it('allows git reset --mixed HEAD~1', () => {
    assertAllow(run('git reset --mixed HEAD~1'), 'reset --mixed');
  });
});

// --- BLOCKED_PATTERNS — force push to protected branches ---

describe('BLOCKED_PATTERNS — force push to protected branches', () => {
  it('blocks git push -f origin develop', () => {
    assertDeny(run('git push -f origin develop'), 'force push develop');
  });

  it('blocks git push -f origin main', () => {
    assertDeny(run('git push -f origin main'), 'force push main');
  });

  it('blocks git push --force origin develop', () => {
    assertDeny(run('git push --force origin develop'), 'force push --force develop');
  });

  it('allows git push -f origin feature/foo (feature branch)', () => {
    assertAllow(run('git push -f origin feature/foo'), 'force push feature branch');
  });

  it('allows git push --force-with-lease origin develop (safe force)', () => {
    assertAllow(
      run('git push --force-with-lease origin develop'),
      'push --force-with-lease develop'
    );
  });

  it('blocks git push --force-with-lease origin main (main is always protected)', () => {
    // The "push to main" hard-block fires before the force-push check.
    // --force-with-lease does NOT bypass the main branch protection.
    assertDeny(
      run('git push --force-with-lease origin main'),
      'push --force-with-lease main still blocked'
    );
  });
});

// --- MERGE_PATTERNS — ask for confirmation ---

describe('MERGE_PATTERNS — soft block (ask)', () => {
  it('asks for git merge feature/foo (no --ff-only)', () => {
    assertAsk(run('git merge feature/foo'), 'merge without --ff-only');
  });

  it('asks for git merge develop', () => {
    assertAsk(run('git merge develop'), 'merge develop without --ff-only');
  });

  it('allows git merge --ff-only feature/foo', () => {
    assertAllow(run('git merge --ff-only feature/foo'), 'merge --ff-only');
  });

  it('allows git merge-base develop feature/foo (subcommand not merge)', () => {
    assertAllow(run('git merge-base develop feature/foo'), 'merge-base not a merge');
  });

  it('allows git mergetool (mergetool not a merge)', () => {
    assertAllow(run('git mergetool'), 'mergetool not a merge');
  });
});

// --- Fail-safe: malformed input (ADR-004) ---

describe('Fail-safe — malformed stdin allows (ADR-004)', () => {
  it('allows when stdin is not valid JSON', () => {
    const result = runHook('pre-bash.mjs', 'THIS IS NOT JSON');
    // readHookInput() catches JSON parse error and returns {}
    // getToolInput returns null → command = '' → no matches → allowTool()
    strictEqual(result.exitCode, 0, 'malformed stdin: expected exitCode 0');
    strictEqual(result.stdout, null, 'malformed stdin: expected null stdout (allow)');
  });

  it('allows when tool_input is missing (no command field)', () => {
    const input = { hook_type: 'PreToolUse', tool_name: 'Bash', tool_input: {} };
    const result = runHook('pre-bash.mjs', input);
    assertAllow(result, 'missing command field');
  });
});

// --- Non-Bash tool: hook should allow silently ---

describe('Non-Bash tool calls — always allowed', () => {
  it('allows Read tool (not bash)', () => {
    const input = makePreToolInput('Read', { file_path: '/some/path' });
    const result = runHook('pre-bash.mjs', input);
    // command = '' because tool_input.command is absent → allowTool()
    assertAllow(result, 'Read tool');
  });

  it('allows Edit tool (not bash)', () => {
    const input = makePreToolInput('Edit', { file_path: '/some/path', old_string: 'a', new_string: 'b' });
    const result = runHook('pre-bash.mjs', input);
    assertAllow(result, 'Edit tool');
  });
});

// --- Safe everyday commands — always allowed ---

describe('Safe everyday commands — allowed', () => {
  it('allows git status', () => {
    assertAllow(run('git status'), 'git status');
  });

  it('allows git log --oneline -10', () => {
    assertAllow(run('git log --oneline -10'), 'git log');
  });

  it('allows git diff HEAD', () => {
    assertAllow(run('git diff HEAD'), 'git diff');
  });

  it('allows git stash', () => {
    assertAllow(run('git stash'), 'git stash');
  });

  it('allows git checkout -b feature/new-thing', () => {
    assertAllow(run('git checkout -b feature/new-thing'), 'git checkout -b');
  });

  it('allows npm install', () => {
    assertAllow(run('npm install'), 'npm install');
  });

  it('allows ls -la', () => {
    assertAllow(run('ls -la'), 'ls -la');
  });
});
