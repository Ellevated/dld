# QA Report: TECH-178 — Pre-commit whitespace rollback bypass

**Date:** 2026-05-04
**Environment:** DLD repo HEAD (file/syntax verification, no live VPS test)
**Trigger:** `/qa TECH-178`

## Pre-flight

- Spec status: **`queued`**, but файлы из Allowed Files уже в HEAD (claude-runner.py, run-agent.sh, .pre-commit-config.yaml). Trace ADR-018/TECH-176 — should auto-close on next callback run.
- CI/deploy gate: N/A (orchestrator-internal change, no user-facing endpoint).

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 8     | 7    | 1    | 0       |

## Failures

### F1: Operator override `SKIP=""` НЕ сохраняется — bypass нельзя отключить

**Severity:** Minor
**Reproducibility:** Always
**Expected (Task 2 Step 4 + Acceptance):** `SKIP="" pueue add ...` сохраняет пустое значение → bypass отключён.
**Actual:** Пустая строка перезаписывается дефолтом `trailing-whitespace,end-of-file-fixer,mixed-line-ending`.

**Steps to reproduce:**
```bash
SKIP="" bash -c 'source <(grep -E "^export SKIP=" scripts/vps/run-agent.sh); echo "[$SKIP]"'
# → [trailing-whitespace,end-of-file-fixer,mixed-line-ending]   ❌
# expected: []
```

**Evidence:** см. T2 verification в QA-сессии.

**User impact:** Документированный escape-hatch для оператора (комментарии `run-agent.sh:49`, `claude-runner.py:129`: «Operator override: `SKIP="" pueue add ...` to disable the bypass») не работает. При отладке pre-commit hooks в downstream-проектах оператор не сможет временно вернуть стандартное поведение через переменную окружения.

**Hint for developers:** `scripts/vps/run-agent.sh:50` использует `${SKIP:-default}` — двоеточие подменяет default и для unset, и для empty. Для preserve-empty нужен `${SKIP-default}` (без двоеточия). Acceptance Task 2 внутренне противоречив: «use `${SKIP:-default}`» vs «empty preserved» — одно из двух. Правильный фикс — 1 символ.

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | `claude-runner.py` парсится | ast.parse OK, 308 LOC ≤ 400 |
| 2 | `SKIP` есть в env dict ClaudeAgentOptions | claude-runner.py:130-133 |
| 3 | `run-agent.sh` парсится | bash -n OK |
| 4 | Дефолт применяется при unset SKIP | три hook'а присутствуют |
| 5 | `.pre-commit-config.yaml` валидный YAML | yaml.safe_load OK |
| 6 | exclude-regex матчит research-md зоны | `ai/.spark/**`, `ai/.bughunt/**`, `ai/diary/**`, `ai/reflect/**`, `ai/features/*.md` |
| 7 | exclude-regex НЕ матчит prod-код | `src/**`, `tests/**`, `README.md`, `ai/glossary/**` отфильтрованы |
| 8 | SSOT cross-refs во всех 3 файлах | hook list одинаковый |

## Out of Scope (требует live-прогона)

- Acceptance #4 спеки: «commits с research-md проходят с первого раза в downstream awardybot» — нужен реальный autopilot-таск, не файловая проверка.
- Спека в `queued` несмотря на merged-файлы — проверить что callback auto-close сработает на следующем цикле.

## Fixes Applied

Нет — найденный баг требует обсуждения acceptance criteria (противоречие в спеке), не light fix.
