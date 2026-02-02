# Tech: [TECH-055] Review Pipeline Hardening

**Status:** queued | **Priority:** P1 | **Date:** 2026-02-02

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

## Implementation Plan

### Task 1: Create task-loop.md

**Files:**
- Create: `.claude/skills/autopilot/task-loop.md`

**Steps:**
1. Create file with full decision tree for PHASE 2
2. Include explicit "approved → COMMIT → next task" flow
3. Include pre-review check step

**Acceptance:**
- [ ] Decision tree covers all statuses (approved, needs_*, FAIL)
- [ ] Explicit "→ COMMIT → NEXT TASK" after Code Quality approved

### Task 2: Update autopilot references

**Files:**
- Modify: `.claude/skills/autopilot/SKILL.md`
- Modify: `.claude/skills/autopilot/subagent-dispatch.md`

**Steps:**
1. Add reference to task-loop.md in SKILL.md modules table
2. Add "See task-loop.md for execution flow" in subagent-dispatch.md
3. Update Quick Reference to mention task-loop.md

**Acceptance:**
- [ ] SKILL.md references task-loop.md
- [ ] subagent-dispatch.md references task-loop.md

### Task 3: Create pre-review-check.py

**Files:**
- Create: `scripts/pre-review-check.py`

**Steps:**
1. Implement TODO/FIXME check (grep)
2. Implement bare exceptions check (grep)
3. Implement LOC limits check (wc -l)
4. Exit 0 on pass, exit 1 on fail with issues list

**Acceptance:**
- [ ] Script runs without errors
- [ ] Detects TODO/FIXME in .py files
- [ ] Detects bare exceptions
- [ ] Detects files > 400/600 LOC
- [ ] Returns proper exit codes

### Task 4: Enhance Spec Reviewer

**Files:**
- Modify: `.claude/agents/spec-reviewer.md`

**Steps:**
1. Add "Code Hygiene" section to checklist
2. Add TODO/FIXME check rule
3. Map to needs_implementation if found

**Acceptance:**
- [ ] Checklist includes TODO/FIXME check
- [ ] Clear action: needs_implementation

### Task 5: Enhance Code Quality Reviewer

**Files:**
- Modify: `.claude/agents/review.md`

**Steps:**
1. Add "Anti-Patterns" section referencing architecture.md
2. Add bare exceptions check
3. Map to needs_refactor if found

**Acceptance:**
- [ ] Checklist includes bare exceptions check
- [ ] Reference to architecture.md anti-patterns

### Task 6: Create escaped defects tracking

**Files:**
- Create: `ai/diary/escaped-defects.md`
- Modify: `.claude/agents/diary-recorder.md`

**Steps:**
1. Create template file with format
2. Add escaped_defect trigger to diary-recorder
3. Document when to use (bug found after merge)

**Acceptance:**
- [ ] Template file created
- [ ] Diary recorder handles escaped_defect type

### Execution Order

```
Task 1 (task-loop.md)
  → Task 2 (update references)
  → Task 3 (pre-review-check.py)
  → Task 4 (Spec Reviewer)
  → Task 5 (Code Quality)
  → Task 6 (escaped defects)
```

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
