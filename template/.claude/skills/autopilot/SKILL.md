---
name: autopilot
description: Autonomous task execution with subagents (coder, tester, debugger, reviewer)
model: opus
---

# Autopilot v3.0 — Fresh Subagents + Worktree Always

Autonomous execution: Plan → Fresh subagent per task → commit → next.

**Activation:**
- `autopilot` — creates worktree, plans, executes (default)
- `autopilot --no-worktree` — skip worktree (for tiny fixes only)

## TL;DR — Quick Reference

```
PHASE 0: Worktree Setup
  └─ CI check → save MAIN_REPO → worktree → env copy → baseline

PHASE 1: Plan
  └─ [Plan Agent] opus → tasks in spec

PHASE 2: Execute (per task)
  └─ [Coder] sonnet → files
  └─ [Tester] sonnet → pass?
      └─ fail? → [Debugger] opus (max 3)
  └─ DOCUMENTER (inline)
  └─ [Spec Reviewer] sonnet → approved?
  └─ [Code Quality] opus → approved?
  └─ COMMIT (no push)

PHASE 3: Finish
  └─ Final test → status done → push feature (3a) → merge+push develop (3b) → cleanup
```

**Limits:** Debug 3, Refactor 2, ./test fast 5, ./test llm 2
**Escalate:** Bug → Spark (BUG spec) | Architecture → Council | Unclear → Human

---

## Architecture Reference

**SSOT:**
- Agent roles & model routing: `docs/foundation/02-agent-roles.md`
- Creating new skills/agents: `/scaffold` skill

---

## Architecture

```
PHASE 0: WORKTREE SETUP (ALWAYS by default!)
  0. ./scripts/ci-status.sh (exit 0=continue, exit 2=DEPLOY ERROR PROTOCOL)
  1. git worktree add ".worktrees/{ID}" -b "{type}/{ID}"
  2. cd to worktree
  3. Environment setup (spec-driven: python + docker/database if needed)
  4. ./test fast (baseline must pass)

PHASE 1: PLAN (if no detailed plan exists)
  [Plan Subagent] → deep analysis → detailed tasks
  Output: "## Detailed Implementation Plan" in spec

PHASE 2: FOR EACH TASK (fresh subagent per task!):
  [Fresh CODER Subagent] → code → files_changed
  [Fresh TESTER Subagent] → Smart Testing
  [DEPLOY CHECK] → migrations? edge functions?
  [DOCUMENTER]
  [TWO-STAGE REVIEW]:
    Stage 1: SPEC REVIEWER — matches spec?
    Stage 2: CODE QUALITY REVIEWER — architecture ok?
  COMMIT to {type}/{ID} branch (NO PUSH yet!)

  (subagent contexts die after each task → main context stays clean)

PHASE 3: FINISHING (SINGLE PUSH!)
  1. ./test fast (final verification)
  2. Pre-Done Checklist
  3. Status → done + commit
  4. Push feature branch (backup)
  5. Merge → develop + SINGLE push
  6. Cleanup worktree + delete branch

DEBUG LOOP (if TESTER fails, max 3):
  - In-scope? → DEBUGGER → CODER fix → TESTER
  - Out-of-scope? → Log + Skip
  - After 3 → ESCALATE (see Escalation Types below)

REFACTOR LOOP (if CODE QUALITY REVIEWER needs_refactor, max 2):
  CODER fix → TESTER → DOCUMENTER → CODE QUALITY REVIEWER
  After 2 → ESCALATE (see Escalation Types below)

ESCALATION TYPES:
  | Type | Trigger | Target | Action |
  |------|---------|--------|--------|
  | bug_unresolved | Debug 3x, code bug | Spark | Create BUG-XXX spec |
  | decision_needed | Architecture unclear | Council | Expert review |
  | human_required | Blocked, unclear | STOP | Ask user |
```

## Plan vs Workflow Separation (CRITICAL)

