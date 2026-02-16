#!/usr/bin/env node
/**
 * Deterministic validator: checks Tests section in spec (Gate S2).
 * Spark v2 requires mandatory Tests section with min 3 test cases.
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

// Check Tests section exists
if (!/^## Tests/m.test(content)) {
  errors.push('Missing mandatory section: ## Tests');
} else {
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
    const dodMatch = content.match(/## Definition of Done\n([\s\S]*?)(?=\n## |\Z)/);
    if (dodMatch) {
      const dod = dodMatch[1].toLowerCase();
      if (!dod.includes('test')) {
        errors.push('Definition of Done does not mention tests');
      }
    }
  }
}

if (errors.length > 0) {
  console.log('FAIL: Tests validation');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Tests validation');
  process.exit(0);
}
