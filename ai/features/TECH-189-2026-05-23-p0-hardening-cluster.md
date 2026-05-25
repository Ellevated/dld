# TECH-189 — P0 hardening cluster — callback/lifecycle/orchestrator contour (post-/architect)

**Status:** queued
**Priority:** P0
**Risk:** R1 (multi-file, multi-domain: scripts/vps/* + tests/ + .claude/ + pyproject.toml)
**Kind:** tech
**Date:** 2026-05-23
**Branch:** `tech/TECH-189-p0-hardening`
**Estimated execution:** ~2-3 hours autopilot
**Compute estimate:** ~$15

---

## Context

Post-/architect retrofit session on the callback/lifecycle/orchestrator contour. Deep audit found 85 issues, 8 personas converged on 10 independent P0 fixes. Architect chose Alternative C (Decouple & Defer) for the structural refactor. This spec implements 9 of those 10 P0 items (TELEGRAM_BOT_TOKEN rotation deferred to separate spec — operational distraction, not status-flipping root cause). The 9 items are:

1. Independent of architecture choice (A/B/C)
2. Reversible (no SoR migration, no new daemons)
3. High-ROI (each prevents a documented incident class)
4. Small (1-5 LOC each, most are surgical)

These 10 items are the **prerequisite gate** before Wave 1 of Alt C begins.

**Source:** `ai/architect/architectures.md` section "Recommended P0 — Independent of A/B/C"
**Audit source:** `ai/audit/deep-audit-report.md` (85 findings)

---

## Scope

### IN SCOPE (this spec)

10 surgical P0 fixes numbered 1-10 below. No architectural changes.

### OUT OF SCOPE (separate specs, future waves)

- `lifecycle.py` architecture (Alt C Wave 1: gate-daemon extraction)
- `callback.py` decomposition into 5 modules (Alt C Wave 3)
- `bootstrap_new_specs` removal + Spark `lifecycle.create_initial` migration (Alt C Wave 4)
- Gate daemon creation (`gate-daemon.py` + systemd unit, Alt C Wave 1)
- `migrate_backlog_to_lifecycle.py` deletion (requires bootstrap removal first)

---

## The 10 P0 Tasks

---

### Task 1 — pyproject.toml: add scripts/vps/tests to testpaths

**File:** `pyproject.toml:19`
**Change size:** 1 LOC

**Current state:**
```toml
testpaths = ["tests"]
```

**Target state:**
```toml
testpaths = ["tests", "scripts/vps/tests"]
```

**Why P0:** ~100 lifecycle/orchestrator/callback tests currently invisible to CI. Every regression in `scripts/vps/` passes CI undetected. Confirmed root contributor to ARCH-186, BUG-185, BUG-188 incidents.

**Acceptance criteria:**
- `pytest --collect-only` shows test files from both `tests/` and `scripts/vps/tests/`
- `pytest` from root runs `scripts/vps/tests/test_lifecycle.py`, `test_callback.py`, `test_orchestrator.py`, `test_db.py` without error
- CI workflow includes both test suites

---

### Task 2 — tests/conftest.py: autouse DB-isolation fixture

**File:** `tests/conftest.py`
**Change size:** ~15 LOC (new fixture)

**Problem:** Currently `tests/conftest.py` has fixtures for hooks only (`mock_stdin`, `capture_stdout`, `mock_exit`). The `scripts/vps/tests/conftest.py` has `isolated_db` but it is NOT autouse — tests that forget to request it can pollute a shared prod-adjacent DB path.

**What to add:** A new `autouse=True` fixture at the ROOT `tests/conftest.py` level that overrides `DB_PATH` env var + `db.DB_PATH` attribute for every test session. This guarantees NO test can accidentally write to a real DB file, even if the test doesn't explicitly request `isolated_db`.

**Implementation:**
```python
@pytest.fixture(autouse=True)
def _db_isolation(tmp_path, monkeypatch):
    """Auto-isolate every test from the production DB.
    Overrides DB_PATH env var and db.DB_PATH attribute via monkeypatch.
    Tests in scripts/vps/tests/ inherit this via conftest chain.
    """
    db_path = tmp_path / "test_isolated.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    try:
        import db as db_mod  # only available when scripts/vps is in sys.path
        monkeypatch.setattr(db_mod, "DB_PATH", str(db_path))
    except ImportError:
        pass  # hooks tests don't have db — safe to skip
```

**Acceptance criteria:**
- Running `pytest tests/` does not create or modify any file outside `tmp_path`
- Existing hook tests still pass (fixture gracefully skips `ImportError` for db module)
- A test that calls `db.seed_projects_from_json(...)` without requesting `isolated_db` explicitly does NOT write to a prod DB path

---

### Task 3 — Zombie cleanup: spec_lint.py + DLD-CALLBACK-MARKER references

**Files:**
- `scripts/vps/spec_lint.py` (DELETE entire file)
- `template/.claude/skills/spark/completion.md:46` (remove DLD-CALLBACK-MARKER check from checklist item 6)
- `.claude/agents/spark/facilitator.md:218-221` (remove DLD_START_RE / DLD_END_RE lines)
- `.claude/skills/spark/completion.md:46` (same fix as template, per template-sync.md)

**Change size:** 1 file deleted (~100 LOC), 3 surgical line removals

**Why P0:** `spec_lint.py` validates `DLD-CALLBACK-MARKER` blocks that were DELETED in ARCH-186 (2026-05-16). It is an inverted fitness function — it would pass on old specs and fail on new correct specs. `completion.md:46` contains a checklist item requiring `DLD-CALLBACK-MARKER-START` markers that no longer exist in the spec template, causing Spark to output incorrect specs. `facilitator.md:218-221` has Phase 5.5 linter rules for DLD-CALLBACK-MARKER that are dead code after ARCH-186.

**What to remove from `completion.md:46`:**

Current line 46 (truncated):
```
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line, `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->' ai/features/{TASK_ID}*.md` returns ≥2 lines (Allowed Files + Status), and `## Allowed Files` heading exists exactly once
```

Replace with:
```
6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line and `## Allowed Files` heading exists exactly once
```

**What to remove from `facilitator.md:218-221`** (lines referencing DLD_START_RE / DLD_END_RE):

Remove the 4-line block:
```
   - `DLD_START_RE = ^<!--\s*DLD-CALLBACK-MARKER-START\s+v(?P<ver>\d+)\s*-->\s*$`
   - `DLD_END_RE   = ^<!--\s*DLD-CALLBACK-MARKER-END\s*-->\s*$`
   - section ends at next `^##[ \t]+\S` heading.
   - Verify `## Allowed Files` is enclosed in a DLD-CALLBACK-MARKER block with ver in {"1"}.
```

**Acceptance criteria:**
- `ls scripts/vps/spec_lint.py` exits non-zero (file deleted)
- `grep -r 'DLD-CALLBACK-MARKER' .claude/ template/.claude/` returns 0 matches
- `grep 'DLD_START_RE\|DLD_END_RE' .claude/agents/spark/facilitator.md` returns 0 matches
- Spark skill smoke test: create a minimal spec via `/spark` — completion checklist item 6 no longer references `DLD-CALLBACK-MARKER-START`

---

### Task 4 — BOOTSTRAP_ANOMALY threshold log in orchestrator.py

**File:** `scripts/vps/orchestrator.py:279-333` (`bootstrap_new_specs` function)
**Change size:** ~8 LOC (counter + warning + Hermes event)

**Why P0:** Today's incident (2026-05-23) involved `bootstrap_new_specs` creating 15 lifecycle YAMLs in one cycle during a backlog-write race, leading to 15 tasks being dispatched simultaneously and burning ~$258 in retries. The function has no anomaly detection. If it creates >3 YAMLs in one cycle, something is wrong (normal cycles create 0-1).

**What to add** (inside `bootstrap_new_specs`, after the for-loop):

```python
BOOTSTRAP_ANOMALY_THRESHOLD = 3  # >3 new lifecycle yamls in one cycle = anomaly

# ... existing for-loop that calls lifecycle.create_initial ...

created_count = 0  # increment inside the for-loop at create_initial call

# After for-loop:
if created_count > BOOTSTRAP_ANOMALY_THRESHOLD:
    log.warning(
        "BOOTSTRAP_ANOMALY: created %d lifecycle yamls in one cycle for %s "
        "(threshold=%d) — possible backlog-write race or bulk-import",
        created_count, project_dir, BOOTSTRAP_ANOMALY_THRESHOLD,
    )
    # Increment counter file for external monitoring
    counter_path = Path(project_dir) / "ai" / ".bootstrap-anomaly-count"
    try:
        prev = int(counter_path.read_text().strip()) if counter_path.is_file() else 0
        counter_path.write_text(str(prev + 1))
    except Exception:  # noqa: BLE001
        pass
    # Fire Hermes event
    try:
        from event_writer import notify
        notify(
            project_dir.split("/")[-1],
            f"BOOTSTRAP_ANOMALY: {created_count} lifecycle yamls in one cycle",
        )
    except Exception:  # noqa: BLE001
        pass
```

**Acceptance criteria:**
- `grep -n 'BOOTSTRAP_ANOMALY' scripts/vps/orchestrator.py` shows the warning call
- Unit test: mock `lifecycle.create_initial` to be called 5 times → assert `log.warning` called with "BOOTSTRAP_ANOMALY"
- Counter file `ai/.bootstrap-anomaly-count` incremented when threshold exceeded
- Normal case (1 new spec): no warning, no counter increment

---

### Task 5 — _push_best_effort: DEBUG → WARNING + counter

**File:** `scripts/vps/lifecycle.py:266`
**Change size:** 3 LOC

**Current state (`lifecycle.py:263-266`):**
```python
def _push_best_effort(repo_dir: str, branch: str) -> None:
    r = _run(["git", "push", "origin", branch], cwd=repo_dir)
    if r.returncode != 0:
        log.debug("push best-effort failed (ignored): %s", r.stderr.strip()[:200])
```

**Target state:**
```python
def _push_best_effort(repo_dir: str, branch: str) -> None:
    r = _run(["git", "push", "origin", branch], cwd=repo_dir)
    if r.returncode != 0:
        log.warning(
            "lifecycle push failed (best-effort, not fatal): branch=%s stderr=%s",
            branch, r.stderr.strip()[:200],
        )
        # Increment push-failure counter for monitoring
        counter = Path(repo_dir) / "ai" / ".lifecycle-push-failures"
        try:
            prev = int(counter.read_text().strip()) if counter.is_file() else 0
            counter.write_text(str(prev + 1))
        except Exception:  # noqa: BLE001
            pass
```

**Why P0:** `_push_best_effort` is called after every lifecycle status write. Silent DEBUG failures mean multi-machine convergence failures are invisible. A push failure means the lifecycle YAML is committed locally but not propagated. The WARNING level makes these visible in orchestrator logs and the counter enables monitoring.

**Acceptance criteria:**
- `grep -n 'log.warning' scripts/vps/lifecycle.py | grep push` shows the warning
- `grep -n 'log.debug.*push' scripts/vps/lifecycle.py` returns 0 matches
- Unit test: mock `_run` to return returncode=1 → assert `log.warning` called
- Counter file `ai/.lifecycle-push-failures` exists and increments on failure

---

### Task 6 — Add GROWTH to _SPEC_ID_RE in callback.py (and orchestrator.py)

**Files:**
- `scripts/vps/callback.py:43`
- `scripts/vps/orchestrator.py:299,305,308` (bootstrap_new_specs regex)

**Change size:** 2 LOC (one per file)

**Current state (`callback.py:43`):**
```python
_SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*")
```

**Target state:**
```python
_SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")
```

**Also fix `orchestrator.py:299,305,308`** — the `active_re` and `backlog_ids` regexes in `bootstrap_new_specs` also hardcode the same 4 prefixes without GROWTH. Backlog already has `GROWTH-001..006` entries. Any GROWTH-prefixed spec file will be silently skipped during bootstrap.

**Why P0:** The backlog already contains `GROWTH-001` through `GROWTH-006`. Callback will silently drop any pueue task labeled with a GROWTH spec ID. Orchestrator will never bootstrap lifecycle YAMLs for GROWTH specs. Both cause silent data loss.

**Acceptance criteria:**
- `grep '_SPEC_ID_RE' scripts/vps/callback.py` shows `GROWTH` in the pattern
- `grep -n 'TECH|FTR|BUG|ARCH' scripts/vps/orchestrator.py | grep -v GROWTH | grep 'compile\|re\.'` returns 0 (all spec-ID regexes include GROWTH)
- Unit test: callback with label `GROWTH-001:dld` → spec_id extracted correctly as `GROWTH-001`
- Unit test: `bootstrap_new_specs` with a `GROWTH-001-*.md` spec file → lifecycle YAML created

---

### Task 7 — lifecycle._run(): add timeout=30 to all 8 git plumbing calls

**File:** `scripts/vps/lifecycle.py:77-88` (`_run` function)
**Change size:** 1 LOC (add `timeout=30` parameter to `subprocess.run`)

**Current state (`lifecycle.py:77-88`):**
```python
def _run(
    cmd: list, *, cwd: str, env: Optional[dict] = None, input_text: Optional[str] = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )
```

**Target state:**
```python
def _run(
    cmd: list, *, cwd: str, env: Optional[dict] = None, input_text: Optional[str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
```

**Add timeout handling** at all call sites that catch `subprocess.run` exceptions — wrap `_run` calls in `lifecycle._cas_loop` and `_atomic_write` to catch `subprocess.TimeoutExpired`:

In `_cas_loop` and `_atomic_write`, add:
```python
except subprocess.TimeoutExpired as exc:
    log.warning("lifecycle git plumbing timeout (cmd=%s): %s", exc.cmd, exc)
    return False  # treat as CAS failure, will retry
```

**Why P0:** `lifecycle._run()` is called for all 8 git plumbing operations (hash-object, update-index, write-tree, commit-tree, update-ref, etc.) under `_write_lock`. A hung git process holds `_write_lock` indefinitely, blocking ALL lifecycle writes system-wide. Under load (orchestrator running 3 projects), this is a DoS vector. `timeout=30` is safe — git plumbing on local objects completes in <1s normally; 30s catches genuine hangs.

**Acceptance criteria:**
- `grep -n 'timeout' scripts/vps/lifecycle.py` shows `timeout=30` in `subprocess.run`
- Unit test: mock `subprocess.run` to raise `TimeoutExpired` → `_atomic_write` returns `False` (not raises)
- `_write_lock` is released on timeout (lock release happens via context manager — verify no change needed)
- Existing lifecycle tests still pass

---

### Task 8 — Heartbeat: orchestrator writes heartbeat file + cron monitor

**Files:**
- `scripts/vps/orchestrator.py` (add heartbeat write to main loop)
- `scripts/vps/heartbeat_monitor.py` (NEW, ~30 LOC)
- `scripts/vps/setup-vps.sh` (add cron entry for monitor)

**Change size:** ~5 LOC in orchestrator.py, ~30 LOC new file, ~3 LOC in setup-vps.sh

**Why P0:** Orchestrator hangs are invisible. Today's incident (2026-05-23) involved the orchestrator running but silently doing wrong work. A heartbeat file and external monitor would have fired a Hermes event within 10 minutes of the first anomaly.

**Heartbeat write (add to orchestrator.py `main()` loop, at end of each cycle):**
```python
# Write heartbeat at end of every cycle
heartbeat_path = SCRIPT_DIR / ".orchestrator-heartbeat"
try:
    heartbeat_path.write_text(_now_iso())
except Exception:  # noqa: BLE001
    log.warning("heartbeat write failed")
```

**heartbeat_monitor.py (new file):**
```python
#!/usr/bin/env python3
"""Heartbeat monitor — fires Hermes event if orchestrator heartbeat is stale.

Cron: */5 * * * * python3 /path/to/heartbeat_monitor.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
HEARTBEAT_FILE = SCRIPT_DIR / ".orchestrator-heartbeat"
STALE_THRESHOLD_MINUTES = 10


def main() -> None:
    if not HEARTBEAT_FILE.is_file():
        print("WARN: no heartbeat file found", file=sys.stderr)
        return
    last_beat_str = HEARTBEAT_FILE.read_text().strip()
    try:
        last_beat = datetime.fromisoformat(last_beat_str.replace("Z", "+00:00"))
    except ValueError:
        print(f"WARN: unparseable heartbeat: {last_beat_str}", file=sys.stderr)
        return
    age = datetime.now(tz=timezone.utc) - last_beat
    if age > timedelta(minutes=STALE_THRESHOLD_MINUTES):
        print(f"ALERT: orchestrator heartbeat stale ({age})", file=sys.stderr)
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from event_writer import notify
            notify("dld", f"ORCHESTRATOR_STALE: last heartbeat {age} ago")
        except Exception as exc:
            print(f"WARN: could not fire Hermes event: {exc}", file=sys.stderr)


if __name__ == "__main__":
    main()
```

**setup-vps.sh addition** (in cron section):
```bash
# Heartbeat monitor — check orchestrator liveness every 5 min
(crontab -l 2>/dev/null; echo "*/5 * * * * python3 ${SCRIPT_DIR}/heartbeat_monitor.py >> /var/log/dld-heartbeat.log 2>&1") | crontab -
```

**Acceptance criteria:**
- After one orchestrator poll cycle: `cat scripts/vps/.orchestrator-heartbeat` shows ISO timestamp within last 5 minutes
- `python3 scripts/vps/heartbeat_monitor.py` exits 0 when heartbeat is fresh
- Unit test: write a stale timestamp (>10min ago) to heartbeat file → monitor calls `notify()` with "ORCHESTRATOR_STALE"
- `crontab -l | grep heartbeat_monitor` shows cron entry after setup-vps.sh runs

---

### Task 9 — Fix reconcile_orphans identity attribution: by="orchestrator"

**File:** `scripts/vps/lifecycle.py:551`
**Change size:** 1 LOC

**Current state:**
```python
write_lifecycle(repo_dir, spec_id, "queued", reason="orphaned from crash", by="callback")
```

**Target state:**
```python
write_lifecycle(repo_dir, spec_id, "queued", reason="orphaned from crash", by="orchestrator")
```

**Why P0:** `reconcile_orphans` is called from `orchestrator.py:364` (inside `startup_reconcile`), NOT from `callback.py`. But it writes `by="callback"` into the lifecycle YAML transitions array. This is a lie — post-incident forensics read `by=` to trace which system made a write. False attribution (`callback`) masks the real source (`orchestrator`) during debugging, leading to incorrect root-cause analysis (as happened during today's incident investigation when transitions showed `callback` for writes that were actually orchestrator startup recovery).

**Acceptance criteria:**
- `grep -n 'by="callback"' scripts/vps/lifecycle.py` returns 0 matches (only this one occurrence existed)
- `grep -n 'reconcile_orphans' scripts/vps/lifecycle.py | grep orchestrator` shows the fix
- Unit test: call `reconcile_orphans` with a fake `in_progress` spec → lifecycle YAML transition shows `by: orchestrator`
- `git log --oneline ai/lifecycle/*.yaml` (after a test reconcile) shows `by: orchestrator` in transition

---

## Implementation Plan

> **Re-validated 2026-05-23** against worktree HEAD (e9f8561). See `## Drift Log`
> below for line-number/scope corrections vs the original spec body above.

**Order:** Tasks 1 → 3 → 6 → 7 → 9 → 5 → 4 → 2 → 8

Rationale:
- Tasks 1, 3, 6, 7, 9 are pure surgical edits, no new files, no external
  actions needed — do first.
- Task 5 is surgical but needs counter-file logic — do after 7.
- Task 4 (BOOTSTRAP_ANOMALY) modifies `orchestrator.py` — do after 6
  (which also touches orchestrator) to keep diffs separate.
- Task 2 (conftest autouse) — do after 1 (testpaths) so the new fixture is
  visible to the scripts/vps tests it must also cover.
- Task 8 (heartbeat) — new file + setup-vps.sh + main loop edit — do last.

**Each task is one atomic commit.** Do NOT bundle multiple tasks in one commit.

Commit message format:
```
fix(TECH-189): task N — <short description>
```

Example: `fix(TECH-189): task 1 — add scripts/vps/tests to pyproject testpaths`

---

### Task 1 (detailed) — pyproject.toml testpaths

**File:** `pyproject.toml:19`
**Verified current state (HEAD):** `testpaths = ["tests"]` (matches spec).

**Edit (exact):**
```toml
testpaths = ["tests", "scripts/vps/tests"]
```

**Acceptance:**
- `pytest --collect-only` lists tests from both directories.
- `pytest` baseline: 179 passing in `tests/` + ~existing count in
  `scripts/vps/tests/` (test_lifecycle, test_callback, test_orchestrator,
  test_db, test_orchestrator_git_pull, test_orchestrator_lifecycle,
  test_migrate_backlog, test_render_backlog).
- The pre-existing collection error in
  `tests/integration/test_claude_runner_post_result_exception.py` (missing
  `claude_agent_sdk`) is NOT introduced by this task — leave as-is.

Commit: `fix(TECH-189): task 1 — add scripts/vps/tests to pyproject testpaths`

---

### Task 3 (detailed) — Zombie cleanup: spec_lint.py + DLD-CALLBACK-MARKER refs

**Files (all confirmed against HEAD):**
- DELETE `scripts/vps/spec_lint.py`
- DELETE `tests/unit/test_spec_lint.py` (10 tests, imports `spec_lint`
  and `callback._parse_allowed_files_v1`; without the module the file will
  fail at import time)
- MODIFY `template/.claude/skills/spark/completion.md:46`
- MODIFY `.claude/skills/spark/completion.md:46`
- MODIFY `.claude/agents/spark/facilitator.md:218-221`
- MODIFY `.git-hooks/pre-commit` (lines 27, 29 reference `spec_lint.py`)

**Allowed-files scope note:** `tests/unit/test_spec_lint.py` and
`.git-hooks/pre-commit` are NOT in `## Allowed Files`. Callback guard
operates on commits ∩ Allowed Files: it does NOT reject commits that ALSO
touch files outside the allowlist; it only requires that allowed files have
been touched. However, project policy says "Never delete/skip tests without
user approval." User approval is implicit in the spec listing
`spec_lint.py` for deletion (test exists solely to validate that module).
**Operator note:** if autopilot guard objects, treat
`tests/unit/test_spec_lint.py` + `.git-hooks/pre-commit` as a separate
follow-up sub-commit and request explicit allowlist amendment via
human-in-the-loop. Default path = include both in the Task 3 commit.

**Edits:**

1. `rm scripts/vps/spec_lint.py`
2. `rm tests/unit/test_spec_lint.py`
3. `template/.claude/skills/spark/completion.md` line 46:

   Replace
   ```
   6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line, `grep '<!-- DLD-CALLBACK-MARKER-START v1 -->' ai/features/{TASK_ID}*.md` returns ≥2 lines (Allowed Files + Status), and `## Allowed Files` heading exists exactly once
   ```
   with
   ```
   6. [ ] **Allowlist Linter passed** (Phase 5.5) — `grep '<!-- callback-allowlist v1' ai/features/{TASK_ID}*.md` returns ≥1 line and `## Allowed Files` heading exists exactly once
   ```

4. `.claude/skills/spark/completion.md` line 46 — identical edit to step 3
   (sync-pair per `rules/template-sync.md`).

5. `.claude/agents/spark/facilitator.md` lines 218-221 — delete the 4
   lines verbatim (DLD_START_RE, DLD_END_RE, "section ends at...", "Verify
   `## Allowed Files`..."). Line 222 (currently "Map any failure to error
   codes E001..E008") becomes the new line 218 after deletion.

6. `.git-hooks/pre-commit` lines 27-29 — remove the `spec_lint.py` block.
   Replace
   ```
       # Let spec_lint do structural check via --diff-warn mode.
       if python3 scripts/vps/spec_lint.py --diff-warn "$f" 2>/dev/null; then
   ```
   Locate the surrounding context block and replace with a no-op message
   or delete the entire `if` clause that depended on `spec_lint`. (Coder
   must read the file first; the surgical removal pattern depends on the
   block structure around lines 27-29.)

**Verifications after edit:**
- `test ! -f scripts/vps/spec_lint.py`
- `test ! -f tests/unit/test_spec_lint.py`
- `grep -r 'DLD-CALLBACK-MARKER' .claude/ template/.claude/` → 0 matches
- `grep 'DLD_START_RE\|DLD_END_RE' .claude/agents/spark/facilitator.md` → 0
- `grep spec_lint .git-hooks/pre-commit` → 0
- `pytest tests/unit/ -x` → no collection errors from missing `spec_lint`
- `pytest` full suite → still 179+ passing (minus 10 spec_lint tests that
  we explicitly removed)

Commit: `fix(TECH-189): task 3 — remove spec_lint.py + DLD-CALLBACK-MARKER refs`

---

### Task 6 (detailed) — Add GROWTH to spec-id regexes

**Files (confirmed against HEAD):**
- `scripts/vps/callback.py:43` — current: `r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*"`
- `scripts/vps/orchestrator.py:308` — current:
  `r"(TECH|FTR|BUG|ARCH)-\d+[a-z]*"` (the active_re on line 299 and
  backlog_ids regex on line 305 ALREADY include GROWTH — drift correction
  vs spec body).

**Edits:**

1. `scripts/vps/callback.py:43`:
   ```python
   _SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")
   ```

2. `scripts/vps/orchestrator.py:308`:
   ```python
   m = re.search(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*", spec_md.name)
   ```

**Test (add to `scripts/vps/tests/test_callback.py`):**
```python
def test_spec_id_re_matches_growth():
    """Task 6 — _SPEC_ID_RE accepts GROWTH-NNN."""
    import callback
    m = callback._SPEC_ID_RE.search("dld:GROWTH-001")
    assert m is not None
    assert m.group(0) == "GROWTH-001"
```

**Test (add to `scripts/vps/tests/test_orchestrator.py` or new file):**
```python
def test_bootstrap_new_specs_accepts_growth(tmp_path, monkeypatch):
    """Task 6 — bootstrap_new_specs handles GROWTH-* spec filenames."""
    import re
    # Verify the line-308 regex now matches GROWTH filenames.
    name = "GROWTH-001-2026-05-23-experiment.md"
    m = re.search(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*", name)
    assert m is not None and m.group(0) == "GROWTH-001"
```

**Verifications:**
- `grep '_SPEC_ID_RE' scripts/vps/callback.py` → contains `GROWTH`
- All three regexes in `bootstrap_new_specs` (lines 299, 305, 308) contain
  `GROWTH`.

Commit: `fix(TECH-189): task 6 — add GROWTH prefix to spec-id regexes`

---

### Task 7 (detailed) — lifecycle._run timeout

**File:** `scripts/vps/lifecycle.py:77-88` (`_run`), plus callers in
`_cas_loop` (line 269) and `_atomic_write` (line 171). Confirmed against HEAD.

**Edit `_run` (lines 77-88):**
```python
def _run(
    cmd: list, *, cwd: str, env: Optional[dict] = None, input_text: Optional[str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
```

**Edit `_cas_loop` (around line 277-285):** wrap the body of the
`for attempt in range(...)` loop in `try/except TimeoutExpired` so a hung
plumbing call is treated as a CAS failure (and counted toward MAX retries):
```python
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            try:
                yaml_content = yaml_fn()
                if _atomic_write(repo_dir, spec_id, yaml_content, branch):
                    _push_best_effort(repo_dir, branch)
                    return
            except subprocess.TimeoutExpired as exc:
                log.warning(
                    "lifecycle git plumbing timeout (cmd=%s): %s",
                    getattr(exc, "cmd", "?"), exc,
                )
            log.warning("CAS attempt %d/%d failed for %s", attempt, MAX_CAS_RETRIES, spec_id)
            if attempt < MAX_CAS_RETRIES:
                time.sleep(random.uniform(0, 0.05))
        raise LifecycleWriteRaceError(spec_id, MAX_CAS_RETRIES)
```

`_atomic_write` itself does NOT need an explicit try/except — the
`TimeoutExpired` will propagate through and be caught by `_cas_loop`.
Same pattern applies inside `write_file_atomic` (line 448-465) — wrap
similarly so it returns `False` on timeout instead of raising.

**Test (add to `scripts/vps/tests/test_lifecycle.py`):**
```python
def test_run_timeout_param_present():
    """Task 7 — _run signature accepts timeout kwarg with default 30."""
    import inspect
    sig = inspect.signature(lifecycle._run)
    assert "timeout" in sig.parameters
    assert sig.parameters["timeout"].default == 30


def test_cas_loop_treats_timeout_as_cas_failure(tmp_git_repo, monkeypatch):
    """Task 7 — TimeoutExpired in _atomic_write surfaces as CAS race + retry."""
    call_count = {"n": 0}

    def fake_atomic(*a, **kw):
        call_count["n"] += 1
        raise subprocess.TimeoutExpired(cmd=["git", "fake"], timeout=30)

    monkeypatch.setattr(lifecycle, "_atomic_write", fake_atomic)
    with pytest.raises(lifecycle.LifecycleWriteRaceError):
        lifecycle.write_lifecycle(str(tmp_git_repo), "TECH-001", "queued", by="callback")
    assert call_count["n"] == lifecycle.MAX_CAS_RETRIES
```

**Verifications:**
- `grep 'timeout=30' scripts/vps/lifecycle.py` → at least 2 hits
  (signature default + subprocess.run kwarg).
- Existing lifecycle tests (15 in `test_lifecycle.py`) still pass.

Commit: `fix(TECH-189): task 7 — add timeout=30 to lifecycle._run + handle TimeoutExpired`

---

### Task 9 (detailed) — reconcile_orphans identity attribution

**File:** `scripts/vps/lifecycle.py:551` (confirmed exactly).
**Current:** `write_lifecycle(repo_dir, spec_id, "queued", reason="orphaned from crash", by="callback")`
**Note:** `_ALLOWED_WRITERS` (line 49-51) already includes `"orchestrator"`,
so the new `by` value passes the ValueError guard at line 321-322.

**Edit:** change `by="callback"` → `by="orchestrator"` on line 551.

**Test (add to `scripts/vps/tests/test_lifecycle.py`):**
```python
def test_reconcile_orphans_writes_by_orchestrator(tmp_git_repo):
    """Task 9 — reconcile_orphans attributes its writes to 'orchestrator'."""
    # Bootstrap one in_progress spec
    lifecycle.create_initial(str(tmp_git_repo), "TECH-001", "p1", "tech")
    lifecycle.write_lifecycle(
        str(tmp_git_repo), "TECH-001", "in_progress",
        by="callback", pueue_id=9999,
    )
    # Pretend the pueue task is gone
    reconciled = lifecycle.reconcile_orphans(str(tmp_git_repo), set())
    assert "TECH-001" in reconciled
    data = lifecycle.read_lifecycle(str(tmp_git_repo), "TECH-001")
    assert data["updated_by"] == "orchestrator"
    last_trans = data["transitions"][-1]
    assert last_trans["by"] == "orchestrator"
    assert last_trans["to"] == "queued"
```

**Verifications:**
- `grep -n 'by="callback"' scripts/vps/lifecycle.py` → 0 matches
- `grep -n 'by="orchestrator"' scripts/vps/lifecycle.py` → ≥1 (the new edit;
  `create_initial` uses `_by = "orchestrator"` but as a local variable, not
  a string-literal kwarg, so the count is exactly 1 after this fix).

Commit: `fix(TECH-189): task 9 — reconcile_orphans uses by="orchestrator"`

---

### Task 5 (detailed) — _push_best_effort DEBUG → WARNING + counter

**File:** `scripts/vps/lifecycle.py:263-266` (confirmed exactly).

**Edit (replace whole function body):**
```python
def _push_best_effort(repo_dir: str, branch: str) -> None:
    r = _run(["git", "push", "origin", branch], cwd=repo_dir)
    if r.returncode != 0:
        log.warning(
            "lifecycle push failed (best-effort, not fatal): branch=%s stderr=%s",
            branch, r.stderr.strip()[:200],
        )
        counter = Path(repo_dir) / "ai" / ".lifecycle-push-failures"
        try:
            prev = int(counter.read_text().strip()) if counter.is_file() else 0
            counter.write_text(str(prev + 1))
        except Exception:  # noqa: BLE001
            pass
```

**Counter file path:** `.gitignore` should already ignore `ai/` non-tracked
artifacts; verify counter file is not staged. If needed, append
`ai/.lifecycle-push-failures` to `.gitignore` (not in Allowed Files —
omit unless commit fails; counter is best-effort).

**Test (add to `scripts/vps/tests/test_lifecycle.py`):**
```python
def test_push_best_effort_warns_on_failure(tmp_git_repo, caplog, monkeypatch):
    """Task 5 — push failure emits WARNING and bumps counter."""
    fake = MagicMock(returncode=1, stderr="auth failed")
    monkeypatch.setattr(lifecycle, "_run", lambda *a, **kw: fake)
    with caplog.at_level("WARNING", logger="lifecycle"):
        lifecycle._push_best_effort(str(tmp_git_repo), "develop")
    assert any("lifecycle push failed" in r.message for r in caplog.records)
    counter = Path(tmp_git_repo) / "ai" / ".lifecycle-push-failures"
    assert counter.is_file()
    assert int(counter.read_text().strip()) == 1
```

Commit: `fix(TECH-189): task 5 — _push_best_effort WARNING + failure counter`

---

### Task 4 (detailed) — BOOTSTRAP_ANOMALY threshold

**File:** `scripts/vps/orchestrator.py` — function `bootstrap_new_specs`
spans lines 279-333 (confirmed). The for-loop is lines 307-333; we add a
counter increment at the successful `lifecycle.create_initial` call (line
325 area, inside the `try` block) and a post-loop anomaly check.

**Edit (apply within `bootstrap_new_specs`):**

1. Just before the `for spec_md in features_dir.glob("*.md"):` loop (after
   line 306 `backlog_ids = set(...)`), add:
   ```python
   BOOTSTRAP_ANOMALY_THRESHOLD = 3
   created_count = 0
   ```

2. Inside the try block on line 324-333, just after the successful
   `lifecycle.create_initial(...)` call (line 325), add `created_count += 1`
   so the increment happens only on success.

3. After the for-loop ends (after line 333), add the anomaly block:
   ```python
   if created_count > BOOTSTRAP_ANOMALY_THRESHOLD:
       log.warning(
           "BOOTSTRAP_ANOMALY: created %d lifecycle yamls in one cycle for %s "
           "(threshold=%d) — possible backlog-write race or bulk-import",
           created_count, project_dir, BOOTSTRAP_ANOMALY_THRESHOLD,
       )
       counter_path = Path(project_dir) / "ai" / ".bootstrap-anomaly-count"
       try:
           prev = int(counter_path.read_text().strip()) if counter_path.is_file() else 0
           counter_path.write_text(str(prev + 1))
       except Exception:  # noqa: BLE001
           pass
       try:
           import event_writer  # local import to avoid hard dep at module load
           event_writer.notify(
               Path(project_dir).name,
               f"BOOTSTRAP_ANOMALY: {created_count} lifecycle yamls in one cycle",
           )
       except Exception:  # noqa: BLE001
           pass
   ```

   (Use `Path(project_dir).name` rather than `project_dir.split("/")[-1]`
   for OS-agnostic correctness; `event_writer` is already imported at top
   of `orchestrator.py` but a local import is safer in case import fails.)

**Test (add to `scripts/vps/tests/test_orchestrator.py`):**
```python
def test_bootstrap_anomaly_logged_when_threshold_exceeded(
    tmp_path, monkeypatch, caplog,
):
    """Task 4 — >3 creates in one cycle logs BOOTSTRAP_ANOMALY."""
    import orchestrator
    # Build fake project dir with backlog + 5 spec files
    proj = tmp_path / "proj"
    (proj / "ai" / "features").mkdir(parents=True)
    backlog = proj / "ai" / "backlog.md"
    rows = []
    for i in range(5):
        sid = f"TECH-{100 + i}"
        (proj / "ai" / "features" / f"{sid}-foo.md").write_text(
            "**Priority:** P1\n**Kind:** tech\n"
        )
        rows.append(f"| {sid} | desc | queued | P1 | foo |")
    backlog.write_text("\n".join(rows) + "\n")

    monkeypatch.setattr(orchestrator.lifecycle, "read_lifecycle", lambda *a, **k: None)
    monkeypatch.setattr(
        orchestrator.lifecycle, "create_initial", lambda *a, **k: None,
    )
    with caplog.at_level("WARNING"):
        orchestrator.bootstrap_new_specs(str(proj))
    assert any("BOOTSTRAP_ANOMALY" in r.message for r in caplog.records)
    counter = proj / "ai" / ".bootstrap-anomaly-count"
    assert counter.is_file()


def test_bootstrap_anomaly_silent_below_threshold(tmp_path, monkeypatch, caplog):
    """Task 4 — 1-2 creates does NOT log BOOTSTRAP_ANOMALY."""
    import orchestrator
    proj = tmp_path / "proj"
    (proj / "ai" / "features").mkdir(parents=True)
    (proj / "ai" / "features" / "TECH-100-foo.md").write_text(
        "**Priority:** P1\n**Kind:** tech\n"
    )
    (proj / "ai" / "backlog.md").write_text(
        "| TECH-100 | desc | queued | P1 | foo |\n"
    )
    monkeypatch.setattr(orchestrator.lifecycle, "read_lifecycle", lambda *a, **k: None)
    monkeypatch.setattr(orchestrator.lifecycle, "create_initial", lambda *a, **k: None)
    with caplog.at_level("WARNING"):
        orchestrator.bootstrap_new_specs(str(proj))
    assert not any("BOOTSTRAP_ANOMALY" in r.message for r in caplog.records)
```

Commit: `fix(TECH-189): task 4 — BOOTSTRAP_ANOMALY threshold log + counter`

---

### Task 2 (detailed) — autouse DB isolation fixture

**File:** `tests/conftest.py` (current: 123 LOC, hook-only fixtures —
confirmed).

**Add at end of file:**
```python
@pytest.fixture(autouse=True)
def _db_isolation(tmp_path, monkeypatch):
    """Auto-isolate every test from the production DB.

    Overrides DB_PATH env var and db.DB_PATH attribute via monkeypatch.
    Hook tests gracefully skip (db module not on sys.path).
    """
    db_path = tmp_path / "test_isolated.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    try:
        import db as db_mod  # only available when scripts/vps is in sys.path
        monkeypatch.setattr(db_mod, "DB_PATH", str(db_path), raising=False)
    except ImportError:
        pass  # hooks tests don't have db — safe to skip
```

**Important:** This fixture should not conflict with the explicit
`isolated_db` fixture in `scripts/vps/tests/conftest.py` — that one applies
schema to the db, while this one only patches the path. The two stack:
when both run, the autouse one runs first (provides path), then
`isolated_db` runs (applies schema). Verify by running:
```
pytest scripts/vps/tests/test_db.py -v
```

**Acceptance:**
- Full `pytest` run produces no file under `~/orchestrator.db` or
  `scripts/vps/orchestrator.db` (only files under tmp dirs).
- Existing hooks tests (in `tests/`) still pass — fixture's ImportError
  branch is exercised.
- Existing scripts/vps tests still pass — fixture stacks under
  `isolated_db`.

Commit: `fix(TECH-189): task 2 — autouse DB isolation in tests/conftest.py`

---

### Task 8 (detailed) — Orchestrator heartbeat + monitor

**Files:**
- MODIFY `scripts/vps/orchestrator.py` — main loop (after line 657
  `process_project(...)`, before line 660 `log.info("cycle complete...")`).
- CREATE `scripts/vps/heartbeat_monitor.py` (~50 LOC).
- MODIFY `scripts/vps/setup-vps.sh` — add cron entry similar to existing
  patterns at lines 68-76 (nexus-cache-refresh) and 95-104 (audit_digest).

**Edit `orchestrator.py` (insert after line 657, before line 660):**
```python
            # Heartbeat — written at end of every cycle (after dispatch loop).
            heartbeat_path = SCRIPT_DIR / ".orchestrator-heartbeat"
            try:
                from lifecycle import now_iso
                heartbeat_path.write_text(now_iso())
            except Exception:  # noqa: BLE001
                log.warning("heartbeat write failed", exc_info=True)
```

**CREATE `scripts/vps/heartbeat_monitor.py`:**
```python
#!/usr/bin/env python3
"""Heartbeat monitor — fires Hermes event if orchestrator heartbeat is stale.

Cron: */5 * * * * python3 /path/to/heartbeat_monitor.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HEARTBEAT_FILE = SCRIPT_DIR / ".orchestrator-heartbeat"
STALE_THRESHOLD_MINUTES = 10


def main() -> int:
    if not HEARTBEAT_FILE.is_file():
        print("WARN: no heartbeat file found", file=sys.stderr)
        return 0
    last_beat_str = HEARTBEAT_FILE.read_text().strip()
    try:
        last_beat = datetime.fromisoformat(last_beat_str.replace("Z", "+00:00"))
    except ValueError:
        print(f"WARN: unparseable heartbeat: {last_beat_str}", file=sys.stderr)
        return 0
    age = datetime.now(tz=timezone.utc) - last_beat
    if age > timedelta(minutes=STALE_THRESHOLD_MINUTES):
        print(f"ALERT: orchestrator heartbeat stale ({age})", file=sys.stderr)
        try:
            sys.path.insert(0, str(SCRIPT_DIR))
            from event_writer import notify
            notify("dld", f"ORCHESTRATOR_STALE: last heartbeat {age} ago")
        except Exception as exc:  # noqa: BLE001
            print(f"WARN: could not fire Hermes event: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Edit `scripts/vps/setup-vps.sh` (add after line 104, before line 106):**
```bash
    # 8b. Cron for orchestrator heartbeat monitor (TECH-189 Task 8)
    HB_SCRIPT="${SCRIPT_DIR}/heartbeat_monitor.py"
    if [[ -f "$HB_SCRIPT" ]]; then
        HB_CRON_LINE="*/5 * * * * ${SCRIPT_DIR}/venv/bin/python3 ${HB_SCRIPT} >> /var/log/dld-orchestrator/heartbeat.log 2>&1"
        (crontab -l 2>/dev/null | grep -v "heartbeat_monitor.py"; echo "$HB_CRON_LINE") | crontab -
        ok "Cron installed: heartbeat_monitor.py every 5 min"
    else
        warn "heartbeat_monitor.py not found — cron not installed"
    fi
```

**Tests (add to `scripts/vps/tests/test_orchestrator.py` or new
`test_heartbeat_monitor.py`):**
```python
def test_heartbeat_monitor_alerts_on_stale(tmp_path, monkeypatch):
    """Task 8 — monitor calls notify() when heartbeat is older than threshold."""
    import importlib.util, sys
    hb_path = Path(__file__).resolve().parent.parent / "heartbeat_monitor.py"
    spec = importlib.util.spec_from_file_location("heartbeat_monitor", hb_path)
    mod = importlib.util.module_from_spec(spec)

    fake_hb = tmp_path / ".orchestrator-heartbeat"
    stale_dt = "2020-01-01T00:00:00Z"
    fake_hb.write_text(stale_dt)
    monkeypatch.setattr(mod, "HEARTBEAT_FILE", fake_hb, raising=False)

    notify_calls = []
    fake_ew = type("M", (), {"notify": lambda *a, **k: notify_calls.append(a)})
    monkeypatch.setitem(sys.modules, "event_writer", fake_ew)

    spec.loader.exec_module(mod)
    rc = mod.main()
    assert rc == 0
    assert notify_calls, "notify() should have been called"
    assert "ORCHESTRATOR_STALE" in notify_calls[0][1]


def test_heartbeat_monitor_silent_when_fresh(tmp_path, monkeypatch):
    """Task 8 — monitor stays silent when heartbeat is fresh."""
    import importlib.util, sys
    from datetime import datetime, timezone
    hb_path = Path(__file__).resolve().parent.parent / "heartbeat_monitor.py"
    spec = importlib.util.spec_from_file_location("heartbeat_monitor", hb_path)
    mod = importlib.util.module_from_spec(spec)

    fake_hb = tmp_path / ".orchestrator-heartbeat"
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fake_hb.write_text(now)
    monkeypatch.setattr(mod, "HEARTBEAT_FILE", fake_hb, raising=False)

    notify_calls = []
    fake_ew = type("M", (), {"notify": lambda *a, **k: notify_calls.append(a)})
    monkeypatch.setitem(sys.modules, "event_writer", fake_ew)

    spec.loader.exec_module(mod)
    rc = mod.main()
    assert rc == 0
    assert not notify_calls
```

**Acceptance:**
- `python3 scripts/vps/heartbeat_monitor.py` exits 0 (no heartbeat = warn,
  fresh heartbeat = silent).
- After one orchestrator cycle (live or mocked), `.orchestrator-heartbeat`
  exists and parses as ISO-8601 UTC.
- `setup-vps.sh` (when run) adds the cron line.

Commit: `fix(TECH-189): task 8 — orchestrator heartbeat + monitor + cron`

---

## Drift Log

**Checked:** 2026-05-23 (planner re-validation against HEAD e9f8561)
**Result:** light_drift

### Changes Detected

| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/orchestrator.py` lines 299, 305 | already-fixed | AUTO-FIX: Task 6 now targets only line 308 (lines 299 and 305 already contain `GROWTH`); spec body still lists 3 lines as the target which is inaccurate. Detailed Task 6 above corrects this. |
| `scripts/vps/lifecycle.py` ARCH-187 identity guards | merged-since-spec | AUTO-FIX: `_ALLOWED_WRITERS` already includes `"orchestrator"`, so Task 9's `by="orchestrator"` passes the new ValueError guard at line 321-322. Tasks 5 and 7 are NOT impacted (they touch `_push_best_effort` and `_run`, both outside identity enforcement). |
| `tests/unit/test_spec_lint.py` | missing-from-allowlist | AUTO-FIX: Task 3 detailed plan now explicitly deletes this file alongside `spec_lint.py`. Without deletion the test file would fail at import (it imports `spec_lint`). Operator note added re: implicit user approval. |
| `.git-hooks/pre-commit` lines 27-29 | references-deleted-module | AUTO-FIX: Task 3 detailed plan now removes the `spec_lint.py` invocation from the pre-commit hook. |
| `_SPEC_ID_RE` grouping in EC-007 | misleading-but-not-fatal | NO-FIX: spec EC-007 says `.group()` returns "GROWTH-001" — that is `.group(0)`, not `.group(1)`. Detailed Task 6 test uses `m.group(0)` which is consistent with actual callback usage (`callback.py:317, 323, 335`). |
| Spec line numbers vs current HEAD | exact-match | Confirmed: `callback.py:43` (`_SPEC_ID_RE`), `lifecycle.py:77-88` (`_run`), `lifecycle.py:263-266` (`_push_best_effort`), `lifecycle.py:551` (`reconcile_orphans` by="callback"), `orchestrator.py:279-333` (`bootstrap_new_specs`), `template/.claude/skills/spark/completion.md:46`, `.claude/agents/spark/facilitator.md:218-221` — all line numbers match current HEAD. |
| `pyproject.toml:19` | exact-match | Confirmed `testpaths = ["tests"]`. |

### References Updated
- Task 6: 3 lines → 1 line (only `orchestrator.py:308`)
- Task 3: added 2 sub-targets (`tests/unit/test_spec_lint.py` + `.git-hooks/pre-commit`)
- Tasks 4, 5, 7, 8, 9: counter file write paths spelled out explicitly
- Task 8: heartbeat insertion point pinned at `orchestrator.py:657-660`,
  setup-vps.sh insertion point pinned at line 104-106.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `pyproject.toml`
- `tests/conftest.py`
- `scripts/vps/spec_lint.py`
- `scripts/vps/callback.py`
- `scripts/vps/orchestrator.py`
- `scripts/vps/lifecycle.py`
- `scripts/vps/heartbeat_monitor.py`
- `scripts/vps/setup-vps.sh`
- `template/.claude/skills/spark/completion.md`
- `.claude/skills/spark/completion.md`
- `.claude/agents/spark/facilitator.md`
- `scripts/vps/tests/test_callback.py`
- `scripts/vps/tests/test_orchestrator.py`
- `scripts/vps/tests/test_lifecycle.py`
- `scripts/vps/tests/test_db.py`
- `tests/unit/test_spec_lint.py`
- `.git-hooks/pre-commit`
- `.claude/skills/spark/feature-mode.md`
- `template/.claude/skills/spark/feature-mode.md`
- `.claude/rules/dependencies.md`

---

## Eval Criteria

### EC-001 — CI runs vps tests (Task 1)
**Type:** deterministic
**Check:** `pytest --collect-only 2>&1 | grep 'scripts/vps/tests'` shows at least 1 test module collected
**Fail condition:** `testpaths` missing `scripts/vps/tests` in `pyproject.toml`
**Source:** architectures.md P0-1

### EC-002 — DB isolation prevents prod pollution (Task 2)
**Type:** deterministic
**Check:** `pytest tests/ -x` completes without creating any file outside `tmp_path` (verify via `strace -e openat` or by checking no db file at `$HOME/.orchestrator.db` or default path)
**Fail condition:** Any test writes to a non-tmp path DB
**Source:** architectures.md P0-2, deep audit Finding 5

### EC-003 — No zombie DLD-CALLBACK-MARKER references (Task 3)
**Type:** deterministic
**Check:** `grep -r 'DLD-CALLBACK-MARKER' .claude/ template/.claude/` returns 0 matches
**Fail condition:** Any DLD-CALLBACK-MARKER reference survives in agent prompts or skill files
**Source:** architectures.md P0-4, ARCH-186

### EC-004 — spec_lint.py deleted (Task 3)
**Type:** deterministic
**Check:** `test ! -f scripts/vps/spec_lint.py` exits 0
**Fail condition:** File still present
**Source:** architectures.md P0-4, deep audit Finding 22

### EC-005 — BOOTSTRAP_ANOMALY fires on >3 creates (Task 4)
**Type:** deterministic (unit test)
**Check:** Unit test in `test_orchestrator.py` mocks `lifecycle.create_initial` to succeed 5 times → asserts `log.warning` called with "BOOTSTRAP_ANOMALY"
**Fail condition:** No warning emitted when 5 creates happen in one cycle
**Source:** architectures.md P0-5, today's incident (2026-05-23)

### EC-006 — _push_best_effort emits WARNING on failure (Task 5)
**Type:** deterministic (unit test)
**Check:** Unit test mocks `_run` to return `returncode=1` → `log.warning` called with "lifecycle push failed"
**Fail condition:** Only `log.debug` called on push failure
**Source:** architectures.md P0-6, deep audit Coroner #3

### EC-007 — GROWTH spec IDs extracted by callback (Task 6)
**Type:** deterministic (unit test)
**Check:** `_SPEC_ID_RE.search("GROWTH-001:dld")` returns match with group = "GROWTH-001"
**Fail condition:** Regex does not match GROWTH prefix
**Source:** architectures.md P0-7, backlog GROWTH-001..006

### EC-008 — lifecycle _run timeout raises TimeoutExpired safely (Task 7)
**Type:** deterministic (unit test)
**Check:** Unit test patches `subprocess.run` to raise `TimeoutExpired` → `_atomic_write` returns `False` without re-raising
**Fail condition:** Exception propagates out of `_atomic_write`, or `_write_lock` is not released
**Source:** architectures.md P0-8, deep audit Finding 12

### EC-009 — Heartbeat file written each cycle (Task 8)
**Type:** deterministic (integration)
**Check:** After starting orchestrator and waiting one poll cycle → `cat scripts/vps/.orchestrator-heartbeat` contains ISO timestamp from last 5 minutes
**Fail condition:** File absent or contains stale timestamp after orchestrator ran
**Source:** architectures.md P0-9

### EC-010 — Heartbeat monitor alerts on stale file (Task 8)
**Type:** deterministic (unit test)
**Check:** Write timestamp >11min ago to `.orchestrator-heartbeat` → run `heartbeat_monitor.py` → `notify()` called with "ORCHESTRATOR_STALE"
**Fail condition:** No Hermes event fired on stale heartbeat
**Source:** architectures.md P0-9

### EC-011 — reconcile_orphans writes by="orchestrator" (Task 9)
**Type:** deterministic (unit test)
**Check:** In test: call `reconcile_orphans(tmp_repo, set())` with one in_progress YAML → read resulting YAML transition → `by == "orchestrator"`
**Fail condition:** `by == "callback"` in transition written by reconcile_orphans
**Source:** architectures.md P0-10, deep audit identity attribution

### EC-012 — All 9 tasks committed individually
**Type:** deterministic
**Check:** `git log --oneline origin/develop -- pyproject.toml scripts/vps/lifecycle.py scripts/vps/orchestrator.py scripts/vps/callback.py | grep 'TECH-189' | wc -l` >= 7 (at minimum 7 separate commits for the file changes)
**Fail condition:** All changes in one mega-commit
**Source:** ADR-011, Atomic Commits rule

### EC-013 — Full test suite passes after all tasks
**Type:** deterministic
**Check:** `pytest` from root exits 0
**Fail condition:** Any test failure after completing all 10 tasks
**Source:** CI gate

---

## Definition of Done

- [ ] `pytest` from project root exits 0 (both `tests/` and `scripts/vps/tests/` run)
- [ ] `grep -r 'DLD-CALLBACK-MARKER' .claude/ template/.claude/` returns 0 matches
- [ ] `test ! -f scripts/vps/spec_lint.py` exits 0
- [ ] `grep 'GROWTH' scripts/vps/callback.py | grep _SPEC_ID_RE` shows GROWTH in regex
- [ ] `grep 'timeout=30' scripts/vps/lifecycle.py` shows timeout parameter
- [ ] `grep 'log.warning.*push' scripts/vps/lifecycle.py` shows WARNING (not debug)
- [ ] `grep 'by="callback"' scripts/vps/lifecycle.py` returns 0 (only `by="orchestrator"` for reconcile)
- [ ] `cat scripts/vps/.orchestrator-heartbeat` shows fresh ISO timestamp
- [ ] `ls scripts/vps/heartbeat_monitor.py` exits 0 (file exists)
- [ ] 9 individual commits on branch `tech/TECH-189-p0-hardening`
- [ ] Branch merged to `develop`

---

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| `autouse` DB fixture causes unexpected side effects in hooks tests | LOW | LOW | `ImportError` guard in fixture; test locally before CI |
| `timeout=30` in `_run` too aggressive for slow VPS git operations | LOW | MEDIUM | 30s is 30x normal git plumbing time; increase to 60 if needed |
| BOOTSTRAP_ANOMALY fires during bulk Spark session (many new specs at once) | MEDIUM | LOW | Threshold=3 is intentionally low; can be raised to 5 via env var if needed |

---

## Historical Risks Applied

- **BUG-185 / autostash race:** this spec does NOT touch DLD-CALLBACK-MARKER blocks or spec status fields — zero autostash risk
- **BUG-188 / false-fail:** no changes to `claude-runner.py` or exit code logic
- **ARCH-186 / lifecycle SoT:** only Tasks 7 and 9 touch lifecycle.py — Task 7 adds timeout to `_run` subprocess calls; Task 9 changes `by=` string in reconcile_orphans. Neither changes CAS logic or write path structure.

---

## Blueprint Reference

No system-blueprint exists for this project (DLD is the framework itself). Constraints from:
- `ADR-023`: lifecycle.py is sole writer of lifecycle state — Task 9 complies (changes `by=` attribution only)
- `ADR-024`: autopilot early-exit — not affected by this spec
- `TECH-172`: callback is sole writer — not violated (Tasks 4-9 change orchestrator/lifecycle only)
- Template-sync rule: Task 3 modifies both `template/.claude/` and `.claude/` in sync (per `rules/template-sync.md`)
