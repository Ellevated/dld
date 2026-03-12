---
name: council
description: Multi-agent review with 5 expert perspectives for architectural decisions.
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

## Phase 0: Load Context (MANDATORY)

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

## Session Directory

Compute before any phase:

```
SESSION_DIR = ai/.council/{YYYYMMDD}-{spec_id}/

Create structure:
  {SESSION_DIR}/
  ├── phase1/           # Expert analyses
  │   └── anonymous/    # Shuffled anonymous copies for cross-critique
  ├── phase2/           # Cross-critiques
  └── synthesis.md      # Final synthesis
```

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store agent responses in orchestrator variables
⛔ NEVER pass full agent output in another agent's prompt
⛔ NEVER use TaskOutput to read agent results
⛔ NEVER read output_file paths from background agents

✅ ALL Task calls use run_in_background: true
✅ Agents WRITE their output to SESSION_DIR files
✅ Agents READ peer files themselves (via Read tool)
✅ File gates (Glob) verify completion between phases
✅ Only synthesis.md is read by orchestrator at the end
```

---

### Cost Estimate

Before launching Phase 1, inform user (non-blocking):

```
"Council review: {SPEC_ID} — 9 agents (4 opus × 2 phases + 1 opus synthesizer), est. ~$3-8. Running..."
```

---

## 3-Phase Protocol (Karpathy)

### Phase 1: PARALLEL ANALYSIS (Divergence)

All 4 experts (except Synthesizer) run **in parallel** as background subagents:

```
┌─────────────┬─────────────┬─────────────┬─────────────┐
│  Architect  │  Security   │  Pragmatist │   Product   │
└──────┬──────┴──────┬──────┴──────┬──────┴──────┬──────┘
       │             │             │             │
       └─────────────┴──────┬──────┴─────────────┘
                            ▼
                   Write to {SESSION_DIR}/phase1/
```

**Model:** Defined in each agent's frontmatter (`council-*.md`). SSOT — don't duplicate here.

**Each expert:**
1. Receives spec/problem
2. **MUST** search Exa (patterns, risks, examples)
3. Forms verdict with reasoning
4. **Writes** output to `{SESSION_DIR}/phase1/analysis-{role}.md`

## Expert Subagent Format

Each expert — separate background subagent with isolated context.

**Note:** `subagent_type` matches agent's `name` in frontmatter (e.g., `council-architect`), not file path (`council/architect.md`).

### Phase 1: PARALLEL ANALYSIS

```yaml
# Before launching: read .claude/rules/dependencies.md and .claude/rules/architecture.md
# Compute SESSION_DIR = ai/.council/{YYYYMMDD}-{spec_id}/
# Create directory structure: phase1/, phase1/anonymous/, phase2/

# Launch experts (ALL background, ALL parallel)
Task:
  subagent_type: council-architect
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT:
      dependencies: [summary from dependencies.md]
      patterns: [key patterns from architecture.md]
      anti_patterns: [anti-patterns from architecture.md]
    Analyze this spec/problem:
    [spec_content]
    OUTPUT: Write your full analysis to {SESSION_DIR}/phase1/analysis-architect.md

Task:
  subagent_type: council-product
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT:
      dependencies: [summary from dependencies.md]
      patterns: [key patterns from architecture.md]
      anti_patterns: [anti-patterns from architecture.md]
    Analyze this spec/problem:
    [spec_content]
    OUTPUT: Write your full analysis to {SESSION_DIR}/phase1/analysis-product.md

Task:
  subagent_type: council-pragmatist
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT:
      dependencies: [summary from dependencies.md]
      patterns: [key patterns from architecture.md]
      anti_patterns: [anti-patterns from architecture.md]
    Analyze this spec/problem:
    [spec_content]
    OUTPUT: Write your full analysis to {SESSION_DIR}/phase1/analysis-pragmatist.md

Task:
  subagent_type: council-security
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT:
      dependencies: [summary from dependencies.md]
      patterns: [key patterns from architecture.md]
      anti_patterns: [anti-patterns from architecture.md]
    Analyze this spec/problem:
    [spec_content]
    OUTPUT: Write your full analysis to {SESSION_DIR}/phase1/analysis-security.md
```

**⏳ FILE GATE:** Wait for ALL 4 completion notifications, then verify:
```
Glob("{SESSION_DIR}/phase1/analysis-*.md") → must find 4 files
If < 4: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

**Anonymous label shuffling (between Phase 1 and Phase 2):**
```
Create {SESSION_DIR}/phase1/anonymous/
Copy analyses with shuffled random labels: peer-A.md, peer-B.md, peer-C.md, peer-D.md
Mapping is random each run to prevent anchoring bias
Each expert knows which label is theirs (to exclude from review)
```

