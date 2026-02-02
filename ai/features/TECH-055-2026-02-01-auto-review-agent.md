# Tech: [TECH-055] Review Pipeline Hardening

**Status:** in_progress | **Priority:** P1 | **Date:** 2026-02-02

## Why

Autopilot иногда прерывается после того как Spec Reviewer или Code Quality говорит "approved". Нет явного decision tree что делать после review. Также отсутствуют детерминистичные pre-checks которые могли бы сэкономить токены на AI review.

## Context

**Текущий flow (нестабильный):**
```
Coder → Tester → Spec Reviewer → Code Quality → ???
                                              ↑
                          нет явной инструкции "→ COMMIT → next task"
```

**Целевой flow:**
```
Coder → Tester → PRE-CHECK (детерминистичный) → Spec Reviewer → Code Quality
                      ↓                                              ↓
                 FAIL = Coder                              approved → COMMIT → next task
                                                           needs_* → Coder → re-review
```

**Best practices (Scout research):**
- Microsoft/Graphite: layered approach (static + AI review)
- Static pre-checks экономят токены — FAIL до AI review
- Escaped defects tracking — учиться на пропущенных багах

---

## Scope

**In scope:**
1. **BUG FIX:** Task Loop с явным decision tree после каждого шага
2. **Pre-review check:** Детерминистичный скрипт `scripts/pre-review-check.py`
3. **Review усиление:** Добавить TODO/FIXME check в Spec Reviewer
4. **Escaped defects:** Tracking что прошло review но стало багом

**Out of scope:**
- Новый auto-reviewer агент (используем существующие)
- Domain-specific checks (float for money и т.п.)
- Evaluation harness (отдельная задача)

---

## Allowed Files

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `.claude/skills/autopilot/task-loop.md` | create | Явный decision tree после каждого шага |
| 2 | `.claude/skills/autopilot/SKILL.md` | modify | Ссылка на task-loop.md |
| 3 | `.claude/skills/autopilot/subagent-dispatch.md` | modify | Ссылка на task-loop.md |
| 4 | `.claude/agents/spec-reviewer.md` | modify | Добавить TODO/FIXME check |
| 5 | `.claude/agents/review.md` | modify | Добавить bare exceptions check |
| 6 | `scripts/pre-review-check.py` | create | Детерминистичные проверки |
| 7 | `ai/diary/escaped-defects.md` | create | Template для tracking |
| 8 | `.claude/agents/diary-recorder.md` | modify | Добавить escaped_defect type |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1 | `.claude/skills/autopilot/task-loop.md` | Decision trees |
| 2 | `scripts/pre-review-check.py` | Deterministic checks |
| 3 | `ai/diary/escaped-defects.md` | Defects log template |

---

## Approaches

### Approach 1: Inline в subagent-dispatch.md

**Summary:** Добавить decision trees прямо в subagent-dispatch.md

**Pros:**
- Меньше файлов
- Всё в одном месте

**Cons:**
- Файл станет слишком большим
- Смешивает dispatch и flow logic

### Approach 2: Отдельный task-loop.md (SELECTED)

**Source:** DLD modular architecture pattern

**Summary:** Создать отдельный файл с явным task loop и decision trees

**Pros:**
- Модульность (как worktree-setup.md, finishing.md)
- Легко найти и отладить
- SSOT для flow logic

**Cons:**
- Ещё один файл

### Selected: Approach 2

**Rationale:** Следует существующему паттерну модульности в autopilot (worktree-setup.md, finishing.md, escalation.md).

---

## Design

### 1. Task Loop (task-loop.md)

