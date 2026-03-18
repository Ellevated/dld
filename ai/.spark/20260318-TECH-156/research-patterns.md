# Pattern Research — Silence Intermediate Telegram Notifications

## Context

`pueue-callback.sh` и `inbox-processor.sh` отправляют Telegram-уведомления на каждый шаг
цикла (spark, autopilot, QA, inbox dispatch). Цель: заглушить эти промежуточные уведомления,
чтобы репортингом занимался исключительно OpenClaw.

Оба файла уже содержат паттерн `SKIP_NOTIFY=true` для skill `reflect` и вторичных QA
(`qa-inbox-*`). Задача — расширить логику подавления на spark, autopilot, qa.

---

## Approach 1: Skill Allowlist (Hardcoded)

**Source:** [Shell Scripting Best Practices — OneUptime](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view)

### Description

Добавить `spark`, `autopilot`, `qa` в существующий блок `SKIP_NOTIFY` в `pueue-callback.sh`
по аналогии с уже работающим блоком для `reflect` (строки 241-243). В `inbox-processor.sh`
добавить аналогичную проверку перед вызовом `notify.py` — если skill входит в заданный
набор, пропустить отправку. Логика полностью детерминирована и встроена в скрипт.

### Pros

- Следует существующему паттерну кодовой базы — блок `SKIP_NOTIFY` для `reflect` уже есть
- Нулевое введение зависимостей — никаких новых env-переменных, таблиц, конфигов
- Максимальная предсказуемость: список виден прямо в коде, grep-able, review-able
- R2 риск — два файла, изменения тривиально откатываются через `git revert`
- Самый быстрый путь к production (~$1, 15 мин)

### Cons

- Изменение списка требует правки скрипта (хотя скрипт читается при каждом вызове — reload не нужен)
- Нет runtime-переключения без изменения кода
- Если логика разрастётся (разные правила для разных проектов), hardcode окажется недостаточен

### Compute Cost

**Estimate:** ~$1 (R2: contained)
**Why:** 2 файла, 2-4 строки на файл, паттерн уже задан в codebase. Blast radius: только
уведомления, функциональность агентов не затронута.

### Example Source

Расширение существующего блока в `pueue-callback.sh` (после строки 243):

```bash
# Silence intermediate cycle steps — OpenClaw handles reporting
if [[ "$SKILL" =~ ^(spark|autopilot|qa|reflect)$ ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: skill '${SKILL}' silenced (OpenClaw handles reporting)"
fi
```

Аналог для `inbox-processor.sh` (перед строкой 187, где вызывается `notify.py`):

```bash
# Silence pre-dispatch notifications for cycle skills
SKIP_INBOX_NOTIFY=false
if [[ "$SKILL" =~ ^(spark|autopilot|qa|reflect)$ ]]; then
    SKIP_INBOX_NOTIFY=true
    echo "[inbox] Skipping dispatch notification: skill '${SKILL}' silenced"
fi

if [[ "$SKIP_INBOX_NOTIFY" == "false" && -f "$NOTIFY_PY" ]]; then
    python3 "$NOTIFY_PY" "$PROJECT_ID" "$NOTIFY_MSG" 2>/dev/null || ...
fi
```

---

## Approach 2: Environment Variable SILENT_SKILLS

