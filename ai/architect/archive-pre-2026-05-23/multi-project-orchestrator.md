# Multi-Project Orchestrator: Architecture Spec

> Собрано из сессии обсуждения. Готово к реализации через `/spark` или `/autopilot`.

---

## Концепция

Единый config-driven оркестратор, управляющий N проектами с одного VPS. Каждый проект — отдельный топик в Telegram-группе. Пишешь в топик — работаешь с конкретным проектом.

---

## Telegram: 1 чат + N топиков = N проектов

```
Telegram Supergroup (Forum mode ON)
├── General Topic        → общие команды (/projects, /help, /addproject)
├── Topic "SaaS App"     → thread_id=5  → /home/user/saas-app
├── Topic "Side Project" → thread_id=8  → /home/user/side-project
└── Topic "Freelance"    → thread_id=12 → /home/user/freelance
```

**Принцип:** `message_thread_id` из входящего сообщения → однозначная маршрутизация к проекту.

### Что даёт

- Пишешь в топик "SaaS App" голосовое — идея попадает в `/home/user/saas-app/ai/inbox/`
- `/status` в этом же топике → бэклог именно SaaS App
- `/run` в этом топике → триггерит автопайлот для этого проекта
- Бот отвечает **в тот же топик** — переписки не смешиваются
- Скриншоты, голосовые, текст — всё в контексте проекта

---

## Конфиг: projects.json

```json
{
  "chat_id": -1001234567890,
  "general_topic_id": null,
  "max_concurrent_claude": 2,
  "projects": [
    {
      "name": "SaaS App",
      "topic_id": 5,
      "path": "/home/user/saas-app",
      "priority": "high",
      "poll_interval": 300,
      "enabled": true
    },
    {
      "name": "Side Project",
      "topic_id": 8,
      "path": "/home/user/side-project",
      "priority": "low",
      "poll_interval": 900,
      "enabled": true
    }
  ]
}
```

**Где лежит:** `scripts/vps/projects.json`

**Hot-reload:** оркестратор перечитывает конфиг каждый цикл (или по `inotifywait`).

---

## Оркестратор: единый event loop

### Архитектура

```
orchestrator.sh (единый процесс)
  │
  ├── reads projects.json
  ├── for each enabled project (sorted by priority):
  │     ├── check inbox     → run inbox-processor.sh (Spark)
  │     ├── check backlog   → run autopilot-loop.sh
  │     └── check done      → run qa-loop.sh
  │
  ├── global semaphore: flock (max N concurrent claude calls)
  ├── notifications → send to project's topic_id
  └── state → .orchestrator-state.json (per-project states)
```

### Семафор для Claude API

```bash
# Глобальный лок — max 2 concurrent claude вызова
SEMAPHORE_DIR="/tmp/claude-semaphore"
MAX_CONCURRENT=2  # из projects.json

acquire_claude_slot() {
    while true; do
        for i in $(seq 1 $MAX_CONCURRENT); do
            if flock -n "$SEMAPHORE_DIR/slot-$i" true 2>/dev/null; then
                echo "$i"
                return 0
            fi
        done
        sleep 5
    done
}
```

### Приоритеты

- `high` — проверяется каждый цикл
- `medium` — каждый второй цикл
- `low` — каждый третий цикл
- При равном приоритете — round-robin

### State файл (расширенный)

```json
{
  "updated": "2026-03-10T12:00:00Z",
  "pid": 12345,
  "projects": {
    "saas-app": {
      "phase": "autopilot",
      "detail": "FTR-042",
      "last_check": "2026-03-10T11:55:00Z"
    },
    "side-project": {
      "phase": "idle",
      "detail": "",
      "last_check": "2026-03-10T11:50:00Z"
    }
  }
}
```

---

## Telegram бот: роутинг по топикам

### Маршрутизация

```python
# При старте — загрузить маппинг
projects_by_topic = {}
for p in config["projects"]:
    projects_by_topic[p["topic_id"]] = p

# Обработка сообщения
async def handle_message(update, context):
    thread_id = update.message.message_thread_id
    project = projects_by_topic.get(thread_id)

    if project:
        # Контекст проекта определён
        handle_project_message(update, context, project)
    else:
        # General topic — общие команды
        handle_general_message(update, context)
```

### Отправка нотификаций в топик

```python
async def notify_project(bot, project, text):
    await bot.send_message(
        chat_id=config["chat_id"],
        message_thread_id=project["topic_id"],
        text=text,
        parse_mode="Markdown"
    )
```

### Команды

#### В топике проекта (контекст = этот проект)

| Команда | Действие |
|---|---|
| `/status` | Бэклог, inbox, QA статус проекта |
| `/run` | Триггернуть autopilot прямо сейчас |
| `/pause` / `/resume` | Поставить/снять проект с паузы |
| `/priority high\|medium\|low` | Сменить приоритет |
| `/queue` | Показать очередь задач |
| `/qa` | QA статус по последним спекам |
| `/log` | Последние 20 строк лога |
| (текст) | → ai/inbox/ как идея |
| (голосовое) | → Whisper → ai/inbox/ как идея |
| (скриншот) | → ai/inbox/ как идея с изображением |

