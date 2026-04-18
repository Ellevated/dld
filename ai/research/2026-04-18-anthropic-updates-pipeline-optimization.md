# Anthropic Updates 2026-04-04 — 2026-04-18: Pipeline Optimization

**Автор:** 5 параллельных скаутов (API, Product, Claude Code, Agent SDK, Multi-Agent Patterns)
**Дата:** 2026-04-18
**Цель:** определить где оптимизировать DLD-пайплайн (токены, модели, новые инструменты)

---

## 0. Executive Summary

За 2 недели Anthropic выпустил **Opus 4.7** (16.04), **Advisor Tool** (09.04), **Task Budgets** (beta), **Managed Agents** (08.04 beta), 22 версии Claude Code (2.1.92→2.1.114), 7 релизов Agent SDK.

**Три главных рычага экономии без потери качества:**
1. **Модельный роутинг** — перевести 5–7 Opus-агентов на Sonnet (potential –30–40% стоимости)
2. **Prompt caching + 1h TTL** — новый env `ENABLE_PROMPT_CACHING_1H`, экономия до 90% на повторяющихся system prompts
3. **Effort tuning** — новый уровень `xhigh` для Opus 4.7 и эффективное снижение до `medium` для рутинных агентов

---

## 1. КРИТИЧНО / Срочное (до конца недели)

### 1.1 Claude Haiku 3 retire 2026-04-19 (ЗАВТРА)

`claude-3-haiku-20240307` deprecated, умирает завтра.

**Проверено:** в runtime-коде DLD **НЕ используется** (только в архивных `ai/architect/` отчётах как примеры — безопасно).

**Действие:** ничего не требуется, но зафиксировать в changelog.

### 1.2 Agent SDK v0.1.48 → v0.1.63 (отстаём на 15 версий)

**Где:** `/home/dld/projects/dld/scripts/vps/venv/` → `claude-agent-sdk 0.1.48`
**Требуется:** v0.1.60+ для Opus 4.7, v0.1.63 — текущая стабильная

**Критичные фиксы между 0.1.48 и 0.1.63:**

| Версия | Фикс |
|---|---|
| **0.1.57** | **Критичный bugfix: thinking маппинг** — `adaptive`/`disabled` неверно конвертировался в `--max-thinking-tokens` вместо `--thinking` |
| **0.1.60** | Bundled CLI 2.1.111+ с Opus 4.7 support |
| **0.1.60** | Фикс: `setting_sources=[]` теперь реально отключает настройки (было молча игнорируется) |
| **0.1.62** | Новый параметр `skills=["spark", ...]` в `ClaudeAgentOptions` |
| **0.1.57** | `permission_mode="auto"` — новый режим |
| **0.1.57** | `exclude_dynamic_sections=True` — убирает cwd/git status → кэшируемый system prompt |

**Действие:**
```bash
/home/dld/projects/dld/scripts/vps/venv/bin/pip install --upgrade claude-agent-sdk==0.1.63
```
Проверить `claude-runner.py` на использование `thinking` + `setting_sources`.

### 1.3 Opus 4.7 breaking changes (если будем переезжать)

Проверить в коде:
- `temperature`, `top_p`, `top_k` — удалены, 400 error на Opus 4.7
- `thinking: {type: "enabled", budget_tokens: N}` — удалено, только `{type: "adaptive"}`
- Assistant prefills — удалены (уже знаем из ADR-006)

**Проверить**: `claude-runner.py` и `scripts/vps/*` — использует ли эти параметры.

---

## 2. Оптимизация моделей (потенциал ~30-40% экономии)

### Текущее распределение (60 агентов)

- **Opus:** 19 агентов ($5/$25 per MTok)
- **Sonnet:** 40 агентов ($3/$15 per MTok)
- **Haiku:** 1 агент ($0.80/$4 per MTok)

### Рекомендации по переводу Opus → Sonnet

