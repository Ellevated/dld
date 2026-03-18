# Feature: [TECH-157] Immediate OpenClaw wake after pending-event write
**Status:** queued | **Priority:** P1 | **Date:** 2026-03-18

## Why
After autopilot/qa/reflect completion, pueue-callback.sh writes a JSON event file to `ai/openclaw/pending-events/`. OpenClaw only picks these up via cron scan (every 5 minutes). This creates up to 5 minutes of lag before cycle completion is reported to the user. With 3 sequential skills (autopilot -> QA -> reflect), total cron lag can reach 15 minutes.

## Context
- Step 6.8 in pueue-callback.sh already writes pending-event files correctly
- OpenClaw has a cron job (`dld-openclaw-artifact-check`) that scans every 5 min
- The cron scan is idempotent (renames processed files to `processed-events/`)
- We need a push notification to reduce latency, keeping cron as fallback

---

## Scope
**In scope:**
- Add `openclaw system event --mode now` call after event file write in pueue-callback.sh
- Wrap with `timeout 5` to prevent callback hang
- Use full binary path to solve systemd PATH issue
- Log wake attempt to CALLBACK_LOG

**Out of scope:**
- Replacing cron with inotifywait or FIFO
- Changes to OpenClaw itself
- Changes to orchestrator.sh
- Multi-project wake scoping (only dld has OpenClaw job currently)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP -- who uses?
- `setup-vps.sh` registers pueue-callback.sh as pueue callback
- Pueue daemon fires it on every task completion
- `dependencies.md` documents it

### Step 2: DOWN -- what depends on?
- `db.py` (get_project_state)
- `notify.py` (Telegram notification)
- `pueue CLI` (status, log, add)
- `openclaw CLI` (NEW dependency: `~/.npm-global/bin/openclaw`)

### Step 3: BY TERM -- grep entire project
- `grep -rn "openclaw" scripts/vps/` -> 3 files: pueue-callback.sh (Step 6.8), openclaw-artifact-scan.py, tests/test_artifact_scan.py
- Zero existing usage of `openclaw system event` in codebase (net-new call)

### Step 4: CHECKLIST -- mandatory folders
- [x] `tests/**` -- No unit tests for pueue-callback.sh (bash script, no test infra)
- [x] `db/migrations/**` -- N/A
- [x] `ai/glossary/**` -- N/A

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old term = N/A (additive change, no renames)

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `scripts/vps/pueue-callback.sh` -- add wake call after event file write

**New files allowed:**
- None

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/)
**Cross-cutting:** Fail-safety (all callback operations must be non-fatal)
**Data model:** No schema changes

---

## Approaches

### Approach 1: Direct CLI with timeout + full path (based on codebase + patterns + devil scouts)
**Source:** [Shell Scripting Best Practices](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view)
**Summary:** Call `timeout 5 /path/to/openclaw system event --mode now` directly after event file write, with `|| true` fail-safe and CALLBACK_LOG redirect. Uses full binary path to bypass systemd PATH issue.
**Pros:** Simple (5 lines), matches existing callback patterns (notify.py call), timeout prevents hang, cron stays as fallback
**Cons:** Adds up to 5s latency to callback if openclaw is slow (bounded by timeout)

