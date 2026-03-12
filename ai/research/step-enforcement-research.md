# Исследование: Как защитить Bug Hunt от пропуска шагов

**Date:** 2026-02-14
**Method:** 3 parallel scouts (Exa) + Sequential Thinking (9 steps)
**Sources:** 30+ sources, 5 academic papers, official docs Anthropic/LangGraph/CrewAI

---

## TL;DR

**Индустриальный консенсус (все источники сходятся):**
> LLM ненадёжен в отслеживании своего прогресса через multi-step процедуры.
> Внешний state tracking — не опция, а архитектурное ТРЕБОВАНИЕ.
> Код контролирует flow. LLM работает ВНУТРИ шагов, но НИКОГДА не решает какой шаг следующий.

**Лучшее решение для Claude Code:** 3-слойная защита.

---

## Ключевые findings по источникам

### Академические papers

| Paper | Год | Главный результат |
|-------|-----|-------------------|
| **Blueprint First, Model Second** (arXiv 2508.02721) | 2025 | Workflow как код + LLM для подзадач = +10.1% SOTA. Gate check ("Double-Check") = **+11.7%** самый большой вклад |
| **Agent-C** (arXiv 2512.23738) | 2025 | Формальные temporal constraints через SMT solving = **100% conformance** на Claude Sonnet 4.5 (было 77.4%). При этом utility ВЫРОСЛА |
| **StateFlow** (arXiv 2403.11322) | 2024 | FSM (Init→Observe→Solve→Verify→Error) = 13-28% лучше ReAct при 3-5x меньше cost |
| **DSPy Assertions** (ICLR 2024) | 2024 | Assert/Suggest с backtracking retry = +35.7% constraint compliance |
| **SagaLLM** (Stanford) | 2025 | Saga транзакции для LLM: каждый шаг имеет compensating action для rollback |

### Фреймворки (что делают другие)

| Framework | Как enforces порядок | Применимо к Claude Code? |
|-----------|---------------------|--------------------------|
| **LangGraph** | StateGraph: nodes = Python functions, edges = code. LLM внутри node, не контролирует flow | Нет (Python runtime) |
| **CrewAI** | `Process.sequential`: tasks в порядке массива, output N → context N+1 | Частично (паттерн) |
| **Temporal** | Durable execution: автоматический retry + crash recovery + replay | Нет (инфраструктура) |
| **DSPy** | `dspy.Assert()`: validation + backtracking retry | Частично (паттерн) |
| **Instructor** | Pydantic schema validation + retry loop | Частично (паттерн) |

### Claude Code специфика

| Механизм | Тип | Надёжность |
|----------|-----|------------|
| **Hooks (exit code 2)** | Детерминистический | Высокая — выполняется ВСЕГДА, LLM не контролирует |
| **Subagent tool restrictions** | Архитектурный | Высокая — tools в frontmatter = allowlist |
| **Stop hook** | Детерминистический | Высокая — блокирует завершение |
| **TaskCompleted hook** | Детерминистический | Высокая — блокирует закрытие задачи |
| **SubagentStop hook** | Детерминистический | Высокая — блокирует завершение субагента |
| **PreToolUse hook** | Детерминистический | Средняя — был баг #4362 (fix: use permissionDecision) |
| **Plan mode** | Human-in-the-loop | Высокая, но требует ручного approval |
| **Prompt instruction** | Вероятностный | **НИЗКАЯ** — BUG-084 доказал |

---

## Решение для Bug Hunt: 3-Layer Defense

### Слой 1: THIN ORCHESTRATOR (архитектурный)

**Принцип из "Blueprint First":** Оркестратор — это КОД (последовательность вызовов), не LLM с инструкцией.

**Реализация в Claude Code:**

```
SKILL.md (bug-hunt) = ОДНА строка:
  "Launch Task(bughunt-orchestrator) with target path"

bughunt-orchestrator.md:
  tools: Task    ← ТОЛЬКО Task tool. Не может Read, Write, Grep, Glob.

  Промпт: последовательно вызови 8 субагентов.
  Для каждого: передай output предыдущего как input.
```

**Почему работает:** Оркестратор ФИЗИЧЕСКИ не может делать работу сам — у него нет инструментов. Может ТОЛЬКО делегировать. Как менеджер без рук — не может написать код, может только дать задание.

**Что это даёт:**
- Не может пропустить шаг (нет инструментов чтобы сделать работу самому)
- Не может батчить (каждый шаг = отдельный Task() call)
- Не может "оптимизировать" (нет информации о "тривиальности" задачи)

### Слой 2: PRECONDITION CHECKS (defense in depth)

**Принцип из StateFlow:** Каждый state проверяет свои preconditions.

**Реализация:**

Каждый step-agent при старте:
1. Читает файл-артефакт предыдущего шага
2. Валидирует его структуру
3. Если файла нет или структура invalid → STOP, return error

```yaml
# В каждом step-agent.md:

## Precondition Check (EXECUTE FIRST)
Read `ai/bug-hunt/session/step-{N-1}-*.yaml`
If file does not exist → STOP. Return:
  "ERROR: Step {N-1} output not found. Cannot proceed."
If file exists but missing required fields → STOP. Return:
  "ERROR: Step {N-1} output incomplete: missing {field}."
```

