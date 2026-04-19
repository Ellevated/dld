# External Research — TECH-165: Anthropic Pipeline Optimization

**Scout:** External Research Scout
**Date:** 2026-04-18
**Primary source:** `ai/research/2026-04-18-anthropic-updates-pipeline-optimization.md` (5 параллельных скаутов)
**Note:** Exa credits исчерпаны, web-поиск недоступен. Анализ основан на первичном research-отчёте + прямом чтении кода (`claude-runner.py`, agent frontmatter, `model-capabilities.md`). По каждому пункту указан уровень уверенности.

---

## Ответы по 7 пунктам

---

### Пункт 1: SDK 0.1.48 → 0.1.63 — шаги upgrade и breaking changes

**Статус первичного отчёта:** частично раскрыт (версии перечислены, шаги — нет)

#### Анализ текущего кода

`claude-runner.py` использует следующие импорты из `claude_agent_sdk`:

```python
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TaskNotificationMessage,
    query,
)
from claude_agent_sdk._errors import CLIConnectionError, ProcessError
```

`ClaudeAgentOptions` получает:
- `cwd`, `setting_sources`, `allowed_tools`, `permission_mode`, `max_turns`, `env`

НЕ использует: `temperature`, `top_p`, `thinking`, `budget_tokens` — риск breaking changes минимален.

#### Шаги upgrade

```bash
# 1. Активировать venv
source /home/dld/projects/dld/scripts/vps/venv/bin/activate

# 2. Проверить текущую версию
pip show claude-agent-sdk | grep Version

# 3. Upgrade
pip install --upgrade "claude-agent-sdk==0.1.63"

# 4. Проверить импорты не сломались
python3 -c "
from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TaskNotificationMessage, query
from claude_agent_sdk._errors import CLIConnectionError, ProcessError
print('OK: all imports intact')
"

# 5. Проверить новые поля ClaudeAgentOptions (0.1.57+)
python3 -c "
from claude_agent_sdk import ClaudeAgentOptions
import inspect
print(inspect.signature(ClaudeAgentOptions.__init__))
"

# 6. Smoke test (короткая задача)
python3 /home/dld/projects/dld/scripts/vps/claude-runner.py \
    /home/dld/projects/dld "echo test" "autopilot"
```

#### Ожидаемые новые поля в ClaudeAgentOptions (0.1.57+, из отчёта)

| Поле | Версия | Применимость для нас |
|------|--------|----------------------|
| `permission_mode="auto"` | 0.1.57 | Сейчас используем `bypassPermissions` — не ломает |
| `exclude_dynamic_sections=True` | 0.1.57 | НОВОЕ — позволяет убрать cwd/git из system prompt → лучше кэшируется |
| `skills=[...]` | 0.1.62 | НОВОЕ — но мы запускаем скиллы через prompt prefix (`/spark task`) |

#### Breaking changes между 0.1.48 и 0.1.63

**Подтверждено из отчёта:**
- `setting_sources=[]` в 0.1.48 молча игнорировался (теперь реально отключает настройки) — мы используем `["user", "project"]`, поэтому не ломает
- Thinking mapping bugfix в 0.1.57 — мы НЕ передаём `thinking` параметры, не ломает

**Не подтверждено web-поиском** (Exa недоступен): точный список переименованных импортов между 0.1.48 и 0.1.63. Рекомендую после upgrade запустить `pip show claude-agent-sdk` и проверить CHANGELOG в `venv/lib/python*/site-packages/claude_agent_sdk-*/`.

**Уверенность:** Medium — анализ кода показывает низкий риск, но точный SDK changelog не верифицирован.

---

### Пункт 2: Thinking bugfix в 0.1.57 — эффект на подписку

**Статус первичного отчёта:** описан как "критичный bugfix", но эффект не раскрыт

#### Что именно было сломано

Из отчёта: `adaptive`/`disabled` неверно конвертировался в `--max-thinking-tokens` вместо `--thinking`. Это означало, что Claude Code CLI получал некорректный аргумент и либо:
- (a) игнорировал thinking параметр → думал дефолтно (unknown baseline)
- (b) ошибался и думал меньше чем нужно

#### Эффект после фикса на подписку

**Ключевой вопрос:** у нас `claude-runner.py` НЕ передаёт `thinking` параметры в `ClaudeAgentOptions`. Значит:

- Мы не задействуем ни правильный, ни сломанный thinking mapping
- На нас этот bugfix **прямого влияния не имеет**
- Но агенты, которые сами запрашивают `max` effort через frontmatter (planner, council), используют thinking через CLI flags напрямую (не через SDK `thinking` параметр)

