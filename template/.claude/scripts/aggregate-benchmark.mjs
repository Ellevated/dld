#!/usr/bin/env node

/**
 * aggregate-benchmark.mjs — Aggregate multiple eval runs into benchmark report.
 *
 * Usage:
 *   node .claude/scripts/aggregate-benchmark.mjs --workspace <path>
 *   node .claude/scripts/aggregate-benchmark.mjs --help
 *
 * Reads iteration-N directories in workspace, aggregates grading.json and
 * timing data, computes statistical summaries, writes benchmark.json + benchmark.md.
 */

import { readFileSync, writeFileSync, readdirSync, existsSync } from 'fs';
import { resolve, join } from 'path';

// --- Parse arguments ---
const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h') || args.length === 0) {
  console.log(`aggregate-benchmark.mjs — Aggregate eval runs into benchmark report

Usage:
  node .claude/scripts/aggregate-benchmark.mjs --workspace <path>

Options:
  --workspace <path>      Path to eval workspace (contains iteration-N dirs)
  --help                  Show this help

Expects:
  workspace/
  ├── iteration-1/
  │   ├── eval-1-output.txt
  │   ├── eval-1-timing.json
  │   └── run-summary.json
  ├── iteration-2/
  │   └── ...
  └── iteration-3/
      └── ...

Output:
  workspace/benchmark.json  — Statistical summary
  workspace/benchmark.md    — Human-readable report
`);
  process.exit(0);
}

function getArg(flag) {
  const idx = args.indexOf(flag);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : null;
}

const workspacePath = getArg('--workspace');

if (!workspacePath) {
  console.error('Error: --workspace is required.');
  process.exit(1);
}

const resolvedWorkspace = resolve(workspacePath);

if (!existsSync(resolvedWorkspace)) {
  console.error(`Error: workspace not found: ${resolvedWorkspace}`);
  process.exit(1);
}

// --- Find iteration directories ---
const entries = readdirSync(resolvedWorkspace, { withFileTypes: true });
const iterationDirs = entries
  .filter(e => e.isDirectory() && e.name.startsWith('iteration-'))
  .map(e => e.name)
  .sort((a, b) => {
    const numA = parseInt(a.split('-')[1], 10);
    const numB = parseInt(b.split('-')[1], 10);
    return numA - numB;
  });

if (iterationDirs.length === 0) {
  console.error('Error: no iteration-N directories found in workspace');
  process.exit(1);
}

console.log(JSON.stringify({ action: 'aggregate-benchmark', iterations: iterationDirs.length }));

// --- Collect data from all iterations ---
const allSummaries = [];
const allTimings = [];

for (const dir of iterationDirs) {
  const iterPath = join(resolvedWorkspace, dir);

  // Read run summary
  const summaryPath = join(iterPath, 'run-summary.json');
  if (existsSync(summaryPath)) {
    try {
      allSummaries.push(JSON.parse(readFileSync(summaryPath, 'utf-8')));
    } catch { /* skip corrupt files */ }
  }

  // Read timing files
  const files = readdirSync(iterPath);
  for (const f of files) {
    if (f.endsWith('-timing.json')) {
      try {
        allTimings.push(JSON.parse(readFileSync(join(iterPath, f), 'utf-8')));
      } catch { /* skip corrupt files */ }
    }
  }
}

// --- Statistical helpers ---
function stats(values) {
  if (values.length === 0) return { mean: 0, stddev: 0, min: 0, max: 0 };
  const n = values.length;
  const mean = values.reduce((a, b) => a + b, 0) / n;
  const variance = values.reduce((a, b) => a + (b - mean) ** 2, 0) / n;
  return {
    mean: Math.round(mean * 1000) / 1000,
    stddev: Math.round(Math.sqrt(variance) * 1000) / 1000,
    min: Math.min(...values),
    max: Math.max(...values)
  };
}

// --- Compute aggregates ---
const passRates = allSummaries.map(s => s.succeeded / s.total);
const tokenCounts = allTimings
  .filter(t => t.executor?.tokens_input != null)
  .map(t => (t.executor.tokens_input || 0) + (t.executor.tokens_output || 0));
const elapsedTimes = allTimings
  .filter(t => t.executor?.elapsed_ms != null)
  .map(t => t.executor.elapsed_ms);

// Per-eval aggregation
const evalResults = {};
for (const summary of allSummaries) {
  for (const result of (summary.results || [])) {
    const id = result.eval_id;
    if (!evalResults[id]) evalResults[id] = { successes: 0, total: 0, scores: [] };
    evalResults[id].total++;
    if (result.success) evalResults[id].successes++;
  }
}

const perEval = Object.entries(evalResults).map(([id, data]) => ({
  eval_id: parseInt(id, 10),
  pass_rate: Math.round((data.successes / data.total) * 1000) / 1000,
  runs: data.total
}));

// --- Build benchmark result ---
const skillName = allSummaries[0]?.skill_name || 'unknown';

const benchmark = {
  skill_name: skillName,
  iterations: iterationDirs.length,
  timestamp: new Date().toISOString(),
  summary: {
    pass_rate: stats(passRates),
    tokens: tokenCounts.length > 0 ? stats(tokenCounts) : null,
    elapsed_ms: elapsedTimes.length > 0 ? stats(elapsedTimes) : null
  },
  per_eval: perEval
};

// --- Write benchmark.json ---
const benchmarkPath = join(resolvedWorkspace, 'benchmark.json');
writeFileSync(benchmarkPath, JSON.stringify(benchmark, null, 2));

// --- Write benchmark.md ---
const pr = benchmark.summary.pass_rate;
const md = `# Benchmark — ${skillName}

**Generated:** ${benchmark.timestamp}
**Iterations:** ${benchmark.iterations}

## Summary

| Metric | Mean | StdDev | Min | Max |
|--------|------|--------|-----|-----|
| Pass rate | ${(pr.mean * 100).toFixed(1)}% | ±${(pr.stddev * 100).toFixed(1)}% | ${(pr.min * 100).toFixed(1)}% | ${(pr.max * 100).toFixed(1)}% |
${benchmark.summary.tokens ? `| Tokens | ${benchmark.summary.tokens.mean} | ±${benchmark.summary.tokens.stddev} | ${benchmark.summary.tokens.min} | ${benchmark.summary.tokens.max} |` : ''}
${benchmark.summary.elapsed_ms ? `| Time (ms) | ${benchmark.summary.elapsed_ms.mean} | ±${benchmark.summary.elapsed_ms.stddev} | ${benchmark.summary.elapsed_ms.min} | ${benchmark.summary.elapsed_ms.max} |` : ''}

## Per-Eval Results

| Eval ID | Pass Rate | Runs |
|---------|-----------|------|
${perEval.map(e => `| ${e.eval_id} | ${(e.pass_rate * 100).toFixed(1)}% | ${e.runs} |`).join('\n')}
`;

const mdPath = join(resolvedWorkspace, 'benchmark.md');
writeFileSync(mdPath, md);

// --- Output ---
console.log(JSON.stringify({
  action: 'aggregate-benchmark-complete',
  iterations: benchmark.iterations,
  pass_rate_mean: pr.mean,
  pass_rate_stddev: pr.stddev,
  output_json: benchmarkPath,
  output_md: mdPath
}));