| Агент | Файл | Текущая | Рекомендация | Обоснование |
|---|---|---|---|---|
| council/synthesizer | `.claude/agents/council/synthesizer.md` | opus | **sonnet** | merge/format экспертных заключений — не глубокое мышление |
| architect/facilitator | `.claude/agents/architect/facilitator.md` | opus | **sonnet** | process keeper, НЕ голосует (по описанию) |
| board/facilitator | `.claude/agents/board/facilitator.md` | opus | **sonnet** | process keeper, НЕ голосует |
| spark/facilitator | `.claude/agents/spark/facilitator.md` | opus | **sonnet** | orchestration 8 фаз, не принимает решений |
| bughunt/validator | `.claude/agents/bug-hunt/validator.md` | opus | **sonnet** high effort | triage — в model-capabilities.md уже написано "sonnet" но файл на opus (расхождение!) |

**Потенциал:** 5 агентов × ~20K токенов на run × переход 5/25 → 3/15 = **~40% снижение на этих агентах**.

### Оставить на Opus 4.7 (критично)

- `planner` — сложная декомпозиция
- `review` — анализ качества (можно проверить на Sonnet если станет Opus 4.7)
- `debugger` — root cause analysis
- `council/{architect,pragmatist,product,security}` — экспертная глубина
- `architect/synthesizer`, `board/synthesizer`, `audit/synthesizer` — синтез альтернатив
- `bughunt/solution-architect` — дизайн фикса
- `triz/{synthesizer,toc-analyst,triz-analyst}` — системный анализ

### Расхождение с rules/model-capabilities.md

В `model-capabilities.md` описано:
- `bughunt validator` — opus ✓ (совпадает)
- `bughunt solution-architect` — opus ✓
- `reflect aggregator` — haiku ✓ (совпадает)

Однако в rule для `council experts` указано `opus` (правильно) — но для нас открыт вопрос нужно ли 4/5 переводить.

---

## 3. Effort Levels & Adaptive Thinking

### Новый уровень: `xhigh` (Opus 4.7 only)

```
max > xhigh > high > medium > low
```

`xhigh` рекомендован для coding + agentic workflows, меньше "overthinking" чем `max`.

### Рекомендации для DLD

| Агент | Текущий effort | Рекомендация |
|---|---|---|
| planner | max | **xhigh** (Opus 4.7) — меньше overthinking |
| council experts | max | **xhigh** — сохранить глубину, меньше токенов |
| coder | high | **high** (оставить) |
| review | high | **high** |
| tester | medium | **medium** |
| bughunt personas | high | **medium** — чтение и описание, не решение |
| spec-reviewer | medium | **medium** |
| documenter | medium | **low** |
| reflect-aggregator | — | **low** (на Haiku) |

**Ожидаемый эффект:** `max → xhigh` даёт ~20% экономии thinking tokens на агенте без потери качества (по данным Anthropic).

### Миграция: thinking config

Для Opus 4.7: убрать `budget_tokens`, использовать только:
```python
thinking={"type": "adaptive"}
output_config={"effort": "xhigh"}
```

---

## 4. Prompt Caching (потенциал ~75-90% на input)

### Новые env переменные Claude Code

```bash
ENABLE_PROMPT_CACHING_1H=1   # 1-часовой TTL (полезно для bughunt/council — циклы >5 мин)
FORCE_PROMPT_CACHING_5M=1     # форсировать 5-минутный TTL
```

### Automatic caching (GA с 19.02)

`cache_control` в body → система сама кэширует последний cacheable блок. Не нужно вручную расставлять breakpoints.

### Стратегия для bughunt (6 персон × N зон)

**Сейчас:** каждая персона получает свой system prompt → 6 отдельных запросов
**Оптимизация:** вынести общие правила + persona description в cacheable static block → 1 cache write + 5 cache reads

**Экономия:** на 100K static prompt:
- Было: 6 × 100K input × $3/MTok (Sonnet) = $1.80
- Станет: 1 × 100K write + 5 × 100K read × $0.30/MTok = $0.45
- **–75% на input для этой группы**

### Рекомендации агентам

Убрать из system prompts динамику (дату, task ID, cwd) — переносить в user message:

```python
# ПЛОХО: дата ломает кэш
system = f"You are a coder. Today: {date}. Task: {task_id}."

# ХОРОШО
system = [{"type": "text", "text": "You are a coder.", "cache_control": {"type": "ephemeral"}}]
messages = [{"role": "user", "content": f"Today: {date}. Task: {task_id}. ..."}]
```

