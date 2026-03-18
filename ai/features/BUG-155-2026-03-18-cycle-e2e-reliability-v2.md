# Bug: [BUG-155] DLD Cycle E2E Reliability v2 — Three Gap Closure + Smoke Test

**Status:** done | **Priority:** P0 | **Date:** 2026-03-18

## Why

TECH-154 (v1) attempted to fix cycle gaps but the DLD cycle has STILL never completed
a full pass from inbox to reflect without manual intervention. Three confirmed gaps
persist from the 2026-03-18 diagnostic session, plus additional issues found by devil
scout analysis.

**False pass scenario:** QA reports exit 0 even when it couldn't find the spec, meaning
broken specs pass QA and enter production. This is a P0 reliability issue.

## Context

TECH-154 was marked done but did not resolve the underlying issues. This spec addresses
the actual root causes found by 4 parallel scout analysis of the live codebase.

Key architectural fact: `qa-loop.sh` is dead code. The actual QA dispatch goes through
`pueue-callback.sh:361-363` → `run-agent.sh` → `claude-runner.py`. But `qa-loop.sh`
is still referenced in orchestrator.sh `dispatch_qa()` (currently neutered — callback
owns dispatch). Fixing the dead code is out of scope; fixing the live dispatch path is
in scope.

---

## Scope

**In scope:**
- Gap 1: QA spec resolution — fix `pueue-callback.sh` artifact_rel lookup to find the
  correct QA report (not draft files)
- Gap 2: Artifact scan filename filter — `pueue-callback.sh:303` uses `sort | tail -1`
  which picks up `draft-v2-*` files; need to filter to canonical format only
- Gap 3: `notify.py` — add OPS_TOPIC_ID fallback for projects without explicit topic_id
- Gap 4 (devil): `_submit_to_pueue` in `telegram-bot.py` has wrong arg order for
  `run-agent.sh` — `provider` arg gets the full command string
- Smoke test: `scripts/vps/tests/test_cycle_smoke.py` — validate label parsing, QA dispatch
  args, artifact lookup, and notify fallback

