#!/usr/bin/env node
/**
 * Deterministic validator: checks Eval Criteria or Tests section in spec (Gate S2).
 * Spark v2 requires mandatory Eval Criteria (preferred) or Tests (legacy) section.
 *
 * Dual-detection logic:
 * 1. Check ## Eval Criteria first (new format) — count | EC-N rows
 * 2. Fallback: check ## Tests (legacy format) — count checkboxes
 *
 * Usage: node validate-spec-tests.mjs <spec_file>
 * Exit: 0 = pass, 1 = fail (reasons on stdout)
 */

import { readFileSync } from 'fs';

const specPath = process.argv[2];
if (!specPath) {
  console.error('Usage: node validate-spec-tests.mjs <spec_file>');
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

// Priority 1: Check Eval Criteria section (new format)
if (/^## Eval Criteria/m.test(content)) {
  const evalMatch = content.match(/## Eval Criteria[\s\S]*?(?=\n## [^#]|\s*$)/);
  if (evalMatch) {
    const section = evalMatch[0];

    // Count EC rows (| EC-1 | ... pattern)
    const ecRows = (section.match(/\|\s*EC-\d+/g) || []).length;
    if (ecRows < 3) {
      errors.push(`Eval Criteria: only ${ecRows} criteria (minimum 3 required)`);
    }

    // Check Coverage Summary
    if (!/### Coverage Summary/i.test(section)) {
      errors.push('Eval Criteria section missing ### Coverage Summary');
    }

    // Check TDD Order
    if (!/### TDD Order/i.test(section)) {
      errors.push('Eval Criteria section missing ### TDD Order');
    }

    // Check DoD includes tests/eval
    const dodMatch = content.match(/## Definition of Done\n([\s\S]*?)(?=\n## |\s*$)/);
    if (dodMatch) {
      const dod = dodMatch[1].toLowerCase();
      if (!dod.includes('test') && !dod.includes('eval')) {
        errors.push('Definition of Done does not mention tests or eval criteria');
      }
    }
  }
} else if (/^## Tests/m.test(content)) {
  // Priority 2: Fallback to legacy Tests section
  const testsMatch = content.match(/## Tests\n([\s\S]*?)(?=\n## [^#]|\Z)/);
  if (testsMatch) {
    const section = testsMatch[1];

    // Check "What to test" subsection
    if (!/### What to test/i.test(section)) {
      errors.push('Tests section missing ### What to test');
    }

    // Count test cases (checkboxes in What to test)
    const whatMatch = section.match(/### What to test\n([\s\S]*?)(?=\n### |\Z)/);
    if (whatMatch) {
      const checkboxes = whatMatch[1].match(/- \[ \]/g) || [];
      if (checkboxes.length < 3) {
        errors.push(`Tests: only ${checkboxes.length} test cases (minimum 3 required)`);
      }
    }

    // Check "How to test" subsection
    if (!/### How to test/i.test(section)) {
      errors.push('Tests section missing ### How to test');
    }

    // Check DoD includes tests
    const dodMatch = content.match(/## Definition of Done\n([\s\S]*?)(?=\n## |\s*$)/);
    if (dodMatch) {
      const dod = dodMatch[1].toLowerCase();
      if (!dod.includes('test')) {
        errors.push('Definition of Done does not mention tests');
      }
    }
  }
} else {
  // Neither section found
  errors.push('Missing mandatory section: ## Eval Criteria (or ## Tests for legacy specs)');
}

if (errors.length > 0) {
  console.log('FAIL: Eval/Tests validation');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Eval/Tests validation');
  process.exit(0);
}
