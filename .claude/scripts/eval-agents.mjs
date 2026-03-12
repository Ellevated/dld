#!/usr/bin/env node

/**
 * eval-agents.mjs — Scan test/agents/ for golden datasets, return eval task list.
 *
 * Usage:
 *   node .claude/scripts/eval-agents.mjs              # all agents
 *   node .claude/scripts/eval-agents.mjs devil         # single agent
 *   node .claude/scripts/eval-agents.mjs --report      # last report path
 *
 * Output: JSON array of eval task objects.
 *
 * Directory structure expected:
 *   test/agents/{agent}/
 *     config.json
 *     golden-NNN.input.md
 *     golden-NNN.output.md    (reference, for human review)
 *     golden-NNN.rubric.md    (scoring rubric for eval-judge)
 */

import { readdirSync, readFileSync, existsSync, statSync } from 'fs';
import { join, resolve } from 'path';

const args = process.argv.slice(2);
const reportFlag = args.includes('--report');
const agentFilter = args.find(a => !a.startsWith('--'));

// Find project root (walk up to find CLAUDE.md)
let root = process.cwd();
while (root !== '/' && !existsSync(join(root, 'CLAUDE.md'))) {
  root = resolve(root, '..');
}

const agentsDir = join(root, 'test', 'agents');
const reportPath = join(agentsDir, 'eval-report.md');

if (reportFlag) {
  console.log(JSON.stringify({ report_path: reportPath, exists: existsSync(reportPath) }));
  process.exit(0);
}

if (!existsSync(agentsDir)) {
  console.log(JSON.stringify([]));
  process.exit(0);
}

const tasks = [];

// Scan agent directories
let dirs;
try {
  dirs = readdirSync(agentsDir).filter(d => {
    const full = join(agentsDir, d);
    return statSync(full).isDirectory() && d !== 'node_modules';
  });
} catch {
  console.log(JSON.stringify([]));
  process.exit(0);
}

// Apply agent filter
if (agentFilter) {
  dirs = dirs.filter(d => d === agentFilter);
}

for (const dir of dirs) {
  const agentPath = join(agentsDir, dir);
  const configPath = join(agentPath, 'config.json');

  if (!existsSync(configPath)) continue;

  let config;
  try {
    config = JSON.parse(readFileSync(configPath, 'utf-8'));
  } catch {
    continue;
  }

  // Find golden pairs: golden-NNN.input.md
  const files = readdirSync(agentPath);
  const goldenInputs = files
    .filter(f => /^golden-\d+\.input\.md$/.test(f))
    .sort();

  for (const inputFile of goldenInputs) {
    const num = inputFile.match(/golden-(\d+)/)[1];
    const rubricFile = `golden-${num}.rubric.md`;
    const outputFile = `golden-${num}.output.md`;

    // Rubric is required, output is optional (for human reference)
    if (!existsSync(join(agentPath, rubricFile))) continue;

    const inputPath = join(agentPath, inputFile);
    const rubricPath = join(agentPath, rubricFile);
    const outputPath = join(agentPath, outputFile);

    tasks.push({
      agent: config.agent || dir,
      agent_path: config.agent_path || `.claude/agents/${dir}.md`,
      subagent_type: config.subagent_type || dir,
      description: config.description || dir,
      golden_id: `golden-${num}`,
      input_path: inputPath,
      rubric_path: rubricPath,
      output_path: existsSync(outputPath) ? outputPath : null,
      threshold: config.threshold || 0.7
    });
  }
}

console.log(JSON.stringify(tasks, null, 2));
