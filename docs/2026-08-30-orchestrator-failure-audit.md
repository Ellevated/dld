# Аудит отказов оркестратора — 16–30 августа 2026

Источник: `callback-audit.jsonl`, `orchestrator.db:task_log`, `callback-debug.log`, логи раннера
`scripts/vps/logs/*.log` и git-история проектов на tietokettu-claude (5.61.91.190). Снято 30.08.2026 read-only.

## Цифры за 14 дней

Раннер (`task_log`, skill=autopilot): **31 done · 19 failed · 1 running** → 38 % прогонов падают
до финала.

Гейт (`callback-audit.jsonl`, 61 вердикт):

| Вердикт | Штук | Из них |
|---|---|---|
| `blocked / no_merged_implementation` | **31** | 12 — при `target_in=done` (раннер отработал, автопилот сказал complete, гейт не увидел реализацию) |
| `blocked / autopilot_signaled_blocked` | 7 | осознанный самоблок — норма |
| `blocked / missing_allowed_files` | 1 | спека без Allowed Files |
| `done / ok` | 11 | |
| `noop` (already done / not in project) | 11 | |

Итого честно закрытых гейтом спек — **11 из 61**. Остальное — либо повтор, либо ручной `force-done`.

## Четыре причины, по убыванию веса

### 1. Шаблон коммита `{type}({scope})` в 9 из 15 даунстримов — гейт слеп

`gate_logic.match_subject` признаёт реализацию только по spec-id в scope subject'а. DLD исправил
`task-loop.md` на `{type}({SPEC_ID})` **25.07.2026** (`262d4f5`), но `/upgrade` — ручной cherry-pick,
и строка не доехала. На VPS сегодня:

| `{SPEC_ID}` ✅ | `{scope}` ❌ (на оркестраторе) | `{scope}` ❌ (не на оркестраторе) |
|---|---|---|
| awardybot, dld | **dowry, dowry-mc, gipotenuza, plpilot, wb** | memyselfandi, mishkinlyap, nexus, dowry-landing-main |

Следствие видно в dowry-mc: `feat(managed): …` × 8 коммитов на develop, FTR-409/410/411 подряд
`no_merged_implementation`, очередь стоит до ручного force-done. Олег закрыл дыру в dowry-mc
30.08 (`c0748d7`), на VPS этот коммит ещё не подтянут; остальные четыре проекта открыты.

**Структурная причина:** контракт «subject обязан нести spec-id» живёт только в промпте. Ни один
хук в цепочке не проверяет subject перед коммитом, хотя `CLAUDE_CURRENT_SPEC_PATH` в env автопилота
есть. Промпт — не гейт.

### 2. Таймаут убивает прогон до merge — 13 прогонов из ~50

| Лимит | Прогонов убито | Ходов на момент смерти |
|---|---|---|
| 5405 с (до 23.08) | 11 | 352–531 |
| 10800 с (с 23.08) | 2 | 473, 655 |

`salvage` после kill пушит ветку `feature/<ID>` (это работает — `pushed: true`, 5–6 коммитов),
но **никто её не мержит**: гейт смотрит только `origin/develop` → `blocked` → оркестратор через
сутки раздаёт спеку заново с нуля (и salvage-push при этом отвергается как non-fast-forward) →
ещё 90–180 минут и ещё $20–30 до того же таймаута. Удвоение таймаута 23.08 не помогло: 655 ходов
и та же смерть.

**Куда уходит время — разбор транскрипта убитого прогона FTR-1467 (3 ч, `059cb85f`):**

| Что | Минут | Заметка |
|---|---|---|
| 3 × `tester` | 82 | 40 + 22 + 19 мин |
| 3 × `coder` | 30 | |
| `planner` | 11 | |
| Bash в главном цикле | 45 | из них pytest/`./test fast`/`check_file_sizes` — 30 |
| всего вызовов инструментов | **103** | модель не «крутится» — 103 вызова за 3 часа |

Внутри 40-минутного `tester` (`agent-afe23f`): `pytest tests/architecture/ -n 4` — **5м01с, убит;
`until ! pgrep …` 5м01с; снова `pytest tests/architecture/` 5м01с; снова pgrep 5м01с**. Сьют
`tests/architecture` в awardybot — 1825 тестов, **325–423 с** даже в одиночку, а Bash-таймаут CLI
по умолчанию 120 с (max 600 с): tester ставил 120/300 с, сьют умирал на 5:01, tester ждал
и перезапускал. Один tester = три убитых сьюта = 20 минут впустую; три tester'а — час.