**Если бы мы использовали SDK thinking parameter:**
- До фикса: thinking мог идти с неверным budget → либо overdraft токенов (если бесконечный лимит) либо underspend (если 0)
- После фикса: thinking работает как указано → для `adaptive` — модель сама решает, для `max` — максимальный бюджет

**На подписке (flat fee):** латентность была бы нестабильной до фикса. После — предсказуема. Для нас нейтрально, т.к. thinking не настраиваем через SDK.

**Уверенность:** High (анализ кода показывает что мы вне затронутого кода пути).

---

### Пункт 3: xhigh effort — где задавать в Agent SDK

**Статус первичного отчёта:** упомянут, место задания не раскрыто

#### В Agent SDK (через ClaudeAgentOptions)

Из отчёта (section 3, migration):
```python
output_config={"effort": "xhigh"}
```

Это поле `output_config` в `ClaudeAgentOptions`. Текущий `claude-runner.py` его НЕ использует — значит агенты работают на дефолтном effort (обычно `high` или `medium` в зависимости от модели).

#### В subagent frontmatter (через Claude Code)

Из отчёта (section 5, Subagent Frontmatter):
```yaml
---
name: planner
model: opus
effort: xhigh   # НОВОЕ поле (требует Claude Code 2.1.111+ и SDK 0.1.60+)
maxTurns: 30
---
```

Это **предпочтительный способ** для DLD — effort задаётся декларативно в агентном файле, не в коде runner'а.

#### Через CLI flag

```bash
claude --effort xhigh --print "..."
```

Применимо если вызывать напрямую, без SDK.

#### Текущее состояние в DLD

Проверено по файлам:
- `council/synthesizer.md`: `effort: max` — frontmatter уже содержит effort
- `spark/facilitator.md`: `effort: max` — аналогично

Т.е. frontmatter-подход уже используется. Для xhigh достаточно изменить значение в `.md` файлах агентов. Но **xhigh работает только на Opus 4.7** — на текущем Opus 4.6 поле будет игнорироваться или вернёт ошибку.

**Источник:** первичный отчёт, section 3 + section 5 (Subagent Frontmatter).
**Уверенность:** Medium — API shape подтверждён отчётом, но конкретная версия SDK в которой `output_config.effort` появился в ClaudeAgentOptions не верифицирован через реальный changelog.

---

### Пункт 4: Rate limits на Claude Code Max subscription

**Статус первичного отчёта:** НЕ раскрыт (отчёт фокусировался на per-token API billing)

#### Что известно (из первичных знаний модели, август 2025)

Claude Code Max subscription (на момент знаний модели):
- **Не имеет** опубликованных числовых rate limits в token/hour единицах
- Лимиты реализованы как **fair use** с rate limiting при аномальной нагрузке
- Anthropic применяет throttling когда один пользователь потребляет непропорционально много compute в рамках подписки
- Opus-вызовы "тяжелее" с точки зрения compute → меньше Opus = дольше до throttling

#### Практический вывод для DLD

- **Нет публичного числового лимита** (в отличие от API tier с RPM/TPM)
- Снижение числа Opus-вызовов (перевод 5 агентов на Sonnet) снижает compute-нагрузку → меньше вероятность throttling в длинных autopilot-сессиях
- Task Budgets (из отчёта) помогут ограничить runway одной сессии, освобождая compute для параллельных

#### Рекомендация

Искать лимиты в: `claude.ai/settings` → Usage / Limits (если отображается для Max) или Anthropic Support. Официальная документация по Max-subscription limits на апрель 2026 через web недоступна (Exa кредиты исчерпаны).

**Уверенность:** Low — конкретные лимиты не верифицированы. Известно только общее поведение.

---

### Пункт 5: ENABLE_PROMPT_CACHING_1H — env var или SDK параметр?

**Статус первичного отчёта:** упомянут как env var Claude Code

#### Это Claude Code CLI env var

Из отчёта (section 4):
```bash
ENABLE_PROMPT_CACHING_1H=1   # 1-часовой TTL
FORCE_PROMPT_CACHING_5M=1    # форсировать 5-минутный TTL
```

Это **переменные окружения для Claude Code CLI процесса**, не параметры Agent SDK.

#### Как передать через claude-runner.py

В текущем коде runner'а `env` dict передаётся в `ClaudeAgentOptions`:
```python
options = ClaudeAgentOptions(
    ...
    env={
        "PROJECT_DIR": str(project_path),
        "CLAUDE_PROJECT_DIR": str(project_path),
        "CLAUDE_CURRENT_SPEC_PATH": ...,
        # ДОБАВИТЬ:
        "ENABLE_PROMPT_CACHING_1H": "1",
    },
)
```

Или установить на уровне shell окружения VPS (в `scripts/vps/.env` или systemd unit).

#### Как проверить что кэш работает

