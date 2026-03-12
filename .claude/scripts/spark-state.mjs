/**
 * Spark Session State — JSON state tracking for Spark phases.
 *
 * Provides deterministic phase tracking instead of relying on LLM memory.
 * State file: ai/.spark/{session}/state.json
 *
 * Used by: Spark orchestrator (writes), validate-spec-complete hook (reads).
 * ADR-004: All functions are fail-safe — never throw.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'fs';
import { join } from 'path';

const PHASES = ['collect', 'research', 'synthesize', 'decide', 'write', 'validate', 'reflect', 'completion'];

/**
 * Read state from session directory.
 * @param {string} sessionDir - Path to ai/.spark/{session}/
 * @returns {object|null} State object or null if not found
 */
export function readState(sessionDir) {
  try {
    const statePath = join(sessionDir, 'state.json');
    if (!existsSync(statePath)) return null;
    return JSON.parse(readFileSync(statePath, 'utf-8'));
  } catch {
    return null; // fail-safe (ADR-004)
  }
}

/**
 * Initialize a new Spark session state.
 * @param {string} sessionDir - Path to ai/.spark/{session}/
 * @param {string} specId - Spec ID (e.g., "FTR-042")
 * @returns {object|null} Created state or null on error
 */
export function initState(sessionDir, specId) {
  try {
    mkdirSync(sessionDir, { recursive: true });
    const state = {
      spec_id: specId,
      created: new Date().toISOString(),
      phases: {},
    };
    for (const phase of PHASES) {
      state.phases[phase] = { status: 'pending' };
    }
    writeFileSync(join(sessionDir, 'state.json'), JSON.stringify(state, null, 2) + '\n');
    return state;
  } catch {
    return null; // fail-safe
  }
}

/**
 * Update a phase status in the state file.
 * @param {string} sessionDir - Path to ai/.spark/{session}/
 * @param {string} phase - Phase name (collect, research, etc.)
 * @param {string} status - New status (done, in_progress, skipped)
 * @param {object} [extra] - Additional fields (e.g., { files: [...], approach: 2 })
 * @returns {boolean} Success
 */
export function updatePhase(sessionDir, phase, status, extra = {}) {
  try {
    const state = readState(sessionDir);
    if (!state) return false;
    if (!PHASES.includes(phase)) return false;

    state.phases[phase] = {
      ...state.phases[phase],
      status,
      ts: new Date().toISOString(),
      ...extra,
    };
    writeFileSync(join(sessionDir, 'state.json'), JSON.stringify(state, null, 2) + '\n');
    return true;
  } catch {
    return false; // fail-safe
  }
}

/**
 * Validate that a phase is complete before proceeding.
 * @param {string} sessionDir - Path to ai/.spark/{session}/
 * @param {string} phase - Phase name to check
 * @returns {{ valid: boolean, reason?: string }}
 */
export function validatePhase(sessionDir, phase) {
  try {
    const state = readState(sessionDir);
    if (!state) return { valid: false, reason: 'state.json not found' };
    if (!state.phases[phase]) return { valid: false, reason: `unknown phase: ${phase}` };
    if (state.phases[phase].status !== 'done') {
      return { valid: false, reason: `phase ${phase} status is ${state.phases[phase].status}, expected done` };
    }
    return { valid: true };
  } catch {
    return { valid: true }; // fail-safe: don't block on error
  }
}

/**
 * Check if research phase produced required files.
 * @param {string} sessionDir - Path to ai/.spark/{session}/
 * @param {number} [minFiles=2] - Minimum research files required
 * @returns {{ valid: boolean, found: number, reason?: string }}
 */
export function validateResearch(sessionDir, minFiles = 2) {
  try {
    const state = readState(sessionDir);
    if (!state) return { valid: false, found: 0, reason: 'state.json not found' };

    const research = state.phases.research;
    if (!research || research.status !== 'done') {
      return { valid: false, found: 0, reason: 'research phase not done' };
    }

    const files = research.files || [];
    if (files.length < minFiles) {
      return { valid: false, found: files.length, reason: `only ${files.length} research files, need ${minFiles}` };
    }
    return { valid: true, found: files.length };
  } catch {
    return { valid: true, found: 0 }; // fail-safe
  }
}

/**
 * Get ordered list of phase names.
 * @returns {string[]}
 */
export function getPhases() {
  return [...PHASES];
}

/**
 * Find session directory for a spec ID by scanning ai/.spark/.
 * @param {string} specId - Spec ID (e.g., "FTR-042")
 * @param {string} [baseDir='ai/.spark'] - Base directory
 * @returns {string|null} Session directory path or null
 */
export function findSession(specId, baseDir = 'ai/.spark') {
  try {
    if (!existsSync(baseDir)) return null;
    const dirs = readdirSync(baseDir, { withFileTypes: true })
      .filter(d => d.isDirectory() && d.name.toLowerCase().includes(specId.toLowerCase()))
      .sort((a, b) => b.name.localeCompare(a.name)); // latest first
    if (dirs.length === 0) return null;
    return join(baseDir, dirs[0].name);
  } catch {
    return null; // fail-safe
  }
}
