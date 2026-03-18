# Tech: [TECH-154] DLD Cycle E2E Reliability — First Full Pass

**Status:** queued | **Priority:** P0 | **Date:** 2026-03-18

## Why

Ни один полный цикл `inbox → spark → queued → autopilot → QA → reflect` не прошёл
от начала до конца без ручного вмешательства. Четыре конкретных разрыва найдены
в ходе сессии 2026-03-18:

1. **QA не находит спеку** — qa-loop.sh запускается без передачи пути к spec-файлу;
   агент спрашивает "что тестировать?" и продолжает без ответа (exit 0 = false pass).
2. **Reflect не запускался** — pueue-callback.sh проверял `PENDING_COUNT` diary/index.md;
   все записи `done` → reflect тихо пропускался после каждого autopilot.
   *Исправлено в e7d619d, но требует верификации.*
3. **QA report статус unknown** — три файла `ai/qa/2026-03-17-tech-*.md` со статусом
   `unknown`; openclaw-artifact-scan.py не может их прочитать.
4. **topic_id NULL для 5 из 6 проектов** — notify.py не знает куда слать уведомления;
   фиксы в 1b358e4 требуют `/bindtopic` в каждом топике.

## Scope

**In scope:**

- `qa-loop.sh`: передавать путь к spec-файлу как аргумент; fallback — fail с `exit 1`
  если спека не найдена (не продолжать вслепую)
- `pueue-callback.sh`: проверить что reflect dispatch работает после e7d619d (smoke test)
- `openclaw-artifact-scan.py`: распознавать формат `2026-MM-DD-spec-id.md` (lowercase, дефисы)
  помимо текущего `YYYYMMDD-HHMMSS-SPEC-ID.md`
- `notify.py` + `/bindtopic`: добавить guard — если topic_id NULL, логировать и fail-close
  (уже частично в 1b358e4, проверить полноту)
- Один интеграционный smoke test: запустить дешёвый autopilot (echo task) и убедиться
  что QA + reflect задиспатчены и дошли до completion

**Out of scope:**

- Перенос QA/Reflect dispatch в orchestrator poll cycle (это TECH-155 если нужно)
- Починка diary записей в awardybot (это проектная задача, не DLD цикл)
- Переработка структуры QA отчётов

---

## Root Cause Analysis

### Разрыв 1: QA вслепую

`qa-loop.sh` вызывается из pueue-callback.sh:
```bash
run-agent.sh "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" "/qa Проверь изменения после ${TASK_LABEL}"
```

`TASK_LABEL` содержит ID типа `awardybot:autopilot-FTR-702`, но qa-скилл ищет
спеку по ID самостоятельно — и не находит, потому что ID в label не совпадает
с именем файла. Нужно передавать `SPEC_ID` явно.

### Разрыв 2: Reflect пропускался (исправлен e7d619d)

```bash
PENDING_COUNT=$(grep -c '| pending |' "$DIARY_INDEX")
if (( PENDING_COUNT < 1 )); then echo "Skipping reflect" ...
```

Все diary записи `done` → reflect никогда не запускался. Удалено в e7d619d.

### Разрыв 3: artifact-scan не читает legacy QA filenames

Паттерн в `openclaw-artifact-scan.py`:
```python
re.match(r'\d{8}-\d{6}-(.+)\.md', filename)  # только YYYYMMDD-HHMMSS-ID
```

Файлы `2026-03-17-tech-151.md` не матчатся → статус `unknown`.

### Разрыв 4: topic_id NULL

В `db.py` `get_project_by_topic()` принимает только `topic_id`, без `chat_id`.
При нескольких форумах в разных чатах routing ломается.
Частично починено в 1b358e4 + admin_handler.py.

---

## Detailed Implementation Plan

### Data Flow Summary (for coder reference)

**Label format**: orchestrator.sh line 259 creates `task_label="${project_id}:${spec_id}"` (e.g., `dld:TECH-154`).
In pueue-callback.sh line 58: `TASK_LABEL="${LABEL#*:}"` extracts the part after colon, so `TASK_LABEL=TECH-154`.

