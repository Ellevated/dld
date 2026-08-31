# Bug: [BUG-199] Autopilot scope creep — session does not stop on spec done, commits out-of-scope work to develop

**Priority:** P1 | **Date:** 2026-06-13

> **Lifecycle state** is tracked in `ai/lifecycle/BUG-199.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.

## Why

Incident 2026-06-13 (pueue #574, `awardybot:FTR-1185`, Ozon product-card parser): after the autopilot session finished FTR-1185 and merged it back to develop (`8eb4202d`), it did **not stop**. It continued in the same session and committed **unrelated** work to develop — `flows/cb-wb-end.yaml` (200 LOC WB-cashback template) + changes to `scripts/create_flow_campaign.py` + `tests/architecture/test_flows_artefacts_packaged.py` — as commit `5196867e` (12:54:23), **pushed to origin/develop**. None of those files are in FTR-1185's `## Allowed Files`. Out-of-scope work landed on develop under the wrong spec's session, past the implementation guard, and the session then wedged (see TECH-198).

This is both a **cost** problem (paying Opus to do unbudgeted work) and a **governance/integrity** problem (R1): code reaches develop attributed to an unrelated spec, the per-spec `## Allowed Files` contract is violated silently, and the callback gate can be fooled into marking a spec `done` on commits that touched files outside its allowlist.

## Context — two independent root causes (both verified)

**Root cause A — the prompt does not force a hard STOP after the spec's tasks are done.**
- The orchestrator **always** dispatches `/autopilot SPEC_ID` (loop mode) — `orchestrator.py:768` (scan_queued dispatch).
- Loop mode is *documented* to exit: `SKILL.md:35,201` and `finishing.md:81-86` ("Exit after completion — do NOT continue to next spec"; "EXIT … External orchestrator provides fresh context").
- But the same `SKILL.md` also carries an **interactive-mode** flow — `SKILL.md:165-192`: `while (queued/resumed tasks in ai/backlog.md): … 7. Continue to next spec` — with **no exit condition** ("if queue empty → stop" is absent), and `finishing.md:88-90` phrases continuation as a directive. The two modes share one prompt; the "continue to next / keep working while there's queue" framing can leak into a loop-mode session and license the model to find more work after `task_status` should have been emitted. There is **no structural gate** that blocks doing further work once the dispatched spec's tasks are complete.

**Root cause B — the pre-edit Allowed-Files guard is a no-op once the session is on develop.**
- The real *prevention* layer is the hook: `pre-edit.mjs:142-162` hard-denies edits to files outside `## Allowed Files` — **but only when a spec can be resolved**: `const specPath = process.env.CLAUDE_CURRENT_SPEC_PATH || inferSpecFromBranch()` (`pre-edit.mjs:143`). If no spec resolves, `isFileAllowed` imposes no restriction → edits pass.
- `run-agent.sh` does **not** export `CLAUDE_CURRENT_SPEC_PATH` (only `SKIP`, `:50`). The orchestrator sets `CLAUDE_CURRENT_SPEC_PATH` **only for inbox dispatch** (`orchestrator.py:681`, `done_file`), **not** for the autopilot scan_queued dispatch (`orchestrator.py:768`). So in autopilot loop mode the hook falls back to `inferSpecFromBranch()`.
- While on the worktree branch `feature/FTR-1185`, `inferSpecFromBranch()` can resolve FTR-1185 → allowlist enforced. **But after merge-back the session is on `develop`**, where `inferSpecFromBranch()` resolves nothing → `specPath` null → allowlist check is **skipped** → out-of-scope edits to `flows/cb-wb-end.yaml` etc. pass freely. This is precisely the window the cb-wb-end commit (12:54, post-merge, on develop) exploited.
- The **callback** guard is post-factum and allowlist-scoped only: `callback._commit_stats` / `_is_done_on_develop` run `git log … -- <allowed>` (`callback.py:~608-670`, `~1126-1152`) — they **count** commits on allowed files and check for a `SPEC_ID` subject, but never inspect whether a commit *also* touched files outside the allowlist. So out-of-scope commits are neither blocked nor flagged.

Net: the prompt permits continuing, and the only hard guard (pre-edit hook) is disabled on develop — so unbudgeted work flows straight to origin.

---

## Scope

