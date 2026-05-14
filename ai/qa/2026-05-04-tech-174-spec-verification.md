# QA Report: TECH-174 — Manual Spec Verification Protocol

**Date:** 2026-05-04
**Environment:** local repo `/home/dld/projects/dld` @ `e4efd50`
**Trigger:** `/qa TECH-174`
**Spec status:** `queued` (not yet `done`; last commit marks blocked)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 7     | 4    | 3    | 0       |

EC-3 (operator demote via plumbing-commit) и EC-4 (protocol с 7 шагами) **не выполнены** — Task 1 (создание protocol .md) и Task 5 (ссылка из `/qa` skill) пропущены. Это полностью соответствует тому, что spec в статусе `queued/blocked`, но как продукт оператора — TECH-174 пока недоставлен.

## Failures

### F1: Protocol document missing (EC-4)

**Severity:** Major
**Reproducibility:** Always
**Expected:** `~/.claude/projects/-root/memory/spec-verification-protocol.md` существует, содержит `## Step 1` … `## Step 7` и хотя бы один ` ```bash ` блок.
**Actual:** Файл отсутствует (`ls` → `No such file or directory`). Pytest `test_protocol_doc_has_seven_steps` → SKIPPED (а не PASSED).

**Steps to reproduce:**
1. `ls ~/.claude/projects/-root/memory/spec-verification-protocol.md` → not found
2. `pytest tests/integration/test_spec_verify.py::test_protocol_doc_has_seven_steps -v` → `SKIPPED`

**Evidence:** см. вывод pytest (6 passed, 1 skipped).
**User impact:** Оператор, открывший Claude Code из `~`, не получает auto-loaded checklist. EC-4 не выполнен → spec нельзя честно перевести в `done`.
**Hint:** Task 1 спеки описывает ровно содержимое — заполнить шаги 1–7, обновить ссылку на `spec_operator.py` (а не `operator.py`).

---

### F2: `/qa` skill не ссылается на protocol (Task 5)

**Severity:** Minor
**Reproducibility:** Always
**Expected:** `.claude/skills/qa/SKILL.md` содержит ссылки на `spec-verification-protocol.md`, `spec_verify.py`, `spec_operator.py`.
**Actual:** `grep -nE 'spec-verification-protocol|spec_verify\.py|spec_operator\.py' .claude/skills/qa/SKILL.md` → 0 hits.

**Steps to reproduce:** см. grep выше.
**User impact:** При `/qa` на закрытую спеку оператор не получает указатель на checklist — задача Task 5 спеки не выполнена.
**Hint:** добавить раздел "Spec Verification Protocol (when QA-ing a closed spec)" перед footer, как описано в Implementation Plan §Task 5.

---

### F3: EC-2 surrogate репортит HARD-FAIL для BUG-913

**Severity:** Minor (возможно false-positive в самом тесте)
**Reproducibility:** Always
**Expected (по спеке EC-2):** `spec_verify.py BUG-913 awardybot reports OK (allowed files exist, recent commits)`.
**Actual:** Verdict `HARD-FAIL — 1 missing file(s)`:

```
MISS supabase/migrations/2026050xxxxxx_consents_fk_restrict.sql
```

**Steps to reproduce:**
```bash
python3 scripts/vps/spec_verify.py ~/projects/awardybot BUG-913
```

**User impact:** EC-2 как сформулирован в спеке не достижим — либо переформулировать EC-2 (имя файла-миграции в спеке BUG-913 — placeholder `2026050xxxxxx`, который никогда не существует), либо использовать другой эталонный спек. Сами тесты `test_spec_verify_*` проходят, потому что они синтетические.
**Hint:** заменить EC-2 на спек без placeholder-имён или допустить wildcard-резолвинг для `2026050xxxxxx_*.sql` в `spec_verify.py`.

## Passed

| # | Сценарий | Notes |
|---|----------|-------|
| 1 | `spec_verify.py --help` | usage печатается, два позиционных аргумента — OK |
| 2 | `spec_operator.py --help` | три subcommand: demote / force-done / reset-circuit — OK |
| 3 | `pytest tests/integration/test_spec_verify.py` | 6 passed, 1 skipped (см. F1) |
| 4 | EC-1 — `spec_verify FTR-897` | Verdict `HARD-FAIL — 4 missing file(s)`, как и ожидалось спекой (Task 11 missing) |

## Blocked

Нет.

## Fixes Applied

Нет — ни одна находка не вписывается в "<5 LOC light fix" (F1 — целый документ, F2 — раздел skill, F3 — концептуальная переформулировка EC-2).

## Recommendation

Spec **не готов к `done`**. Перед закрытием:
1. Реализовать Task 1 (создать protocol .md) → разблокирует EC-4 и `test_protocol_doc_has_seven_steps`.
2. Реализовать Task 5 (ссылка в `.claude/skills/qa/SKILL.md`).
3. Переформулировать или релокализовать EC-2 (BUG-913 не подходит из-за placeholder-имени миграции).
