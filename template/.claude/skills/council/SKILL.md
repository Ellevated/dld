---
name: council
description: Multi-agent review with 5 expert perspectives for complex architectural decisions
model: opus
---

# Council v2.0 — Multi-Agent Review (Karpathy Protocol)

5 экспертов анализируют спеку через 3-phase protocol.

**Activation:** `council`, `/council`

## When to Use

- Escalation от Autopilot (Spark создал BUG spec, но нужен review)
- Сложные изменения, затрагивающие архитектуру
- Human просит review перед реализацией
- Controversial decisions (breaking changes, >10 files)

**Don't use:** Hotfixes, простые баги, задачи < 3 файлов

## Experts (LLM-Native Mindset)

| Role | Name | Focus | Key Question |
|------|------|-------|--------------|
| **Architect** | Winston | DRY, SSOT, dependencies, scale | "Где ещё эта логика? Кто owner данных?" |
| **Security** | Viktor | OWASP, vulnerabilities, attack surface | "Как это можно сломать?" |
| **Pragmatist** | Amelia | YAGNI, complexity, feasibility | "Можно проще? Нужно ли сейчас?" |
| **Product** | John | User journey, edge cases, consistency | "Что видит пользователь? Как это влияет на flow?" |
| **Synthesizer** | Oracle | Chairman — final decision, trade-offs | Синтезирует решение из всех inputs |

### LLM-Native Mindset (CRITICAL!)

Все эксперты ДОЛЖНЫ мыслить в терминах LLM-разработки:

```
❌ "Рефакторинг займёт месяц работы команды"
✅ "Рефакторинг = 1 час LLM работы, ~$5 compute"

❌ "Это слишком сложно для реализации"
✅ "LLM справится, но нужен чёткий план"

❌ "Нужно много тестов писать"
✅ "Tester субагент сгенерирует тесты автоматически"
```

## Phase 0: Load Context (MANDATORY — NEW)

**Before any expert analysis, load project context ONCE:**

```bash
Read: .claude/rules/dependencies.md
Read: .claude/rules/architecture.md
```

**Each expert receives this context in their prompt:**
- Current dependency graph (who uses what)
- Established patterns (what to follow)
- Anti-patterns (what to avoid)

**This ensures all 5 experts have architectural awareness.**

Include in expert prompts:
```yaml
context:
  dependencies: [summary from dependencies.md]
  patterns: [key patterns from architecture.md]
  anti_patterns: [anti-patterns to watch for]
```

---

## 3-Phase Protocol (Karpathy)

### Phase 1: PARALLEL ANALYSIS (Divergence)

Все 4 эксперта (кроме Synthesizer) запускаются **параллельно** как субагенты:

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  Architect  │  Security   │  Pragmatist │   Product   │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
       │             │             │             │
       └─────────────┴──────┬──────┴─────────────┘
                            ▼
                    Собираем 4 независимых анализа
```

**Model:** Defined in each agent's frontmatter (`council-*.md`). SSOT — don't duplicate here.

**Каждый эксперт:**
1. Получает spec/problem
2. **ОБЯЗАТЕЛЬНО** ищет в Exa (patterns, risks, examples)
3. Формирует verdict с reasoning
4. Возвращает structured output

### Phase 2: CROSS-CRITIQUE (Peer Review)

Каждый эксперт видит **анонимизированные** ответы других:

```
Expert A видит:
- "Analysis 1: [content]"
- "Analysis 2: [content]"
- "Analysis 3: [content]"

И отвечает:
- Согласен/не согласен с каждым
- Gaps и weak points
- Ranking: best → worst
```

**Важно:** Анонимизация предотвращает bias ("Architect сказал, значит правильно")

### Phase 3: SYNTHESIS (Chairman)

**Synthesizer (Oracle)** получает:
- Все 4 первичных анализа
- Все cross-critiques
- Rankings от каждого

И формирует:
```yaml
decision: approved | needs_changes | rejected | needs_human
reasoning: "Краткое обоснование"
changes_required: [...] # если needs_changes
dissenting_opinions: [...] # кто был против и почему
confidence: high | medium | low
```

## Expert Subagent Format

Каждый эксперт — отдельный субагент с изолированным контекстом.

**Note:** `subagent_type` matches agent's `name` in frontmatter (e.g., `council-architect`), not file path (`council/architect.md`).

### Phase 1: PARALLEL ANALYSIS

```yaml
# Запуск экспертов (параллельно)
Task:
  subagent_type: council-architect  # → agents/council/architect.md
  prompt: |
    PHASE: 1
    Analyze this spec/problem:
    [spec_content]

Task:
  subagent_type: council-product
  prompt: |
    PHASE: 1
    Analyze this spec/problem:
    [spec_content]

Task:
  subagent_type: council-pragmatist
  prompt: |
    PHASE: 1
    Analyze this spec/problem:
    [spec_content]

Task:
  subagent_type: council-security
  prompt: |
    PHASE: 1
    Analyze this spec/problem:
    [spec_content]