**Source:** [Checking whether a word is in a comma-separated list — Unix SE](https://unix.stackexchange.com/questions/529611/checking-whether-a-word-value-is-in-a-comma-separated-list)

### Description

Определить переменную `SILENT_SKILLS="spark,autopilot,qa,reflect"` в `.env`. Оба скрипта
уже читают `.env` через `set -a && source "${SCRIPT_DIR}/.env" && set +a`. Перед отправкой
уведомления проверить, содержится ли `$SKILL` в `$SILENT_SKILLS` с помощью bash-паттерна
`[[ ",$SILENT_SKILLS," == *",$SKILL,"* ]]`. Без переменной — безопасный fallback.

### Pros

- Runtime-конфигурация без правки кода: изменил `.env` — поведение меняется при следующем вызове
- `.env` уже читается обоими скриптами — нет нового механизма загрузки
- Можно быстро переключить конкретный skill (например, вернуть уведомления для `qa`) без git push
- Паттерн проверки `",$LIST," == *",$SKILL,"*` — стандартный, задокументирован на Unix SE

### Cons

- Добавляет env-переменную, которую нужно поддерживать в `.env.example`
- Если `.env` нет или переменная не задана, нужно явно определить default (молчать или кричать)
- Два места синхронизации: `.env` + `.env.example`
- Тест усложняется: нужно проверить, что переменная читается корректно в обоих скриптах

### Compute Cost

**Estimate:** ~$1-3 (R2: contained)
**Why:** 2 файла скриптов + `.env.example` + документация default-значения. Основной overhead
— тест граничного случая (переменная не задана).

### Example Source

Паттерн из [Unix SE answer](https://unix.stackexchange.com/questions/529611):

```bash
# .env:
# SILENT_SKILLS="spark,autopilot,qa,reflect"

# В скрипте (после source .env):
SILENT_SKILLS="${SILENT_SKILLS:-spark,autopilot,qa,reflect}"  # safe default

if [[ ",$SILENT_SKILLS," == *",$SKILL,"* ]]; then
    SKIP_NOTIFY=true
    echo "[callback] Skipping notification: skill '${SKILL}' in SILENT_SKILLS"
fi
```

Обёртка в запятые гарантирует точное совпадение — `spa` не матчит `spark`,
`reflect` не матчит `reflective`.

---

## Approach 3: Notification Policy в БД

**Source:** [Grafana Notification Policies](https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/notification-policies),
[SQLite Data Change Notification](https://sqlite.org/c3ref/update_hook.html)

### Description

Добавить колонку `notification_policy` в таблицу `project_state` в SQLite со значениями
`"silent_cycle"` / `"verbose"`. Скрипты перед отправкой вызывают
`python3 db.py get_notify_policy <project_id>` и принимают решение на основе результата.
Политика задаётся на уровне проекта — разные проекты могут иметь разные режимы.

### Pros

- Гранулярность на уровне проекта: один проект verbose, другой silent
- Политика персистентна в DB, можно менять через Telegram-бот без редактирования файлов
- Масштабируется: возможны политики типа "уведомлять только об ошибках"

### Cons

- Schema migration: нужно `ALTER TABLE project_state` — изменение затрагивает 8+ downstream
  компонентов из `dependencies.md` (telegram-bot.py, notify.py, orchestrate.sh и др.)
- `db.py` вызывается синхронно в callback-скрипте, который уже делает несколько
  Python-вызовов — ещё один round-trip
- Over-engineering для задачи с 2 файлами: Approach 1 решает это в 4 строках
- Логика подавления уведомлений уходит в слой БД — нарушает locality
- Требует обновления: `db.py`, `schema.sql`, `setup-vps.sh`, тесты

### Compute Cost

**Estimate:** ~$15 (R1: high blast radius)
**Why:** `schema.sql` + migration + `db.py` (новая функция) + `setup-vps.sh` +
опционально `telegram-bot.py` (UI для управления политикой) + тесты.
10+ файлов затронуто. По `dependencies.md` `db.py` используется 8+ компонентами.

### Example Source

[Grafana Notification Policies](https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/notification-policies) —
tree-based routing с label matchers. Релевантен для систем с десятками проектов
и разнородными правилами. При текущем масштабе (5-10 проектов, единственная нужная политика) —
избыточен.

---

## Comparison Matrix

| Criteria | Approach 1: Allowlist | Approach 2: SILENT_SKILLS | Approach 3: DB Policy |
|----------|-----------------------|---------------------------|----------------------|
| Complexity | Low | Low | High |
| Maintainability | High | Medium | Low |
| Runtime reconfiguration | No | Yes (.env edit) | Yes (via bot) |
| Blast radius | R2 | R2 | R1 |
| New dependencies | None | None (+env var doc) | schema migration |
| Testability | High | High | Medium |
| Follows existing pattern | Yes (reflect block) | Partial | No |
| Compute cost | ~$1 | ~$1-3 | ~$15 |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 (Skill Allowlist, hardcoded)

### Rationale

Задача однозначно сформулирована в Socratic insights: "Only 2 files need changes",
"The change is R2 (contained, 2 files, trivially rollbackable)". Approach 1 — прямая
реализация этого требования без отклонений.

Ключевой факт: в `pueue-callback.sh` строки 241-243 уже содержат идентичный паттерн для
`reflect`. Добавление `spark|autopilot|qa` к существующему условию — это один коммит,
одна смысловая единица, понятная без дополнительного контекста.

Key factors:

1. **Consistency** — паттерн `SKIP_NOTIFY` уже задан в codebase; расширение его читается
   как естественное продолжение, а не новая концепция
2. **Zero new dependencies** — никаких новых env-переменных, колонок, функций; код
   понятен без контекста `.env` или схемы DB
3. **R2 is the stated constraint** — Approach 3 нарушает это ограничение,
   Approach 2 добавляет env-variable dependency без видимой необходимости при
   фиксированном наборе skills

### Trade-off Accepted

Отказываемся от runtime-конфигурации (Approach 2) и per-project политик (Approach 3).
Это оправдано: набор "silent skills" предположительно статичен (все cycle-шаги молчат),
а разные политики для разных проектов — not a stated requirement. Если в будущем появится
нужда в runtime-переключении, добавить `SILENT_SKILLS` из `.env` — отдельный PR,
не требующий архитектурных изменений.

---

## Research Sources

- [Shell Scripting Best Practices — OneUptime](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view) — production-grade bash: allowlist через `case` / regex, validate_inputs
- [Checking whether a word is in a comma-separated list — Unix SE](https://unix.stackexchange.com/questions/529611/checking-whether-a-word-value-is-in-a-comma-separated-list) — `",$LIST," == *",$SKILL,"*` паттерн для точного совпадения в CSV-строке
- [Grafana Notification Policies](https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/notification-policies) — tree-based routing как reference для Approach 3
- [Alert Exclusion Rules in Flux](https://oneuptime.com/blog/post/2026-03-05-alert-exclusion-rules-flux/view) — exclusionList паттерн: regex-based подавление уведомлений по паттерну
- [rfxn/alert_lib](https://github.com/rfxn/alert_lib) — production bash alerting library: channel enable/disable через env vars (референс для Approach 2)
