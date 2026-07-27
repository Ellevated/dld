# Diary

| Date | ID | Type | Summary | Debug | Files | Status |
|------|----|------|---------|-------|-------|--------|
| 2026-03-10 | FTR-146 | success | Task 1/11: SQLite Schema + Python DB Module | 0 | 3 | done |
| 2026-03-10 | FTR-146 | problem | Task 2/11: debug ×1: jq --argi invalid flag + set -e exit code | 1 | 3 | done |
| 2026-03-10 | FTR-146 | problem | Task 3/11: debug ×1: SQL injection via db_exec.sh shell interpolation | 1 | 2 | done |
| 2026-03-10 | FTR-146 | problem | Task 4/11: debug ×1: DRY notify.py + bare exception + returncode + utcnow | 1 | 3 | done |

## Types: success, problem, escalation, regression, escaped_defect
## Statuses: pending, done
## Columns: Debug = debug_attempts count, Files = files_changed count
| 2026-07-27 | TECH-211 | success | Характеризационные тесты lifecycle_audit (22) до раскола | 0 | 1 | done |
| 2026-07-27 | TECH-211 | success | Раскол heartbeat_reaper.py 459->255 + 2 sibling-модуля | 0 | 4 | done |
| 2026-07-27 | TECH-211 | success | Раскол lifecycle_audit.py 525->254 + audit_probe/audit_categories | 0 | 3 | done |
| 2026-07-27 | TECH-211 | advisory | dependencies.md вне Allowed Files — карта зависимостей не описывает 4 новых модуля | 0 | 0 | done |
| 2026-07-28 | TECH-212 | success | Характеризационные тесты CLI-контракта db.py (12) до раскола | 0 | 1 | done |
| 2026-07-28 | TECH-212 | success | Раскол db.py 602->373 + db_decisions/db_findings/db_cli | 0 | 4 | done |
| 2026-07-28 | TECH-212 | success | Структурные контрактные тесты EC-1..EC-10 (568 LOC) | 0 | 1 | done |
| 2026-07-28 | TECH-212 | advisory | dependencies.md + docs/orchestrator/components.md вне Allowed Files — не описывают 3 новых модуля | 0 | 0 | done |
| 2026-07-28 | TECH-212 | advisory | get_finding_by_id / get_all_findings — мёртвый код без единого потребителя, перенесён как есть | 0 | 0 | done |