**In scope:**
- **Fix A (prompt — hard stop):** make loop-mode termination unambiguous and structural. After the dispatched spec's tasks complete and `task_status` is emitted, the session MUST EXIT — do **not** scan backlog, do **not** pick another spec, do **not** start unrelated work. Remove/guard the "continue to next spec" framing so it cannot leak into a `SPEC_ID`-dispatched (loop-mode) session. Mirror to `template/.claude/`.
- **Fix B (guard — keep allowlist enforced on develop):** ensure the pre-edit Allowed-Files hook stays effective for the dispatched spec for the whole session, including after merge-back to develop. Make the dispatched spec resolvable independent of branch — e.g. orchestrator/run-agent exports `CLAUDE_CURRENT_SPEC_PATH` (or an equivalent `CLAUDE_AUTOPILOT_SPEC_ID`) for autopilot dispatch, and `pre-edit.mjs` prefers it over branch inference. (Investigate the cleanest of: env var from dispatch vs. a session-pinned spec marker.)
- **Fix C (callback — surface out-of-scope, optional/secondary):** decide whether the callback gate should *flag* (not silently ignore) commits that touch files outside the allowlist for the dispatched spec, as a detection backstop. Scope this as analysis + a low-risk warning/telemetry only — NOT a new hard block on the status writer (R0-adjacent; do not risk false `blocked`).
- Regression tests for A and B; real deps, no mocks (ADR-013).

**Out of scope:**
- The SDK wedge / zombie slot — separate spec **TECH-198**.
- Reworking interactive-mode autopilot UX broadly — only the loop-mode/interactive bleed-through that licenses scope creep.
- Changing the callback status-writer contract or gate semantics (ADR-023/025) — Fix C must not introduce a new `done→blocked` hard path.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `.claude/skills/autopilot/SKILL.md` + `finishing.md` — consumed by the autopilot SDK session prompt; mirrored in `template/.claude/`. ✓
- `pre-edit.mjs` — Claude Code PreToolUse hook (Edit/Write) for all sessions in the project. ✓
- `orchestrator.py` autopilot dispatch (`:768`) — the env-var wiring point for Fix B. ✓
- `run-agent.sh` — provider dispatcher between orchestrator and claude-runner; alt env-wiring point. ✓

### Step 2: DOWN — what depends on?
- Fix A → prompt-only (no code deps).
- Fix B → `pre-edit.mjs` spec resolution; `orchestrator.py`/`run-agent.sh` env passthrough (claude-runner already forwards `CLAUDE_CURRENT_SPEC_PATH`, `claude-runner.py:204`).
- Fix C → `callback._commit_stats` / `_parse_allowed_files`; read-only git inspection.

### Step 3: BY TERM
- `CLAUDE_CURRENT_SPEC_PATH` → `pre-edit.mjs:143`, `claude-runner.py:204`, `orchestrator.py:681` (inbox only). Fix B adds the autopilot dispatch site.
- `inferSpecFromBranch` → `pre-edit.mjs` (fallback). Behaviour on develop is the gap.
- `Continue to next spec` → `SKILL.md:~192`, `finishing.md:88-90`. Fix A target.

### Step 4: CHECKLIST
- Template sync: every `.claude/skills/autopilot/` edit mirrors to `template/.claude/skills/autopilot/` (template-sync.md). ✓
- Tests: `scripts/vps/tests/` (env wiring) + a hook-behaviour test for `pre-edit.mjs` if a harness exists; else a documented manual check. ✓
- `dependencies.md`: update run-agent.sh / orchestrator env-passthrough notes if Fix B touches them. ✓

### Step 5: DUAL SYSTEM
- Spec resolution has two sources (env var vs branch inference). Fix B must make them consistent so the allowlist source is stable across the merge-back branch switch.

---

## Approaches

**Fix A.** Add an explicit, structural STOP at the top of the loop-mode finish path: "If invoked with a SPEC_ID (loop mode), after emitting `task_status` you MUST EXIT immediately. Do NOT read the backlog, pick another spec, or start work not in this spec's `## Allowed Files`. The orchestrator dispatches the next spec with fresh context." Guard the interactive "continue" block behind an explicit "interactive mode only (no SPEC_ID)" condition so it cannot apply to dispatched sessions.