**Почему стало хуже именно 23.08:** VPS перезагрузился 23.08 14:37, после чего:
- `crafty.service` (Crafty Controller 4, Minecraft, поставлен 21.03) крутит **98 % ядра
  непрерывно 6 суток 19 часов** без единого игрового Java-сервера;
- `sar`: **%steal 13–16 % до 22.08 → 35–42 % с 23.08** (KVM, 6 vCPU — эффективно ~4);
- `slot-admin.service` (awardybot) пишет **8 700 строк в час** в journald, journald на 44 %
  накопленного CPU;
- на это два параллельных автопилота с `pytest -n 4` каждый.

`check_file_sizes.py` в прогоне занял 7м41с; сейчас — 3,25 с. Машина была задушена, сьют
не укладывался в таймаут инструмента, а внешний таймаут прогона просто фиксировал результат.

### 3. CLI умирает с `exit 1`, stderr потерян — 4 прогона 25–26.08

`claude_agent_sdk` бросает `Command failed with exit code 1 … Check stderr output for details`.
Два случая — после 95 и 38 ходов ($30.27 и $22.41 сожжено), два — мгновенно на первом ходу
(`turns=1, cost=0`). Всё в окне 25.08 12:49–15:34, CLI 2.1.234.

`claude-runner.py:539-545` ставит коллектор stderr (BUG-188), но в логах он **пуст** — SDK-коллбэк
ничего не отдал. Причина неизвестна, следов rate-limit в логах нет. Открытый вопрос, диагностировать
нечем, пока stderr не пишется на диск отдельно от SDK.

### 4. Нет телеметрии времени — «стало дольше» измерить нечем

`ai/lifecycle/*.yaml`: у 30 из 31 done-спек все переходы записаны одним timestamp, `started_at` /
`finished_at` пустые. `task_status` пуст при любом падении. Единственный замер длительности за
всю историю — TECH-214 (47,5 мин). Вопрос «почему спеки долго» на этих данных не имеет ответа.

## Шум, не отказы

- `OUT_OF_SCOPE` × 10 — детектор (BUG-199 Fix C) ругается на миграции, тесты, `openapi.json`,
  `autopilot-state.json`. Аллоулисты спек уже узки, детектор это подтверждает, но не блокирует.
- `not_in_project` × 5 (awardybot) — callback ищет lifecycle не в том проекте; безвредно.

## Что делать — по весу

| # | Действие | Где | Закрывает |
|---|---|---|---|
| 1 | Прокатить `{type}({SPEC_ID})` + чеклист из `c0748d7` в dowry, gipotenuza, plpilot, wb; `git pull` dowry-mc на VPS | даунстримы | причина 1, сегодня |
| 2 | Pre-commit хук в template: при непустом `CLAUDE_CURRENT_SPEC_PATH` отвергать subject без spec-id | `template/.claude/hooks/` | причина 1 навсегда |
| 3a | `BASH_DEFAULT_TIMEOUT_MS=900000`, `BASH_MAX_TIMEOUT_MS=1800000` в env раннера — сделано 30.08 | `claude-runner.py` | причина 2, петля в tester |
| 3b | Остановить `crafty.service` на клод-сервере (решение founder'а — это Minecraft), утихомирить `slot-admin` лог | VPS | причина 2, steal |
| 3c | Гейт учитывает `origin/feature/<ID>` после salvage — или salvage делает `--ff-only` merge сам, когда `./test ci` зелёный; повторный диспатч продолжает ветку, а не стартует с нуля | `callback_sync` / `salvage` | причина 2, потеря работы |
| 4 | Писать stderr CLI в файл рядом с логом прогона, не через SDK-коллбэк | `claude-runner.py` | причина 3 |
| 5 | `started_at`/`finished_at` в lifecycle от orchestrator/callback | `lifecycle.py` | причина 4 |

Пункты 2–5 — работа в DLD; 1 — в проектах. Всё это ложится рядом с TECH-213/216/ARCH-209, которые
тоже стоят: TECH-213 `blocked` с 28.07, TECH-216 снят с автопилота 28.08 и делается в интерактиве.
