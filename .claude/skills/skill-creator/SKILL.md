---
name: skill-creator
description: Create new skills, modify existing skills, and measure skill performance. Triggers on keywords: create skill, new skill, write skill, eval skill, benchmark skill, optimize skill, improve skill, update CLAUDE.md, update rules, skill-creator
model: opus
project-agnostic: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
  - Agent
---

# Skill Creator — Create, Eval, and Iterate on Skills

Create skills from scratch, test them with evals, improve based on data, and benchmark performance.

**Activation:**
- `skill-creator create {name}` — new skill/agent with eval-driven iteration
- `skill-creator eval {skill-path}` — test existing skill against prompts
- `skill-creator update {target}` — optimize CLAUDE.md, rules, agents (preserved from v1)
- `skill-creator benchmark {skill-path}` — variance analysis across multiple runs

---

## Communicating with the User

- Audience spans non-coders to engineers — read context cues
- Technical terms like "evaluation" and "benchmark" are fine
- Terms like "JSON schema" or "assertion" — explain unless user signals familiarity
- Show progress after each phase, not just at the end

---

## CREATE Mode

### Phase 1: Capture Intent

Extract from conversation if workflow already present. If not, ask:

1. **What:** One sentence — what does the skill do?
2. **Who calls:** User / autopilot / both?
3. **Tools needed:** Read, Edit, Bash, MCP tools, etc.
4. **Model:** opus (complex reasoning) / sonnet (routine) / haiku (simple capture)
5. **Anti-patterns:** What should the skill NEVER do?

> **ALWAYS/NEVER anti-pattern:** If you find yourself writing ALWAYS or NEVER in caps, that's a yellow flag. Instead, explain the WHY so the model gets reasoning, not just a rule.

### Phase 2: Research

Use Exa + Context7 for best practices (max 3 calls, skip if trivial):

```yaml
mcp__exa__web_search_exa:
  query: "{skill_type} best practices claude code 2025 2026"
  numResults: 5
```

### Phase 3: Determine Type

```
Need reusable prompt for Autopilot?
  YES → Wrapper (agent + skill)
  NO  → Multi-agent orchestration?
        YES → Orchestrator
        NO  → Standalone
```

