#!/usr/bin/env node
/**
 * Deterministic validator: checks spec file structure (mandatory sections).
 * Used by Spark Phase 6 (Gate S1) and Autopilot spec-reviewer pre-check.
 *
 * Usage: node validate-spec-structure.mjs <spec_file>
 * Exit: 0 = pass, 1 = fail (reasons on stdout)
 */

import { readFileSync } from 'fs';

const specPath = process.argv[2];
if (!specPath) {
  console.error('Usage: node validate-spec-structure.mjs <spec_file>');
  process.exit(2);
}

let content;
try {
  content = readFileSync(specPath, 'utf-8');
} catch {
  console.error(`Cannot read file: ${specPath}`);
  process.exit(2);
}

const errors = [];

// Mandatory sections for feature specs
const mandatorySections = [
  { pattern: /^## Why/m, name: 'Why' },
  { pattern: /^## Scope/m, name: 'Scope' },
  { pattern: /^## Allowed Files/m, name: 'Allowed Files' },
  { pattern: /^## Implementation Plan/m, name: 'Implementation Plan' },
  { pattern: /^## Definition of Done/m, name: 'Definition of Done' },
];

for (const section of mandatorySections) {
  if (!section.pattern.test(content)) {
    errors.push(`Missing mandatory section: ## ${section.name}`);
  }
}

// Check for forbidden markers
const forbidden = [
  { pattern: /\bTBD\b/i, name: 'TBD' },
  { pattern: /\bTODO\b/i, name: 'TODO' },
  { pattern: /\blater\b/i, name: '"later"' },
];

for (const marker of forbidden) {
  const match = content.match(marker.pattern);
  if (match) {
    const lineNum = content.substring(0, match.index).split('\n').length;
    errors.push(`Forbidden marker "${marker.name}" at line ${lineNum}`);
  }
}

// Check Allowed Files has at least one entry
const allowedFilesMatch = content.match(/## Allowed Files\n([\s\S]*?)(?=\n## |\n---|\Z)/);
if (allowedFilesMatch) {
  const section = allowedFilesMatch[1];
  if (!section.match(/\d+\.\s+`/)) {
    errors.push('Allowed Files section is empty (no numbered file entries)');
  }
}

// Check Implementation Plan has at least one task
const planMatch = content.match(/## Implementation Plan\n([\s\S]*?)(?=\n## |\n---|\Z)/);
if (planMatch) {
  const section = planMatch[1];
  if (!section.match(/### Task \d+/)) {
    errors.push('Implementation Plan has no tasks (expected ### Task N)');
  }
}

// Check DoD has checkboxes
const dodMatch = content.match(/## Definition of Done\n([\s\S]*?)(?=\n## |\n---|\Z)/);
if (dodMatch) {
  const section = dodMatch[1];
  if (!section.match(/- \[ \]/)) {
    errors.push('Definition of Done has no checkboxes');
  }
}

if (errors.length > 0) {
  console.log('FAIL: Spec structure validation');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Spec structure validation');
  process.exit(0);
}
