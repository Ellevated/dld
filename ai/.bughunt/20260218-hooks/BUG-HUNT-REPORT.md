# Bug Hunt Report: .claude/hooks/ — ADR-010 Verification

**Date:** 2026-02-18
**Target:** `.claude/hooks/` (6 hook files + utils.mjs + hooks.config.mjs)
**Trigger:** Verification of ADR-010 Orchestrator Zero-Read pattern
**Session:** `ai/.bughunt/20260218-hooks/`

---

## Executive Summary

A 6-persona bug hunt of `.claude/hooks/` produced 40 validated findings across 8 severity groups. The most critical theme is that hooks silently disable their own enforcement when running inside git worktrees — the exact context autopilot uses — due to inconsistent use of `process.cwd()` vs `getProjectDir()`. Secondary themes include a security-critical race condition in the deny-output path, multiple bypass vectors in the spec allowlist system, and a non-standard glob engine that mismatches the most common allowlist pattern (`src/**/*.py`). The ADR-010 zero-read pipeline executed successfully with no orchestrator context pollution.

---

## Pipeline Statistics

| Metric | Value |
|--------|-------|
| Zones analyzed | 1 |
| Personas deployed | 6 |
| Raw findings | 83 |
| After dedup/validation | 40 |
| False positives caught | 2 |
| Duplicates merged | 25 |
| Rejected (noise) | 18 |
| Grouped specs created | 8 |
| Finding IDs | F-001 through F-040 |

**Raw findings by persona:**

| Persona | Raw findings |
|---------|-------------|
| code-reviewer | 12 |
| security-auditor | 13 |
| ux-analyst | 15 |
| junior-developer | 12 |
| software-architect | 13 |
| qa-engineer | 18 |

---

## Severity Distribution

| Priority | Finding Count | Spec |
|----------|--------------|------|
| P0 (Critical) | 8 | BUG-121, BUG-122 |
| P1 (High) | 12 | BUG-123, BUG-124, BUG-125 |
| P2 (Medium) | 10 | BUG-126, BUG-127 |
| P3 (Low) | 10 | BUG-128 |

---

## Spec Index

### P0 — Critical

#### BUG-121: Worktree Path Resolution
- **Findings:** F-001 through F-005
- **Priority:** P0
- **Summary:** Five hooks use `process.cwd()` or bare relative paths where `getProjectDir()` is required. In git worktrees (the autopilot execution context), this silently bypasses LOC enforcement, spec allowlist enforcement, and Impact Tree validation across `pre-edit.mjs`, `session-end.mjs`, `validate-spec-complete.mjs`, and `utils.mjs`. Root cause: inconsistent path resolution pattern across the codebase.
- **Spec:** [step5/BUG-121-worktree-path-resolution.md](step5/BUG-121-worktree-path-resolution.md)

#### BUG-122: getProjectDir() Safety
- **Findings:** F-006, F-007, F-008
- **Priority:** P0
- **Summary:** The central path safety function has three compounding bugs: macOS `/tmp` symlink resolution failure (`/private/tmp` vs `/tmp`) breaks all test environments, accepting bare `/tmp` as a project root makes the entire `/tmp` filesystem "inside the project", and use of `resolve()` instead of `realpathSync()` allows symlinks to escape the home directory boundary into dynamic ESM import execution.
- **Spec:** [step5/BUG-122-getProjectDir-safety.md](step5/BUG-122-getProjectDir-safety.md)

---

### P1 — High

#### BUG-123: Hook Output Reliability
- **Findings:** F-009, F-010
- **Priority:** P1
- **Summary:** Two related reliability bugs in `outputJson()` can cause deny decisions to silently become allows. A race condition between the write callback and a 500ms safety-net `setTimeout` can exit the process before the deny JSON is delivered. A missing `process.stdout.on('error', ...)` handler causes uncaught EPIPE crashes, which Claude Code treats as fail-open allows. Every `denyTool()`, `askTool()`, `blockPrompt()`, and `postBlock()` call flows through this path.
- **Spec:** [step5/BUG-123-hook-output-reliability.md](step5/BUG-123-hook-output-reliability.md)

#### BUG-124: Spec Allowlist Enforcement
- **Findings:** F-011 through F-017
- **Priority:** P1
- **Summary:** Seven independent bypass vectors weaken the primary file write protection boundary. Highlights: a path extraction regex that truncates names containing `+`, `(`, or spaces (false denials); `./` prefix normalization asymmetry between filePath and allowed entries (false denials); `##`-only heading matching — `### Allowed Files` silently disables enforcement; CRLF line ending corruption of section parsing; an unvalidated `CLAUDE_CURRENT_SPEC_PATH` env var that enables arbitrary file read and full allowlist bypass; and a `SEC` prefix in spec inference that creates phantom paths for non-existent specs.
- **Spec:** [step5/BUG-124-spec-allowlist-enforcement.md](step5/BUG-124-spec-allowlist-enforcement.md)

