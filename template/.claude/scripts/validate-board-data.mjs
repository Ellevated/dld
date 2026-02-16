#!/usr/bin/env node
/**
 * Deterministic validator: Board Phase 7 Step 1 (Gate B1).
 * Checks all research files exist and contradiction log is empty.
 *
 * Usage: node validate-board-data.mjs <board_work_dir>
 * Exit: 0 = pass, 1 = fail (reasons on stdout)
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const workDir = process.argv[2];
if (!workDir) {
  console.error('Usage: node validate-board-data.mjs <board_work_dir>');
  process.exit(2);
}

if (!existsSync(workDir)) {
  console.error(`Directory not found: ${workDir}`);
  process.exit(2);
}

const errors = [];

// Check all director research files exist
const directors = ['cpo', 'cfo', 'cmo', 'coo', 'cto', 'devil'];
for (const dir of directors) {
  const researchPath = join(workDir, `research-${dir}.md`);
  if (!existsSync(researchPath)) {
    errors.push(`Missing research file: research-${dir}.md`);
  } else {
    const content = readFileSync(researchPath, 'utf-8');
    if (content.trim().length < 100) {
      errors.push(`Research file too short (<100 chars): research-${dir}.md`);
    }
  }
}

// Check critique files exist
for (const dir of directors) {
  const critiquePath = join(workDir, `critique-${dir}.md`);
  if (!existsSync(critiquePath)) {
    errors.push(`Missing critique file: critique-${dir}.md`);
  }
}

// Check strategies.md exists
if (!existsSync(join(workDir, 'strategies.md'))) {
  errors.push('Missing strategies.md (synthesis output)');
}

// Check founder feedback exists
const feedbackFiles = readdirSync(workDir).filter(f => f.startsWith('founder-feedback'));
if (feedbackFiles.length === 0) {
  errors.push('No founder feedback files found');
}

// Check contradiction log
const contradictionPath = join(workDir, 'contradiction-log.md');
if (existsSync(contradictionPath)) {
  const log = readFileSync(contradictionPath, 'utf-8');
  const unresolved = (log.match(/- \[ \]/g) || []).length;
  if (unresolved > 0) {
    errors.push(`Contradiction log has ${unresolved} unresolved items`);
  }
}

// Check for TBD/TODO in strategies
const strategiesPath = join(workDir, 'strategies.md');
if (existsSync(strategiesPath)) {
  const strategies = readFileSync(strategiesPath, 'utf-8');
  if (/\bTBD\b|\bTODO\b/i.test(strategies)) {
    errors.push('strategies.md contains TBD/TODO markers');
  }
}

if (errors.length > 0) {
  console.log('FAIL: Board data check');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Board data check');
  process.exit(0);
}
