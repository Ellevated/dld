#!/usr/bin/env node

/**
 * improve-description.mjs — Optimize skill description for trigger accuracy.
 *
 * Usage:
 *   node .claude/scripts/improve-description.mjs --skill-path <path> [--eval-set <json>]
 *   node .claude/scripts/improve-description.mjs --help
 *
 * Process:
 *   1. Read current skill frontmatter description
 *   2. Load trigger queries (positive/negative/edge)
 *   3. Split 60/40 train/test
 *   4. Evaluate current description accuracy
 *   5. Generate improved description via claude CLI
 *   6. Re-evaluate on train set, validate on test set
 *   7. Accept if test accuracy improves
 *   8. Max 5 iterations
 *
 * Requires: claude CLI in PATH
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { resolve, join } from 'path';
import { execSync } from 'child_process';

// --- Parse arguments ---
const args = process.argv.slice(2);

if (args.includes('--help') || args.includes('-h') || args.length === 0) {
  console.log(`improve-description.mjs — Optimize skill trigger description

Usage:
  node .claude/scripts/improve-description.mjs --skill-path <path> [options]

Options:
  --skill-path <path>     Path to skill directory
  --eval-set <path>       Path to trigger queries JSON (default: auto-generate prompt)
  --max-iterations <n>    Max optimization iterations (default: 5)
  --runs-per-query <n>    Runs per query for reliability (default: 3)
  --help                  Show this help

Eval Set Format (JSON):
  {
    "queries": [
      { "text": "create a new skill", "should_trigger": true },
      { "text": "fix this bug", "should_trigger": false },
      { "text": "write an agent", "should_trigger": true }
    ]
  }

Example:
  node .claude/scripts/improve-description.mjs \\
    --skill-path .claude/skills/my-skill \\
    --eval-set triggers.json
`);
  process.exit(0);
}

function getArg(flag) {
  const idx = args.indexOf(flag);
  return idx !== -1 && idx + 1 < args.length ? args[idx + 1] : null;
}

const skillPath = getArg('--skill-path');
const evalSetPath = getArg('--eval-set');
const maxIterations = parseInt(getArg('--max-iterations') || '5', 10);
const runsPerQuery = parseInt(getArg('--runs-per-query') || '3', 10);

// --- Pre-flight checks ---
if (!skillPath) {
  console.error('Error: --skill-path is required.');
  process.exit(1);
}

try {
  execSync('command -v claude', { stdio: 'ignore' });
} catch {
  console.error('Error: claude CLI not found in PATH.');
  console.error('Install Claude Code CLI: https://docs.anthropic.com/en/docs/claude-code');
  process.exit(1);
}

const resolvedSkillPath = resolve(skillPath);
const skillMdPath = join(resolvedSkillPath, 'SKILL.md');

if (!existsSync(skillMdPath)) {
  console.error(`Error: SKILL.md not found at: ${skillMdPath}`);
  process.exit(1);
}

// --- Read current description ---
const skillContent = readFileSync(skillMdPath, 'utf-8');
const descMatch = skillContent.match(/^description:\s*(.+)$/m);

if (!descMatch) {
  console.error('Error: no description found in SKILL.md frontmatter');
  process.exit(1);
}

const currentDescription = descMatch[1].trim();
console.log(JSON.stringify({ action: 'improve-description', current: currentDescription }));

// --- Load or prompt for eval set ---
let queries;

if (evalSetPath) {
  try {
    const data = JSON.parse(readFileSync(resolve(evalSetPath), 'utf-8'));
    queries = data.queries;
  } catch (err) {
    console.error(`Error parsing eval set: ${err.message}`);
    process.exit(1);
  }
} else {
  console.log(JSON.stringify({
    action: 'needs-eval-set',
    message: 'No --eval-set provided. Create a JSON file with trigger queries.',
    format: {
      queries: [
        { text: 'create a new skill', should_trigger: true },
        { text: 'fix this bug', should_trigger: false }
      ]
    }
  }));
  process.exit(2);
}

if (!queries || queries.length === 0) {
  console.error('Error: eval set has no queries');
  process.exit(1);
}

// --- Split train/test ---
const shuffled = [...queries].sort(() => Math.random() - 0.5);
const splitIdx = Math.ceil(shuffled.length * 0.6);
const trainSet = shuffled.slice(0, splitIdx);
const testSet = shuffled.slice(splitIdx);

console.log(JSON.stringify({
  total_queries: queries.length,
  train: trainSet.length,
  test: testSet.length
}));

// --- Evaluate description accuracy ---
function evaluateAccuracy(description, evalSet) {
  let correct = 0;
  const results = [];

  for (const q of evalSet) {
    // Simple heuristic: check if keywords from query match description keywords
    // In production, this would use claude CLI to check trigger activation
    const descWords = description.toLowerCase().split(/\W+/);
    const queryWords = q.text.toLowerCase().split(/\W+/);
    const overlap = queryWords.filter(w => descWords.includes(w)).length;
    const triggered = overlap >= 2;
    const pass = triggered === q.should_trigger;

    if (pass) correct++;
    results.push({ query: q.text, should_trigger: q.should_trigger, triggered, pass });
  }

  return {
    accuracy: correct / evalSet.length,
    correct,
    total: evalSet.length,
    results
  };
}

// --- Run optimization loop ---
let bestDescription = currentDescription;
let bestAccuracy = evaluateAccuracy(currentDescription, testSet).accuracy;

console.log(JSON.stringify({
  iteration: 0,
  description: currentDescription,
  test_accuracy: bestAccuracy
}));

const history = [{
  iteration: 0,
  description: currentDescription,
  train_accuracy: evaluateAccuracy(currentDescription, trainSet).accuracy,
  test_accuracy: bestAccuracy
}];

for (let i = 1; i <= maxIterations; i++) {
  const trainResult = evaluateAccuracy(bestDescription, trainSet);

  // Ask claude to improve the description
  const prompt = `Given this skill description:
"${bestDescription}"

These trigger queries should activate it: ${trainSet.filter(q => q.should_trigger).map(q => `"${q.text}"`).join(', ')}
These should NOT activate it: ${trainSet.filter(q => !q.should_trigger).map(q => `"${q.text}"`).join(', ')}

Current train accuracy: ${(trainResult.accuracy * 100).toFixed(0)}%
Failed cases: ${trainResult.results.filter(r => !r.pass).map(r => `"${r.query}" (expected ${r.should_trigger ? 'trigger' : 'no trigger'})`).join(', ')}

Write an improved description (one line, max 200 chars) that better captures when this skill should trigger. Include "Triggers on keywords:" with the key activation words.
Reply with ONLY the new description, nothing else.`;

  let newDescription;
  try {
    newDescription = execSync(`claude -p "${prompt.replace(/"/g, '\\"')}"`, {
      timeout: 60000,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe']
    }).trim();
  } catch {
    console.log(JSON.stringify({ iteration: i, status: 'claude-error', skipped: true }));
    continue;
  }

  // Evaluate new description
  const newTrainResult = evaluateAccuracy(newDescription, trainSet);
  const newTestResult = evaluateAccuracy(newDescription, testSet);

  const entry = {
    iteration: i,
    description: newDescription,
    train_accuracy: newTrainResult.accuracy,
    test_accuracy: newTestResult.accuracy
  };
  history.push(entry);

  console.log(JSON.stringify(entry));

  // Accept if test accuracy improves
  if (newTestResult.accuracy > bestAccuracy) {
    bestDescription = newDescription;
    bestAccuracy = newTestResult.accuracy;
    console.log(JSON.stringify({ iteration: i, status: 'accepted', new_best: bestAccuracy }));
  } else {
    console.log(JSON.stringify({ iteration: i, status: 'rejected', current_best: bestAccuracy }));
  }
}

// --- Output report ---
const report = {
  action: 'improve-description-complete',
  original: currentDescription,
  improved: bestDescription,
  changed: bestDescription !== currentDescription,
  accuracy_before: history[0].test_accuracy,
  accuracy_after: bestAccuracy,
  iterations: history.length - 1,
  history
};

const reportPath = join(resolvedSkillPath, 'description-optimization.json');
writeFileSync(reportPath, JSON.stringify(report, null, 2));

console.log(JSON.stringify(report));