| Type | Description | Has Agent File? |
|------|-------------|-----------------|
| Wrapper | Thin layer over agent | Yes (agents/*.md) |
| Orchestrator | Dispatches multiple agents | No |
| Standalone | Self-contained logic | No |

### Phase 4: Write Draft

Follow progressive disclosure (3-level loading):
1. **Metadata** (~100 tokens): name + description in frontmatter — always in context
2. **Body** (<500 lines): SKILL.md instructions — loaded when skill triggers
3. **Resources** (unlimited): scripts/, references/, assets/ — loaded on demand

**Frontmatter template:**
```yaml
---
name: skill-name
description: Third-person description. Triggers on keywords: keyword1, keyword2
model: opus|sonnet|haiku
project-agnostic: false
allowed-tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---
```

**Agent template:**
```markdown
---
name: {name}
description: {One-line}
model: {opus|sonnet|haiku}
tools: {Read, Glob, Grep, Edit, Write, Bash, ...}
---

# {Name} Agent

{Mission.}

## Input
{input spec}

## Process
1. {Steps}

## Output
{output spec}

## Rules
- {Rules}
```

### Phase 5: Create Test Cases

Generate 5-10 test prompts in `evals/evals.json`:

```json
{
  "skill_name": "my-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "task to execute",
      "expected_output": "description of expected result",
      "assertions": [
        { "id": "check-output", "text": "Output includes expected section", "type": "quality" },
        { "id": "file-created", "text": "File was created at correct path", "type": "deterministic" }
      ]
    }
  ]
}
```

**Assertion types:**
- `deterministic` — binary pass/fail (file exists, grep matches, exit code)
- `quality` — LLM-judged (content quality, completeness, style)

### Phase 6: Run + Grade

1. Run eval via script: `node .claude/scripts/run-eval.mjs --skill-path {path} --evals-path {evals}`
2. Grade outputs using eval-judge agent (reused as grader):

```yaml
Agent:
  subagent_type: eval-judge
  prompt: |
    Grade this skill output against rubric:
    - Structure clarity (1-5)
    - Activation triggers (1-5)
    - Protective sections (1-5)
    - Completeness (1-5)
    - Overall quality (1-5)
```

### Phase 7: Compare (Blind A/B)

If updating an existing skill, use comparator for blind A/B:

```yaml
Agent:
  subagent_type: comparator
  prompt: |
    Compare these two outputs blindly.
    Output A: {old_skill_output}
    Output B: {new_skill_output}
    Task: {eval_prompt}
```

The comparator doesn't know which is old/new. Returns winner + reasoning.

### Phase 8: Analyze Patterns

After grading, use analyzer to surface non-obvious patterns:

```yaml
Agent:
  subagent_type: analyzer
  prompt: |
    Analyze benchmark data from: {workspace_path}
    Look for: non-discriminating assertions, high-variance evals, time/token tradeoffs
```

### Phase 9: Improve

Based on grading + analysis:
1. Identify weakest areas from rubric scores
2. Rewrite specific sections (not full rewrite)
3. Re-run evals on changed sections
4. Compare new vs old via comparator

### Phase 10: Iterate

Repeat Phases 6-9 until:
- User is satisfied, OR
- 3 consecutive iterations show no improvement, OR
- All assertions pass at > 80% rate

### Phase 11: Write Final

1. Create directory: `.claude/skills/{name}/`
2. Write `SKILL.md`
3. If wrapper → also write `.claude/agents/{name}.md`
4. Save evals: `.claude/skills/{name}/evals/evals.json`
5. Register in CLAUDE.md Skills table (if user-invocable)

---

## EVAL Mode

Test an existing skill against prompts. No modification.

### Process

1. Load test cases from `{skill-path}/evals/evals.json`
   - If none exist, help user create 5-10 test prompts
2. For each eval:
   a. Run skill via: `node .claude/scripts/run-eval.mjs --skill-path {path} --evals-path {evals}`
   b. Grade output via eval-judge (rubric scoring)
3. Generate markdown report:

```markdown
## Eval Results — {skill_name}

| # | Prompt | Pass Rate | Score | Notes |
|---|--------|-----------|-------|-------|
| 1 | "..." | 3/4 | 4.2 | Missing X |

### Summary
- Overall pass rate: 85%
- Avg score: 4.1/5
- Weakest: assertion "check-completeness" (60%)
```

4. Present to user with recommendations

---

## UPDATE Mode

Optimize CLAUDE.md, rules, agents. Preserved from v1.

### Phase 1: Requirements

- **Target file:** Which file to optimize?
- **What to change:** Specific section or full optimization?
- **Source:** From /reflect spec or direct request?

### Documentation Hierarchy

```
1. CLAUDE.md          — always loaded, < 200 lines
2. .claude/rules/     — conditional (paths: frontmatter), < 500 lines
3. .claude/agents/    — loaded per Task tool dispatch
4. .claude/skills/    — loaded per Skill tool invocation
5. Co-located (src/)  — loaded when reading nearby code
```

### What Belongs Where

| Content | Location |
|---------|----------|
| Universal rules, commands | `CLAUDE.md` |
| Domain-specific logic | `.claude/rules/{domain}.md` |
| Agent execution behavior | `.claude/agents/{name}.md` |
| User-facing skill flow | `.claude/skills/{name}/SKILL.md` |
| Code style | Linter config (NOT docs) |

### Preservation Checklist (BEFORE Three-Expert)

**CRITICAL:** Before removing ANY section, check if it's a protective mechanism:

| Section Type | Purpose | Can Remove? |
|--------------|---------|-------------|
| "What NOT to Do" | Prevents common mistakes | NEVER without explicit approval |
| "Quality Checklist" | Ensures completeness | NEVER without explicit approval |
| "When to Use" | Prevents misuse | Only if activation triggers are clear |
| "Terminology" | Prevents confusion | Only if terms are obvious |
| "Rules" at end | Reinforces critical behavior | Can compress, not delete |
| Examples (yaml/code) | Shows correct usage | Keep at least 1 per pattern |

**Rule:** If unsure, KEEP IT. Better verbose than broken.

### Three-Expert Gate

**Apply ONLY to content that passed Preservation Checklist.**

**Karpathy (Remove redundancy):**
- Does Claude already know this? Remove **if not protective**.
- "If I remove this line, will output worsen?" No → remove.
- HOW to think vs WHAT to achieve? Prefer WHAT.

**Sutskever (Unlock capability):**
- Constraining vs guiding? Principles > procedures.
- Fighting model's strengths? Examples > descriptions.

**Murati (Simplify UX):**
- Did you check Preservation Checklist first?
- Can steps be eliminated?
- Is input/output format minimal?

### Write Changes

1. Apply changes to target file
2. Verify limits after edit: `wc -l {file}`
3. Check no duplication introduced
4. Report what changed

---

## BENCHMARK Mode

Variance analysis across multiple runs of the same skill.

### Process

1. Run N iterations (default 3, max 10): `node .claude/scripts/run-eval.mjs` per iteration
2. Aggregate results: `node .claude/scripts/aggregate-benchmark.mjs --workspace {path}`
3. Analyze with analyzer agent for patterns aggregate stats hide
4. Generate benchmark report:

```markdown
## Benchmark — {skill_name}

### Summary (N=3 runs)
| Metric | Mean | StdDev | Min | Max |
|--------|------|--------|-----|-----|
| Pass rate | 85% | ±5% | 80% | 90% |
| Tokens | 12.4K | ±1.2K | 11K | 14K |
| Time | 45s | ±8s | 38s | 55s |

### Per-Assertion Variance
| Assertion | Pass Rate | Notes |
|-----------|-----------|-------|
| check-output | 100% | Stable |
| check-style | 67% | High variance — unreliable |

### Analyzer Notes
- {pattern observations from analyzer agent}
```

5. Present to user with improvement recommendations

---

## Description Optimization

Optimize skill description for trigger accuracy.

### Process

1. Generate 20 trigger queries:
   - 10 positive (should activate this skill)
   - 5 negative (should NOT activate)
   - 5 edge cases (ambiguous)
2. User reviews queries via markdown table
3. Split 60% train / 40% test
4. Run `node .claude/scripts/improve-description.mjs`:
   - Evaluate current description (3 runs per query)
   - Propose improved description
   - Re-evaluate on train set
   - Validate on held-out test set
   - Accept if test accuracy improves
5. Max 5 iterations
6. Report before/after accuracy

---

## Anti-Patterns

| Don't | Do |
|-------|-----|
| Duplicate across files | Single source of truth |
| Code style in docs | Linter config |
| Count manually | `wc -l`, `grep -c` |
| > 200 lines CLAUDE.md | Split to rules/ |
| Overspecify steps | Principles + examples |
| Delete protective sections | Check Preservation Checklist first |
| ALWAYS/NEVER in caps | Explain the WHY instead |
| Full rewrite on iteration | Targeted section rewrites |

---

## Validation

**Naming:** lowercase, hyphenated (`my-skill`, not `MySkill`)

**Structure checks:**
- Agent has: frontmatter, Input, Process, Output, Rules
- Skill has: frontmatter, Activation, Process
- Frontmatter has: name, description, model (agent), tools (agent)

**Limits:** Always verify with `wc -l {file}`

---

## Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `run-eval.mjs` | Run skill against test prompts | `node .claude/scripts/run-eval.mjs --skill-path X --evals-path Y` |
| `improve-description.mjs` | Optimize description triggers | `node .claude/scripts/improve-description.mjs --skill-path X` |
| `aggregate-benchmark.mjs` | Variance analysis | `node .claude/scripts/aggregate-benchmark.mjs --workspace X` |

---

## Agents

| Agent | Role | Model |
|-------|------|-------|
| eval-judge (reuse) | Rubric-based grading | sonnet |
| comparator (new) | Blind A/B comparison | sonnet |
| analyzer (new) | Benchmark pattern analysis | sonnet |