### Phase 2: CROSS-CRITIQUE (Peer Review)

Each expert reads **anonymous** peer files via Read tool (NOT passed in prompt):

```yaml
# Launch cross-critique (ALL background, ALL parallel)
Task:
  subagent_type: council-architect
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial analysis: {SESSION_DIR}/phase1/analysis-architect.md
    Read anonymous peer files from {SESSION_DIR}/phase1/anonymous/:
    - peer-A.md, peer-B.md, peer-C.md
    (3 files — your own analysis is excluded, you are label {X})

    For each peer: agree/disagree, gaps, weak points, ranking best→worst.
    OUTPUT: Write critique to {SESSION_DIR}/phase2/critique-architect.md

Task:
  subagent_type: council-product
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial analysis: {SESSION_DIR}/phase1/analysis-product.md
    Read anonymous peer files from {SESSION_DIR}/phase1/anonymous/:
    - peer-A.md, peer-B.md, peer-C.md
    (3 files — your own analysis is excluded, you are label {Y})

    For each peer: agree/disagree, gaps, weak points, ranking best→worst.
    OUTPUT: Write critique to {SESSION_DIR}/phase2/critique-product.md

Task:
  subagent_type: council-pragmatist
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial analysis: {SESSION_DIR}/phase1/analysis-pragmatist.md
    Read anonymous peer files from {SESSION_DIR}/phase1/anonymous/:
    - peer-A.md, peer-B.md, peer-C.md
    (3 files — your own analysis is excluded, you are label {Z})

    For each peer: agree/disagree, gaps, weak points, ranking best→worst.
    OUTPUT: Write critique to {SESSION_DIR}/phase2/critique-pragmatist.md

Task:
  subagent_type: council-security
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial analysis: {SESSION_DIR}/phase1/analysis-security.md
    Read anonymous peer files from {SESSION_DIR}/phase1/anonymous/:
    - peer-A.md, peer-B.md, peer-C.md
    (3 files — your own analysis is excluded, you are label {W})

    For each peer: agree/disagree, gaps, weak points, ranking best→worst.
    OUTPUT: Write critique to {SESSION_DIR}/phase2/critique-security.md
```

**⏳ FILE GATE:** Wait for ALL 4 completion notifications, then verify:
```
Glob("{SESSION_DIR}/phase2/critique-*.md") → must find 4 files
If < 4: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

### Degraded Mode

If expert phases fail partially, continue with available data:

| Failed Phase | Action | Impact |
|-------------|--------|--------|
| Phase 1: 1-2 experts fail | Continue with available analyses (min 2 required) | Reduced perspective diversity, note missing roles |
| Phase 1: 3+ experts fail | Abort — insufficient diversity for meaningful council | Report "Council aborted — too few expert analyses" |
| Phase 2: 1-2 critiques fail | Continue synthesis with available critiques | Note missing cross-critiques in synthesis |
| Phase 2: All critiques fail | Skip to synthesis using Phase 1 only | Synthesis notes "No cross-critique performed" |
| Phase 3: Synthesizer fails | Read Phase 1 + Phase 2 files directly, present raw findings | No formatted synthesis, show available expert opinions |

Minimum viable council: 2 expert analyses + synthesizer.

---

### Phase 3: SYNTHESIS (Chairman)

Synthesizer reads ALL files via Read tool (NOT passed in prompt):

```yaml
Task:
  subagent_type: council-synthesizer
  run_in_background: true
  prompt: |
    PHASE: 3 (Synthesis)
    Read all analysis and critique files:
    - Phase 1: {SESSION_DIR}/phase1/analysis-architect.md, analysis-product.md, analysis-pragmatist.md, analysis-security.md
    - Phase 2: {SESSION_DIR}/phase2/critique-architect.md, critique-product.md, critique-pragmatist.md, critique-security.md

    Synthesize final decision.
    OUTPUT: Write synthesis to {SESSION_DIR}/synthesis.md
```

**⏳ FILE GATE:** Verify `{SESSION_DIR}/synthesis.md` exists.
**Orchestrator reads ONLY `synthesis.md`** for the final decision.

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

### When decision = needs_human

Council MUST notify user and halt execution:

1. Set spec status to `blocked`
2. Add `## ACTION REQUIRED` section to spec with:
   - Clear explanation of what Council needs from human
   - Specific questions or decisions required
3. Output to user: "COUNCIL BLOCKED — Human decision required. See ACTION REQUIRED section in spec."
4. Exit autopilot (do not continue to next task)

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
