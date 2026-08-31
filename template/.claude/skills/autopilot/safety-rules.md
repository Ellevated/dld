# Safety Rules

Critical rules that must never be violated.

## Parallel Safety

For multi-autopilot environments:

- ⛔ **NEVER take task with status `in_progress`** — another autopilot working!
- ⛔ **ONLY take tasks with `queued` or `resumed`**
- Before taking ANY task: READ backlog → VERIFY status

### Single Instance Rule

**WARNING: No file locking is implemented.** Run ONLY ONE autopilot instance at a time.

Parallel autopilot instances can:
1. Both read same task as "queued" simultaneously
2. Both start working on the same task
3. Create conflicting git commits on the same branch
4. Corrupt backlog status (both write "in_progress")

**Prevention:** Use `autopilot-loop.sh` for sequential execution. Never run multiple `autopilot` commands in parallel terminals.

## Git Safety

- ⛔ **NEVER push to `main`** — only `develop`
- ⛔ **NEVER auto-resolve conflicts** → STATUS: blocked
- ⛔ **NEVER** `git clean -fd` — destroys parallel work
- ⛔ **NEVER** `git reset --hard` — loses changes

## File Safety

- ⛔ **Modify files NOT in `## Allowed Files`** — File Allowlist!
- ⛔ **Take tasks with status `draft`** — no plan yet!

**Rule:** File NOT in spec's `## Allowed Files` → REFUSE. No exceptions.

## Ход не заканчивается ожиданием

⛔ **NEVER** запускать проверки в фоне (`run_in_background: true`, `&`, отложенный
`Agent`-таск) и завершать ход, чтобы «вернуться за результатом».
⛔ **NEVER** заканчивать ход фразой вида «жду прогона», «жду кодера», «жду гейт»,
«I'll commit once the suite lands», «Waiting on the full suite».

**Почему это дороже всего остального в этом файле.** Autopilot бежит без человека.
Завершённый ход = завершённая сессия: следующего хода не будет, разбудить агента некому.
Фоновая задача досчитает в пустоту, работа останется незакоммиченной в worktree, а раннер
отчитается `exit=0` — то есть «успех». Callback потом честно поставит
`no_merged_implementation`, спека уйдёт в blocked, и следующий заход начнёт всё заново.

Ночь 21.08.2026, awardybot, три прогона подряд — все три погибли ровно так:

| Прогон | Последняя фраза агента | Цена |
|---|---|---|
| TECH-1450 | «Waiting on the full suite.» | $21.81 — 5 коммитов в ветке, мержа нет |
| BUG-1448 #1 | «Тестер гоняет архитектурные гейты» | $13.22 — ни одного коммита |
| BUG-1448 #2 | «Waiting on the architecture suite before committing.» | $23.77 — работа только в worktree |

Итого $58.80 за ночь при полностью сделанной работе. Тогда правило внесли только в awardybot,
и остальные проекты продолжили гибнуть тем же способом: 24.08.2026 в dowry так ушли три прогона
из четырёх («Жду кодера по Task 4», «Жду последний гейт — мутационную проверку тестов»,
обрывок `until [ -f /tmp/test_fast_full.log ]`) плюс таймаут на 655 ходов — ~$115 за сутки при
одной доведённой спеке. Поэтому правило живёт в template и во всех проектах, а не в одном.

**Как правильно:**

- Проверка гоняется **синхронно**, в том же вызове: `timeout 900 <команда прогона> | tail -20`.
  Ход не завершается, пока команда не вернула результат.
- **Откуда вообще берётся соблазн фона:** у Bash-тула дефолтный лимит 120 000 мс, а полный
  набор на занятой машине легко перебирает две минуты. Получив таймаут, агент естественным
  движением уносит прогон в фон — и убивает сессию. Поэтому **задавай параметр `timeout` явно**
  (до 600 000 мс) в самом вызове Bash, вместо того чтобы ловить дефолт и спасаться фоном.
- Набор не влезает в один вызов → **сузить набор** до затронутых путей, а не уносить в фон.
  Полный прогон не является обязательным условием коммита: PHASE 3 всё равно упрётся в CI.
- Долгая проверка неизбежна → **сначала коммит, потом проверка**. Незакоммиченная работа
  переживает конец сессии только в виде diff'а в worktree, который никто не ищет.

**Проверка перед завершением хода (обязательная):** `git status --porcelain` пуст, либо
осталось ровно то, что перечислено в отчёте как намеренно незакоммиченное. Непустой вывод +
завершение хода = потерянная работа.

## Test Safety

- ⛔ **NEVER modify** `tests/contracts/**` or `tests/regression/**`
- ⛔ **NEVER change test assertions** without user approval
- Test fails → fix CODE, not test (unless created in current session)
- Unclear? → ASK USER

## Code Quality Gates

- ⛔ File > 400 LOC (600 for tests) → split
- ⛔ `__init__.py` > 5 exports → reduce API
- ⛔ New code in `src/services/`, `src/db/`, `src/utils/` → use domains/
- ⛔ Import upward in dependency graph → fix direction

## Workflow Rules

- ⛔ Commit without Reviewer approved
- ⛔ Group multiple tasks before review
- ⛔ Skip Documenter or Reviewer
- ⛔ Run ALL LLM tests without reason (Smart Testing!)
- ⛔ Fix out-of-scope test failures (Scope Protection!)
- ⛔ Check DoD at start — DoD is FINAL checklist!

## Scope Protection

**SSOT:** `.claude/agents/tester.md#scope-protection`

Test fails but NOT related to `files_changed`? → SKIP, don't fix. Log and continue.

## Smart Testing

**SSOT:** `.claude/agents/tester.md#smart-testing`

Run only tests related to changed files, not entire suite.

## Migration Safety

- ⛔ **NEVER apply migrations manually** — CI only!
- Validate locally: squawk lint, dry-run
- CI applies after push to develop

## Serverless Functions

- ⛔ **NEVER deploy serverless functions manually** — CI only!
- Validate locally: type check, lint
- CI deploys after push to develop
