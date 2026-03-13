# TECH-150: Orchestrator E2E Fixes — Path to Working Pipeline

**Status:** in_progress (E2E cycle verified 2026-03-12)
**Date:** 2026-03-12
**Type:** Tech Debt / Bug Fix Batch

## Problem

Orchestrator pipeline (FTR-148/149) was architecturally sound but had ~15 bugs preventing end-to-end flow from working. User never received a full cycle: Telegram → Spark → Approval → Autopilot → Result notification.

## Root Causes Found (in order of discovery)

### 1. venv не активирован в bash скриптах
**Files:** pueue-callback.sh, inbox-processor.sh, qa-loop.sh, night-reviewer.sh
**Symptom:** `ModuleNotFoundError: dotenv`, `telegram` not found
**Fix:** Added `[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"` to all scripts

### 2. git pull падает когда агент работает
**File:** orchestrator.sh `git_pull()`
**Symptom:** `pull --rebase` requires clean working tree, agents leave dirty files
**Fix:** 3-tier strategy: skip if agent running → clean→pull → dirty→fetch+rebase --autostash

### 3. Reflect spam — бесконечный dispatch
**File:** orchestrator.sh `dispatch_reflect()`
**Symptom:** reflect запускался каждый цикл, diary entries оставались `pending`
**Fix:** (a) reflect skill обязан помечать entries done, (b) pueue dedup check before dispatch

### 4. grep -c || echo "0" даёт двойной output
**File:** orchestrator.sh
**Symptom:** `grep -c` outputs "0" AND returns exit 1 → `|| echo "0"` appends second "0" → arithmetic error
**Fix:** `|| true` + `$(( x + 0 ))`

### 5. Duplicate draft notifications из-за regex matching status doc table
**File:** orchestrator.sh `scan_drafts()`
**Symptom:** Regex `| draft |` matched `| draft | Spec in progress |` в документации
**Fix:** Tighter regex requiring spec ID at start of line

### 6. Markdown brackets breaking Telegram API
**File:** notify.py `send_spec_approval()`
**Symptom:** Title `Feature: [FTR-242]` — brackets interpreted as markdown link
**Fix:** Strip spec ID prefix from title

### 7. Все ответы бота на английском
**Files:** telegram-bot.py, approve_handler.py, voice_handler.py, photo_handler.py, inbox-processor.sh, notify.py
**Fix:** Full Russian localization of all user-facing messages

### 8. Devops dump в нотификациях
**Files:** pueue-callback.sh, inbox-processor.sh
**Symptom:** Raw JSON/log in completion notifications — user couldn't read them
**Fix:** Human-readable format with skill labels and result_preview

### 9. Council результат терялся
**File:** pueue-callback.sh
**Symptom:** Council завершался, result в pueue log, но никуда не записывался
**Fix:** Step 6.5 — council/architect result → inbox с route=spark → orchestrator подхватит → spark создаст spec

### 10. QA/Reflect не запускались (wrong pueue group)
**File:** pueue-callback.sh Step 7
**Symptom:** `pueue add --group "dowry"` — group не существует, только `claude-runner`
**Fix:** Берём provider из DB → `${provider}-runner`

### 11. QA/Reflect бесконечная рекурсия
**File:** pueue-callback.sh Step 7
**Symptom:** Каждый QA порождал QA+reflect, каждый reflect порождал QA+reflect → экспоненциальный рост
**Fix:** Step 7 только для `SKILL in (autopilot, spark, spark_bug)`

### 12. Нет route для QA/reflect/scout
**Files:** telegram-bot.py `detect_route()`, inbox-processor.sh
**Symptom:** "проверь как работает" → route=spark (default), spark не знает что делать
**Fix:** Added qa, reflect, scout routes с ключевыми словами

### 13. Spark не создаёт spec (CRITICAL)
**File:** inbox-processor.sh
**Symptom:** Spark входил в интерактивный режим (bug-mode: "воспроизведи ошибку"), ждал user input, не получал → сдавался на 8 turns без создания spec
**Root cause:** Telegram задачи шли БЕЗ `[headless]` маркера. Код пропускал `[headless]` для source=telegram.
**Fix:** ВСЕ inbox задачи получают `[headless]` — они всегда запускаются в orchestrator без TTY

