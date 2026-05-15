# QA Report: TECH-973 — Hermes intake contract

**Date:** 2026-05-15
**Environment:** local repo (documentation + regression test spec)
**Trigger:** `/qa TECH-973`
**Spec status at QA time:** `queued` (implementation already merged on develop)

## Summary

| Total | Pass | Fail | Blocked |
|-------|------|------|---------|
| 7     | 7    | 0    | 0       |

Спека documentation-only + один regression-тест-блок. UI/API/бота тут нет — проверка свелась к acceptance verification из спеки + grep-инвариантам.

Замечание по статусу: артефакты ВСЕ на месте и тесты зелёные, но `**Status:** queued` в самом spec-файле не переключен на `done`. Это вопрос к callback/autopilot, а не к качеству реализации.

## Passed

| # | Scenario | Notes |
|---|----------|-------|
| 1 | AV-S1 — `ai/inbox/README.md` существует | файл на месте, 113 строк, содержит таблицу из 7 статусов |
| 2 | AV-S2 — pytest collect OK | `pytest --collect-only` зелёный |
| 3 | AV-F1 — regression suite `scan_inbox` зелёный | 7 passed, 0 failed (`scan_inbox_dispatches_queued`, `_ignores_draft`, `_ignores_clarifying_stale_rejected` × 3 параметризации, `_ignores_legacy_new`, `_no_status_field`) |
| 4 | AV-F2 — OpenClaw rename в 4 целевых файлах | `grep -n "OpenClaw"` = 0 во всех 4 файлах (reflect/SKILL.md, audit/night-mode.md, bughunt/completion.md, rules/dependencies.md) |
| 5 | ADR-022 присутствует в architecture.md | строка 104, формулировка совпадает с Design-секцией спеки |
| 6 | README ссылается на SSOT-источники | `_VALID_STATUSES` (callback.py:417), `scan_inbox` (orchestrator.py:315), TECH-181, ADR-021/022 — все цитаты есть |
| 7 | Status lifecycle SSOT согласован | 7 статусов в README ↔ Design-таблица спеки ↔ regex в `scan_inbox` — совпадают |

## Failures

Нет.

## Out-of-scope наблюдения (информативно, НЕ баги TECH-973)

1. В `ai/inbox/README.md:8` есть одна явная сноска «formerly known as OpenClaw» — это разрешено спекой (см. Verification: «или явное "бывший OpenClaw, ныне Hermes" в одной строке-сноске»).
2. В архиве `ai/inbox/done/2026031*-openclaw-*.md` — 5 файлов со словом «OpenClaw». Это исторические intake-документы (уже `done`), не входят в Allowed Files спеки и не должны переименовываться. Behaviour корректное.
3. Spec-файл TECH-973 всё ещё `Status: queued` несмотря на то что вся работа выполнена. Похоже на callback auto-close miss — стоит проверить отдельно (`python3 scripts/vps/spec_verify.py . TECH-973`), но это вопрос orchestrator, а не качества реализации спеки.

## Verify command (из спеки) — результат

```
$ test -f ai/inbox/README.md                            → exit 0 ✓
$ pytest scripts/vps/tests/test_orchestrator.py -k scan_inbox -q  → 7 passed ✓
$ ! grep -rn "OpenClaw" .claude/ ai/inbox/README.md     → exit 0 (только разрешённая сноска в README) ✓
```

## Fixes Applied

Нет (тестирование read-only).
