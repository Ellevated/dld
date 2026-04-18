# Feature: [TECH-165] Anthropic Pipeline Optimization (SDK upgrade + model routing + observability)

**Status:** queued | **Priority:** P1 | **Date:** 2026-04-18

## Why

За последние 2 недели Anthropic выпустил Opus 4.7, 22 версии Claude Code (2.1.92→2.1.114) и 7 релизов Agent SDK (0.1.57→0.1.63). Наш pipeline отстал:

1. `claude-agent-sdk` в VPS venv на **0.1.48** (отстаём на 15 версий)
2. 5 «process keeper» агентов на Opus, хотя делают orchestration/triage (не принятие экспертных решений)
3. Нет observability по token usage и prompt cache — не знаем что реально тратится на 3 параллельных autopilot + night reviewer

**Billing mode:** проект работает на Claude Code Max-подписке (flat fee), поэтому цель — не сокращение счёта, а:
- **Latency** — быстрее Sonnet vs Opus на простых orchestration задачах
- **Rate limits** — меньше Opus usage = реже упираемся в fair-use throttling
- **Observability** — метрики для будущих решений

Полный research-отчёт: `ai/research/2026-04-18-anthropic-updates-pipeline-optimization.md`.

## Context

**Текущее состояние** (подтверждено scout-ами):
- `scripts/vps/venv/` → `claude-agent-sdk 0.1.48` (требуется 0.1.63)
- `scripts/vps/requirements.txt` содержит только `groq>=0.5.0` — SDK не закреплён
- 20 агентов на Opus, 40 на Sonnet, 1 на Haiku (60 total)
- Bughunt personas (6): уже на `model: sonnet`, `effort: high`
- 5 целевых агентов: `council/synthesizer`, `architect/facilitator`, `board/facilitator`, `spark/facilitator`, `bug-hunt/validator` — все `model: opus`
- Противоречие: `.claude/rules/model-capabilities.md:49` указывает `bughunt validator — opus`, но запрос говорит sonnet
- `claude-runner.py` НЕ передаёт thinking/temperature/top_p в `ClaudeAgentOptions` → Opus 4.7 breaking changes к нам не применимы
- `claude-runner.py` НЕ читает `.env` файл — env vars должны быть в окружении процесса
- Devil-замечание: `council/synthesizer` принимает production-решение при 2-2 split между экспертами (не чистый merge/format). Нужен явный rollback criteria.

**Не в scope:**
- Batch API, Managed Agents, Advisor Tool — не применимы на подписке (API-only)
- Прямой рефакторинг system prompts агентов (вынос дат/task IDs в user messages) — отложено до подтверждения что caching реально работает на подписке
- Upgrade Claude Code CLI на VPS — отдельная задача (меняется globally через npm)

---

## Scope
**In scope:**
- Section 1: Apgrade `claude-agent-sdk` в VPS venv с 0.1.48 до 0.1.63 + pin в requirements.txt
- Section 2: 5 агентов Opus → Sonnet + effort tuning для bughunt personas (high → medium)
- Section 3: Добавить `ENABLE_PROMPT_CACHING_1H=1` в окружение runner'а + логирование token usage (включая cache) в callback.py

**Out of scope:**
- Смена моделей для planner/coder/reviewer/debugger/council experts/architect synthesizer/triz/solution-architect (эти остаются на Opus)
- Рефакторинг system prompts агентов (вынос динамики) — отдельная спека ПОСЛЕ того как логирование покажет cache hit rate на подписке
- Upgrade Claude Code CLI на VPS
- Миграция на Managed Agents / Advisor Tool / Batch API

---

## Impact Tree Analysis

### Step 1: UP — кто использует?

| Изменяемый узел | Callers |
|-----------------|---------|
| `scripts/vps/claude-runner.py` | `scripts/vps/run-agent.sh:57` (единственный) |
| `scripts/vps/callback.py` | pueue daemon callback, `scripts/vps/orchestrator.py` |
| 5 agent .md файлов | Claude Code CLI через Task tool (`subagent_type:`), упоминаются в `.claude/skills/{council,architect,board,spark,bughunt}/SKILL.md` |
| `.claude/rules/model-capabilities.md` | Загружается CLAUDE.md hierarchy, используется агентами для effort routing |
| bughunt personas | Spawned bughunt SKILL → 6 personas × N zones |

