---
id: EXP-001
title: Финальный тест — один контракт в SKILL.md + реальная команда ./test ci в awardybot
opened: 2026-09-05
status: open
metric: autopilot по awardybot — timeout_rate, p50_min, доля прогонов с маркером CI_PARITY_* в транскрипте
baseline: n=12 ok=6 timeout=6 (50%) p50_min=136 p90_min=158 p50_usd=28.3 turns=87; CI_PARITY_* в 0 из 198 транскриптов
expected: timeout_rate <= 0.25 И p50_min <= 100 И маркер CI_PARITY_REUSED или CI_PARITY_UNAVAILABLE есть минимум в половине прогонов
command: python3 scripts/metrics/run_metrics.py --split 2026-09-05 --project awardybot
check_after_runs: 15
check_after_date: 2026-09-19
verdict:
---

## Что было

Контракт финальной фазы (§5.1 один полный прогон, §5.4 CI-parity gate, §5.6 fallback)
жил в `.claude/skills/autopilot/autopilot-git.md`. Замер 05.09 по 198 транскриптам
awardybot: **этот файл не открывался ни разу**, а строки `CI_PARITY_REUSED` /
`CI_PARITY_UNAVAILABLE` / `TESTED_TREE` не встречаются нигде. Файла нет в карте «Modules»
в SKILL.md, единственная ссылка на него — из `worktree-setup.md:184`. TECH-206, сделанный
21.06, ни разу не исполнялся.

Иерархия чтения по тем же 198 прогонам: `worktree-setup.md` 83, `task-loop.md` 45,
`subagent-dispatch.md` 40, `finishing.md` 39, `safety-rules.md` 7, `escalation.md` 7,
`autopilot-git.md` 0.

Вторым слоем: в awardybot `finishing.md:12` требовал `./test fast`, то есть
`scripts/dev_cycle.py` с жёстким потолком 300 с на команду, при наборе в ~16 минут.
Обёртка убивала прогон на 5-й минуте, и Opus импровизировал: «Run full suite without the
300s wrapper cap», «chunk 1..3», «CI Test-job on clean develop baseline» — 2–7 полных
прогонов на спеку, 60–150 минут финальной фазы.

## Что изменено

1. `SKILL.md` (оба дерева) — гейт `PHASE-3-FINAL-TEST` прямо в always-loaded промпте:
   один прогон, `TESTED_TREE`, reuse на неизменном дереве, явный запрет дробить набор и
   перезапускать «без потолка», и предписание считать невлезающий набор дефектом проекта
   (`needs_review`), а не поводом обойти.
2. `autopilot-git.md` (оба дерева) — шапка «human reference only» + строка в карте Modules,
   чтобы следующая правка не ушла снова в мёртвый файл.
3. `finishing.md` (оба дерева) — ссылки §5.6 переведены на гейт в SKILL.md.
4. **awardybot `./test ci`** — зеркало job `test` из `.github/workflows/ci.yml`: два
   pytest-прогона (`tests/` без contract/integration/e2e/llm + `src/ --dist=loadfile`),
   без `dev_cycle.py` и его потолка, с MC_OPS_* env из workflow-level env (без них пять
   тестов `tests/unit/flow_engine/test_checkpoint_runner.py` краснеют локально при зелёном
   CI — и агент шёл чинить несуществующий баг).

## Механизм, который проверяем

Правило, вписанное в файл, который читают в 0–20% прогонов, не действует. Правило в
SKILL.md — в контексте всегда. Плюс команда, которая физически может завершиться.

## Если не сработает

Если `timeout_rate` не упал, а маркеры CI_PARITY в транскриптах есть — значит финальная
фаза не была главным пожирателем, и следующий подозреваемый уже назван замером 05.09:
кодер, пишущий тесты пачкой «EC-1..EC-10» (BUG-1494 Task 5 — 70.8 минуты на один вызов).
Тогда рычаг переезжает в то, как sentry-bughunt режет спеки, а не в промпт автопилота.

Если маркеров нет и после правки — гипотеза «дело в том, какой файл читают» опровергнута,
и вопрос переходит к тому, доходит ли до PHASE 3 сам прогон.