**План определяет ЧТО:**
- Какой код писать
- Какие файлы создавать/изменять
- Acceptance criteria для каждой задачи

**Autopilot определяет КАК:**
- Фиксированный workflow для КАЖДОЙ задачи
- Gates и checkpoints
- Review процесс

### ⛔ BLOCKING RULE

```
План НЕ определяет workflow!

Даже если план содержит:
  "Task 1: Create file → Task 2: Commit"

Autopilot ОБЯЗАН выполнить:
  CODER (Task 1) → TESTER → DOCUMENTER → REVIEWER → COMMIT

Пропуск любого шага = VIOLATION
```

### Task Execution Template

Для КАЖДОЙ задачи из плана:

```
┌─────────────────────────────────────────────────────┐
│ 1. CODER                                            │
│    Input: Task description from plan                │
│    Output: files_changed: [...]                     │
├─────────────────────────────────────────────────────┤
│ 2. MIGRATION VALIDATION (if migrations/*.sql)       │
│    VALIDATE ONLY — NO APPLY!                        │
│    → squawk lint (local)                            │
│    → dry-run (optional)                             │
│    CI will apply after push!                        │
├─────────────────────────────────────────────────────┤
│ 3. TESTER                                           │
│    Run: Smart Testing based on files_changed        │
│    Gate: All in-scope tests pass                    │
├─────────────────────────────────────────────────────┤
│ 4. DOCUMENTER                                       │
│    Update related docs if needed                    │
├─────────────────────────────────────────────────────┤
│ 5. SPEC REVIEWER (Stage 1)                          │
│    Question: Does code match spec exactly?          │
│    Gate: approved | needs_implementation | needs_removal │
├─────────────────────────────────────────────────────┤
│ 6. CODE QUALITY REVIEWER (Stage 2)                  │
│    Question: Architecture, duplication, quality?    │
│    Gate: approved | needs_refactor                  │
├─────────────────────────────────────────────────────┤
│ 7. COMMIT (NO PUSH yet!)                            │
│    Only after BOTH reviewers approved               │
│    Push happens once in PHASE 3                     │
└─────────────────────────────────────────────────────┘
```

## Git Workflow

**SSOT:** `autopilot-git.md` — all Git operations, worktrees, commit rules, push strategy.

**CRITICAL:**
- **NEVER push to `main`** — only `develop`
- NO COMMIT without BOTH reviewers approved
- ONE push per spec (CI cost optimization)

**Quick flow:**
```
PHASE 0: worktree setup → baseline test
PHASE 2: per task → COMMIT (no push!)
PHASE 3: push feature → merge develop → push → cleanup
```

## Plan Subagent (PHASE 1)

If spec doesn't have `## Detailed Implementation Plan`, dispatch Plan subagent first.

**Detection:**
```python
# Check if plan exists
plan_exists = "## Detailed Implementation Plan" in spec_content
             or "## Implementation Plan" in spec_content  # legacy format
```

**If no plan → dispatch Plan subagent:**
```yaml
Task tool:
  description: "Create detailed plan for {TASK_ID}"
  subagent_type: "planner"
  prompt: |
    INPUT:
      SPEC_PATH: ai/features/{TASK_ID}-*.md
      TASK_ID: {task_id}
```

**Wait for plan before proceeding to PHASE 2!**

### Fresh Subagent per Task (PHASE 2)

Each task gets FRESH subagents — no shared context pollution!

**Why fresh subagents:**
- Context isolation → errors caught earlier
- No accumulated garbage
- Main context only sees: "Task N: completed, 3 files, tests pass"
- **Model routing** → cost optimization (sonnet for routine, opus for complex)