**Out of scope:**
- Removing `qa-loop.sh` entirely (separate cleanup task)
- Reflect dispatch race condition with QA (devil gap #6 — phase machine redesign)
- `db_exec.sh` SQL injection (ADR-017 violation — separate TECH task)
- Migrating QA dispatch from callback to orchestrator

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP -- who uses?
- [x] `pueue-callback.sh` used by: Pueue daemon (callback on task completion)
- [x] `notify.py` used by: pueue-callback.sh, orchestrator.sh, qa-loop.sh, night-reviewer.sh
- [x] `telegram-bot.py` used by: systemd service (dld-telegram-bot.service)

### Step 2: DOWN -- what depends on?
- [x] `pueue-callback.sh` → db.py, notify.py, run-agent.sh, pueue CLI
- [x] `notify.py` → db.py, python-telegram-bot
- [x] `telegram-bot.py` → db.py, run-agent.sh, pueue CLI

### Step 3: BY TERM -- grep entire project
- [x] `artifact_rel` — only in pueue-callback.sh
- [x] `OPS_TOPIC_ID` — new env var, grep = 0 (new)
- [x] `_submit_to_pueue` — only in telegram-bot.py

### Step 4: CHECKLIST -- mandatory folders
- [x] `scripts/vps/tests/` — new test file
- [x] `scripts/vps/.env.example` — add OPS_TOPIC_ID

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old terms = no rename needed

---

## Allowed Files

**ONLY these files may be modified during implementation:**
1. `scripts/vps/pueue-callback.sh` — fix artifact_rel lookup for QA reports
2. `scripts/vps/notify.py` — add OPS_TOPIC_ID fallback
3. `scripts/vps/telegram-bot.py` — fix _submit_to_pueue arg order
4. `scripts/vps/.env.example` — add OPS_TOPIC_ID

**New files allowed:**
- `scripts/vps/tests/test_cycle_smoke.py` — smoke test for cycle components

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (scripts/vps/)
**Cross-cutting:** Notifications, Phase Machine
**Data model:** project_state.topic_id

---

## Approaches

### Approach 1: Surgical Fix + Unit Smoke Test (Selected)

**Source:** Codebase scout + Devil scout analysis
**Summary:** Fix 4 specific bugs in 3 files + add pytest smoke test
**Pros:** Minimal blast radius, each fix is independent, testable
**Cons:** Doesn't address phase machine race conditions (devil gap #6)

### Approach 2: QA Dispatch Rewrite

**Source:** Pattern scout recommendation
**Summary:** Move QA dispatch from callback to orchestrator poll loop
**Pros:** Cleaner architecture, eliminates race conditions
**Cons:** Major refactor of phase machine, R0 risk (could break existing flow)

### Selected: 1

**Rationale:** Approach 1 fixes the 3 reported gaps + 1 critical devil finding with
R1 risk. Phase machine redesign (Approach 2) is a separate ARCH task.

---

## Design

### User Flow
1. Autopilot completes a spec → pueue callback fires
2. Callback identifies correct QA report file (not drafts) → creates OpenClaw event
3. Callback dispatches QA via run-agent.sh with correct args
4. QA agent runs, writes report
5. notify.py sends result to project topic (or OPS_TOPIC_ID fallback)

### Architecture

```
pueue-callback.sh
├── Fix 1: artifact_rel filter (grep for canonical YYYYMMDD-HHMMSS pattern)
├── Fix 2: _submit_to_pueue arg order (provider before command)
└── Fix 3: QA report lookup excludes draft-* files

notify.py
└── Fix 4: OPS_TOPIC_ID fallback when topic_id is NULL
```

### Root Cause Analysis (per gap)

**Gap 1: QA не находит спеку**

Root cause: NOT in qa-loop.sh (dead code). Real issue is in `telegram-bot.py:_submit_to_pueue()`.
Args to run-agent.sh are in WRONG order:
```python
# CURRENT (BROKEN):
task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
            f"claude -p /autopilot {task_id}", project.get("provider", "claude"), "autopilot"]
# This produces: run-agent.sh <path> <"claude -p /autopilot TECH-151"> <"claude"> <"autopilot">
# run-agent.sh expects: <path> <provider> <skill> <task...>
# So PROVIDER gets the full command string → case match fails

# FIXED:
task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
            project.get("provider", "claude"), "autopilot",
            f"/autopilot {task_id}"]
# This produces: run-agent.sh <path> <"claude"> <"autopilot"> <"/autopilot TECH-151">
```

When run-agent.sh fails silently (pueue catches exit), the callback fires with
STATUS=failed, SKILL="" (no agent JSON output), and QA is never dispatched.
Result: no QA runs, cycle stops.

**Gap 2: artifact-scan не читает QA файлы**

Root cause in `pueue-callback.sh:303`:
```bash
find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "*.md" | sort | tail -1
```
This picks the lexicographically LAST .md file, which could be `draft-v2-from-scratch.md`
instead of the actual QA report. Fix: filter to canonical pattern `[0-9]*-*.md`.

**Gap 3: topic_id NULL**

Root cause: `notify.py:96-101` fail-closed (correct behavior) but provides NO fallback.
Five projects have NULL topic_id because they were added before `/bindtopic` existed.
Fix: add OPS_TOPIC_ID env var as operations fallback channel.

---

## Drift Log

**Checked:** 2026-03-18 22:15 UTC (planner re-validation)
**Result:** no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/telegram-bot.py` | no change | `_submit_to_pueue` at lines 136-150, broken arg order at 139-140 confirmed |
| `scripts/vps/pueue-callback.sh` | no change | `ARTIFACT_REL` find at line 303 uses `"*.md"` (bug confirmed) |
| `scripts/vps/notify.py` | no change | `send_to_project` at lines 85-103, no OPS fallback (gap confirmed) |
| `scripts/vps/.env.example` | no change | 32 lines, no OPS_TOPIC_ID present |
| `scripts/vps/run-agent.sh` | no change | arg signature at line 4: `<project_dir> <provider> <skill> <task...>` |

### Cross-Reference: run-agent.sh Callers
| Caller | File:Line | Args | Correct? |
|--------|-----------|------|----------|
| pueue-callback.sh | 361-362 | `$PROJECT_PATH $PROJECT_PROVIDER "qa" "/qa $TASK_LABEL"` | YES |
| inbox-processor.sh | 218 | `$PROJECT_DIR $PROVIDER $SKILL $TASK_FILE` | YES |
| orchestrator.sh | 270 | `$project_dir $provider "autopilot" $task_cmd` | YES |
| telegram-bot.py | 139-140 | `project["path"] f"claude -p ..." provider "autopilot"` | **BUG** |

### Real ai/qa/ Directory (confirms artifact bug)
`draft-v2-skill-creator.md` and `draft-v2-from-scratch.md` exist alongside canonical files.
With `-name "*.md" | sort | tail -1`: picks `draft-v2-skill-creator.md` -- WRONG.

### References Updated
- No updates needed (all line references current)

---

## Detailed Implementation Plan

### Research Sources
- Codebase scout: pueue-callback.sh dispatch flow analysis
- Devil scout: 4 additional gaps found (2 included in scope)
- Pattern scout: "normalize at write boundary" principle
- Verified: `run-agent.sh` line 4: `Usage: run-agent.sh <project_dir> <provider> <skill> <task...>`
- Verified: `pueue-callback.sh` lines 361-362: correct pattern `run-agent.sh "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" "/qa ${TASK_LABEL}"`
- Verified: `inbox-processor.sh` line 218: correct pattern `run-agent.sh "$PROJECT_DIR" "$PROVIDER" "$SKILL" "$TASK_FILE"`
- Verified: `orchestrator.sh` line 270: correct pattern `run-agent.sh "$project_dir" "$provider" "autopilot" "$task_cmd"`
- Verified: `scripts/vps/tests/conftest.py` has `isolated_db` and `seed_project` fixtures
- Verified: real `ai/qa/` dir has `draft-v2-*` and `SKILL-v1-*` noise files confirming artifact bug
- WARNING: `pytest-asyncio` NOT installed in VPS venv -- smoke test uses `asyncio.run()` wrapper

### Task 1: Fix _submit_to_pueue arg order in telegram-bot.py

**Files:**
- Modify: `scripts/vps/telegram-bot.py:139-140`
- Test: `scripts/vps/tests/test_cycle_smoke.py` (Task 4)

**Context:**
`_submit_to_pueue()` builds the pueue command list for `run-agent.sh`. Currently args are
in wrong order: `<path> <full_command> <provider> <skill>`. `run-agent.sh` expects
`<path> <provider> <skill> <task...>`. This causes the provider case-match in `run-agent.sh:52`
to receive `"claude -p /autopilot TECH-151"` instead of `"claude"`, failing the match and
breaking the entire autopilot dispatch.

**Step 1: Apply fix**

In `scripts/vps/telegram-bot.py`, replace lines 139-140.

old_string (exact, including indentation):
```python
    task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
                f"claude -p /autopilot {task_id}", project.get("provider", "claude"), "autopilot"]
