#!/usr/bin/env node

/**
 * validate-allowlist.mjs — pre-flight check of a spec's `## Allowed Files`.
 *
 * Usage:
 *   node .claude/scripts/validate-allowlist.mjs <spec-file>
 *
 * Exit: 0 = pass, 1 = fail, 2 = usage error.
 * Output: one JSON object on stdout, always.
 *
 * Why this is a script and not prose in a prompt.
 * -----------------------------------------------
 * Spark used to run this check by reading four regexes out of its own prompt
 * and applying them by hand. That copy drifted from the parser that actually
 * gates the pipeline: numbered-list items were accepted by `callback.py`
 * (TECH-208) and rejected by the prompt, and a rejection there *deletes the
 * spec file*. A check whose failure mode is destructive has no business being
 * an LLM re-derivation of someone else's regex.
 *
 * The rules below therefore mirror `callback._parse_allowed_files_v1` and
 * `gate_logic.strip_bookkeeping_paths` exactly. Where this script is stricter
 * than the parser, it is because the parser's tolerance is silent and the
 * author would not learn about it until the run failed — each such case is
 * argued in place.
 */

import { readFileSync } from 'fs';

// --- Regexes: byte-for-byte the parser's, JS syntax ------------------------
// Sources: scripts/vps/callback.py:451-459, scripts/vps/gate_logic.py:46-52.
// Python `^`/`$` here are per-line because we match line by line, matching the
// parser, which iterates `spec_text.splitlines()`.
const HEADING_RE = /^##[ \t]+Allowed Files[ \t]*$/;
const MARKER_RE = /<!--\s*callback-allowlist\s+v1\b[^>]*-->/;
const BULLET_RE = /^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$/;
const NUMBERED_RE = /^\d+\.[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$/;
const NEXT_H2_RE = /^##\s+\S/;
// Any backticked path-shape, used only to detect paths the parser will drop.
const ANY_PATH_RE = /`([^\s`\n]+\.[a-zA-Z][\w-]*)`/g;

// gate_logic._BOOKKEEPING_* — paths that record work rather than perform it.
// A spec whose allowlist is entirely bookkeeping can never satisfy the
// implementation guard: it looks for a commit touching a non-bookkeeping path.
const BOOKKEEPING_PREFIXES = ['ai/lifecycle/', 'ai/features/', 'ai/diary/'];
const BOOKKEEPING_EXACT = new Set(['ai/backlog.md']);

function isBookkeeping(raw) {
  const p = raw.trim().replace(/^\.\//, '').replace(/\\/g, '/');
  if (BOOKKEEPING_EXACT.has(p)) return true;
  return BOOKKEEPING_PREFIXES.some((prefix) => p.startsWith(prefix));
}

function emit(payload, code) {
  console.log(JSON.stringify(payload, null, 2));
  process.exit(code);
}

// --- Entry ------------------------------------------------------------------
const specPath = process.argv[2];

if (!specPath || specPath === '--help' || specPath === '-h') {
  console.log(`validate-allowlist.mjs — check a spec's ## Allowed Files section

Usage:
  node .claude/scripts/validate-allowlist.mjs <spec-file>

Exit codes:
  0  allowlist is valid and usable by the implementation guard
  1  allowlist is missing, malformed, or unusable (details in JSON)
  2  usage error (no file given, or file unreadable)`);
  process.exit(specPath ? 0 : 2);
}

let text;
try {
  text = readFileSync(specPath, 'utf-8');
} catch (err) {
  emit(
    { ok: false, error_code: 'ALLOWLIST_E000_UNREADABLE', error_message: err.message, spec: specPath },
    2
  );
}

const lines = text.split(/\r?\n/);
const errors = [];
const warnings = [];

// 1. Canonical heading. The parser returns None without it and the caller
//    degrades open — the guard then verifies nothing at all.
const headingIdxs = [];
lines.forEach((ln, i) => {
  if (HEADING_RE.test(ln)) headingIdxs.push(i);
});

if (headingIdxs.length === 0) {
  emit(
    {
      ok: false,
      error_code: 'ALLOWLIST_E001_NO_HEADING',
      error_message:
        'No canonical `## Allowed Files` heading. Must be exactly that, case-sensitive, no suffix or parenthetical.',
      spec: specPath
    },
    1
  );
}

// 2. Duplicate heading. The parser silently uses the FIRST section
//    (`heading_idxs[0]`), so a second list is dead text that reads as live —
//    the author believes those paths are allowed and they are not.
if (headingIdxs.length > 1) {
  errors.push({
    code: 'ALLOWLIST_E002_DUPLICATE_HEADING',
    message: `${headingIdxs.length} \`## Allowed Files\` headings at lines ${headingIdxs
      .map((i) => i + 1)
      .join(', ')}. The parser reads the first and ignores the rest.`
  });
}