```markdown
# Task Loop — PHASE 2 Execution

For EACH task from Implementation Plan:

## Step 1: CODER
[dispatch coder] → files_changed

## Step 2: TESTER
[dispatch tester] → passed?
├─ YES → Step 3
├─ FAIL in scope → [Debugger loop, max 3] → re-test
└─ FAIL out of scope → SKIP, log → Step 3

## Step 3: PRE-REVIEW CHECK (NEW!)
```bash
python scripts/pre-review-check.py {files_changed}
```
├─ PASS (exit 0) → Step 4
└─ FAIL (exit 1) → Back to CODER with issues list

## Step 4: SPEC REVIEWER
[dispatch spec-reviewer] → status?
├─ approved → Step 5
├─ needs_implementation → CODER adds → re-review (Step 4)
└─ needs_removal → CODER removes → re-review (Step 4)

## Step 5: CODE QUALITY
[dispatch review] → status?
├─ approved → Step 6  ← CRITICAL: explicit next step!
├─ needs_refactor → CODER fixes → re-review (max 2, then Council)
└─ needs_discussion → STOP, ask human

## Step 6: COMMIT
```bash
git add {files_changed}
git commit -m "{type}({scope}): {description}"
```
Log to Autopilot Log → NEXT TASK

## After ALL tasks → PHASE 3 (finishing.md)
```

### 2. Pre-Review Check Script

```python
#!/usr/bin/env python3
"""
Deterministic pre-review checks. Run BEFORE AI review to save tokens.
Exit 0 = PASS, Exit 1 = FAIL with issues list.
"""

Checks:
1. TODO/FIXME — grep "# TODO|# FIXME" in changed .py files
2. Bare exceptions — grep "except:|except Exception:"
3. LOC limits — wc -l > 400 (code) / 600 (tests)

Output format:
  PASS: "PRE-REVIEW PASSED"
  FAIL: "PRE-REVIEW FAILED:\n  - file.py:42: # TODO: fix this\n  - ..."
```

### 3. Spec Reviewer Enhancement

Add to checklist:
```markdown
### Code Hygiene (NEW)
- [ ] No `# TODO` or `# FIXME` in new code
- [ ] If found → needs_implementation (clean up before commit)
```

### 4. Code Quality Enhancement

Add to checklist:
```markdown
### Anti-Patterns (from architecture.md)
- [ ] No bare `except:` or `except Exception:` without re-raise
- [ ] If found → needs_refactor
```

### 5. Escaped Defects Tracking

Template `ai/diary/escaped-defects.md`:
```markdown
# Escaped Defects Log

Defects that passed review but were found after merge.
Used by /reflect to improve review checklists.

---

## Template

### YYYY-MM-DD: BUG-XXX (escaped from TASK-YYY)

**Found by:** manual testing | user report | CI | monitoring
**Symptom:** [what happened]
**Root cause:** [why it happened]
**Why review missed it:** [what check was missing]
**Action taken:**
- [ ] Added check to pre-review-check.py
- [ ] Added to Code Quality checklist
- [ ] Added to Spec Reviewer checklist
- [ ] Other: ___
```

Diary Recorder gets new trigger:
```yaml
problem_type: escaped_defect
# When: bug found after merge that should have been caught by review
```

---

## Detailed Implementation Plan

### Task 1: Create task-loop.md

**Files:**
- Create: `.claude/skills/autopilot/task-loop.md`

**Context:**
The current autopilot SKILL.md and subagent-dispatch.md lack explicit decision trees for what happens after each review step. This causes autopilot to stop after "approved" instead of proceeding to commit. This file creates the SSOT for PHASE 2 task execution flow.

**Step 1: Create the task-loop.md file**

```markdown
# Task Loop — PHASE 2 Execution

SSOT for task execution flow. For EACH task from Implementation Plan.

## Flow Overview

```
CODER → TESTER → PRE-CHECK → SPEC REVIEWER → CODE QUALITY → COMMIT → NEXT
```

---

## Step 1: CODER

```yaml
Task tool:
  subagent_type: "coder"
  prompt: |
    task: "Task {N}/{M} — {title}"
    ...
```

**Output:** `files_changed: [list of modified files]`

**Next:** Step 2 (TESTER)

---

## Step 2: TESTER

```yaml
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {description}"
```

