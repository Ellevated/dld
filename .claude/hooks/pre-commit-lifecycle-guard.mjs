#!/usr/bin/env node
// ARCH-187 / ADR-024 / ARCH-193 — block direct `git add ai/lifecycle/*.yaml` commits.
//
// Lifecycle state is written EXCLUSIVELY by callback via git plumbing
// (private GIT_INDEX_FILE) — callback and spec_operator NEVER stage files in
// the working index, so this guard never triggers for them.
//
// Wired by .git-hooks/pre-commit when core.hooksPath is set:
//   git config core.hooksPath .git-hooks
//
// Bypass: set LIFECYCLE_WRITE_AUTHORIZED=1 (last-resort operator override).
//         Bypass is audited — event_writer.py is invoked before exit(0).
//
// Exit codes:
//   0 — no lifecycle changes staged, or bypass active
//   1 — staged lifecycle changes detected (no bypass)
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

// TECH-194 C3: resolve event_writer.py relative to this file, not CWD.
// guard.mjs lives at .claude/hooks/ -> ../../scripts/vps/ = repo root/scripts/vps/
// This makes audit logging work for DLD repo regardless of worktree CWD.
const _guardDir = dirname(fileURLToPath(import.meta.url));
const _eventWriter = resolve(_guardDir, '../../scripts/vps/event_writer.py');

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

const files = staged();
const lifecycleFiles = files.filter((f) => /^ai\/lifecycle\/[^/]+\.yaml$/.test(f));

if (lifecycleFiles.length === 0) process.exit(0);

if (process.env.LIFECYCLE_WRITE_AUTHORIZED === '1') {
    try {
        let subject = '<no HEAD>';
        try {
            subject = execFileSync('git', ['log', '-1', '--format=%s', 'HEAD'],
                { encoding: 'utf-8', timeout: 2000 }).trim();
        } catch {}
        execFileSync('python3', [
            _eventWriter,
            process.cwd(),    // project_path
            'callback',       // skill
            'warning',        // status
            `LIFECYCLE_AUTHORIZED_BYPASS: ${lifecycleFiles.join(',')} prev_subject=${subject}`
        ], { timeout: 5000 });
    } catch { /* best-effort */ }
    process.exit(0);
}

console.error('');
console.error('✗ pre-commit-lifecycle-guard (ARCH-187 / ARCH-193):');
console.error('  Direct git commit touching ai/lifecycle/ is forbidden.');
console.error('  Lifecycle is written exclusively by callback (ADR-023/ARCH-193).');
console.error('  Staged lifecycle files:');
for (const f of lifecycleFiles) console.error(`    ${f}`);
console.error('');
console.error('  Allowed paths:');
console.error('    • python3 scripts/vps/spec_operator.py demote ... --by=<id>');
console.error('    • python3 scripts/vps/spec_operator.py force-done ... --by=<id>');
console.error('    • LIFECYCLE_WRITE_AUTHORIZED=1 git commit ... (last-resort override, audited)');
process.exit(1);
