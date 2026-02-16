#!/usr/bin/env node
/**
 * Deterministic validator: checks spec/code against System Blueprint (Gate S3, P2).
 * Verifies Blueprint Reference section in spec and cross-cutting compliance.
 *
 * Usage: node validate-blueprint-compliance.mjs <spec_file> [blueprint_dir]
 * Exit: 0 = pass, 1 = fail, 2 = skip (no blueprint exists)
 */

import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const specPath = process.argv[2];
const blueprintDir = process.argv[3] || 'ai/blueprint/system-blueprint';

if (!specPath) {
  console.error('Usage: node validate-blueprint-compliance.mjs <spec_file> [blueprint_dir]');
  process.exit(2);
}

// If no blueprint exists, skip (backwards compatible with legacy projects)
if (!existsSync(blueprintDir)) {
  console.log('SKIP: No system blueprint found (legacy project)');
  process.exit(0);
}

let content;
try {
  content = readFileSync(specPath, 'utf-8');
} catch {
  console.error(`Cannot read file: ${specPath}`);
  process.exit(2);
}

const errors = [];

// Check Blueprint Reference section exists
if (!/^## Blueprint Reference/m.test(content)) {
  errors.push('Missing section: ## Blueprint Reference');
} else {
  const refMatch = content.match(/## Blueprint Reference\n([\s\S]*?)(?=\n## |\n---|\Z)/);
  if (refMatch) {
    const section = refMatch[1];

    if (!/Domain:/i.test(section)) {
      errors.push('Blueprint Reference missing Domain field');
    }
    if (!/Cross-cutting:/i.test(section)) {
      errors.push('Blueprint Reference missing Cross-cutting field');
    }
    if (!/Data model:/i.test(section)) {
      errors.push('Blueprint Reference missing Data model field');
    }
  }
}

// Check cross-cutting.md exists and validate known rules
const crossCuttingPath = join(blueprintDir, 'cross-cutting.md');
if (existsSync(crossCuttingPath)) {
  try {
    const crossCutting = readFileSync(crossCuttingPath, 'utf-8');

    // Check if spec mentions money and cross-cutting has Money type
    if (/money|price|amount|billing|payment/i.test(content)) {
      if (/Money.*int|cents/i.test(crossCutting)) {
        // Cross-cutting defines money as int/cents — check spec doesn't use float
        if (/float.*money|money.*float|decimal.*price/i.test(content)) {
          errors.push('Blueprint conflict: spec uses float/decimal for money, cross-cutting requires int (cents)');
        }
      }
    }
  } catch {
    // Can't read cross-cutting, non-fatal
  }
}

// Check domain-map.md — verify spec domain exists
const domainMapPath = join(blueprintDir, 'domain-map.md');
if (existsSync(domainMapPath)) {
  const refMatch = content.match(/Domain:\s*(.+)/i);
  if (refMatch) {
    try {
      const domainMap = readFileSync(domainMapPath, 'utf-8');
      const specDomain = refMatch[1].trim().toLowerCase();
      if (specDomain && !domainMap.toLowerCase().includes(specDomain)) {
        errors.push(`Blueprint conflict: domain "${specDomain}" not found in domain-map.md`);
      }
    } catch {
      // Can't read domain-map, non-fatal
    }
  }
}

if (errors.length > 0) {
  console.log('FAIL: Blueprint compliance');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Blueprint compliance');
  process.exit(0);
}