**Decision Tree:**
```
TESTER result?
├─ PASSED → Step 3 (PRE-CHECK)
├─ FAILED (in-scope)
│   └─ debug_attempts < 3?
│       ├─ YES → [Debugger] → [Coder fix] → re-test (Step 2)
│       └─ NO → ESCALATE (see escalation.md)
└─ FAILED (out-of-scope)
    └─ Log "out-of-scope failure: {test}" → Step 3 (PRE-CHECK)
```

**In-scope:** Test file path contains any of `files_changed` directories.

---

## Step 3: PRE-REVIEW CHECK

Deterministic checks BEFORE AI review (saves tokens on obvious issues).

```bash
python scripts/pre-review-check.py {files_changed}
```

**Decision Tree:**
```
Exit code?
├─ 0 (PASS) → Step 4 (SPEC REVIEWER)
└─ 1 (FAIL) → Back to CODER with issues list
    └─ CODER fixes issues → re-run PRE-CHECK (Step 3)
```

**What PRE-CHECK catches:**
- `# TODO` or `# FIXME` in code
- Bare `except:` or `except Exception:` without re-raise
- Files > 400 LOC (code) or > 600 LOC (tests)

---

## Step 4: SPEC REVIEWER

```yaml
Task tool:
  subagent_type: "spec-reviewer"
  prompt: |
    feature_spec: "ai/features/{TASK_ID}*.md"
    task: "Task {N}/{M} — {title}"
    files_changed: [...]
```

**Decision Tree:**
```
Spec Reviewer status?
├─ approved → Step 5 (CODE QUALITY)
├─ needs_implementation
│   └─ CODER adds missing → re-review (Step 4)
│   └─ spec_review_loop < 2? YES: retry | NO: ESCALATE
└─ needs_removal
    └─ CODER removes extras → re-review (Step 4)
    └─ spec_review_loop < 2? YES: retry | NO: ESCALATE
```

---

## Step 5: CODE QUALITY

```yaml
Task tool:
  subagent_type: "review"
  prompt: |
    TASK: {description}
    FILES CHANGED: {list}
```

**Decision Tree:**
```
Code Quality status?
├─ approved → Step 6 (COMMIT)  ← CRITICAL!
├─ needs_refactor
│   └─ refactor_loop < 2?
│       ├─ YES → CODER fixes → re-test (Step 2) → re-review (Step 5)
│       └─ NO → ESCALATE to Council
└─ needs_discussion
    └─ STOP → Ask human (status: blocked)
```

**CRITICAL:** `approved` means proceed to COMMIT. Do NOT stop here!

---

## Step 6: COMMIT

**All reviews passed. Commit the changes.**

```bash
git add {files_changed}
git commit -m "{type}({scope}): {description}"
```

**Commit message format:**
- `feat(autopilot): add task-loop decision trees`
- `fix(review): add TODO/FIXME check`
- `docs(diary): create escaped-defects template`

**After commit:**
1. Log to Autopilot Log in spec file
2. Increment task counter: `current_task += 1`
3. Continue to NEXT TASK (back to Step 1)

---

## After ALL Tasks

When `current_task > total_tasks`:

```
→ PHASE 3 (finishing.md)
```

---

## Loop Counters

| Counter | Limit | On Limit |
|---------|-------|----------|
| `debug_attempts` | 3 | Escalate (escalation.md) |
| `spec_review_loop` | 2 | Escalate to Council |
| `refactor_loop` | 2 | Escalate to Council |

Reset counters at start of each task.

---

## Quick Reference