**Subagent dispatch (frontmatter provides model + tools):**
```yaml
# PLAN (once at start, if no detailed plan)
Task tool:
  subagent_type: "planner"
  prompt: |
    INPUT:
      SPEC_PATH: ai/features/{TASK_ID}-*.md
      TASK_ID: {task_id}

### Task Parsing Algorithm (MANDATORY)

Before dispatching to CODER, extract these values from spec:

**Step 1: Find current task in spec**
```
Read spec file → find "## Implementation Plan" or "## Detailed Implementation Plan"
Search for "### Task N:" where N = current task number
```

**Step 2: Extract TASK description**
```
# Pattern: ### Task N: [Title]\n\n[Context paragraph]
# Or: ### Task N: [Title]\n**Context:**\n[text]

TASK = title + context (first 2-3 sentences)
```

**Step 3: Extract ALLOWED FILES**
```
Read spec file → find "## Allowed Files"
Parse list of files (numbered or bulleted)
Files = [path1, path2, path3, ...]
```

**Step 4: Extract task-specific files**
```
In "### Task N:" section, find "**Files:**"
Parse: "Create:", "Modify:", "Test:" entries
Task_Files = subset of ALLOWED FILES for this task
```

**Example extraction:**
```
Spec contains:
  ## Allowed Files
  1. src/domains/billing/service.py
  2. src/domains/billing/service_test.py

  ### Task 1: Add calculate_price function
  **Context:** We need pricing logic for campaigns.
  **Files:**
  - Modify: src/domains/billing/service.py:45-60

Extracted:
  TASK = "Add calculate_price function. We need pricing logic for campaigns."
  ALLOWED FILES = ["src/domains/billing/service.py", "src/domains/billing/service_test.py"]
  TASK FILES = ["src/domains/billing/service.py:45-60"]
```

# CODER (for each task)
# First, export spec path for pre_edit.py hook (ARCH-233-22)
export CLAUDE_CURRENT_SPEC_PATH="ai/features/{TASK_ID}-*.md"

Task tool:
  subagent_type: "coder"
  prompt: |
    task: "Task {N}/{M} — {title}"
    type: {code|test|migrate}
    files:
      create: [{from task "Create:" entries}]
      modify: [{from task "Modify:" entries}]
    pattern: "{Research Source URL if any, else 'none'}"
    acceptance: "{from task acceptance criteria}"

# TESTER
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {current task description}"

# DEBUGGER (if tester fails)
Task tool:
  subagent_type: "debugger"
  prompt: |
    failure:
      test: "{failed_test_name}"
      error: "{traceback}"
    files_changed: [{list}]
    attempt: {debug_attempts}

# SPEC REVIEWER (Stage 1)
Task tool:
  subagent_type: "spec-reviewer"
  prompt: |
    feature_spec: "ai/features/{TASK_ID}*.md"
    task: "Task {N}/{M} — {title}"
    files_changed:
      - path: "{path}"
        action: "{created|modified}"

# CODE QUALITY REVIEWER (Stage 2)
Task tool:
  subagent_type: "review"
  prompt: |
    TASK: {description}
    FILES CHANGED: {list}
```

### Finishing Workflow (PHASE 3)

**SSOT:** `autopilot-git.md#5-finishing-workflow-phase-3`

**Steps:** test → status done → push feature → merge develop → push → cleanup

---

## Forbidden

### Parallel Safety (CRITICAL for multi-autopilot environments)
- ⛔ **NEVER take task with status `in_progress`** — another autopilot is working on it!
- ⛔ **ONLY take tasks with `queued` or `resumed`**
- Before taking ANY task: READ backlog → VERIFY status is `queued` or `resumed`
- If you see `in_progress` → SKIP immediately, find next `queued` task

### Git Safety

**SSOT:** `autopilot-git.md#6-git-safety`

- ⛔ **NEVER push to `main`** — only `develop`
- ⛔ **NEVER auto-resolve conflicts** → STATUS: blocked

### Code Quality
- Commit without Reviewer approved
- Group multiple tasks before review
- Skip Documenter or Reviewer
- Run ALL LLM tests without reason (Smart Testing!)
- Fix out-of-scope test failures (Scope Protection!)
- Check DoD at start — DoD is FINAL checklist!

