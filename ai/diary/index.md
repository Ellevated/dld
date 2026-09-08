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
| 2026-07-28 | BUG-218 | success | Регрессионные тесты обоих дефектов, RED 9/2 до фикса (11 тестов) | 0 | 1 | done |
| 2026-07-28 | BUG-218 | success | scan_queued пишет in_progress с pueue_id после pueue add | 0 | 2 | done |
| 2026-07-28 | BUG-218 | success | startup_reconcile fail-closed при недоступном pueue | 0 | 2 | done |
| 2026-07-28 | BUG-218 | success | Патч write_lifecycle в 5 happy-path тестах (не 10 — три делят хелпер) | 0 | 1 | done |
| 2026-07-28 | BUG-218 | success | docs/orchestrator: назван фактический писатель перехода | 0 | 3 | done |
| 2026-07-28 | BUG-218 | advisory | EC-5/EC-6 были зелены тривиально — тест без detection power поймал ревьюер, не прогон | 0 | 1 | done |
| 2026-07-28 | BUG-218 | advisory | Девятая приватная копия фикстуры tmp_git_repo — хойст в conftest.py = отдельная TECH-спека | 0 | 0 | done |
| 2026-07-28 | BUG-218 | advisory | startup_reconcile fail-closed одноразовый: pueue лёг на старте и поднялся без рестарта → сироты не демоутятся никогда | 0 | 0 | done |
| 2026-07-28 | BUG-218 | advisory | Корневой tests/ красный на develop (3 pre-existing) + ruff format красный там же | 0 | 0 | done |
| 2026-08-30 | TECH-220 | success | Task 1/5: gate_ancestry ancestry gate + EC-1..EC-8 tests | 0 | 2 | done |
| 2026-08-30 | TECH-220 | advisory | Task 1/5: dependencies.md lacks gate_ancestry entry | 0 | 2 | done |
| 2026-08-30 | TECH-220 | success | Task 2/5: callback contour через find_implementation + gate_via | 0 | 2 | done |
| 2026-08-30 | TECH-220 | success | Task 3/5: orchestrator contour + record_dispatch префикс | 0 | 3 | done |
| 2026-08-30 | TECH-220 | advisory | Task 2+3: gate-daemon.py 398/400 LOC | 0 | 5 | done |
| 2026-08-30 | TECH-221 | success | branch_state + branch_pushed_not_merged verdict + three-way reconcile | 0 | 3 | done |
| 2026-08-30 | TECH-221 | success | EC-1..EC-6 tests; reuse-aware prompts in both trees, EC-7 on throwaway repos | 0 | 5 | done |
| 2026-08-30 | TECH-221 | advisory | 4 advisory findings across tasks 1-4 | 0 | 0 | done |
| 2026-08-30 | TECH-221 | problem | Exa verify found a real data-loss hole in the shipped Task 4 push (bare lease) | 0 | 4 | done |
| 2026-08-30 | TECH-222 | success | Task 1/9: depends_on schema in lifecycle YAML | 0 | 3 | done |
| 2026-08-30 | TECH-222 | advisory | Task 1/9: test_lifecycle.py 788 LOC > 600 guideline (pre-existing 730) | 0 | 1 | done |
| 2026-08-30 | TECH-222 | success | Task 2/9: _spec_deps YAML u backlog, LOC-neutral | 0 | 2 | done |
| 2026-08-30 | TECH-222 | success | Task 3/9: set_depends_on via callable-CAS | 0 | 2 | done |
| 2026-08-30 | TECH-222 | success | Task 4/9: TestDependencyGate on YAML fixtures (mutation-proven) | 0 | 1 | done |
| 2026-08-30 | TECH-222 | success | Tasks 5-6/9: Spark producer depends_on, both trees | 0 | 4 | done |
| 2026-08-30 | TECH-222 | success | Tasks 7-8/9: dead renderer deleted, orchestrator docs corrected | 0 | 3 | done |
| 2026-09-08 | REFLECT-2026-09-08 | reflect | 0 pending в индексе (последняя запись 30.08) + 1 неразобранный сигнал SIGNAL-2026-08-31-2215. Материал добыт из orchestrator.db / логов / git, не из дневника. 4 находки → findings-2026-09-08.md: (1) reflect диспатчится безусловно на каждом мёрже — callback_dispatch.dispatch_reflect без предусловия по входу, дедуп is_already_queued мёртв (метка per-spec уникальна); 39 прогонов по флоту с 01.09 на $97.77, ≥12 на нулевом входе; решение «работать или нет» стоит $2.50 вместо grep -c; (2) в dld поток обучения идёт мимо дневника целиком — 100 коммитов за 9 дней, 0 строк index.md, при этом 5 ai/experiments + 4 docs-разбора; писатели дневника только автопилот/spark, интерактивных сессий у него нет by design — это НЕ дефект awardybot'а, дневник пуст честно; (3) enough_runs у check-experiments.py срабатывает только на VDS, а вызывается только в CI, где логов нет по признанию самого комментария ci.yml:125-133 → 4 эксперимента просрочены (EXP-001 33/15, EXP-003 33/10, EXP-004 27/20, EXP-008 6/5), grep по scripts/vps = 0; (4) Gate 6 (feature-mode.md:909) проверяет наличие строки с командой, а не её исполнение — сигнал 08-31 (`for D in $DEPS` без присваивания) + 4 случая awardybot R114. Внешняя опора (Exa ×2): Airflow ShortCircuitOperator/PythonSensor soft_fail + правило Monte Carlo «не сливать предикат в задачу» под №1; stale-flag литература («adding has an owner and a deadline, removing has neither», эскалирующее уведомление вместо разового warning, практика Google 30 дней-или-продли) под №3. Отдельно проверено и опровергнуто: вывод awardybot R116 «findings пишутся в никуда» в dld не воспроизводится — файлы цитируются 8/5/5/4 раза вне ai/reflect. | 0 | 0 | done |