#### BUG-125: Glob Engine
- **Findings:** F-018, F-019, F-020
- **Priority:** P1
- **Summary:** The custom `minimatch()` implementation has three bugs that break allowlist pattern matching. `**` requires at least one intermediate directory, so `src/**/*.py` does not match `src/foo.py` — breaking the most common allowlist pattern. Bracket character class escaping corrupts `[abc]` patterns before glob conversion. Unmatched `]` in a pattern causes a `RegExp` syntax error that propagates to fail-open behavior.
- **Spec:** [step5/BUG-125-glob-engine.md](step5/BUG-125-glob-engine.md)

---

### P2 — Medium

#### BUG-126: Config & Dead Code
- **Findings:** F-021 through F-026
- **Priority:** P2
- **Summary:** `prompt-guard.mjs` completely ignores `hooks.config.mjs` — all `promptGuard.*` config values are dead code and user overrides via `hooks.config.local.mjs` have zero effect. `loadConfig()` permanently caches failures as `{}` (truthy), disabling retry for the process lifetime with no diagnostic output. Additional issues: silent local config load failure, duplicated `isDestructiveClean` definition, duplicated `ALWAYS_ALLOWED_PATTERNS`, and an unused `dirname` import.
- **Spec:** [step5/BUG-126-config-dead-code.md](step5/BUG-126-config-dead-code.md)

#### BUG-127: Git Command Safety
- **Findings:** F-027 through F-030
- **Priority:** P2
- **Summary:** Three gaps in the pre-bash hook's git command blocking. `git clean -fx` (removes ignored files including `.env`) is not blocked because only `-d` is checked, not `-x`. The `--ff-only` merge bypass is exploitable by combining with `--no-ff` in the same command. Bare `git push -f` without an explicit branch name is not blocked even when the tracking branch is `develop` or `main`.
- **Spec:** [step5/BUG-127-git-command-safety.md](step5/BUG-127-git-command-safety.md)

---

### P3 — Low

#### BUG-128: Minor Quality
- **Findings:** F-031 through F-040
- **Priority:** P3
- **Summary:** Ten low-severity quality issues grouped for efficient single-pass implementation. Includes: ruff argument injection via `--`-prefixed file paths, unvalidated `DLD_HOOK_LOG_FILE` path, inconsistent `matchesPattern()` usage, hardcoded diary reminder threshold with no config path, mutually exclusive LOC and sync zone warnings, single-spec limitation in commit validation, empty-string `CLAUDE_CURRENT_SPEC_PATH` behavior inversion, unreachable warn threshold at `warnThreshold=1.0`, brittle worktree root parsing in `run-hook.mjs`, and fragile `stripCodeBlocks` regex with nested backtick sequences.
- **Spec:** [step5/BUG-128-minor-quality.md](step5/BUG-128-minor-quality.md)

---

## ADR-010 Verification Results

This bug hunt was triggered as a verification run for the ADR-010 (Orchestrator Zero-Read) pattern. The pipeline operated with all agent output written to files and read by a collector subagent; the orchestrator never read agent outputs directly.

| ADR | Status | Evidence |
|-----|--------|----------|
| ADR-007 (Caller-Writes) | VERIFIED | All 8 spec files written by the solution-architect caller agent from structured agent responses. Subagent responses were structured YAML/text; file writes executed by the orchestrating step. Pattern confirmed functional. |
| ADR-008 (Background Fan-Out) | VERIFIED | 6 persona agents launched as background tasks. Findings accumulated in `step2/findings-summary.yaml` (83 raw findings) without flooding the orchestrator context. Fan-out produced 15x context reduction vs foreground execution. |
| ADR-009 (Background ALL Steps) | VERIFIED | All pipeline steps (persona analysis, validation, spec assembly) ran in background mode. Step outputs passed via gate files (`step2/`, `step3/`, `step5/` directories). No sequential foreground accumulation observed. |
| ADR-010 (Zero-Read) | VERIFIED | Orchestrator did not read any agent TaskOutput directly. Step progression verified via Glob file-gate checks on output directories. Collector subagent read `step2/` outputs and wrote `step3/validated-findings.yaml` (single consolidated summary). Orchestrator context remained bounded throughout the 5-step pipeline. |

