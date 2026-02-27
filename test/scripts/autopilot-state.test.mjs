/**
 * Tests for autopilot-state.mjs
 *
 * Verifies:
 * - initState creates valid state
 * - setPlan sets plan_exists and task list
 * - updateTask validates step names (VALID_STEPS whitelist)
 * - isPlanned returns correct gate status
 * - getCurrentTask finds first non-done task
 * - getProgress returns summary
 */

import { mkdirSync, rmSync } from 'fs';
import { join } from 'path';
import { strict as assert } from 'assert';

const MOD_PATH = join(process.cwd(), 'template/.claude/scripts/autopilot-state.mjs');
const mod = await import(`file://${MOD_PATH}`);
const { initState, readState, setPlan, updateTask, isPlanned, getCurrentTask, getProgress } = mod;

const TEST_DIR = join(process.cwd(), 'test/scripts/.tmp-autopilot-state');

function setup() {
  rmSync(TEST_DIR, { recursive: true, force: true });
  mkdirSync(TEST_DIR, { recursive: true });
}

function cleanup() {
  try { rmSync(TEST_DIR, { recursive: true, force: true }); } catch {}
}

// --- Tests ---

function testInitState() {
  const state = initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  assert.ok(state, 'initState should return state object');
  assert.equal(state.spec_id, 'FTR-042');
  assert.equal(state.spec_path, 'ai/features/FTR-042.md');
  assert.equal(state.plan_exists, false);
  assert.deepEqual(state.tasks, []);
  assert.ok(state.started, 'Should have started timestamp');

  const onDisk = readState(TEST_DIR);
  assert.equal(onDisk.spec_id, 'FTR-042');
  console.log('  PASS: testInitState');
}

function testSetPlan() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');

  const tasks = [
    { id: 1, name: 'Setup database' },
    { id: 2, name: 'Add API endpoint' },
  ];
  const ok = setPlan(TEST_DIR, tasks);
  assert.ok(ok, 'setPlan should return true');

  const state = readState(TEST_DIR);
  assert.equal(state.plan_exists, true);
  assert.equal(state.tasks.length, 2);
  assert.equal(state.tasks[0].id, 1);
  assert.equal(state.tasks[0].name, 'Setup database');
  assert.equal(state.tasks[0].status, 'pending');
  assert.equal(state.tasks[0].coder, 'pending');
  assert.equal(state.tasks[0].tester, 'pending');
  assert.equal(state.tasks[0].reviewer, 'pending');
  assert.equal(state.tasks[0].commit, null);
  console.log('  PASS: testSetPlan');
}

function testUpdateTaskValidSteps() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);

  // Valid steps should succeed
  for (const step of ['status', 'coder', 'tester', 'reviewer', 'commit']) {
    const ok = updateTask(TEST_DIR, 1, step, 'done');
    assert.ok(ok, `updateTask should succeed for step: ${step}`);
  }

  const state = readState(TEST_DIR);
  assert.equal(state.tasks[0].status, 'done');
  assert.equal(state.tasks[0].coder, 'done');
  assert.equal(state.tasks[0].tester, 'done');
  assert.equal(state.tasks[0].reviewer, 'done');
  assert.equal(state.tasks[0].commit, 'done');
  console.log('  PASS: testUpdateTaskValidSteps');
}

function testUpdateTaskInvalidStep() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);

  // Invalid steps should be rejected
  const badSteps = ['id', 'name', 'ts', '__proto__', 'constructor', 'toString', 'arbitrary'];
  for (const step of badSteps) {
    const ok = updateTask(TEST_DIR, 1, step, 'hacked');
    assert.equal(ok, false, `updateTask should reject step: ${step}`);
  }

  // Verify task structure wasn't corrupted
  const state = readState(TEST_DIR);
  assert.equal(state.tasks[0].id, 1);
  assert.equal(state.tasks[0].name, 'Task 1');
  console.log('  PASS: testUpdateTaskInvalidStep');
}

function testUpdateTaskNonexistentTask() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);

  const ok = updateTask(TEST_DIR, 999, 'status', 'done');
  assert.equal(ok, false, 'Should return false for nonexistent task');
  console.log('  PASS: testUpdateTaskNonexistentTask');
}

function testUpdateTaskTimestamp() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);

  updateTask(TEST_DIR, 1, 'coder', 'done');
  const state = readState(TEST_DIR);
  assert.ok(state.tasks[0].ts, 'Non-status step should add timestamp');

  // Status step should NOT add timestamp
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);
  updateTask(TEST_DIR, 1, 'status', 'in_progress');
  const state2 = readState(TEST_DIR);
  assert.equal(state2.tasks[0].ts, undefined, 'Status step should not add timestamp');
  console.log('  PASS: testUpdateTaskTimestamp');
}

function testIsPlanned() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');

  assert.equal(isPlanned(TEST_DIR), false, 'Should be false before setPlan');

  setPlan(TEST_DIR, [{ id: 1, name: 'Task 1' }]);
  assert.equal(isPlanned(TEST_DIR), true, 'Should be true after setPlan');
  console.log('  PASS: testIsPlanned');
}

function testIsPlannedMissingState() {
  // No state file = fail-safe = true (don't block)
  assert.equal(isPlanned('/nonexistent/path'), true, 'Missing state should fail-safe to true');
  console.log('  PASS: testIsPlannedMissingState');
}

function testGetCurrentTask() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [
    { id: 1, name: 'Task 1' },
    { id: 2, name: 'Task 2' },
  ]);

  let current = getCurrentTask(TEST_DIR);
  assert.equal(current.id, 1, 'First pending task should be current');

  updateTask(TEST_DIR, 1, 'status', 'done');
  current = getCurrentTask(TEST_DIR);
  assert.equal(current.id, 2, 'After task 1 done, task 2 should be current');

  updateTask(TEST_DIR, 2, 'status', 'done');
  current = getCurrentTask(TEST_DIR);
  assert.equal(current, null, 'All done = null');
  console.log('  PASS: testGetCurrentTask');
}

function testGetProgress() {
  initState(TEST_DIR, 'FTR-042', 'ai/features/FTR-042.md');
  setPlan(TEST_DIR, [
    { id: 1, name: 'Task 1' },
    { id: 2, name: 'Task 2' },
    { id: 3, name: 'Task 3' },
  ]);

  let progress = getProgress(TEST_DIR);
  assert.equal(progress.total, 3);
  assert.equal(progress.done, 0);
  assert.equal(progress.current, 1);

  updateTask(TEST_DIR, 1, 'status', 'done');
  updateTask(TEST_DIR, 2, 'status', 'done');
  progress = getProgress(TEST_DIR);
  assert.equal(progress.done, 2);
  assert.equal(progress.current, 3);
  console.log('  PASS: testGetProgress');
}

function testReadStateMissing() {
  const state = readState('/nonexistent/path');
  assert.equal(state, null, 'Missing state should return null');
  console.log('  PASS: testReadStateMissing');
}

// --- Runner ---

function main() {
  console.log('autopilot-state.test.mjs');
  setup();
  try {
    testInitState();
    testSetPlan();
    testUpdateTaskValidSteps();
    testUpdateTaskInvalidStep();
    testUpdateTaskNonexistentTask();
    testUpdateTaskTimestamp();
    testIsPlanned();
    testIsPlannedMissingState();
    testGetCurrentTask();
    testGetProgress();
    testReadStateMissing();
    console.log('\n11/11 tests passed');
  } finally {
    cleanup();
  }
}

main();