```
Task N:
  CODER → files
  TESTER → pass?
    └─ fail in-scope? debug (max 3)
    └─ fail out-scope? skip, continue
  PRE-CHECK → pass?
    └─ fail? coder fix, retry
  SPEC REVIEWER → approved?
    └─ needs_*? coder fix, retry (max 2)
  CODE QUALITY → approved?
    └─ needs_refactor? coder fix, retry (max 2)
  COMMIT → log → NEXT TASK
```
```

**Step 2: Verify file was created correctly**

```bash
cat .claude/skills/autopilot/task-loop.md | head -20
```

Expected: File exists with "# Task Loop" header.

**Acceptance Criteria:**
- [ ] Decision tree covers all statuses (approved, needs_implementation, needs_removal, needs_refactor, needs_discussion)
- [ ] Explicit "approved -> Step 6 (COMMIT)" after Code Quality
- [ ] Loop counters documented (debug_attempts, spec_review_loop, refactor_loop)
- [ ] PRE-CHECK step included between TESTER and SPEC REVIEWER
- [ ] Quick Reference section for easy lookup

---

### Task 2: Update autopilot references

**Files:**
- Modify: `.claude/skills/autopilot/SKILL.md` (lines 44-51)
- Modify: `.claude/skills/autopilot/subagent-dispatch.md` (add reference)

**Context:**
SKILL.md has a Modules table that lists all autopilot modules. Need to add task-loop.md. Also need to add reference in subagent-dispatch.md so users know where to find the execution flow.

**Step 1: Add task-loop.md to SKILL.md Modules table**

In `.claude/skills/autopilot/SKILL.md`, find the Modules table (around line 44) and add task-loop.md:

```markdown
## Modules

| Module | Content |
|--------|---------|
| `worktree-setup.md` | Git worktree creation, env setup, cleanup |
| `subagent-dispatch.md` | Subagent types, dispatch templates, model routing |
| `task-loop.md` | PHASE 2 execution flow, decision trees after each step |
| `finishing.md` | Pre-done checklist, status sync, merge flow |
| `escalation.md` | Limits, debug/refactor loops, Spark/Council |
| `safety-rules.md` | Forbidden actions, file/test/git safety |
```

**Step 2: Update Quick Reference in SKILL.md**

Find "Quick Reference" section (around line 16) and update PHASE 2 to reference task-loop.md:

```markdown
## Quick Reference

```
PHASE 0: Worktree Setup        → worktree-setup.md
  └─ CI check → worktree → env copy → baseline

PHASE 1: Plan (ALWAYS)         → subagent-dispatch.md
  └─ [Plan Agent] opus → validates spec + creates/updates tasks

PHASE 2: Execute (per task)    → task-loop.md
  └─ [Coder] sonnet → files
  └─ [Tester] sonnet → pass?
      └─ fail? → [Debugger] opus (max 3) → escalation.md
  └─ PRE-CHECK (deterministic)
  └─ [Spec Reviewer] sonnet → approved?
  └─ [Code Quality] opus → approved?
  └─ COMMIT (no push)

PHASE 3: Finish                → finishing.md
  └─ Final test → Exa verification → status done → merge develop → cleanup
```
```

**Step 3: Add reference in subagent-dispatch.md**

Add at the top of subagent-dispatch.md, after the title:

```markdown
# Subagent Dispatch

How to spawn and manage subagents in autopilot workflow.

**Execution Flow:** See `task-loop.md` for decision trees after each subagent.
```

**Step 4: Verify changes**

```bash
grep -n "task-loop" .claude/skills/autopilot/SKILL.md
grep -n "task-loop" .claude/skills/autopilot/subagent-dispatch.md
```

Expected: Both files contain references to task-loop.md.

**Acceptance Criteria:**
- [ ] SKILL.md Modules table includes task-loop.md with description
- [ ] SKILL.md Quick Reference shows task-loop.md for PHASE 2
- [ ] subagent-dispatch.md has reference to task-loop.md at top

---

### Task 3: Create pre-review-check.py

**Files:**
- Create: `scripts/pre-review-check.py`

**Context:**
Deterministic pre-review checks run BEFORE AI review to save tokens. If basic issues (TODO/FIXME, bare exceptions, LOC limits) are found, fail immediately without calling AI reviewers. This is the "layered approach" (static + AI) best practice.

**Step 1: Create scripts directory if needed**

```bash
mkdir -p scripts
```

**Step 2: Create pre-review-check.py**

```python
#!/usr/bin/env python3
"""
Deterministic pre-review checks.

Run BEFORE AI review to save tokens on obvious issues.
Exit 0 = PASS, Exit 1 = FAIL with issues list.

Usage:
    python scripts/pre-review-check.py file1.py file2.py ...
    python scripts/pre-review-check.py  # reads from stdin (newline-separated)
"""