**Two QA dispatch paths exist**:
1. **pueue-callback.sh line 360-366** (post-autopilot) — dispatches via `run-agent.sh` with free-text prompt. This is the BROKEN path.
2. **qa-loop.sh** (standalone, called by orchestrator) — takes `spec_id` as CLI arg, finds spec file, works correctly.

Path 1 is the one that runs after every autopilot completion. It passes `/qa Проверь изменения после ${TASK_LABEL}` to the QA agent. The agent receives this as natural language and must guess what to test. **Fix: pass clean SPEC_ID so the QA skill can find the spec file.**

---

### Task 1: Fix QA spec-id extraction in pueue-callback.sh

**Files:**
- Modify: `scripts/vps/pueue-callback.sh:340-366`

**Context:**
The callback dispatches QA after autopilot with a vague natural-language prompt.
TASK_LABEL already contains the spec ID (e.g., `TECH-154`) because orchestrator.sh
sets the label to `project_id:SPEC_ID`. We just need to pass it cleanly to the QA
skill instead of embedding it in a Russian sentence.

**Step 1: Write failing test**

No unit test possible for bash dispatch logic. Verification is manual:
```bash
# Before fix: grep the current QA dispatch line
grep -n 'Проверь изменения' scripts/vps/pueue-callback.sh
# Expected: line 362 contains "/qa Проверь изменения после ${TASK_LABEL}"
```

**Step 2: Modify pueue-callback.sh lines 340-366**

Replace the QA dispatch block. The key change: instead of
`"/qa Проверь изменения после ${TASK_LABEL}"`, send `"/qa ${TASK_LABEL}"`.

The TASK_LABEL already IS the spec ID (e.g., `TECH-154`) because:
- orchestrator.sh line 259: `task_label="${project_id}:${spec_id}"`
- pueue-callback.sh line 58: `TASK_LABEL="${LABEL#*:}"` strips project_id prefix

Current code at lines 340-366:
```bash
        QA_LABEL="${PROJECT_ID}:qa-${TASK_LABEL}"
        REFLECT_LABEL="${PROJECT_ID}:reflect-${TASK_LABEL}"

        # Dispatch QA once per autopilot completion
        if pueue status --json 2>/dev/null | python3 -c "
...
        else
            pueue add --group "$RUNNER_GROUP" --label "$QA_LABEL" \
                -- "${SCRIPT_DIR}/run-agent.sh" "$PROJECT_PATH" "$PROJECT_PROVIDER" "qa" \
                "/qa Проверь изменения после ${TASK_LABEL}" 2>/dev/null && {
```

Replace line 362 ONLY (the run-agent.sh invocation line). Change:
```bash
                "/qa Проверь изменения после ${TASK_LABEL}" 2>/dev/null && {
```
To:
```bash
                "/qa ${TASK_LABEL}" 2>/dev/null && {
```

This makes the QA agent receive `/qa TECH-154` which is exactly how qa-loop.sh
calls it (`-p "/qa ${SPEC_ID}"`  on qa-loop.sh line 65), and how the QA skill
expects its input.

**Step 3: Add debug log for spec-id tracing**

After line 339 (where RUNNER_GROUP is set), add a debug log:
```bash
    echo "[callback] Post-autopilot tail: TASK_LABEL=${TASK_LABEL} (used as QA spec_id)" >> "$CALLBACK_LOG"
```

**Step 4: Verify**

```bash
# After edit, verify the line change:
grep -n '/qa' scripts/vps/pueue-callback.sh
# Expected: line ~362 shows "/qa ${TASK_LABEL}" (no Russian text)

# Verify TASK_LABEL extraction still works:
LABEL="dld:TECH-154"
TASK_LABEL="${LABEL#*:}"
echo "$TASK_LABEL"
# Expected: TECH-154
```

**Acceptance Criteria:**
- [ ] Line 362 passes `/qa ${TASK_LABEL}` instead of Russian free-text
- [ ] Debug log added to callback-debug.log for traceability
- [ ] No other lines in the file are changed

---

### Task 2: Add reflect dispatch debug logging

**Files:**
- Modify: `scripts/vps/pueue-callback.sh:369-392`

**Context:**
Reflect dispatch was fixed in e7d619d (removed PENDING_COUNT gate). The current
code at lines 369-392 dispatches reflect unconditionally after autopilot completion
with a duplicate-check guard. This is correct. We add debug logging to confirm it
runs and to aid future debugging.