```

**⏳ SYNC POINT:** Wait for ALL 4 Task agents to complete before Phase 2.
Store results in variables: `architect_analysis`, `product_analysis`, `pragmatist_analysis`, `security_analysis`.

### Phase 2: CROSS-CRITIQUE

После получения 4 анализов — каждый эксперт видит **анонимизированные** ответы других:

```yaml
# Запуск cross-critique (параллельно)
Task:
  subagent_type: council-architect
  prompt: |
    PHASE: 2
    Your initial analysis:
    [architect_analysis]

    Review these anonymized peer analyses:
    - Analysis A: [product_analysis]
    - Analysis B: [pragmatist_analysis]
    - Analysis C: [security_analysis]

Task:
  subagent_type: council-product
  prompt: |
    PHASE: 2
    Your initial analysis:
    [product_analysis]

    Review these anonymized peer analyses:
    - Analysis A: [architect_analysis]
    - Analysis B: [pragmatist_analysis]
    - Analysis C: [security_analysis]

Task:
  subagent_type: council-pragmatist
  prompt: |
    PHASE: 2
    Your initial analysis:
    [pragmatist_analysis]

    Review these anonymized peer analyses:
    - Analysis A: [architect_analysis]
    - Analysis B: [product_analysis]
    - Analysis C: [security_analysis]

Task:
  subagent_type: council-security
  prompt: |
    PHASE: 2
    Your initial analysis:
    [security_analysis]

    Review these anonymized peer analyses:
    - Analysis A: [architect_analysis]
    - Analysis B: [product_analysis]
    - Analysis C: [pragmatist_analysis]
```

**⏳ SYNC POINT:** Wait for ALL 4 cross-critique Task agents to complete before Phase 3.
Store results: `architect_cross_critique`, `product_cross_critique`, `pragmatist_cross_critique`, `security_cross_critique`.

### Phase 3: SYNTHESIS

После cross-critique — Synthesizer получает всё:

```yaml
Task:
  subagent_type: council-synthesizer
  prompt: |
    PHASE: 3

    Initial analyses (Phase 1):
    - Architect: [architect_analysis]
    - Product: [product_analysis]
    - Pragmatist: [pragmatist_analysis]
    - Security: [security_analysis]

    Cross-critiques (Phase 2):
    - Architect critique: [architect_cross_critique]
    - Product critique: [product_cross_critique]
    - Pragmatist critique: [pragmatist_cross_critique]
    - Security critique: [security_cross_critique]

    Synthesize final decision.
```

**Note:** Каждый агент имеет frontmatter с model=opus и необходимыми tools (Exa, Read, Grep, Glob).

## Exa Research (MANDATORY)

**Каждый эксперт ОБЯЗАН искать:**

| Expert | Search Focus |
|--------|--------------|
| Architect | Architecture patterns, similar systems, scaling approaches |
| Security | Known vulnerabilities, OWASP patterns, security best practices |
| Pragmatist | Implementation examples, complexity analysis, YAGNI patterns |
| Product | UX patterns, user journey examples, edge case handling |

**Формат research в output:**
```markdown
### Research
- Query: "telegram bot rate limiting patterns 2025"
- Found: [Telegram Bot Best Practices](url) — use middleware approach
- Found: [Rate Limit Strategies](url) — token bucket > sliding window
```

## Voting & Decision

**Простое большинство + Synthesizer:**

| Scenario | Decision |
|----------|----------|
| 3-4 approve | approved |
| 2-2 split | Synthesizer decides |
| 3-4 reject | rejected |
| Any "needs_human" | → Human escalation |

**Synthesizer может override** если видит critical issue, пропущенный другими.

## Output Format

```yaml
status: approved | needs_changes | rejected | needs_human
decision_summary: "Что решили и почему"

votes:
  architect: approve
  security: approve_with_changes
  pragmatist: approve
  product: reject
  synthesizer: approve_with_changes

changes_required:
  - "Add rate limiting to endpoint X"
  - "Cover edge case Y in tests"

dissenting_opinions:
  - expert: product
    concern: "User flow breaks on mobile"
    resolution: "Addressed in changes_required[2]"

research_highlights:
  - "[Pattern X](url) — adopted"
  - "[Risk Y](url) — mitigated via Z"

confidence: high | medium | low
next_step: autopilot | spark | human
```

## Escalation Mode (from Autopilot)

Когда Spark создал BUG spec и нужен review:

**Input:**
```yaml
escalation_type: bug_review | architecture_change
spec_path: "ai/features/BUG-XXX.md"
context: "Why Council is needed"
```

**Process:**
1. All experts read spec
2. Phase 1-2-3 as usual
3. Output includes fix validation

## After Council

| Result | Next Step |
|--------|-----------|
| approved | → autopilot |
| needs_changes | Update spec → autopilot (или council повторно) |
| rejected | → spark с новым подходом |
| needs_human | ⚠️ Блокер — ждём human input |

## Limits

| Condition | Action |
|-----------|--------|
| Simple task (<3 files) | Skip council, go autopilot |
| Urgent hotfix | Skip council, fix directly |
| Council disagrees 2x | → human (не зацикливаться) |
