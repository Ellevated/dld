# Feature: [FTR-149] Orchestrator Cycle v2: Inbox-Centric Architecture

**Status:** done | **Priority:** P0 | **Date:** 2026-03-12

## Why

Текущий цикл оркестратора работает только в минимальном режиме: inbox → spark → backlog → autopilot.
Остальные skills (council, architect, bughunt, qa, reflect) не интегрированы в цикл —
их выход теряется или требует ручного вмешательства.

Ночь 11→12 марта показала: Agent SDK работает (30 задач success), но цикл неполный —
QA не запускается после autopilot, bughunt не создаёт спеки, reflect не автоматический.

## Принцип архитектуры

**Inbox — единая точка входа. Backlog — единая очередь исполнения.**

- Все skills кроме Spark пишут результат в `ai/inbox/`
- Spark — единственный мост `inbox → backlog` (создаёт спеки)
- Autopilot — единственный исполнитель backlog
- Замкнутый цикл: autopilot → QA + Reflect → inbox → spark → backlog → autopilot

```
ВХОДЫ (Telegram: текст, голос, фото+caption, кнопки)
    │
    ▼
ROUTER по проекту (topic_id → project_id)
    │
    ▼
ROUTER по intent (keyword matching)
    ├─ ЛЁГКИЕ (сразу в inbox): spark, spark_bug
    └─ ТЯЖЁЛЫЕ (confirm в TG): architect, council, bughunt
    │
    ▼
╔══════════════════════╗
║    ai/inbox/*.md     ║ ← единая точка входа
╚══════════╤═══════════╝
           │
    orchestrator.sh scan_inbox() → по Route
           │
    ┌──────┼──────────┬──────────────┐
    ▼      ▼          ▼              ▼
  SPARK  ARCHITECT  COUNCIL       BUGHUNT
    │      │          │              │
    ▼      ▼          ▼              ▼
 backlog  inbox/     inbox/        inbox/
 (draft)  +link      +link         (N findings)
    │
    │ Telegram: "Новая спека BUG-123"
    │ [✅ Approve] [✏️ Доработать] [❌ Отмена]
    │
    │ approve → draft → queued
    │ доработать → inbox (spark перечитает)
    │ отмена → rejected
    │
    │ scan_backlog() → первый queued
    ▼
 AUTOPILOT → commit + push develop
    │
    │ pueue-callback
    ▼
 POST-AUTOPILOT (параллельно):
    ├─ QA      → issues? → inbox (spark_bug)
    └─ REFLECT → patterns? → inbox (spark)
```

## Scope

### Task 1: Telegram — обработка скриншотов
**Файл:** `scripts/vps/telegram-bot.py`

Добавить `handle_photo()`:
- Скачать фото через Telegram API (`message.photo[-1].get_file()`)
- Сохранить в `{project}/ai/inbox/img/{timestamp}.jpg`
- Создать inbox file с `![screenshot](img/{timestamp}.jpg)` + caption
- Route определяется по caption через `detect_route()`
- Если caption пуст → Route: spark, текст: "Скриншот без описания, проанализируй"

**Acceptance:**
- Отправить фото с caption в топик проекта → появляется inbox file
- Фото сохраняется в `ai/inbox/img/`, inbox file содержит markdown image link

### Task 2: Router — подтверждение тяжёлых skills
**Файл:** `scripts/vps/telegram-bot.py`

Для routes `architect`, `council`, `bughunt`:
- НЕ создавать inbox file сразу
- Отправить в Telegram: "Запустить {skill} для {project}? Это тяжёлый skill."
- Кнопки: `[Да ✅]` `[Нет ❌]` `[→ Spark]` (переклассифицировать в spark)
- При confirm → создать inbox file
- При reject → ответить "Отменено"
- При → Spark → создать inbox file с Route: spark

**Callback data format:** `confirm_heavy:{project_id}:{route}:{msg_hash}`

Сообщение пользователя сохранять в pending dict (in-memory, TTL 1 час).

**Acceptance:**
- Отправить "консилиум по архитектуре платежей" → получить кнопку подтверждения
- Нажать Да → inbox file создан
- Нажать → Spark → inbox file создан с Route: spark

### Task 3: Spark — headless mode + push
**Файлы:** `template/.claude/skills/spark/SKILL.md`, `completion.md`, `feature-mode.md`

#### 3a: Headless mode
Добавить в SKILL.md секцию "Headless Mode Detection":

```markdown
## Headless Mode

Если в prompt есть маркер `[headless]` или `Source: council|qa|architect|bughunt|reflect`:
- НЕ задавать уточняющих Socratic questions
- Вся информация уже в prompt (от другого skill)
- Если Context: указан — прочитать linked document для полного контекста
- Если не хватает данных — принять решение самостоятельно или эскалировать через /council
- Сохранять способность дёргать council, scout и другие skills при необходимости
```

#### 3b: Push после commit
В `completion.md` после git commit добавить:

```markdown
### Step: Push
After commit, push to develop:
git push origin develop
```

#### 3c: Убрать handoff к autopilot
В `completion.md` убрать блок "Run autopilot?" / Skill("autopilot").
Spark завершается после создания спеки + commit + push.
Оркестратор решает когда запускать autopilot.

