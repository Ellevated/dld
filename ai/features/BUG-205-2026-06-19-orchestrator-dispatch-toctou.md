# Bug: [BUG-205] Orchestrator dispatches spec on stale status snapshot (TOCTOU) — out-of-order / blocked-spec dispatch

**Priority:** P1 | **Date:** 2026-06-19

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).

R1 — touches the prod dispatch path (`scripts/vps/orchestrator.py`), but the fix is
additive and fails *safe* (an extra pre-dispatch check whose only failure mode is
"skip this dispatch, retry next cycle" — never an over-dispatch).

## Why

`scan_queued` decides what to dispatch from a status **snapshot** taken at the top of
the function, then dispatches many lines later. Between the snapshot and the actual
`pueue add`, the authoritative lifecycle status of the chosen spec can change — and
nothing re-reads it. The result: the orchestrator can `pueue add` a spec that is no
longer `queued`/`resumed` (already `blocked` or `done`).

**Concrete code path (`scripts/vps/orchestrator.py`):**

1. **Line 731** — `queued_list = lifecycle.list_by_status(project_dir, {"queued","resumed"})`
   reads a snapshot from HEAD.
2. **Line 737** — `spec_id = queued_list[0]["spec_id"]` (first match wins).
3. **Lines 742–794** — audit-log guard, project-state read, provider detection,
   slot check, two pueue dedup checks, spec-file read. *Time passes here.*
4. **Line 795** — `_pueue_add(...)` actually dispatches.

