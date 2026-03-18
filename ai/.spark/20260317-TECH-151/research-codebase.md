# Codebase Research — TECH-151: Align Orchestrator with North-Star Flow

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `scan_backlog()` | scripts/vps/orchestrator.sh:192 | Finds first `queued` spec, submits to pueue | Keep as-is — already looks for `queued` only |
| `scan_inbox()` | scripts/vps/orchestrator.sh:163 | Reads `ai/inbox/*.md` with `Status: new` | Keep as-is |
| `dispatch_qa()` | scripts/vps/orchestrator.sh:330 | Checks `qa_pending` invariant, resets to idle if no task | Keep as invariant checker — callback already owns dispatch |
| `handle_spec_approve()` | scripts/vps/approve_handler.py:240 | draft → queued transition via Telegram button | Becomes dead path if draft is removed; can be repurposed |
| `handle_rework_comment()` | scripts/vps/approve_handler.py:292 | Writes rework inbox item for human-initiated rework | Keep — this IS legitimate OpenClaw-equivalent writing to inbox |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `scan_drafts()` dead code | scripts/vps/orchestrator.sh:371 | Sends Telegram approval notifications for draft specs | Dead — never called from `process_project()` |
| Step 5.9 WILL_WRITE_INBOX | scripts/vps/pueue-callback.sh:274 | Computes flag to decide if QA/Reflect result will go to inbox | Obsolete logic — north-star forbids it; flag still used for message text |
| Reflect → inbox | .claude/skills/reflect/SKILL.md:113 | Reflect writes findings to `ai/inbox/` directly | Violates north-star invariant 7: Reflect writes diary only |
| Bughunt → inbox | .claude/skills/bughunt/completion.md:59 | `git add ai/bughunt/ ai/inbox/` in commit command | Bughunt writes to inbox — needs review vs north-star |

**Recommendation:** `scan_drafts()` — remove entirely (dead code). `WILL_WRITE_INBOX` flag — the flag itself is no longer semantic after Step 6.5 was gutted but the messaging text still references it. Reflect's inbox-writing instructions — replace with diary-only output.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -r "scan_drafts\|draft.*status\|status.*draft" scripts/vps/ --include="*.sh" --include="*.py"
```

| File | Line | Usage |
|------|------|-------|
| scripts/vps/orchestrator.sh | 371 | `scan_drafts()` defined but **never called** from `process_project()` |
| scripts/vps/pueue-callback.sh | 225–254 | Step 5.5: searches backlog for `draft` spec after spark finishes, sends approval buttons |
| scripts/vps/pueue-callback.sh | 230 | `grep -E '.*\| draft \|'` — finds draft spec by regex |
| scripts/vps/approve_handler.py | 241 | `handle_spec_approve`: draft → queued transition |
| scripts/vps/approve_handler.py | 343 | `handle_spec_reject`: draft → rejected transition |
| scripts/vps/tests/test_approve_handler.py | 30, 44, 82–110 | Tests that create draft fixtures and verify transitions |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `.notified-drafts-{project_id}` | scripts/vps/ (state files) | Dedup file for draft notification; used by both callback Step 5.5 and `scan_drafts()` |
| `db.get_project_state()` | scripts/vps/db.py | Used in callback Step 5.5 to resolve project path |
| `notify.py --spec-approval` | scripts/vps/notify.py | Called by `scan_drafts()` and callback Step 5.5 to send Telegram buttons |
| `ai/backlog.md` | project repos | Draft spec regex match; orchestrator depends on status field in backlog |
| `ai/diary/index.md` | project repos | Reflect reads `pending` entries; callback checks `PENDING_COUNT` to decide reflect dispatch |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "draft" scripts/vps/ .claude/skills/spark/ CLAUDE.md --include="*.sh" --include="*.py" --include="*.md"
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/orchestrator.sh | 371–424 | `scan_drafts()` function — dead code |
| scripts/vps/pueue-callback.sh | 214–256 | Step 5.5: spark completion → find draft → send approval |
| scripts/vps/pueue-callback.sh | 230 | `grep` for `\| draft \|` in backlog |
| scripts/vps/approve_handler.py | 241 | `handle_spec_approve`: "draft → queued" docstring |
| scripts/vps/approve_handler.py | 343 | `handle_spec_reject`: "draft → rejected" docstring |
| .claude/skills/spark/SKILL.md | 59, 63 | "Create spec in `draft` status (orchestrator handles approval via Telegram)" |
| .claude/skills/spark/SKILL.md | 43–44 | *(partially correct)* Key point says `queued` directly — but lines 59, 63 contradict |
| .claude/skills/spark/completion.md | 45 | Checklist item 5: "Status = draft — spec awaits human approval via Telegram!" |
| .claude/skills/spark/completion.md | 82–83 | "Setting spec file: Status → draft" verbalization |
| .claude/skills/spark/completion.md | 93, 99–101 | Backlog example shows `draft`; status table says `draft` always |
| .claude/skills/spark/completion.md | 260 | `spec_status: draft  # always draft — human approves via Telegram` |
| .claude/skills/spark/feature-mode.md | 643 | "spec stays `draft`" on gate failure |
| .claude/skills/spark/bug-mode.md | 197–198, 211 | Checklist: "status: draft"; return format: `spec_status: draft` |
| CLAUDE.md | 263 | Task Statuses table: "`draft` | Spark | Spec incomplete" |