**Step 1: Verify current code is correct**

```bash
# Verify no PENDING_COUNT or "Skipping reflect" remains:
grep -n 'PENDING_COUNT\|Skipping reflect' scripts/vps/pueue-callback.sh
# Expected: no matches (removed in e7d619d)

# Verify reflect dispatch block exists:
grep -n 'Dispatch Reflect' scripts/vps/pueue-callback.sh
# Expected: line 369 comment "Dispatch Reflect after every autopilot completion"
```

**Step 2: Add debug log entry before reflect dispatch**

After line 369 (the comment line), before the duplicate-check `if` block on line 370,
insert:
```bash
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] reflect dispatch attempt: project=${PROJECT_ID} task=${TASK_LABEL}" >> "$CALLBACK_LOG"
```

**Step 3: Add debug log entry after successful reflect dispatch**

After line 388 (the echo line inside the success block), add:
```bash
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] reflect dispatched OK: project=${PROJECT_ID} task=${TASK_LABEL}" >> "$CALLBACK_LOG"
```

**Step 4: Verify**

```bash
grep -n 'reflect dispatch' scripts/vps/pueue-callback.sh
# Expected: 3 lines — the comment, the attempt log, and the OK log
```

**Acceptance Criteria:**
- [ ] No functional changes to reflect dispatch logic
- [ ] Two new debug log lines added to CALLBACK_LOG
- [ ] grep confirms no PENDING_COUNT or "Skipping reflect" remnants

---

### Task 3: Fix artifact-scan QA report parsing

**Files:**
- Modify: `scripts/vps/openclaw-artifact-scan.py:29-40,79`
- Create: `scripts/vps/tests/test_artifact_scan.py`

**Context:**
Two problems in openclaw-artifact-scan.py:
1. `extract_status()` only finds `**Status:**` header. Hand-written QA reports
   (like `2026-03-17-tech-151.md`) don't have this header — they use a Summary table.
2. Line 79 filters QA candidates by `p.name[:4].isdigit()` which works for both
   `20260317-...` and `2026-03-17-...`, but `extract_spec()` only finds `**Spec:**`
   header — hand-written reports use `# QA Report: TECH-151` instead.

**Step 1: Write failing test**

```python
# scripts/vps/tests/test_artifact_scan.py
"""Unit tests for openclaw-artifact-scan.py extract functions."""

import sys
from pathlib import Path

import pytest

VPS_DIR = str(Path(__file__).resolve().parent.parent)
if VPS_DIR not in sys.path:
    sys.path.insert(0, VPS_DIR)

# Module uses hyphens in name, import via importlib
import importlib
artifact_scan = importlib.import_module("openclaw-artifact-scan")


class TestExtractStatus:
    """Tests for extract_status()."""

    def test_standard_qa_loop_format(self):
        """qa-loop.sh writes **Status:** passed — should parse."""
        text = "# QA Report: TECH-153\n\n**Status:** passed\n**Project:** dld\n"
        assert artifact_scan.extract_status(text) == "passed"

    def test_standard_qa_loop_failed(self):
        """qa-loop.sh writes **Status:** failed — should parse."""
        text = "**Status:** failed\n**Spec:** BUG-123\n"
        assert artifact_scan.extract_status(text) == "failed"

    def test_hand_written_report_no_status_header(self):
        """Hand-written QA reports have Summary table, no **Status:** line.
        Should return 'no_status_header' instead of 'unknown'."""
        text = (
            "# QA Report: TECH-151 — Orchestrator North-Star Alignment\n\n"
            "**Date:** 2026-03-17\n"
            "**Environment:** VPS\n\n"
            "## Summary\n\n"
            "| Total | Pass | Fail | Blocked |\n"
            "|-------|------|------|--------|\n"
            "| 10    | 3    | 6    | 1       |\n"
        )
        assert artifact_scan.extract_status(text) == "no_status_header"

    def test_empty_text(self):
        """Empty text returns 'no_status_header'."""
        assert artifact_scan.extract_status("") == "no_status_header"


class TestExtractSpec:
    """Tests for extract_spec()."""

    def test_standard_spec_header(self):
        """qa-loop.sh writes **Spec:** TECH-153 — should parse."""
        text = "**Status:** passed\n**Spec:** TECH-153\n"
        assert artifact_scan.extract_spec(text) == "TECH-153"

    def test_hand_written_report_title_fallback(self):
        """Hand-written reports have spec ID in title: '# QA Report: TECH-151'."""
        text = (
            "# QA Report: TECH-151 — Orchestrator North-Star Alignment\n\n"
            "**Date:** 2026-03-17\n"
        )
        assert artifact_scan.extract_spec(text) == "TECH-151"

    def test_hand_written_lowercase_title(self):
        """Spec ID in title may be lowercase: '# QA Report: tech-153'."""
        text = "# QA Report: tech-153 AI-First Model\n"
        assert artifact_scan.extract_spec(text) == "TECH-153"

    def test_no_spec_anywhere(self):
        """No spec info at all returns empty string."""
        text = "# Some Report\n\nNo spec info here.\n"
        assert artifact_scan.extract_spec(text) == ""
```