### 14. Autopilot result_preview всегда пустой (CRITICAL)
**File:** claude-runner.py
**Symptom:** Пользователь никогда не видел что autopilot сделал
**Root cause:** Autopilot использует Agent tool → Tasks. Результат приходит как `TaskNotificationMessage.summary`, а claude-runner.py ловил только `ResultMessage.result` (= None для Tasks)
**Fix:** Добавлена обработка `TaskNotificationMessage` + `AssistantMessage` fallback. Также fix: `total_cost_usd` вместо несуществующего `cost_usd`

### 15. Тройные ответы при перезапуске бота
**File:** telegram-bot.py
**Symptom:** При перезапуске старые инстансы не умирают мгновенно → TG API отдаёт updates нескольким
**Fix:** `_kill_other_instances()` при старте — pkill + SIGKILL старых PID

### 16. inbox-processor.sh — venv не активирован
**File:** inbox-processor.sh
**Symptom:** `ModuleNotFoundError: dotenv` при вызове notify.py из inbox-processor
**Root cause:** В inbox-processor.sh была загрузка .env (`set -a && source`), но не было активации venv
**Fix:** Добавлена строка `[[ -d "${SCRIPT_DIR}/venv" ]] && export PATH="${SCRIPT_DIR}/venv/bin:$PATH"`

### 17. UnicodeEncodeError surrogates в result_preview
**File:** pueue-callback.sh Step 4
**Symptom:** Telegram notification падает с `UnicodeEncodeError: surrogates not allowed` — пользователь не получает QA notification
**Root cause:** claude-runner.py может вернуть текст с surrogate characters (из LLM output), Telegram API их отвергает
**Fix:** `text.encode('utf-8', errors='replace').decode('utf-8')` при парсинге result_preview

### 18. Callback errors скрыты `2>/dev/null`
**File:** pueue-callback.sh Steps 5.5, 6, 6.5
**Symptom:** notify.py падает тихо, никто не знает что уведомления не доходят
**Fix:** Все `2>/dev/null` заменены на `2>>"$CALLBACK_LOG"` + добавлен debug-трейс на входе/выходе callback

### 19. Дубль approval notification (callback + scan_drafts race)
**Files:** pueue-callback.sh Step 5.5, orchestrator.sh scan_drafts()
**Symptom:** Два одинаковых approval сообщения в Telegram для одной спеки
**Root cause:** Callback записывал spec_id в `.notified-drafts` ПОСЛЕ отправки. Orchestrator scan_drafts мог прочитать файл до записи и отправить повторно.
**Fix:** `.notified-drafts` записывается ДО отправки в callback

### 20. Surrogate fix не покрывал MSG и SUMMARY
**File:** pueue-callback.sh
**Symptom:** Surrogate fix стоял только в Step 4 (парсинг JSON), но surrogates проскакивали через fallback grep или bash variable passing
**Fix:** Финальная очистка surrogates на MSG перед Step 6 и на SUMMARY перед Step 5.5

### 21. Пустое подтверждение при нажатии кнопок
**File:** approve_handler.py
**Symptom:** После нажатия "В работу" кнопки исчезают и просто пишется "✅ FTR-0062 принята → в очередь" — непонятно что произошло
**Fix:** Подробное сообщение с проектом, статусом и ETA (~5 мин до autopilot)

### 22. Summary "—" в approval notification
**File:** pueue-callback.sh Step 5.5
**Symptom:** Если result_preview от spark пуст, пользователь видит "—" вместо описания спеки
**Fix:** Fallback на секцию Problem/Why/Что делаем из spec файла

## Files Modified