```bash
grep -rn "ai/inbox" .claude/skills/ --include="*.md"
```

| File | Line | Context |
|------|------|---------|
| .claude/skills/reflect/SKILL.md | 113 | Reflect writes findings to `ai/inbox/{timestamp}-reflect-{N}.md` |
| .claude/skills/reflect/SKILL.md | 139 | `git add ai/diary/ ai/inbox/ ai/reflect/` in commit step |
| .claude/skills/bughunt/completion.md | 59 | `git add ai/bughunt/ ai/inbox/` |

```bash
grep -rn "WILL_WRITE_INBOX\|inbox_files_created\|Step 5.9\|Step 6.5" scripts/vps/pueue-callback.sh
```

| File | Line | Context |
|------|------|---------|
| scripts/vps/pueue-callback.sh | 260–281 | Pre-compute `WILL_WRITE_INBOX=true` for qa/council/architect/reflect |
| scripts/vps/pueue-callback.sh | 274–281 | Step 5.9: sets flag, but Step 6.5 comment says "no automatic feedback → inbox" — contradiction |
| scripts/vps/pueue-callback.sh | 284–295 | QA message appends "→ Результат передан в Spark для оформления" if `WILL_WRITE_INBOX=true` |
| scripts/vps/pueue-callback.sh | 356–360 | Step 6.5 comment says north-star, but WILL_WRITE_INBOX flag and messaging still reference old flow |

### Step 4: CHECKLIST — Mandatory folders

- [x] `scripts/vps/tests/` — 1 test file found: `test_approve_handler.py` (tests draft → queued flow)
- [ ] `db/migrations/**` — N/A (SQLite schema in `schema.sql`, no migration files)
- [ ] `ai/glossary/**` — not present in this project

### Step 5: DUAL SYSTEM check

Changing spec status from `draft` → `queued` directly affects TWO readers:

1. **`scan_backlog()` in orchestrator.sh** — reads `queued` from `ai/backlog.md` → already correct
2. **`pueue-callback.sh` Step 5.5** — reads `draft` from backlog after Spark completes → becomes dead path if Spark creates `queued` directly
3. **`approve_handler.py`** — `handle_spec_approve()` transitions `draft → queued` → becomes redundant path for normal flow
4. **`.notified-drafts-{project_id}` state files** — dedup files for draft notifications; if `scan_drafts()` and callback Step 5.5 are removed, these files become orphaned state

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| scripts/vps/orchestrator.sh | 485 | Main daemon loop | modify — remove `scan_drafts()` dead code |
| scripts/vps/pueue-callback.sh | 450 | Pueue completion callback | modify — remove Step 5.5 (draft approval), clean Step 5.9 WILL_WRITE_INBOX messaging |
| scripts/vps/approve_handler.py | 360 | Telegram approval buttons | modify — `handle_spec_approve()` can remain for manual override, but Step 5.5 trigger path dies |
| .claude/skills/spark/SKILL.md | 168 | Spark skill entry point | modify — remove lines 59, 63 (draft in headless/interactive mode) |
| .claude/skills/spark/completion.md | 262 | Spark completion checklist | modify — replace all `draft` references with `queued`, update checklist item 5, return format |
| .claude/skills/spark/feature-mode.md | 735 | Feature mode phases | modify — line 643: "spec stays `draft`" → "spec stays in current state" |
| .claude/skills/spark/bug-mode.md | 213 | Bug mode completion | modify — lines 197–198, 211: `draft` → `queued` |
| .claude/skills/reflect/SKILL.md | 212 | Reflect skill | modify — Step 5 (lines 107–140): replace inbox-writing with diary-only output |
| CLAUDE.md | 311 | Project rules | modify — Task Statuses table: clarify `draft` definition or remove as valid output of Spark |
| template/.claude/skills/spark/SKILL.md | ~168 | Template copy | modify — same changes as .claude/skills/spark/SKILL.md (template-sync rule) |
| template/.claude/skills/spark/completion.md | ~262 | Template copy | modify — same changes as .claude/skills/spark/completion.md |
| template/.claude/skills/spark/feature-mode.md | ~735 | Template copy | modify — same as feature-mode.md |
| template/.claude/skills/spark/bug-mode.md | ~213 | Template copy | modify — same as bug-mode.md |
| scripts/vps/tests/test_approve_handler.py | ~130 | Tests for approve_handler | modify — fixtures with `draft` status may need update if approval flow changes |

**Total:** 14 files, ~4,700 LOC affected

---

## Reuse Opportunities

### Import (use as-is)
- `scan_backlog()` — already correct, reads `queued` only
- `scan_inbox()` — already correct, OpenClaw-only intake
- `dispatch_qa()` — invariant checker is fine; callback owns actual dispatch
- `handle_rework_comment()` in approve_handler.py — legitimate OpenClaw-style inbox write (human-initiated rework)

### Extend (modify in-place)
- `pueue-callback.sh` Step 5.5 — remove entirely (draft approval trigger); keep Step 7 (post-autopilot QA+Reflect dispatch)
- `pueue-callback.sh` Step 5.9 — remove `WILL_WRITE_INBOX` flag and messaging that references "→ Результат передан в Spark"
- `.claude/skills/reflect/SKILL.md` Step 5 — replace inbox-writing with diary artifact writing (durable file like `ai/reflect/{timestamp}-findings.md`)

### Pattern (copy structure, not code)
- `qa-loop.sh` QA report pattern — writes to `ai/qa/{timestamp}-{spec_id}.md` — use same durable-file approach for reflect output
- `scan_drafts()` dedup with `.notified-drafts-{project_id}` — pattern for avoiding notification spam; if removed, the state files can be cleaned from VPS

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- scripts/vps/orchestrator.sh scripts/vps/pueue-callback.sh scripts/vps/qa-loop.sh .claude/skills/spark/
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-17 | 3a27f82 | Ellevated | orchestrator: align north-star intake and reporting flow |
| 2026-03-16 | 9b79f7e | Ellevated | fix(BUG-121): stop duplicate post-autopilot tail dispatch |
| 2026-03-16 | 6f2cbd2 | Ellevated | fix(vps): informative approval messages + kill QA/reflect spam |
| — | ce9bae1 | Ellevated | fix(callback): add next-step hints to QA and Spark-from-QA notifications |
| — | 1ce52ee | Ellevated | fix(callback): informative notifications + suppress noise + depth limit |
| — | 2db370d | Ellevated | fix(orchestrator): reset qa_pending to idle when current_task is empty |
| — | 96489ed | Ellevated | fix(callback): markdown escape, dedup approval, skip night-reviewer, no double notify |
| — | 29d8d06 | Ellevated | feat(vps): QA→inbox loop, structured skill output, notification polish |

