#!/usr/bin/env node

/**
 * check-prompt-integrity.mjs — static integrity check of the prompt tree.
 *
 * Usage:
 *   node .claude/scripts/check-prompt-integrity.mjs [--tree .claude] [--json]
 *
 * Exit: 0 = clean, 1 = findings, 2 = usage error.
 *
 * Why this exists
 * ---------------
 * Two classes of rot have been found in this tree by hand, twice, months after
 * they appeared:
 *
 *   - Agent prompts that nothing dispatches. Four were found this way. One had
 *     silently drifted into describing a different protocol than the skill it
 *     duplicated, so the copy disagreed with the original and nobody knew.
 *   - Prompts referencing scripts that do not exist in this tree. Seven were
 *     found this way. A missing script does not fail loudly — the agent hits a
 *     shell error and improvises around it, which reads like a bad model day.
 *
 * Both are decidable by grep, which means neither should ever have been found
 * by a person. This runs in seconds and is meant for a nightly routine or a
 * pre-commit sweep, not for a model to reason about.
 *
 * What it deliberately does NOT do: judge prompt quality. That needs a golden
 * dataset and an eval run. This checks only facts — does the referenced file
 * exist, does the declared agent have a caller.
 */

import { readdirSync, readFileSync, existsSync, statSync } from 'fs';
import { join, resolve, relative, dirname } from 'path';

const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h')) {
  console.log(`check-prompt-integrity.mjs — find dead agents and dangling file references

Usage:
  node .claude/scripts/check-prompt-integrity.mjs [options]

Options:
  --tree <dir>   Prompt tree to check (default: .claude). Use template/.claude
                 to check the shipped copy.
  --root <dir>   Repo root that referenced paths resolve against (default: cwd)
  --json         Machine-readable output
  --help         Show this help

Exit: 0 = clean, 1 = findings, 2 = usage error.`);
  process.exit(0);
}

function getArg(flag, fallback) {
  const i = args.indexOf(flag);
  return i !== -1 && i + 1 < args.length ? args[i + 1] : fallback;
}

const repoRoot = resolve(getArg('--root', process.cwd()));
const treeArg = getArg('--tree', '.claude');
const treeRoot = resolve(repoRoot, treeArg);
const asJson = args.includes('--json');

if (!existsSync(treeRoot)) {
  console.error(`Error: prompt tree not found: ${treeRoot}`);
  process.exit(2);
}

// --- Collect markdown files -------------------------------------------------
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry.startsWith('.git')) continue;
    const full = join(dir, entry);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) walk(full, out);
    else if (entry.endsWith('.md')) out.push(full);
  }
  return out;
}

const mdFiles = walk(treeRoot);
const rel = (p) => relative(repoRoot, p).replace(/\\/g, '/');

// Corpus that can contain a dispatch: the prompt tree plus any orchestration
// code. An agent dispatched only from Python is not dead.
const codeRoots = ['scripts', 'src'].map((d) => join(repoRoot, d)).filter(existsSync);

function walkCode(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === '__pycache__' || entry.startsWith('.')) continue;
    const full = join(dir, entry);
    let st;
    try {
      st = statSync(full);
    } catch {
      continue;
    }
    if (st.isDirectory()) walkCode(full, out);
    else if (/\.(py|sh|mjs|js|ts|json|ya?ml)$/.test(entry)) out.push(full);
  }
  return out;
}

const codeFiles = codeRoots.flatMap((d) => walkCode(d));

const corpus = new Map();
for (const f of [...mdFiles, ...codeFiles]) {
  try {
    corpus.set(f, readFileSync(f, 'utf-8'));
  } catch {
    /* unreadable file is not this check's business */
  }
}

// Every executable filename that exists anywhere in the repo. Used to resolve
// bare-name invocations, which are run from inside their own directory.
const knownBasenames = new Set();
for (const f of codeFiles) knownBasenames.add(f.split(/[\\/]/).pop());
for (const dir of [join(treeRoot, 'scripts'), join(treeRoot, 'hooks')]) {
  if (!existsSync(dir)) continue;
  for (const entry of readdirSync(dir)) knownBasenames.add(entry);
}

const findings = [];