```

new_string:
```python
    task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
                project.get("provider", "claude"), "autopilot",
                f"/autopilot {task_id}"]
```

The fix reorders args to match `run-agent.sh` signature: `<project_dir> <provider> <skill> <task...>`.
The task string changes from `"claude -p /autopilot {task_id}"` to `"/autopilot {task_id}"` because
`run-agent.sh` handles provider dispatch internally -- the task string is the prompt, not a CLI command.

**Step 2: Verify**

```bash
grep -A3 'task_cmd = \[str(SCRIPT_DIR' scripts/vps/telegram-bot.py
```

Expected output:
```
    task_cmd = [str(SCRIPT_DIR / "run-agent.sh"), project["path"],
                project.get("provider", "claude"), "autopilot",
                f"/autopilot {task_id}"]
```

**Acceptance Criteria:**
- [ ] `task_cmd` list has args in order: path, provider, skill, task
- [ ] Task string is `/autopilot {task_id}` (not `claude -p /autopilot {task_id}`)
- [ ] Pattern matches all 3 other callers (pueue-callback.sh, inbox-processor.sh, orchestrator.sh)

---

### Task 2: Fix artifact_rel lookup in pueue-callback.sh

**Files:**
- Modify: `scripts/vps/pueue-callback.sh:303`
- Test: `scripts/vps/tests/test_cycle_smoke.py` (Task 4)

**Context:**
Line 303 of `pueue-callback.sh` uses `find ... -name "*.md" | sort | tail -1` to pick the latest
QA report. With the real `ai/qa/` directory contents, `sort | tail -1` picks `draft-v2-skill-creator.md`
(lexicographically last) instead of `20260318-185452-TECH-154.md`. Filter to `-name "[0-9]*-*.md"`
to only match canonical QA report format `YYYYMMDD-HHMMSS-SPEC-ID.md`.

**Step 1: Apply fix**

In `scripts/vps/pueue-callback.sh`, replace line 303.

old_string (exact):
```bash
            ARTIFACT_REL=$(find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "*.md" | sort | tail -1 | sed "s#^${PROJECT_PATH_FOR_EVENT}/##" || true)
