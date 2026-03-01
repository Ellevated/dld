/**
 * Autopilot Task State — JSON state tracking for Autopilot task loop.
 *
 * Provides deterministic task progress tracking instead of relying on LLM memory.
 * State file: {worktree}/autopilot-state.json (in worktree, not main repo)
 *
 * Used by: Autopilot orchestrator (writes), pre-edit hook (reads plan gate).
 * ADR-004: All functions are fail-safe — never throw.
 */

import { readFileSync, writeFileSync, existsSync } from 'fs';
import { join } from 'path';

const STATE_FILENAME = 'autopilot-state.json';

/**
 * Resolve the state file path from a directory.
 * @param {string} [dir] - Directory (defaults to cwd)
 * @returns {string} Full path to autopilot-state.json
 */
function statePath(dir) {
  return join(dir || process.cwd(), STATE_FILENAME);
}

/**
 * Read autopilot state from directory.
 * @param {string} [dir] - Directory containing autopilot-state.json
 * @returns {object|null} State object or null if not found
 */
export function readState(dir) {
  try {
    const path = statePath(dir);
    if (!existsSync(path)) return null;
    return JSON.parse(readFileSync(path, 'utf-8'));
  } catch {
    return null; // fail-safe (ADR-004)
  }
}

/**
 * Initialize a new Autopilot session state.
 * @param {string} dir - Worktree directory
 * @param {string} specId - Spec ID (e.g., "FTR-042")
 * @param {string} specPath - Path to spec file
 * @returns {object|null} Created state or null on error
 */
export function initState(dir, specId, specPath) {
  try {
    const state = {
      spec_id: specId,
      spec_path: specPath,
      started: new Date().toISOString(),
      plan_exists: false,
      tasks: [],
    };
    writeFileSync(statePath(dir), JSON.stringify(state, null, 2) + '\n');
    return state;
  } catch {
    return null; // fail-safe
  }
}

/**
 * Set the plan as created.
 * @param {string} dir - Worktree directory
 * @param {Array<{id: number, name: string}>} tasks - Task list from plan
 * @returns {boolean} Success
 */
export function setPlan(dir, tasks) {
  try {
    const state = readState(dir);
    if (!state) return false;

    state.plan_exists = true;
    state.tasks = tasks.map(t => ({
      id: t.id,
      name: t.name,
      status: 'pending',
      coder: 'pending',
      tester: 'pending',
      reviewer: 'pending',
      commit: null,
      verify: 'pending',
    }));
    writeFileSync(statePath(dir), JSON.stringify(state, null, 2) + '\n');
    return true;
  } catch {
    return false; // fail-safe
  }
}

/**
 * Update a specific task's step result.
 * @param {string} dir - Worktree directory
 * @param {number} taskId - Task ID (1-based)
 * @param {string} step - Step name (status, coder, tester, reviewer, commit)
 * @param {string} value - Step value (done, pass, fail, approved, commit hash, etc.)
 * @returns {boolean} Success
 */
export function updateTask(dir, taskId, step, value) {
  try {
    const state = readState(dir);
    if (!state) return false;

    const VALID_STEPS = ['status', 'coder', 'tester', 'reviewer', 'commit', 'verify'];
    if (!VALID_STEPS.includes(step)) return false;

    const task = state.tasks.find(t => t.id === taskId);
    if (!task) return false;

    task[step] = value;
    if (step !== 'status') {
      task.ts = new Date().toISOString();
    }
    writeFileSync(statePath(dir), JSON.stringify(state, null, 2) + '\n');
    return true;
  } catch {
    return false; // fail-safe
  }
}

/**
 * Check if plan exists in autopilot state.
 * @param {string} [dir] - Directory containing autopilot-state.json
 * @returns {boolean} True if plan exists (or state not found — fail-safe allows)
 */
export function isPlanned(dir) {
  try {
    const state = readState(dir);
    if (!state) return true; // fail-safe: no state = don't block
    return state.plan_exists === true;
  } catch {
    return true; // fail-safe
  }
}

/**
 * Get current task (first non-done task).
 * @param {string} [dir] - Directory
 * @returns {{ id: number, name: string, status: string }|null}
 */
export function getCurrentTask(dir) {
  try {
    const state = readState(dir);
    if (!state || !state.tasks) return null;
    return state.tasks.find(t => t.status !== 'done') || null;
  } catch {
    return null; // fail-safe
  }
}

/**
 * Get progress summary.
 * @param {string} [dir] - Directory
 * @returns {{ total: number, done: number, current: number|null }}
 */
export function getProgress(dir) {
  try {
    const state = readState(dir);
    if (!state || !state.tasks) return { total: 0, done: 0, current: null };

    const total = state.tasks.length;
    const done = state.tasks.filter(t => t.status === 'done').length;
    const current = state.tasks.find(t => t.status !== 'done');
    return { total, done, current: current ? current.id : null };
  } catch {
    return { total: 0, done: 0, current: null }; // fail-safe
  }
}
