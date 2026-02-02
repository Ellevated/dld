---
name: council
description: |
  Multi-agent review with 5 expert perspectives for architectural decisions.

  AUTO-ACTIVATE when user says:
  - "should we", "which approach", "what's better"
  - "debate", "discuss options", "pros and cons"
  - "review architecture", "review design"
  - "controversial", "risky change"

  Also activate when:
  - Change affects >10 files
  - Breaking change to API/interfaces
  - User uncertain about approach

  DO NOT USE when:
  - Simple task (<3 files) → just implement
  - Urgent hotfix → fix directly
  - User wants to create spec → use spark
  - User wants implementation → use autopilot
model: opus
---

# Council v2.0 — Multi-Agent Review (Karpathy Protocol)

5 experts analyze spec through 3-phase protocol.

**Activation:** `council`, `/council`

## When to Use

- Escalation from Autopilot (Spark created BUG spec, but needs review)
- Complex changes affecting architecture
- Human requests review before implementation
- Controversial decisions (breaking changes, >10 files)

**Don't use:** Hotfixes, simple bugs, tasks < 3 files

## Experts (LLM-Native Mindset)

| Role | Name | Focus | Key Question |
|------|------|-------|--------------|
| **Architect** | Winston | DRY, SSOT, dependencies, scale | "Where else is this logic? Who owns the data?" |
| **Security** | Viktor | OWASP, vulnerabilities, attack surface | "How can this be broken?" |
| **Pragmatist** | Amelia | YAGNI, complexity, feasibility | "Can it be simpler? Is it needed now?" |
| **Product** | John | User journey, edge cases, consistency | "What does user see? How does this affect the flow?" |
| **Synthesizer** | Oracle | Chairman — final decision, trade-offs | Synthesizes decision from all inputs |

### LLM-Native Mindset (CRITICAL!)

All experts MUST think in terms of LLM development:

```
❌ "Refactoring will take a month of team work"
✅ "Refactoring = 1 hour LLM work, ~$5 compute"

❌ "This is too complex to implement"
✅ "LLM will handle it, but needs clear plan"

❌ "Need to write many tests"
✅ "Tester subagent will generate tests automatically"
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

All 4 experts (except Synthesizer) run **in parallel** as subagents:

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  Architect  │  Security   │  Pragmatist │   Product   │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
       │             │             │             │
       └─────────────┴──────┬──────┴─────────────┘
                            ▼
                    Collect 4 independent analyses
```

**Model:** Defined in each agent's frontmatter (`council-*.md`). SSOT — don't duplicate here.

**Each expert:**
1. Receives spec/problem
2. **MUST** search Exa (patterns, risks, examples)
3. Forms verdict with reasoning
4. Returns structured output

### Phase 2: CROSS-CRITIQUE (Peer Review)

Each expert sees **anonymized** responses from others:

```
Expert A sees:
- "Analysis 1: [content]"
- "Analysis 2: [content]"
- "Analysis 3: [content]"

And responds:
- Agree/disagree with each
- Gaps and weak points
- Ranking: best → worst
```

**Important:** Anonymization prevents bias ("Architect said it, so it's correct")

### Phase 3: SYNTHESIS (Chairman)

**Synthesizer (Oracle)** receives:
- All 4 primary analyses
- All cross-critiques
- Rankings from each

And forms:
```yaml
decision: approved | needs_changes | rejected | needs_human
reasoning: "Brief justification"
changes_required: [...] # if needs_changes
dissenting_opinions: [...] # who disagreed and why
confidence: high | medium | low
```

## Expert Subagent Format

Each expert — separate subagent with isolated context.

**Note:** `subagent_type` matches agent's `name` in frontmatter (e.g., `council-architect`), not file path (`council/architect.md`).

### Phase 1: PARALLEL ANALYSIS

```yaml
# Launch experts (parallel)
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

After receiving 4 analyses — each expert sees **anonymized** responses from others:

```yaml
# Launch cross-critique (parallel)
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

After cross-critique — Synthesizer receives everything:

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

**Note:** Each agent has frontmatter with model=opus and necessary tools (Exa, Read, Grep, Glob).

## Exa Research (MANDATORY)

**Each expert MUST search:**

| Expert | Search Focus |
|--------|--------------|
| Architect | Architecture patterns, similar systems, scaling approaches |
| Security | Known vulnerabilities, OWASP patterns, security best practices |
| Pragmatist | Implementation examples, complexity analysis, YAGNI patterns |
| Product | UX patterns, user journey examples, edge case handling |

**Research format in output:**
```markdown
### Research
- Query: "telegram bot rate limiting patterns 2025"
- Found: [Telegram Bot Best Practices](url) — use middleware approach
- Found: [Rate Limit Strategies](url) — token bucket > sliding window
```

## Voting & Decision

**Simple majority + Synthesizer:**

| Scenario | Decision |
|----------|----------|
| 3-4 approve | approved |
| 2-2 split | Synthesizer decides |
| 3-4 reject | rejected |
| Any "needs_human" | → Human escalation |

**Synthesizer can override** if sees critical issue missed by others.

## Output Format

```yaml
status: approved | needs_changes | rejected | needs_human
decision_summary: "What was decided and why"

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

When Spark created BUG spec and needs review:

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
| needs_changes | Update spec → autopilot (or council again) |
| rejected | → spark with new approach |
| needs_human | ⚠️ Blocker — wait for human input |

## Limits

| Condition | Action |
|-----------|--------|
| Simple task (<3 files) | Skip council, go autopilot |
| Urgent hotfix | Skip council, fix directly |
| Council disagrees 2x | → human (don't loop) |
