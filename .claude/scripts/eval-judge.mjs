#!/usr/bin/env node

/**
 * eval-judge.mjs — Parse Eval Criteria from spec, extract entries by type.
 *
 * Usage:
 *   node .claude/scripts/eval-judge.mjs <spec_path> --type llm-judge
 *   node .claude/scripts/eval-judge.mjs <spec_path> --type deterministic
 *   node .claude/scripts/eval-judge.mjs <spec_path>  # all types
 *
 * Output: JSON array of eval criteria objects.
 */

import { readFileSync } from 'fs';
import { resolve } from 'path';

const args = process.argv.slice(2);
const specPath = args[0];
const typeFlag = args.indexOf('--type');
const filterType = typeFlag !== -1 ? args[typeFlag + 1] : null;

if (!specPath) {
  console.error('Usage: node eval-judge.mjs <spec_path> [--type llm-judge|deterministic|integration]');
  process.exit(1);
}

const fullPath = resolve(specPath);
let content;
try {
  content = readFileSync(fullPath, 'utf-8');
} catch (err) {
  console.error(`Cannot read file: ${fullPath}`);
  process.exit(1);
}

// Extract ## Eval Criteria section
const evalMatch = content.match(/## Eval Criteria[\s\S]*?(?=\n## [^#]|\s*$)/);
if (!evalMatch) {
  console.log(JSON.stringify([]));
  process.exit(0);
}

const section = evalMatch[0];
const criteria = [];

// Parse table rows with EC-N pattern
// Supports both deterministic/integration tables (| EC-N | scenario | input | expected | type | source | priority |)
// and LLM-Judge tables (| EC-N | input | rubric | threshold | source | priority |)
const lines = section.split('\n');

for (const line of lines) {
  const trimmed = line.trim();
  if (!trimmed.startsWith('|')) continue;

  const ecMatch = trimmed.match(/^\|\s*EC-(\d+)\s*\|/);
  if (!ecMatch) continue;

  const cells = trimmed.split('|').map(c => c.trim()).filter(Boolean);
  if (cells.length < 4) continue;

  const id = cells[0]; // EC-N

  // Detect table type by checking if "threshold" column looks like a number (0.X)
  // LLM-Judge table: | EC-N | input | rubric | threshold | source | priority |
  // Deterministic table: | EC-N | scenario | input | expected | type | source | priority |

  let entry;

  // Check if any cell matches threshold pattern (0.X or 1.0)
  const hasThreshold = cells.some(c => /^0\.\d+$|^1\.0$/.test(c));

  if (hasThreshold) {
    // LLM-Judge format: | ID | Input | Rubric | Threshold | Source | Priority |
    entry = {
      id,
      type: 'llm-judge',
      input: cells[1] || '',
      rubric: cells[2] || '',
      threshold: parseFloat(cells[3]) || 0.7,
      source: cells[4] || '',
      priority: cells[5] || ''
    };
  } else if (cells.length >= 6) {
    // Deterministic/Integration: | ID | Scenario | Input | Expected | Type | Source | Priority |
    const typeCell = cells[4] || '';
    entry = {
      id,
      type: typeCell.toLowerCase(),
      scenario: cells[1] || '',
      input: cells[2] || '',
      expected: cells[3] || '',
      source: cells[5] || '',
      priority: cells[6] || ''
    };
  } else {
    continue;
  }

  // Apply type filter
  if (filterType && entry.type !== filterType) continue;

  criteria.push(entry);
}

console.log(JSON.stringify(criteria, null, 2));