### File Safety
- **Modify files NOT in `## Allowed Files` section** (File Allowlist!)
- **Take tasks with status `draft`** (no plan yet!)

### Test Safety
- **Modify tests in `tests/contracts/` or `tests/regression/`**
- **Change test assertions without user approval**

### Multi-Agent Safety (BUG-314)

**SSOT:** `autopilot-git.md#63-multi-agent-safety-bug-314`

**FORBIDDEN:** `git clean -fd`, `git reset --hard` — destroys parallel work.

## Test Safety Protocol

**SSOT:** `.claude/agents/tester.md#immutable-tests` + `#test-safety-awareness`

**Key rules:**
- ⛔ `tests/contracts/**`, `tests/regression/**` — NEVER modify
- Test fails → fix CODE, not test (unless created in current session)
- Unclear? → ASK USER

## File Allowlist (STRICT)

**SSOT:** `.claude/agents/coder.md#file-allowlist-check-mandatory`

**Rule:** File NOT in spec's `## Allowed Files` → REFUSE. No exceptions.

## LLM-Friendly Code Gates (ARCH-211)

**SSOT:** `.claude/agents/coder.md#llm-friendly-code-gates-mandatory` + `.claude/agents/review.md#llm-friendly-architecture`

**Quick check:**
- ⛔ File > 400 LOC (600 for tests) → split
- ⛔ `__init__.py` > 5 exports → reduce API
- ⛔ New code in `src/services/`, `src/db/`, `src/utils/` → use domains/
- ⛔ Import upward in dependency graph → fix direction

## How to Read Feature Doc

```
## Зачем (RU)     ← context for understanding
## Контекст (RU)  ← context for understanding
---
## Scope (EN)            ← what to do
## Allowed Files         ← ONLY these can be modified!
## Implementation Plan   ← YOUR TASKS!
  ### Task 1             ← execute in order
  ### Execution Order
---
## Definition of Done    ← check AFTER all tasks!
```

**Rule:**
1. Read `Implementation Plan` → find tasks
2. Execute by `Execution Order`
3. AFTER all tasks → check `Definition of Done`
4. DoD met → feature status → done

## Subagents

**v3.1:** Agent classification by invocation pattern + model routing.

### Internal Agents (called only by Autopilot)

| Agent | subagent_type | When |
|-------|---------------|------|
| Plan | `planner` | PHASE 1 (always) |
| Coder | `coder` | PHASE 2 per task |
| Tester | `tester` | PHASE 2 per task |
| Debugger | `debugger` | If Tester fails (max 3) |
| Spec Reviewer | `spec-reviewer` | PHASE 2 per task |
| Documenter | *(inline)* | PHASE 2 per task (runs in main context) |
| Diary Recorder | `diary-recorder` | On problems detected |

### External Agents (can be called by user OR Autopilot)

| Agent | subagent_type | When |
|-------|---------------|------|
| Scout | `scout` | Research (optional) |
| Code Quality | via `review` skill | PHASE 2 per task |

**Model SSOT:** Model defined in agent frontmatter (`agents/*.md:4`), not here.

### Inline Phases (main context, no Task tool)

| Phase | Why Inline |
|-------|------------|
| Worktree Setup | Simple bash commands |
| Commit/Push | Git operations |

**Model Routing Rationale:**
- **Opus** for: Plan (architecture), Debugger (root cause), Code Quality (deep analysis)
- **Sonnet** for: Coder (90% capability, 2x speed), Tester, Spec Reviewer, Scout
- **Haiku** for: Diary Recorder (fast, cheap)

**Dispatch via Task tool:**
```yaml
Task tool:
  subagent_type: "coder"  # frontmatter provides model + tools
  prompt: |
    TASK: {task description from plan}
    ALLOWED FILES: {from spec}
```

## Context Management — Auto-Compact

### Problem

После работы над несколькими спеками контекст накапливается (~200K tokens).
Качество деградирует, costs растут.