// Section = first heading until the next H2 (parser's rule exactly).
const start = headingIdxs[0] + 1;
let end = lines.length;
for (let j = start; j < lines.length; j++) {
  if (NEXT_H2_RE.test(lines[j])) {
    end = j;
    break;
  }
}
const section = lines.slice(start, end);

// 3. v1 marker. Without it the parser falls back to the legacy reader, which
//    scrapes every backticked path in the section — including ones in prose.
//    A newly written spec must be v1; legacy is for specs that predate it.
if (!MARKER_RE.test(section.join('\n'))) {
  errors.push({
    code: 'ALLOWLIST_E003_NO_MARKER',
    message:
      'Missing `<!-- callback-allowlist v1 -->` marker inside the section. Without it the spec is parsed by the legacy reader, which also picks up paths mentioned in prose.'
  });
}

// 4. Collect paths exactly as the parser does, and separately find paths the
//    author clearly meant to list that the parser will NOT see.
//
//    The distinction that matters: free prose in this section is legal, and
//    prose legitimately names files ("`callback.py` loses ~270 lines"). Those
//    are references, not entries, and flagging them is noise. What is a real
//    loss is a line SHAPED like an entry — a list item or a table row — whose
//    path the parser drops on the floor. Table rows earn their place here
//    because that was the format of an older spec template, so the mistake is
//    one specs actually make.
const LIST_SHAPED_RE = /^\s*(?:[-*+]|\d+\.)\s/;
const TABLE_ROW_RE = /^\s*\|.*\|/;

const paths = [];
const lostLines = [];
const extraPathLines = [];

section.forEach((ln, offset) => {
  const m = BULLET_RE.exec(ln) || NUMBERED_RE.exec(ln);
  const lineNo = start + offset + 1;
  const mentioned = [...ln.matchAll(ANY_PATH_RE)].map((x) => x[1]);

  if (m) {
    paths.push(m[1]);
    // Trailing prose after the path is the "reason" field and may legitimately
    // name other files. But it may equally be a second entry the parser silently
    // drops, and no rule can tell the two apart — so warn, never block.
    const extras = mentioned.filter((p) => p !== m[1]);
    if (extras.length > 0) {
      extraPathLines.push({ line: lineNo, text: ln.trim(), not_extracted: extras });
    }
    return;
  }

  if (mentioned.length === 0) return;
  if (ln.trim().startsWith('<!--')) return; // the marker is a comment

  if (LIST_SHAPED_RE.test(ln) || TABLE_ROW_RE.test(ln)) {
    lostLines.push({ line: lineNo, text: ln.trim(), lost: mentioned });
  }
});

if (lostLines.length > 0) {
  errors.push({
    code: 'ALLOWLIST_E004_UNPARSED_PATH',
    message:
      'Lines shaped like allowlist entries whose paths the parser will not extract. One path per line, as "- `path/to/file.py` — reason" or "1. `path/to/file.py` — reason". Tables are not parsed.',
    occurrences: lostLines
  });
}

if (extraPathLines.length > 0) {
  warnings.push({
    code: 'ALLOWLIST_W002_EXTRA_PATH_IN_REASON',
    message:
      'Additional backticked paths appear after the entry path. Only the first is extracted. Harmless if they are references; a lost entry if they were meant to be listed.',
    occurrences: extraPathLines
  });
}

// 5. Empty list. Marker present with zero paths is "degrade-closed" in the
//    parser: the guard permits nothing and the run cannot commit anything.
if (paths.length === 0) {
  errors.push({
    code: 'ALLOWLIST_E006_EMPTY_LIST',
    message: 'No paths extracted. An empty allowlist blocks every write the implementation would make.'
  });
}

// 6. Bookkeeping-only. Every path records work rather than performing it, so
//    `strip_bookkeeping_paths` empties the list and the implementation guard
//    can never find a commit that proves the spec was implemented. The old
//    in-prompt linter had no equivalent check and this shape passed it.
const implPaths = paths.filter((p) => !isBookkeeping(p));
if (paths.length > 0 && implPaths.length === 0) {
  errors.push({
    code: 'ALLOWLIST_E007_BOOKKEEPING_ONLY',
    message:
      'Every path is bookkeeping (ai/lifecycle/, ai/features/, ai/diary/, ai/backlog.md). The implementation guard strips these, finds an empty list, and can never confirm the spec was implemented.',
    paths
  });
} else if (paths.length !== implPaths.length) {
  warnings.push({
    code: 'ALLOWLIST_W001_BOOKKEEPING_PRESENT',
    message: 'Bookkeeping paths are stripped by the guard and prove nothing. Harmless, but they are not implementation.',
    paths: paths.filter(isBookkeeping)
  });
}

const ok = errors.length === 0;
emit(
  {
    ok,
    spec: specPath,
    paths,
    implementation_paths: implPaths,
    errors,
    warnings,
    ...(ok ? {} : { remediation: 'Fix the section in place and re-run this script. Do not delete the spec.' })
  },
  ok ? 0 : 1
);
