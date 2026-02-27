/**
 * Block git commit if spec has structural issues.
 *
 * Checks (in order):
 * 1. Impact Tree — unfilled checkboxes
 * 2. Implementation Plan — must have at least one ### Task
 * 3. Research — spark state.json must show research phase = done
 * 4. Tests — must have ## Tests with at least N checkboxes
 *
 * Each check is a separate function. If state.json not found → fail-safe skip (ADR-004).
 * Configurable via hooks.config.mjs enforcement section.
 */

import { readFileSync, existsSync, readdirSync } from 'fs';
import { execFileSync } from 'child_process';
import { join } from 'path';
import { debugLog, debugTiming, denyTool, getToolInput, loadConfig, readHookInput } from './utils.mjs';

function stripCodeBlocks(text) {
  return text.replace(/```[\s\S]*?```/g, '');
}

// --- Check 1: Impact Tree (existing) ---

function checkImpactTree(content, specFile) {
  const impactSection = content.match(/## Impact Tree Analysis[\s\S]*?(?=\n## (?!#)|\s*$)/);
  if (!impactSection) return null; // no section = skip

  const stripped = stripCodeBlocks(impactSection[0]);
  if (stripped.includes('- [ ]')) {
    return (
      'Spec has unfilled Impact Tree checkboxes!\n\n' +
      'Complete the Impact Tree Analysis before committing:\n' +
      '1. Fill all checkboxes in Impact Tree section\n' +
      '2. Ensure grep results are recorded\n' +
      '3. Verify all found files are in Allowed Files\n\n' +
      'See: CLAUDE.md -> Impact Tree Analysis'
    );
  }
  return null;
}

// --- Check 2: Implementation Plan ---

function checkImplementationPlan(content) {
  const planSection = content.match(/## Implementation Plan[\s\S]*?(?=\n## |\s*$)/);
  if (!planSection) {
    return (
      'Spec missing Implementation Plan!\n\n' +
      'Add ## Implementation Plan with at least one ### Task section.\n' +
      'Each task needs: Type, Files, Acceptance criteria.\n\n' +
      'See: feature-mode.md -> Phase 5: WRITE'
    );
  }

  const hasTasks = /### Task \d+/i.test(planSection[0]);
  if (!hasTasks) {
    return (
      'Implementation Plan has no tasks!\n\n' +
      'Add at least one ### Task section with:\n' +
      '- Type (code | test | migrate)\n' +
      '- Files to create/modify\n' +
      '- Acceptance criteria'
    );
  }
  return null;
}

// --- Check 3: Research phase done ---

function checkResearch(specFile, minFiles) {
  try {
    // Extract spec ID from filename (e.g., FTR-042 from FTR-042-2026-02-22-auth.md)
    const specMatch = specFile.match(/((?:FTR|BUG|TECH|ARCH)-\d+)/i);
    if (!specMatch) return null; // can't determine spec ID = skip

    const specId = specMatch[1].toUpperCase();
    const sparkBase = 'ai/.spark';
    if (!existsSync(sparkBase)) return null; // no spark dir = skip (fail-safe)

    // Find session dir for this spec
    let sessionDir = null;
    try {
      const dirs = readdirSync(sparkBase, { withFileTypes: true })
        .filter(d => d.isDirectory() && d.name.toLowerCase().includes(specId.toLowerCase()))
        .sort((a, b) => b.name.localeCompare(a.name));
      if (dirs.length > 0) sessionDir = join(sparkBase, dirs[0].name);
    } catch {
      return null; // fail-safe
    }

    if (!sessionDir) return null; // no session = skip

    const statePath = join(sessionDir, 'state.json');
    if (!existsSync(statePath)) return null; // no state = skip (fail-safe)

    const state = JSON.parse(readFileSync(statePath, 'utf-8'));
    const research = state.phases?.research;

    if (!research || research.status !== 'done') {
      return (
        'Research phase not completed!\n\n' +
        `State: ${statePath}\n` +
        `Research status: ${research?.status || 'missing'}\n\n` +
        'Complete research phase before committing spec.\n' +
        'Run scouts to research the feature first.'
      );
    }

    const files = research.files || [];
    if (files.length < minFiles) {
      return (
        `Research has only ${files.length} files (minimum: ${minFiles})!\n\n` +
        `State: ${statePath}\n\n` +
        'Ensure all scouts produced research files.'
      );
    }

    return null;
  } catch {
    return null; // fail-safe (ADR-004)
  }
}

// --- Check 4: Eval Criteria / Tests section (dual-detection) ---

function checkEvalCriteria(content, minCriteria) {
  const evalSection = content.match(/## Eval Criteria[\s\S]*?(?=\n## |\s*$)/);
  if (!evalSection) return null; // not found — caller should try legacy

  const stripped = stripCodeBlocks(evalSection[0]);
  const ecRows = (stripped.match(/\|\s*EC-\d+/g) || []).length;
  if (ecRows < minCriteria) {
    return (
      `Eval Criteria has only ${ecRows} criteria (minimum: ${minCriteria})!\n\n` +
      'Add more eval criteria including edge cases from devil\'s advocate.\n\n' +
      'See: feature-mode.md -> Phase 5: WRITE -> Eval Criteria (MANDATORY)'
    );
  }

  if (!/### Coverage Summary/i.test(stripped)) {
    return (
      'Eval Criteria missing ### Coverage Summary!\n\n' +
      'Add coverage summary with counts per type.\n\n' +
      'See: feature-mode.md -> Phase 6: VALIDATE -> Gate 2'
    );
  }

  return null;
}

function checkTests(content, minTestCases) {
  // Priority 1: Check Eval Criteria (new format)
  if (/^## Eval Criteria/m.test(content)) {
    const minCriteria = minTestCases; // reuse same minimum
    return checkEvalCriteria(content, minCriteria);
  }

  // Priority 2: Legacy Tests section (backward compat)
  const testsSection = content.match(/## Tests[\s\S]*?(?=\n## |\s*$)/);
  if (!testsSection) {
    return (
      'Spec missing Eval Criteria or Tests section!\n\n' +
      `Add ## Eval Criteria with at least ${minTestCases} criteria (preferred)\n` +
      `or ## Tests with at least ${minTestCases} test cases (legacy).\n\n` +
      'See: feature-mode.md -> Phase 5: WRITE -> Eval Criteria (MANDATORY)'
    );
  }

  const stripped = stripCodeBlocks(testsSection[0]);
  const checkboxes = stripped.match(/- \[[ x]\]/g) || [];
  if (checkboxes.length < minTestCases) {
    return (
      `Tests section has only ${checkboxes.length} test cases (minimum: ${minTestCases})!\n\n` +
      'Add more test cases including edge cases from devil\'s advocate.\n\n' +
      'See: feature-mode.md -> Phase 6: VALIDATE -> Gate 2'
    );
  }

  return null;
}

// --- Main ---

async function main() {
  const timer = debugTiming('validate-spec');
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';

    // Only check for git commit (excludes git commit-graph, git commit-tree, etc.)
    if (!/\bgit\s+commit\b(?!-)/i.test(command)) {
      debugLog('validate-spec', 'skip', { reason: 'not_git_commit' });
      timer.end('skip');
      process.exit(0);
    }

    debugLog('validate-spec', 'check', { command: command.slice(0, 100) });

    // Load config for enforcement rules
    const config = await loadConfig();
    const enforcement = config?.enforcement || {};

    // Find spec in current staged changes
    let stagedFiles;
    try {
      stagedFiles = execFileSync('git', ['diff', '--cached', '--name-only'], {
        encoding: 'utf-8',
        timeout: 5000,
      }).trim();
    } catch {
      debugLog('validate-spec', 'skip', { reason: 'git_diff_failed' });
      timer.end('skip');
      process.exit(0);
    }

    const specFile = stagedFiles
      .split('\n')
      .find(f => /^ai\/features\/.*\.md$/.test(f));

    if (!specFile || !existsSync(specFile)) {
      debugLog('validate-spec', 'skip', { reason: 'no_spec_staged' });
      timer.end('allow');
      process.exit(0);
    }

    debugLog('validate-spec', 'spec_found', { specFile });
    const content = readFileSync(specFile, 'utf-8');

    // Check 1: Impact Tree (always on)
    const impactResult = checkImpactTree(content, specFile);
    if (impactResult) {
      debugLog('validate-spec', 'deny', { reason: 'unchecked_impact_tree', specFile });
      timer.end('deny');
      denyTool(impactResult);
      return;
    }

    // Check 2: Implementation Plan (configurable)
    if (enforcement.requirePlanBeforeCode !== false) {
      const planResult = checkImplementationPlan(content);
      if (planResult) {
        debugLog('validate-spec', 'deny', { reason: 'no_implementation_plan', specFile });
        timer.end('deny');
        denyTool(planResult);
        return;
      }
    }

    // Check 3: Research exists (configurable)
    if (enforcement.requireResearchForSpec !== false) {
      const minFiles = enforcement.minResearchFiles ?? 2;
      const researchResult = checkResearch(specFile, minFiles);
      if (researchResult) {
        debugLog('validate-spec', 'deny', { reason: 'research_incomplete', specFile });
        timer.end('deny');
        denyTool(researchResult);
        return;
      }
    }

    // Check 4: Tests section (configurable)
    if (enforcement.requireTestsInSpec !== false) {
      const minTests = enforcement.minTestCases ?? 3;
      const testsResult = checkTests(content, minTests);
      if (testsResult) {
        debugLog('validate-spec', 'deny', { reason: 'tests_incomplete', specFile });
        timer.end('deny');
        denyTool(testsResult);
        return;
      }
    }

    debugLog('validate-spec', 'allow');
    timer.end('allow');
    process.exit(0);
  } catch {
    timer.end('error');
    process.exit(0); // fail-safe
  }
}

main();
