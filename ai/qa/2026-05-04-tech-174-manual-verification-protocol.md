# QA Report: TECH-174 — Manual Spec Verification Protocol

**Date:** 2026-05-04
**Environment:** local repo `/home/dld/projects/dld` @ `e4efd50` (develop)
**Trigger:** `/qa TECH-174` — verify spec was actually delivered
**Tooling:** dogfooded `scripts/vps/spec_verify.py` + manual checks (CLI/Bash, no UI)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 7     | 4    | 3    | 0       |

**Verdict:** HARD-FAIL. Спека помечена как реализованная, но **Task 1** (главный артефакт — protocol document) и **Task 5** (ссылка из `/qa` skill) **не выполнены**. EC-4 не достигнут. CLI-инструменты (Tasks 2–4) работают.

## Failures

### F1: Protocol document отсутствует (Task 1, EC-4)

**Severity:** Critical
**Reproducibility:** Always
**Expected:** `~/.claude/projects/-root/memory/spec-verification-protocol.md` существует, содержит заголовки `## Step 1` … `## Step 7` и хотя бы один ` ```bash ` блок (per Implementation Plan Task 1).
**Actual:** Файла нет.

**Steps to reproduce:**
1. `test -f ~/.claude/projects/-root/memory/spec-verification-protocol.md && echo OK || echo MISSING`
2. Видим `MISSING`.
3. `pytest tests/integration/test_spec_verify.py::test_protocol_doc_has_seven_steps -v` → **SKIPPED** (не PASS — тест помечает себя skip когда файла нет, что и происходит).

**Evidence:**
- `spec_verify.py /home/dld/projects/dld TECH-174` → `MISS ~/.claude/projects/-root/memory/spec-verification-protocol.md`
- pytest output: `6 passed, 1 skipped` — `test_protocol_doc_has_seven_steps SKIPPED`
- Drift Log в спеке (line 122) сам признаёт: "Plan: CREATE in Task 1" — но Task 1 не выполнен.

**User impact:** Оператор (или агент в режиме `/qa`) не имеет того самого checklist, ради которого вся спека и заводилась. Главная цель TECH-174 — "превратить ручную работу в воспроизводимый чек-лист" — не достигнута. EC-4 ("Protocol .md имеет все 7 шагов + примеры команд") **fail**.

**Hint for developers:** Создать файл по шаблону из Implementation Plan Task 1 (lines 137–179 спеки). После этого `test_protocol_doc_has_seven_steps` перестанет быть skipped.

---

### F2: `/qa` skill не ссылается на протокол (Task 5)

**Severity:** Major
**Reproducibility:** Always
**Expected:** В `.claude/skills/qa/SKILL.md` есть секция "Spec Verification Protocol" со ссылками на `spec-verification-protocol.md`, `spec_verify.py`, `spec_operator.py` (per Task 5, lines 249–304).
**Actual:** Ноль упоминаний.

**Steps to reproduce:**
```
grep -nE 'spec-verification-protocol|spec_verify\.py|spec_operator\.py' .claude/skills/qa/SKILL.md
# → no output
```

**Evidence:** Я сейчас QA-аю эту самую спеку, и в моём промпте /qa skill **нет** секции про spec verification — пришлось читать спеку и собирать чеклист руками. Это в точности тот UX-провал, который Task 5 должен был закрыть.

**User impact:** Когда оператор пишет `/qa <SPEC_ID>` для проверки закрытой спеки, агент не знает, что есть готовая автоматизация (`spec_verify.py`) и checklist. Идёт по длинному пути.

---

### F3: Stale reference `operator.py` в спеке (allowed_files + Task 3 текст)

**Severity:** Minor
**Reproducibility:** Always
**Expected:** Спека ссылается на актуальный путь `scripts/vps/spec_operator.py`.
**Actual:** В `## Allowed Files` (line 84) и тексте Task 3 (line 94) фигурирует `scripts/vps/operator.py`. Файл переименован в `spec_operator.py` (commit 5e472cd, stdlib shadow fix), но спека не обновлена.

**Evidence:**
- `spec_verify.py /home/dld/projects/dld TECH-174` → `MISS scripts/vps/operator.py` (ложно-позитивный fail из-за stale spec text).
- Drift Log это признаёт (line 120) но fix не сделан.

**User impact:** Любой автоматический верификатор (включая сам `spec_verify.py`) будет помечать TECH-174 как HARD-FAIL даже после починки F1+F2, пока allowed_files не починят. Self-referential bug.

**Hint:** Заменить в спеке `operator.py` → `spec_operator.py` (2 места: allowed_files + Task 3 заголовок).

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | EC-1: `spec_verify` reports missing file | `test_spec_verify_reports_missing_file` PASS |
| 2 | EC-2: `spec_verify` OK when files+symbols present | `test_spec_verify_ok_when_files_and_symbols_present` PASS |
| 3 | EC-3: `spec_operator demote` через plumbing-commit не трогает working tree | `test_operator_demote_via_plumbing_does_not_touch_working_tree` PASS + `test_operator_force_done` + `test_operator_demote_unknown_spec_returns_3` PASS |
| 4 | CLI surface: `--help` обоих скриптов корректен (3 subcommands у operator: demote/force-done/reset-circuit) | `python3 scripts/vps/spec_operator.py --help` PASS |

## Recommendation

Демотнуть TECH-174 обратно в `queued`:

```bash
python3 scripts/vps/spec_operator.py demote dld TECH-174 \
  "Task 1 (protocol doc) and Task 5 (qa skill ref) not implemented; EC-4 fails; stale operator.py reference"
```

Затем создать `/spark` багфикс или просто доделать Task 1 + Task 5 + поправить stale references — это <50 LOC работы, R2.

Дополнительный самоприкол: `spec_verify` корректно поймал собственную незаконченную спеку → инструмент уже даёт пользу даже в недоделанном виде. Это серьёзный аргумент в пользу того, чтобы доделать Task 1 и Task 5.