### Мониторинг

Добавить в callback.py логирование:
```python
print(f"Cache hits: {usage.cache_read_input_tokens}")
print(f"Cache writes: {usage.cache_creation_input_tokens}")
```
Целевой hit rate: **>60%** на повторяющихся агентах (council, bughunt).

---

## 5. Новые Инструменты Claude Code

### Хуки (расширение с ~14 до 21+ событий)

| Новое событие | Применимость для DLD |
|---|---|
| **PreCompact / PostCompact** | Сохранить diary/spec state перед сжатием длинной autopilot-сессии |
| **TaskCreated / TaskCompleted** | Валидация задач TaskCreate через hook (уже используем pueue callback) |
| **WorktreeCreate / WorktreeRemove** | Интеграция кастомной логики при autopilot worktree (сейчас в bash) |
| **InstructionsLoaded** | Audit загрузки CLAUDE.md / rules — видеть какие правила подтягиваются |
| **ConfigChange** | Блокировать нежелательные изменения settings.json |
| **Elicitation / ElicitationResult** | Контроль MCP user input (полезно для nexus MCP) |
| **PermissionDenied** | Auto-retry логика после отказа permission classifier |

### Conditional `if` field в хуках

```json
{"type": "command", "if": "Bash(rm *)", "command": "/path/to/check.sh"}
```
Фильтрация без лишних fork — упростить наши hooks.

### HTTP hooks

Hook-логика вынесется в HTTP сервис вместо bash скриптов — можно мигрировать валидационные хуки в Python/Node service.

### Subagent Frontmatter новые поля

```yaml
---
name: my-agent
model: sonnet
effort: medium        # НОВОЕ
maxTurns: 30          # НОВОЕ
disallowedTools: [...] # НОВОЕ
initialPrompt: "..."  # НОВОЕ — auto-submit первого сообщения
---
```

**Применимо:** добавить `maxTurns` в bughunt personas (сейчас используют дефолт), `effort` в агентные frontmatter (заменит описательную таблицу в `model-capabilities.md`).

### Новые slash-команды

| Команда | Польза для DLD |
|---|---|
| `/ultrareview` | Параллельный multi-agent code review — может дополнить или заменить наш `/review` |
| `/less-permission-prompts` | Сканирует transcript, предлагает allowlist для `.claude/settings.json` — уменьшит permission spam |
| `/recap` | Восстановление контекста после compaction |
| `/effort` | Интерактивный слайдер без аргументов |

### Skill tool

Модель теперь может сама вызывать встроенные slash-команды (`/init`, `/review`, `/security-review`).

**Применимо:** в наших кастомных агентах можно писать "вызови `/security-review`" — работает нативно.

### Нативный binary (v2.1.113)

Claude Code теперь распространяется как native binary (не bundled JS). Быстрее старт, меньше памяти. Обновление `npm install -g @anthropic-ai/claude-code`.

---

## 6. Новые API Фичи

### Advisor Tool (09.04, beta)

**Паттерн:** дешёвый executor + умный советник в одном запросе.

```python
tools=[{
    "type": "advisor_20260301",
    "name": "advisor",
    "model": "claude-opus-4-7",
    "max_uses": 3,
    "caching": {"type": "ephemeral", "ttl": "5m"}
}]
```

Sonnet executor вызывает `advisor()` → Anthropic делает sub-inference на Opus 4.7 → возвращает план 400-700 токенов.

**Потенциальная замена для DLD:**
- `planner` сейчас: Opus $5/$25 весь run
- С Advisor: Sonnet executor + Opus advisor (только для ключевых решений) → экономия 50%+ на простых задачах

**Beta header:** `advisor-tool-2026-03-01`

### Task Budgets (beta)

```python
output_config={
    "effort": "high",
    "task_budget": {"type": "tokens", "total": 64000}
}
```

Мягкий cap токенов на весь agentic loop. Модель видит countdown.

**Применимо:** заменит hard `max_turns=30` в claude-runner.py на token-based budget.

**Beta header:** `task-budgets-2026-03-13`

### Batch API — 50% скидка