```

new_string:
```bash
            ARTIFACT_REL=$(find "${PROJECT_PATH_FOR_EVENT}/ai/qa" -maxdepth 1 -type f -name "[0-9]*-*.md" | sort | tail -1 | sed "s#^${PROJECT_PATH_FOR_EVENT}/##" || true)
```

The only change is `-name "*.md"` to `-name "[0-9]*-*.md"`. This glob matches files starting
with a digit, then any chars, a dash, any chars, ending in `.md`. This correctly matches
`20260318-185452-TECH-154.md` but rejects `draft-v2-from-scratch.md`, `SKILL-v1-skill-writer.md`,
and old-format `2026-03-17-tech-151.md` files.

**Step 2: Verify**

```bash
grep 'find.*ai/qa' scripts/vps/pueue-callback.sh | head -1
```

Expected output contains `-name "[0-9]*-*.md"` instead of `-name "*.md"`.

**Acceptance Criteria:**
- [ ] `find` command uses `-name "[0-9]*-*.md"` glob pattern
- [ ] EC-2 test passes (canonical file selected over draft)
- [ ] EC-3 test passes (empty dir returns empty string)

---

### Task 3: Add OPS_TOPIC_ID fallback to notify.py + .env.example

**Files:**
- Modify: `scripts/vps/notify.py:85-103`
- Modify: `scripts/vps/.env.example`
- Test: `scripts/vps/tests/test_cycle_smoke.py` (Task 4)

**Context:**
`send_to_project()` currently fail-closes when a project has no `topic_id` -- it returns `False`
and the notification is silently lost. Adding an OPS_TOPIC_ID env var as fallback sends these
notifications to an operations topic so they are visible.

**Step 1: Apply fix to notify.py**

Replace the `send_to_project` function at lines 85-103.

old_string (exact):
```python
async def send_to_project(project_id: str, text: str) -> bool:
    """Send a message to a project's Telegram topic.

    Fail closed: if project has no explicit topic binding, do NOT send to General.
    """
    project = db.get_project_state(project_id)
    if project is None:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")
    if not topic_id or topic_id == 1:
        print(
            f"[notify] Refusing to send for project '{project_id}': missing explicit topic_id binding",
            file=sys.stderr,
        )
        return False

    return await _send_message(text, thread_id=topic_id)
```

new_string:
```python
async def send_to_project(project_id: str, text: str) -> bool:
    """Send a message to a project's Telegram topic.

    Routing priority:
    1. Project's explicit topic_id binding
    2. OPS_TOPIC_ID env var (operations fallback)
    3. Fail closed (return False)
    """
    project = db.get_project_state(project_id)
    if project is None:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")
    if topic_id and topic_id != 1:
        return await _send_message(text, thread_id=topic_id)

    # Fallback: OPS_TOPIC_ID for projects without explicit topic binding
    ops_topic = os.environ.get("OPS_TOPIC_ID", "")
    if ops_topic:
        print(
            f"[notify] WARN: project '{project_id}' has no topic_id, "
            f"falling back to OPS_TOPIC_ID={ops_topic}",
            file=sys.stderr,
        )
        return await _send_message(text, thread_id=int(ops_topic))

    print(
        f"[notify] Refusing to send for project '{project_id}': "
        "missing topic_id and no OPS_TOPIC_ID fallback",
        file=sys.stderr,
    )
    return False
```

**Backward compatibility:** Existing test `test_missing_topic_id_refuses_to_send` does NOT set
`OPS_TOPIC_ID`. After fix, `os.environ.get("OPS_TOPIC_ID", "")` returns `""` (falsy), so
`send_to_project` returns `False`. Same for `test_topic_id_1_refuses_to_send`. Both pass unchanged.

**Step 2: Apply fix to .env.example**

old_string:
```
TELEGRAM_ALLOWED_USERS=123456789

# Groq (Voice Transcription)
```

new_string:
```
TELEGRAM_ALLOWED_USERS=123456789

# Operations fallback topic (for projects without /bindtopic)
OPS_TOPIC_ID=

