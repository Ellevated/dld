#!/usr/bin/env node

/**
 * run-eval.mjs — Run a skill against test prompts and capture outputs.
 *
 * Usage:
 *   node .claude/scripts/run-eval.mjs --skill-path <path> --evals-path <path> [--workspace <dir>]
 *   node .claude/scripts/run-eval.mjs --help
 *
 * Requires: claude CLI in PATH
 *
 * Output: Captured outputs in workspace directory, one file per eval.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { resolve, join, basename } from 'path';
import { execFileSync } from 'child_process';

// --- Parse arguments ---
const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h') || args.length === 0) {
  console.log(`run-eval.mjs — Run a skill against test prompts

Usage:
  node .claude/scripts/run-eval.mjs --skill-path <path> --evals-path <path> [options]

Options:
  --skill-path <path>     Path to skill directory (e.g., .claude/skills/my-skill)
  --evals-path <path>     Path to evals.json file
  --workspace <dir>       Output directory (default: .claude/eval-workspace/<skill-name>)
  --iteration <n>         Iteration number for benchmark mode (default: 1)
  --timeout <ms>          Timeout per eval in milliseconds (default: 120000)
  --help                  Show this help

Example:
  node .claude/scripts/run-eval.mjs \\
    --skill-path .claude/skills/my-skill \\
    --evals-path .claude/skills/my-skill/evals/evals.json
`);
  process.exit(0);
}

function getArg(flag) {
  const idx = args.indexOf(flag);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : null;
}

const skillPath = getArg('--skill-path');
const evalsPath = getArg('--evals-path');
const iteration = parseInt(getArg('--iteration') || '1', 10);
const timeout = parseInt(getArg('--timeout') || '120000', 10);

// --- Pre-flight checks ---
if (!skillPath || !evalsPath) {
  console.error('Error: --skill-path and --evals-path are required.');
  console.error('Run with --help for usage.');
  process.exit(1);
}

try {
  // Run the binary rather than probing with `command -v`: that is a POSIX shell
  // builtin, and execSync on Windows runs through cmd.exe where it does not exist.
  execFileSync('claude', ['--version'], { stdio: 'ignore' });
} catch {
  console.error('Error: claude CLI not found in PATH.');
  console.error('Install Claude Code CLI: https://docs.anthropic.com/en/docs/claude-code');
  process.exit(1);
}

const resolvedSkillPath = resolve(skillPath);
const resolvedEvalsPath = resolve(evalsPath);

if (!existsSync(resolvedEvalsPath)) {
  console.error(`Error: evals file not found: ${resolvedEvalsPath}`);
  process.exit(1);
}

if (!existsSync(resolvedSkillPath)) {
  console.error(`Error: skill directory not found: ${resolvedSkillPath}`);
  process.exit(1);
}

// --- Load evals ---
let evalsData;
try {
  evalsData = JSON.parse(readFileSync(resolvedEvalsPath, 'utf-8'));
} catch (err) {
  console.error(`Error: cannot parse evals file: ${err.message}`);
  process.exit(1);
}

const skillName = evalsData.skill_name || basename(resolvedSkillPath);
const evals = evalsData.evals || [];

// The slash command the CLI resolves is the skill's frontmatter `name:`, which
// need not match `skill_name` in evals.json (that one is a display label).
// Directory basename is the fallback the CLI itself falls back to.
function slashName(skillDir) {
  try {
    const md = readFileSync(join(skillDir, 'SKILL.md'), 'utf-8');
    const m = md.match(/^name:\s*(\S+)\s*$/m);
    if (m) return m[1];
  } catch { /* fall through to basename */ }
  return basename(skillDir);
}

const skillCommand = slashName(resolvedSkillPath);

if (evals.length === 0) {
  console.error('Error: no evals found in evals.json');
  process.exit(1);
}

// --- Setup workspace ---
const defaultWorkspace = getArg('--workspace') || join('.claude', 'eval-workspace', skillName);
const workspaceDir = resolve(defaultWorkspace);
const iterationDir = join(workspaceDir, `iteration-${iteration}`);
mkdirSync(iterationDir, { recursive: true });

console.log(JSON.stringify({
  action: 'run-eval',
  skill: skillName,
  command: `/${skillCommand}`,
  evals_count: evals.length,
  iteration,
  workspace: iterationDir
}));

// --- Run each eval ---
const results = [];

for (const eval_ of evals) {
  const evalId = eval_.id;
  const prompt = eval_.prompt;
  const outputFile = join(iterationDir, `eval-${evalId}-output.txt`);
  const timingFile = join(iterationDir, `eval-${evalId}-timing.json`);

  console.log(JSON.stringify({ eval_id: evalId, status: 'running', prompt: prompt.slice(0, 80) }));

  const startTime = Date.now();
  let output = '';
  let success = false;

  try {
    // Invoke the skill as a slash command. There is no `--skill` flag — the CLI
    // rejects it outright ("unknown option '--skill'"), so the previous form
    // failed every eval and the run still reported files on disk.
    // `--setting-sources=project` is what makes .claude/skills/ discoverable at
    // all; without it the prompt reaches the model as literal text.
    // execFileSync, not execSync: the prompt is eval data and must never be
    // pasted into a shell string, where a backtick or `$(` would run.
    output = execFileSync(
      'claude',
      ['--print', '--setting-sources=project', '-p', `/${skillCommand} ${prompt}`],
      {
        timeout,
        encoding: 'utf-8',
        maxBuffer: 10 * 1024 * 1024, // 10MB
        // stdin closed: the CLI otherwise waits ~3s for piped input it never gets
        stdio: ['ignore', 'pipe', 'pipe']
      }
    );
    success = true;
  } catch (err) {
    output = err.stdout || err.message || 'Execution failed';
    if (err.killed) {
      output = `TIMEOUT after ${timeout}ms\n\n${output}`;
    }
  }

  const elapsed = Date.now() - startTime;

  // Save output
  writeFileSync(outputFile, output);

  // Save timing
  const timing = {
    eval_id: evalId,
    iteration,
    executor: {
      start: new Date(startTime).toISOString(),
      end: new Date(startTime + elapsed).toISOString(),
      elapsed_ms: elapsed
    }
  };
  writeFileSync(timingFile, JSON.stringify(timing, null, 2));

  const result = {
    eval_id: evalId,
    success,
    elapsed_ms: elapsed,
    output_file: outputFile,
    output_length: output.length
  };
  results.push(result);

  console.log(JSON.stringify({ eval_id: evalId, status: success ? 'done' : 'failed', elapsed_ms: elapsed }));
}

// --- Summary ---
const summary = {
  skill_name: skillName,
  iteration,
  total: evals.length,
  succeeded: results.filter(r => r.success).length,
  failed: results.filter(r => !r.success).length,
  results,
  workspace: iterationDir
};

const summaryFile = join(iterationDir, 'run-summary.json');
writeFileSync(summaryFile, JSON.stringify(summary, null, 2));

console.log(JSON.stringify({
  action: 'run-eval-complete',
  total: summary.total,
  succeeded: summary.succeeded,
  failed: summary.failed,
  workspace: iterationDir
}));
