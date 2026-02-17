#!/usr/bin/env node
/**
 * Structural gate: validates deep-audit-report.md has all required sections.
 *
 * Usage: node validate-audit-report.mjs <report_path>
 * Exit: 0 = pass, 1 = fail, 2 = usage error
 */

import { readFileSync, existsSync } from 'fs';

const reportPath = process.argv[2];

if (!reportPath) {
  console.error('Usage: node validate-audit-report.mjs <report_path>');
  process.exit(2);
}

if (!existsSync(reportPath)) {
  console.error(`Report not found: ${reportPath}`);
  console.log('FAIL: deep-audit-report.md does not exist');
  process.exit(1);
}

const content = readFileSync(reportPath, 'utf-8');
const errors = [];

// Required sections (8 + For Architect)
const requiredSections = [
  { pattern: /^## 1\.\s*Project Stats/m, name: 'Project Stats' },
  { pattern: /^## 2\.\s*Architecture Map/m, name: 'Architecture Map' },
  { pattern: /^## 3\.\s*Pattern Inventory/m, name: 'Pattern Inventory' },
  { pattern: /^## 4\.\s*Data Model/m, name: 'Data Model' },
  { pattern: /^## 5\.\s*Test Coverage/m, name: 'Test Coverage' },
  { pattern: /^## 6\.\s*Tech Debt Inventory/m, name: 'Tech Debt Inventory' },
  { pattern: /^## 7\.\s*External Integrations/m, name: 'External Integrations' },
  { pattern: /^## 8\.\s*Red Flags/m, name: 'Red Flags' },
  { pattern: /^## For Architect/m, name: 'For Architect' },
];

for (const section of requiredSections) {
  if (!section.pattern.test(content)) {
    errors.push(`Missing section: ${section.name}`);
  }
}

// Check for placeholder-only lines (lines that ARE placeholders, not mentions of them)
// "TBD" alone = placeholder. "TODO count: 7" or "found 3 TODO markers" = legitimate finding.
const placeholderPatterns = [
  /^\s*TBD\.?\s*$/i,           // Line is just "TBD" or "TBD."
  /^\s*TODO\.?\s*$/i,          // Line is just "TODO" or "TODO."
  /^\s*FIXME\.?\s*$/i,         // Line is just "FIXME"
  /\{fill[^}]*\}/,             // Template placeholder {fill...}
  /\{placeholder[^}]*\}/,      // Template placeholder {placeholder...}
  /\{[A-Z_]+\}/,               // Template placeholder {SOMETHING}
];
const lines = content.split('\n');
for (let i = 0; i < lines.length; i++) {
  const line = lines[i].trim();
  // Skip code blocks, tables, headers, inline code
  if (line.startsWith('```') || line.startsWith('|') || line.startsWith('#') || line.startsWith('- `')) continue;
  for (const ph of placeholderPatterns) {
    if (ph.test(line)) {
      errors.push(`Placeholder found on line ${i + 1}: "${line.substring(0, 60)}"`);
      break;
    }
  }
}

// Check minimum content length (deep audit should be substantial)
const MIN_LENGTH = 2000;
if (content.length < MIN_LENGTH) {
  errors.push(`Report too short: ${content.length} chars (minimum: ${MIN_LENGTH})`);
}

// Check required metadata
if (!/\*\*Date:\*\*/m.test(content)) errors.push('Missing metadata: Date');
if (!/\*\*Project:\*\*/m.test(content)) errors.push('Missing metadata: Project');
if (!/\*\*Files scanned:\*\*/m.test(content)) errors.push('Missing metadata: Files scanned');
if (!/\*\*LOC:\*\*/m.test(content)) errors.push('Missing metadata: LOC');

// Check that sections have content (not just headers)
for (const section of requiredSections) {
  const match = content.match(section.pattern);
  if (match) {
    const start = match.index + match[0].length;
    const nextSection = content.indexOf('\n## ', start + 1);
    const sectionContent = nextSection > 0
      ? content.substring(start, nextSection).trim()
      : content.substring(start).trim();
    if (sectionContent.length < 50) {
      errors.push(`Section "${section.name}" appears empty or too short`);
    }
  }
}

if (errors.length > 0) {
  console.log('FAIL: Deep audit report validation');
  errors.forEach(e => console.log(`  - ${e}`));
  process.exit(1);
} else {
  console.log('PASS: Deep audit report validation');
  console.log(`  Sections: ${requiredSections.length}/${requiredSections.length}`);
  console.log(`  Length: ${content.length} chars`);
  process.exit(0);
}