### Solution: Compact After Each Spec

```
AUTOPILOT SESSION
│
├─ Spec 1: FTR-100
│  ├── PHASE 0: Worktree setup
│  ├── PHASE 1: Plan
│  ├── PHASE 2: Tasks 1-5 (context needed between tasks!)
│  └── PHASE 3: Merge + Push
│      └── AUTO-COMPACT ← HERE
│
├─ Spec 2: BUG-200
│  ├── PHASE 0-3...
│  └── AUTO-COMPACT ← HERE
│
└─ No more queued → END
```

### Why Between Specs (Not Tasks)

| Compact After | Pros | Cons |
|---------------|------|------|
| Each task | Max freshness | Loses inter-task context |
| Each spec | Balance: fresh + context | Slightly more accumulation |
| Session end | No overhead | Context explosion |

**Decision:** Compact after each spec — natural boundary, tasks stay connected.

### Implementation

Add to PHASE 3 (Finishing) after cleanup:

```
6. **AUTO-COMPACT:**
   Invoke: /compact
7. Continue to next spec (or END)
```

## Main Loop (v3.0)

### Pre-Loop Validation (MANDATORY — BUG-358)

Before starting loop, detect orphan specs:
```bash
# 1. Count queued in backlog
backlog_count=$(grep -c "| queued |" ai/backlog.md 2>/dev/null || echo 0)

# 2. Count queued in spec files
spec_count=$(grep -l "Status:.*queued" ai/features/*.md 2>/dev/null | wc -l | tr -d ' ')

# 3. Compare
if [ "$spec_count" -gt "$backlog_count" ]; then
  echo "⚠️ Found $(($spec_count - $backlog_count)) orphan specs not in backlog!"
  # List orphan specs
  grep -l "Status:.*queued" ai/features/*.md | while read f; do
    id=$(basename "$f" | grep -oE '^[A-Z]+-[0-9]+')
    if ! grep -q "$id" ai/backlog.md; then
      echo "  - $f (missing from backlog)"
    fi
  done
  # ASK USER: "Add to backlog or skip?"
fi
```

⛔ If orphan specs found → report to user before proceeding!

