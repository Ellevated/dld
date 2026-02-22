/**
 * Tests for spark-state.mjs
 *
 * Verifies:
 * - initState creates valid state with all phases
 * - updatePhase changes status and adds timestamp
 * - validatePhase checks phase completion
 * - validateResearch checks file count
 * - findSession handles case-insensitive matching
 */

import { mkdirSync, rmSync, readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';
import { strict as assert } from 'assert';

// Dynamic import to handle ESM
const MOD_PATH = join(process.cwd(), 'template/.claude/scripts/spark-state.mjs');
const mod = await import(`file://${MOD_PATH}`);
const { initState, readState, updatePhase, validatePhase, validateResearch, getPhases, findSession } = mod;

const TEST_DIR = join(process.cwd(), 'test/scripts/.tmp-spark-state');
const SESSION_DIR = join(TEST_DIR, 'sessions', '20260222-ftr-042-auth');

function setup() {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(SESSION_DIR, { recursive: true });
}

function cleanup() {
  try { rmSync(TEST_DIR, { recursive: true, force: true }); } catch {}
}

// --- Tests ---

function testInitState() {
  const state = initState(SESSION_DIR, 'FTR-042');
  assert.ok(state, 'initState should return state object');
  assert.equal(state.spec_id, 'FTR-042');
  assert.ok(state.created, 'Should have created timestamp');
  assert.ok(state.phases, 'Should have phases');

  const phases = getPhases();
  for (const phase of phases) {
    assert.equal(state.phases[phase].status, 'pending', `Phase ${phase} should be pending`);
  }

  // Verify file was written
  const onDisk = readState(SESSION_DIR);
  assert.deepEqual(onDisk.spec_id, 'FTR-042');
  console.log('  PASS: testInitState');
}

function testUpdatePhase() {
  initState(SESSION_DIR, 'FTR-042');

  const ok = updatePhase(SESSION_DIR, 'collect', 'done');
  assert.ok(ok, 'updatePhase should return true');

  const state = readState(SESSION_DIR);
  assert.equal(state.phases.collect.status, 'done');
  assert.ok(state.phases.collect.ts, 'Should have timestamp');
  console.log('  PASS: testUpdatePhase');
}

function testUpdatePhaseWithExtra() {
  initState(SESSION_DIR, 'FTR-042');
  updatePhase(SESSION_DIR, 'research', 'done', { files: ['a.md', 'b.md'] });

  const state = readState(SESSION_DIR);
  assert.equal(state.phases.research.status, 'done');
  assert.deepEqual(state.phases.research.files, ['a.md', 'b.md']);
  console.log('  PASS: testUpdatePhaseWithExtra');
}

function testUpdatePhaseInvalidPhase() {
  initState(SESSION_DIR, 'FTR-042');
  const ok = updatePhase(SESSION_DIR, 'nonexistent', 'done');
  assert.equal(ok, false, 'Should reject invalid phase');
  console.log('  PASS: testUpdatePhaseInvalidPhase');
}

function testValidatePhase() {
  initState(SESSION_DIR, 'FTR-042');

  let result = validatePhase(SESSION_DIR, 'collect');
  assert.equal(result.valid, false, 'Pending phase should not be valid');

  updatePhase(SESSION_DIR, 'collect', 'done');
  result = validatePhase(SESSION_DIR, 'collect');
  assert.equal(result.valid, true, 'Done phase should be valid');
  console.log('  PASS: testValidatePhase');
}

function testValidatePhaseMissingState() {
  const result = validatePhase('/nonexistent/path', 'collect');
  assert.equal(result.valid, false, 'Missing state should be invalid');
  assert.ok(result.reason.includes('not found'), 'Should mention not found');
  console.log('  PASS: testValidatePhaseMissingState');
}

function testValidateResearch() {
  initState(SESSION_DIR, 'FTR-042');
  updatePhase(SESSION_DIR, 'research', 'done', { files: ['a.md', 'b.md', 'c.md'] });

  const result = validateResearch(SESSION_DIR, 2);
  assert.equal(result.valid, true);
  assert.equal(result.found, 3);
  console.log('  PASS: testValidateResearch');
}

function testValidateResearchTooFew() {
  initState(SESSION_DIR, 'FTR-042');
  updatePhase(SESSION_DIR, 'research', 'done', { files: ['a.md'] });

  const result = validateResearch(SESSION_DIR, 2);
  assert.equal(result.valid, false);
  assert.equal(result.found, 1);
  console.log('  PASS: testValidateResearchTooFew');
}

function testValidateResearchNotDone() {
  initState(SESSION_DIR, 'FTR-042');

  const result = validateResearch(SESSION_DIR, 2);
  assert.equal(result.valid, false);
  assert.ok(result.reason.includes('not done'));
  console.log('  PASS: testValidateResearchNotDone');
}

function testFindSessionCaseInsensitive() {
  const baseDir = join(TEST_DIR, 'spark-sessions');
  mkdirSync(join(baseDir, '20260222-ftr-042-auth'), { recursive: true });

  // Uppercase search should find lowercase dir
  const found = findSession('FTR-042', baseDir);
  assert.ok(found, 'Should find session with case-insensitive match');
  assert.ok(found.includes('20260222-ftr-042-auth'));
  console.log('  PASS: testFindSessionCaseInsensitive');
}

function testFindSessionNoMatch() {
  const baseDir = join(TEST_DIR, 'spark-sessions-empty');
  mkdirSync(baseDir, { recursive: true });

  const found = findSession('FTR-999', baseDir);
  assert.equal(found, null, 'Should return null for no match');
  console.log('  PASS: testFindSessionNoMatch');
}

function testFindSessionMissingDir() {
  const found = findSession('FTR-042', '/nonexistent/path');
  assert.equal(found, null, 'Should return null for missing dir');
  console.log('  PASS: testFindSessionMissingDir');
}

function testGetPhases() {
  const phases = getPhases();
  assert.ok(Array.isArray(phases));
  assert.ok(phases.includes('collect'));
  assert.ok(phases.includes('research'));
  assert.ok(phases.includes('write'));
  assert.ok(phases.includes('validate'));
  console.log('  PASS: testGetPhases');
}

// --- Runner ---

function main() {
  console.log('spark-state.test.mjs');
  setup();
  try {
    testInitState();
    testUpdatePhase();
    testUpdatePhaseWithExtra();
    testUpdatePhaseInvalidPhase();
    testValidatePhase();
    testValidatePhaseMissingState();
    testValidateResearch();
    testValidateResearchTooFew();
    testValidateResearchNotDone();
    testFindSessionCaseInsensitive();
    testFindSessionNoMatch();
    testFindSessionMissingDir();
    testGetPhases();
    console.log('\n13/13 tests passed');
  } finally {
    cleanup();
  }
}

main();
