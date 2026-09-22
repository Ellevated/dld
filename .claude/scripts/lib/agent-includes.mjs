/**
 * agent-includes.mjs — inline `_shared/` modules into agent prompt files.
 *
 * Claude Code imports `@path` lines in CLAUDE.md, but not in `.claude/agents/*.md`:
 * there the line reaches the model as literal text. Measured 2026-09-23, CLI 2.1.280:
 *   - a canary agent whose rule came through an `@` line ignored it three times out of
 *     three, with and without the Read tool; the same rule written into the body was
 *     followed;
 *   - on the VPS, `_shared/output-conventions.md` — "added to every agent" — was opened
 *     by 5 of 782 production subagent runs, `minimal-code.md` by 0 of 434 coder runs.
 *
 * So the shared text is written into each agent between marker comments, generated
 * from the one source in `agents/_shared/`. Editing the source and re-running the
 * expander is the only way to change it; the integrity check fails on a stale block
 * or on a raw `@` line, so the two copies cannot drift apart unnoticed.
 */

import { existsSync, readFileSync } from 'fs';
import { join } from 'path';

// Modules deliberately not inlined. Both are procedures, not calibration: one makes
// every agent read the project's rule files before any work, the other makes it write
// back to them after. Production ran without both (coder opened them 11 and 18 times
// out of 434), rules scoped by `paths:` already load when an agent touches matching
// files, and the 2026-09-02 autopilot review named that cold-start read as a cost to
// cut. A raw line naming one of these is removed, not expanded.
export const NOT_INLINED = new Set(['context-loader.md', 'context-updater.md']);

const RAW = /^@\.claude\/agents\/_shared\/([\w-]+\.md)\s*$/;
const BEGIN = /^<!-- include: _shared\/([\w-]+\.md) — .*-->\s*$/;
const END = (name) => `<!-- /include: _shared/${name} -->`;

export function beginMarker(name) {
  return (
    `<!-- include: _shared/${name} — generated from .claude/agents/_shared/${name} ` +
    'by .claude/scripts/expand-agent-includes.mjs; edit the source and re-run -->'
  );
}

function readShared(sharedDir, name) {
  const path = join(sharedDir, name);
  if (!existsSync(path)) throw new Error(`shared module not found: ${path}`);
  return readFileSync(path, 'utf-8').replace(/\r\n/g, '\n').replace(/\s+$/, '');
}

/**
 * Rewrite one agent file's text.
 * @param {string} text - the agent file as read (LF or CRLF)
 * @param {string} sharedDir - the tree's `agents/_shared` directory
 * @returns {{text: string, changed: boolean, raw: string[], stale: string[], dropped: string[]}}
 *   raw     — modules named by a raw `@` line (never reached the model)
 *   stale   — generated blocks whose body differs from the current source
 *   dropped — NOT_INLINED modules whose raw line was removed
 */
export function expandText(text, sharedDir) {
  const eol = text.includes('\r\n') ? '\r\n' : '\n';
  const lines = text.replace(/\r\n/g, '\n').split('\n');
  const out = [];
  const raw = [];
  const stale = [];
  const dropped = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const rawMatch = line.match(RAW);
    const beginMatch = line.match(BEGIN);

    if (rawMatch) {
      const name = rawMatch[1];
      raw.push(name);
      if (NOT_INLINED.has(name)) {
        dropped.push(name);
        // Removing the line must not leave a double blank line behind.
        if (out.length && out[out.length - 1].trim() === '' && (lines[i + 1] ?? '').trim() === '') {
          i++;
        }
        continue;
      }
      out.push(beginMarker(name), readShared(sharedDir, name), END(name));
      continue;
    }

    if (beginMatch) {
      const name = beginMatch[1];
      const end = lines.indexOf(END(name), i + 1);
      if (end === -1) throw new Error(`unterminated include block for ${name}`);
      const body = lines.slice(i + 1, end).join('\n');
      const fresh = readShared(sharedDir, name);
      if (body !== fresh || line !== beginMarker(name)) stale.push(name);
      out.push(beginMarker(name), fresh, END(name));
      i = end;
      continue;
    }

    out.push(line);
  }

  const result = out.join('\n').replace(/\n/g, eol);
  return { text: result, changed: result !== text, raw, stale, dropped };
}
