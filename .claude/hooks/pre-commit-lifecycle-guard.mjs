#!/usr/bin/env node
// ARCH-187 / ADR-024 — block direct `git add ai/lifecycle/*.yaml` commits
// from any author whose commit message does not begin with `lifecycle(<ID>):`
// (the canonical callback / spec_operator pattern).
//
// Wired by .git-hooks/pre-commit when core.hooksPath is set:
//   git config core.hooksPath .git-hooks
//
// Bypass: set LIFECYCLE_WRITE_AUTHORIZED=1 (last-resort operator override).
// Callback and spec_operator do NOT need the bypass — they write via git
// plumbing (private GIT_INDEX_FILE) and never stage lifecycle files in the
// working index, so this guard never triggers for them.
//
// Exit codes:
//   0 — no lifecycle changes staged, or bypass active, or message matches
//   1 — staged lifecycle changes with a non-conforming commit message
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

function staged() {
    try {
        const out = execFileSync(
            'git',
            ['diff', '--cached', '--name-only', '--diff-filter=ACMR'],
            { encoding: 'utf-8', timeout: 5000 },
        );
        return out.split('\n').filter(Boolean);
    } catch {
        return [];
    }
}

function commitMsg() {
    // pre-commit hook runs BEFORE the message is finalised; fall back to
    // COMMIT_EDITMSG which git populates with the prepared message.
    try {
        return readFileSync('.git/COMMIT_EDITMSG', 'utf-8').trim();
    } catch {
        return '';
    }
}

const files = staged();
const lifecycleFiles = files.filter((f) => /^ai\/lifecycle\/[^/]+\.yaml$/.test(f));

if (lifecycleFiles.length === 0) process.exit(0);
if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') process.exit(0);

const msg = commitMsg();
if (/^lifecycle\([A-Z]+-\d+\):/.test(msg)) process.exit(0);

console.error('');
console.error('\u2717 pre-commit-lifecycle-guard (ARCH-187 / ADR-024):');
console.error('  Direct git commit touching ai/lifecycle/ is forbidden.');
console.error('  Lifecycle is written exclusively by callback (ADR-023/024).');
console.error('  Staged lifecycle files:');
for (const f of lifecycleFiles) console.error(`    ${f}`);
console.error('');
console.error('  Allowed paths:');
console.error('    \u2022 python3 scripts/vps/spec_operator.py demote ... --by=<id>');
console.error('    \u2022 python3 scripts/vps/spec_operator.py force-done ... --by=<id>');
console.error('    \u2022 LIFECYCLE_WRITE_AUTHORIZED=1 git commit ... (last-resort override)');
console.error('    \u2022 commit message starting with lifecycle(<SPEC-ID>):');
process.exit(1);