### Step 2: DOWN — от чего зависит?

| Узел | Зависимости |
|------|-------------|
| `claude-runner.py` | `claude_agent_sdk` (types, query, _errors), `asyncio`, `os.environ`, stdlib |
| `callback.py` | `db.py`, `event_writer.py`, pueue CLI, spec files |
| Agent .md files | Claude Code CLI frontmatter schema (`model:`, `effort:`) |

### Step 3: BY TERM — grep ключевых терминов

- `claude-agent-sdk` / `claude_agent_sdk` → `scripts/vps/claude-runner.py:23-34`, `scripts/vps/requirements.txt:1`
- `model: opus` в 5 target файлах → подтверждено scout-ом
- `ENABLE_PROMPT_CACHING` → 0 совпадений (не используется нигде, добавим)
- `effort: high` в bughunt personas (6 файлов) → подтверждено
- `cache_read_input_tokens` / `cache_creation_input_tokens` → 0 совпадений в callback.py (добавим)

### Step 4: CHECKLIST — обязательные папки

- [x] `tests/` — `scripts/vps/tests/` существует, но `claude-runner.py` не покрыт — добавить smoke test НЕ требуется (manual replay достаточно)
- [x] `template/.claude/` — **КРИТИЧНО: Template Sync Rule** — 5 агентов + model-capabilities.md присутствуют в template идентичными копиями, менять в ОБОИХ местах
- [x] `db/migrations/` — N/A
- [x] `ai/glossary/` — не затрагивается

### Verification