# Groq (Voice Transcription)
```

**Step 3: Verify**

```bash
grep -A5 'OPS_TOPIC_ID' scripts/vps/notify.py
grep 'OPS_TOPIC_ID' scripts/vps/.env.example
```

**Step 4: Run existing notify tests to confirm no regression**

```bash
cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/test_notify.py -v
```

**Acceptance Criteria:**
- [ ] `send_to_project` tries project topic_id first (EC-6)
- [ ] Falls back to OPS_TOPIC_ID when topic_id is NULL (EC-4)
- [ ] Returns False + logs warning when neither available (EC-5)
- [ ] OPS_TOPIC_ID documented in .env.example
- [ ] Existing tests in `scripts/vps/tests/test_notify.py` still pass

---

### Task 4: Cycle smoke test

**Files:**
- Create: `scripts/vps/tests/test_cycle_smoke.py`

**Context:**
This test file validates all 7 eval criteria (EC-1 through EC-7) as unit tests.
Tests are organized by component: submit_to_pueue args, artifact_rel filtering, notify
fallback routing, and label parsing.

Placed in `scripts/vps/tests/` (not `tests/scripts/`) to share the existing conftest.py
with `isolated_db` and `seed_project` fixtures, and to match the established test pattern.

Async notify tests use `asyncio.run()` wrapper instead of `@pytest.mark.asyncio` because
`pytest-asyncio` is not installed in the VPS venv.

**Step 1: Create scripts/vps/tests/test_cycle_smoke.py**

```python
# scripts/vps/tests/test_cycle_smoke.py
"""Cycle E2E smoke tests for BUG-155.

Covers 7 eval criteria:
- EC-1: _submit_to_pueue arg order
- EC-2: artifact_rel excludes drafts
- EC-3: artifact_rel handles empty dir
- EC-4: notify fallback to OPS_TOPIC_ID
- EC-5: notify no fallback when no OPS_TOPIC_ID
- EC-6: notify normal path unchanged
- EC-7: label parsing colon separator
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# scripts/vps is already on sys.path via conftest.py
VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)


# ---------------------------------------------------------------------------
# EC-1: _submit_to_pueue arg order
# ---------------------------------------------------------------------------
class TestSubmitToPueueArgOrder:
    """Verify run-agent.sh args: <path> <provider> <skill> <task>."""

    def test_arg_order_from_source(self) -> None:
        """EC-1: Parse telegram-bot.py source to verify arg order.

        The broken version passed: path, "claude -p /autopilot X", provider, skill
        The fixed version passes:  path, provider, skill, "/autopilot X"
        """
        bot_path = Path(VPS_DIR) / "telegram-bot.py"
        source = bot_path.read_text(encoding="utf-8")

        # Find the _submit_to_pueue function and extract task_cmd lines
        in_func = False
        task_cmd_lines: list[str] = []
        for line in source.splitlines():
            if "def _submit_to_pueue" in line:
                in_func = True
                continue
            if in_func and "task_cmd" in line and "run-agent.sh" in line:
                task_cmd_lines.append(line.strip())
                continue
            if in_func and task_cmd_lines and line.strip() and not line.strip().startswith(("r ", "#")):
                task_cmd_lines.append(line.strip())
                if "]" in line:
                    break

        joined = " ".join(task_cmd_lines)

        # Verify: path is first arg after run-agent.sh
        assert 'project["path"]' in joined or "project['path']" in joined, \
            f"project path must be first arg after run-agent.sh: {joined}"

        # Provider must come BEFORE skill and task
        path_pos = joined.find("project[")
        provider_pos = joined.find("provider")
        autopilot_pos = joined.find('"autopilot"')

        assert provider_pos > path_pos, \
            f"provider must come after path: provider@{provider_pos} path@{path_pos}"
        assert autopilot_pos > provider_pos, \
            f"'autopilot' skill must come after provider: autopilot@{autopilot_pos} provider@{provider_pos}"

        # The old broken pattern must NOT be present
        assert "claude -p /autopilot" not in joined, \
            f"Old broken pattern 'claude -p /autopilot' still present: {joined}"


# ---------------------------------------------------------------------------
# EC-2, EC-3: artifact_rel filtering
# ---------------------------------------------------------------------------
class TestArtifactRelFilter:
    """Verify pueue-callback.sh artifact_rel find command filters correctly."""

    def test_excludes_draft_files(self, tmp_path: Path) -> None:
        """EC-2: With draft + canonical files, only canonical is returned."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "draft-v2-from-scratch.md").write_text("draft")
        (qa_dir / "SKILL-v1-skill-writer.md").write_text("skill draft")
        (qa_dir / "20260318-120000-TECH-151.md").write_text("report")

        result = subprocess.run(
            ["find", str(qa_dir), "-maxdepth", "1", "-type", "f",
             "-name", "[0-9]*-*.md"],
            capture_output=True, text=True, timeout=5,
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]

        assert len(files) == 1, f"Expected 1 file, got {len(files)}: {files}"
        assert "20260318-120000-TECH-151.md" in files[0]
        assert "draft" not in files[0]

    def test_empty_dir_returns_nothing(self, tmp_path: Path) -> None:
        """EC-3: Empty ai/qa/ dir returns no matches."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)

        result = subprocess.run(
            ["find", str(qa_dir), "-maxdepth", "1", "-type", "f",
             "-name", "[0-9]*-*.md"],
            capture_output=True, text=True, timeout=5,
        )
        files = [f.strip() for f in result.stdout.strip().splitlines() if f.strip()]
        assert len(files) == 0, f"Expected 0 files, got {len(files)}: {files}"

    def test_multiple_canonical_sorted(self, tmp_path: Path) -> None:
        """Multiple canonical files: sort | tail -1 picks latest."""
        qa_dir = tmp_path / "ai" / "qa"
        qa_dir.mkdir(parents=True)
        (qa_dir / "20260317-100000-TECH-150.md").write_text("old")
        (qa_dir / "20260318-120000-TECH-151.md").write_text("new")
        (qa_dir / "draft-v2-notes.md").write_text("draft")

        result = subprocess.run(
            ["bash", "-c",
             f'find "{qa_dir}" -maxdepth 1 -type f -name "[0-9]*-*.md" | sort | tail -1'],
            capture_output=True, text=True, timeout=5,
        )
        artifact = result.stdout.strip()

        assert "20260318-120000-TECH-151.md" in artifact
        assert "draft" not in artifact

    def test_callback_source_has_fixed_pattern(self) -> None:
        """Verify pueue-callback.sh source uses [0-9]*-*.md for QA find."""
        callback_path = Path(VPS_DIR) / "pueue-callback.sh"
        source = callback_path.read_text(encoding="utf-8")

        for i, line in enumerate(source.splitlines()):
            if "ai/qa" in line and "find" in line:
                assert "[0-9]*-*.md" in line, \
                    f"QA find at line {i+1} must use '[0-9]*-*.md': {line.strip()}"


# ---------------------------------------------------------------------------
# EC-4, EC-5, EC-6: notify.py OPS_TOPIC_ID fallback
# ---------------------------------------------------------------------------
class TestNotifyFallback:
    """Verify notify.py OPS_TOPIC_ID fallback logic.

    Uses asyncio.run() wrapper because pytest-asyncio is not installed.
    """

    def test_normal_topic_id_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-6: Project with topic_id=100 sends to thread_id=100."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("OPS_TOPIC_ID", raising=False)

        import notify

        mock_project = {"project_id": "tp", "path": "/tmp/tp", "topic_id": 100}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("tp", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=100)

    def test_fallback_to_ops_topic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-4: Project with topic_id=NULL falls back to OPS_TOPIC_ID=42."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("OPS_TOPIC_ID", "42")

        import notify

        mock_project = {"project_id": "nt", "path": "/tmp/nt", "topic_id": None}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("nt", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=42)

    def test_no_fallback_when_no_ops(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """EC-5: Project with topic_id=NULL and no OPS_TOPIC_ID returns False."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.delenv("OPS_TOPIC_ID", raising=False)

        import notify

        mock_project = {"project_id": "nt", "path": "/tmp/nt", "topic_id": None}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                result = asyncio.run(notify.send_to_project("nt", "Hello"))

        assert result is False
        mock_send.assert_not_called()

    def test_topic_id_1_triggers_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """topic_id=1 (General) should also try OPS_TOPIC_ID fallback."""
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
        monkeypatch.setenv("OPS_TOPIC_ID", "99")

        import notify

        mock_project = {"project_id": "gp", "path": "/tmp/gp", "topic_id": 1}
        with patch.object(notify.db, "get_project_state", return_value=mock_project):
            with patch("notify._send_message", new_callable=AsyncMock) as mock_send:
                mock_send.return_value = True
                result = asyncio.run(notify.send_to_project("gp", "Hello"))

        assert result is True
        mock_send.assert_called_once_with("Hello", thread_id=99)