**Fix B — where to pin the spec.** Preferred: orchestrator autopilot dispatch (`:768`) passes the spec id/path into the env (mirroring the inbox path at `:681`), `run-agent.sh` forwards it, claude-runner already passes `CLAUDE_CURRENT_SPEC_PATH` through, and `pre-edit.mjs` prefers the env value over branch inference. This keeps the allowlist anchored to the **dispatched** spec regardless of the current branch (feature branch or develop). Rejected alt: making `inferSpecFromBranch` "remember" the last feature branch — fragile and stateful.

**Fix C.** Analysis-first. Add a *warning-level* signal (log/telemetry/Hermes) in callback when commits attributed to the spec window touched files outside the allowlist — visibility, not enforcement. Do not gate status on it.

---

## Tasks

1. **Fix A — prompt hard stop** (`SKILL.md`, `finishing.md` + template mirrors): explicit loop-mode EXIT after `task_status`; scope-guard the interactive "continue to next spec" flow.
2. **Fix B — spec pinning for the hook** (`orchestrator.py` autopilot dispatch + `run-agent.sh` passthrough + `pre-edit.mjs` prefer-env): ensure the dispatched spec's `## Allowed Files` is enforced for the whole session, including after merge-back to develop.
3. **Fix C — out-of-scope detection (warning only)** (`callback.py`): investigate + add low-risk telemetry/warning for commits touching files outside the dispatched spec's allowlist. No new status hard-block.
4. **Tests** (`scripts/vps/tests/`): Fix B env wiring (autopilot dispatch sets the spec env var; `pre-edit` would resolve a spec on develop); Fix A prompt assertions if testable; Fix C detection unit test. Real deps (ADR-013).
5. **Docs**: `dependencies.md` env-passthrough note; `ai/reflect/upstream-signals.md` signal on the prompt/guard dual gap.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `.claude/skills/autopilot/SKILL.md` — Task 1: loop-mode hard STOP + interactive guard (modify)
- `.claude/skills/autopilot/finishing.md` — Task 1: exit-after-task_status, no continue in loop mode (modify)
- `template/.claude/skills/autopilot/SKILL.md` — Task 1: template sync (modify)
- `template/.claude/skills/autopilot/finishing.md` — Task 1: template sync (modify)
- `.claude/hooks/pre-edit.mjs` — Task 2: prefer env spec path over branch inference (modify)
- `scripts/vps/orchestrator.py` — Task 2: export spec env var on autopilot dispatch (modify)
- `scripts/vps/run-agent.sh` — Task 2: forward spec env var (modify)
- `scripts/vps/callback.py` — Task 3: out-of-scope-commit warning/telemetry (modify)
- `scripts/vps/tests/test_autopilot_scope_guard.py` — Task 4: env-wiring + detection tests (create)
- `.claude/rules/dependencies.md` — Task 5: env-passthrough docs (modify)
- `ai/reflect/upstream-signals.md` — Task 5: dual-gap signal (modify)

---

## Tests

1. **Fix B — autopilot dispatch sets the spec env var.** Drive `orchestrator` autopilot dispatch (scan_queued path) and assert the pueue add / run-agent invocation carries `CLAUDE_CURRENT_SPEC_PATH` (or the chosen var) pointing at the dispatched spec.
2. **Fix B — hook resolves spec independent of branch.** With the env var set, `pre-edit` spec resolution returns the dispatched spec even when the working branch is `develop` (no feature branch) — so an out-of-allowlist edit is denied. (Real hook invocation if a harness exists; else a focused unit test of the resolution function.)
3. **Fix B — out-of-scope edit denied on develop.** Given a spec with a small `## Allowed Files` and a session on develop, an edit to a non-listed file is blocked by the hook.
4. **Fix C — out-of-scope commit flagged.** Given commits in the spec window where one touches a file outside the allowlist, the callback emits the warning/telemetry signal (and does NOT mark the spec `blocked` solely because of it).
5. **Fix A — loop-mode prompt asserts exit.** Lightweight check that `finishing.md`/`SKILL.md` loop-mode path contains the explicit EXIT directive and the interactive continue block is guarded by a no-SPEC_ID condition (doc-lint style assertion).

---

## Blueprint Reference

Infrastructure governance (DLD orchestrator / autopilot execution contract). Enforces the per-spec `## Allowed Files` boundary end-to-end (prompt discipline + hook prevention + callback detection). Relates to TECH-167 (canonical Allowed Files), ADR-024 (front-side guard), and TECH-198 (same incident, separate failure surface).