В `claude-runner.py` уже есть логирование `ResultMessage`. После включения добавить:
```python
if isinstance(message, ResultMessage):
    usage = getattr(message, "usage", None)
    if usage:
        cache_read = getattr(usage, "cache_read_input_tokens", 0)
        cache_write = getattr(usage, "cache_creation_input_tokens", 0)
        logger.info("cache_read=%d cache_write=%d", cache_read, cache_write)
```

#### Влияет ли на подписку?

Prompt caching — это серверная оптимизация **на стороне Anthropic**. Для per-token API она снижает стоимость. Для flat-fee подписки:
- Кэш снижает compute на сервере → меньше шанс throttling
- Снижает латентность (cache hit быстрее inference)
- **Кэш per-account**, не shared между пользователями подписки

Для подписки основная польза — **латентность** и **снижение compute-нагрузки** (что откладывает throttling в длинных пайплайнах).

**Уверенность:** Medium — механизм env var подтверждён отчётом; влияние на flat-fee vs per-token — логический вывод, не верифицировано документацией.

---

### Пункт 6: Managed Agents (beta) — доступны ли на Max-подписке?

**Статус первичного отчёта:** упомянут как "$0.08/active session-час" + "стандартные токены"

#### Вывод из ценовой модели

Из отчёта: "стандартные API tokens + $0.08/active session-час"

Это **однозначно API-only продукт**:
- Max-подписка — flat fee, нет механизма добавочной оплаты $0.08/session
- API billing допускает дополнительные тарифные компоненты
- Beta-доступ через `X-Beta: managed-agents-2026-04-08` header → только в API calls

#### Для DLD (Claude Code Max + self-hosted pueue)

Managed Agents **недоступны** в рамках текущей подписки. Для использования потребуется:
1. Переключиться на API-доступ (или иметь оба)
2. Платить per-token + $0.08/session

**Вывод из отчёта** (section 6): "POC имеет смысл в отдельном спринте, но не критично — self-hosted работает". Это корректная оценка — на Max-подписке Managed Agents недоступны архитектурно.

**Уверенность:** High — ценовая модель однозначно указывает на API-only.

---

### Пункт 7: Migration checklist для Opus 4.7 на подписке — нужно ли что-то делать?

**Статус первичного отчёта:** раскрыт для API-пути, не для CLI-пути

#### Как DLD вызывает Claude

`claude-runner.py` → `ClaudeAgentOptions` → Agent SDK → **Claude Code CLI** (бинарь)

Claude Code CLI — это **не прямой API клиент**. Он сам управляет model routing, API calls, параметрами запроса. Пользователь не передаёт `temperature`, `thinking.budget_tokens` и т.д. напрямую.

#### Что это означает для Opus 4.7 breaking changes

| Breaking change | Путь воздействия | DLD затронут? |
|----------------|-----------------|---------------|
| `temperature`/`top_p` удалены | Прямые API calls | **Нет** — мы не вызываем API напрямую |
| `thinking.budget_tokens` удалено | Прямые API calls + SDK `thinking` param | **Нет** — `claude-runner.py` не передаёт `thinking` |
| Assistant prefills удалены | Прямые API calls | **Нет** — уже ADR-006 |
| Model ID `claude-opus-4-7` | В agent frontmatter `model:` поле | **Да** — нужно обновить `model: opus` → уточнить маппинг |

#### Маппинг model alias в Claude Code

Claude Code CLI использует алиасы (`opus`, `sonnet`, `haiku`) которые он сам резолвит в актуальные model IDs. Проверить текущий маппинг:

```bash
claude --help | grep -i model
# или
cat ~/.claude/settings.json | grep -i model
```

Если `model: opus` в frontmatter маппится на `claude-opus-4-6` сейчас — после обновления Claude Code CLI он будет маппить на `claude-opus-4-7` автоматически. **Ручная миграция model IDs не требуется** если используем алиасы.

#### Что нужно сделать

1. Убедиться что frontmatter использует **алиасы** (`opus`, `sonnet`), не hardcoded IDs — **уже так в коде** (проверено: `model: opus` в synthesizer.md и facilitator.md)
2. После upgrade Claude Code CLI (`npm install -g @anthropic-ai/claude-code`) алиасы автоматически переключатся на 4.7
3. Протестировать одну сессию с planner (max effort) — это самый "тяжёлый" агент

**Уверенность:** High для "алиасы работают автоматически"; Medium для конкретного поведения CLI при model upgrade.

---

## Best Practices (подтверждённые из кода)

### 1. Exclude dynamic sections для prompt caching
Добавить `exclude_dynamic_sections=True` в `ClaudeAgentOptions` (доступно с 0.1.57). Убирает cwd и git status из system prompt → промпт становится статичным → кэшируется.

