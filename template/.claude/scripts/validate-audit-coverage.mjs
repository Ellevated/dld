#!/usr/bin/env node
/**
 * Coverage gate: checks that audit personas covered files from inventory.
 *
 * Usage: node validate-audit-coverage.mjs <inventory_json> <reports_dir>
 * Exit: 0 = pass (>= 80%), 1 = fail (< 80%), 2 = usage error
 *
 * Reads codebase-inventory.json and all report-*.md files.
 * Checks every file from inventory is mentioned in at least one report.
 */

import { readFileSync, readdirSync, existsSync } from 'fs';
import { join, basename } from 'path';

const inventoryPath = process.argv[2];
const reportsDir = process.argv[3];

if (!inventoryPath || !reportsDir) {
  console.error('Usage: node validate-audit-coverage.mjs <inventory.json> <reports_dir>');
  process.exit(2);
}

if (!existsSync(inventoryPath)) {
  console.error(`Inventory file not found: ${inventoryPath}`);
  process.exit(2);
}

if (!existsSync(reportsDir)) {
  console.error(`Reports directory not found: ${reportsDir}`);
  process.exit(2);
}

// Read inventory
const inventory = JSON.parse(readFileSync(inventoryPath, 'utf-8'));
const inventoryFiles = inventory.files
  .filter(f => f.language && !['markdown', 'json', 'yaml', 'toml'].includes(f.language))
  .map(f => f.path);

// Read all persona report files
const reportFiles = readdirSync(reportsDir)
  .filter(f => f.startsWith('report-') && f.endsWith('.md'));

if (reportFiles.length === 0) {
  console.log('FAIL: No persona report files found in ' + reportsDir);
  process.exit(1);
}

// Collect all file mentions across reports
const mentionedFiles = new Set();
for (const rf of reportFiles) {
  const content = readFileSync(join(reportsDir, rf), 'utf-8');
  for (const filePath of inventoryFiles) {
    // Check if file path (or its basename) is mentioned in the report
    if (content.includes(filePath) || content.includes(basename(filePath))) {
      mentionedFiles.add(filePath);
    }
  }
}

// Calculate coverage
const total = inventoryFiles.length;
const covered = mentionedFiles.size;
const missed = inventoryFiles.filter(f => !mentionedFiles.has(f));
const coverage = total > 0 ? (covered / total * 100).toFixed(1) : 100;

console.log(`Coverage: ${covered}/${total} files (${coverage}%)`);
console.log(`Reports analyzed: ${reportFiles.length}`);

if (missed.length > 0) {
  console.log(`\nMissed files (${missed.length}):`);
  // Group by directory for readability
  const byDir = {};
  for (const f of missed) {
    const dir = f.includes('/') ? f.substring(0, f.lastIndexOf('/')) : '.';
    if (!byDir[dir]) byDir[dir] = [];
    byDir[dir].push(f);
  }
  for (const [dir, files] of Object.entries(byDir).sort()) {
    console.log(`  ${dir}/`);
    for (const f of files) console.log(`    - ${basename(f)}`);
  }
}

const THRESHOLD = 80;
if (parseFloat(coverage) >= THRESHOLD) {
  console.log(`\nPASS: Coverage >= ${THRESHOLD}%`);
  process.exit(0);
} else {
  console.log(`\nFAIL: Coverage < ${THRESHOLD}% (threshold: ${THRESHOLD}%)`);
  process.exit(1);
}