import re
import sys
from pathlib import Path
from typing import NamedTuple


class Issue(NamedTuple):
    """A detected issue."""

    file: str
    line: int
    check: str
    message: str


def check_todo_fixme(file_path: Path) -> list[Issue]:
    """Check for TODO/FIXME comments in Python files."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    pattern = re.compile(r"#\s*(TODO|FIXME)[\s:](.*)", re.IGNORECASE)
    for line_num, line in enumerate(content.splitlines(), start=1):
        match = pattern.search(line)
        if match:
            tag, text = match.groups()
            issues.append(
                Issue(
                    file=str(file_path),
                    line=line_num,
                    check="TODO/FIXME",
                    message=f"# {tag.upper()}: {text.strip()[:50]}",
                )
            )
    return issues


def check_bare_exceptions(file_path: Path) -> list[Issue]:
    """Check for bare except: or except Exception: without re-raise."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    lines = content.splitlines()
    # Pattern: except: or except Exception: (without specific exception type)
    bare_except_pattern = re.compile(r"^\s*except\s*:\s*(#.*)?$")
    generic_except_pattern = re.compile(r"^\s*except\s+Exception\s*:\s*(#.*)?$")

    for line_num, line in enumerate(lines, start=1):
        if bare_except_pattern.match(line):
            # Check if next non-empty line has 'raise'
            has_reraise = _check_reraise(lines, line_num)
            if not has_reraise:
                issues.append(
                    Issue(
                        file=str(file_path),
                        line=line_num,
                        check="BARE_EXCEPT",
                        message="Bare `except:` without re-raise",
                    )
                )
        elif generic_except_pattern.match(line):
            has_reraise = _check_reraise(lines, line_num)
            if not has_reraise:
                issues.append(
                    Issue(
                        file=str(file_path),
                        line=line_num,
                        check="BARE_EXCEPT",
                        message="`except Exception:` without re-raise",
                    )
                )
    return issues


def _check_reraise(lines: list[str], except_line: int) -> bool:
    """Check if except block contains a raise statement."""
    # Look at next 5 lines for a raise statement
    for i in range(except_line, min(except_line + 5, len(lines))):
        line = lines[i].strip()
        if line.startswith("raise"):
            return True
        # If we hit another except/else/finally/def/class, stop looking
        if re.match(r"^(except|else|finally|def |class |@)", line):
            break
    return False


def check_loc_limits(file_path: Path) -> list[Issue]:
    """Check file line count against limits (400 code, 600 tests)."""
    issues: list[Issue] = []
    if not file_path.suffix == ".py":
        return issues

    try:
        content = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return issues

    line_count = len(content.splitlines())
    is_test = "test" in file_path.name.lower() or "/tests/" in str(file_path)
    limit = 600 if is_test else 400

    if line_count > limit:
        issues.append(
            Issue(
                file=str(file_path),
                line=line_count,
                check="LOC_LIMIT",
                message=f"{line_count} lines (max {limit})",
            )
        )
    return issues