```
while (queued/resumed tasks in ai/backlog.md):
  1. Read ai/backlog.md
  2. Find first queued/resumed (P0 first)
  3. Status → in_progress (BOTH spec + backlog!)

  ┌─────────────────────────────────────────────────────────────┐
  │ PHASE 0: WORKTREE SETUP (ALWAYS by default!)               │
  └─────────────────────────────────────────────────────────────┘
  4. CI health check: ./scripts/ci-status.sh

     **Exit code handling:**

     | Exit | Meaning | Action |
     |------|---------|--------|
     | 0 | Green or CI-only failures | Proceed to Step 5 |
     | 2 | Deploy failure | → DEPLOY ERROR PROTOCOL |

     ### DEPLOY ERROR PROTOCOL (exit code 2)

     ⛔ **DO NOT attempt to fix directly!**

     1. **Create BUG spec inline:**
        - ID: next BUG-XXX from backlog
        - Title: "Deploy failure: {workflow_name}"
        - Copy error output to spec
        - Allowed Files: based on error (migrations, edge functions, etc.)
        - Status: queued

     2. **Block current task:**
        - Edit current spec: Status → blocked
        - Add: "Blocked by: BUG-XXX (deploy failure)"
        - Edit backlog: Status → blocked

     3. **Take BUG spec immediately:**
        - Continue autopilot with BUG-XXX
        - After fix → return to queue (next spec, not blocked one)

     4. **Blocked spec stays blocked:**
        - Human decides when to resume
        - May need re-evaluation after deploy fix

  5. Determine branch type from task ID (FTR→feature, BUG→fix, etc.)
  6. Directory selection: .worktrees/ > worktrees/ > create
  7. Safety verification: git check-ignore + auto-fix .gitignore
  8. **Save MAIN_REPO:** `MAIN_REPO="$(git rev-parse --show-toplevel)"` (for Step 3b)
  9. Create worktree: git worktree add ".worktrees/{ID}" -b "{type}/{ID}"
  10. Copy .env: from main repo (gitignored, not in worktree!)
  11. Environment setup: spec-driven (python + docker/database if spec requires)
  12. Baseline verification: ./test fast must pass
  13. cd to worktree directory

  ┌─────────────────────────────────────────────────────────────┐
  │ PHASE 1: PLAN (if no detailed plan exists)                 │
  └─────────────────────────────────────────────────────────────┘
  14. Read feature file
  15. Check for "## Detailed Implementation Plan"
  16. If missing → dispatch Plan Subagent
  17. Wait for plan → verify it was added to spec

  ┌─────────────────────────────────────────────────────────────┐
  │ PHASE 2: EXECUTE (fresh subagent per task!)                │
  └─────────────────────────────────────────────────────────────┘
  18. FOR EACH TASK from plan:

      a. [Fresh CODER Subagent] → code → files_changed: [...]
         (subagent context dies after returning)

      b. [Fresh TESTER Subagent] → Smart Testing
         In-scope fail? → DEBUG LOOP (max 3, track retry count!)
         If retry_count > 1 → DIARY RECORDER (test_retry)
         (subagent context dies after returning)

      c. **DEPLOY VALIDATION** (if migrations or serverless functions changed):
         - files_changed has `db/migrations/*.sql`?
           → lint migration (local validation)
           → dry-run (optional, if connected)
           → ⛔ NO APPLY! CI applies after push!
         - files_changed has serverless functions?
           → validate locally (type check, lint)
           → ⛔ NO DEPLOY! CI deploys after push!
         - Validation failed? → STATUS: blocked, fix first

      d. DOCUMENTER → update docs

      e. **TWO-STAGE REVIEW:**
         ┌───────────────────────────────────────────────────┐
         │ Stage 1: SPEC REVIEWER                            │
         │   - Does code match spec exactly?                 │
         │   - needs_implementation → CODER adds             │
         │   - needs_removal → CODER removes                 │
         │   - approved → Stage 2                            │
         │   - Max 2 loops → status: blocked                 │
         └───────────────────────────────────────────────────┘

         **Spec Reviewer Loop (Stage 1):**
         ```
         SPEC REVIEWER returns:
         ├─ approved → proceed to Stage 2
         ├─ needs_implementation:
         │   └─ CODER adds missing features
         │   └─ TESTER verifies
         │   └─ SPEC REVIEWER re-reviews
         │   └─ Max 2 loops → status: blocked
         ├─ needs_removal:
         │   └─ CODER removes extra features
         │   └─ TESTER verifies
         │   └─ SPEC REVIEWER re-reviews
         │   └─ Max 2 loops → status: blocked
         ```
                              ↓
         ┌───────────────────────────────────────────────────┐
         │ Stage 2: CODE QUALITY REVIEWER                    │
         │   - Architecture, duplication, quality            │
         │   - needs_refactor → CODER fix → re-review        │
         │   - approved → COMMIT                             │
         │   - Max 2 loops → Council                         │
         └───────────────────────────────────────────────────┘

      f. COMMIT to {type}/{ID} branch (NO PUSH yet!)
         (main context only sees: "Task N: completed, 3 files")

  ┌─────────────────────────────────────────────────────────────┐
  │ PHASE 3: FINISHING (SINGLE PUSH!)                          │
  └─────────────────────────────────────────────────────────────┘
  18. ./test fast (final verification)
  19. PRE-DONE CHECKLIST — verify ALL items
  20. Update status → done (BOTH spec + backlog!)
  21. Commit: "docs: mark TYPE-XXX as done"
  22. Push feature branch to origin (backup)
  23. Switch to develop in main repo
  24. Stash uncommitted changes if any (hooks, parallel agents)
  25. git pull --rebase origin develop (sync with remote + Spark commits)
  26. Fast-forward merge feature → develop
  27. git push with retry (handles parallel developers)
  28. Restore stashed changes (if any)
  29. Cleanup worktree + delete local feature branch
  30. Legacy stash cleanup (optional, if spark-auto entries exist)
  31. AUTO-COMPACT: Run /compact to free context before next spec

  32. Goto 1 (next task)
```

## Status Sync (MANDATORY)

**Статус должен совпадать в ДВУХ местах:**

| Transition | Feature File | Backlog |
|------------|--------------|---------|
| Start work | `**Status:** in_progress` | `in_progress` |
| Blocked | `**Status:** blocked` | `blocked` |
| Complete | `**Status:** done` | `done` |

**При КАЖДОМ изменении статуса:**
1. Обнови `**Status:** X` в файле спеки
2. Обнови статус в строке backlog
3. Верифицируй — оба совпадают?

**⛔ Рассинхрон = путаница. Всегда обновляй ОБА!**

### Status Sync Self-Check (SAY OUT LOUD — BUG-358)

When changing status, **verbally confirm**:

```
"Updating spec file: Status → {new_status}" [Edit spec]
"Updating backlog: Status → {new_status}"   [Edit backlog]
"Both updated? ✓"                           [Verify match]
```

⛔ **Одно место = рассинхрон = путаница для следующего autopilot!**

## Pre-flight Check

Before taking a task from backlog:

1. **Status check:** Must be `queued` or `resumed`
   - `draft` → SKIP (spec not finished by Spark)
   - `in_progress` → SKIP (already working)
   - `blocked` → SKIP (needs human)
   - `done` → SKIP (completed)

2. **Plan check:** Feature file must contain `## Implementation Plan` or `## Detailed Implementation Plan`
   - No plan section → SKIP + log: `"⚠️ Skipping FTR-XXX: no implementation plan"`

Only proceed if BOTH checks pass.

## Smart Testing

**SSOT:** `.claude/agents/tester.md#smart-testing`

## Migration Validation — Git-First (TECH-059)

**SSOT:** `.claude/rules/database.md#migrations`

## Serverless Functions — CI Deploy Only (ARCH-233-07)

**Like migrations — CI is the only source of deploy!**

After CODER completes, check `files_changed`:
- Has serverless functions? → **LOCAL VALIDATION ONLY**

```bash
# Local validation (NO deploy!)
# Use your platform's CLI: deno check, tsc, etc.
```

⛔ **NEVER deploy serverless functions manually!**
→ CI deploys after push to develop.

## Scope Protection

**SSOT:** `.claude/agents/tester.md#scope-protection`

**Rule:** Test fails but NOT related to `files_changed`? → SKIP, don't fix. Log and continue.

## Limits

| Situation | Limit | After |
|-----------|-------|-------|
| Debug retry (code bug) | 3 | → Spark (BUG spec) |
| Debug retry (architecture) | 3 | → Council |
| ./test fast fail | 5 | → STOP (ask human) |
| ./test llm fail | 2 | → STOP (ask human) |
| Reviewer refactor | 2 | → Council |
| Out-of-scope | ∞ | skip |

## Escalation Decision Tree

After debug/refactor limits exhausted — choose escalation path:

```
After 3 debug attempts:
├── Is it a CODE BUG in current scope?
│   └── YES → Spark (create BUG-XXX spec)
│       └── "Баг требует отдельной спеки."
│
├── Is it an ARCHITECTURE question?
│   └── YES → Council (expert review)
│       └── "Архитектурный вопрос."
│
├── Is it OUT OF SCOPE?
│   └── YES → Log + Continue
│       └── "Out-of-scope. Skipping."
│
└── UNCLEAR?
    └── STOP → Ask Human
        └── "Не могу определить. Нужна помощь."
```

## Spark Escalation (for bugs)

When code bug can't be fixed after 3 attempts — create BUG spec via Spark.

**How to call:**
```yaml
Skill tool:
  skill: "spark"
  args: |
    MODE: bug
    SYMPTOM: "{test failure or error}"
    ATTEMPTS: [list of what was tried]
    FILES: [files_changed]
```

**Spark will:**
1. Run 5 Whys analysis
2. Find root cause
3. Create BUG-XXX spec
4. Hand off to autopilot (fresh context)

## Council Escalation (for architecture)

When architecture decision needed — escalate to Council via Skill tool.

**How to call:**
```yaml
Skill tool:
  skill: "council"
  args: |
    escalation_type: debug_stuck | refactor_stuck
    feature: "{TASK_ID}"
    task: "{N}/{M} — {name}"
    attempts:
      - attempt: 1
        action: "what did"
        result: "what got"
    current_error: "..."
    hypotheses_rejected:
      - hypothesis: "..."
        reason: "..."
    question: "Specific question"
```

**Council returns:**
- `solution_found` → apply fix, continue
- `architecture_change` → update plan, restart task
- `needs_human` → status: blocked

## Diary Recording

**SSOT:** `.claude/agents/diary-recorder.md`

**Triggers:** `bash_instead_of_tools`, `test_retry > 1`, `escalation_used`

**When:** After DEBUG LOOP (if retry > 1) or after escalation.

**Dispatch:**
```yaml
Task tool:
  subagent_type: "diary-recorder"
  prompt: |
    task_id: "{TASK_ID}"
    problem_type: {trigger}
    error_message: "{error}"
    files_changed: [...]
```

**Trigger File (ARCH-233-20):** Hook logs to `.claude/diary-triggers.jsonl` → process before COMMIT → clear after.

## Pre-Done Checklist (BLOCKING)

⛔ **Before setting status=done, verify ALL items:**

### Code Quality
- [ ] `./test fast` passes (run it!)
- [ ] No `# TODO` or `# FIXME` in changed files
- [ ] All tasks from Implementation Plan completed

### Definition of Done
- [ ] Each item in spec's "Definition of Done" section checked
- [ ] E2E user journey works (for UI features)

### Documentation
- [ ] If BREAKING/FEATURE change → changelog entry added (MANDATORY)
- [ ] Related docs updated (see `.claude/DOCUMENTATION.md`)

### Autopilot Log Completeness
For EACH task in log, verify:
- [ ] Coder entry present
- [ ] Tester entry present
- [ ] Spec Reviewer entry with status
- [ ] Code Quality entry with status
- [ ] Commit hash present

### Git State
- [ ] All changes committed
- [ ] Pushed to develop (or feature branch if worktree)
- [ ] `git status` shows clean working directory

### Cleanup
- [ ] Autopilot Log updated in spec file
- [ ] Status synced: spec=done AND backlog=done
- [ ] If worktree used → cleanup (see Worktree Cleanup)

**❌ Any item unchecked → status stays `in_progress`, fix first!**

---

## Statuses

**SSOT:** `CLAUDE.md#task-statuses`

**Flow:** `draft → queued → in_progress → done`
**Recovery:** `in_progress → blocked → resumed → in_progress`

## Autopilot Log

In feature file:
```markdown
## Autopilot Log

### Task N/M: [Name] — YYYY-MM-DD HH:MM
- Coder: completed (N files: file1.py, file2.py)
- Tester: passed | failed → debug loop | skipped (no tests for .md)
- Deploy: applied | skipped (no migrations)
- Documenter: completed | skipped (no docs needed)
- Spec Reviewer: approved | needs_implementation | needs_removal
- Code Quality Reviewer: approved | needs_refactor
- Commit: abc1234 | BLOCKED (reviewer not approved)
```

**Required fields (MANDATORY):**
- Coder — always present
- Tester — always present (even "skipped" is explicit)
- Spec Reviewer — always present
- Code Quality Reviewer — always present
- Commit — always present

**Если в логе отсутствует любое из полей → INCOMPLETE TASK**
