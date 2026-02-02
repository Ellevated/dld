# Tech: [TECH-069] Ralph Loop Autopilot (Fresh Context per Spec)

**Status:** queued | **Priority:** P1 | **Date:** 2026-02-02

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

## Implementation Plan

### Task 1: Create ralph-autopilot.sh

**Type:** code
**Files:** create `scripts/ralph-autopilot.sh`
**Acceptance:**
- [ ] Script reads ai/backlog.md for queued specs
- [ ] Calls `claude --print "autopilot SPEC_ID"` for each
- [ ] Logs progress to ai/diary/autopilot-progress.md
- [ ] Handles blocked/done/in_progress statuses
- [ ] Exits on blocked or all complete
- [ ] Executable (`chmod +x`)

### Task 2: Modify autopilot SKILL.md for Ralph mode

**Type:** code
**Files:** modify `template/.claude/skills/autopilot/SKILL.md`
**Acceptance:**
- [ ] Accepts optional SPEC_ID argument
- [ ] When SPEC_ID provided: process only that spec
- [ ] When SPEC_ID provided: exit after completion (no next spec)
- [ ] When no argument: existing behavior (interactive)

### Task 3: Update finishing.md

**Type:** docs
**Files:** modify `template/.claude/skills/autopilot/finishing.md`
**Acceptance:**
- [ ] Remove `/compact` step (no longer needed)
- [ ] Add "Exit for Ralph orchestrator" section
- [ ] Document Ralph mode exit behavior

### Task 4: Create progress log template

**Type:** docs
**Files:** create `ai/diary/autopilot-progress.md`
**Acceptance:**
- [ ] Template structure for progress logging
- [ ] Gitignored content, committed template

### Task 5: Update documentation

**Type:** docs
**Files:** modify `docs/15-skills-setup.md`
**Acceptance:**
- [ ] Document `ralph-autopilot.sh` usage
- [ ] Explain when to use Ralph vs interactive autopilot
- [ ] Add troubleshooting section

### Execution Order

1 → 2 → 3 → 4 → 5

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