### Approach 2: Background subshell with timeout (based on patterns scout)
**Source:** [Bash Background Processes](https://oneuptime.com/blog/post/2026-01-24-bash-background-processes/view)
**Summary:** `(timeout 5 openclaw ... || true) &` -- detach to background so callback exits immediately.
**Pros:** Zero callback latency
**Cons:** Pueue SIGHUP risk -- when callback exits, pueue may kill the session group before background process completes (documented pueue pitfall)

### Approach 3: Direct HTTP ping via curl (based on devil scout)
**Source:** Devil scout analysis of openclaw.json gateway config
**Summary:** `curl -s --max-time 3 -X POST http://localhost:18789/wake` -- bypass CLI entirely
**Pros:** curl always on PATH, max-time protects against hang
**Cons:** Gateway REST endpoint path is undocumented, may not exist

### Selected: 1
**Rationale:** Direct CLI with timeout is the simplest, safest approach. It matches the existing callback pattern (notify.py uses identical structure). The `timeout 5` wrapper handles the devil scout's critical finding about 120s gateway timeouts. Full binary path resolves the PATH issue. If the 5s callback latency proves problematic in practice, switching to Approach 2 is a 1-character change (add `&`).

---

## Design

### User Flow
1. Autopilot/QA/Reflect completes -> Pueue fires callback
2. Step 6.8 writes event JSON to `ai/openclaw/pending-events/`
3. **NEW:** Immediately after file write, call `openclaw system event --mode now` with timeout
4. OpenClaw wakes, reads pending-events, reports cycle completion to user
5. If wake fails -> cron picks up event within 5 min (existing fallback, unchanged)

### Architecture
No architectural change. Additive 5-line block inside existing Step 6.8 `if` block.

### Code Change

After line 324 (closing `EOF` of heredoc), before the closing `fi` on line 325:

```bash
        # Wake OpenClaw immediately so it reports cycle completion without cron lag
        OPENCLAW_BIN="${HOME}/.npm-global/bin/openclaw"
        if [[ -x "$OPENCLAW_BIN" ]]; then
            timeout 5 "$OPENCLAW_BIN" system event --mode now 2>>"$CALLBACK_LOG" || true
            echo "[callback] OpenClaw wake sent for ${SKILL} event (project=${PROJECT_ID})" >> "$CALLBACK_LOG"
        fi
```

### Database Changes
None

---

## UI Event Completeness (REQUIRED for UI features)

N/A -- no UI elements.

---

## Implementation Plan

### Research Sources
- [Shell Scripting Best Practices](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view) -- fail-safe `|| true` pattern
- [Timeout Handling in Bash](https://coderlegion.com/12372/timeout-handling-in-bash-preventing-hanging-scripts-in-production) -- bounding synchronous CLI calls

### Task 1: Add OpenClaw wake call to pueue-callback.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/pueue-callback.sh`
**Pattern:** [Timeout + fail-safe pattern](https://coderlegion.com/12372/timeout-handling-in-bash-preventing-hanging-scripts-in-production)
**Acceptance:**
  - Wake call is placed AFTER `cat > "$EVENT_FILE"` heredoc (line 324) and BEFORE closing `fi` (line 325)
  - Uses full path `${HOME}/.npm-global/bin/openclaw` (not bare `openclaw`)
  - Wrapped with `timeout 5` to prevent hang
  - Guarded with `[[ -x "$OPENCLAW_BIN" ]]` to handle missing binary gracefully
  - Logged to `$CALLBACK_LOG`
  - `|| true` ensures callback never fails due to wake
  - File stays under 420 LOC (currently 411, adding ~5 lines)

### Execution Order
1

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Autopilot/QA/Reflect completes | - | existing |
| 2 | Callback writes event JSON | - | existing |
| 3 | Wake call fires immediately after | Task 1 | new |
| 4 | OpenClaw processes event | - | existing (OpenClaw side) |
| 5 | Cron fallback if wake fails | - | existing |

**GAPS:** None

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Wake fires after event file write | skill=autopilot, STATUS=done | CALLBACK_LOG contains "OpenClaw wake sent" | deterministic | devil DA-3 | P0 |
| EC-2 | Wake NOT fired when no event written | skill=spark, STATUS=done | No "OpenClaw wake" in CALLBACK_LOG | deterministic | devil DA-4 | P0 |
| EC-3 | Missing binary handled gracefully | OPENCLAW_BIN points to non-existent path | Callback exits 0, no "OpenClaw wake sent" log | deterministic | devil DA-1 | P0 |
| EC-4 | Timeout prevents hang | openclaw binary hangs (simulated) | Callback completes within 10s (5s timeout + overhead) | deterministic | devil DA-2 | P1 |
| EC-5 | QA skill also triggers wake | skill=qa, STATUS=done | CALLBACK_LOG contains "OpenClaw wake sent for qa" | deterministic | codebase scout | P1 |
| EC-6 | Reflect skill also triggers wake | skill=reflect, STATUS=done | CALLBACK_LOG contains "OpenClaw wake sent for reflect" | deterministic | codebase scout | P1 |
| EC-7 | Failed QA (STATUS=failed) triggers wake | skill=qa, STATUS=failed | Wake fires (Step 6.8 condition includes failed QA) | deterministic | codebase scout | P1 |
| EC-8 | Callback exit code remains 0 | openclaw returns exit 1 | Callback exits 0 (|| true) | deterministic | devil DA-8 | P2 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 | LLM-Judge: 0 | Total: 8 (min 3)

### TDD Order
1. EC-1 (happy path) -> EC-2 (negative) -> EC-3 (missing binary) -> EC-4 (timeout)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Callback script syntax valid | `bash -n scripts/vps/pueue-callback.sh` | exit 0 | 5s |
| AV-S2 | File under LOC limit | `wc -l scripts/vps/pueue-callback.sh` | <= 420 lines | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Wake call present in Step 6.8 | File modified | `grep "openclaw" scripts/vps/pueue-callback.sh` | Shows "system event --mode now" |
| AV-F2 | Timeout wrapper present | File modified | `grep "timeout 5" scripts/vps/pueue-callback.sh` | Shows timeout before openclaw call |
| AV-F3 | Full path used | File modified | `grep "npm-global/bin/openclaw" scripts/vps/pueue-callback.sh` | Shows full binary path |
| AV-F4 | Guard present | File modified | `grep -x ".*-x.*OPENCLAW_BIN" scripts/vps/pueue-callback.sh` | Shows executable check |

### Verify Command (copy-paste ready)

```bash
# Smoke
bash -n scripts/vps/pueue-callback.sh && echo "syntax OK"
wc -l scripts/vps/pueue-callback.sh | awk '{if ($1 <= 420) print "LOC OK: "$1; else print "LOC EXCEEDED: "$1}'
# Functional
grep -n "system event --mode now" scripts/vps/pueue-callback.sh
grep -n "timeout 5" scripts/vps/pueue-callback.sh
grep -n "npm-global/bin/openclaw" scripts/vps/pueue-callback.sh
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [x] Wake call fires after event file write for autopilot/qa/reflect
- [x] Wake does NOT fire when no event file is written
- [x] Missing binary handled gracefully (no crash)
- [x] Timeout prevents callback hang

### Tests
- [x] All eval criteria from Eval Criteria section pass
- [x] Coverage not decreased (no existing tests for bash callback)

### Acceptance Verification
- [x] All Smoke checks (AV-S*) pass locally
- [x] All Functional checks (AV-F*) pass locally
- [x] Verify Command runs without errors

### Technical
- [x] Tests pass (bash -n syntax check)
- [x] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
