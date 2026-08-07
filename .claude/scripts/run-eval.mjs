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
import { execFileSync, spawn } from 'child_process';
import { captureArtifacts } from './lib/capture-artifacts.mjs';

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
  --cwd <dir>             Run the skill in this directory (default: current)
  --help                  Show this help

Isolation:
  A skill that writes files writes them into --cwd. Evaluating /spark or
  /autopilot against your live repository will create specs, lifecycle records
  and commits. Point --cwd at a throwaway clone for anything that writes.

Outputs, per eval:
  eval-N-output.txt        what the CLI printed
  eval-N-artifacts/        every file the skill created or modified in --cwd
  eval-N-timing.json       wall clock

  For a skill that writes files, the artifacts are the output and stdout is a
  report about it. Judge the artifacts.

Timeouts:
  claude --print prints only when it finishes, so a killed run yields little
  or no stdout — but the files it already wrote are captured regardless. Size
  the timeout to the skill: a /spark run is three scouts plus synthesis and does
  not fit in 15 minutes. A timed-out eval is reported as "timeout", never as a
  pass.

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
// Where the skill runs. The CLI has no --cwd flag (checked against 2.1.220), so
// this is the child process's working directory, not an argument to claude.
const runCwd = getArg('--cwd') ? resolve(getArg('--cwd')) : process.cwd();

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

// A skill under evaluation may commit and push. /spark claims an ID and pushes;
// /autopilot merges. If --cwd still points at a clone of the real repository,
// that lands in the real repository. Measured: an eval run committed a spec and
// attempted `git push` to the origin it was cloned from — it failed only because
// that origin was a non-bare repo with the branch checked out, which is git
// refusing, not isolation working.
if (!args.includes('--allow-push-to-origin')) {
  let origin = '';
  try {
    origin = execFileSync('git', ['remote', 'get-url', 'origin'], {
      cwd: runCwd, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch { /* no remote, or not a repo — nothing to protect against */ }

  if (origin) {
    console.error(`Error: ${runCwd} still has an 'origin' remote (${origin}).`);
    console.error('A skill that pushes would push there. Detach it first:');
    console.error(`  git -C "${runCwd}" remote remove origin`);
    console.error('Or pass --allow-push-to-origin if writing to that remote is genuinely intended.');
    process.exit(2);
  }
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
  workspace: iterationDir,
  cwd: runCwd
}));

/**
 * Run the CLI, keeping whatever it emitted even if we have to kill it.
 *
 * `execFileSync` discarded everything on timeout — `spawnSync` sets `stdout` to
 * null for ETIMEDOUT, so a run that was killed at 15 minutes wrote a 26-byte
 * file reading `spawnSync claude ETIMEDOUT` and the work was unrecoverable.
 */
function runCli(args, { cwd, timeout }) {
  return new Promise((res) => {
    const chunks = [];
    const child = spawn('claude', args, { cwd, stdio: ['ignore', 'pipe', 'pipe'] });
    let timedOut = false;

    const timer = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => child.kill('SIGKILL'), 5000).unref();
    }, timeout);

    child.stdout.on('data', (d) => chunks.push(d));
    child.stderr.on('data', (d) => chunks.push(d));

    const finish = (code, err) => {
      clearTimeout(timer);
      const text = Buffer.concat(chunks).toString('utf-8');
      res({ output: err ? `${text}\n${err.message}` : text, code, timedOut });
    };
    child.on('close', (code) => finish(code ?? 1));
    child.on('error', (err) => finish(-1, err));
  });
}


// --- Run each eval ---
const results = [];

for (const eval_ of evals) {
  const evalId = eval_.id;
  const prompt = eval_.prompt;
  const outputFile = join(iterationDir, `eval-${evalId}-output.txt`);
  const timingFile = join(iterationDir, `eval-${evalId}-timing.json`);

  console.log(JSON.stringify({ eval_id: evalId, status: 'running', prompt: prompt.slice(0, 80) }));

  // Anchor for artifact capture: anything committed after this is the skill's work.
  let baseRef = null;
  try {
    baseRef = execFileSync('git', ['rev-parse', 'HEAD'], {
      cwd: runCwd, encoding: 'utf-8', stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch { /* not a git repo — working tree capture only */ }

  const startTime = Date.now();

  // Invoke the skill as a slash command. There is no `--skill` flag — the CLI
  // rejects it outright ("unknown option '--skill'"), so the previous form
  // failed every eval and the run still reported files on disk.
  // `--setting-sources=project` is what makes .claude/skills/ discoverable at
  // all; without it the prompt reaches the model as literal text.
  // Args are passed as argv, never through a shell: the prompt is eval data, and
  // a backtick or `$(` in it would otherwise run.
  const run = await runCli(
    ['--print', '--setting-sources=project', '-p', `/${skillCommand} ${prompt}`],
    { cwd: runCwd, timeout }
  );

  let output = run.output;
  if (run.timedOut) {
    output = `TIMEOUT after ${timeout}ms — process killed, partial output below.\n` +
      `The skill may still have written files; see artifacts/.\n\n${output}`;
  }
  const success = run.code === 0 && !run.timedOut;

  const elapsed = Date.now() - startTime;

  // Save output
  writeFileSync(outputFile, output);

  // Capture what the skill wrote — for a file-writing skill this is the real
  // output, and it survives a timeout that leaves stdout empty.
  const artifactDir = join(iterationDir, `eval-${evalId}-artifacts`);
  mkdirSync(artifactDir, { recursive: true });
  const artifacts = captureArtifacts(runCwd, artifactDir, baseRef);

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
    timed_out: run.timedOut,
    exit_code: run.code,
    artifacts: artifacts.captured,
    artifacts_note: artifacts.note,
    elapsed_ms: elapsed,
    output_file: outputFile,
    output_length: output.length
  };
  results.push(result);

  console.log(JSON.stringify({
    eval_id: evalId,
    status: success ? 'done' : (run.timedOut ? 'timeout' : 'failed'),
    elapsed_ms: elapsed,
    artifacts: artifacts.captured.length
  }));
}

// --- Summary ---
const summary = {
  skill_name: skillName,
  iteration,
  total: evals.length,
  succeeded: results.filter(r => r.success).length,
  failed: results.filter(r => !r.success).length,
  timed_out: results.filter(r => r.timed_out).length,
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