During step 3 the status can flip because **`callback.py` is a separate process**
(fired by pueue on *another* task's completion) that writes `blocked`/`done` for this
very spec via git plumbing (updates HEAD atomically). The snapshot from step 1 is now
stale, but the dispatch in step 4 proceeds anyway.

The **only** existing safeguard is the `callback-audit.jsonl` heuristic (lines 742–765),
which is **not authoritative**:
- **Node-local** — the audit log lives in `SCRIPT_DIR`, not in git. Useless if the
  block was committed/pushed by another node or a different code path.
- **Window-limited** — 30 min for `blocked`, 5 min for `done`. A spec blocked 31 min
  ago but *still blocked* sails through.
- **Heuristic** — depends on `reason != "fixed"` and best-effort JSON parsing wrapped
  in `except Exception: pass` (any parse hiccup silently disables the guard).
- It never re-reads the **lifecycle yaml** (the SoT, ARCH-186/ADR-023) before dispatch.

This is compounded by `git_pull` being **skipped while any agent is running**
(`orchestrator.py:271`, "skip git pull — agent running"). With `parallel_tasks=2`, a
free slot triggers `scan_queued` against a **stale local HEAD** — the snapshot can be
minutes old.

**Observed impact (R0-grade near-miss, 2026-06-19, awardybot):** `FTR-1239` — a
money-ordering-sensitive spec (`payment_model` fixed→by_receipt, ARCH-1235 EC-3) that
**must** run *after* `TECH-1236` — was dispatched out-of-order (pueue #623 → blocked;
then re-dispatched as #624) and was running on a base where its prerequisite was not
yet merged. The operator (founder) had to **manually kill #624** to stop an R0 money
bug from landing out of order. It later ran legitimately as #626 only after the
founder unblocked it once `TECH-1236` merged (`a0a3e608`). The manual kill is exactly
the human-in-the-loop toil this guard is supposed to make unnecessary.

> **Honest scope note:** the structural TOCTOU window above is provable from the code.
> The exact micro-trigger of the #624 dispatch (same-node callback race vs. stale-HEAD
> read) is not fully reconstructable from the audit trail. The fix closes the gap
> **regardless of which sub-mechanism fired**, because it makes the dispatch decision
> authoritative at the last moment.

## Context

- `scan_queued` is single-threaded *within* the orchestrator, but `callback.py` runs
  as a **separate pueue-callback process** and mutates lifecycle yaml concurrently via
  `lifecycle.write_lifecycle` (git plumbing, CAS update-ref). So the "single-threaded"
  property does NOT protect the snapshot.
- `lifecycle.read_lifecycle(repo_dir, spec_id)` already exists and reads the **current
  HEAD** state via `git show HEAD:ai/lifecycle/{spec_id}.yaml` — a cheap, authoritative
  single-spec read. This is the right primitive for the last-moment re-check.
- The fix direction is **fail-safe**: if the re-check says "not queued anymore" (or the
  read fails), we simply skip this dispatch and let the next 300 s cycle reconsider.
  Over-skipping costs at most one cycle of latency; over-dispatching costs money/R0.
- **Out of scope (separate, larger concern):** the orchestrator has *no inter-spec
  dependency ordering* (no DAG). `FTR-1239 must-run-after TECH-1236` is a dependency
  the orchestrator cannot express today. That is a future FTR (dependency-aware
  dispatch), **not** this bug. This bug only fixes "don't dispatch a spec whose status
  changed under us."
- `orchestrator.py` is DLD-specific (`scripts/vps/`), **not** in `template/` — no
  template-sync needed (rules/template-sync.md).

---

## Scope

**In scope:**
- `scripts/vps/orchestrator.py` — in `scan_queued`, immediately before `_pueue_add`
  (after all existing pueue/slot dedup checks), add an **authoritative lifecycle
  re-read** of the chosen `spec_id`; abort the dispatch (return `False`) if its status
  is no longer in `{"queued","resumed"}` or the read fails.
- `scripts/vps/tests/test_orchestrator.py` — regression tests proving the re-check
  blocks a stale dispatch and is a no-op when status is unchanged.
- `.claude/rules/dependencies.md` — "Last Update" row.

**Out of scope:**
- Inter-spec dependency ordering / DAG (separate future FTR).
- Removing or rewriting the `callback-audit.jsonl` guard — it stays as a cheap
  first-line filter; the new re-check is the authoritative backstop. (Do **not** delete
  it; it still short-circuits the common recently-processed case before the slot/pueue
  work.)
- Any cross-node `git fetch` inside `scan_queued` — deferred. The local-HEAD re-read
  closes the same-node callback race (the realistic single-VPS topology today). A
  cross-node authoritative check (fetch tracking-ref + read `origin/develop:`) is a
  possible future hardening, noted but not built here (keeps this fix R1-contained and
  avoids re-introducing FETCH_HEAD-race surface, cf. commit 417ea12).
- `scan_inbox` (Hermes intake) — different path, different SoT (`ai/inbox/`), not
  affected.

---

## Impact Tree Analysis

### Step 1: UP — who calls scan_queued?
- `process_project` (`orchestrator.py:842`) → main loop. The only caller. The new
  early-return is just one more reason `scan_queued` returns `False` (no dispatch this
  cycle) — callers already handle `False`.

### Step 2: DOWN — what does the fix depend on?
- `lifecycle.read_lifecycle(project_dir, spec_id)` (existing, HEAD-authoritative).
- No new imports (`lifecycle` already imported in orchestrator.py).

### Step 3: BY TERM
- `grep -n "list_by_status\|read_lifecycle\|_pueue_add" scripts/vps/orchestrator.py`
- `grep -n "skip dispatch" scripts/vps/orchestrator.py` (the new log line joins the
  existing family of skip-dispatch logs).

### Step 4: CHECKLIST
- [ ] No change to `_pueue_add` signature or to `scan_inbox`.
- [ ] Re-check placed AFTER the pueue dedup checks but BEFORE `_pueue_add` (so it's the
      last gate; placing it earlier would re-open the window).
- [ ] `dependencies.md` "Last Update" row added.
- [ ] No `template/` edits (orchestrator is DLD-specific).

### Step 5: DUAL SYSTEM
- SoT for status = lifecycle yaml (HEAD). The fix makes `scan_queued` consult the SoT
  at dispatch time instead of trusting the older `list_by_status` snapshot. No second
  data source introduced.

### Verification
- [ ] `read_lifecycle` returning `blocked` ⇒ `_pueue_add` NOT called.
- [ ] `read_lifecycle` returning `queued` ⇒ `_pueue_add` called exactly as before.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/orchestrator.py` — authoritative lifecycle re-read before `_pueue_add` in `scan_queued` (modify)
- `scripts/vps/tests/test_orchestrator.py` — regression tests for the TOCTOU re-check (modify)
- `.claude/rules/dependencies.md` — Last Update row for BUG-205 (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (dispatch loop).
**Cross-cutting:** lifecycle SoT (ARCH-186/ADR-023), callback concurrency.
**Data model:** none (read-only consult of existing lifecycle yaml).

---

## Historical Risks

<!-- lessons-binding v1 -->

none (no `ai/lessons/` bank). Related project memory:
- `lifecycle-manual-wt-edit` — orchestrator reads lifecycle from HEAD, not WT.
- FETCH_HEAD-race fix (commit 417ea12) — why we do NOT add a `git pull`/`fetch` inside
  the scan; the re-check reads HEAD only.

---

## Approaches

### Approach 1: Authoritative single-spec re-read of HEAD lifecycle right before dispatch (SELECTED)
**Source:** code analysis (this session) + FTR-1239 incident.
**Summary:** After the existing pueue/slot checks and immediately before `_pueue_add`,
call `lifecycle.read_lifecycle(project_dir, spec_id)`; if status ∉ {queued, resumed}
(or read fails), log `skip dispatch: ... status changed (TOCTOU re-check)` and return
`False`.
**Pros:** Closes the window with the SoT primitive; ~one `git show`/dispatch (cheap);
fail-safe; no new deps; ~8 LOC; testable by patching `read_lifecycle`.
**Cons:** Same-node only (does not pull remote). Acceptable — single-VPS topology;
cross-node hardening deferred and documented.

### Approach 2: Re-validate the whole `queued_list` and re-pick
**Cons:** Larger change, re-opens the same window for the *re-picked* spec, more code.
Rejected — Approach 1 is the minimal correct fix.

### Approach 3: Targeted `git fetch origin develop` + read `origin/develop:` before dispatch
**Cons:** Re-introduces fetch surface inside the scan (FETCH_HEAD-race lessons,
417ea12), adds latency every dispatch, R1→R1+. Deferred to a future cross-node
hardening spec. Documented in Out of scope.

### Selected: 1
**Rationale:** Smallest change that makes the dispatch decision authoritative; fails
safe; uses an existing primitive; fully unit-testable.

---

## Design

### `scripts/vps/orchestrator.py` — `scan_queued`, just before line 795 `_pueue_add`

```python
    # BUG-205: authoritative TOCTOU re-check. The list_by_status() snapshot
    # (top of scan_queued) can go stale before we actually dispatch: callback
    # runs as a SEPARATE process and may have written blocked/done for this
    # spec via git plumbing, and git_pull is skipped while an agent is running
    # (stale local HEAD). The callback-audit.jsonl guard above is node-local +
    # time-windowed, NOT authoritative. Re-read the lifecycle SoT (HEAD) for
    # THIS spec right before pueue add; abort if it is no longer dispatchable.
    fresh = lifecycle.read_lifecycle(project_dir, spec_id)
    fresh_status = fresh.get("status") if fresh else None
    if fresh_status not in ("queued", "resumed"):
        log.info(
            "skip dispatch: %s status changed to %s after scan (TOCTOU re-check)",
            spec_id,
            fresh_status,
        )
        return False
```

**Placement (critical):** insert AFTER the two `pueue_has_active_*` dedup checks and
the `spec_path`/`pueue_env` setup, immediately BEFORE the `pueue_id = _pueue_add(...)`
call. It must be the **last** gate so the window between check and dispatch is minimal.

No other logic changes. The existing `callback-audit.jsonl` guard stays (cheap early
short-circuit); this is the authoritative backstop.

### `.claude/rules/dependencies.md`
Add a "Last Update" row:
`| 2026-06-19 | **BUG-205:** scan_queued authoritative lifecycle re-read before _pueue_add (TOCTOU close) | autopilot |`

---

## Implementation Plan

### Task 1: TOCTOU re-check in scan_queued

**Type:** code
**Files:**
- Modify: `scripts/vps/orchestrator.py:794-795`

**Context:** Insert an authoritative lifecycle re-read immediately before the
`_pueue_add` call (line 795). This is the last gate before dispatch, closing the
TOCTOU window between the `list_by_status` snapshot (line 731) and the actual
pueue submission. The new code goes between the `pueue_env` dict (line 794) and
the `pueue_id = _pueue_add(...)` call (line 795).

**Step 1: Insert TOCTOU re-check**

In `scripts/vps/orchestrator.py`, find the exact block:

```python
    pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": spec_path}
    pueue_id = _pueue_add(
```

Replace with:

```python
    pueue_env = {"CLAUDE_PROJECT_DIR": project_dir, "CLAUDE_CURRENT_SPEC_PATH": spec_path}
    # BUG-205: authoritative TOCTOU re-check.  The list_by_status() snapshot
    # (top of scan_queued) can go stale: callback runs as a SEPARATE process
    # and may have written blocked/done for this spec via git plumbing while
    # we were doing slot/pueue checks above.  Re-read the lifecycle SoT (HEAD)
    # for THIS spec right before pueue add; abort if no longer dispatchable.
    fresh = lifecycle.read_lifecycle(project_dir, spec_id)
    fresh_status = fresh.get("status") if fresh else None
    if fresh_status not in ("queued", "resumed"):
        log.info(
            "skip dispatch: %s status changed to %s after scan (TOCTOU re-check)",
            spec_id,
            fresh_status,
        )
        return False
    pueue_id = _pueue_add(
```

**Step 2: Verify file parses**

```bash
python3 -c "import ast; ast.parse(open('scripts/vps/orchestrator.py').read()); print('OK')"
```

Expected: `OK`

**Acceptance Criteria:**
- [ ] `grep -c "TOCTOU re-check" scripts/vps/orchestrator.py` returns >= 1
- [ ] `read_lifecycle` called for `spec_id` immediately before `_pueue_add` in `scan_queued`
- [ ] Dispatch aborts (return False, INFO log) when status not in {queued, resumed} or read returns None
- [ ] `ast.parse` succeeds
- [ ] No changes to `_pueue_add` signature or `scan_inbox`

---

### Task 2: Regression tests

**Type:** test
**Files:**
- Modify: `scripts/vps/tests/test_orchestrator.py` (append at end of file)

**Context:** Add three regression tests proving the TOCTOU re-check works: (a) stale-block
blocks dispatch, (b) happy-path still dispatches, (c) read-None blocks dispatch. Follow
the existing test patterns: class-based, `seed_project` fixture, `patch("orchestrator._pueue_add")`,
`patch.object(orchestrator.lifecycle, ...)`.

**Step 1: Append test class at end of file**

Append the following after the last line of `test_orchestrator.py` (after the
`TestHeartbeatMonitor` class, currently ending at line 559):

```python


class TestScanQueuedTOCTOU:
    """BUG-205: authoritative lifecycle re-check before _pueue_add in scan_queued."""

    def _seed_queued_spec(self, tmp_path: Path, spec_id: str = "BUG-100") -> Path:
        """Create minimal features dir with a spec file so scan_queued finds it."""
        features = tmp_path / "ai" / "features"
        features.mkdir(parents=True)
        spec = features / f"{spec_id}-2026-06-19-toctou-test.md"
        spec.write_text("# test\n\n**Priority:** P1\n")
        return tmp_path

    def test_stale_block_prevents_dispatch(self, tmp_path, seed_project):
        """EC-4: list_by_status returns queued but read_lifecycle returns blocked
        => _pueue_add NOT called, scan_queued returns False."""
        project_dir = str(self._seed_queued_spec(tmp_path))
        with (
            patch.object(
                orchestrator.lifecycle,
                "list_by_status",
                return_value=[{"spec_id": "BUG-100", "status": "queued"}],
            ),
            patch.object(
                orchestrator.lifecycle,
                "read_lifecycle",
                return_value={"spec_id": "BUG-100", "status": "blocked"},
            ),
            patch("orchestrator._pueue_add") as mock_add,
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
            patch("orchestrator.db.get_available_slots", return_value=2),
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.pueue_has_active_spec", return_value=False),
        ):
            result = orchestrator.scan_queued("testproject", project_dir)

        assert result is False
        mock_add.assert_not_called()

    def test_happy_path_dispatches(self, tmp_path, seed_project):
        """EC-5: read_lifecycle returns queued => _pueue_add called once."""
        project_dir = str(self._seed_queued_spec(tmp_path))
        with (
            patch.object(
                orchestrator.lifecycle,
                "list_by_status",
                return_value=[{"spec_id": "BUG-100", "status": "queued"}],
            ),
            patch.object(
                orchestrator.lifecycle,
                "read_lifecycle",
                return_value={"spec_id": "BUG-100", "status": "queued"},
            ),
            patch("orchestrator._pueue_add", return_value=42) as mock_add,
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
            patch("orchestrator.db.get_available_slots", return_value=2),
            patch("orchestrator.db.try_acquire_slot"),
            patch("orchestrator.db.log_task"),
            patch("orchestrator.db.update_project_phase"),
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.pueue_has_active_spec", return_value=False),
        ):
            result = orchestrator.scan_queued("testproject", project_dir)

        assert result is True
        mock_add.assert_called_once()

    def test_read_none_prevents_dispatch(self, tmp_path, seed_project):
        """EC-6: read_lifecycle returns None => _pueue_add NOT called."""
        project_dir = str(self._seed_queued_spec(tmp_path))
        with (
            patch.object(
                orchestrator.lifecycle,
                "list_by_status",
                return_value=[{"spec_id": "BUG-100", "status": "queued"}],
            ),
            patch.object(
                orchestrator.lifecycle,
                "read_lifecycle",
                return_value=None,
            ),
            patch("orchestrator._pueue_add") as mock_add,
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
            patch("orchestrator.db.get_available_slots", return_value=2),
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.pueue_has_active_spec", return_value=False),
        ):
            result = orchestrator.scan_queued("testproject", project_dir)

        assert result is False
        mock_add.assert_not_called()

    def test_stale_done_prevents_dispatch(self, tmp_path, seed_project):
        """Variant: spec flipped to done between snapshot and dispatch."""
        project_dir = str(self._seed_queued_spec(tmp_path))
        with (
            patch.object(
                orchestrator.lifecycle,
                "list_by_status",
                return_value=[{"spec_id": "BUG-100", "status": "queued"}],
            ),
            patch.object(
                orchestrator.lifecycle,
                "read_lifecycle",
                return_value={"spec_id": "BUG-100", "status": "done"},
            ),
            patch("orchestrator._pueue_add") as mock_add,
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
            patch("orchestrator.db.get_available_slots", return_value=2),
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.pueue_has_active_spec", return_value=False),
        ):
            result = orchestrator.scan_queued("testproject", project_dir)

        assert result is False
        mock_add.assert_not_called()

    def test_resumed_status_dispatches(self, tmp_path, seed_project):
        """Resumed is a valid dispatchable status — re-check must allow it."""
        project_dir = str(self._seed_queued_spec(tmp_path))
        with (
            patch.object(
                orchestrator.lifecycle,
                "list_by_status",
                return_value=[{"spec_id": "BUG-100", "status": "resumed"}],
            ),
            patch.object(
                orchestrator.lifecycle,
                "read_lifecycle",
                return_value={"spec_id": "BUG-100", "status": "resumed"},
            ),
            patch("orchestrator._pueue_add", return_value=42) as mock_add,
            patch("orchestrator.db.get_project_state", return_value={"provider": "claude"}),
            patch("orchestrator.db.get_available_slots", return_value=2),
            patch("orchestrator.db.try_acquire_slot"),
            patch("orchestrator.db.log_task"),
            patch("orchestrator.db.update_project_phase"),
            patch("orchestrator.pueue_has_active_label", return_value=False),
            patch("orchestrator.pueue_has_active_spec", return_value=False),
        ):
            result = orchestrator.scan_queued("testproject", project_dir)

        assert result is True
        mock_add.assert_called_once()
```

**Step 2: Verify tests are discoverable**

```bash
cd /home/dld/projects/dld
scripts/vps/venv/bin/python -m pytest scripts/vps/tests/test_orchestrator.py::TestScanQueuedTOCTOU --collect-only
```

Expected: 5 tests collected.

**Acceptance Criteria:**
- [ ] 5 tests in `TestScanQueuedTOCTOU` class (stale-block, happy-path, read-None, stale-done, resumed)
- [ ] All 5 tests pass after Task 1 implementation
- [ ] Full `test_orchestrator.py` suite green (no regressions)
- [ ] Tests follow existing patterns (class-based, `seed_project` fixture, `patch`)

---

### Task 3: dependencies.md row

**Type:** docs
**Files:**
- Modify: `.claude/rules/dependencies.md:677`

**Context:** Add a Last Update row documenting the BUG-205 change.

**Step 1: Append row**

In `.claude/rules/dependencies.md`, find:

```
| 2026-06-19 | **TECH-203:** claude-runner.py: AUTOPILOT_EFFORT env (default high, enum-validated) + ClaudeAgentOptions(effort=...). model-capabilities.md table synced to frontmatter SSOT. ADR-028 added. 9 template agent files synced to ADR-019 frontmatter. | autopilot |
```

Append after it:

```
| 2026-06-19 | **BUG-205:** scan_queued authoritative lifecycle re-read before _pueue_add (TOCTOU close). orchestrator.py reads lifecycle.read_lifecycle for chosen spec_id as last gate before dispatch; aborts if status changed. 5 regression tests. | autopilot |
```

**Acceptance Criteria:**
- [ ] `grep -c "BUG-205" .claude/rules/dependencies.md` returns >= 1

---

### Execution Order

Task 1 → Task 2 → Task 3

(Sequential: Task 2 tests verify Task 1 code; Task 3 is docs, no code dependency.)

### Dependencies

- Task 2 depends on Task 1 (tests exercise the new re-check code)
- Task 3 is independent (docs-only)

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | re-check wired | `grep -c "TOCTOU re-check" scripts/vps/orchestrator.py` | ≥1 | deterministic | design | P0 |
| EC-2 | uses read_lifecycle in scan_queued | `grep -n "read_lifecycle" scripts/vps/orchestrator.py` | present (≥1, in scan_queued) | deterministic | design | P0 |
| EC-3 | orchestrator parses | `python3 -c "import ast;ast.parse(open('scripts/vps/orchestrator.py').read())"` | exit 0 | deterministic | safety | P0 |
| EC-4 | stale-block blocks dispatch | pytest: list_by_status→queued, read_lifecycle→blocked | `_pueue_add` not called, returns False | integration | Task 2a | P0 |
| EC-5 | happy path still dispatches | pytest: read_lifecycle→queued | `_pueue_add` called once | integration | Task 2b | P0 |
| EC-6 | read-None blocks dispatch | pytest: read_lifecycle→None | no dispatch | integration | Task 2c | P1 |
| EC-7 | dependencies row | `grep -c "BUG-205" .claude/rules/dependencies.md` | ≥1 | deterministic | Task 3 | P2 |
| EC-8 | no template edits | `git diff --name-only` excludes `template/` | true | deterministic | scope guard | P0 |

### Coverage Summary
- Deterministic: 5 | Integration: 3 | LLM-Judge: 0 | Total: 8 (min 3) ✓

### TDD Order
1. EC-4 (write failing stale-block test first) → implement Task 1 → EC-4 passes.
2. EC-5/EC-6 (happy path + read-None).
3. EC-1/EC-2/EC-3 (static), EC-7/EC-8 (docs + scope guard).

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | orchestrator imports | `python3 -c "import ast;ast.parse(open('scripts/vps/orchestrator.py').read())"` | exit 0 | 10s |
| AV-S2 | re-check present | `grep -n "TOCTOU re-check" scripts/vps/orchestrator.py` | 1 line | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | stale block stops dispatch | seed queued spec; monkeypatch read_lifecycle→blocked | call scan_queued | returns False, _pueue_add not called |
| AV-F2 | happy path dispatches | seed queued spec; read_lifecycle→queued | call scan_queued | _pueue_add called once |

### Verify Command

```bash
cd /home/dld/projects/dld
python3 -c "import ast;ast.parse(open('scripts/vps/orchestrator.py').read());print('parse OK')"
grep -n "TOCTOU re-check" scripts/vps/orchestrator.py
grep -n "read_lifecycle" scripts/vps/orchestrator.py
# run the regression tests (orchestrator venv has pyyaml etc.):
scripts/vps/venv/bin/python -m pytest scripts/vps/tests/test_orchestrator.py -q 2>&1 | tail -20
grep -c "BUG-205" .claude/rules/dependencies.md
git diff --name-only | grep -c '^template/' || echo "0 template files (expected)"
```

> **Note:** tests require the orchestrator venv (`scripts/vps/venv`) for `pyyaml`.
> DB is NOT touched by this change (lifecycle.py has no db import); no `DB_PATH`
> override needed for these specific tests, but if the suite imports `db`, run with
> `DB_PATH=/tmp/test-orch.db` per project convention.

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] `scan_queued` re-reads the lifecycle SoT for the chosen spec immediately before
      `_pueue_add` and aborts dispatch when status ∉ {queued, resumed} or read is None
- [ ] Existing `callback-audit.jsonl` guard retained (not removed)
- [ ] Fail-safe direction confirmed (over-skip, never over-dispatch)

### Tests
- [ ] EC-4/EC-5/EC-6 regression tests pass (stale-block, happy-path, read-None)
- [ ] Full `test_orchestrator.py` suite green

### Technical
- [ ] No change to `_pueue_add` signature or `scan_inbox`
- [ ] No `template/` edits (orchestrator is DLD-specific)
- [ ] `dependencies.md` "Last Update" row added
- [ ] No inter-spec dependency/DAG logic added (out of scope — separate future FTR)

---

## Drift Log

**Checked:** 2026-06-19 UTC
**Result:** no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/orchestrator.py` | no change | Line refs verified: L731 list_by_status, L737 spec_id, L742-765 audit guard, L783-789 pueue dedup, L794 pueue_env, L795 _pueue_add — all match spec |
| `scripts/vps/tests/test_orchestrator.py` | no change | 560 lines, ends with TestHeartbeatMonitor. Patterns confirmed: class-based, seed_project, patch |
| `.claude/rules/dependencies.md` | no change | Last Update table ends at L677 (TECH-203 row) |

### References Updated
- No updates needed — all spec references are current.

---

## Autopilot Log
[Auto-populated by autopilot during execution]
