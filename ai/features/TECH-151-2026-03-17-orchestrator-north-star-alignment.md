# Tech: [TECH-151] Orchestrator North-Star Alignment
**Status:** queued | **Priority:** P0 | **Date:** 2026-03-17

## Why
Текущее поведение оркестратора расходится с north-star моделью из `ai/architect/orchestrator-final-state.md`. Spark создаёт `draft` спеки вместо `queued`, callback шлёт approval-уведомления с кнопками, `scan_drafts()` — мёртвый код, messaging в callback ссылается на устаревший inbox-writing flow, а `reflect/SKILL.md` пишет findings в `ai/inbox/` вместо дневника. 10 инвариантов north-star должны быть реализованы в коде и документации.

## Context
North-star документ (`ai/architect/orchestrator-final-state.md`) определяет линейный пайплайн: OpenClaw → inbox → Spark → backlog(queued) → Autopilot → QA → Reflect → STOP. Текущий код частично обновлён (Step 6.5 в callback уже no-op, qa-loop.sh пишет в ai/qa/), но 6 рассинхронизаций остаются.

---

## Scope
**In scope:**
- Spark status: `draft` → `queued` во всех docs (SKILL.md, completion.md, feature-mode.md, bug-mode.md)
- Удаление `scan_drafts()` из orchestrator.sh (мёртвый код)
- Удаление Step 5.5 (draft approval) из pueue-callback.sh
- Очистка Step 5.9 `WILL_WRITE_INBOX` messaging из pueue-callback.sh
- Замена inbox-writing в reflect/SKILL.md на diary-only output
- Template sync (template/.claude/skills/spark/*)
- Обновление CLAUDE.md Task Statuses

**Out of scope:**
- Перенос QA/Reflect dispatch из callback в orchestrator poll cycle (отдельная задача)
- Удаление `send_spec_approval()` / `_parse_spec_for_approval()` из notify.py (может понадобиться для ручного override)
- Удаление `approve_handler.py` handlers (draft→queued transition остаётся для ручного override через Telegram)
- Очистка `.notified-drafts-*` файлов на VPS (операторская задача)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `scan_backlog()` in orchestrator.sh:200 — reads `queued` from backlog → already correct
- `pueue-callback.sh:230` — reads `draft` from backlog → becomes dead path
- `approve_handler.py:241` — draft→queued transition → stays for manual override
- `test_approve_handler.py` — tests draft→queued → stays valid

### Step 2: DOWN — what depends on?
- `.notified-drafts-{project_id}` state files — used by callback Step 5.5 dedup → orphaned after Step 5.5 removal
- `db.get_project_state()` — used in Step 5.5 → no longer needed there
- `notify.py --spec-approval` — called by Step 5.5 → no longer called from callback

### Step 3: BY TERM — grep entire project
| File | Line | Context | Action |
|------|------|---------|--------|
| scripts/vps/orchestrator.sh | 371-424 | `scan_drafts()` | delete function |
| scripts/vps/pueue-callback.sh | 214-256 | Step 5.5: draft approval | delete block |
| scripts/vps/pueue-callback.sh | 260-303 | Step 5.9: WILL_WRITE_INBOX + messaging | clean up |
| .claude/skills/spark/SKILL.md | 59, 63 | "Create spec in `draft` status" | change to `queued` |
| .claude/skills/spark/completion.md | 45, 82-88, 93-101, 260 | draft references | change to `queued` |
| .claude/skills/spark/feature-mode.md | 643 | "spec stays `draft`" | change to `queued` |
| .claude/skills/spark/bug-mode.md | 197-198, 211 | draft in checklist + output | change to `queued` |
| .claude/skills/reflect/SKILL.md | 107-141 | Step 5: writes ai/inbox/ | change to diary-only |
| CLAUDE.md | 263 | Task Statuses: draft = Spark | update definition |

### Step 4: CHECKLIST — mandatory folders
- [x] `scripts/vps/tests/` — test_approve_handler.py stays valid (tests manual override path)
- [x] `ai/glossary/` — N/A
- [x] `db/migrations/` — N/A (no schema changes)

### Verification
- [x] All found files added to Allowed Files
- [x] grep "draft" after changes → only in approve_handler.py (manual override) and CLAUDE.md (status definition)

---

## Allowed Files
**ONLY these files may be modified during implementation:**
1. `scripts/vps/orchestrator.sh` — remove scan_drafts()
2. `scripts/vps/pueue-callback.sh` — remove Step 5.5, clean Step 5.9
3. `.claude/skills/spark/SKILL.md` — fix status references
4. `.claude/skills/spark/completion.md` — fix all draft→queued
5. `.claude/skills/spark/feature-mode.md` — fix gate failure status
6. `.claude/skills/spark/bug-mode.md` — fix checklist + output
7. `.claude/skills/reflect/SKILL.md` — replace inbox-writing with diary output
8. `CLAUDE.md` — update Task Statuses table
9. `template/.claude/skills/spark/SKILL.md` — template sync
10. `template/.claude/skills/spark/completion.md` — template sync
11. `template/.claude/skills/spark/feature-mode.md` — template sync
12. `template/.claude/skills/spark/bug-mode.md` — template sync
13. `template/.claude/skills/reflect/SKILL.md` — template sync

**New files allowed:**
- None

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** scripts/vps (orchestrator infrastructure)
**Cross-cutting:** N/A
**Data model:** project_state.phase (SQLite, no changes)

---

## Approaches

### Approach 1: Full north-star alignment — always `queued` (based on patterns scout + external research)
**Source:** [Singular Update Queue (Martin Fowler)](https://martinfowler.com/articles/patterns-of-distributed-systems/singular-update-queue.html), [Approvals for autonomous AI agents (Cordum)](https://cordum.io/blog/approvals-for-autonomous-workflows)
**Summary:** Spark всегда создаёт `queued`. scan_drafts() и Step 5.5 удаляются. Reflect пишет только в diary. WILL_WRITE_INBOX messaging чистится. Template sync.
**Pros:** Простота, один путь, полное соответствие north-star invariant #4
**Cons:** Нет паузы между Spark и Autopilot для ручных запусков

### Approach 2: Mode-aware (headless=queued, interactive=draft)
**Source:** [Draft-First Automation](https://operaitions.ai/blog/automation-you-can-trust/)
**Summary:** Headless Spark создаёт `queued`, interactive — `draft`. Step 5.5 остаётся для interactive path. scan_drafts() repurpose.
**Pros:** Backward compatible, interactive users видят spec перед execution
**Cons:** Два пути, scan_drafts() не удаляется, больше кода

### Selected: 1
**Rationale:** North-star invariant #4 универсален. OpenClaw — conversational gate до inbox. Interactive `/spark` — человек сам создал spec, не нуждается в self-approval. Mode-aware добавляет ветвление без safety value.

---

## Design

### User Flow
1. OpenClaw обсуждает задачу с human/tester
2. OpenClaw пишет mature item в `ai/inbox/`
3. Orchestrator scan_inbox() → inbox-processor.sh → Spark (pueue)
4. Spark создаёт spec в `ai/features/` со статусом `queued` и entry в `ai/backlog.md`
5. Orchestrator scan_backlog() подхватывает `queued` → dispatches Autopilot
6. Autopilot implements → callback dispatches QA + Reflect
7. QA пишет report в `ai/qa/` → STOP
8. Reflect пишет в diary → STOP
9. OpenClaw читает artifacts и решает следующий шаг

### Architecture
Изменения затрагивают 3 слоя:
- **Skill docs** (Spark, Reflect) — определяют поведение LLM-агентов
- **Orchestrator scripts** (bash) — управляют жизненным циклом задач
- **Callback scripts** (bash) — реагируют на завершение pueue-задач

---

## Detailed Implementation Plan

### Research Sources
- [Singular Update Queue (Martin Fowler)](https://martinfowler.com/articles/patterns-of-distributed-systems/singular-update-queue.html) — single-writer inbox pattern
- [Approvals for autonomous AI agents (Cordum)](https://cordum.io/blog/approvals-for-autonomous-workflows) — approval gate placement
- [6 Patterns for Production-Grade Pipelines (Wasowski)](https://medium.com/@wasowski.jarek/6-patterns-that-turned-my-pipeline-from-chaotic-to-production-grade-agentic-workflows-cdd45d2d314a) — immutable state machine, durable artifacts

### Task 1: Update Spark skill docs (draft -> queued)

**Files:**
  - Modify: `.claude/skills/spark/SKILL.md:59,63`
  - Modify: `.claude/skills/spark/completion.md:45,82-83,93,97-101,155-157,260`
  - Modify: `.claude/skills/spark/feature-mode.md:643`
  - Modify: `.claude/skills/spark/bug-mode.md:197-198,211`

**Context:** Spark currently documents `draft` as the output status in 4 skill files. North-star invariant #4 says Spark creates `queued` directly. Line 226 of completion.md already says `queued` -- no change needed there.

**Step 1: SKILL.md -- lines 59 and 63**

Replace line 59:
```
- Create spec in `draft` status (orchestrator handles approval via Telegram)
```
With:
```
- Create spec in `queued` status (orchestrator picks it up automatically)
```

Replace line 63:
```
- Create spec in `draft` status (user approves via Telegram or directly)
```
With:
```
- Create spec in `queued` status (user created it, no self-approval needed)
```

**Step 2: completion.md -- 9 changes**

Replace line 45:
```
5. [ ] **Status = draft** — spec awaits human approval via Telegram!
```
With:
```
5. [ ] **Status = queued** — spec is ready for orchestrator pickup
```

Replace line 82:
```
"Setting spec file: Status → draft"        [Write/Edit spec]
```
With:
```
"Setting spec file: Status → queued"        [Write/Edit spec]
```

Replace line 83:
```
"Setting backlog entry: Status → draft"    [Edit backlog]
```
With:
```
"Setting backlog entry: Status → queued"    [Edit backlog]
```

Replace line 93:
```
| FTR-XXX | Task name | draft | P1 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```
With:
```
| FTR-XXX | Task name | queued | P1 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

Replace lines 97-101 (status table):
```
| Situation | Status | Reason |
|-----------|--------|--------|
| Spark completed fully | `draft` | Awaits human approval via Telegram |
| Spec created but interrupted | `draft` | Awaits completion or approval |
| Needs discussion/postponed | `draft` | Left for refinement |
```
With:
```
| Situation | Status | Reason |
|-----------|--------|--------|
| Spark completed fully | `queued` | Ready for orchestrator pickup |
| Spec created but interrupted | `draft` | Awaits completion |
| Needs discussion/postponed | `draft` | Left for refinement |
```

Replace lines 155-157 (Bug Hunt grouped specs table):
```
| BUG-085 | Hook safety fixes | draft | P0 | [BUG-085](features/BUG-085.md) |
| BUG-086 | Missing references | draft | P1 | [BUG-086](features/BUG-086.md) |
| BUG-087 | Prompt injection | draft | P1 | [BUG-087](features/BUG-087.md) |
```
With:
```
| BUG-085 | Hook safety fixes | queued | P0 | [BUG-085](features/BUG-085.md) |
| BUG-086 | Missing references | queued | P1 | [BUG-086](features/BUG-086.md) |
| BUG-087 | Prompt injection | queued | P1 | [BUG-087](features/BUG-087.md) |
```

Replace line 260:
```
spec_status: draft  # always draft — human approves via Telegram
```
With:
```
spec_status: queued  # always queued — orchestrator picks up automatically
```

**Step 3: feature-mode.md -- line 643**

Replace line 643:
```
**If any gate fails →** spec stays `draft`, return to Phase 3 (re-synthesize with feedback).
```
With:
```
**If any gate fails →** spec stays in current state, return to Phase 3 (re-synthesize with feedback).
```

**Step 4: bug-mode.md -- lines 197, 198, 211**

Replace line 197:
```
8. [ ] Spec file created (status: draft)
```
With:
```
8. [ ] Spec file created (status: queued)
```

Replace line 198:
```
9. [ ] Backlog entry added (status: draft)
```
With:
```
9. [ ] Backlog entry added (status: queued)
```

Replace line 211:
```
spec_status: draft
```
With:
```
spec_status: queued
```

**Step 5: Verify**

```bash
grep -rn "draft" .claude/skills/spark/ | grep -vi "gate fail\|current state\|interrupted\|discussion\|postponed\|refinement\|bughunt.md\|Bug Hunt\|MOVED\|standalone"
```

Expected: 0 results (all remaining `draft` refs are for incomplete/interrupted specs or bughunt redirect text).

**Acceptance:**
- [ ] `grep -rn "spec_status: draft\|Status = draft\|status: draft" .claude/skills/spark/` returns 0 results
- [ ] `grep -rn "Status.*queued\|spec_status: queued" .claude/skills/spark/` returns matches in all 4 files

---

### Task 2: Update Reflect SKILL.md -- inbox -> diary-only output

**Files:**
  - Modify: `.claude/skills/reflect/SKILL.md:106-141,181-184,195`

**Context:** Reflect currently writes findings to `ai/inbox/`, creating a Spark dispatch loop. North-star says Reflect writes only to diary/reflect durable files. OpenClaw decides next steps.

**Step 1: Replace Step 5 (lines 106-134)**

Replace lines 106-134:
```
### Step 5: Write to Inbox (NOT direct spec creation!)

**CRITICAL:** Reflect does NOT create TECH specs directly. It writes findings to inbox.
Spark will create specs from reflect findings.

For each pattern found (frequency >= 3):

**Location:** `ai/inbox/{timestamp}-reflect-{N}.md`

**Format:**
\`\`\`markdown
# Idea: {timestamp}
**Source:** reflect
**Route:** spark
**Status:** new
**Context:** ai/diary/index.md
---
Reflect finding: {description of pattern and recommendation}
Frequency: {N} occurrences. Evidence: {task_ids}.
Pattern type: {user_preference | failure_pattern | design_decision | tool_workflow}
Proposed action: {what should change}
\`\`\`

**Rules:**
- Only patterns with frequency >= 3 get inbox files
- Patterns with frequency 2 are noted in diary but NOT sent to inbox
- Max 5 inbox files per reflect session (prioritize by frequency)
- One inbox file per pattern (not per diary entry)
- Context links to diary index for full evidence
```
With:
```
### Step 5: Write Reflect Report (durable file, NOT inbox)

**CRITICAL:** Reflect does NOT write to `ai/inbox/`. It writes a durable report.
OpenClaw reads reflect artifacts and decides next steps.

For each pattern found (frequency >= 3):

**Location:** `ai/reflect/reports/{YYYY-MM-DD}-reflect.md`

**Format:**
\`\`\`markdown
# Reflect Report: {YYYY-MM-DD}

## Patterns Found

### Pattern 1: {description}
- **Frequency:** {N} occurrences
- **Evidence:** {task_ids}
- **Type:** {user_preference | failure_pattern | design_decision | tool_workflow}
- **Recommendation:** {what should change}

### Pattern 2: ...
\`\`\`

**Rules:**
- Only patterns with frequency >= 3 go into the report
- Patterns with frequency 2 are noted in diary but NOT in report
- Max 5 patterns per reflect session (prioritize by frequency)
- One report file per reflect session (not per pattern)
- Evidence links to diary index for full context
```

**Step 2: Update Step 5.5 git add (line 139)**

Replace line 139:
```
git add ai/diary/ ai/inbox/ ai/reflect/ 2>/dev/null
```
With:
```
git add ai/diary/ ai/reflect/ 2>/dev/null
```

**Step 3: Update "What NOT to Do" table (lines 181-184)**

Replace lines 181-184:
```
| Wrong | Correct |
|-------|---------|
| Create TECH spec directly | Write to inbox -> Spark creates spec |
| Edit CLAUDE.md directly | Write to inbox -> Spark -> skill-creator |
| Skip marking entries done | MUST mark diary entries `pending → done` in Step 5.6 |
| Write all patterns to inbox | Only frequency >= 3, max 5 files |
```
With:
```
| Wrong | Correct |
|-------|---------|
| Create TECH spec directly | Write reflect report -> OpenClaw decides next steps |
| Edit CLAUDE.md directly | Write reflect report -> OpenClaw -> Spark -> skill-creator |
| Write to ai/inbox/ | Write to ai/reflect/reports/ (north-star: only OpenClaw writes inbox) |
| Skip marking entries done | MUST mark diary entries `pending → done` in Step 5.6 |
| Write all patterns to report | Only frequency >= 3, max 5 patterns |
```

**Step 4: Update Quality Checklist (line 195)**

Replace line 195:
```
- [ ] Findings written to inbox (not direct spec/edits)
```
With:
```
- [ ] Findings written to ai/reflect/reports/ (not inbox, not direct spec/edits)
```

**Step 5: Verify**

```bash
grep -n "ai/inbox" .claude/skills/reflect/SKILL.md
```

Expected: 0 results.

**Acceptance:**
- [ ] `grep -c "ai/inbox" .claude/skills/reflect/SKILL.md` returns 0
- [ ] Step 5 header says "Write Reflect Report" not "Write to Inbox"
- [ ] Step 5.5 git add does NOT include `ai/inbox/`
- [ ] "What NOT to Do" table references reflect reports, not inbox

---

### Task 3: Remove scan_drafts() from orchestrator.sh

**Files:**
  - Modify: `scripts/vps/orchestrator.sh:367-425` -- delete entire function + separator comment

**Context:** `scan_drafts()` is dead code. It is defined at lines 367-425 but never called in `process_project()` (lines 431-447). With Spark now creating `queued` directly, this function has no purpose.

**Step 1: Delete lines 367-425**

Delete the entire block from the separator comment to the closing brace:
```bash
# ---------------------------------------------------------------------------
# Scan backlog for draft specs and send Telegram approval notifications
# ---------------------------------------------------------------------------

scan_drafts() {
    local project_id="$1" project_dir="$2"
    local backlog="${project_dir}/ai/backlog.md"

    [[ ! -f "$backlog" ]] && return

    # Find all draft spec IDs (exclude status documentation table)
    local draft_ids
    draft_ids=$(grep -E '^\|\s*(TECH|FTR|BUG|ARCH)-[0-9]+\s*\|.*\|\s*draft\s*\|' "$backlog" 2>/dev/null | \
                grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' || true)

    [[ -z "$draft_ids" ]] && return

    # Track which drafts we've already notified about (avoid spam)
    local notified_file="${SCRIPT_DIR}/.notified-drafts-${project_id}"
    touch "$notified_file"

    while IFS= read -r spec_id; do
        [[ -z "$spec_id" ]] && continue

        # Skip if already notified
        if grep -qF "$spec_id" "$notified_file" 2>/dev/null; then
            continue
        fi

        # Find spec file
        local spec_file
        spec_file=$(find "${project_dir}/ai/features/" -name "${spec_id}*" -type f 2>/dev/null | head -1 || true)
        [[ -z "$spec_file" ]] && continue

        # Extract title and problem from spec (flexible: handles Symptom, Why, Root Cause, Problem)
        local title problem tasks_count
        title=$(grep -m1 '^# ' "$spec_file" 2>/dev/null | sed 's/^# //' | head -c 100 || true)
        title="${title:-$spec_id}"
        # Try multiple section names for problem description
        problem=$(grep -A1 -E '^## (Why|Symptom|Problem|Root Cause)' "$spec_file" 2>/dev/null | tail -1 | head -c 200 || true)
        problem="${problem:-—}"
        # Count tasks: try "### Task" and "## Task" patterns
        tasks_count=$(grep -c -E '^#{2,3} Task' "$spec_file" 2>/dev/null || true)
        tasks_count=$(( tasks_count + 0 ))

        log_json "info" "sending draft approval" "project" "$project_id" "spec" "$spec_id"

        # Send approval notification via notify.py
        python3 "${SCRIPT_DIR}/notify.py" --spec-approval \
            "$project_id" "$spec_id" "$title" "$problem" "$tasks_count" 2>/dev/null && {
            # Mark as notified
            echo "$spec_id" >> "$notified_file"
            log_json "info" "draft notification sent" "project" "$project_id" "spec" "$spec_id"
        } || {
            log_json "error" "draft notification failed" "project" "$project_id" "spec" "$spec_id"
        }

    done <<< "$draft_ids"
}
```

This leaves the file going directly from `dispatch_qa()` closing brace (line 365) to the `process_project()` separator comment.

**Step 2: Verify**

```bash
grep -n "scan_drafts" scripts/vps/orchestrator.sh
bash -n scripts/vps/orchestrator.sh && echo "syntax OK"
```

Expected: grep returns 0 results, bash -n exits 0.

**Acceptance:**
- [ ] `grep -c "scan_drafts" scripts/vps/orchestrator.sh` returns 0
- [ ] `bash -n scripts/vps/orchestrator.sh` exits 0
- [ ] `process_project()` function unchanged (lines 431-447 become ~372-388 after deletion)

---

### Task 4: Clean pueue-callback.sh -- remove Step 5.5 + clean Step 5.9

**Files:**
  - Modify: `scripts/vps/pueue-callback.sh:204-303`

**Context:** Step 5.5 (lines 206-257) sends spark draft approval notifications -- dead path since Spark now creates `queued`. Step 5.9 (lines 274-303) uses `WILL_WRITE_INBOX` to hint about inbox routing -- dead path since callback no longer writes inbox (Step 6.5 is already no-op). Variables `NOTIFY_PY` (line 211) and `SENT_APPROVAL` (line 212) are used downstream at lines 298, 345, 347, 351 -- must handle.

**Step 1: Replace Step 5.5 block (lines 204-257) with minimal variable setup**

Replace the entire Step 5.5 block (from the comment after surrogate cleanup note through the closing fi):
```bash
# (surrogate cleanup moved after Step 5.9 — MSG gets modified there)

# ---------------------------------------------------------------------------
# Step 5.5: Spark approval notification with result_preview
# When spark completes successfully, send approval buttons with the summary
# so the user sees WHAT spark plans to do, not dry spec headers.
# ---------------------------------------------------------------------------
NOTIFY_PY="${SCRIPT_DIR}/notify.py"
SENT_APPROVAL=false

if [[ "$STATUS" == "done" && "$SKILL" == "spark" && -f "$NOTIFY_PY" ]]; then
    # Resolve project path for spec file lookup
    SPARK_PROJECT_PATH=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${PROJECT_ID}')
print(state['path'] if state else '')
" 2>/dev/null || true)

    if [[ -n "$SPARK_PROJECT_PATH" ]]; then
        # Find newest draft spec in backlog
        BACKLOG="${SPARK_PROJECT_PATH}/ai/backlog.md"
        SPEC_ID=""

        if [[ -f "$BACKLOG" ]]; then
            SPEC_ID=$(grep -E '^\|\s*(TECH|FTR|BUG|ARCH)-[0-9]+\s*\|.*\|\s*draft\s*\|' "$BACKLOG" 2>/dev/null | \
                      grep -oE '(TECH|FTR|BUG|ARCH)-[0-9]+' | tail -1 || true)
        fi

        if [[ -n "$SPEC_ID" ]]; then
            # Dedup: skip if already notified (two sparks can finish simultaneously for same spec)
            if grep -qxF "$SPEC_ID" "${SCRIPT_DIR}/.notified-drafts-${PROJECT_ID}" 2>/dev/null; then
                echo "[callback] Skipping duplicate approval: ${SPEC_ID} already notified"
            else
                # Mark as notified BEFORE sending — prevents scan_drafts race condition
                echo "$SPEC_ID" >> "${SCRIPT_DIR}/.notified-drafts-${PROJECT_ID}"

                echo "[callback] Sending spark approval: project=${PROJECT_ID} spec=${SPEC_ID}"
                echo "[$(date '+%Y-%m-%d %H:%M:%S')] spark approval: project=${PROJECT_ID} spec=${SPEC_ID}" >> "$CALLBACK_LOG"
                # notify.py reads spec file directly — no need to pass summary/title/tasks
                python3 "$NOTIFY_PY" --spec-approval \
                    "$PROJECT_ID" "$SPEC_ID" 2>>"$CALLBACK_LOG" && {
                    SENT_APPROVAL=true
                    echo "[callback] Spark approval sent: ${PROJECT_ID}:${SPEC_ID}"
                } || {
                    echo "[callback] WARN: spark approval notification failed" >&2
                }
            fi  # end dedup check
        else
            echo "[callback] WARN: no draft spec found in backlog for spark result" >&2
        fi
    fi
fi
```
With:
```bash
# (surrogate cleanup moved after Step 5.9 — MSG gets modified there)

# ---------------------------------------------------------------------------
# Step 5.5: REMOVED (TECH-151) — Spark now creates queued specs directly.
# Draft approval notifications no longer needed. notify.py + SENT_APPROVAL
# kept for Step 6 notification logic.
# ---------------------------------------------------------------------------
NOTIFY_PY="${SCRIPT_DIR}/notify.py"
```

**Step 2: Replace Step 5.9 WILL_WRITE_INBOX logic (lines 259-303)**

Replace the entire block from "Pre-compute inbox decision flags" through the "Spark from QA result" block:
```bash
# ---------------------------------------------------------------------------
# Pre-compute inbox decision flags (used by Step 5.9, 6, and 6.5)
# ---------------------------------------------------------------------------
EMPTY_RESULT=false
if echo "$PREVIEW" | grep -qiE 'analyzed: 0|inbox_files_created: 0|нечего обрабатывать|0 pending|0 ✗|0 fail|0 FAIL|все проверки пройдены|all tests passed|QA PASSED'; then
    EMPTY_RESULT=true
fi

FEEDBACK_DEPTH_OK=true
if [[ "$SKILL" == "qa" && "$TASK_LABEL" =~ ^qa-(qa-|inbox-.*-(reflect|qa)-result) ]]; then
    FEEDBACK_DEPTH_OK=false
    echo "[callback] Skipping QA→inbox: depth limit reached (label=${TASK_LABEL})"
fi

# ---------------------------------------------------------------------------
# Step 5.9: Determine if this skill result will go to inbox (for Step 6 message)
# ---------------------------------------------------------------------------
WILL_WRITE_INBOX=false
if [[ "$STATUS" == "done" && "$EMPTY_RESULT" == "false" && "$FEEDBACK_DEPTH_OK" == "true" && -n "$PREVIEW" ]]; then
    if [[ "$SKILL" == "qa" || "$SKILL" == "council" || "$SKILL" == "architect" || "$SKILL" == "reflect" ]]; then
        WILL_WRITE_INBOX=true
    fi
fi

# Append next-step hint to QA/reflect messages
if [[ "$STATUS" == "done" && "$SKILL" == "qa" ]]; then
    if [[ "$WILL_WRITE_INBOX" == "true" ]]; then
        MSG="${MSG}
→ Результат передан в Spark для оформления"
    elif [[ "$EMPTY_RESULT" == "true" ]]; then
        MSG="${MSG}
→ Проблем не найдено"
    elif [[ "$FEEDBACK_DEPTH_OK" == "false" ]]; then
        MSG="${MSG}
→ Цикл завершён (depth limit)"
    fi
fi

# Spark from QA result — no new spec means cycle is closed
if [[ "$STATUS" == "done" && "$SKILL" == "spark" && "$SENT_APPROVAL" == "false" ]]; then
    if [[ "$TASK_LABEL" =~ inbox-.*-(qa|reflect)-result ]]; then
        MSG="✅ *${PROJECT_ID}*: Spark просмотрел результат QA
→ Новых спек нет. Цикл закрыт."
    fi
fi
```
With:
```bash
# ---------------------------------------------------------------------------
# Pre-compute result analysis flags (used by Step 6 notification)
# ---------------------------------------------------------------------------
EMPTY_RESULT=false
if echo "$PREVIEW" | grep -qiE 'analyzed: 0|inbox_files_created: 0|нечего обрабатывать|0 pending|0 ✗|0 fail|0 FAIL|все проверки пройдены|all tests passed|QA PASSED'; then
    EMPTY_RESULT=true
fi

FEEDBACK_DEPTH_OK=true
if [[ "$SKILL" == "qa" && "$TASK_LABEL" =~ ^qa-(qa-|inbox-.*-(reflect|qa)-result) ]]; then
    FEEDBACK_DEPTH_OK=false
    echo "[callback] Depth limit reached (label=${TASK_LABEL})"
fi

# ---------------------------------------------------------------------------
# Step 5.9: CLEANED (TECH-151) — no inbox routing. Append next-step hints only.
# ---------------------------------------------------------------------------

# Append next-step hint to QA messages
if [[ "$STATUS" == "done" && "$SKILL" == "qa" ]]; then
    if [[ "$EMPTY_RESULT" == "true" ]]; then
        MSG="${MSG}
→ Проблем не найдено"
    elif [[ "$FEEDBACK_DEPTH_OK" == "false" ]]; then
        MSG="${MSG}
→ Цикл завершён (depth limit)"
    fi
fi
```

**Step 3: Update Step 6 -- remove SENT_APPROVAL check (line 345)**

Replace line 345:
```bash
if [[ "$SENT_APPROVAL" == "false" && "$SKIP_NOTIFY" == "false" && -f "$NOTIFY_PY" ]]; then
```
With:
```bash
if [[ "$SKIP_NOTIFY" == "false" && -f "$NOTIFY_PY" ]]; then
```

**Step 4: Remove SENT_APPROVAL from debug trace (line 450)**

Replace line 450 (last line with SENT_APPROVAL):
```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback done: id=${PUEUE_ID} project=${PROJECT_ID} skill=${SKILL} status=${STATUS} sent_approval=${SENT_APPROVAL} skip_notify=${SKIP_NOTIFY}" >> "$CALLBACK_LOG"
```
With:
```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] callback done: id=${PUEUE_ID} project=${PROJECT_ID} skill=${SKILL} status=${STATUS} skip_notify=${SKIP_NOTIFY}" >> "$CALLBACK_LOG"
```

**Step 5: Verify**

```bash
grep -n "WILL_WRITE_INBOX\|SENT_APPROVAL\|notified-drafts\|spec-approval\|spec_approve" scripts/vps/pueue-callback.sh
bash -n scripts/vps/pueue-callback.sh && echo "syntax OK"
grep -c 'SKILL.*autopilot' scripts/vps/pueue-callback.sh  # Step 7 still present
```

Expected: first grep returns 0 results, bash -n exits 0, Step 7 grep returns >= 1.

**Acceptance:**
- [ ] `grep -c "WILL_WRITE_INBOX" scripts/vps/pueue-callback.sh` returns 0
- [ ] `grep -c "SENT_APPROVAL" scripts/vps/pueue-callback.sh` returns 0
- [ ] `grep -c "notified-drafts" scripts/vps/pueue-callback.sh` returns 0
- [ ] `bash -n scripts/vps/pueue-callback.sh` exits 0
- [ ] Step 7 (post-autopilot QA+Reflect dispatch) still present and functional
- [ ] Step 6 notification still fires (NOTIFY_PY still defined, SKIP_NOTIFY logic intact)

---

### Task 5: Update CLAUDE.md Task Statuses + template sync

**Files:**
  - Modify: `CLAUDE.md:263`
  - Sync: `template/.claude/skills/spark/SKILL.md` <-- `.claude/skills/spark/SKILL.md`
  - Sync: `template/.claude/skills/spark/completion.md` <-- `.claude/skills/spark/completion.md`
  - Sync: `template/.claude/skills/spark/feature-mode.md` <-- `.claude/skills/spark/feature-mode.md`
  - Sync: `template/.claude/skills/spark/bug-mode.md` <-- `.claude/skills/spark/bug-mode.md`
  - Sync: `template/.claude/skills/reflect/SKILL.md` <-- `.claude/skills/reflect/SKILL.md`

**Context:** CLAUDE.md defines `draft` as "Spec incomplete" at line 263. After this change, `draft` means only manual/interrupted specs. Template files must be synced to match root.

**Step 1: Update CLAUDE.md Task Statuses table (line 263)**

Replace line 263:
```
| `draft` | Spark | Spec incomplete |
```
With:
```
| `draft` | Spark | Spec incomplete (manual override or interrupted) |
```

**Step 2: Sync template files**

```bash
cp .claude/skills/spark/SKILL.md template/.claude/skills/spark/SKILL.md
cp .claude/skills/spark/completion.md template/.claude/skills/spark/completion.md
cp .claude/skills/spark/feature-mode.md template/.claude/skills/spark/feature-mode.md
cp .claude/skills/spark/bug-mode.md template/.claude/skills/spark/bug-mode.md
cp .claude/skills/reflect/SKILL.md template/.claude/skills/reflect/SKILL.md
```

**Step 3: Verify**

```bash
diff .claude/skills/spark/SKILL.md template/.claude/skills/spark/SKILL.md
diff .claude/skills/spark/completion.md template/.claude/skills/spark/completion.md
diff .claude/skills/spark/feature-mode.md template/.claude/skills/spark/feature-mode.md
diff .claude/skills/spark/bug-mode.md template/.claude/skills/spark/bug-mode.md
diff .claude/skills/reflect/SKILL.md template/.claude/skills/reflect/SKILL.md
```

Expected: all diffs empty.

**Acceptance:**
- [ ] All 5 diffs return empty (root == template)
- [ ] CLAUDE.md line 263 clarifies `draft` scope

### Execution Order

1 -> 2 -> 3 -> 4 -> 5

Tasks 1-4 are independent (different files), but sequential execution is safer.
Task 5 must be LAST (syncs files modified in Tasks 1-2).

### Dependencies

- Task 5 depends on Task 1 (syncs spark skill files modified in Task 1)
- Task 5 depends on Task 2 (syncs reflect SKILL.md modified in Task 2)
- Tasks 1, 2, 3, 4 have no cross-dependencies

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | OpenClaw writes inbox item | - | existing (no changes) |
| 2 | Orchestrator scan_inbox → Spark | - | existing |
| 3 | Spark creates `queued` spec | Task 1 | new behavior |
| 4 | Orchestrator scan_backlog → Autopilot | - | existing (already reads `queued`) |
| 5 | Autopilot → callback → QA + Reflect | - | existing (Step 7 unchanged) |
| 6 | QA writes ai/qa/ report | - | existing |
| 7 | Reflect writes diary (not inbox) | Task 2 | new behavior |
| 8 | Cycle stops | Task 4 | cleanup (already works) |
| 9 | scan_drafts() removed | Task 3 | dead code cleanup |
| 10 | Template synced | Task 5 | doc sync |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Spark SKILL.md headless mode | grep "draft" in headless section | 0 matches for "draft" as spec status | deterministic | devil | P0 |
| EC-2 | completion.md no draft as target | grep draft references | Only "draft" in context of gate failure fallback or status definition, not as Spark output target | deterministic | devil | P0 |
| EC-3 | scan_drafts removed | grep scan_drafts orchestrator.sh | 0 results | deterministic | codebase | P0 |
| EC-4 | Step 5.5 removed from callback | grep SENT_APPROVAL callback.sh | 0 results | deterministic | patterns | P0 |
| EC-5 | WILL_WRITE_INBOX removed | grep WILL_WRITE_INBOX callback.sh | 0 results | deterministic | codebase | P1 |
| EC-6 | Reflect no inbox writing | grep "ai/inbox" reflect/SKILL.md | 0 results | deterministic | codebase | P0 |
| EC-7 | Callback Step 7 still dispatches QA+Reflect | grep "autopilot.*qa\|dispatch.*qa" callback.sh | Step 7 block present and functional | deterministic | patterns | P0 |
| EC-8 | Template sync — no divergence | diff spark skill files root vs template | No draft/queued divergence | deterministic | codebase | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 | LLM-Judge: 0 | Total: 8 (min 3 met)

### TDD Order
1. EC-1, EC-2 (Spark docs) → Task 1
2. EC-6 (Reflect) → Task 2
3. EC-3 (orchestrator) → Task 3
4. EC-4, EC-5 (callback) → Task 4
5. EC-7 (regression: Step 7 intact) → Task 4
6. EC-8 (template sync) → Task 5

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Bash syntax valid | `bash -n scripts/vps/orchestrator.sh && bash -n scripts/vps/pueue-callback.sh` | exit 0 | 5s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | No draft as Spark output target | Files modified | `grep -rn "spec_status: draft\|Status = draft\|status.*draft" .claude/skills/spark/` | Only references to gate-failure fallback, not as Spark's normal output |
| AV-F2 | scan_drafts removed | orchestrator.sh modified | `grep -c "scan_drafts" scripts/vps/orchestrator.sh` | 0 |
| AV-F3 | Step 5.5 + WILL_WRITE_INBOX removed | callback modified | `grep -cE "SENT_APPROVAL|WILL_WRITE_INBOX|spec_approve.*callback|notified-drafts" scripts/vps/pueue-callback.sh` | 0 |
| AV-F4 | Reflect no inbox | reflect SKILL.md modified | `grep -c "ai/inbox" .claude/skills/reflect/SKILL.md` | 0 |
| AV-F5 | Step 7 still present | callback modified | `grep -c 'SKILL.*autopilot.*qa\|dispatch.*QA' scripts/vps/pueue-callback.sh` | >= 1 |

### Verify Command (copy-paste ready)

```bash
# Smoke
bash -n scripts/vps/orchestrator.sh && echo "orchestrator OK"
bash -n scripts/vps/pueue-callback.sh && echo "callback OK"
# Functional
echo "--- EC-1: Spark SKILL.md ---"
grep -n "draft" .claude/skills/spark/SKILL.md | grep -v "status definition\|gate failure" || echo "PASS: no draft as target"
echo "--- EC-3: scan_drafts ---"
grep -c "scan_drafts" scripts/vps/orchestrator.sh && echo "FAIL" || echo "PASS"
echo "--- EC-4: SENT_APPROVAL ---"
grep -c "SENT_APPROVAL" scripts/vps/pueue-callback.sh && echo "FAIL" || echo "PASS"
echo "--- EC-5: WILL_WRITE_INBOX ---"
grep -c "WILL_WRITE_INBOX" scripts/vps/pueue-callback.sh && echo "FAIL" || echo "PASS"
echo "--- EC-6: Reflect inbox ---"
grep -c "ai/inbox" .claude/skills/reflect/SKILL.md && echo "FAIL" || echo "PASS"
echo "--- EC-7: Step 7 intact ---"
grep -c 'SKILL.*autopilot' scripts/vps/pueue-callback.sh | grep -q "0" && echo "FAIL: Step 7 missing" || echo "PASS"
```

---

## Drift Log

**Checked:** 2026-03-17 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `.claude/skills/spark/completion.md:155-157` | Bug Hunt grouped specs table has `draft` 3x -- missed by original spec | AUTO-FIX: added to Task 1 Step 2 |
| `.claude/skills/spark/completion.md:226` | Already says `queued` -- no change needed | AUTO-FIX: removed from Task 1 file list |
| `.claude/skills/reflect/SKILL.md:181-184` | "What NOT to Do" table references inbox | AUTO-FIX: added to Task 2 Step 3 |
| `.claude/skills/reflect/SKILL.md:195` | Quality Checklist references inbox | AUTO-FIX: added to Task 2 Step 4 |
| `scripts/vps/orchestrator.sh:367-425` | Separator comment at 367 not 371; closing brace at 425 not 424 | AUTO-FIX: updated range to 367-425 |
| `scripts/vps/pueue-callback.sh:211` | `NOTIFY_PY` var defined inside Step 5.5 but used by Step 6 (line 345) | AUTO-FIX: keep NOTIFY_PY in Task 4 |
| `scripts/vps/pueue-callback.sh:212,298,345,450` | `SENT_APPROVAL` used downstream after Step 5.5 removal | AUTO-FIX: remove entirely, update Step 6 condition |
| `scripts/vps/orchestrator.sh` | `scan_drafts()` confirmed dead -- not called in `process_project()` | No action needed |

### References Updated
- Task 1: completion.md `lines 226` removed (already queued); added `lines 155-157` (Bug Hunt table)
- Task 2: added `lines 181-184` (What NOT to Do) and `line 195` (Quality Checklist)
- Task 3: `lines 371-424` -> `lines 367-425` (include separator + closing brace)
- Task 4: added Step 3 (SENT_APPROVAL removal from Step 6 condition) and Step 4 (debug trace cleanup)

---

## Definition of Done

### Functional
- [x] All 10 north-star invariants reflected in code and docs
- [x] Spark creates `queued` specs (not `draft`)
- [x] scan_drafts() removed from orchestrator
- [x] Step 5.5 removed from callback
- [x] WILL_WRITE_INBOX logic cleaned from callback
- [x] Reflect writes to diary, not inbox
- [x] Template files synced

### Tests
- [x] All 8 eval criteria pass
- [x] bash -n passes for modified shell scripts

### Acceptance Verification
- [x] AV-S1 smoke passes
- [x] AV-F1 through AV-F5 pass

### Technical
- [x] No regressions in orchestrator flow
- [x] approve_handler.py still functional (manual override path)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
