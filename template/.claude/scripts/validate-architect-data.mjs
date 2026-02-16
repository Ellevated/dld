#!/usr/bin/env node
/**
 * Deterministic validator: Architect Phase 7 Step 1 (Gate A1).
 * Checks all research files exist and contradiction log is empty.
 *
 * Usage: node validate-architect-data.mjs <architect_work_dir>
 * Exit: 0 = pass, 1 = fail (reasons on stdout)
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import { join } from 'path';

const workDir = process.argv[2];
if (!workDir) {
  console.error('Usage: node validate-architect-data.mjs <architect_work_dir>');
  process.exit(2);
}

if (!existsSync(workDir)) {
  console.error(`Directory not found: ${workDir}`);
  process.exit(2);
}

const errors = [];

// Check all persona research files exist
const personas = ['domain', 'data', 'ops', 'security', 'evolutionary', 'dx', 'llm'];
for (const p of personas) {
  const researchPath = join(workDir, `research-${p}.md`);
  if (!existsSync(researchPath)) {
    errors.push(`Missing research file: research-${p}.md`);
  } else {
    const content = readFileSync(researchPath, 'utf-8');
    if (content.trim().length < 100) {
      errors.push(`Research file too short (<100 chars): research-${p}.md`);
    }
  }
}

// Check critique files exist
for (const p of personas) {
  const critiquePath = join(workDir, `critique-${p}.md`);
  if (!existsSync(critiquePath)) {
    errors.push(`Missing critique file: critique-${p}.md`);
  }
}

// Check architectures.md exists
if (!existsSync(join(workDir, 'architectures.md'))) {
  errors.push('Missing architectures.md (synthesis output)');
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

// Check business blueprint reference
if (!existsSync('ai/blueprint/business-blueprint.md')) {
  errors.push('Business Blueprint not found (Board must run first)');
}

// Check blueprint files for completeness
const blueprintDir = join(workDir, 'output');
if (existsSync(blueprintDir)) {
  const required = ['domain-map.md', 'data-architecture.md', 'api-contracts.md', 'cross-cutting.md'];
  for (const f of required) {
    if (!existsSync(join(blueprintDir, f))) {
      errors.push(`Missing blueprint file: ${f}`);
    }
  }
}

if (errors.length > 0) {
  console.log('FAIL: Architect data check');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Architect data check');
  process.exit(0);
}
