# Bug Fix: [BUG-164] callback.py pueue socket mismatch — empty agent output

**Status:** queued | **Priority:** P0 | **Risk:** R1 | **Date:** 2026-03-20

## Symptom

callback.py logs `agent output: skill= preview_len=0` for every completed task.
QA and Reflect never dispatch because `skill != "autopilot"` and `spec_id` is never resolved.

## Root Cause (5 Whys Result)

**Why 1:** Why is skill empty in callback?
→ `extract_agent_output()` returns `("", "")`.

**Why 2:** Why does `extract_agent_output()` return empty?
→ `pueue log <id> --json` returns no task data (task not found in pueue's status).

**Why 3:** Why is the task not found?
→ `pueue log` connects to the **user** pueued socket (`/run/user/1000/pueue.sock`), but tasks were submitted to the **root** pueued socket.

**Why 4:** Why are sockets different?
→ `orchestrator.py` runs as systemd service which may inherit a different `XDG_RUNTIME_DIR` / `PUEUE_CONFIG_DIR` than the callback's `pueue` CLI subprocess.

**Why 5:** Why not just fix the socket path?
→ Fragile — depends on runtime environment. Better to eliminate pueue CLI dependency entirely. `claude-runner.py` already writes structured JSON logs to `scripts/vps/logs/` and `task_log` DB table already stores `pueue_id → project_id, task_label, skill`.

**ROOT CAUSE:** `callback.py` uses `pueue` CLI for data that's already available from other sources (log files + SQLite). Socket mismatch makes pueue CLI unreliable.

## Reproduction Steps

1. Orchestrator dispatches autopilot task via pueue
2. Task completes, pueue triggers callback
3. callback.py calls `pueue log <id> --json` — returns empty/wrong data
4. Expected: `skill=autopilot preview_len>0`, Got: `skill= preview_len=0`
5. QA and Reflect are not dispatched

## Fix Approach

Eliminate `pueue` CLI dependency in callback.py for data retrieval. Use existing data sources:

### 1. `resolve_label()` → DB-first (task_log table)

**Current:** `pueue status --json` → parse task label
**New:** Query `task_log WHERE pueue_id = ?` → get `task_label` directly

Add `get_task_by_pueue_id(pueue_id)` to `db.py`:
```python
def get_task_by_pueue_id(pueue_id: int) -> Optional[dict]:
    """Get task_log entry by pueue_id. Returns dict with project_id, task_label, skill."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT project_id, task_label, skill FROM task_log "
            "WHERE pueue_id = ? ORDER BY id DESC LIMIT 1",
            (pueue_id,),
        ).fetchone()
        return dict(row) if row else None
```

### 2. `extract_agent_output()` → Read log files

**Current:** `pueue log <id> --json` → parse stdout for JSON with skill/preview
**New:** Find log file in `scripts/vps/logs/` by project_name, read JSON directly

Algorithm:
1. Get `project_id` from `resolve_label()` (now DB-based)
2. Get `project_path` from `db.get_project_state(project_id)`
3. Derive `project_name = Path(project_path).name`
4. Find most recent `logs/{project_name}-*.log` file (by mtime)
5. Parse JSON → return `(skill, result_preview)`

Fallback chain: log file → pueue log → ("", "")

### 3. `resolve_label()` fallback chain

```
DB (task_log) → pueue status --json → "unknown"
```

Keep pueue as fallback for edge cases (e.g., task not in DB yet).

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] `resolve_label()` called by `main()` at line 265
- [x] `extract_agent_output()` called by `main()` at line 302
- [x] `is_already_queued()` called by `dispatch_qa()` and `dispatch_reflect()` — NOT changing (dedup check needs live pueue state)

### Step 2: DOWN — what depends on?
- [x] `db.py` — adding new function `get_task_by_pueue_id()`
- [x] Log files at `scripts/vps/logs/` — read-only access
- [x] `pueue` CLI — kept as fallback only

### Step 3: BY TERM — grep entire project

| File | Line | Status | Action |
|------|------|--------|--------|
| callback.py:62-73 | resolve_label() | FIX | DB-first with pueue fallback |
| callback.py:92-121 | extract_agent_output() | FIX | Log file reader |
| callback.py:153-168 | is_already_queued() | KEEP | Still needs live pueue state |

### Verification
- [x] All found files added to Allowed Files

## Tests

### Deterministic

1. **test_resolve_label_from_db**: Mock db.get_task_by_pueue_id returning task_label → assert correct label returned without pueue CLI call
2. **test_resolve_label_fallback_to_pueue**: DB returns None → falls back to pueue status → returns label
3. **test_extract_agent_output_from_logfile**: Create temp log file with JSON → assert skill and preview extracted correctly
4. **test_extract_agent_output_no_logfile**: No matching log → returns ("", "")
5. **test_get_task_by_pueue_id_found**: Insert task_log row → query by pueue_id → returns correct dict
6. **test_get_task_by_pueue_id_not_found**: Query non-existent pueue_id → returns None

### Integration

7. **test_callback_full_flow_without_pueue**: End-to-end: insert task_log + create log file → run callback main → verify QA dispatch attempted (mock _pueue_add only)

## Allowed Files

1. `scripts/vps/callback.py` — rewrite resolve_label() and extract_agent_output()
2. `scripts/vps/db.py` — add get_task_by_pueue_id() function
3. `tests/scripts/test_callback.py` — regression tests (create if not exists)
4. `tests/scripts/test_db.py` — test for get_task_by_pueue_id (create if not exists)

## Definition of Done

- [x] Root cause fixed (pueue CLI eliminated for data retrieval)
- [x] `resolve_label()` uses DB-first approach
- [x] `extract_agent_output()` reads from log files
- [x] `get_task_by_pueue_id()` added to db.py
- [x] Fallback chain preserved (DB → pueue → default)
- [x] Regression tests added
- [x] callback.py stays under 400 LOC
- [x] No new failures

## Blueprint Reference

- **Domain:** scripts/vps (orchestrator infrastructure)
- **ADR-017:** SQL only via Python parameterized queries — new db.py function complies
- **Dependencies:** callback.py → db.py (existing), callback.py → logs/ (new read-only)