**Step 2: Verify tests fail**

```bash
cd /tmp/wt-TECH-154
python -m pytest scripts/vps/tests/test_artifact_scan.py -v
```

Expected failures:
- `test_hand_written_report_no_status_header` — returns `"unknown"` not `"no_status_header"`
- `test_empty_text` — returns `"unknown"` not `"no_status_header"`
- `test_hand_written_report_title_fallback` — returns `""` not `"TECH-151"`
- `test_hand_written_lowercase_title` — returns `""` not `"TECH-153"`

**Step 3: Fix extract_status() — lines 29-33**

Replace the current `extract_status` function:
```python
def extract_status(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("**Status:**"):
            return line.split(":", 1)[1].strip()
    return "unknown"
```

With:
```python
def extract_status(text: str) -> str:
    """Extract status from QA report.

    Supports two formats:
    1. qa-loop.sh generated: '**Status:** passed' header line
    2. Hand-written/agent: no Status header (returns 'no_status_header')
    """
    for line in text.splitlines():
        if line.startswith("**Status:**"):
            val = line.split(":", 1)[1].strip().rstrip("*").strip()
            return val if val else "no_status_header"
    return "no_status_header"
```

**Step 4: Fix extract_spec() — lines 36-40**

Replace the current `extract_spec` function:
```python
def extract_spec(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("**Spec:**"):
            return line.split(":", 1)[1].strip()
    return ""
```

With:
```python
def extract_spec(text: str) -> str:
    """Extract spec ID from QA report.

    Supports two formats:
    1. qa-loop.sh generated: '**Spec:** TECH-153' header line
    2. Hand-written/agent: '# QA Report: TECH-151 — description' title
    """
    import re

    # Primary: explicit **Spec:** header
    for line in text.splitlines():
        if line.startswith("**Spec:**"):
            return line.split(":", 1)[1].strip()

    # Fallback: extract from title '# QA Report: SPEC-ID ...'
    for line in text.splitlines():
        m = re.match(r"^#\s+QA Report:\s*(\S+)", line)
        if m:
            spec_id = m.group(1).rstrip(" —-")
            # Normalize: tech-151 → TECH-151
            prefix_match = re.match(r"^(tech|ftr|bug|arch)(-\d+)$", spec_id, re.IGNORECASE)
            if prefix_match:
                spec_id = prefix_match.group(1).upper() + prefix_match.group(2)
            return spec_id

    return ""
```

**Step 5: Verify tests pass**

```bash
cd /tmp/wt-TECH-154
python -m pytest scripts/vps/tests/test_artifact_scan.py -v
```

Expected: all 8 tests pass.

**Acceptance Criteria:**
- [ ] `extract_status()` returns `"no_status_header"` for reports without `**Status:**` line
- [ ] `extract_spec()` falls back to title parsing: `# QA Report: TECH-151`
- [ ] `extract_spec()` normalizes lowercase `tech-151` to `TECH-151`
- [ ] All 8 new tests pass
- [ ] Existing qa_reports logic in `main()` unchanged (line 79 filter works for both formats)

---

### Task 4: Verify notify.py fail-closed behavior (Break 4)

**Files:**
- Read-only: `scripts/vps/notify.py:85-103`

