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

## Implementation Plan

### Research Sources
- [Singular Update Queue (Martin Fowler)](https://martinfowler.com/articles/patterns-of-distributed-systems/singular-update-queue.html) — single-writer inbox pattern
- [Approvals for autonomous AI agents (Cordum)](https://cordum.io/blog/approvals-for-autonomous-workflows) — approval gate placement
- [6 Patterns for Production-Grade Pipelines (Wasowski)](https://medium.com/@wasowski.jarek/6-patterns-that-turned-my-pipeline-from-chaotic-to-production-grade-agentic-workflows-cdd45d2d314a) — immutable state machine, durable artifacts

### Task 1: Update Spark skill docs (draft → queued)
**Type:** code
**Files:**
  - modify: `.claude/skills/spark/SKILL.md` — lines 59, 63: draft → queued
  - modify: `.claude/skills/spark/completion.md` — lines 45, 82-88, 93-101, 226, 260: all draft → queued
  - modify: `.claude/skills/spark/feature-mode.md` — line 643: draft → queued
  - modify: `.claude/skills/spark/bug-mode.md` — lines 197-198, 211: draft → queued
**Acceptance:** `grep -rn "status.*draft\|draft.*status" .claude/skills/spark/` returns only "spec stays in current state" for gate failure (not "draft" as target status)

### Task 2: Update Reflect SKILL.md — inbox → diary
**Type:** code
**Files:**
  - modify: `.claude/skills/reflect/SKILL.md` — Step 5 (lines 106-141): replace inbox-writing with durable file in `ai/reflect/`
**Acceptance:** `grep -n "ai/inbox" .claude/skills/reflect/SKILL.md` returns 0 results. Step 5.5 git add no longer includes `ai/inbox/`.

### Task 3: Remove scan_drafts() from orchestrator.sh
**Type:** code
**Files:**
  - modify: `scripts/vps/orchestrator.sh` — delete scan_drafts() function (lines 371-424)
**Acceptance:** `grep -n "scan_drafts" scripts/vps/orchestrator.sh` returns 0 results

### Task 4: Clean pueue-callback.sh — remove Step 5.5 + clean Step 5.9
**Type:** code
**Files:**
  - modify: `scripts/vps/pueue-callback.sh` — delete Step 5.5 (lines 207-257), clean Step 5.9 WILL_WRITE_INBOX logic (lines 260-303)
**Acceptance:**
  - `grep -n "SENT_APPROVAL\|WILL_WRITE_INBOX\|spec_approve\|notified-drafts\|scan_drafts" scripts/vps/pueue-callback.sh` returns 0 for WILL_WRITE_INBOX and scan_drafts
  - SENT_APPROVAL variable removed entirely
  - Step 6 notification still fires for spark completion ("✅ Спека — готово")

### Task 5: Update CLAUDE.md Task Statuses + template sync
**Type:** code
**Files:**
  - modify: `CLAUDE.md` — Task Statuses table: clarify `draft` is only for manual/incomplete specs
  - modify: `template/.claude/skills/spark/SKILL.md` — sync from root
  - modify: `template/.claude/skills/spark/completion.md` — sync from root
  - modify: `template/.claude/skills/spark/feature-mode.md` — sync from root
  - modify: `template/.claude/skills/spark/bug-mode.md` — sync from root
  - modify: `template/.claude/skills/reflect/SKILL.md` — sync from root
**Acceptance:** `diff .claude/skills/spark/SKILL.md template/.claude/skills/spark/SKILL.md` shows no draft/queued divergence. CLAUDE.md statuses consistent.

### Execution Order
1 → 2 → 3 → 4 → 5

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