def main() -> int:
    """Run all checks on provided files."""
    # Get files from args or stdin
    if len(sys.argv) > 1:
        files = [Path(f) for f in sys.argv[1:]]
    else:
        # Read from stdin (newline-separated)
        files = [Path(line.strip()) for line in sys.stdin if line.strip()]

    if not files:
        print("PRE-REVIEW PASSED (no files to check)")
        return 0

    all_issues: list[Issue] = []

    for file_path in files:
        if not file_path.exists():
            continue
        all_issues.extend(check_todo_fixme(file_path))
        all_issues.extend(check_bare_exceptions(file_path))
        all_issues.extend(check_loc_limits(file_path))

    if not all_issues:
        print("PRE-REVIEW PASSED")
        return 0

    print("PRE-REVIEW FAILED:")
    for issue in all_issues:
        print(f"  - {issue.file}:{issue.line}: [{issue.check}] {issue.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Make script executable**

```bash
chmod +x scripts/pre-review-check.py
```

**Step 4: Verify script works**

```bash
# Test with a file that has TODO
echo '# TODO: fix this' > /tmp/test_todo.py
python scripts/pre-review-check.py /tmp/test_todo.py
echo "Exit code: $?"
# Expected: Exit code: 1

# Test with clean file
echo 'print("hello")' > /tmp/test_clean.py
python scripts/pre-review-check.py /tmp/test_clean.py
echo "Exit code: $?"
# Expected: Exit code: 0

rm /tmp/test_todo.py /tmp/test_clean.py
```

**Acceptance Criteria:**
- [ ] Script runs without syntax errors
- [ ] Detects `# TODO` and `# FIXME` in .py files
- [ ] Detects bare `except:` without re-raise
- [ ] Detects `except Exception:` without re-raise
- [ ] Detects files > 400 LOC (code) or > 600 LOC (tests)
- [ ] Exit 0 on pass, exit 1 on fail
- [ ] Output format: "PRE-REVIEW FAILED:\n  - file:line: [CHECK] message"

---

### Task 4: Enhance Spec Reviewer

**Files:**
- Modify: `.claude/agents/spec-reviewer.md` (add Code Hygiene section after Scope Compliance, around line 73)

**Context:**
Spec Reviewer currently checks missing requirements and extra features. Adding TODO/FIXME check ensures no unfinished code gets committed. This is a backup for pre-review-check.py in case the script is bypassed.

**Step 1: Add Code Hygiene section**

In `.claude/agents/spec-reviewer.md`, find the "### Scope Compliance" section (around line 69) and add after it:

```markdown
### Scope Compliance

- [ ] Only files from `## Allowed Files` modified
- [ ] No out-of-scope changes

### Code Hygiene (NEW)

Check for unfinished code markers:

- [ ] No `# TODO` comments in new/modified code
- [ ] No `# FIXME` comments in new/modified code

**If found:**
```yaml
status: needs_implementation
missing_requirements:
  - requirement: "Remove TODO/FIXME before commit"
    spec_location: "Code Hygiene check"
    action: "Complete or remove: {file}:{line} — {comment}"
```

**Why:** TODO/FIXME indicates unfinished work. Complete the work or remove the comment with a tracking issue.
```

**Step 2: Verify changes**

```bash
grep -n "Code Hygiene" .claude/agents/spec-reviewer.md
grep -n "TODO" .claude/agents/spec-reviewer.md
```

Expected: "Code Hygiene" section exists with TODO/FIXME check.

**Acceptance Criteria:**
- [ ] "Code Hygiene" section added after "Scope Compliance"
- [ ] TODO check documented with clear action (needs_implementation)
- [ ] FIXME check documented with clear action (needs_implementation)
- [ ] Example output format provided

---

### Task 5: Enhance Code Quality Reviewer

**Files:**
- Modify: `.claude/agents/review.md` (add Anti-Patterns section, around line 87)

**Context:**
Code Quality reviewer checks architecture and duplication. Adding explicit bare exceptions check ensures this anti-pattern (from architecture.md) is caught. This is a backup for pre-review-check.py.

**Step 1: Add Anti-Patterns section**

In `.claude/agents/review.md`, find "### 3. Simplicity" section (around line 85) and add after it:

```markdown
### 3. Simplicity
**Red flags:**
- Class when function suffices
- New module for 20 lines

### 3.5. Anti-Patterns (from architecture.md)

Reference: `.claude/rules/architecture.md#anti-patterns-forbidden`

**Check for bare exceptions:**
```bash
grep -n "except:" {changed_py_files}
grep -n "except Exception:" {changed_py_files}
```

**Red flags:**
- [ ] `except:` without re-raise (swallows all errors)
- [ ] `except Exception:` without re-raise or specific handling

**If found:**
```yaml
status: needs_refactor
architecture_issues:
  - file: {file}:{line}
    issue: "Bare exception swallows errors"
    action: "Use specific exception type or add re-raise"
```

**Acceptable patterns:**
```python
# OK: re-raises
except Exception:
    logger.error("Failed")
    raise

# OK: specific exception
except ValueError as e:
    return Err(ValidationError(str(e)))

# NOT OK: swallows everything
except:
    pass
```
```

**Step 2: Verify changes**

```bash
grep -n "Anti-Patterns" .claude/agents/review.md
grep -n "bare exception" .claude/agents/review.md
```

Expected: "Anti-Patterns" section exists with bare exceptions check.

**Acceptance Criteria:**
- [ ] "Anti-Patterns" section added with reference to architecture.md
- [ ] Bare `except:` check documented with needs_refactor action
- [ ] Bare `except Exception:` check documented
- [ ] Acceptable patterns shown (re-raise, specific exception)

---

### Task 6: Create escaped defects tracking

**Files:**
- Create: `ai/diary/escaped-defects.md`
- Modify: `.claude/agents/diary-recorder.md` (add escaped_defect trigger, around line 17)

**Context:**
Escaped defects are bugs that passed review but were found after merge. Tracking them helps improve review checklists over time. This is the feedback loop for continuous improvement.

**Step 1: Create ai/diary directory if needed**

```bash
mkdir -p ai/diary
```

**Step 2: Create escaped-defects.md template**

```markdown
# Escaped Defects Log

Defects that passed code review but were found after merge to develop/main.

**Purpose:** Learn from review gaps to improve checklists and pre-review-check.py.

**Used by:** `/reflect` to analyze patterns and suggest new checks.

---

## How to Log

When a bug is found that should have been caught by review:

1. Create entry below using template
2. Run diary-recorder with `problem_type: escaped_defect`
3. After analysis, add check to prevent recurrence

---

## Template

### YYYY-MM-DD: BUG-XXX (escaped from TASK-YYY)

**Found by:** manual testing | user report | CI | monitoring | /audit

**Symptom:**
[What happened? Error message, unexpected behavior, etc.]

**Root cause:**
[Why it happened? Code issue, logic error, missing check, etc.]

**Why review missed it:**
[What check was missing? What should reviewer have caught?]

**Action taken:**
- [ ] Added check to `scripts/pre-review-check.py`
- [ ] Added to Code Quality checklist (`.claude/agents/review.md`)
- [ ] Added to Spec Reviewer checklist (`.claude/agents/spec-reviewer.md`)
- [ ] Added to architecture.md anti-patterns
- [ ] Other: ___

**Prevention check:**
```bash
# Command to detect this issue in future
grep -n "pattern" {files}
```

---

## Log

*(Entries below, newest first)*
```

**Step 3: Add escaped_defect trigger to diary-recorder.md**

In `.claude/agents/diary-recorder.md`, find the "## When Called" section (around line 10) and update:

```markdown
## When Called

Autopilot detects:

**Problems:**
- `bash_instead_of_tools` — Bash used where Edit/Write should be
- `test_retry > 1` — Test failed and required debug loop
- `escaped_defect` — Bug found after merge that review should have caught

**Successes:**
- `first_pass_success` — Coder + Tester passed on first attempt (no debug loop)
- `research_useful` — Coder used Exa research source in code
- `pattern_reused` — Planner found relevant diary entry and applied it
```

**Step 4: Add escaped_defect to Input schema**

In `.claude/agents/diary-recorder.md`, find the "## Input" section (around line 25) and update:

```markdown
## Input

```yaml
task_id: "FTR-XXX" | "BUG-XXX" | "TECH-XXX"
problem_type: bash_instead_of_tools | test_retry | escalation_used | escaped_defect | first_pass_success | research_useful | pattern_reused
error_message: "..."           # for problems
success_detail: "..."          # for successes (pattern, source, reuse hint)
escaped_from: "TASK-YYY"       # for escaped_defect: which task introduced bug
found_by: "manual | user | CI" # for escaped_defect: how bug was discovered
files_changed: [...]
attempts: "what was tried"     # for problems
```
```

**Step 5: Add escaped_defect entry template**

In `.claude/agents/diary-recorder.md`, find "### Diary Entry (minimal)" (around line 43) and add after it:

```markdown
### Escaped Defect Entry

```markdown
# Session: {task_id} — {date}

## Escaped Defect

**Escaped from:** {escaped_from}
**Found by:** {found_by}

## Details
- Error: {error_message}
- Files: {files_changed}

## TODO for review improvement
- Analyze why review missed this
- Add check to prevent recurrence
- Update ai/diary/escaped-defects.md
```
```

**Step 6: Verify changes**

```bash
cat ai/diary/escaped-defects.md | head -10
grep -n "escaped_defect" .claude/agents/diary-recorder.md
```

Expected: Template file exists, diary-recorder has escaped_defect in triggers and input.

**Acceptance Criteria:**
- [ ] `ai/diary/escaped-defects.md` created with template
- [ ] Template has all fields (Found by, Symptom, Root cause, Why missed, Action taken)
- [ ] diary-recorder.md has `escaped_defect` in "When Called" section
- [ ] diary-recorder.md has `escaped_from` and `found_by` in Input schema
- [ ] diary-recorder.md has Escaped Defect entry template

---

### Execution Order

```
Task 1 (task-loop.md) — creates SSOT for execution flow
    ↓
Task 2 (update references) — links SKILL.md and subagent-dispatch.md to task-loop.md
    ↓
Task 3 (pre-review-check.py) — creates deterministic checker
    ↓
Task 4 (Spec Reviewer) — adds TODO/FIXME check as backup
    ↓
Task 5 (Code Quality) — adds bare exceptions check as backup
    ↓
Task 6 (escaped defects) — creates tracking system

Tasks 4-6 can run in parallel after Task 3.
```

### Dependencies

- Task 2 depends on Task 1 (needs task-loop.md to exist)
- Tasks 3-6 are independent of each other
- Task 3 should complete before Tasks 4-5 (they reference pre-review-check.py)

### Research Sources

- [Pre-commit hooks for TODO/FIXME detection](https://gist.github.com/coryodaniel/6575466155b1b8e505ecc047fe5c4bcd) — grep pattern approach
- [SonarQube deterministic approach](https://www.linkedin.com/posts/akshay-pachaar_every-ai-coding-assistant-has-the-same-problem-activity-7405152774629425152-xtPn) — static analysis before AI review
- [AI Code Review Guide 2025](https://www.digitalapplied.com/blog/ai-code-review-automation-guide-2025) — layered review architecture
- [Pre-commit hooks ultimate guide](https://gatlenculp.medium.com/effortless-code-quality-the-ultimate-pre-commit-hooks-guide-for-2025-57ca501d9835) — comprehensive hook patterns

---

## Definition of Done

### Functional
- [ ] Autopilot no longer stops after "approved" — continues to commit
- [ ] Pre-review check runs before AI review
- [ ] Pre-review FAIL returns to Coder without AI review (token savings)
- [ ] TODO/FIXME caught by Spec Reviewer
- [ ] Bare exceptions caught by Code Quality

### Technical
- [ ] task-loop.md has explicit decision trees
- [ ] pre-review-check.py passes lint
- [ ] No circular references in autopilot modules

### Documentation
- [ ] task-loop.md documented in SKILL.md
- [ ] escaped-defects.md has clear template

---

## Autopilot Log

*(Filled by Autopilot during execution)*