### 2. Effort в frontmatter, не в runner
Текущий подход (effort: max/high в `.md` файлах) — правильный. Не дублировать в `output_config` в runner'е. SSOT = frontmatter.

### 3. Smoke test после SDK upgrade
Перед деплоем на VPS: запустить `claude-runner.py` с короткой задачей (`echo test`) и проверить JSON output. Это занимает 30 секунд и ловит import errors сразу.

---

## Libraries/Tools

| Компонент | Текущая версия | Целевая версия | Изменения | Риск |
|-----------|---------------|----------------|-----------|------|
| claude-agent-sdk | 0.1.48 | 0.1.63 | thinking bugfix, exclude_dynamic_sections, permission_mode="auto", skills param | Low — наш код не использует затронутые параметры |
| Claude Code CLI | неизвестно | 2.1.111+ | Opus 4.7 support, xhigh effort, nativе binary | Low — алиасы автоматически обновляются |

**Рекомендация:** Upgrade SDK первым, без изменений кода. Затем добавить `exclude_dynamic_sections=True` и logging кэша. Затем перевести 5 агентов на Sonnet.

---

## Key Decisions Supported by Research

1. **Decision:** SDK upgrade НЕ требует изменения импортов в claude-runner.py
   **Evidence:** Прямой анализ кода — используемые импорты (`query`, `ClaudeAgentOptions`, `AssistantMessage`, `ResultMessage`, `TaskNotificationMessage`, `CLIConnectionError`, `ProcessError`) стабильны между версиями по данным отчёта
   **Confidence:** Medium

2. **Decision:** Thinking bugfix (0.1.57) нас не затрагивает
   **Evidence:** `claude-runner.py` не передаёт `thinking` параметры в ClaudeAgentOptions
   **Confidence:** High

3. **Decision:** xhigh effort задавать в frontmatter, не в runner
   **Evidence:** Текущие агенты уже используют frontmatter `effort:` поле; runner не должен знать о конкретных агентах
   **Confidence:** High

4. **Decision:** Managed Agents — API-only, не для нашей подписки
   **Evidence:** Ценовая модель "$0.08/session" несовместима с flat-fee подпиской
   **Confidence:** High

5. **Decision:** Opus 4.7 migration — только обновить Claude Code CLI, не код
   **Evidence:** DLD использует model aliases, не hardcoded IDs; breaking changes касаются прямых API calls, не CLI-пути
   **Confidence:** Medium

---

## Gaps (что не удалось верифицировать)

Из-за исчерпания Exa credits следующие вопросы остались без внешней верификации:

| Gap | Что нужно | Где искать |
|----|-----------|------------|
| Точный SDK 0.1.48→0.1.63 changelog | Список переименованных символов | `pip show claude-agent-sdk` + CHANGELOG в venv после upgrade |
| Rate limits Max subscription | Числовые лимиты | Anthropic Support или `claude.ai/settings` |
| `ENABLE_PROMPT_CACHING_1H` официальная дока | Exact env var name | Claude Code release notes в GitHub |
| Managed Agents официальное подтверждение API-only | Явная фраза в docs | `docs.anthropic.com/en/managed-agents/overview` |

---

## Production Patterns

### Pattern 1: Staged SDK upgrade
**Description:** Upgrade в staging venv, запустить smoke test, затем promote в production venv.
**Применимость:** Да — у нас есть `/home/dld/projects/dld/scripts/vps/venv/`. Создать test venv рядом, проверить, заменить.

### Pattern 2: Cache monitoring before optimization
**Description:** Сначала включить логирование cache hits/misses, измерить baseline, затем оптимизировать промпты.
**Применимость:** Да — добавить 5 строк в `claude-runner.py` ResultMessage handler перед тем как менять system prompts агентов.

### Pattern 3: Model downgrade validation
**Description:** При переводе агента Opus→Sonnet запустить один реальный run на Sonnet, сравнить output качество с историческим.
**Применимость:** Да — для 5 кандидатов на downgrade (council/synthesizer, ark/facilitator, board/facilitator, spark/facilitator, bughunt/validator).

---

## Research Sources

- `ai/research/2026-04-18-anthropic-updates-pipeline-optimization.md` — основной первичный отчёт (5 скаутов), sections 1-8
- `/home/dld/projects/dld/scripts/vps/claude-runner.py` — прямой анализ импортов и ClaudeAgentOptions usage
- `/home/dld/projects/dld/.claude/agents/council/synthesizer.md` — проверка frontmatter `effort: max` + `model: opus`
- `/home/dld/projects/dld/.claude/agents/spark/facilitator.md` — проверка frontmatter `effort: max` + `model: opus`
- `/home/dld/projects/dld/.claude/rules/model-capabilities.md` — текущее состояние effort routing table (устарела — Claude Opus 4.6, нет xhigh)