- [ ] После изменений `grep -rn "model: opus" .claude/agents/council/synthesizer.md .claude/agents/architect/facilitator.md .claude/agents/board/facilitator.md .claude/agents/spark/facilitator.md .claude/agents/bug-hunt/validator.md` → 0 результатов
- [ ] `diff .claude/agents/council/synthesizer.md template/.claude/agents/council/synthesizer.md` → 0 (template sync'ed)
- [ ] `/home/dld/projects/dld/scripts/vps/venv/bin/pip show claude-agent-sdk | grep Version` → `Version: 0.1.63`
- [ ] Smoke replay одной queued-задачи через claude-runner.py → exit_code=0, pueue task completes

---

## Allowed Files

**ONLY these files may be modified during implementation:**

**Section 1 — SDK Upgrade:**
1. `scripts/vps/requirements.txt` — pin `claude-agent-sdk>=0.1.63,<0.2.0`
2. `scripts/vps/claude-runner.py` — добавить `ENABLE_PROMPT_CACHING_1H` в `options.env`, добавить `load_env()` из `.env`, расширить usage logging

**Section 2 — Model Routing:**
3. `.claude/agents/council/synthesizer.md` — `model: opus` → `model: sonnet`
4. `.claude/agents/architect/facilitator.md` — `model: opus` → `model: sonnet`
5. `.claude/agents/board/facilitator.md` — `model: opus` → `model: sonnet`
6. `.claude/agents/spark/facilitator.md` — `model: opus` → `model: sonnet`
7. `.claude/agents/bug-hunt/validator.md` — `model: opus` → `model: sonnet`
8. `template/.claude/agents/council/synthesizer.md` — mirror
9. `template/.claude/agents/architect/facilitator.md` — mirror
10. `template/.claude/agents/board/facilitator.md` — mirror
11. `template/.claude/agents/spark/facilitator.md` — mirror
12. `template/.claude/agents/bug-hunt/validator.md` — mirror
13. `.claude/agents/bug-hunt/code-reviewer.md` — `effort: high` → `effort: medium`
14. `.claude/agents/bug-hunt/junior-developer.md` — `effort: high` → `effort: medium`
15. `.claude/agents/bug-hunt/qa-engineer.md` — `effort: high` → `effort: medium`
16. `.claude/agents/bug-hunt/security-auditor.md` — `effort: high` → `effort: medium`
17. `.claude/agents/bug-hunt/software-architect.md` — `effort: high` → `effort: medium`
18. `.claude/agents/bug-hunt/ux-analyst.md` — `effort: high` → `effort: medium`
19. `template/.claude/agents/bug-hunt/code-reviewer.md` — mirror
20. `template/.claude/agents/bug-hunt/junior-developer.md` — mirror
21. `template/.claude/agents/bug-hunt/qa-engineer.md` — mirror
22. `template/.claude/agents/bug-hunt/security-auditor.md` — mirror
23. `template/.claude/agents/bug-hunt/software-architect.md` — mirror
24. `template/.claude/agents/bug-hunt/ux-analyst.md` — mirror
25. `.claude/rules/model-capabilities.md` — обновить Opus 4.7 as default, `xhigh` effort level, validator opus→sonnet, bughunt personas effort high→medium, дата
26. `template/.claude/rules/model-capabilities.md` — mirror

**Section 3 — Observability:**
27. `scripts/vps/.env.example` — документировать `ENABLE_PROMPT_CACHING_1H=1`
28. `scripts/vps/callback.py` — расширить `_parse_log_file()` логированием `cache_read_input_tokens`, `cache_creation_input_tokens`, `input_tokens`

**New files allowed:**
- None

**Files to be modified manually (NOT via autopilot, NOT in git):**
- `scripts/vps/.env` на VPS — вручную добавить `ENABLE_PROMPT_CACHING_1H=1` (файл в .gitignore)
- Venv rebuild: `/home/dld/projects/dld/scripts/vps/venv/bin/pip install --upgrade claude-agent-sdk==0.1.63` (не файл, операция)

**FORBIDDEN:** Все остальные файлы. Autopilot must refuse changes outside this list. Особенно: `.claude/agents/planner.md`, `.claude/agents/review.md`, `.claude/agents/debugger.md`, `.claude/agents/council/{architect,pragmatist,product,security}.md`, `.claude/agents/{architect,board,audit,triz}/synthesizer.md`, `.claude/agents/bug-hunt/solution-architect.md`, `.claude/agents/triz/*.md` — эти остаются на Opus.

---

## Environment

nodejs: false
docker: false
database: false
python_venv: `/home/dld/projects/dld/scripts/vps/venv/`

---

## Blueprint Reference

**Domain:** infra (scripts/vps/ orchestrator + .claude/agents/ prompts)
**Cross-cutting:** Observability (cache hit rate, token usage logging)
**Data model:** нет изменений в schema

---

## Approaches

### Approach A (selected): Одна спека с 3 секциями + conditional prompt caching

**Source:** scout-patterns — прецедент TECH-055 (Review Pipeline Hardening — 6 задач в одной спеке, 4 направления, успешно выполнено)
**Summary:** Три секции в одной спеке, последовательное выполнение (1 → 2 → 3). SDK upgrade первым (минимальный risk-surface). Model routing вторым. Observability третьим. Рефакторинг system prompts (Devil-замечание) отложен до подтверждения данных от Section 3.
**Pros:**
- Один commit, один replay, общая картина в backlog
- Каждая секция даёт независимый атомарный commit — rollback возможен пер-секция через `git revert`
- Прецедент в DLD есть
**Cons:**
- R1 риск (multi-section на live VPS с 3 autopilot-сессиями)
- 28 файлов — большой PR

### Approach B (rejected): Три отдельные спеки (TECH-165/166/167)

**Summary:** Разбить по направлениям.
**Pros:** Независимый rollback на уровне спеки
**Cons:** Прецедент FTR-146/147/148 требует code-level dependency — у нас её нет между секциями. Искусственное разделение, 3 backlog row вместо 1.

### Approach C (rejected): Umbrella + sub-specs (Bug Hunt pattern)

**Summary:** TECH-165 как report, TECH-166/167/168 как standalone.
**Cons:** Bug Hunt pattern для динамически обнаруживаемых findings, а у нас 3 заранее известных направления. Overhead без пользы.

### Selected: A

**Rationale:**
1. Прецедент TECH-055 — такой же multi-section TECH.
2. Section 1 (SDK upgrade) — prerequisite для Section 3 (caching flag не заработает без нового CLI в bundled SDK).
3. Atomic commits внутри спеки сохраняют per-section rollback.
4. Devil-замечания адресованы в Section 2 rollback criteria + Section 3 conditional gate.

---

## Design

### Execution Order (last → first по риску)

```
Section 1: SDK Upgrade
  ├─ Pre-flight: проверить импорты `from claude_agent_sdk._errors import ...` в новой версии
  ├─ Pin в requirements.txt
  ├─ pip install в venv на VPS
  ├─ Smoke replay одной queued задачи
  └─ 48h мониторинг (turns/duration/exit_code)
           ↓
Section 2: Model Routing
  ├─ 5 агентов opus→sonnet + template sync
  ├─ 6 bughunt personas effort high→medium + template sync
  ├─ model-capabilities.md: Opus 4.7 default, xhigh effort, validator sonnet, bughunt medium + template sync
  └─ Rollback criteria: если в 5 следующих council-вердиктах заметна деградация качества синтеза → revert synthesizer на opus
           ↓
Section 3: Observability
  ├─ claude-runner.py: load_env() + ENABLE_PROMPT_CACHING_1H в options.env
  ├─ callback.py: логировать cache_read_input_tokens, cache_creation_input_tokens, input_tokens
  ├─ .env.example: документировать новую env var
  └─ Follow-up gate: если cache_hit_rate<10% после 48h → закрыть дальнейший refactor как "не применимо на подписке"
```

### Section 1: SDK Upgrade

**Подтверждено scout-ом:**
- `claude-runner.py` не трогает `thinking`, `temperature`, `top_p` → Opus 4.7 breaking changes неприменимы
- SDK v0.1.48 уже содержит `ClaudeAgentOptions.effort` и env passthrough
- Thinking bugfix в 0.1.57 неприменим (runner не использует thinking)

**Риск:** `from claude_agent_sdk._errors import CLIConnectionError, ProcessError` (claude-runner.py:30) — импорт приватного модуля. В 0.1.63 могло переехать.

**Mitigation:** pre-flight check ДО pip install на prod — создать temp venv, установить 0.1.63, проверить импорт.

### Section 2: Model Routing

**5 агентов Opus → Sonnet:**
| Агент | Обоснование |
|-------|-------------|
| `council/synthesizer` | Merge/format + decision при 2-2 split. **Rollback trigger:** деградация качества 5+ council-вердиктов подряд |
| `architect/facilitator` | Process keeper, НЕ голосует (по описанию) |
| `board/facilitator` | Process keeper, НЕ голосует |
| `spark/facilitator` | Orchestration 8 фаз, не принимает решений |
| `bug-hunt/validator` | Triage (в model-capabilities.md УЖЕ указан sonnet — устранение расхождения) |

**6 bughunt personas: effort high → medium**
- По рекомендации Anthropic для задач "чтение + описание" medium достаточно
- Персоны генерируют findings, не решают сложные архитектурные вопросы

**Template Sync:** каждое изменение в `.claude/` дублируется в `template/.claude/` (правило template-sync.md).

### Section 3: Observability

**claude-runner.py:**
```python
# Добавить load_env() в начало
def load_env():
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

load_env()  # вызвать в module load

# В run_task builder:
options = ClaudeAgentOptions(
    ...,
    env={
        "ENABLE_PROMPT_CACHING_1H": os.environ.get("ENABLE_PROMPT_CACHING_1H", "1"),
    },
)
```

**callback.py `_parse_log_file()`:**
- Текущее: читает `cost_usd`, `skill`, `result_preview`, `usage`
- Добавить: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens`
- Вычислить: `cache_hit_rate = cache_read / (cache_read + input_tokens)` если знаменатель > 0
- Логировать в stdout (уходит в pueue log, читается manual review)

**.env.example:**
```
# Prompt caching 1h TTL (polezno dlya long-running council/bughunt sessions)
ENABLE_PROMPT_CACHING_1H=1
```

---

## Implementation Plan

### Research Sources

- [Anthropic Opus 4.7 announcement](https://www.anthropic.com/news/claude-opus-4-7) — model id, capabilities
- [Agent SDK Python releases 0.1.48-0.1.63](https://github.com/anthropics/claude-code-sdk-python/releases) — changelog
- [Prompt caching 1h TTL](https://platform.claude.com/docs/en/build-with-claude/prompt-caching) — how ENABLE_PROMPT_CACHING_1H works
- `.claude/rules/template-sync.md` — Template Sync Rule
- `ai/features/TECH-055-2026-02-01-auto-review-agent.md` — precedent for multi-section TECH spec
- `ai/research/2026-04-18-anthropic-updates-pipeline-optimization.md` — full research report

### Task 1: Pre-flight check + SDK upgrade

**Type:** infra
**Files:**
- modify: `scripts/vps/requirements.txt`
- manual (not in git): venv rebuild on VPS
**Steps:**
1. Pre-flight — создать temp venv локально, установить `claude-agent-sdk==0.1.63`, проверить что импорты из `claude-runner.py:23-30` работают без ошибок
2. Добавить в `scripts/vps/requirements.txt` строку `claude-agent-sdk>=0.1.63,<0.2.0`
3. На VPS: `/home/dld/projects/dld/scripts/vps/venv/bin/pip install --upgrade claude-agent-sdk==0.1.63`
4. Smoke test: `python3 -c "from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolResultBlock, UserMessage; from claude_agent_sdk._errors import CLIConnectionError, ProcessError"`
5. Verify: `/home/dld/projects/dld/scripts/vps/venv/bin/pip show claude-agent-sdk | grep Version` → `0.1.63`

**Acceptance:** SDK установлен, импорты работают, версия зафиксирована в requirements.txt.

### Task 2: Smoke replay через claude-runner.py

**Type:** test
**Files:** N/A (manual verification)
**Steps:**
1. На VPS найти queued spec (или использовать свежесозданную спеку-никогда-не-критичную)
2. Вызвать `run-agent.sh` с этой задачей вручную через pueue
3. Verify: exit_code=0, pueue task completes без ошибок

**Acceptance:** Один полный autopilot цикл отработал на новой SDK.

### Task 3: 5 agents Opus → Sonnet + template sync

**Type:** code
**Files:**
- modify: `.claude/agents/council/synthesizer.md`
- modify: `.claude/agents/architect/facilitator.md`
- modify: `.claude/agents/board/facilitator.md`
- modify: `.claude/agents/spark/facilitator.md`
- modify: `.claude/agents/bug-hunt/validator.md`
- modify: `template/.claude/agents/council/synthesizer.md`
- modify: `template/.claude/agents/architect/facilitator.md`
- modify: `template/.claude/agents/board/facilitator.md`
- modify: `template/.claude/agents/spark/facilitator.md`
- modify: `template/.claude/agents/bug-hunt/validator.md`
**Pattern:** В каждом файле frontmatter на 4-й строке `model: opus` → `model: sonnet`
**Acceptance:**
- `grep -l "^model: opus" .claude/agents/council/synthesizer.md .claude/agents/architect/facilitator.md .claude/agents/board/facilitator.md .claude/agents/spark/facilitator.md .claude/agents/bug-hunt/validator.md` → 0 файлов
- `diff -r .claude/agents/council/synthesizer.md template/.claude/agents/council/synthesizer.md` → пусто (для каждой из 5 пар)

### Task 4: 6 bughunt personas effort high → medium + template sync

**Type:** code
**Files:**
- modify: `.claude/agents/bug-hunt/{code-reviewer,junior-developer,qa-engineer,security-auditor,software-architect,ux-analyst}.md` (6 files)
- modify: `template/.claude/agents/bug-hunt/{code-reviewer,junior-developer,qa-engineer,security-auditor,software-architect,ux-analyst}.md` (6 files)
**Pattern:** В frontmatter `effort: high` → `effort: medium`
**Acceptance:**
- `grep -l "^effort: high" .claude/agents/bug-hunt/*.md` → только solution-architect, validator (должны остаться high — это не personas)
- Template sync — diff пустой

### Task 5: Update model-capabilities.md + template sync

**Type:** docs
**Files:**
- modify: `.claude/rules/model-capabilities.md`
- modify: `template/.claude/rules/model-capabilities.md`
**Changes:**
1. Обновить заголовок: `## Active Model: Claude Opus 4.7`
2. Released: February 5, 2026 → April 16, 2026
3. Model ID: `claude-opus-4-6` → `claude-opus-4-7`
4. Last updated date
5. В Effort levels добавить строку `xhigh` (между high и max)
6. В Effort Routing Strategy: строка `bughunt personas (6)` → effort `medium` (было high)
7. В Effort Routing Strategy: строка `bughunt validator` → effort `high`, model `sonnet` (было opus)
8. Добавить пометку про automatic caching в секцию "What Agents Should Know"
**Acceptance:** Правки применены в обоих копиях, diff пустой между ними.

### Task 6: claude-runner.py — load_env + caching env + usage logging

**Type:** code
**Files:**
- modify: `scripts/vps/claude-runner.py`
**Changes:**
1. Добавить функцию `load_env()` читающую `.env` файл рядом с скриптом
2. Вызвать `load_env()` на module load (до использования os.environ)
3. В `run_task()` builder — добавить `env={"ENABLE_PROMPT_CACHING_1H": os.environ.get("ENABLE_PROMPT_CACHING_1H", "1")}` в `ClaudeAgentOptions`
4. Расширить логирование ResultMessage: извлекать `usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens`, `usage.cache_read_input_tokens`, печатать в stdout JSON
**Acceptance:**
- `grep "ENABLE_PROMPT_CACHING_1H" scripts/vps/claude-runner.py` → найдено
- `grep "cache_read_input_tokens" scripts/vps/claude-runner.py` → найдено
- Smoke run показывает строку с usage metrics в pueue log

### Task 7: callback.py — cache hit rate logging

**Type:** code
**Files:**
- modify: `scripts/vps/callback.py`
**Changes:**
В `_parse_log_file()` расширить парсинг JSON:
1. Извлечь `usage.input_tokens`, `usage.output_tokens`, `usage.cache_creation_input_tokens`, `usage.cache_read_input_tokens`
2. Вычислить `cache_hit_rate` (безопасно, если 0)
3. Логировать в stdout
**Acceptance:**
- `grep "cache_hit_rate" scripts/vps/callback.py` → найдено
- Unit test или manual replay показывает metrics в callback log

### Task 8: .env.example — документирование новой env var

**Type:** docs
**Files:**
- modify: `scripts/vps/.env.example`
**Changes:** Добавить секцию:
```
# Enable 1-hour prompt cache TTL (snizhaet latency dlya council/bughunt sessions)
# Polezno na Max-podpiske — ne vliyaet na billing, uluchshaet response time.
ENABLE_PROMPT_CACHING_1H=1
```
**Acceptance:** `grep "ENABLE_PROMPT_CACHING_1H" scripts/vps/.env.example` → найдено.

### Execution Order

1 (SDK pre-flight + install) → 2 (smoke) → 3 (5 agents opus→sonnet) → 4 (bughunt effort tuning) → 5 (rules docs) → 6 (runner caching + usage) → 7 (callback usage) → 8 (.env.example)

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | SDK version pinned | `pip show claude-agent-sdk` | Version=0.1.63 | deterministic | user req | P0 |
| EC-2 | 5 target agents on sonnet | `grep "^model: opus" <5 files>` | 0 matches | deterministic | user req | P0 |
| EC-3 | Template sync for 5 model changes | `diff .claude/... template/.claude/...` for each | empty diff | deterministic | template-sync rule | P0 |
| EC-4 | 6 bughunt personas on medium | `grep "^effort: high" .claude/agents/bug-hunt/{personas}.md` | 0 matches | deterministic | user req | P1 |
| EC-5 | Template sync for 6 bughunt effort changes | `diff` for each pair | empty | deterministic | template-sync rule | P0 |
| EC-6 | model-capabilities.md updated for 4.7 | `grep "claude-opus-4-7" .claude/rules/model-capabilities.md` | match found | deterministic | user req | P1 |
| EC-7 | model-capabilities.md has xhigh | `grep "xhigh" .claude/rules/model-capabilities.md` | match found | deterministic | user req | P1 |
| EC-8 | claude-runner.py loads .env | `grep "def load_env" scripts/vps/claude-runner.py` | match found | deterministic | design | P1 |
| EC-9 | claude-runner.py passes caching env | `grep "ENABLE_PROMPT_CACHING_1H" scripts/vps/claude-runner.py` | match found | deterministic | user req | P1 |
| EC-10 | callback.py logs cache metrics | `grep "cache_read_input_tokens" scripts/vps/callback.py` | match found | deterministic | user req | P1 |
| EC-11 | .env.example documents caching | `grep "ENABLE_PROMPT_CACHING_1H" scripts/vps/.env.example` | match found | deterministic | user req | P2 |
| EC-12 | requirements.txt pins SDK | `grep "claude-agent-sdk" scripts/vps/requirements.txt` | match found with version | deterministic | design | P0 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-13 | SDK 0.1.63 installed in venv | Import smoke: `from claude_agent_sdk import ClaudeAgentOptions, query` and `from claude_agent_sdk._errors import CLIConnectionError, ProcessError` | exit 0 | integration | devil scout | P0 |
| EC-14 | Upgraded runner, queued spec | Manual replay via pueue + claude-runner.py | exit_code=0, spec→done | integration | devil scout | P0 |
| EC-15 | Runner + caching env set | Run one task with ENABLE_PROMPT_CACHING_1H=1 | Pueue log contains `cache_read_input_tokens` field | integration | user req | P1 |

### Coverage Summary
- Deterministic: 12 | Integration: 3 | LLM-Judge: 0 | Total: 15 (min 3 ✓)

### TDD Order
1. EC-13 (pre-flight) → fail → install SDK → pass
2. EC-1 → pip show after install → pass
3. EC-12 → edit requirements.txt → pass
4. EC-2, EC-3 → grep before → fail → edit 10 files → pass
5. EC-4, EC-5 → grep before → fail → edit 12 files → pass
6. EC-6, EC-7 → grep before → fail → edit rules → pass
7. EC-8, EC-9 → grep before → fail → edit runner → pass
8. EC-10 → edit callback → pass
9. EC-11 → edit .env.example → pass
10. EC-14, EC-15 → manual smoke replay

---

## Acceptance Verification (MANDATORY)

Machine-executable checks: feature WORKS in running system.

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | SDK install succeeds | `/home/dld/projects/dld/scripts/vps/venv/bin/pip install --upgrade claude-agent-sdk==0.1.63` | exit 0 | 60s |
| AV-S2 | SDK imports work | `/home/dld/projects/dld/scripts/vps/venv/bin/python3 -c "from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolResultBlock, UserMessage; from claude_agent_sdk._errors import CLIConnectionError, ProcessError; print('OK')"` | `OK` | 10s |
| AV-S3 | SDK version correct | `/home/dld/projects/dld/scripts/vps/venv/bin/pip show claude-agent-sdk \| grep Version` | `Version: 0.1.63` | 5s |
| AV-S4 | claude-runner.py loads | `/home/dld/projects/dld/scripts/vps/venv/bin/python3 -c "import sys; sys.path.insert(0, '/home/dld/projects/dld/scripts/vps'); import importlib.util; spec = importlib.util.spec_from_file_location('claude_runner', '/home/dld/projects/dld/scripts/vps/claude-runner.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('loaded')"` | `loaded` | 10s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | Smoke replay | Any queued spec exists | Pueue add via run-agent.sh | pueue task completes with exit_code=0 |
| AV-F2 | Cache metrics in logs | Run task through claude-runner.py | `grep "cache_read_input_tokens" <pueue log>` | match found (even if 0) |
| AV-F3 | Template sync | All 5+6+1 .claude and template pairs | `for f in synthesizer facilitator...; do diff .claude/.../${f}.md template/.claude/.../${f}.md; done` | all empty |

### Verify Command (copy-paste ready)

```bash
# --- Run on VPS ---
cd /home/dld/projects/dld

# AV-S1, AV-S3
/home/dld/projects/dld/scripts/vps/venv/bin/pip install --upgrade "claude-agent-sdk>=0.1.63,<0.2.0"
/home/dld/projects/dld/scripts/vps/venv/bin/pip show claude-agent-sdk | grep Version

# AV-S2
/home/dld/projects/dld/scripts/vps/venv/bin/python3 -c "
from claude_agent_sdk import ClaudeAgentOptions, query, AssistantMessage, ResultMessage, SystemMessage, TextBlock, ToolResultBlock, UserMessage
from claude_agent_sdk._errors import CLIConnectionError, ProcessError
print('imports OK')
"

# AV-S4
/home/dld/projects/dld/scripts/vps/venv/bin/python3 /home/dld/projects/dld/scripts/vps/claude-runner.py --help 2>&1 || true

# EC-2: 5 agents should be on sonnet
grep -c "^model: opus" \
  .claude/agents/council/synthesizer.md \
  .claude/agents/architect/facilitator.md \
  .claude/agents/board/facilitator.md \
  .claude/agents/spark/facilitator.md \
  .claude/agents/bug-hunt/validator.md
# Expected: all zeros

# EC-4: 6 bughunt personas should be on medium
grep -c "^effort: high" .claude/agents/bug-hunt/code-reviewer.md \
  .claude/agents/bug-hunt/junior-developer.md \
  .claude/agents/bug-hunt/qa-engineer.md \
  .claude/agents/bug-hunt/security-auditor.md \
  .claude/agents/bug-hunt/software-architect.md \
  .claude/agents/bug-hunt/ux-analyst.md
# Expected: all zeros

# EC-3, EC-5: Template sync verification
for agent in council/synthesizer architect/facilitator board/facilitator spark/facilitator bug-hunt/validator; do
  diff ".claude/agents/${agent}.md" "template/.claude/agents/${agent}.md" || echo "DESYNC: $agent"
done
for persona in code-reviewer junior-developer qa-engineer security-auditor software-architect ux-analyst; do
  diff ".claude/agents/bug-hunt/${persona}.md" "template/.claude/agents/bug-hunt/${persona}.md" || echo "DESYNC: $persona"
done
diff .claude/rules/model-capabilities.md template/.claude/rules/model-capabilities.md || echo "DESYNC: model-capabilities"

# AV-F2: после smoke replay — проверить что usage logged
# (manual step after running one real autopilot task)
```

### Post-Deploy

```
DEPLOY_URL=local-only (VPS orchestrator)
```

**Rules:**
- Все команды выше копи-пасте executable.
- Минимум 4 smoke checks (AV-S1..S4) + 3 functional checks (AV-F1..F3).

---

## Rollback Criteria

### Section 1 (SDK upgrade) rollback
- Triggered if: AV-S2 fails, или smoke replay exit_code != 0, или >50% следующих 10 autopilot tasks падают с новыми ошибками
- How: `pip install claude-agent-sdk==0.1.48` + revert requirements.txt

### Section 2 (model routing) rollback
- Triggered if: **council/synthesizer** — в 5+ подряд council-вердиктах отмечена деградация качества синтеза (subjective review — manual)
- Triggered if: **facilitators** — 3+ orchestration failures (phase skips, state.json не обновляется)
- Triggered if: **bughunt validator** — triage пропускает обнаруженные issues на 2+ zone-ах подряд
- Triggered if: **bughunt personas effort:medium** — findings становятся существенно менее детальными (manual review первых 3 bughunt runs)
- How: revert specific commit для соответствующего агента (атомарность по секциям позволяет)

### Section 3 (observability) rollback
- Если cache_hit_rate < 10% после 48h на Max-подписке → НЕ rollback кода, но задокументировать в diary что refactor system prompts для cache не нужен
- Если logging ломает callback.py JSON parsing → revert callback.py изменения

---

## Definition of Done

### Functional
- [ ] SDK upgraded to 0.1.63 на VPS venv
- [ ] `requirements.txt` pins `claude-agent-sdk>=0.1.63,<0.2.0`
- [ ] 5 target agents переведены opus → sonnet (в `.claude/` и `template/.claude/`)
- [ ] 6 bughunt personas effort high → medium (в `.claude/` и `template/.claude/`)
- [ ] `model-capabilities.md` обновлён (Opus 4.7, xhigh, validator sonnet, personas medium) в обоих местах
- [ ] `claude-runner.py` загружает `.env` и передаёт `ENABLE_PROMPT_CACHING_1H` в `options.env`
- [ ] `callback.py` логирует cache metrics
- [ ] `.env.example` документирует новую env var
- [ ] One smoke replay через autopilot отработал с exit_code=0

### Tests
- [ ] All deterministic EC-1 через EC-12 pass (grep-based)
- [ ] Integration EC-13, EC-14, EC-15 pass (manual smoke)

### Acceptance Verification
- [ ] AV-S1..S4 pass
- [ ] AV-F1..F3 pass
- [ ] Verify Command runs без ошибок

### Technical
- [ ] Tests pass (`./test fast` если применимо)
- [ ] No regressions на 48h мониторинге orchestrator logs
- [ ] Template-sync verification: diff пустой между `.claude/` и `template/.claude/` для всех затронутых файлов

### Observability (follow-up after 48h monitoring)
- [ ] Зафиксировать в `ai/diary/corrections.md`: работает ли prompt caching на Max-подписке (по cache_hit_rate)
- [ ] Если cache_hit_rate >10% — создать отдельную спеку на рефакторинг system prompts (вынос динамики)
- [ ] Если cache_hit_rate <10% — задокументировать как "не применимо на Max-подписке"

---

## Autopilot Log
[Auto-populated by autopilot during execution]