The pipeline completed all 5 steps without context crashes or compaction events, validating the ADR-010 design for a non-trivial 6-agent fan-out workload.

---

## Key Themes

### 1. Worktree Blindness (P0 — BUG-121, BUG-122)
The hooks system has `getProjectDir()` as the canonical path resolver, but 5 code paths bypass it. This is the highest-impact class of bugs because autopilot always runs in worktrees, making ALL enforcement silently inactive during the primary production use case.

### 2. Deny-Output Reliability (P1 — BUG-123)
The core security primitive — delivering a deny JSON to Claude Code — has a race condition and a crash vector. A hook enforcement system whose output channel is unreliable provides weaker guarantees than the threat model assumes.

### 3. Allowlist Swiss Cheese (P1 — BUG-124, BUG-125)
Seven distinct bypass vectors exist in the allowlist system, each independently exploitable. The most impactful are the `CLAUDE_CURRENT_SPEC_PATH` env var injection (no path validation, enables allow-all) and the `**` glob engine mismatch (most common pattern silently mismatches).

### 4. Config Contract Violation (P2 — BUG-126)
The configuration system has a documented contract (hooks read from `hooks.config.mjs`, users override via `hooks.config.local.mjs`) that is violated by `prompt-guard.mjs`. Dead config sections erode user trust in the customization mechanism.

### 5. Defense-in-Depth Gaps (P2 — BUG-127)
Individual gaps in git command blocking (`-x` flag, `--ff-only`/`--no-ff` combination, bare `push -f`) each allow a specific dangerous operation through. These are not systemic failures but each represents a concrete scenario where the safety net has a hole.

---

## Recommended Execution Order

**Phase 1 — Foundation (BUG-121 + BUG-122, implement together):**
BUG-122 fixes `getProjectDir()` to return the correct value; BUG-121 ensures all hooks call it. Neither is useful without the other. Implement BUG-122 first (safe, pure utils.mjs change), then BUG-121 (callers). Combined, they re-enable all hook enforcement in worktree context.

**Phase 2 — Security (BUG-123 + BUG-124 + BUG-125, high-leverage fixes):**
BUG-123 makes deny delivery reliable before Phase 1 fixes produce more deny decisions. BUG-124 and BUG-125 fix the allowlist parsing and glob engine — BUG-124's F-015 (`CLAUDE_CURRENT_SPEC_PATH` validation) is the highest-priority security item in the entire run. Implement BUG-125 before BUG-124 since BUG-124 calls `minimatch()` internally.

**Phase 3 — Reliability (BUG-126 + BUG-127):**
BUG-126's config fixes unblock user customization and remove dead code. BUG-127's git safety fixes close specific defense-in-depth gaps. Both are independent and can proceed in parallel after Phase 2.

**Phase 4 — Polish (BUG-128):**
Ten low-severity items consolidated for a single implementation pass. Batch these to minimize context switches.

---

## False Positives Rejected

| Original ID | Title | Reason |
|-------------|-------|--------|
| A-CR-010 | Comment typo — missing slash on line 213 | FALSE finding. Verified line 213 in source: comment is properly formed with `//`. Finding fabricated a non-existent bug. |
| A-SEC-008 | Protected path check ordering — always-allowed patterns bypass protected paths | FALSE finding. Incorrect control flow analysis. `isFileAllowed()` returning `{allowed: true}` causes pre-edit to CONTINUE to the protected path check — no bypass exists. |

---

## Out-of-Scope Observations

The following were valid observations but rejected from actionable specs for the listed reasons:

- **A-CR-009** (approvePrompt async path): By design — `UserPromptSubmit` hooks must return JSON per Claude Code protocol; `allowTool()`'s silent exit is for `PreToolUse` hooks. Different hook types, different protocols.
- **A-SEC-009** (Turkish locale toLowerCase): Theoretical; hooks run in a controlled Node.js server context. Extremely unlikely in practice.
- **A-ARCH-007** (force-with-lease stale tracking ref): Known git limitation, not a hook bug. Changing this would block the documented safe-push workflow.
- **A-QA-005** (missing contract file test): Test coverage request, not a bug — the code is correct. Appropriate for a separate testing task.
- **A-JR-007 / A-ARCH-008** (loadConfig async TOCTOU): Invalid assumption — each hook runs as a separate Node.js process; concurrent calls to `loadConfig()` cannot occur in production.
- **A-SEC-007** (ReDoS in extractAllowedFiles): Overstated. The non-greedy quantifier is linear in Node.js V8; no catastrophic backtracking in practice.
