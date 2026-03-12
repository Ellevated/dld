# Исследование: Enforcement as Code + Tests as Steering

**Дата:** 2026-02-22
**Контекст:** Аудит тяжёлых скилов DLD → поиск best practices для управляемого pipeline

---

## Корневая проблема

DLD = Level 1 enforcement (промпт описывает процесс, LLM интерпретирует).
Нужен Level 2+ (enforcement через код, а не через промпты).

Гипотеза "Process as Code" (bash-скрипты оркестрируют pipeline) **не подтверждена** индустрией.
Правильная формулировка: **"Enforcement as Code + Tests as Steering"**.

---

## Tier 1: Доказано на масштабе Anthropic

### 1. Initializer + Incremental Agent (Anthropic, Nov 2025)

**Источник:** https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

- Первый запуск: initializer создаёт `feature_list.json`, `init.sh`, progress file
- Каждый запуск: читает state → работает над ОДНОЙ задачей → коммитит → обновляет progress
- **JSON как state machine** (не markdown — LLM реже ломает JSON)
- Инкрементальная работа — ключевой паттерн

Цитата: *"We found that the best way to elicit this behavior was to ask the model to commit its progress to git with descriptive commit messages and to write summaries of its progress in a progress file."*

### 2. Tests as Primary Steering (Carlini, Anthropic, Feb 2026)

**Источник:** https://www.anthropic.com/engineering/building-c-compiler

- 16 параллельных Claude, 2000 сессий, $20K, 100K строк Rust
- **Нет оркестрирующего агента**. Простой loop: `while true; do claude -p "$(cat PROMPT.md)"; done`
- Каждый агент сам решает что делать
- Главный рычаг: **чрезвычайно качественные тесты**
- File-based synchronization (lock files в current_tasks/)

Цитата: *"Most of my effort went into designing the environment around Claude — the tests, the environment, the feedback — so that it could orient itself without me."*

Ключевые инсайты:
- Time blindness: LLM не чувствует время → harness печатает прогресс редко
- Context pollution: тесты не должны печатать тысячи бесполезных байт → summary statistics
- `--fast` option: 1-10% random sample тестов для быстрой обратной связи

### 3. Orchestrator-Worker с Filesystem IPC (Anthropic Research, Jun 2025)

**Источник:** https://www.anthropic.com/engineering/multi-agent-research-system

- Lead agent координирует, subagents выполняют параллельно
- Subagents пишут в filesystem, не обратно в контекст lead'а
- Token usage explains 80% of performance variance
- "Prompting strategy focuses on instilling good heuristics rather than rigid rules"

Цитата: *"Subagent output to a filesystem to minimize the 'game of telephone.' Direct subagent outputs can bypass the main coordinator."*

---

## Tier 2: Community-Validated

### 4. Superpowers (57K stars, v4.3.0, Feb 2026)

**Источник:** https://github.com/obra/superpowers, https://blog.fsck.com/releases/2026/02/12/superpowers-v4-3-0/

Их v4.3.0 описывает нашу проблему:
> *"The brainstorming skill already described the right process. But it described the process the way a textbook describes good habits. Descriptive, not prescriptive. And I am very good at rationalizing my way past descriptions."*

Решение: **hooks делают процесс non-optional**, не bash-скрипты.

### 5. Google Conductor (обновление Feb 13, 2026)

**Источник:** https://developers.googleblog.com/conductor-update-introducing-automated-reviews/

Persistent context markdown → spec → plan → implement. State machine через наличие файлов.

---

## Tier 3: Сегодняшний синтез

### 6. Guardrails for Agentic Coding (Van Eyck, Feb 22, 2026)

**Источник:** https://jvaneyck.wordpress.com/2026/02/22/guardrails-for-agentic-coding-how-to-move-up-the-ladder-without-lowering-your-bar/

Принципы:
- "If there's a deterministic tool for the job, don't 'prompt' the model to do the tool's work."
- "More autonomy → more constraints, tighter loops, more deterministic validation."
- "Hooks are deterministic. This isn't 'prompt the agent to remember.' It's 'tests run because the workflow requires it.'"
- "Grow your agentic layer, don't big bang it"
- Validate only the DIFF, not the whole codebase
- Wrapper scripts reduce noise in context

---

## Анти-паттерны (что НЕ работает)

| Анти-паттерн | Источник |
|---|---|
| Role-based multi-agent (planner/coder/tester/reviewer) | Anthropic: "spent more tokens on coordination than actual work" |
| Bash-скрипты вызывающие `claude --auto` последовательно | Нет прецедентов для production SDLC |
| YAML schema validation между каждым шагом | Overengineering, нет прецедентов |
| Жёсткое внешнее управление процессом | Anthropic: "good heuristics rather than rigid rules" |

---

## Решение для DLD: Spark + Autopilot

### Spark — enforcement research phase:
- Hook: нельзя создать spec без наличия research-файлов
- JSON session state вместо "LLM помнит фазу"
- Validation script проверяет spec completeness перед `queued`

### Autopilot — enforcement execution loop:
- Hook: нельзя писать код без плана в spec
- Hook: нельзя коммитить без прохождения тестов
- JSON task-progress вместо markdown пометок
- Wrapper для test output (меньше шума в контексте)
- autopilot-loop.sh (fresh session per spec) — усилить

### Принцип:
- Процесс остаётся в промптах (SKILL.md, agent.md)
- Enforcement переезжает в hooks + validation scripts
- State переезжает в JSON
- Качество обеспечивают тесты, не дополнительные агенты

---

## Дополнительные источники

- Building effective agents (Anthropic, Dec 2024): https://www.anthropic.com/research/building-effective-agents
- autonomous-dev 8-Agent Pipeline: https://github.com/akaszubski/autonomous-dev
- Claude Code Agent Teams: https://claudefa.st/blog/guide/agents/agent-teams