Стекируется с cache reads:
- Cache read ($0.50) + Batch (50%) = **$0.25/MTok на Opus** vs стандартные $5.00
- **Экономия 95%**

**Применимо:** ночной ревьюер, плановый bughunt, архивные audit — всё что не realtime можно через Batch API.

### Managed Agents (08.04, beta)

Hosted harness с environments (Python/Node/Go), built-in tools, prompt caching, compaction, SSE streaming. Цена: стандартные токены + $0.08/active session-час.

**Оценка для DLD:** может заменить `claude-runner.py + run-agent.sh + pueue` pipeline. POC имеет смысл в отдельном спринте, но **не критично** — self-hosted работает.

### 1M Context Window — GA

Opus 4.7, Sonnet 4.6 — 1M без beta header, стандартная цена.
`context-1m-2025-08-07` beta header для Sonnet 4/4.5 умирает **2026-04-30** — но у нас не используется.

---

## 7. Дорожная карта (по приоритетам)

### P0 — этой недели

1. **Upgrade claude-agent-sdk 0.1.48 → 0.1.63** (есть критичный bugfix thinking mapping!)
2. **Обновить `.claude/rules/model-capabilities.md`:**
   - Добавить `xhigh` effort level
   - Отметить Opus 4.7 как актуальный
   - Добавить Task Budgets, Advisor Tool, 1M GA, automatic caching
3. **Проверить `claude-runner.py`:**
   - Использует ли `temperature`/`top_p`? Если да — убрать для совместимости с Opus 4.7
   - Использует ли `thinking.budget_tokens`? → `adaptive` + effort
   - Upgrade импортов под v0.1.63 API

### P1 — этот спринт

4. **Перевести 5 Opus→Sonnet агентов:**
   - `council/synthesizer.md`
   - `architect/facilitator.md`
   - `board/facilitator.md`
   - `spark/facilitator.md`
   - bughunt/validator — проверить факт несоответствия model-capabilities.md

5. **Prompt caching:** вынести даты/task IDs из system prompts в user messages для всех агентов
6. **Effort tuning:** bughunt personas → medium (сейчас high в rules)
7. **Добавить PreCompact hook** в `.claude/hooks/` для сохранения diary перед сжатием

### P2 — следующий спринт

8. **Advisor Tool POC** — переписать `planner.md` с Sonnet+Opus-advisor паттерном
9. **Task Budgets** вместо `max_turns=30` в `claude-runner.py`
10. **Batch API** для ночного ревьюера (async, 50% скидка)
11. **1h cache TTL** через `ENABLE_PROMPT_CACHING_1H` для council/bughunt
12. **Subagent frontmatter:** `effort`, `maxTurns`, `initialPrompt` вместо описательных rules

### P3 — когда будет желание

13. **Managed Agents POC** — замена self-hosted pueue pipeline
14. **HTTP hooks** — миграция bash hooks в Python/Node сервис
15. **Нативный binary** claude-code — обновление на VDS

---

## 8. Источники

### API / Models
- [Anthropic News — Claude Opus 4.7](https://www.anthropic.com/news/claude-opus-4-7)
- [Migration Guide Opus 4.6 → 4.7](https://platform.claude.com/docs/en/about-claude/models/migration-guide)
- [Adaptive Thinking Docs](https://platform.claude.com/docs/en/build-with-claude/adaptive-thinking)
- [Prompt Caching Docs](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)
- [Task Budgets](https://platform.claude.com/docs/en/build-with-claude/task-budgets)
- [Advisor Tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool)
- [Managed Agents](https://platform.claude.com/docs/en/managed-agents/overview)

### Claude Code / SDK
- [Claude Code Releases 2.1.92-2.1.114](https://github.com/anthropics/claude-code/releases)
- [Agent SDK Python Releases 0.1.48-0.1.63](https://github.com/anthropics/claude-code-sdk-python/releases)
- [Hooks Reference](https://code.claude.com/docs/en/hooks)

### Best Practices
- [Anthropic Engineering — Multi-Agent Research System](https://www.anthropic.com/engineering/multi-agent-research-system)
- [Anthropic Engineering — Harness Design](https://www.anthropic.com/engineering/harness-design-long-running-apps)