**Context:**
Break 4 (topic_id NULL) was already fixed in commit 1b358e4. The current code
at notify.py lines 95-101 explicitly refuses to send when `topic_id` is missing
or equals 1 (General topic). Tests already exist in `test_notify.py`.

**Step 1: Verify existing guard is complete**

```bash
# Check the fail-closed guard exists:
grep -A5 'topic_id' scripts/vps/notify.py | head -10
# Expected: lines 95-101 show the guard

# Check existing tests cover this:
grep -c 'topic_id' scripts/vps/tests/test_notify.py
# Expected: >=3 (test_topic_id_1_refuses, test_missing_topic_id_refuses, test_uses_explicit)
```

**Step 2: Run existing tests to confirm**

```bash
cd /tmp/wt-TECH-154
python -m pytest scripts/vps/tests/test_notify.py -v
```

Expected: all 4 tests pass.

**Step 3: No code changes needed**

The guard at notify.py:95-101 is correct:
```python
topic_id = project.get("topic_id")
if not topic_id or topic_id == 1:
    print(f"[notify] Refusing to send for project '{project_id}': missing explicit topic_id binding", ...)
    return False
```

This is complete. Break 4 is CLOSED (fixed in 1b358e4, covered by tests).

**Acceptance Criteria:**
- [ ] Existing notify.py guard verified as correct
- [ ] Existing test_notify.py tests pass (3 topic routing tests)
- [ ] No code changes to notify.py needed

---

### Execution Order

```
Task 1 (callback QA fix) → Task 2 (reflect logging)
                          ↘ Task 3 (artifact-scan)  → (parallel with Task 2)
Task 4 (notify verify)   → (independent, any time)
```

Task 1 and Task 2 both modify `pueue-callback.sh` — execute them sequentially.
Task 3 is independent (different file). Task 4 is read-only verification.

### Dependencies

- Task 2 depends on Task 1 (both modify pueue-callback.sh, apply in order)
- Task 3 is independent (openclaw-artifact-scan.py)
- Task 4 is independent (read-only verification of notify.py)

---

## Drift Log

**Checked:** 2026-03-18 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/pueue-callback.sh` | Spec RCA incorrect: said label is `awardybot:autopilot-FTR-702` but actual format is `project_id:SPEC_ID` (no `autopilot-` prefix) | AUTO-FIX: updated plan to use correct label format |
| `scripts/vps/qa-loop.sh` | Already correctly handles spec lookup (line 38) | No action: qa-loop.sh is NOT broken, only callback dispatch path is |
| `scripts/vps/notify.py` | Break 4 already fully fixed in 1b358e4 with tests | AUTO-FIX: Task 4 changed from patch to read-only verification |
| `scripts/vps/openclaw-artifact-scan.py` | No `re.match` in file — spec RCA was wrong about regex pattern. Actual code uses `p.name[:4].isdigit()` filter | AUTO-FIX: updated Task 3 to fix actual functions (`extract_status`, `extract_spec`) |

### References Updated
- Task 1: `regex: autopilot-(.+)$` → TASK_LABEL is already the spec ID (no extraction needed)
- Task 1: `run-agent.sh` removed from Files (no changes needed there)
- Task 3: `re.match(r'\d{8}-\d{6}-(.+)\.md')` → actual problem is `extract_status()` and `extract_spec()`
- Task 4: changed from patch to read-only verification

---

## Acceptance Criteria

- [ ] `pueue-callback.sh` QA dispatch sends `/qa ${TASK_LABEL}` (clean spec ID, not Russian text)
- [ ] Reflect dispatch has debug logging in callback-debug.log
- [ ] `openclaw-artifact-scan.py` returns `"no_status_header"` for reports without `**Status:**` line
- [ ] `openclaw-artifact-scan.py` extracts spec ID from `# QA Report: TECH-151` title fallback
- [ ] `notify.py` fail-closed guard verified (existing tests pass)
- [ ] All 4 breaks documented as closed or won't-fix

---

## Links

- Предыдущая работа: `TECH-151` (north-star alignment, done)
- Commit `e7d619d` — reflect dispatch fix
- Commit `1b358e4` — topic-scoped routing
- Commit `5ece67d` — test layer cleanup