**Файловая цепочка:**
```
session/step-0-zones.yaml          ← Step 0 output
session/step-1-raw-findings.yaml   ← Step 1 output (requires step-0)
session/step-2-summary.yaml        ← Step 2 output (requires step-1)
session/step-3-framework.yaml      ← Step 3 output (requires step-2)
session/step-4-spec.md             ← Step 4 output (requires step-2 + step-3)
session/step-5-validation.yaml     ← Step 5 output (requires step-4)
session/step-6-report.md           ← Step 6 output (requires step-5)
session/step-7-specs.yaml          ← Step 7 output (requires step-5)
```

**Почему работает:** Даже если оркестратор вызовет шаг не по порядку — субагент сам откажется работать без input файла.

### Слой 3: HOOK ENFORCEMENT (детерминистический турникет)

**Принцип из Agent-C + Claude Code hooks:** Детерминистическая проверка, которую LLM не контролирует.

**Реализация:**

```javascript
// .claude/hooks/bug-hunt-gate.mjs
// PreToolUse hook for Write tool

import { readFileSync, existsSync } from 'fs';

const input = JSON.parse(process.argv[2] || '{}');

// Only applies to bug-hunt session files
const filePath = input?.tool_input?.file_path || '';
if (!filePath.includes('ai/bug-hunt/session/')) {
  process.exit(0); // Not a bug-hunt file, allow
}

// Extract step number from filename
const match = filePath.match(/step-(\d+)/);
if (!match) process.exit(0);

const stepNum = parseInt(match[1]);
if (stepNum === 0) process.exit(0); // First step, no prereq

// Check prerequisite exists
const prevPattern = `ai/bug-hunt/session/step-${stepNum - 1}-`;
// ... check if file with prevPattern exists
if (!prerequisiteExists) {
  console.error(`BLOCKED: Cannot write step-${stepNum} without step-${stepNum-1}`);
  process.exit(2); // EXIT 2 = BLOCK
}

process.exit(0); // Allow
```

**Почему работает:** Hook выполняется ВСЕГДА при попытке Write в session directory. LLM не контролирует hook. Exit code 2 = физический блок. Это ТУРНИКЕТ.

---

## Сравнение с текущей архитектурой

| Аспект | Сейчас (bug-mode.md) | Предлагаемое решение |
|--------|----------------------|---------------------|
| Оркестратор | Spark (все инструменты) | Thin orchestrator (только Task) |
| Шаги 0,2,4,6 | Делает сам | Отдельные субагенты |
| Gate checks | Validator (Step 5) reject | Каждый шаг + hook |
| Файлы между шагами | Не формализовано | YAML артефакты в session/ |
| Enforcement | Промпт "execute ALL steps" | 3 слоя: tool restriction + preconditions + hooks |
| BUG-084 prevention | "⛔ Skipping = VIOLATION" | Физически невозможно пропустить |

---

## Цена решения

| Компонент | Усилие | Разовое или ongoing |
|-----------|--------|---------------------|
| bughunt-orchestrator.md | 1 файл | Разовое |
| 4 новых step-agents (0,2,4,6) | 4 файла | Разовое |
| Precondition checks в каждом agent | +5 строк на agent | Разовое |
| Hook (bug-hunt-gate.mjs) | 1 файл | Разовое |
| Session directory convention | Документация | Разовое |
| Дополнительный API cost | ~2-4 extra subagent calls | Per-run (~$1-2) |

**Total:** ~8-10 файлов, 1 день работы. Ноль ongoing cost кроме ~$1-2 per run.

---

## Ограничения и открытые вопросы

1. **Nesting depth**: Skill → orchestrator → step → persona = 3-4 уровня. Claude Code может иметь практический лимит на вложенность Task().

2. **Orchestrator tool restriction**: `tools: Task` в agent frontmatter — нужно проверить что это реально работает (не даёт Read/Write).

3. **Orchestrator может всё ещё вызвать шаги не по порядку** — Layer 2 (preconditions) и Layer 3 (hooks) ловят это, но orchestrator тратит токены на failed call.

4. **"Fabrication risk"**: Orchestrator теоретически может передать фейковые данные субагенту вместо реального output предыдущего шага. Preconditions проверяют FILE, не prompt content. Hook проверяет FILE existence. Но если orchestrator не пишет файл а передаёт данные через prompt — precondition check бесполезен.

   **Mitigation:** Субагенты ЧИТАЮТ файлы САМИ (Read tool), а не получают данные через prompt. Orchestrator передаёт только session path.

---

## Ключевые источники

| Source | Тип | Главный вклад |
|--------|-----|---------------|
| Blueprint First (arXiv 2508.02721) | Paper | Gate checks = +11.7%, workflow as code |
| Agent-C (arXiv 2512.23738) | Paper | 100% conformance через formal constraints |
| StateFlow (arXiv 2403.11322) | Paper | FSM для LLM = 13-28% лучше ReAct |
| Anthropic Multi-Agent Engineering | Blog | Orchestrator-worker, checkpoint state |
| Claude Code Hooks Docs | Official | Exit code 2, 14 lifecycle events |
| claudefa.st hooks guide | Blog | Stop hook patterns, infinite loop prevention |
| LangGraph Durable Execution | Docs | Checkpoints, interrupt, conditional edges |
| Temporal + LangGraph | Blog | Two-layer: durability + state machine |
