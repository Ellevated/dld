/**
 * captureArtifacts — copy what a skill wrote into an eval workspace.
 *
 * For a skill that writes files, stdout is a report *about* the work and the
 * files are the work: spark's deterministic assertions ("allowlist-parses",
 * "no-status-field", "min-eval-criteria") are all properties of a written spec.
 *
 * Two sources, because either alone loses real output:
 *   - working tree  — a skill that writes but does not commit
 *   - baseRef..HEAD — a skill that commits, which /spark does for every spec and
 *     lifecycle record. Committed work is invisible to `git status`, and a first
 *     version of this that checked only the working tree reported `artifacts: 1`
 *     for a run that had just written nine specs.
 *
 * Used by: run-eval.mjs, test/scripts/capture-artifacts.test.mjs
 */

import { mkdirSync, existsSync, cpSync } from 'fs';
import { join, dirname } from 'path';
import { execFileSync } from 'child_process';

export function captureArtifacts(cwd, destDir, baseRef) {
  const paths = new Set();

  try {
    const porcelain = execFileSync('git', ['status', '--porcelain', '--untracked-files=all'], {
      cwd, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024,
    });
    for (const line of porcelain.split('\n')) {
      if (!line.trim()) continue;
      // porcelain: XY <path>, and renames use "old -> new"
      paths.add(line.slice(3).trim().split(' -> ').pop().replace(/^"|"$/g, ''));
    }
  } catch {
    return { captured: [], note: 'not a git repo — artefacts not captured' };
  }

  if (baseRef) {
    try {
      const changed = execFileSync('git', ['diff', '--name-only', `${baseRef}..HEAD`], {
        cwd, encoding: 'utf-8', maxBuffer: 10 * 1024 * 1024,
      });
      for (const line of changed.split('\n')) {
        if (line.trim()) paths.add(line.trim());
      }
    } catch { /* base ref unreachable — working tree capture still stands */ }
  }

  const captured = [];
  for (const rel of paths) {
    const src = join(cwd, rel);
    if (!existsSync(src)) continue; // deleted
    const dst = join(destDir, rel);
    try {
      mkdirSync(dirname(dst), { recursive: true });
      cpSync(src, dst, { recursive: true });
      captured.push(rel);
    } catch { /* unreadable path — skip rather than fail the run */ }
  }
  return { captured };
}