**Observation:** Commit 3a27f82 (сегодня) уже начал alignment — добавил `orchestrator-final-state.md`, частично обновил Spark skills. Но `scan_drafts()` в orchestrator.sh осталась как dead code (не вызывается из `process_project()`), а `completion.md` всё ещё содержит `spec_status: draft` с комментарием "always draft — human approves via Telegram" на строке 260, противоречащим строке 226 ("status `queued`"). Это незавершённое состояние.

---

## Findings Summary

### 1. `scan_drafts()` — dead code (orchestrator.sh:371–424)
Функция определена, но не вызывается из `process_project()` (строки 431–447). Единственный вызов в `pueue-callback.sh:239` это комментарий "prevents scan_drafts race condition" — само функцию там никто не вызывает. Функцию можно безопасно удалить вместе с `.notified-drafts-*` state-файлами на VPS.

### 2. Противоречие в `completion.md` (spark)
Строка 226: "Spec saved with status `queued`"
Строка 260: `spec_status: draft  # always draft — human approves via Telegram`
Строки 45, 82–83, 93, 99–101: везде `draft`.
**Вердикт:** Документ внутренне противоречив. Нужно выбрать `queued` везде и убрать approval-flow упоминания.

### 3. `pueue-callback.sh` Step 5.5 — триггер approval через Telegram после Spark
Строки 214–256: когда Spark завершается успешно, callback ищет в backlog `draft`-спеку и шлёт кнопки approve/reject. Если Spark создаёт `queued` напрямую — этот блок не найдёт ничего и станет no-op. Можно удалить.

### 4. `pueue-callback.sh` Step 5.9 — `WILL_WRITE_INBOX` флаг
Строки 274–295: флаг `WILL_WRITE_INBOX` для qa/council/architect/reflect. Step 6.5 (строки 356–360) уже имеет правильный комментарий ("no automatic feedback → inbox"), но флаг и messaging "→ Результат передан в Spark для оформления" (строка 287) остались из старого flow. Нужно убрать флаг и строку-hint.

### 5. `reflect/SKILL.md` — Step 5 пишет в `ai/inbox/`
Строки 107–140 в reflect SKILL.md: Reflect пишет `ai/inbox/{timestamp}-reflect-{N}.md`. Это нарушает инвариант 7 north-star ("Reflect writes diary notes, not inbox items"). Нужно заменить на дurable-file в `ai/reflect/` или diary.

### 6. `SKILL.md` (spark) — строки 59, 63
Headless mode (строка 59) и interactive mode (строка 63) оба создают spec в `draft` status. Строки 43–44 (Key point) уже корректны — говорят `queued`. Строки 59, 63 нужно обновить.

---

## Risks

1. **Risk:** `approve_handler.py` имеет `handle_spec_approve()` (draft → queued), которая нужна для ручного override через Telegram.
   **Impact:** Если убрать draft совсем — функция потеряет смысл, но может использоваться для новых кейсов.
   **Mitigation:** Оставить `handle_spec_approve()` как ручной инструмент, просто обновить docstring. Удалить только автоматический trigger из callback Step 5.5.

2. **Risk:** `.notified-drafts-{project_id}` файлы на VPS (5 штук в git status).
   **Impact:** Orphaned state files если `scan_drafts()` удалена.
   **Mitigation:** Удалить вместе с функцией. Файлы не в git (в .gitignore или untracked).

3. **Risk:** `test_approve_handler.py` тестирует draft → queued transition.
   **Impact:** Если approve flow остаётся как ручной override — тесты валидны. Если draft status убирается полностью — тесты сломаются.
   **Mitigation:** Решить сначала политику: draft статус существует для bughunt grouped specs (они по-прежнему `draft` в примерах `completion.md:155–157`). Возможно, `draft` остаётся для bughunt, но не для normal spark flow.

4. **Risk:** `reflect/SKILL.md` Step 5.6 фиксирует diary entries как done — эта логика правильная.
   **Impact:** Замена inbox-writing на durable-file может потребовать нового формата выходного файла.
   **Mitigation:** Использовать паттерн `qa-loop.sh` — писать в `ai/reflect/{timestamp}-{task}.md`.