// --- Check 1: agents nothing dispatches ------------------------------------
// An agent declares `name:` in frontmatter. A dispatch names it as
// `subagent_type`. No dispatch anywhere = the prompt is not reachable.
const agentsDir = join(treeRoot, 'agents');
if (existsSync(agentsDir)) {
  const agentFiles = walk(agentsDir);

  for (const file of agentFiles) {
    const text = corpus.get(file) ?? '';
    const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!fm) continue; // shared include or reference doc, not an agent
    const nameMatch = fm[1].match(/^name:\s*(\S+)\s*$/m);
    if (!nameMatch) continue;

    const agentName = nameMatch[1].replace(/^["']|["']$/g, '');
    const esc = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

    // Literal dispatch: `subagent_type: bughunt-validator`.
    const literalRe = new RegExp(`subagent_type\\s*[:=]\\s*["']?${esc(agentName)}["']?(?![\\w-])`);

    // Templated dispatch: `subagent_type: bughunt-{persona_type}`, with the
    // concrete names listed nearby ("Persona types: code-reviewer, ..."). Six
    // live agents look dead without this, which would make the check noise.
    // Reachability here means: some file dispatches a template whose prefix
    // matches, AND that same file names this agent's suffix.
    const templateRe = /subagent_type\s*[:=]\s*["']?([\w-]*?)-?\{/g;

    let dispatched = false;
    for (const [other, content] of corpus) {
      if (other === file) continue;
      if (literalRe.test(content)) {
        dispatched = true;
        break;
      }
      for (const t of content.matchAll(templateRe)) {
        const prefix = t[1];
        if (!prefix || !agentName.startsWith(`${prefix}-`)) continue;
        const suffix = agentName.slice(prefix.length + 1);
        if (new RegExp(`(?<![\\w-])${esc(suffix)}(?![\\w-])`).test(content)) {
          dispatched = true;
          break;
        }
      }
      if (dispatched) break;
    }

    if (!dispatched) {
      findings.push({
        kind: 'unreachable_agent',
        severity: 'high',
        file: rel(file),
        detail: `Agent '${agentName}' has no dispatch site. Nothing references subagent_type: ${agentName}.`,
        why: 'An unreachable prompt still gets edited and still drifts, and a second copy of a protocol is a copy that will disagree with the original.'
      });
    }
  }
}

// --- Check 2: scripts a prompt tells an agent to RUN that do not exist -----
// Anchored on an interpreter or ./ rather than on the path shape. That
// distinction is the whole difference between signal and noise: `review.md`
// names `scripts/do_X.py` and `scripts/similar.py` as illustrations inside a
// worked example, while the same file runs `python scripts/check_docs_sync.py`
// — and only the second one is a broken instruction.
const RUN_RE =
  /(?:^|[\s`'"(\[])(?:(?:node|python3?|bash|sh)\s+|\.\/)((?:\.claude\/|template\/|scripts\/|test\/)?[\w./-]+\.(?:mjs|js|py|sh))(?=[\s`'")\],:;]|$)/gm;

const PLACEHOLDER = /[{}<>*$]/;

for (const file of mdFiles) {
  const text = corpus.get(file) ?? '';
  const seen = new Set();

  for (const m of text.matchAll(RUN_RE)) {
    const refPath = m[1];
    if (PLACEHOLDER.test(refPath)) continue;
    if (seen.has(refPath)) continue;
    seen.add(refPath);

    // A prompt inside template/ refers to paths as the downstream project will
    // see them, i.e. relative to that project's root, which is template/ here.
    const bases = rel(file).startsWith('template/')
      ? [join(repoRoot, 'template'), repoRoot]
      : [repoRoot];

    if (bases.some((b) => existsSync(join(b, refPath)))) continue;
    // Relative to the prompt's own directory: `hooks/README.md` documenting
    // `utils.mjs` next to it.
    if (existsSync(join(dirname(file), refPath))) continue;
    // A bare filename is a command run from inside its own directory —
    // `python3 db.py <cmd>` is executed with cwd=scripts/vps. Resolve those by
    // basename anywhere in the repo rather than reporting a file that exists.
    if (!refPath.includes('/') && knownBasenames.has(refPath)) continue;

    findings.push({
      kind: 'dangling_reference',
      severity: 'high',
      file: rel(file),
      detail: `References '${refPath}', which does not exist in this tree.`,
      why: 'A missing script does not fail loudly — the agent hits a shell error and improvises around it.'
    });
  }
}

// --- Check 3: @-includes that resolve to nothing ---------------------------
const INCLUDE_RE = /(?:^|\s)@([\w./-]+\.md)(?=[\s`'")\],:;]|$)/gm;

for (const file of mdFiles) {
  const text = corpus.get(file) ?? '';
  const seen = new Set();

  for (const m of text.matchAll(INCLUDE_RE)) {
    const incPath = m[1];
    if (PLACEHOLDER.test(incPath) || seen.has(incPath)) continue;
    seen.add(incPath);

    const candidates = [
      join(dirname(file), incPath),
      join(treeRoot, 'agents', incPath),
      join(treeRoot, incPath),
      join(repoRoot, incPath)
    ];
    if (candidates.some(existsSync)) continue;

    findings.push({
      kind: 'dangling_include',
      severity: 'high',
      file: rel(file),
      detail: `@-include '${incPath}' resolves to no file.`,
      why: 'The include expands into the prompt at dispatch time; an unresolved one silently drops whatever rules it carried.'
    });
  }
}

// --- Check 4: routing left to the API default ------------------------------
// An agent with no `effort:` inherits `high` by omission. That is not a routing
// decision, it is the absence of one — and the only effort sweep ever measured
// on this tree found the intuitive answer backwards (opus/low beat sonnet/xhigh
// on defect recall, 0.883 vs 0.767). Unstated effort is where that mistake hides.
//
// Haiku is the exception in the other direction: it does not support `effort` at
// all, so a value there is inert and reads as a decision that never took effect.
if (existsSync(agentsDir)) {
  for (const file of walk(agentsDir)) {
    const text = corpus.get(file) ?? '';
    const fm = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
    if (!fm) continue;
    const front = fm[1];
    if (!/^name:\s*\S/m.test(front)) continue;

    const model = front.match(/^model:\s*(\S+)\s*$/m)?.[1]?.replace(/^["']|["']$/g, '');
    const effort = front.match(/^effort:\s*(\S+)\s*$/m)?.[1]?.replace(/^["']|["']$/g, '');

    if (!model) {
      findings.push({
        kind: 'unrouted_agent',
        severity: 'medium',
        file: rel(file),
        detail: 'No `model:` in frontmatter — the agent runs on whatever the caller inherits.',
        why: 'Model routing is meant to live in frontmatter as the single source of truth; an omission routes by accident.'
      });
    }

    if (model === 'haiku' && effort) {
      findings.push({
        kind: 'inert_effort',
        severity: 'low',
        file: rel(file),
        detail: `\`effort: ${effort}\` on a haiku agent has no effect — haiku does not support the effort parameter.`,
        why: 'It reads as a tuning decision that was never actually applied.'
      });
    } else if (model && model !== 'haiku' && !effort) {
      findings.push({
        kind: 'unrouted_agent',
        severity: 'low',
        file: rel(file),
        detail: 'No `effort:` in frontmatter — the API default applies by omission.',
        why: 'An unstated effort is not a decision. Set it explicitly either way, then sweep it against a golden dataset.'
      });
    }
  }
}

// --- Baseline ---------------------------------------------------------------
// Suppress findings that are recorded decisions. Kept next to the script rather
// than inside it so the reason travels with the entry and shows up in review.
const baselinePath = join(repoRoot, '.claude', 'scripts', 'prompt-integrity-baseline.json');
let allow = [];
if (existsSync(baselinePath)) {
  try {
    allow = JSON.parse(readFileSync(baselinePath, 'utf-8')).allow ?? [];
  } catch (err) {
    console.error(`Warning: baseline unreadable (${err.message}); reporting everything.`);
  }
}

const suppressed = [];
const live = findings.filter((f) => {
  const hit = allow.find(
    (a) => a.kind === f.kind && a.file === f.file && f.detail.includes(a.match)
  );
  if (hit) suppressed.push({ ...f, reason: hit.reason });
  return !hit;
});

findings.length = 0;
findings.push(...live);

// --- Report -----------------------------------------------------------------
findings.sort((a, b) => a.file.localeCompare(b.file) || a.kind.localeCompare(b.kind));

if (asJson) {
  console.log(
    JSON.stringify(
      { tree: rel(treeRoot), checked: mdFiles.length, findings, suppressed },
      null,
      2
    )
  );
} else {
  const note = suppressed.length ? ` — ${suppressed.length} baselined` : '';
  console.log(`prompt integrity — ${rel(treeRoot)} (${mdFiles.length} markdown files)${note}\n`);
  if (findings.length === 0) {
    console.log('clean: every agent has a dispatch site, every referenced script exists.');
  } else {
    const byKind = {};
    for (const f of findings) (byKind[f.kind] ??= []).push(f);
    for (const [kind, list] of Object.entries(byKind)) {
      console.log(`${kind} (${list.length})`);
      for (const f of list) console.log(`  ${f.file}\n    ${f.detail}`);
      console.log(`  → ${list[0].why}\n`);
    }
    console.log(`${findings.length} finding(s).`);
  }
}

process.exit(findings.length > 0 ? 1 : 0);