| File | Changes |
|------|---------|
| `scripts/vps/pueue-callback.sh` | Step 4 JSON parse + surrogate fix, Step 5.5 spark approval, Step 6 debug logging, Step 6.5 council→inbox + reflect, Step 7 skill filter + provider from DB, callback-debug.log tracing |
| `scripts/vps/claude-runner.py` | TaskNotificationMessage + AssistantMessage capture, total_cost_usd fix |
| `scripts/vps/inbox-processor.sh` | [headless] for ALL tasks, qa/reflect/scout routes, quoted $TASK_CMD, venv activation |
| `scripts/vps/telegram-bot.py` | QA/reflect/scout routes, _kill_other_instances(), Russian localization |
| `scripts/vps/notify.py` | send_spec_approval format with result_preview |
| `scripts/vps/orchestrator.sh` | git_pull safety, reflect dedup, scan_drafts regex, venv activation |
| `scripts/vps/approve_handler.py` | Russian localization, detailed approve/reject/rework confirmations |
| `scripts/vps/voice_handler.py` | Russian localization |
| `scripts/vps/photo_handler.py` | Russian localization |
| `scripts/vps/qa-loop.sh` | venv activation |
| `scripts/vps/night-reviewer.sh` | venv activation |
| `template/.claude/skills/reflect/SKILL.md` | Step 5.6: mark diary entries pending→done |

## Lessons Learned

1. **Всегда headless в pipeline** — если task запускается из orchestrator, пользователя нет. Не важно что source=telegram.
2. **Agent SDK message types** — `ResultMessage` не единственный. Autopilot/Tasks возвращают `TaskNotificationMessage.summary`.
3. **Pueue groups** — задачи ВСЕГДА в `{provider}-runner`, не в `{project_id}`.
4. **Рекурсия в callbacks** — callback порождает задачи → те порождают callbacks → те порождают задачи. Фильтр по SKILL обязателен.
5. **Single instance** — при перезапуске бота SIGKILL старые PID, иначе duplicate responses.
6. **grep -c exit code** — возвращает 1 при 0 matches, `|| echo` даёт двойной output.
7. **Template sync** — DLD-специфичный reflect skill устарел (создавал TECH-спеки вместо inbox файлов). Template-версия правильная.
8. **Pueue daemon restart** — callback не выполняется без перезапуска pueued после изменения pueue.yml.
9. **QA skill отсутствовал** — во всех 4 проектах не было `.claude/skills/qa/`. Callback Step 7 диспатчил QA → "Unknown skill".
10. **venv в inbox-processor** — без venv notify.py падает на `import dotenv`, уведомления "Создаю спеку" не доходят.
11. **Surrogate characters** — LLM output может содержать surrogate chars, Telegram API их отвергает. Нужна явная очистка.
12. **`2>/dev/null` — враг отладки** — все stderr от notify.py уходили в /dev/null. Проблемы не видны. Заменено на debug log.
13. **Surrogate fix — только на финале** — фиксить surrogates на парсинге недостаточно. Bash переменные и fallback пути могут внести surrogates заново. Финальная очистка перед Telegram API — единственно надёжный подход.
14. **Race condition в dedup** — запись в dedup файл должна быть ДО отправки, не после. Иначе параллельный процесс может отправить дубль.
15. **UX кнопок** — после нажатия пользователь должен видеть не просто "принято", а что произойдёт дальше и когда.

## Open Observations (не починено, наблюдаем)

- **Микрофон в подтверждении**: при approve голосовой задачи — сообщение "принято" приходит с иконкой микрофона, при текстовой — без. Гипотеза: Telegram наследует тип сообщения от оригинала.
- **"Создаю спеку" — слишком длинный preview**: обрезано до 100 символов + "…". DONE.
- **"завершена" — неправильный род**: "Автопилот завершена" → "Автопилот — готово". DONE.
- **result_preview — вода вместо сути**: autopilot пишет "Все чекбоксы DoD выполнены..." вместо "Добавлены кнопки отменить/пауза". Корень: LLM не знает формат финального output. TODO: structured output instruction в autopilot agent (template change).

## Acceptance Criteria

- [x] Telegram → Spark → Approval notification с result_preview и кнопками
- [x] User нажимает "В работу" → autopilot запускается
- [x] Autopilot завершается → notification с описанием что сделано
- [x] QA + Reflect запускаются после autopilot (не после QA/reflect)
- [ ] Council → result в inbox → Spark создаёт spec
- [ ] Голосовые и фото обрабатываются корректно
- [ ] Нет duplicate ответов
- [ ] Reflect → inbox files (Route: spark) → Spark подхватывает
- [x] QA skill работает во всех проектах
- [x] Inbox → Orchestrator → Spark → Draft spec → Approval (второй круг)