#### В General topic (контекст = все проекты)

| Команда | Действие |
|---|---|
| `/projects` | Список проектов, статусы, приоритеты |
| `/addproject <name> <path>` | Создать топик + зарегистрировать проект |
| `/removeproject <name>` | Удалить проект (закрыть топик) |
| `/global_status` | Сводка по всем проектам |
| `/budget` | Расход API по проектам |

### Создание проекта через Telegram

```python
async def cmd_addproject(update, context):
    name, path = parse_args(context.args)  # /addproject "My App" /home/user/my-app

    # 1. Создать топик в Telegram
    topic = await context.bot.create_forum_topic(
        chat_id=config["chat_id"],
        name=f"🔧 {name}"
    )

    # 2. Добавить в projects.json
    new_project = {
        "name": name,
        "topic_id": topic.message_thread_id,
        "path": path,
        "priority": "medium",
        "poll_interval": 600,
        "enabled": True
    }
    config["projects"].append(new_project)
    save_config()

    # 3. Подтвердить
    await notify_project(context.bot, new_project,
        f"Project *{name}* registered!\nPath: `{path}`\nWrite here to add ideas.")
```

---

## Нюансы Telegram API

1. **General topic (thread_id=1):** Баг — нельзя отправить с `message_thread_id=1`. Отправлять без `message_thread_id` вообще.
2. **Бот должен быть админом** с правом `can_manage_topics` для создания/закрытия топиков.
3. **Forum mode** включается в настройках группы (Settings → Topics → Enable).
4. **PTB v22+** полностью поддерживает `message_thread_id` во всех send-методах.
5. **Вложенные треды невозможны** — внутри топика нет подтредов.

---

## notify.sh — расширение

```bash
# Текущий вызов
notify "Spec FTR-042 done"

# Новый вызов (с привязкой к проекту)
notify --project "saas-app" "Spec FTR-042 done"
# → отправляет в topic_id проекта saas-app

# Fallback (без --project) → General topic
```

---

## Файловая структура изменений

```
scripts/vps/
├── projects.json              # NEW: реестр проектов
├── orchestrator.sh            # REFACTOR: цикл по проектам, семафор
├── telegram-bot.py            # REFACTOR: роутинг по topic_id
├── notify.sh                  # UPDATE: --project параметр
├── inbox-processor.sh         # UPDATE: принимает PROJECT_DIR как аргумент
├── autopilot-loop.sh          # UPDATE: принимает PROJECT_DIR как аргумент
└── qa-loop.sh                 # UPDATE: принимает PROJECT_DIR как аргумент
```

---

## Ресурсы и лимиты

| Параметр | Рекомендация |
|---|---|
| Max concurrent Claude CLI | 2 (на 8GB VPS) |
| RAM на 1 Claude процесс | 200-500 MB |
| Max проектов (8GB VPS) | 6-10 |
| `--max-turns` на autopilot | 20-30 (защита от runaway) |
| `timeout` на claude вызов | 600-900 секунд |

---

## Альтернативные варианты (рассматривались)

| Вариант | Усилия | Вердикт |
|---|---|---|
| Отдельные tmux на проект | 1 час | Нет координации API, тупик |
| Мета-оркестратор (parent + children) | 1-2 дня | Хорош, но лишний слой |
| **Config-driven (этот)** | **2-3 дня** | **Выбран — баланс простоты и контроля** |
| Docker-контейнеры | 3-5 дней | Оверкилл для 2-3 проектов |

---

## Полезные инструменты

- **Pueue** — task queue для CLI команд (приоритеты, группы, параллелизм)
- **Task Spooler (`ts`)** — проще, файловая очередь
- **`flock`** — встроенный семафор Linux
- **`inotifywait`** — event-driven вместо polling (реакция на новый файл в inbox)

---

## План реализации

1. Создать `projects.json` с конфигом
2. Рефакторить `telegram-bot.py` — роутинг по `message_thread_id`
3. Рефакторить `orchestrator.sh` — цикл по проектам, семафор
4. Обновить `notify.sh` — параметр `--project`
5. Обновить `inbox-processor.sh`, `autopilot-loop.sh`, `qa-loop.sh` — принимать `PROJECT_DIR`
6. Тест: 2 проекта, 2 топика, отправить идею в каждый

---

## Источники

- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Telegram Forums API](https://core.telegram.org/api/forum)
- [PTB ForumTopic docs](https://docs.python-telegram-bot.org/en/v21.7/telegram.forumtopic.html)
- [PTB v22 Bot docs](https://docs.python-telegram-bot.org/telegram.bot.html)
- [PTB issue: message_thread_id=1 bug](https://github.com/python-telegram-bot/python-telegram-bot/issues/4739)