#### 3d: CI protection
Добавить в `completion.md` примечание:
```markdown
### CI Note
Projects MUST have `ai/**` in `.github/workflows` paths-ignore.
Otherwise each spark push triggers CI on documentation-only changes.
```

#### 3e: Human-in-the-loop — draft + approve
Spark создаёт спеку в статусе `draft` (не `queued`).
Оркестратор НЕ берёт draft-спеки в autopilot.

После commit + push → Telegram уведомление с summary:

```
📋 Новая спека: BUG-123
Проект: awardybot
Проблема: {1 строка}
Решение: {1-2 строки}
Tasks: {N штук}

[✅ Approve] [✏️ Доработать] [❌ Отмена]
```

**Кнопки:**
- `✅ Approve` → статус `draft → queued` в спеке + backlog, commit + push
- `✏️ Доработать` → Telegram просит комментарий → сохраняет в inbox:
  ```markdown
  Source: human
  Route: spark
  Context: ai/features/BUG-123-....md
  ---
  Доработай спеку BUG-123: {комментарий пользователя}
  ```
  Spark перечитает спеку + комментарий → обновит → снова draft → снова approve
- `❌ Отмена` → статус `draft → rejected`, НЕ удаляет файл

**Файлы:**
- `scripts/vps/telegram-bot.py` — новый callback `handle_confirm_spec`
  (частично уже реализован в `approve_handler.py`)
- `scripts/vps/notify.py` — функция отправки spec summary с кнопками
- `template/.claude/skills/spark/completion.md` — статус draft вместо queued

**Зачем:** без human-in-the-loop reflect и QA могут генерить мусорные спеки
из ложных findings. Пользователь фильтрует перед попаданием в backlog.

**Acceptance:**
- Spark создаёт спеку в статусе draft
- В Telegram приходит summary с кнопками
- Approve → queued → autopilot подхватит
- Доработать → комментарий → spark обновляет → снова draft
- Отмена → rejected, autopilot не трогает
- Spark запущен оркестратором с `[headless]` → не задаёт вопросов, создаёт спеку
- После commit → push develop
- Не вызывает /autopilot

### Task 4: Bughunt — отдельный skill с output в inbox
**Новые файлы:**
- `template/.claude/skills/bughunt/SKILL.md`
- `template/.claude/skills/bughunt/pipeline.md`
- `template/.claude/skills/bughunt/completion.md`

**Файлы для удаления из spark:**
- Убрать Bug Hunt Mode из `spark/bug-mode.md` (оставить Quick Bug Mode)
- Убрать bughunt triggers из `spark/SKILL.md`

#### Архитектура нового skill:

**Input:** описание области для анализа
**Pipeline:** переиспользовать существующих agents из `template/.claude/agents/bug-hunt/`
(scope-decomposer, personas, findings-collector, validator)

**Output:**
- `ai/bughunt/{YYYY-MM-DD}-report.md` — полный отчёт (для контекста)
- N файлов в `ai/inbox/`:
  ```markdown
  # Idea: {timestamp}
  **Source:** bughunt
  **Route:** spark_bug
  **Status:** new
  **Context:** ai/bughunt/{YYYY-MM-DD}-report.md
  ---
  {finding description: что сломано, где, severity, evidence}
  ```
- Commit + push develop

**НЕ создаёт:** спеки, backlog entries (это работа Spark)

**Acceptance:**
- `/bughunt модуль платежей` → отчёт + N inbox files
- Следующий цикл оркестратора → Spark подхватывает findings → спеки → backlog

### Task 5: Council, Architect — output в inbox
**Файлы:**
- `template/.claude/skills/council/SKILL.md`
- `template/.claude/skills/architect/SKILL.md`

#### Council:
После synthesis.md добавить шаг: создать inbox file:
```markdown
# Idea: {timestamp}
**Source:** council
**Route:** spark
**Status:** new
**Context:** ai/.council/{session}/synthesis.md
---
Решение консилиума: {краткое описание решения и рекомендованных действий}
```

Commit + push develop.

#### Architect:
После создания blueprint/session добавить шаг: создать inbox file(s):
```markdown
# Idea: {timestamp}
**Source:** architect
**Route:** spark
**Status:** new
**Context:** ai/architect/{session}.md
---
Архитектурное решение: {краткое описание задачи для реализации}
```

Одна запись на каждое actionable решение. Commit + push develop.

**Acceptance:**
- `/council тема` → synthesis + inbox file → spark подхватит
- `/architect задача` → blueprint + inbox file(s) → spark подхватит

### Task 6: Post-autopilot — QA + Reflect
**Файлы:**
- `scripts/vps/pueue-callback.sh` или `scripts/vps/orchestrator.sh`
- `template/.claude/skills/reflect/SKILL.md`

#### 6a: Автозапуск QA после autopilot
В pueue-callback (или orchestrator при phase transition):
- Когда autopilot завершился с exit_code=0 → phase=qa_pending
- Оркестратор видит qa_pending → запускает `/qa` на изменённые файлы

Это **уже частично реализовано** (dispatch_qa в orchestrator.sh).
Проверить и довести до рабочего состояния.

#### 6b: Автозапуск Reflect после autopilot
В pueue-callback (или orchestrator):
- Когда autopilot завершился → запустить `/reflect` параллельно с QA
- Reflect читает diary, ищет паттерны
- Если находит → пишет в inbox (Route: spark)

#### 6c: Reflect — output в inbox
В `reflect/SKILL.md` изменить финальный шаг:
- Вместо создания TECH-спеки → создать inbox file(s):
```markdown
# Idea: {timestamp}
**Source:** reflect
**Route:** spark
**Status:** new
**Context:** ai/diary/index.md
---
Reflect finding: {описание паттерна и рекомендация}
Частота: {N} occurrences. Evidence: {task_ids}.
```
- Commit + push develop

**Acceptance:**
- Autopilot завершился → QA + Reflect запускаются автоматически
- QA нашёл баги → inbox files (spark_bug)
- Reflect нашёл паттерн → inbox file (spark)
- Следующий цикл → Spark подхватывает

### Task 7: Inbox file format — стандартизация
**Файлы:** все skills + `scripts/vps/telegram-bot.py` + `scripts/vps/inbox-processor.sh`

Единый формат:
```markdown
# Idea: {timestamp}
**Source:** telegram | council | qa | architect | reflect | bughunt
**Route:** spark | spark_bug | architect | council | bughunt
**Status:** new
**Context:** {optional: path to detailed document}
---
{описание}
```

Поле `Context` — опциональная ссылка на подробный документ (synthesis.md, report.md и т.д.).
Spark при обработке **обязан прочитать** linked document если Context указан.

**Acceptance:**
- Все sources создают inbox files в едином формате
- inbox-processor.sh парсит Context field и передаёт в skill prompt
- Spark читает Context document при создании спеки

## Impact Analysis

### Изменяемые файлы:

| Файл | Изменение |
|------|-----------|
| `scripts/vps/telegram-bot.py` | +handle_photo, +confirm_heavy callback |
| `scripts/vps/inbox-processor.sh` | +Context field parsing, передача в prompt |
| `scripts/vps/orchestrator.sh` | +post-autopilot reflect dispatch |
| `scripts/vps/pueue-callback.sh` | +trigger qa+reflect after autopilot |
| `template/.claude/skills/spark/SKILL.md` | +headless mode section |
| `template/.claude/skills/spark/completion.md` | +push, -handoff |
| `template/.claude/skills/spark/feature-mode.md` | +headless skip questions |
| `template/.claude/skills/spark/bug-mode.md` | -bughunt mode (moved out) |
| `template/.claude/skills/bughunt/SKILL.md` | NEW — standalone bughunt skill |
| `template/.claude/skills/bughunt/pipeline.md` | NEW — pipeline steps |
| `template/.claude/skills/bughunt/completion.md` | NEW — inbox output + push |
| `template/.claude/skills/council/SKILL.md` | +inbox output step |
| `template/.claude/skills/architect/SKILL.md` | +inbox output step |
| `template/.claude/skills/reflect/SKILL.md` | inbox output instead of TECH spec |

### Не трогаем:
- `template/.claude/agents/bug-hunt/*` — переиспользуем as-is
- `template/.claude/skills/autopilot/*` — diary уже работает
- `scripts/vps/claude-runner.py` — Agent SDK runner уже готов
- `scripts/vps/run-agent.sh` — уже вызывает claude-runner.py

## Risks

| Risk | Mitigation |
|------|-----------|
| Spark push триггерит CI | Task 3d: projects MUST have `ai/**` in paths-ignore |
| Bughunt генерит 50 findings → 50 inbox files → 50 spark runs | Лимит: max 10 findings в inbox, остальные в отчёте |
| Reflect false positives → мусор в inbox | Порог: только patterns с frequency ≥ 3 |
| Concurrent spark на одном проекте → duplicate IDs | Pueue group parallel=1 per project (уже настроено) |
| Тяжёлые skills (council/bughunt) → rate limit | Confirm кнопка в Telegram фильтрует случайные запуски |
| Reflect/QA генерят мусорные findings → мусорные спеки | Human-in-the-loop: все спеки в draft, approve через Telegram |
| Цикл доработки спеки (draft → доработать → draft) зацикливается | Max 3 итерации, потом blocked + уведомление |

## Execution Order

```
Task 3  (Spark: headless + push + draft + approve - handoff) ← без этого ничего не работает
Task 7  (Inbox format стандартизация)                        ← контракт для всех
Task 4  (Bughunt отдельный skill → inbox)                    ← вынести из spark
Task 5  (Council + Architect → inbox)                        ← интеграция в цикл
Task 1  (Telegram скриншоты)                                 ← новый вход
Task 2  (Router confirm тяжёлых)                             ← safety gate
Task 6  (Post-autopilot QA + Reflect → inbox)                ← замыкание цикла
```

## Test Plan

- [ ] Spark headless: отправить inbox file от council → спека без вопросов
- [ ] Spark push: спека появляется на remote после commit
- [ ] Spark no handoff: spark завершается, не вызывает autopilot
- [ ] Bughunt standalone: `/bughunt` → inbox files, не backlog
- [ ] Council → inbox: после synthesis → inbox file с Context ссылкой
- [ ] Architect → inbox: после session → inbox file(s)
- [ ] Post-autopilot: QA + Reflect запускаются автоматически
- [ ] QA findings → inbox → spark подхватывает
- [ ] Reflect findings → inbox → spark подхватывает
- [ ] Telegram photo: скриншот + caption → inbox file
- [ ] Router confirm: тяжёлый skill → кнопка → confirm → inbox
- [ ] Spec draft: spark создаёт спеку в status: draft, не queued
- [ ] Spec approve: кнопка в Telegram → draft → queued
- [ ] Spec rework: кнопка "Доработать" + комментарий → inbox → spark обновляет
- [ ] Spec reject: кнопка "Отмена" → rejected, autopilot не трогает
- [ ] Rework loop limit: после 3 итераций → blocked
- [ ] Full cycle: telegram msg → spark(draft) → approve → autopilot → QA → inbox → spark → ...
- [ ] CI protection: push с `ai/**` changes не триггерит workflow

## Drift Log

**Checked:** 2026-03-12 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `.claude/skills/spark/completion.md` | DLD copy still has `Status = queued` (line 45) while template has `Status = draft` | AUTO-FIX: will be updated by Task 3 |
| `template/.claude/skills/spark/SKILL.md` | Already has Headless Mode section (lines 47-63) | No action needed (spec wrote it, already applied) |
| `template/.claude/skills/spark/completion.md` | Already has `Status = draft` (line 45, 99) | No action needed (spec wrote it, already applied) |
| `scripts/vps/telegram-bot.py` | 403 LOC — at limit | Caution: Task 1+2 additions must be minimal, use external handler module |
| `scripts/vps/approve_handler.py` | 200 LOC — has room | OK for new handlers |
| `scripts/vps/inbox-processor.sh` | 194 lines — has room | OK for Context field parsing |
| `scripts/vps/orchestrator.sh` | 387 lines — near limit | Must keep additions small |
| `scripts/vps/pueue-callback.sh` | 126 lines — has room | OK for reflect dispatch |
| `template/.claude/skills/bughunt/` | Does NOT exist yet | Will be created by Task 4 |

### References Updated
- Task 3: completion.md already updated in template; DLD copy needs sync
- Task 3: SKILL.md already has Headless Mode in template; DLD copy needs sync

## Detailed Implementation Plan

### Execution Order

```
Task 3  (Spark: headless + push + draft + approve - handoff) -- foundation
   |
Task 7  (Inbox format standardization)                        -- contract
   |
Task 4  (Bughunt standalone skill -> inbox)                    -- extract from spark
   |
Task 5  (Council + Architect -> inbox)                         -- integrate into cycle
   |
Task 1  (Telegram screenshots)                                 -- new input channel
   |
Task 2  (Router confirm heavy skills)                          -- safety gate
   |
Task 6  (Post-autopilot QA + Reflect -> inbox)                 -- close the loop
   |
Task 8  (Template sync: .claude/ <- template/.claude/)         -- AUTO-GENERATED
```

### Dependencies

- Task 7 depends on Task 3 (needs draft status logic established first)
- Task 4 depends on Task 7 (needs standardized inbox format)
- Task 5 depends on Task 7 (needs standardized inbox format)
- Task 1 depends on Task 7 (needs standardized inbox format)
- Task 2 depends on Task 1 (needs photo handling established; both modify telegram-bot.py)
- Task 6 depends on Task 5 (needs reflect inbox output defined)
- Task 8 depends on all template/ changes (Tasks 3, 4, 5, 6)

---

### Task 3: Spark — headless + push + draft status + no handoff

**Files:**
- Modify: `template/.claude/skills/spark/completion.md:180-264`
- Modify: `scripts/vps/approve_handler.py:177-200`
- Modify: `scripts/vps/notify.py:53-68`

**Context:**
Spark must create specs in `draft` status instead of `queued`, push to develop after commit, and NOT hand off to autopilot. The template SKILL.md and completion.md already have headless mode and draft status (lines 47-63 of SKILL.md, line 99 of completion.md). But completion.md still has the Auto-Handoff section (lines 210-243) that asks "Run autopilot?" and the DLD copy still has `queued` at line 45. Also, approve_handler.py needs a new handler for draft-to-queued approval.

**Step 1: Modify `template/.claude/skills/spark/completion.md` — add push + remove handoff**

Replace the Auto-Commit section (lines 180-206) to add `git push origin develop` after commit:

```markdown
## Auto-Commit + Push (MANDATORY before exit!)

After spec file is created and backlog updated — commit and push:

\`\`\`bash
# 1. Stage spec-related changes only (explicit paths, not entire ai/ directory)
git add "ai/features/${TASK_ID}"* ai/backlog.md 2>/dev/null

# 2. Commit locally only if something was staged
# Note: If ai/ is in .gitignore, git add is a no-op (expected)
git diff --cached --quiet || git commit -m "docs: create spec ${TASK_ID}"

# 3. Push to develop (orchestrator needs to see the spec)
git push origin develop 2>/dev/null || true
\`\`\`

**Why push:** Orchestrator runs on VPS, needs git pull to see new specs.
Push failure is non-fatal (spec is safe in local commit).

### CI Note
Projects MUST have `ai/**` in `.github/workflows` paths-ignore.
Otherwise each spark push triggers CI on documentation-only changes.

**When:** ALWAYS before exiting Spark.
```

Replace the Auto-Handoff section (lines 210-243) with:

```markdown
## Exit (NO Handoff)

Spark exits after commit + push. The orchestrator decides when to run autopilot.

**Spark does NOT:**
- Ask "Run autopilot?"
- Invoke Skill tool with `skill: "autopilot"`
- Start any implementation

**What happens next (automated by orchestrator):**
1. Orchestrator sees new spec in `draft` status
2. Sends Telegram notification with summary + approve/reject buttons
3. User approves -> status becomes `queued`
4. Orchestrator's scan_backlog() picks up `queued` spec -> autopilot
```

**Step 2: Add `send_spec_notification()` to `scripts/vps/notify.py`**

Add a new function after `send_to_general()` (after line 72):

```python
async def send_spec_notification(
    project_id: str,
    spec_id: str,
    summary: str,
    scope: str,
    tasks_count: int,
) -> bool:
    """Send spec draft notification with approve/reject/rework buttons.

    Args:
        project_id: Project identifier for topic routing.
        spec_id: Spec ID like BUG-123, FTR-150.
        summary: One-line problem description.
        scope: 1-2 lines of solution scope.
        tasks_count: Number of implementation tasks.

    Returns:
        True if message was sent successfully.
    """
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token or not chat_id:
        print("[notify] Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID", file=sys.stderr)
        return False

    project = db.get_project_state(project_id)
    if project is None:
        print(f"[notify] Project not found: {project_id}", file=sys.stderr)
        return False

    topic_id = project.get("topic_id")
    thread_id = topic_id if topic_id and topic_id != 1 else None

    text = (
        f"New spec: *{spec_id}*\n"
        f"Project: `{project_id}`\n"
        f"Problem: {summary}\n"
        f"Scope: {scope}\n"
        f"Tasks: {tasks_count}\n"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Approve", callback_data=f"spec_approve:{project_id}:{spec_id}"),
            InlineKeyboardButton("Rework", callback_data=f"spec_rework:{project_id}:{spec_id}"),
            InlineKeyboardButton("Reject", callback_data=f"spec_reject:{project_id}:{spec_id}"),
        ]
    ])

    bot = Bot(token=token)
    try:
        await bot.send_message(
            chat_id=int(chat_id),
            message_thread_id=thread_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        print(f"[notify] Failed to send spec notification: {e}", file=sys.stderr)
        return False
    finally:
        await bot.shutdown()
```

Also add CLI support in `main()`. Replace lines 75-85:

```python
def main() -> None:
    """CLI entrypoint: notify.py <project_id> <message> OR notify.py spec <project_id> <spec_id> <summary> <scope> <tasks_count>"""
    if len(sys.argv) >= 2 and sys.argv[1] == "spec":
        if len(sys.argv) != 7:
            print(
                "Usage: notify.py spec <project_id> <spec_id> <summary> <scope> <tasks_count>",
                file=sys.stderr,
            )
            sys.exit(1)
        success = asyncio.run(
            send_spec_notification(
                sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], int(sys.argv[6])
            )
        )
        sys.exit(0 if success else 1)

    if len(sys.argv) < 3:
        print("Usage: notify.py <project_id> <message>", file=sys.stderr)
        sys.exit(1)

    project_id = sys.argv[1]
    message = sys.argv[2]

    success = asyncio.run(send_to_project(project_id, message))
    sys.exit(0 if success else 1)
```

**Step 3: Rewrite `handle_confirm_spec()` in `scripts/vps/approve_handler.py`**

Replace the existing `handle_confirm_spec` (lines 182-199) with three handlers for the new spec approval workflow:

```python
# ---------------------------------------------------------------------------
# Spec draft approve / rework / reject
# ---------------------------------------------------------------------------

# In-memory store for rework state (project:spec -> iteration count)
_rework_iterations: dict[str, int] = {}
MAX_REWORK_ITERATIONS = 3


async def handle_spec_approve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Approve a draft spec: update status draft -> queued in spec file and backlog."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)

    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Project {project_id} not found")
        return

    project_dir = Path(project["path"])

    # Find spec file
    spec_files = list(project_dir.glob(f"ai/features/{spec_id}*"))
    if not spec_files:
        await query.edit_message_text(f"Spec file for {spec_id} not found")
        return
    spec_file = spec_files[0]

    # Update status in spec file: draft -> queued
    content = spec_file.read_text(encoding="utf-8")
    content = content.replace("**Status:** draft", "**Status:** queued", 1)
    spec_file.write_text(content, encoding="utf-8")

    # Update status in backlog
    backlog = project_dir / "ai" / "backlog.md"
    if backlog.exists():
        bl_content = backlog.read_text(encoding="utf-8")
        # Replace draft with queued for this specific spec_id in backlog
        bl_content = bl_content.replace(
            f"| {spec_id} ", f"| {spec_id} "
        ).replace("| draft |", "| queued |", 1)
        backlog.write_text(bl_content, encoding="utf-8")

    # Commit + push the status change
    import subprocess

    subprocess.run(
        ["git", "-C", str(project_dir), "add", "ai/features/", "ai/backlog.md"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(project_dir), "commit", "-m", f"docs: approve spec {spec_id}"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(project_dir), "push", "origin", "develop"],
        capture_output=True,
        timeout=30,
    )

    # Clear rework counter
    _rework_iterations.pop(f"{project_id}:{spec_id}", None)

    await query.edit_message_text(f"Approved {spec_id} -> queued. Autopilot will pick it up.")


async def handle_spec_rework(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Request spec rework: ask for comment, then write to inbox for spark re-processing."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)

    # Check rework iteration limit
    key = f"{project_id}:{spec_id}"
    count = _rework_iterations.get(key, 0) + 1
    if count > MAX_REWORK_ITERATIONS:
        await query.edit_message_text(
            f"Rework limit ({MAX_REWORK_ITERATIONS}) reached for {spec_id}. "
            f"Spec marked as blocked. Please review manually."
        )
        # Mark as blocked in project phase
        db.update_project_phase(project_id, "blocked", spec_id)
        return

    _rework_iterations[key] = count

    # Store pending rework state for follow-up message
    context.bot_data.setdefault("pending_reworks", {})[key] = {
        "project_id": project_id,
        "spec_id": spec_id,
        "iteration": count,
        "message_id": query.message.message_id,
    }

    await query.edit_message_text(
        f"Rework {spec_id} (iteration {count}/{MAX_REWORK_ITERATIONS}).\n"
        f"Reply to this message with your comment for Spark."
    )


async def handle_spec_reject(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reject a draft spec: update status to rejected."""
    query = update.callback_query
    await query.answer()
    _, project_id, spec_id = query.data.split(":", 2)

    project = db.get_project_state(project_id)
    if not project:
        await query.edit_message_text(f"Project {project_id} not found")
        return

    project_dir = Path(project["path"])

    # Find and update spec file
    spec_files = list(project_dir.glob(f"ai/features/{spec_id}*"))
    if spec_files:
        spec_file = spec_files[0]
        content = spec_file.read_text(encoding="utf-8")
        content = content.replace("**Status:** draft", "**Status:** rejected", 1)
        spec_file.write_text(content, encoding="utf-8")

    # Update backlog
    backlog = project_dir / "ai" / "backlog.md"
    if backlog.exists():
        bl_content = backlog.read_text(encoding="utf-8")
        bl_content = bl_content.replace(
            f"| {spec_id} ", f"| {spec_id} "
        ).replace("| draft |", "| rejected |", 1)
        backlog.write_text(bl_content, encoding="utf-8")

    # Commit + push
    import subprocess

    subprocess.run(
        ["git", "-C", str(project_dir), "add", "ai/features/", "ai/backlog.md"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(project_dir), "commit", "-m", f"docs: reject spec {spec_id}"],
        capture_output=True,
        timeout=10,
    )
    subprocess.run(
        ["git", "-C", str(project_dir), "push", "origin", "develop"],
        capture_output=True,
        timeout=30,
    )

    _rework_iterations.pop(f"{project_id}:{spec_id}", None)

    await query.edit_message_text(f"Rejected {spec_id}. Spec will not be executed.")
```

**Step 4: Add rework reply handler to `scripts/vps/telegram-bot.py`**

In `handle_text()` (line 355), before saving to inbox, add rework detection logic:

After `text = update.message.text` (line 364), add:

```python
    # Check if this is a rework comment (reply to rework message)
    pending = context.bot_data.get("pending_reworks", {})
    if update.message.reply_to_message:
        reply_msg_id = update.message.reply_to_message.message_id
        for key, rework in pending.items():
            if rework["message_id"] == reply_msg_id:
                # This is a rework comment — save to inbox with Context link
                pid = rework["project_id"]
                sid = rework["spec_id"]
                proj = db.get_project_state(pid)
                if proj:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                    inbox_dir = Path(proj["path"]) / "ai" / "inbox"
                    inbox_dir.mkdir(parents=True, exist_ok=True)
                    spec_files = list(Path(proj["path"]).glob(f"ai/features/{sid}*"))
                    ctx_path = str(spec_files[0].relative_to(proj["path"])) if spec_files else ""
                    filepath = inbox_dir / f"{ts}-rework-{sid}.md"
                    filepath.write_text(
                        f"# Idea: {ts}\n"
                        f"**Source:** human\n"
                        f"**Route:** spark\n"
                        f"**Status:** new\n"
                        f"**Context:** {ctx_path}\n"
                        f"---\n"
                        f"Rework spec {sid}: {text}\n",
                        encoding="utf-8",
                    )
                    del pending[key]
                    await update.message.reply_text(
                        f"Rework comment saved for {sid}. Spark will update the spec.",
                        parse_mode="Markdown",
                    )
                    return
```

**Step 5: Register new callbacks in `telegram-bot.py` `main()`**

Replace line 391 (`handle_confirm_spec` pattern) with three new patterns:

```python
    application.add_handler(CallbackQueryHandler(handle_spec_approve, pattern=r"^spec_approve:"))
    application.add_handler(CallbackQueryHandler(handle_spec_rework, pattern=r"^spec_rework:"))
    application.add_handler(CallbackQueryHandler(handle_spec_reject, pattern=r"^spec_reject:"))
```

And update the import block (lines 31-39) to import the new handlers:

```python
from approve_handler import (
    handle_approve_all,
    handle_finding_approve,
    handle_finding_reject,
    handle_launch_review,
    handle_project_toggle,
    handle_reject_all,
    handle_spec_approve,
    handle_spec_rework,
    handle_spec_reject,
    register_evening_job,
)
```

**Acceptance Criteria:**
- [ ] `template/.claude/skills/spark/completion.md` has `git push origin develop` after commit
- [ ] `template/.claude/skills/spark/completion.md` does NOT have "Auto-Handoff to Autopilot" section
- [ ] `template/.claude/skills/spark/completion.md` has CI Note about paths-ignore
- [ ] `notify.py` has `send_spec_notification()` function with approve/rework/reject buttons
- [ ] `notify.py` CLI supports `notify.py spec <args>` syntax
- [ ] `approve_handler.py` has `handle_spec_approve`, `handle_spec_rework`, `handle_spec_reject`
- [ ] Rework iteration limit = 3, then blocked
- [ ] `telegram-bot.py` registers three new CallbackQueryHandlers for `spec_approve:`, `spec_rework:`, `spec_reject:`
- [ ] `telegram-bot.py` `handle_text()` detects rework replies and saves to inbox with Context field
- [ ] Old `handle_confirm_spec` removed (replaced by new three handlers)

---

### Task 7: Inbox format standardization

**Files:**
- Modify: `scripts/vps/telegram-bot.py:100-111` (function `_save_to_inbox`)
- Modify: `scripts/vps/inbox-processor.sh:52-97` (metadata extraction + Context parsing)

**Context:**
All inbox files must follow the unified format with Source, Route, Status, Context fields. The existing `_save_to_inbox()` already produces this format (line 107). The inbox-processor.sh needs to parse the new `Context` field and pass it to skill prompts so Spark can read linked documents.

**Step 1: Verify and confirm `_save_to_inbox()` format in `telegram-bot.py`**

The existing implementation at line 106-108 already writes:
```
# Idea: {timestamp}\n**Source:** telegram\n**Route:** {route}\n**Status:** new\n---\n{text}\n
```

This matches the spec format. No changes needed to `_save_to_inbox()` for Telegram source.

**Step 2: Modify `inbox-processor.sh` to parse Context field**

After the existing ROUTE extraction (line 55), add Context extraction:

```bash
# Extract Context field (optional path to detailed document)
CONTEXT_PATH=$(grep -oE '^\*\*Context:\*\* .+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Context:\*\* //' || true)
```

**Step 3: Update route-to-skill mapping to include Context in prompt**

In the `case "$ROUTE"` block (lines 71-97), update all spark/spark_bug routes to include Context:

```bash
case "$ROUTE" in
    spark)
        SKILL="spark"
        if [[ -n "$CONTEXT_PATH" ]]; then
            TASK_CMD="/spark [headless] Context: ${PROJECT_DIR}/${CONTEXT_PATH} --- ${IDEA_TEXT}"
        else
            TASK_CMD="/spark ${IDEA_TEXT}"
        fi
        ;;
    architect)
        SKILL="architect"
        TASK_CMD="/architect ${IDEA_TEXT}"
        ;;
    council)
        SKILL="council"
        TASK_CMD="/council ${IDEA_TEXT}"
        ;;
    spark_bug)
        SKILL="spark"
        if [[ -n "$CONTEXT_PATH" ]]; then
            TASK_CMD="/spark [headless] Context: ${PROJECT_DIR}/${CONTEXT_PATH} --- ${IDEA_TEXT}"
        else
            TASK_CMD="/spark ${IDEA_TEXT}"
        fi
        ;;
    bughunt)
        SKILL="bughunt"
        TASK_CMD="/bughunt ${IDEA_TEXT}"
        ;;
    *)
        echo "[inbox] Unknown route '${ROUTE}', defaulting to spark" >&2
        SKILL="spark"
        TASK_CMD="/spark ${IDEA_TEXT}"
        ;;
esac
```

Key changes:
1. `spark` and `spark_bug` routes now include `[headless]` marker and `Context:` path when available
2. `bughunt` route now dispatches to `bughunt` skill instead of `spark`
3. Source field from inbox items triggers headless mode automatically

**Step 4: Enhance Source detection for headless mode**

After Context extraction, add Source-based headless detection:

```bash
# Extract Source field
SOURCE=$(grep -oE '^\*\*Source:\*\* [^ ]+' "$INBOX_FILE" 2>/dev/null | sed 's/\*\*Source:\*\* //' || echo "telegram")

# Non-human sources trigger headless mode
HEADLESS=""
if [[ "$SOURCE" != "telegram" && "$SOURCE" != "human" ]]; then
    HEADLESS="[headless] Source: ${SOURCE}"
fi
```

Then use `$HEADLESS` in the case block:

```bash
    spark)
        SKILL="spark"
        CTX_ARG=""
        [[ -n "$CONTEXT_PATH" ]] && CTX_ARG="Context: ${PROJECT_DIR}/${CONTEXT_PATH} ---"
        TASK_CMD="/spark ${HEADLESS} ${CTX_ARG} ${IDEA_TEXT}"
        ;;
```

**Acceptance Criteria:**
- [ ] `inbox-processor.sh` extracts `Context:` field from inbox files
- [ ] `inbox-processor.sh` extracts `Source:` field from inbox files
- [ ] Non-human sources (council, qa, architect, bughunt, reflect) add `[headless]` to prompt
- [ ] Context path is passed as absolute path in skill prompt
- [ ] `bughunt` route dispatches to `bughunt` skill (not `spark`)
- [ ] All existing routes still work (spark, architect, council, spark_bug)

---

### Task 4: Bughunt standalone skill with inbox output

**Files:**
- Create: `template/.claude/skills/bughunt/SKILL.md`
- Create: `template/.claude/skills/bughunt/pipeline.md`
- Create: `template/.claude/skills/bughunt/completion.md`
- Modify: `template/.claude/skills/spark/bug-mode.md` (remove Bug Hunt Mode, keep Quick Bug Mode)

**Context:**
Bug Hunt is currently embedded in spark/bug-mode.md (lines 127-670). It needs to be extracted into a standalone skill that writes findings to ai/inbox/ instead of creating specs directly. The existing agents in `template/.claude/agents/bug-hunt/` are reused as-is.

**Step 1: Create `template/.claude/skills/bughunt/SKILL.md`**

```markdown
---
name: bughunt
description: Deep multi-agent bug analysis. Writes findings to ai/inbox/ for Spark processing.
model: opus
---

# Bughunt -- Deep Multi-Agent Bug Analysis

Analyzes codebase for bugs using 6 persona agents, writes findings to inbox.

**Activation:** `/bughunt`, "bug hunt", "deep analysis"

## When to Use

- Complex/systemic bugs affecting many files
- Requested deep analysis of a module or domain
- Night review found issues needing investigation
- User explicitly requests bug hunt

**Not for:** Simple bugs <5 files (use `/spark` Quick Bug Mode), hotfixes

## Architecture

**Input:** Description of area to analyze
**Pipeline:** Reuses existing agents from `agents/bug-hunt/`
(scope-decomposer, personas, findings-collector, validator)

**Output:**
- `ai/bughunt/{YYYY-MM-DD}-report.md` -- full analysis report
- N files in `ai/inbox/` -- one per validated finding (Route: spark_bug)
- Max 10 findings written to inbox (rest stay in report only)

**Does NOT create:** specs, backlog entries (that is Spark's job)

## Pipeline

Read `pipeline.md` for the full multi-agent pipeline steps.

## Completion

Read `completion.md` for output format and commit rules.

## Limits

| Condition | Value |
|-----------|-------|
| Max inbox findings | 10 |
| Min severity for inbox | medium |
| Min confidence for inbox | high |
```

**Step 2: Create `template/.claude/skills/bughunt/pipeline.md`**

```markdown
# Bughunt Pipeline

Steps 0-4 reuse the existing bug-hunt agents. Step 5 writes to inbox.

## Pipeline Overview

\`\`\`
Step 0: scope-decomposer -> zones.yaml
Step 1: 6 personas x N zones -> findings/
Step 2: findings-collector -> summary.yaml
Step 3: validator -> validated findings
Step 4: Write report to ai/bughunt/
Step 5: Write top findings to ai/inbox/ (max 10)
\`\`\`

All steps use `run_in_background: true` (ADR-009).
File gates between steps (ADR-011).
Reuse agents from `agents/bug-hunt/` as-is.

## Steps 0-3: Same as spark/bug-mode.md Steps 0-4

These steps are identical to the Bug Hunt Mode pipeline in spark/bug-mode.md:
- Step 0: Scope decomposition (bughunt-scope-decomposer)
- Step 1: Persona analysis (6 personas x N zones, parallel background)
- Step 2: Collect and normalize findings (bughunt-findings-collector)
- Step 3: Validate and group (bughunt-validator)

See `spark/bug-mode.md` Pipeline Steps section for exact agent dispatch format.

**Key difference:** No spec-assembler (Step 3 of old pipeline) or solution-architect (Step 6).
Bughunt skill stops at validated findings and writes them to inbox.

## Step 4: Write Report

Write full report to `ai/bughunt/{YYYY-MM-DD}-report.md`:

\`\`\`markdown
# Bughunt Report: {target}

**Date:** YYYY-MM-DD
**Target:** {path analyzed}
**Zones:** {N}
**Total findings:** {N}
**Written to inbox:** {M} (top by severity/confidence)

## Findings

### Finding 1: {title}
**Severity:** high | **Confidence:** high
**File:** {path}:{lines}
**Description:** {what is wrong}
**Suggestion:** {how to fix}

### Finding 2: ...
\`\`\`

## Step 5: Write to Inbox (max 10)

Filter findings: severity >= medium AND confidence >= high.
Sort by severity (critical > high > medium), then confidence.
Take top 10.

For each finding, create inbox file:

\`\`\`markdown
# Idea: {timestamp}
**Source:** bughunt
**Route:** spark_bug
**Status:** new
**Context:** ai/bughunt/{YYYY-MM-DD}-report.md
---
Bug finding: {title}
Severity: {severity}, Confidence: {confidence}
File: {path}:{lines}
Description: {description}
Suggestion: {suggestion}
\`\`\`

Filename: `{timestamp}-bughunt-{N}.md` where N is finding index (01, 02, ...).
```

**Step 3: Create `template/.claude/skills/bughunt/completion.md`**

```markdown
# Bughunt Completion

After pipeline completes:

## Commit + Push

\`\`\`bash
# Stage report and inbox files
git add ai/bughunt/ ai/inbox/ 2>/dev/null

# Commit
git diff --cached --quiet || git commit -m "docs: bughunt report + ${N} findings to inbox"

# Push to develop
git push origin develop 2>/dev/null || true
\`\`\`

## Output Format

\`\`\`yaml
status: completed | degraded
target: "{path analyzed}"
findings_total: N
findings_to_inbox: M
report_path: "ai/bughunt/{date}-report.md"
next: "Orchestrator will dispatch Spark for each finding"
\`\`\`

## Rules

- Do NOT create specs (Spark does that)
- Do NOT add backlog entries (Spark does that)
- Do NOT hand off to autopilot
- Commit + push, then exit
```

**Step 4: Modify `template/.claude/skills/spark/bug-mode.md` -- remove Bug Hunt Mode**

Keep everything from line 1 to the end of Quick Bug Mode (line 125: "→ Then go to `completion.md` for ID protocol and handoff.").

Remove the entire Bug Hunt Mode section (lines 127-670). Replace with a redirect:

```markdown
---

# Bug Hunt Mode (MOVED)

Bug Hunt is now a standalone skill: `/bughunt`

**Do NOT run Bug Hunt from Spark.** Use `/bughunt <target>` directly.

Quick Bug Mode remains in Spark for simple bugs (<5 files).
```

Keep the remaining shared content (Bug Research Template, Exact Paths Required, Bug Mode Rules, Pre-Completion Checklist for Quick Bug Mode).

**Acceptance Criteria:**
- [ ] `template/.claude/skills/bughunt/SKILL.md` exists with proper frontmatter
- [ ] `template/.claude/skills/bughunt/pipeline.md` exists with 6-step pipeline
- [ ] `template/.claude/skills/bughunt/completion.md` exists with commit+push rules
- [ ] `template/.claude/skills/spark/bug-mode.md` no longer contains Bug Hunt Mode pipeline
- [ ] `template/.claude/skills/spark/bug-mode.md` has redirect to `/bughunt`
- [ ] Bug Hunt Mode references are removed from spark skill
- [ ] Quick Bug Mode is preserved intact in spark
- [ ] Max 10 findings written to inbox
- [ ] Findings use standard inbox format with Source: bughunt, Route: spark_bug

---

### Task 5: Council and Architect -- output to inbox

**Files:**
- Modify: `template/.claude/skills/council/SKILL.md:369-430` (after Output Format)
- Modify: `template/.claude/skills/architect/SKILL.md:99-112` (After Architect section)

**Context:**
Council and Architect need to create inbox files after their synthesis, so that Spark can pick up actionable decisions and create specs. Currently they produce synthesis.md / blueprint files but don't feed back into the orchestrator cycle.

**Step 1: Add inbox output to `template/.claude/skills/council/SKILL.md`**

After the "After Council" section (line 422), before "## Limits" (line 426), add:

```markdown
## Inbox Output (Orchestrator Integration)

After synthesis is complete, create an inbox file for each actionable decision:

```markdown
# Idea: {timestamp}
**Source:** council
**Route:** spark
**Status:** new
**Context:** {SESSION_DIR}/synthesis.md
---
Council decision: {brief description of decision and recommended actions}
Votes: {summary of votes}. Confidence: {high/medium/low}.
Changes required: {list of changes if any}
```

**Rules:**
- Create inbox file ONLY if decision = approved or needs_changes
- Do NOT create inbox file for rejected decisions
- One inbox file per council session (not per expert)
- Context field links to full synthesis.md
- Commit + push after creating inbox file

```bash
git add ai/.council/ ai/inbox/ 2>/dev/null
git diff --cached --quiet || git commit -m "docs: council synthesis + inbox"
git push origin develop 2>/dev/null || true
```
```

**Step 2: Add inbox output to `template/.claude/skills/architect/SKILL.md`**

After the "After Architect" section (line 99), before the closing of the file, add:

```markdown
## Inbox Output (Orchestrator Integration)

After blueprint is written, create inbox file(s) for each actionable architecture decision:

```markdown
# Idea: {timestamp}
**Source:** architect
**Route:** spark
**Status:** new
**Context:** ai/architect/{session}.md
---
Architecture decision: {brief description of task for implementation}
Domain: {affected domain}
Priority: {P0/P1/P2}
```

**Rules:**
- One inbox file per actionable decision (not one for entire session)
- Only create for decisions that need implementation (not documentation-only)
- Context links to the full architect session document
- Commit + push after creating inbox files

```bash
git add ai/blueprint/ ai/architect/ ai/inbox/ 2>/dev/null
git diff --cached --quiet || git commit -m "docs: architect blueprint + inbox"
git push origin develop 2>/dev/null || true
```
```

**Acceptance Criteria:**
- [ ] Council SKILL.md has "Inbox Output" section after "After Council"
- [ ] Council creates inbox file with Source: council, Route: spark
- [ ] Council links Context to synthesis.md
- [ ] Council commits + pushes after inbox creation
- [ ] Architect SKILL.md has "Inbox Output" section after "After Architect"
- [ ] Architect creates one inbox file per actionable decision
- [ ] Architect links Context to session document
- [ ] Architect commits + pushes after inbox creation

---

### Task 1: Telegram -- photo/screenshot handling

**Files:**
- Create: `scripts/vps/photo_handler.py` (new file, follows voice_handler.py pattern)
- Modify: `scripts/vps/telegram-bot.py:394-396` (register new handler)

**Context:**
Photos with captions need to be saved to inbox with the image file. The handler follows the same pattern as voice_handler.py -- a separate module to keep telegram-bot.py under 400 LOC.

**Step 1: Create `scripts/vps/photo_handler.py`**

```python
#!/usr/bin/env python3
"""
Module: photo_handler
Role: Telegram photo message handler -- saves screenshots to inbox.
Uses: telegram-bot._save_to_inbox, telegram-bot.is_authorized,
      telegram-bot.get_topic_id, telegram-bot.detect_route, db.get_project_by_topic
Used by: telegram-bot (registered as MessageHandler for PHOTO)
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger("dld-bot.photo")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages in project forum topics.

    Downloads the photo, saves to ai/inbox/img/, creates inbox file
    with markdown image link and caption text.
    """
    sys.path.insert(0, str(Path(__file__).parent))
    import db

    tb = sys.modules.get("telegram_bot") or sys.modules.get("__main__")
    is_authorized = tb.is_authorized
    get_topic_id = tb.get_topic_id
    detect_route = tb.detect_route

    if not is_authorized(update.effective_user.id):
        return

    topic_id = get_topic_id(update)
    project = db.get_project_by_topic(topic_id) if topic_id else None
    if not project:
        return

    # Download the highest resolution photo
    photo = update.message.photo[-1]
    tg_file = await photo.get_file()
    photo_bytes = bytes(await tg_file.download_as_bytearray())

    # Save photo to ai/inbox/img/
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    inbox_dir = Path(project["path"]) / "ai" / "inbox"
    img_dir = inbox_dir / "img"
    img_dir.mkdir(parents=True, exist_ok=True)

    img_filename = f"{timestamp}.jpg"
    img_path = img_dir / img_filename
    img_path.write_bytes(photo_bytes)
    logger.info("Saved photo: %s (%d bytes)", img_path, len(photo_bytes))

    # Build inbox text from caption
    caption = update.message.caption or ""
    if caption:
        route = detect_route(caption)
        text = f"![screenshot](img/{img_filename})\n\n{caption}"
    else:
        route = "spark"
        text = (
            f"![screenshot](img/{img_filename})\n\n"
            f"Screenshot without description. Analyze what is shown."
        )

    # Create inbox file
    filepath = inbox_dir / f"{timestamp}-photo.md"
    filepath.write_text(
        f"# Idea: {timestamp}\n"
        f"**Source:** telegram\n"
        f"**Route:** {route}\n"
        f"**Status:** new\n"
        f"---\n"
        f"{text}\n",
        encoding="utf-8",
    )
    logger.info("Saved photo inbox: %s (route=%s)", filepath, route)
    await update.message.reply_text(
        f"Screenshot saved (route: `{route}`).",
        parse_mode="Markdown",
    )
```

**Step 2: Register photo handler in `telegram-bot.py`**

Add import at line 41 (after voice_handler import):

```python
from photo_handler import handle_photo
```

Add handler registration before the TEXT handler (before line 396):

```python
    application.add_handler(
        MessageHandler(filters.PHOTO & filters.ChatType.SUPERGROUP, handle_photo)
    )
```

**Acceptance Criteria:**
- [ ] `photo_handler.py` exists with `handle_photo()` function
- [ ] Photo downloaded from Telegram and saved to `ai/inbox/img/{timestamp}.jpg`
- [ ] Inbox file created with markdown image link `![screenshot](img/{timestamp}.jpg)`
- [ ] Caption used as description text; if empty, default text added
- [ ] Route detected from caption via `detect_route()`
- [ ] Handler registered in telegram-bot.py for PHOTO & SUPERGROUP filter
- [ ] `telegram-bot.py` stays under 400 LOC (only 2 lines added: import + handler)

---

### Task 2: Router -- confirmation for heavy skills

**Files:**
- Modify: `scripts/vps/telegram-bot.py:355-372` (function `handle_text`)
- Modify: `scripts/vps/approve_handler.py` (add heavy skill confirmation handlers)

**Context:**
When a user sends a message that routes to `architect`, `council`, or `bughunt`, the bot should NOT immediately create an inbox file. Instead, it asks for confirmation with buttons, since these skills are expensive and long-running.

**Step 1: Modify `handle_text()` in `telegram-bot.py`**

Replace the current `handle_text()` (lines 355-372) with:

```python
HEAVY_ROUTES = {"architect", "council", "bughunt"}

# In-memory pending messages for heavy skill confirmation (TTL managed by dict size)
_pending_heavy: dict[str, dict] = {}
MAX_PENDING = 50  # Prevent memory leak


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_authorized(update.effective_user.id):
        return
    topic_id = get_topic_id(update)
    if not topic_id:
        return
    project = db.get_project_by_topic(topic_id)
    if not project:
        return
    text = update.message.text
    if not text or text.startswith("/"):
        return

    # Check if this is a rework comment (reply to rework message)
    pending_reworks = context.bot_data.get("pending_reworks", {})
    if update.message.reply_to_message:
        reply_msg_id = update.message.reply_to_message.message_id
        for key, rework in list(pending_reworks.items()):
            if rework["message_id"] == reply_msg_id:
                pid = rework["project_id"]
                sid = rework["spec_id"]
                proj = db.get_project_state(pid)
                if proj:
                    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
                    inbox_dir = Path(proj["path"]) / "ai" / "inbox"
                    inbox_dir.mkdir(parents=True, exist_ok=True)
                    spec_files = list(Path(proj["path"]).glob(f"ai/features/{sid}*"))
                    ctx_path = str(spec_files[0].relative_to(proj["path"])) if spec_files else ""
                    filepath = inbox_dir / f"{ts}-rework-{sid}.md"
                    filepath.write_text(
                        f"# Idea: {ts}\n"
                        f"**Source:** human\n"
                        f"**Route:** spark\n"
                        f"**Status:** new\n"
                        f"**Context:** {ctx_path}\n"
                        f"---\n"
                        f"Rework spec {sid}: {text}\n",
                        encoding="utf-8",
                    )
                    del pending_reworks[key]
                    await update.message.reply_text(
                        f"Rework comment saved for {sid}.",
                        parse_mode="Markdown",
                    )
                    return

    route = detect_route(text)

    if route in HEAVY_ROUTES:
        # Heavy skill -- ask for confirmation
        import hashlib

        msg_hash = hashlib.md5(text.encode()).hexdigest()[:8]
        _pending_heavy[msg_hash] = {
            "project_id": project["project_id"],
            "text": text,
            "route": route,
        }
        # Evict old entries
        while len(_pending_heavy) > MAX_PENDING:
            _pending_heavy.pop(next(iter(_pending_heavy)))

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Yes", callback_data=f"confirm_heavy:{msg_hash}:yes"),
                InlineKeyboardButton("No", callback_data=f"confirm_heavy:{msg_hash}:no"),
                InlineKeyboardButton("-> Spark", callback_data=f"confirm_heavy:{msg_hash}:spark"),
            ]
        ])
        skill_label = {"architect": "Architect", "council": "Council", "bughunt": "Bug Hunt"}
        await update.message.reply_text(
            f"Run *{skill_label.get(route, route)}* for `{project['project_id']}`?\n"
            f"This is a heavy skill (long runtime, higher cost).",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )
        return

    _save_to_inbox(project, text)
    await update.message.reply_text(
        f"Saved to inbox (route: `{route}`).\nOrchestrator will process on next cycle.",
        parse_mode="Markdown",
    )
```

**Step 2: Add heavy skill confirmation handler to `approve_handler.py`**

Add after the spec reject handler:

```python
async def handle_confirm_heavy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle confirmation for heavy skills (architect, council, bughunt)."""
    query = update.callback_query
    await query.answer()
    _, msg_hash, action = query.data.split(":", 2)

    # Access pending from telegram-bot module
    tb = sys.modules.get("telegram_bot") or sys.modules.get("__main__")
    pending = getattr(tb, "_pending_heavy", {})

    entry = pending.pop(msg_hash, None)
    if not entry:
        await query.edit_message_text("Expired (message too old).")
        return

    project = db.get_project_state(entry["project_id"])
    if not project:
        await query.edit_message_text(f"Project {entry['project_id']} not found.")
        return

    if action == "no":
        await query.edit_message_text("Cancelled.")
        return

    # Determine route: original or reclassified to spark
    route = "spark" if action == "spark" else entry["route"]

    # Create inbox file
    _save = getattr(tb, "_save_to_inbox", None)
    if action == "spark":
        # Override route by modifying text to avoid re-detection
        _save(project, entry["text"])
    else:
        # Save with original heavy route
        from datetime import datetime, timezone
        from pathlib import Path

        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        inbox_dir = Path(project["path"]) / "ai" / "inbox"
        inbox_dir.mkdir(parents=True, exist_ok=True)
        filepath = inbox_dir / f"{ts}-telegram.md"
        filepath.write_text(
            f"# Idea: {ts}\n"
            f"**Source:** telegram\n"
            f"**Route:** {route}\n"
            f"**Status:** new\n"
            f"---\n"
            f"{entry['text']}\n",
            encoding="utf-8",
        )

    label = "Spark" if action == "spark" else route.capitalize()
    await query.edit_message_text(f"Confirmed -> {label}. Saved to inbox.")
```

**Step 3: Register the handler in telegram-bot.py**

Add to imports from approve_handler:

```python
from approve_handler import (
    ...
    handle_confirm_heavy,
    ...
)
```

Add callback handler before the generic text handler:

```python
    application.add_handler(CallbackQueryHandler(handle_confirm_heavy, pattern=r"^confirm_heavy:"))
```

**Acceptance Criteria:**
- [ ] Messages routing to architect/council/bughunt show confirmation buttons
- [ ] "Yes" button creates inbox file with original route
- [ ] "No" button cancels without creating inbox file
- [ ] "-> Spark" button creates inbox file with Route: spark
- [ ] Pending messages stored in memory with max 50 entries (eviction)
- [ ] Non-heavy routes (spark, spark_bug) still save to inbox immediately
- [ ] Callback handler registered for `confirm_heavy:` pattern

---

### Task 6: Post-autopilot QA + Reflect -> inbox

**Files:**
- Modify: `scripts/vps/pueue-callback.sh:74-85` (add reflect dispatch after autopilot)
- Modify: `scripts/vps/orchestrator.sh:300-327` (enhance dispatch_qa to also dispatch reflect)
- Modify: `template/.claude/skills/reflect/SKILL.md:105-183` (inbox output instead of TECH spec)

**Context:**
After autopilot completes, QA is already dispatched via qa_pending phase. But Reflect is not dispatched at all. The cycle needs both QA and Reflect to run post-autopilot, with their findings feeding back into inbox.

**Step 1: Modify `template/.claude/skills/reflect/SKILL.md` -- inbox output**

Replace Step 5 (lines 106-172) "Create Spec" with inbox output:

```markdown
### Step 5: Write to Inbox (NOT direct spec creation!)

**CRITICAL:** Reflect does NOT create TECH specs directly. It writes findings to inbox.
Spark will create specs from reflect findings.

For each pattern found (frequency >= 3):

**Location:** `ai/inbox/{timestamp}-reflect-{N}.md`

**Format:**
\`\`\`markdown
# Idea: {timestamp}
**Source:** reflect
**Route:** spark
**Status:** new
**Context:** ai/diary/index.md
---
Reflect finding: {description of pattern and recommendation}
Frequency: {N} occurrences. Evidence: {task_ids}.
Pattern type: {user_preference | failure_pattern | design_decision | tool_workflow}
Proposed action: {what should change}
\`\`\`

**Rules:**
- Only patterns with frequency >= 3 get inbox files
- Patterns with frequency 2 are noted in diary but NOT sent to inbox
- Max 5 inbox files per reflect session (prioritize by frequency)
- One inbox file per pattern (not per diary entry)
- Context links to diary index for full evidence

### Step 5.5: Commit + Push

\`\`\`bash
git add ai/diary/ ai/inbox/ ai/reflect/ 2>/dev/null
git diff --cached --quiet || git commit -m "docs: reflect synthesis + inbox findings"
git push origin develop 2>/dev/null || true
\`\`\`
```

Also update Step 6 Output format:

```markdown
### Step 6: Output

\`\`\`yaml
entries_analyzed: N
patterns_found:
  - "Pattern 1 (frequency: N)"
  - "Pattern 2 (frequency: N)"
inbox_files_created: M
next_action: "Orchestrator will dispatch Spark for each finding"
\`\`\`
```

Remove the "What NOT to Do" section about creating specs and the "After skill-creator" section. Replace with:

```markdown
---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Create TECH spec directly | Write to inbox -> Spark creates spec |
| Edit CLAUDE.md directly | Write to inbox -> Spark -> skill-creator |
| Mark entries done immediately | Mark after Spark processes findings |
| Write all patterns to inbox | Only frequency >= 3, max 5 files |
```

**Step 2: Add reflect dispatch to `scripts/vps/orchestrator.sh`**

**LOC WARNING:** orchestrator.sh is at 387 lines. Adding dispatch_reflect (~35 lines) pushes it to ~423. To stay under 400 LOC limit, remove the `nexus_ctx` block (lines 221-226 in scan_backlog) which reads unused cache -- saves 6 lines. Also compact the inline python3 calls in dispatch_qa/dispatch_reflect by combining the two python3 calls into one (saves ~8 lines). Target: stay at or under 400 LOC.

After the existing `dispatch_qa()` function (line 327), add:

```bash
# ---------------------------------------------------------------------------
# Dispatch reflect after autopilot (parallel with QA)
# ---------------------------------------------------------------------------

dispatch_reflect() {
    local project_id="$1" project_dir="$2"

    local phase
    phase=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${project_id}')
print(state['phase'] if state else '')
" 2>/dev/null || true)

    # Reflect runs in parallel with QA on qa_pending or qa_running phase
    [[ "$phase" != "qa_pending" && "$phase" != "qa_running" ]] && return

    # Check if diary has pending entries (min 3 for reflect to be useful)
    local diary_index="${project_dir}/ai/diary/index.md"
    [[ ! -f "$diary_index" ]] && return

    local pending_count
    pending_count=$(grep -c '| pending |' "$diary_index" 2>/dev/null || echo "0")
    if (( pending_count < 3 )); then
        log_json "info" "reflect skipped: not enough diary entries" "project" "$project_id" "pending" "$pending_count"
        return
    fi

    # Resolve provider
    local provider
    provider=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}')
import db
state = db.get_project_state('${project_id}')
print(state['provider'] if state else 'claude')
" 2>/dev/null || echo "claude")

    local pueue_group="${provider}-runner"
    local task_label="${project_id}:reflect-$(date '+%Y%m%d')"

    log_json "info" "dispatching reflect" "project" "$project_id" "pending_entries" "$pending_count"

    pueue add \
        --group "$pueue_group" \
        --label "$task_label" \
        -- "${SCRIPT_DIR}/run-agent.sh" "$project_dir" "$provider" "reflect" "/reflect" 2>/dev/null || {
        log_json "warn" "reflect dispatch failed" "project" "$project_id"
    }
}
```

**Step 3: Call `dispatch_reflect()` in `process_project()`**

In the `process_project()` function (line 333), add Step 5 after dispatch_qa:

```bash
    # Step 5: dispatch reflect if diary has enough entries
    dispatch_reflect "$project_id" "$project_dir"
```

**Step 4: Verify QA failure inbox format in `qa-loop.sh`**

The existing qa-loop.sh (lines 87-97) already writes QA failures to inbox with the correct format. Verify it has Source and Context fields. The current format is:

```
**Source:** qa-dispatch
**Route:** spark_bug
**Status:** new
```

This needs a small update to match the standardized format. Add Context field pointing to the spec:

In qa-loop.sh, replace the inbox file creation block (lines 87-97) with:

```bash
    cat > "${INBOX_DIR}/${TIMESTAMP}-qa-fail.md" << EOF
# Idea: ${TIMESTAMP}
**Source:** qa
**Route:** spark_bug
**Status:** new
**Context:** ${SPEC_FILE#${PROJECT_DIR}/}
---
QA failed for ${SPEC_ID}. Exit code: ${QA_EXIT}.
Please investigate and fix the issues found during QA.
EOF
```

Note: Changed `Source: qa-dispatch` to `Source: qa` for consistency, and added `Context:` field with relative spec path.

**Acceptance Criteria:**
- [ ] Reflect SKILL.md writes to inbox instead of creating TECH specs
- [ ] Reflect uses frequency >= 3 threshold for inbox files
- [ ] Reflect max 5 inbox files per session
- [ ] Reflect inbox files have Source: reflect, Route: spark
- [ ] Reflect commits + pushes after inbox creation
- [ ] orchestrator.sh has `dispatch_reflect()` function
- [ ] Reflect is dispatched in parallel with QA on qa_pending phase
- [ ] Reflect requires min 3 pending diary entries to run
- [ ] QA failure inbox files have standardized format with Context field

---

### Task 8: Template sync (.claude/ <- template/.claude/)

**Type:** sync
**Files:**
- sync: `.claude/skills/spark/SKILL.md` <- `template/.claude/skills/spark/SKILL.md`
- sync: `.claude/skills/spark/completion.md` <- `template/.claude/skills/spark/completion.md`
- sync: `.claude/skills/spark/bug-mode.md` <- `template/.claude/skills/spark/bug-mode.md`
- sync: `.claude/skills/spark/feature-mode.md` <- `template/.claude/skills/spark/feature-mode.md`
- create: `.claude/skills/bughunt/SKILL.md` <- `template/.claude/skills/bughunt/SKILL.md`
- create: `.claude/skills/bughunt/pipeline.md` <- `template/.claude/skills/bughunt/pipeline.md`
- create: `.claude/skills/bughunt/completion.md` <- `template/.claude/skills/bughunt/completion.md`

**Steps:**

```bash
# Spark skill files
cp template/.claude/skills/spark/SKILL.md .claude/skills/spark/SKILL.md
cp template/.claude/skills/spark/completion.md .claude/skills/spark/completion.md
cp template/.claude/skills/spark/bug-mode.md .claude/skills/spark/bug-mode.md
cp template/.claude/skills/spark/feature-mode.md .claude/skills/spark/feature-mode.md

# Bughunt skill (new directory)
mkdir -p .claude/skills/bughunt
cp template/.claude/skills/bughunt/SKILL.md .claude/skills/bughunt/SKILL.md
cp template/.claude/skills/bughunt/pipeline.md .claude/skills/bughunt/pipeline.md
cp template/.claude/skills/bughunt/completion.md .claude/skills/bughunt/completion.md
```

Note: Council and Architect SKILL.md are NOT synced to .claude/ because
the DLD project does not have local copies of those (they are read from
template/.claude/ by default). The reflect SKILL.md is also only in template/.

**Acceptance:**
- [ ] `diff template/.claude/skills/spark/SKILL.md .claude/skills/spark/SKILL.md` = empty
- [ ] `diff template/.claude/skills/spark/completion.md .claude/skills/spark/completion.md` = empty
- [ ] `diff template/.claude/skills/spark/bug-mode.md .claude/skills/spark/bug-mode.md` = empty
- [ ] `.claude/skills/bughunt/` directory exists with 3 files

---

### Research Sources

- [python-telegram-bot Photo handling](https://docs.python-telegram-bot.org/en/stable/telegram.message.html#telegram.Message.photo) -- Photo array, get_file(), download_as_bytearray()
- [python-telegram-bot filters.PHOTO](https://docs.python-telegram-bot.org/en/stable/telegram.ext.filters.html#telegram.ext.filters.PHOTO) -- Filter for photo messages
- [InlineKeyboardMarkup](https://docs.python-telegram-bot.org/en/stable/telegram.inlinekeyboardmarkup.html) -- Used for approve/reject/rework buttons