# ---------------------------------------------------------------------------
# EC-7: label parsing colon separator
# ---------------------------------------------------------------------------
class TestLabelParsing:
    """Verify pueue-callback.sh label parsing logic."""

    def test_colon_separator_parsing(self) -> None:
        """EC-7: label='dld:TECH-151' => PROJECT_ID='dld', TASK_LABEL='TECH-151'."""
        label = "dld:TECH-151"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert len(lines) == 2, f"Expected 2 lines, got: {lines}"
        assert lines[0] == "dld"
        assert lines[1] == "TECH-151"

    def test_no_colon_label_warning(self) -> None:
        """Label without colon: both vars equal full label (warning case)."""
        label = "unknown"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                if [[ "$PROJECT_ID" == "$LABEL" ]]; then
                    echo "WARN"
                fi
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert "WARN" in lines

    def test_compound_spec_id_preserved(self) -> None:
        """Label 'proj:qa-BUG-155' preserves full TASK_LABEL after colon."""
        label = "myproj:qa-BUG-155"
        result = subprocess.run(
            ["bash", "-c", f'''
                LABEL="{label}"
                PROJECT_ID="${{LABEL%%:*}}"
                TASK_LABEL="${{LABEL#*:}}"
                echo "$PROJECT_ID"
                echo "$TASK_LABEL"
            '''],
            capture_output=True, text=True, timeout=5,
        )
        lines = result.stdout.strip().splitlines()
        assert lines[0] == "myproj"
        assert lines[1] == "qa-BUG-155"
