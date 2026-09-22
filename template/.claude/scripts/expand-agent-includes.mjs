#!/usr/bin/env node

/**
 * expand-agent-includes.mjs — write `_shared/` modules into the agent prompts that name them.
 *
 * Usage:
 *   node .claude/scripts/expand-agent-includes.mjs [--tree .claude] [--check]
 *
 * Exit: 0 = done (with --check: nothing to do), 1 = --check found a raw `@` line or a
 * stale block, 2 = usage error or a missing shared module.
 *
 * Claude Code does not expand `@path` lines inside agent files — see
 * lib/agent-includes.mjs for the measurement. Run this after editing anything in
 * `agents/_shared/`, in both trees:
 *
 *   node .claude/scripts/expand-agent-includes.mjs --tree .claude
 *   node .claude/scripts/expand-agent-includes.mjs --tree template/.claude
 */

import { existsSync, readdirSync, readFileSync, statSync, writeFileSync } from 'fs';
import { join, relative, resolve } from 'path';
import { expandText } from './lib/agent-includes.mjs';

const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h')) {
  console.log(`expand-agent-includes.mjs — inline agents/_shared/ modules into agent prompts

Options:
  --tree <dir>   Prompt tree (default: .claude)
  --check        Change nothing; exit 1 if any agent still has a raw @ line or a stale block
  --help         Show this help`);
  process.exit(0);
}

const treeIdx = args.indexOf('--tree');
const treeRoot = resolve(treeIdx !== -1 && args[treeIdx + 1] ? args[treeIdx + 1] : '.claude');
const check = args.includes('--check');
const agentsDir = join(treeRoot, 'agents');
const sharedDir = join(agentsDir, '_shared');

if (!existsSync(agentsDir) || !existsSync(sharedDir)) {
  console.error(`Error: ${agentsDir} or its _shared/ not found`);
  process.exit(2);
}

function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry !== '_shared') walk(full, out);
    } else if (entry.endsWith('.md')) {
      out.push(full);
    }
  }
  return out;
}

let pending = 0;
let written = 0;
for (const file of walk(agentsDir)) {
  const before = readFileSync(file, 'utf-8');
  let result;
  try {
    result = expandText(before, sharedDir);
  } catch (err) {
    console.error(`Error in ${relative(process.cwd(), file)}: ${err.message}`);
    process.exit(2);
  }
  if (!result.changed) continue;

  const rel = relative(process.cwd(), file).replace(/\\/g, '/');
  const why = [
    result.raw.length ? `raw @: ${result.raw.join(', ')}` : '',
    result.stale.length ? `stale: ${result.stale.join(', ')}` : '',
    result.dropped.length ? `removed: ${result.dropped.join(', ')}` : ''
  ]
    .filter(Boolean)
    .join('; ');
  pending++;
  if (check) {
    console.log(`${rel} — ${why}`);
  } else {
    writeFileSync(file, result.text);
    written++;
    console.log(`expanded ${rel} (${why})`);
  }
}

if (check) {
  console.log(
    pending
      ? `\n${pending} agent file(s) out of date — run without --check.`
      : 'clean: every shared module is inlined and current.'
  );
  process.exit(pending ? 1 : 0);
}
console.log(`\n${written} agent file(s) rewritten.`);
