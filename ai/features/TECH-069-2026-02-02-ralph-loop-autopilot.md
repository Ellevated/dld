# Tech: [TECH-069] Ralph Loop Autopilot (Fresh Context per Spec)

**Status:** done | **Priority:** P1 | **Date:** 2026-02-02

## Why

Autopilot накапливает контекст между спеками. При запуске 2-3 спеков подряд auto-compact срабатывает ПОСЕРЕДИНЕ работы, что приводит к потере контекста и ошибкам.

**Root cause:** Один вызов `claude` обрабатывает все спеки в одной сессии.

**Решение:** Ralph Loop pattern — внешний bash-оркестратор запускает `claude` отдельно для каждого спека. Каждый спек = fresh context.

## Context

- Паттерн описан Geoffrey Huntley (July 2025)
- Реализация: [snarktank/ralph](https://github.com/snarktank/ralph) — 8.8k stars, MIT
- Статья: [Ship Features in Your Sleep with Ralph Loops](https://www.geocod.io/code-and-coordinates/2026-01-27-ralph-loops/) (Jan 2026)

**Ключевой принцип:** "Each iteration = fresh context. Memory persists via files, not Claude's memory."

---

## Scope

**In scope:**
- Bash скрипт `scripts/ralph-autopilot.sh` — внешний оркестратор
- Модификация autopilot — принимать SPEC_ID, обрабатывать только один спек
- Progress log `ai/diary/autopilot-progress.md` — learnings между итерациями
- Убрать `/compact` из finishing.md (больше не нужен)

**Out of scope:**
- PRD skills (у нас уже есть spark)
- Интерактивный UI для мониторинга
- Параллельное выполнение спеков

---

## Impact Tree Analysis

### Step 1: UP — who uses autopilot?
- [x] `grep -r "autopilot" template/.claude/` → skills/autopilot/, agents/
- [x] Main entry: `template/.claude/skills/autopilot/SKILL.md`

### Step 2: DOWN — what does autopilot depend on?
- [x] `ai/backlog.md` — task list (external state)
- [x] `ai/features/*.md` — specs (external state)
- [x] Subagents: planner, coder, tester, reviewer

### Step 3: BY TERM — grep
- [x] `grep -rn "queued" template/` → backlog parsing
- [x] `grep -rn "in_progress" template/` → status management

### Verification
- [x] All found files in Allowed Files
- [x] External state already exists (backlog.md, features/*.md)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `scripts/ralph-autopilot.sh` — new: bash orchestrator
2. `template/.claude/skills/autopilot/SKILL.md` — modify: accept SPEC_ID argument
3. `template/.claude/skills/autopilot/finishing.md` — modify: remove /compact reference
4. `ai/diary/autopilot-progress.md` — new: progress log template
5. `docs/15-skills-setup.md` — modify: document ralph-autopilot usage

**New files allowed:**
- `scripts/ralph-autopilot.sh`
- `ai/diary/autopilot-progress.md`

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: External Bash Orchestrator (Selected)

**Source:** [snarktank/ralph](https://github.com/snarktank/ralph), [Ralph Loops article](https://www.geocod.io/code-and-coordinates/2026-01-27-ralph-loops/)

**Summary:** Bash скрипт в while loop вызывает `claude "autopilot SPEC_ID"` для каждого спека.

**Pros:**
- Каждый спек в изолированной сессии
- Простая реализация (~50 LOC bash)
- External state уже есть (backlog.md)
- Можно оставить на ночь

**Cons:**
- Требует запуск из терминала (не из Claude)
- Нет интерактивного взаимодействия между спеками

### Approach 2: SDK Wrapper

**Summary:** Node.js приложение через Claude Agent SDK.

**Cons:**
- Требует переписать autopilot
- Добавляет зависимость от SDK
- Overkill для нашей задачи

### Selected: Approach 1

**Rationale:** Минимальные изменения. Bash — универсальный. snarktank/ralph доказал работоспособность (8.8k stars).

---

## Design

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ralph-autopilot.sh                    │
│                   (External Orchestrator)               │
└─────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    ┌──────────┐    ┌──────────┐    ┌──────────┐
    │ claude   │    │ claude   │    │ claude   │
    │ TECH-065 │    │ TECH-066 │    │ TECH-067 │
    └──────────┘    └──────────┘    └──────────┘
     Fresh ctx       Fresh ctx       Fresh ctx
          │                │                │
          ▼                ▼                ▼
    ┌─────────────────────────────────────────────────────┐
    │                  ai/backlog.md                      │
    │              (External State - SSOT)                │
    └─────────────────────────────────────────────────────┘
```

### ralph-autopilot.sh Flow

```bash
#!/bin/bash
# scripts/ralph-autopilot.sh

MAX_ITERATIONS=${1:-20}
ITERATION=0
LOG_FILE="ai/diary/autopilot-progress.md"

echo "# Ralph Autopilot Progress" > "$LOG_FILE"
echo "Started: $(date)" >> "$LOG_FILE"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))

    # 1. Get next queued spec from backlog
    SPEC_ID=$(grep -E '\| queued \|' ai/backlog.md | head -1 | \
              sed 's/.*|\s*\([A-Z]*-[0-9]*\)\s*|.*/\1/')

    # 2. Exit if no more queued
    if [ -z "$SPEC_ID" ]; then
        echo "=== ALL SPECS COMPLETE ===" | tee -a "$LOG_FILE"
        exit 0
    fi

    echo "" >> "$LOG_FILE"
    echo "## Iteration $ITERATION: $SPEC_ID" >> "$LOG_FILE"
    echo "Started: $(date)" >> "$LOG_FILE"

    # 3. Run Claude with fresh context
    echo "=== Starting $SPEC_ID (iteration $ITERATION) ==="
    claude --print "autopilot $SPEC_ID"
    EXIT_CODE=$?

    # 4. Log result
    echo "Exit code: $EXIT_CODE" >> "$LOG_FILE"

    # 5. Check status in backlog
    STATUS=$(grep "$SPEC_ID" ai/backlog.md | grep -oE 'done|blocked|in_progress')
    echo "Status: $STATUS" >> "$LOG_FILE"

    # 6. Handle blocked
    if [ "$STATUS" = "blocked" ]; then
        echo "=== BLOCKED: $SPEC_ID ===" | tee -a "$LOG_FILE"
        echo "Human intervention required." | tee -a "$LOG_FILE"
        exit 1
    fi

    # 7. Handle still in_progress (incomplete)
    if [ "$STATUS" = "in_progress" ]; then
        echo "=== WARNING: $SPEC_ID still in_progress ===" | tee -a "$LOG_FILE"
        echo "May need manual review." | tee -a "$LOG_FILE"
    fi

    echo "Completed: $(date)" >> "$LOG_FILE"
done

echo "=== MAX ITERATIONS REACHED ===" | tee -a "$LOG_FILE"
exit 2
```

### Autopilot SKILL.md Changes

```markdown
## Activation

- `autopilot` — process next queued spec (interactive)
- `autopilot SPEC_ID` — process specific spec only (Ralph mode)

## Ralph Mode

When called with SPEC_ID argument:
1. Process ONLY that spec
2. Do NOT look for next queued
3. Exit after completion (let external orchestrator handle next)
```

### finishing.md Changes

Remove:
```
9. Auto-compact:
   /compact (free context before next spec)
```

Add:
```
9. Exit for Ralph orchestrator:
   If running in Ralph mode (SPEC_ID was provided):
   - Do NOT continue to next spec
   - Return control to external orchestrator
   - Fresh context will be provided for next spec
```

---

## Detailed Implementation Plan

### Task 1: Create ralph-autopilot.sh

**Files:**
- Create: `template/scripts/ralph-autopilot.sh`

**Context:**
Create bash orchestrator script following the snarktank/ralph pattern. The script runs in a while loop, spawning fresh `claude` instances for each spec. Memory persists via ai/backlog.md (external state) and ai/diary/autopilot-progress.md (learnings).

**Step 1: Create the script file**

```bash
#!/usr/bin/env bash
# ralph-autopilot.sh - Long-running autonomous spec execution loop
# Each spec gets a fresh Claude context. Memory persists via files.
#
# Usage:
#   ./scripts/ralph-autopilot.sh              # Run max 20 iterations
#   ./scripts/ralph-autopilot.sh 50           # Run max 50 iterations
#   ./scripts/ralph-autopilot.sh --check      # Show next queued spec only
#
# Based on: https://github.com/snarktank/ralph (9.1k stars)

set -euo pipefail

# Configuration
MAX_ITERATIONS="${1:-20}"
BACKLOG_FILE="ai/backlog.md"
PROGRESS_FILE="ai/diary/autopilot-progress.md"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse arguments
if [[ "${1:-}" == "--check" ]]; then
    echo -e "${BLUE}Ralph Autopilot - Check Mode${NC}"
    SPEC_ID=$(grep -E '\|\s*(queued|resumed)\s*\|' "$BACKLOG_FILE" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || echo "")
    if [[ -z "$SPEC_ID" ]]; then
        echo "No queued/resumed specs found."
        exit 0
    fi
    echo "Next spec: $SPEC_ID"
    grep "$SPEC_ID" "$BACKLOG_FILE"
    exit 0
fi

# Validate prerequisites
if [[ ! -f "$BACKLOG_FILE" ]]; then
    echo -e "${RED}Error: $BACKLOG_FILE not found${NC}"
    exit 1
fi

if ! command -v claude &> /dev/null; then
    echo -e "${RED}Error: claude CLI not found${NC}"
    echo "Install: npm install -g @anthropic-ai/claude-code"
    exit 1
fi

# Initialize progress file
mkdir -p "$(dirname "$PROGRESS_FILE")"
if [[ ! -f "$PROGRESS_FILE" ]]; then
    cat > "$PROGRESS_FILE" << 'EOF'
# Ralph Autopilot Progress

Progress log for autonomous spec execution.
Each entry = one Claude session = one spec.

---

EOF
fi

# Add session header
{
    echo ""
    echo "## Session: $(date '+%Y-%m-%d %H:%M')"
    echo ""
} >> "$PROGRESS_FILE"

echo -e "${BLUE}"
echo "  ____       _       _"
echo " |  _ \ __ _| |_ __ | |__"
echo " | |_) / _\` | | '_ \| '_ \\"
echo " |  _ < (_| | | |_) | | | |"
echo " |_| \_\__,_|_| .__/|_| |_|"
echo "              |_|"
echo -e "${NC}"
echo "Ralph Autopilot - Fresh Context per Spec"
echo "Max iterations: $MAX_ITERATIONS"
echo ""

ITERATION=0

while [[ $ITERATION -lt $MAX_ITERATIONS ]]; do
    ITERATION=$((ITERATION + 1))

    # 1. Get next queued/resumed spec from backlog
    SPEC_ID=$(grep -E '\|\s*(queued|resumed)\s*\|' "$BACKLOG_FILE" 2>/dev/null | head -1 | \
              grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | head -1 || echo "")

    # 2. Exit if no more queued
    if [[ -z "$SPEC_ID" ]]; then
        echo -e "${GREEN}=== ALL SPECS COMPLETE ===${NC}"
        echo "Completed at iteration $ITERATION"
        {
            echo "### Result: ALL COMPLETE"
            echo "Finished: $(date '+%Y-%m-%d %H:%M')"
            echo "Total iterations: $ITERATION"
        } >> "$PROGRESS_FILE"
        exit 0
    fi

    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE} Iteration $ITERATION/$MAX_ITERATIONS: $SPEC_ID${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════${NC}"

    # Log iteration start
    {
        echo "### Iteration $ITERATION: $SPEC_ID"
        echo "Started: $(date '+%Y-%m-%d %H:%M')"
    } >> "$PROGRESS_FILE"

    # 3. Run Claude with fresh context (Ralph mode)
    # --print captures output, autopilot processes single spec
    set +e
    OUTPUT=$(claude --print "autopilot $SPEC_ID" 2>&1 | tee /dev/stderr)
    EXIT_CODE=$?
    set -e

    # 4. Log result
    echo "Exit code: $EXIT_CODE" >> "$PROGRESS_FILE"

    # 5. Check updated status in backlog
    STATUS=$(grep "$SPEC_ID" "$BACKLOG_FILE" 2>/dev/null | grep -oE 'done|blocked|in_progress|queued' | head -1 || echo "unknown")
    echo "Status: $STATUS" >> "$PROGRESS_FILE"

    # 6. Handle blocked - requires human intervention
    if [[ "$STATUS" == "blocked" ]]; then
        echo -e "${RED}=== BLOCKED: $SPEC_ID ===${NC}"
        echo "Human intervention required. Check spec for ACTION REQUIRED."
        {
            echo "**BLOCKED** - Human intervention required"
            echo "Stopped: $(date '+%Y-%m-%d %H:%M')"
        } >> "$PROGRESS_FILE"
        exit 1
    fi

    # 7. Handle still in_progress (incomplete - may need retry)
    if [[ "$STATUS" == "in_progress" ]]; then
        echo -e "${YELLOW}=== WARNING: $SPEC_ID still in_progress ===${NC}"
        echo "Session may have ended early. Will retry next iteration."
        echo "**WARNING** - Still in_progress, will retry" >> "$PROGRESS_FILE"
    fi

    # 8. Log completion
    if [[ "$STATUS" == "done" ]]; then
        echo -e "${GREEN}=== DONE: $SPEC_ID ===${NC}"
        echo "**DONE**" >> "$PROGRESS_FILE"
    fi

    echo "Completed: $(date '+%Y-%m-%d %H:%M')" >> "$PROGRESS_FILE"
    echo "" >> "$PROGRESS_FILE"

    # Brief pause between iterations
    sleep 2
done

echo -e "${YELLOW}=== MAX ITERATIONS REACHED ===${NC}"
echo "Reached $MAX_ITERATIONS iterations. May need to continue."
{
    echo "### Result: MAX ITERATIONS"
    echo "Stopped at: $(date '+%Y-%m-%d %H:%M')"
} >> "$PROGRESS_FILE"
exit 2
```

**Step 2: Make executable**

```bash
chmod +x template/scripts/ralph-autopilot.sh
```

**Step 3: Verify script syntax**

```bash
bash -n template/scripts/ralph-autopilot.sh
```

Expected: No output (no syntax errors).

**Acceptance Criteria:**
- [ ] Script parses backlog.md for queued/resumed specs
- [ ] Calls `claude --print "autopilot SPEC_ID"` for each
- [ ] Logs progress to ai/diary/autopilot-progress.md
- [ ] Handles blocked status (exit 1)
- [ ] Handles done status (continue to next)
- [ ] Exits cleanly when all complete (exit 0)
- [ ] Exits on max iterations (exit 2)
- [ ] Works on macOS and Linux (uses /usr/bin/env bash)

---

### Task 2: Modify autopilot SKILL.md for Ralph mode

**Files:**
- Modify: `template/.claude/skills/autopilot/SKILL.md:23-32`

**Context:**
Add Ralph mode support - when SPEC_ID is provided as argument, autopilot processes only that single spec and exits. This enables external orchestration with fresh context per spec.

**Step 1: Update Activation section**

Find the section (around lines 23-32):
```markdown
# Autopilot v3.4 — Fresh Subagents + Worktree Always

Autonomous execution: Plan → Fresh subagent per task → commit → next.

**Activation:**
- `autopilot` — creates worktree, plans, executes (default)
- `autopilot --no-worktree` — skip worktree (for tiny fixes only)
```

Replace with:
```markdown
# Autopilot v3.5 — Fresh Subagents + Ralph Mode

Autonomous execution: Plan → Fresh subagent per task → commit → next.

**Activation:**
- `autopilot` — process all queued specs (interactive)
- `autopilot SPEC_ID` — process single spec only (Ralph mode)
- `autopilot --no-worktree` — skip worktree (for tiny fixes only)

## Ralph Mode

When called with `autopilot TECH-069` (specific SPEC_ID):

1. **Process ONLY that spec** — ignore other queued specs
2. **Exit after completion** — do NOT continue to next spec
3. **Let external orchestrator handle next** — fresh context per spec

This enables `ralph-autopilot.sh` to run overnight with fresh context per spec.

**Detection:** If first argument matches pattern `(TECH|FTR|BUG|ARCH)-\d+`, enter Ralph mode.
```

**Step 2: Update Main Loop section**

Find (around line 129-156):
```markdown
## Main Loop

```
while (queued/resumed tasks in ai/backlog.md):
  1. Read backlog → find first queued/resumed (P0 first)
```

Replace with:
```markdown
## Main Loop

### Interactive Mode (no SPEC_ID)
```
while (queued/resumed tasks in ai/backlog.md):
  1. Read backlog → find first queued/resumed (P0 first)
  2. Status → in_progress (BOTH spec + backlog!)

  3. PHASE 0: Worktree Setup
     See: worktree-setup.md

  4. PHASE 1: Plan (if needed)
     Check for "## Implementation Plan"
     Missing? → dispatch Plan Subagent

  5. PHASE 2: Execute
     FOR EACH TASK:
       a. CODER → files_changed
       b. TESTER → pass? (debug loop if fail)
       c. DEPLOY CHECK
       d. DOCUMENTER
       e. TWO-STAGE REVIEW
       f. COMMIT (no push)

  6. PHASE 3: Finishing
     See: finishing.md

  7. Continue to next spec
```

### Ralph Mode (SPEC_ID provided)
```
1. Validate SPEC_ID exists in backlog
2. Verify status is queued or resumed (not in_progress!)
3. Set status → in_progress
4. PHASE 0-3: Same as interactive
5. EXIT (do NOT continue to next spec)
   └─ External orchestrator provides fresh context
```

**Why Ralph mode?** Prevents context accumulation. Each spec = fresh Claude session.
```

**Step 3: Update Context Management section**

Find (around line 191-200):
```markdown
## Context Management

Compact after each spec to prevent context explosion:

```
Spec 1 → PHASE 0-3 → AUTO-COMPACT
Spec 2 → PHASE 0-3 → AUTO-COMPACT
...
No more queued → END
```
```

Replace with:
```markdown
## Context Management

### Interactive Mode
Context accumulates. AUTO-COMPACT after each spec (legacy).

### Ralph Mode (Recommended)
Each spec = fresh Claude session via external orchestrator.

```
ralph-autopilot.sh:
  └─ claude "autopilot TECH-065" → fresh context
  └─ claude "autopilot TECH-066" → fresh context
  └─ claude "autopilot TECH-067" → fresh context
  └─ ...
```

**Memory persists via files:**
- `ai/backlog.md` — task status
- `ai/diary/autopilot-progress.md` — learnings
- Git history — code changes

See: `./scripts/ralph-autopilot.sh`
```

**Acceptance Criteria:**
- [ ] SKILL.md documents Ralph mode activation
- [ ] When SPEC_ID provided: process only that spec
- [ ] When SPEC_ID provided: exit after PHASE 3 (no next spec loop)
- [ ] When no argument: existing interactive behavior
- [ ] Version bumped to v3.5

---

### Task 3: Update finishing.md

**Files:**
- Modify: `template/.claude/skills/autopilot/finishing.md:41-43`

**Context:**
Remove the /compact step (replaced by Ralph mode fresh context) and add Ralph mode exit behavior.

**Step 1: Find and replace step 9**

Find (lines 41-43):
```markdown
9. Auto-compact:
   /compact (free context before next spec)
```

Replace with:
```markdown
9. Ralph Mode Exit Check:
   If SPEC_ID was provided (Ralph mode):
   - Do NOT continue to next spec
   - Do NOT call /compact
   - EXIT cleanly — external orchestrator handles next
   - Fresh context will be provided for next spec

   If interactive mode (no SPEC_ID):
   - Continue to next queued spec
   - Context already managed by orchestrator
```

**Step 2: Add note at top of file**

Add after line 1 (`# Finishing Workflow (PHASE 3)`):
```markdown

**Note:** In Ralph mode (SPEC_ID provided), step 9 exits immediately after merge.
External orchestrator (`ralph-autopilot.sh`) provides fresh context for next spec.
```

**Acceptance Criteria:**
- [ ] /compact step removed (no longer needed)
- [ ] Ralph mode exit behavior documented
- [ ] Interactive mode continues to next spec
- [ ] Note explains Ralph mode at top

---

### Task 4: Create progress log template

**Files:**
- Create: `ai/diary/autopilot-progress.md`

**Context:**
Create template for Ralph autopilot progress logging. This file captures learnings between iterations. The actual content is written by ralph-autopilot.sh, but we need the initial template.

**Step 1: Create the template file**

```markdown
# Ralph Autopilot Progress

Progress log for autonomous spec execution.
Each entry = one Claude session = one spec.

Memory persists via:
- This file (learnings)
- `ai/backlog.md` (task status)
- Git history (code changes)

---

*Entries added automatically by `ralph-autopilot.sh`*
```

**Note:** This file is in ai/ directory which is gitignored for DLD itself, but for user projects the template provides the structure.

**Acceptance Criteria:**
- [ ] Template file created
- [ ] Explains purpose of progress log
- [ ] Documents what persists between sessions

---

### Task 5: Update documentation

**Files:**
- Modify: `docs/15-skills-setup.md` (add after line 300)

**Context:**
Document ralph-autopilot.sh usage, when to use Ralph mode vs interactive, and troubleshooting.

**Step 1: Add Ralph Autopilot section after Testing section (around line 303)**

Find:
```markdown
## Testing

```bash
/spark quick      # Research + questions
```

Add after that section:
```markdown
---

## Ralph Autopilot (Overnight Execution)

Run multiple specs with fresh context per spec. No context accumulation.

### When to Use

| Mode | Use When |
|------|----------|
| **Interactive** (`autopilot`) | 1-2 specs, want to monitor |
| **Ralph** (`ralph-autopilot.sh`) | 3+ specs, overnight runs, context-sensitive work |

### Usage

```bash
# Run with default 20 iterations
./scripts/ralph-autopilot.sh

# Run with custom max iterations
./scripts/ralph-autopilot.sh 50

# Check what's next without running
./scripts/ralph-autopilot.sh --check
```

### How It Works

```
ralph-autopilot.sh (bash loop)
  │
  ├─ claude "autopilot TECH-065"  → fresh context
  │    └─ PHASE 0-3 → done
  │
  ├─ claude "autopilot TECH-066"  → fresh context
  │    └─ PHASE 0-3 → done
  │
  └─ ... until all queued complete or blocked
```

**Key principle:** Each spec = fresh Claude session. Memory persists via files, not Claude's memory.

### Files

| File | Purpose |
|------|---------|
| `scripts/ralph-autopilot.sh` | Bash orchestrator |
| `ai/diary/autopilot-progress.md` | Learnings between iterations |
| `ai/backlog.md` | Task status (SSOT) |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All specs complete |
| 1 | Spec blocked (needs human) |
| 2 | Max iterations reached |

### Troubleshooting

**Script exits immediately:**
- Check `ai/backlog.md` has specs with `queued` status
- Verify spec files exist in `ai/features/`

**Spec stays in_progress:**
- Claude session may have ended early
- Ralph will retry on next iteration
- If persists, check spec for issues

**Blocked status:**
- Human intervention required
- Check spec file for `ACTION REQUIRED` section
- Fix issue, change status to `resumed`, re-run

### Reference

Based on [snarktank/ralph](https://github.com/snarktank/ralph) pattern.
See Geoffrey Huntley's [Ralph article](https://ghuntley.com/ralph/) for background.
```

**Acceptance Criteria:**
- [ ] Usage examples documented
- [ ] When to use Ralph vs interactive explained
- [ ] Exit codes documented
- [ ] Troubleshooting section added
- [ ] References to original Ralph pattern

---

### Execution Order

```
Task 1 (ralph-autopilot.sh)
    ↓
Task 2 (SKILL.md Ralph mode)
    ↓
Task 3 (finishing.md update)
    ↓
Task 4 (progress log template)
    ↓
Task 5 (documentation)
```

All tasks are sequential. Task 2-3 implement the autopilot side that Task 1's script calls.

### Dependencies

- Task 2 depends on Task 1 conceptually (script defines how autopilot is called)
- Task 3 depends on Task 2 (finishing behavior depends on Ralph mode detection)
- Task 4-5 are independent but should come after core implementation

### Research Sources (verified)

- [snarktank/ralph](https://github.com/snarktank/ralph) (9.1k stars) — confirmed pattern works, reviewed ralph.sh implementation
- Original ralph.sh uses `claude --dangerously-skip-permissions --print` for autonomous mode
- Key insight: "Each iteration = fresh AI instance. Memory persists via git history, progress.txt, and prd.json"

---

## Definition of Done

### Functional
- [ ] `./scripts/ralph-autopilot.sh` runs multiple specs sequentially
- [ ] Each spec gets fresh Claude session
- [ ] Progress logged to ai/diary/autopilot-progress.md
- [ ] Script exits cleanly on all-complete or blocked
- [ ] Interactive `autopilot` still works (no regression)

### Technical
- [ ] No context accumulation between specs
- [ ] External state (backlog.md) correctly updated by autopilot
- [ ] Script works on macOS and Linux

### Documentation
- [ ] Usage documented in docs/15-skills-setup.md
- [ ] Ralph mode explained in SKILL.md

---

## Research Sources

- [snarktank/ralph](https://github.com/snarktank/ralph) — reference implementation
- [Ship Features in Your Sleep with Ralph Loops](https://www.geocod.io/code-and-coordinates/2026-01-27-ralph-loops/) — pattern explanation
- [Geoffrey Huntley's original Ralph article](https://ghuntley.com/ralph/) — origin of pattern

---

## Autopilot Log

*(Filled by Autopilot during execution)*