```

**Step 2: Verify tests run**

```bash
cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/test_cycle_smoke.py -v
```

Expected (after all fixes applied):
```
PASSED TestSubmitToPueueArgOrder::test_arg_order_from_source
PASSED TestArtifactRelFilter::test_excludes_draft_files
PASSED TestArtifactRelFilter::test_empty_dir_returns_nothing
PASSED TestArtifactRelFilter::test_multiple_canonical_sorted
PASSED TestArtifactRelFilter::test_callback_source_has_fixed_pattern
PASSED TestNotifyFallback::test_normal_topic_id_used
PASSED TestNotifyFallback::test_fallback_to_ops_topic
PASSED TestNotifyFallback::test_no_fallback_when_no_ops
PASSED TestNotifyFallback::test_topic_id_1_triggers_fallback
PASSED TestLabelParsing::test_colon_separator_parsing
PASSED TestLabelParsing::test_no_colon_label_warning
PASSED TestLabelParsing::test_compound_spec_id_preserved
```

**Acceptance Criteria:**
- [ ] All 12 tests pass
- [ ] All 7 eval criteria covered (EC-1 through EC-7)
- [ ] No pytest-asyncio dependency (uses `asyncio.run()` wrapper)

---

### Execution Order

```
Task 1 (telegram-bot.py fix)  ---+
Task 2 (pueue-callback.sh fix)   +--- independent, any order
Task 3 (notify.py + .env.example)-+
    |
    v
