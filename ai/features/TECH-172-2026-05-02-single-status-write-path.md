---
id: TECH-172
type: TECH
status: done
priority: P1
risk: R1
created: 2026-05-02
---

# TECH-172 — Single Status write path: callback is the only writer

**Status:** done
**Priority:** P1
**Risk:** R1

---

## Problem

Сейчас `**Status:**` в спеке могут писать минимум **два** агента:

1. **Autopilot** — `.claude/skills/autopilot/finishing.md:228-229`: `"Updating spec file: Status → done" [Edit spec]`. Прямой Edit-вызов на spec-файле.
2. **Callback** — `verify_status_sync` через `_apply_spec_status` + plumbing commit.

Это classic source of confusion:
- Autopilot пишет `done` в worktree, делает commit с этой правкой.
- Callback потом видит spec at HEAD = `done`, target=done — `STATUS_SYNC: ✓ already synced`. Не запускает guard.
- Если autopilot ошибся (написал `done` без реальной импл) — guard не сработает, потому что HEAD уже корректный.

**Гипотеза:** часть FTR-897/FTR-898 false-done могла пройти именно через этот путь — autopilot Edit'нул спеку, закоммитил вместе с doc-only-changes, callback увидел уже сделанное и не проверил.

---

## Goal

**Callback — единственный, кто пишет `Status:`.** Autopilot выкатывает только код + коммитит, статус не трогает.

1. **Autopilot finishing.md** — переписать: вместо `Edit spec → Status → done` инструкция:
   - Проверить что все Tasks done.
   - Закоммитить финальные правки кода.
   - **НЕ трогать `**Status:**` поле.**
   - В JSON-output финальный verdict: `"task_status": "complete" | "blocked" | "needs_review"`.
   - Callback по `pueue result + task_status` решает target и пишет статус.

2. **Pueue exit codes mapping** уточнить:
   - `Success` (rc=0) + `task_status=complete` → callback target=`done`.
   - `Success` (rc=0) + `task_status=blocked` → callback target=`blocked`.
   - `Failed` → target=`blocked`.

3. **Migration**: текущие in-flight спеки (`in_progress`) — autopilot всё ещё может их Edit'нуть (legacy behavior). Это OK, callback после them всё равно перепроверит через guard. Главное — будущие НЕ Edit'ат.

4. **Спарк-spec template** добавляет в раздел "Definition of Done":
   > **Не правьте `**Status:**` поле в этой спеке вручную. Callback автоматически выставит статус после успешного autopilot прогона на основе guard-проверки. Если нужно форсировать — используйте operator-mode override.**

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `.claude/skills/autopilot/finishing.md`
- `.claude/skills/autopilot/SKILL.md`
- `.claude/skills/autopilot/task-loop.md`
- `.claude/agents/coder.md`
- `template/.claude/skills/autopilot/finishing.md`
- `template/.claude/skills/autopilot/SKILL.md`
- `template/.claude/skills/autopilot/task-loop.md`
- `template/.claude/agents/coder.md`
- `scripts/vps/callback.py`
- `tests/integration/test_autopilot_no_status_write.py`
- `ai/features/TECH-172-2026-05-02-single-status-write-path.md`

---

## Tasks

1. **Autopilot finishing.md** — удалить инструкции Edit Status, добавить task_status JSON.
2. **Autopilot task-loop** — финальный шаг "выпускает task_status, не трогает Status:".
3. **callback.py** — расширить parsing pueue output: ищет `task_status` в agent JSON output (через `_parse_log_file`).
4. **Sync template/.claude** mirror.
5. **Migration note** в CLAUDE.md и в blueprint docs.
6. **Tests**: integration — autopilot run на synthetic spec, проверить что spec файл НЕ изменился по `**Status:**` строке после autopilot session.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | integration | Autopilot session не делает Edit на `**Status:**` строку spec файла |
| EC-2 | integration | Callback читает `task_status` из agent output и переводит в target |
| EC-3 | regression | Существующая работа autopilot (commit code, run tests) не сломана |
| EC-4 | deterministic | Если autopilot всё-таки написал `done` в спеку (legacy/error), callback всё равно прогоняет guard |

---

## Implementation Plan

### Task 1 — autopilot docs: stop writing Status

Files: `.claude/skills/autopilot/finishing.md`, `.claude/skills/autopilot/SKILL.md`, `.claude/skills/autopilot/task-loop.md`, `.claude/agents/autopilot/coder.md` (+ `template/.claude/...` mirrors).

- `finishing.md`: remove step "5. Update status → done / Edit spec" and the "Self-check" block with `[Edit spec]`. Replace with rule: autopilot MUST NOT modify `**Status:**` line or backlog status column. Final `result_preview` JSON must include `task_status: "complete" | "blocked" | "needs_review"`. Callback writes status.
- `SKILL.md`: update Notification Output Format to include `task_status`.
- `task-loop.md`: any Status-edit instruction → removed. Add note that closure emits `task_status`.
- `coder.md`: add forbidden clause — coder never Edits `**Status:**` in spec or backlog row.

Acceptance: grep on autopilot docs finds no Status-writing instruction.

### Task 2 — Mirror to template/

Sync identical changes from `.claude/...` to `template/.claude/...` for the four autopilot files.

### Task 3 — callback.py: parse `task_status`

- `_parse_log_file` returns `(skill, preview, task_status)`. Reads `data.get("task_status")` plus tries to parse `result_preview` JSON for `task_status` field.
- `extract_agent_output` returns triple. Internal returns updated.
- `main()` Step 4 unpacks triple. Step 7: `status=="done" and task_status=="blocked"` → target=`"blocked"`.

### Task 4 — Integration test

`tests/integration/test_autopilot_no_status_write.py` — grep-style assertions on autopilot doc files (no Status-write instruction; coder.md mentions forbidden Status edit + callback).

### Task 5 — Migration note in SKILL.md

Add brief 1–2 sentence note in autopilot SKILL.md (root + template): "Status field is written by callback only. Autopilot emits `task_status` in final JSON; never Edits `**Status:**`."

---

## Open Questions

- Что делать с уже задокументированными autopilot-сессиями где `Status:` уже в коммите? Migration-period 7 дней: callback толерантен к autopilot-mutations, но новые ones — нет.
- task_status из agent output — где именно его искать? Скорее всего `result_preview` финального message. Уточнить в spike.