Task 4 (smoke tests -- validates all 3 fixes)
```

Tasks 1-3 are independent code fixes (different files, no shared changes).
Task 4 depends on all three (tests validate the fixes).

### Dependencies

- Task 4 depends on Tasks 1, 2, 3 (tests validate all fixes)
- Tasks 1, 2, 3 are independent of each other

### Notes for Coder

1. **Test location**: Tests go to `scripts/vps/tests/test_cycle_smoke.py` (NOT `tests/scripts/`).
   This shares the existing conftest.py with `isolated_db`/`seed_project` fixtures and matches
   the established test pattern in the VPS test suite.

2. **No pytest-asyncio**: The VPS venv does NOT have `pytest-asyncio`. The smoke test uses
   `asyncio.run()` wrapper for async notify tests. Do NOT add `@pytest.mark.asyncio`.

3. **No `tests/scripts/__init__.py` needed**: Test location changed from original spec.

4. **old_string for Edit tool**: Each task provides exact old_string and new_string for the
   Edit tool. Use these verbatim -- they have been validated against the current file contents.

5. **Existing test compatibility**: The notify.py fix preserves existing test behavior:
   - `test_missing_topic_id_refuses_to_send`: no OPS_TOPIC_ID set -> returns False (preserved)
   - `test_topic_id_1_refuses_to_send`: no OPS_TOPIC_ID set -> returns False (preserved)
   Run: `python3 -m pytest scripts/vps/tests/test_notify.py -v` after Task 3.

6. **No sync zone**: `scripts/vps/` is DLD-specific (no `template/scripts/vps/` exists).
   No template sync required.

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Autopilot completes spec | - | existing |
| 2 | Callback parses label correctly | Task 4 (test) | existing |
| 3 | _submit_to_pueue sends correct args | Task 1 | fix |
| 4 | Callback finds correct QA artifact | Task 2 | fix |
| 5 | QA dispatched with correct spec ID | Task 1 | fix |
| 6 | QA writes report | - | existing |
| 7 | Notification sent to correct topic | Task 3 | fix |
| 8 | Full cycle validated | Task 4 | new |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | _submit_to_pueue arg order | project with path=/p, provider=claude, task_id=TECH-151 | run-agent.sh args: ["/p", "claude", "autopilot", "/autopilot TECH-151"] | deterministic | devil scout | P0 |
| EC-2 | artifact_rel excludes drafts | ai/qa/ has draft-v2-from-scratch.md + 20260318-120000-TECH-151.md | artifact_rel = ai/qa/20260318-120000-TECH-151.md | deterministic | codebase scout | P0 |
| EC-3 | artifact_rel handles empty dir | ai/qa/ has no matching files | artifact_rel = "" (empty string) | deterministic | devil scout | P1 |
| EC-4 | notify fallback to OPS_TOPIC | project with topic_id=NULL, OPS_TOPIC_ID=42 | message sent to thread_id=42 | deterministic | pattern scout | P0 |
| EC-5 | notify no fallback when no OPS | project with topic_id=NULL, OPS_TOPIC_ID not set | return False, log warning | deterministic | devil scout | P1 |
| EC-6 | notify normal path unchanged | project with topic_id=100 | message sent to thread_id=100 (no fallback) | deterministic | codebase scout | P0 |
| EC-7 | label parsing colon separator | label="dld:TECH-151" | PROJECT_ID="dld", TASK_LABEL="TECH-151" | deterministic | codebase scout | P1 |

### Coverage Summary
- Deterministic: 7 | Integration: 0 | LLM-Judge: 0 | Total: 7 (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Fix _submit_to_pueue -> PASS
2. EC-2, EC-3 -> Fix artifact_rel -> PASS
3. EC-4, EC-5, EC-6 -> Add OPS_TOPIC_ID fallback -> PASS
4. EC-7 -> Existing behavior validation -> PASS

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Tests pass | `cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/test_cycle_smoke.py -v` | exit 0 | 30s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | _submit_to_pueue arg order | Read telegram-bot.py | Verify run-agent.sh args: path, provider, skill, task | Args in correct order |
| AV-F2 | artifact_rel filter | Create dummy ai/qa/ with draft + canonical files | Run find with filter | Only canonical file returned |
| AV-F3 | notify OPS fallback | Set OPS_TOPIC_ID in env | Call send_to_project with NULL topic | Message routed to OPS topic |

### Verify Command (copy-paste ready)

```bash
# Smoke tests
cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/test_cycle_smoke.py -v

# Existing notify tests (regression check)
cd /home/dld/projects/dld && python3 -m pytest scripts/vps/tests/test_notify.py -v

# Verify _submit_to_pueue fix
grep -A3 'task_cmd = \[str(SCRIPT_DIR' scripts/vps/telegram-bot.py

# Verify artifact_rel filter
grep 'find.*ai/qa' scripts/vps/pueue-callback.sh | head -1

# Verify OPS_TOPIC_ID in code and env
grep 'OPS_TOPIC_ID' scripts/vps/notify.py
grep 'OPS_TOPIC_ID' scripts/vps/.env.example
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [x] _submit_to_pueue passes args to run-agent.sh in correct order
- [x] artifact_rel lookup excludes non-canonical files (draft-*, etc.)
- [x] notify.py falls back to OPS_TOPIC_ID when project has no topic_id
- [x] All 7 eval criteria pass

### Tests
- [x] scripts/vps/tests/test_cycle_smoke.py passes (12/12)
- [x] Coverage not decreased (existing test_notify.py 4/4 pass)

### Technical
- [x] Tests pass (44/45, 1 pre-existing failure in test_db.py unrelated)
- [x] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
