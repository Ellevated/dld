# Feature: [TECH-153] AI-First Economic Model for DLD Framework

**Status:** done | **Priority:** P1 | **Date:** 2026-03-17

## Why

DLD agents (council, architect, spark, devil) make decisions using human-centric effort estimates ("refactoring takes 3 weeks", "team busy for a sprint"). This systematically distorts prioritization:

- **Refactoring always deprioritized** — "too expensive" when it costs $5-10
- **Testing cut "for economy"** — when it costs $1
- **Priority inflation by effort** — P2 assigned to high-value tasks because "effort is high"
- **False blocking** — "team busy for a week" when 5 parallel slots available

Reality: 1 autopilot task = $1, refactoring = $5-10, 5 parallel slots, founder's hour = $200. WSJF collapses to pure Cost of Delay when effort is constant (Reinertsen). RICE collapses to R×I×C.

## Context

**Research basis (4 scouts, 2026-03-17):**
- OpenAI Harness Engineering (Feb 2026): 0 manual code, 1M LOC, "humans steer, agents execute"
- "Zen of AI Coding" (Aviram, Mar 2026): "Code is cheap", "Refactoring easy", "Tech debt is shallow"
- Haque 2026: "New Software Cost Curve under Agentic AI" — academic analysis
- Codebase scout: **47 findings across 28 files** with human-centric metrics
- Council already has gold-standard LLM-native mindset blocks (council/SKILL.md:37-38)
- 6 agents missing LLM-native mindset blocks entirely

**Selected approach:** Impact + Risk (replace effort with Risk dimension R0/R1/R2)

---

## Scope

**In scope:**
- Replace human-time language (days/hours/weeks/sprints) with AI-cost language ($1/$5/$10) in all affected agents/skills
- Add Risk classification (R0/R1/R2) as second axis alongside Priority (P0/P1/P2)
- Add Impact×Risk routing matrix to Spark Phase 4
- Add LLM-native mindset blocks to 6 agents missing them
- Add AI-First Economic Model rule to CLAUDE.md (both root and template)
- Template changes: add compute-cost language ALONGSIDE human-time (backward compat)
- DLD-specific changes: REPLACE human-time with compute-cost

**Out of scope:**
- Changing P0/P1/P2 severity system (it's sound for triage — KEEP)
- WSJF-AI numerical formula (LLMs bad at consistent numeric scoring)
- Backlog restructuring (categorical sections work fine)
- Business metrics (CAC payback, revenue targets — legitimate business language)
- Project lifecycle stages ("Day 1", "Day 2" — sequencing, not sizing)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- All skills that make priority/effort decisions: spark, council, architect, board, audit, planner
- All agents that evaluate trade-offs: pragmatist, architect, security, product, devil, patterns, synthesizer

### Step 2: DOWN — what depends on?
- CLAUDE.md (all agents read this)
- Spec template (autopilot reads this)
- Backlog format (orchestrator reads this)

### Step 3: BY TERM — grep entire project
- "days", "hours", "weeks", "sprint" in agent prompts → 47 findings (see research-codebase.md)

### Step 4: CHECKLIST
- [x] `tests/**` — no test changes needed (prompt-only changes)
- [x] `ai/glossary/**` — N/A
- [x] `db/migrations/**` — N/A

### Verification
- [x] All found files added to Allowed Files
- [x] grep by old terms = 0 after implementation

---

## Allowed Files

**ONLY these files may be modified during implementation:**

### Root .claude/ (DLD-specific — REPLACE human-time)
1. `.claude/agents/architect/synthesizer.md` — replace "X days" effort template with $-cost (F-01, F-03)
2. `.claude/agents/architect/evolutionary.md` — remove "sprint" language, add LLM-native block (F-02, F-38)
3. `.claude/agents/architect/dx.md` — add LLM-native mindset block (F-39)
4. `.claude/agents/board/coo.md` — add LLM-native mindset block, add agent-capacity alongside barrels/ammunition (F-19, F-41)
5. `.claude/agents/board/cmo.md` — add LLM-native mindset block (F-42)
6. `.claude/agents/audit/synthesizer.md` — define S/M/L in compute terms (F-10)
7. `.claude/agents/spark/patterns.md` — replace "time estimate" with compute-cost + add LLM-native block (F-30, F-31, F-43)
8. `.claude/agents/spark/devil.md` — quantify ROI in $ not vague "effort" (F-32, F-33)
9. `.claude/agents/council/synthesizer.md` — standardize effort format to $ (F-11)
10. `.claude/skills/spark/feature-mode.md` — add Impact×Risk routing matrix to Phase 4 (F-24)
11. `.claude/skills/architect/retrofit-mode.md` — replace "small|medium|large" with compute-cost (F-09)
12. `.claude/skills/brandbook/completion.md` — replace "Day 1/2/3" with compute-cost phases (F-07)
13. `.claude/skills/architect/greenfield-mode.md` — "compute capacity" not "team Y" (F-21)
14. `.claude/skills/bootstrap/SKILL.md` — add compute budget alongside hours question (F-04, F-05, F-06)

### Root CLAUDE.md + rules
15. `CLAUDE.md` — add AI-First Economic Model section + Risk Classification Guide + P0/P1/P2 redefinition
16. `.claude/skills/spark/completion.md` — add Risk field to backlog entry format

### template/.claude/ (universal — ADD compute-cost ALONGSIDE human-time)
17. `template/.claude/agents/architect/synthesizer.md` — add compute-cost format alongside days
18. `template/.claude/agents/architect/evolutionary.md` — add LLM-native block
19. `template/.claude/agents/architect/dx.md` — add LLM-native block
20. `template/.claude/agents/board/coo.md` — add LLM-native block
21. `template/.claude/agents/board/cmo.md` — add LLM-native block
22. `template/.claude/agents/audit/synthesizer.md` — define S/M/L in compute terms
23. `template/.claude/agents/spark/patterns.md` — add compute-cost alongside time
24. `template/.claude/skills/spark/feature-mode.md` — add routing matrix
25. `template/.claude/skills/architect/retrofit-mode.md` — add compute-cost alongside T-shirt
26. `template/.claude/skills/brandbook/completion.md` — add compute-cost alongside days
27. `template/.claude/skills/architect/greenfield-mode.md` — add compute capacity
28. `template/.claude/skills/bootstrap/SKILL.md` — add compute budget field
29. `template/CLAUDE.md` — add AI-First Economic Model section (universal version)
30. `template/.claude/skills/spark/completion.md` — add Risk field to backlog format

**FORBIDDEN:** All other files. Files verified clean by codebase scout: autopilot, coder, review, reflect, qa, tester, documenter, scout, rules/architecture.md, rules/dependencies.md.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD framework (meta — skills/agents/rules)
**Cross-cutting:** All skills that make priority or trade-off decisions
**Data model:** No data model changes — prompt-only modifications

---

## Approaches

### Approach 1: Minimal — 1 paragraph in CLAUDE.md (Devil's recommendation)
**Source:** research-devil.md
**Summary:** Add "AI-First Effort Model" paragraph to CLAUDE.md, nothing else
**Pros:** Zero risk, 1 file, 5 minutes
**Cons:** Doesn't fix 47 instances of "X days" baked into agent prompts — CLAUDE.md rule won't override specific instructions

### Approach 2: Impact + Risk Framework (Selected)
**Source:** research-patterns.md, research-codebase.md, research-external.md
**Summary:** Replace effort with Risk (R0/R1/R2), add LLM-native blocks to 6 agents, fix all 47 human-centric instances, add routing matrix
**Pros:** Systematic, catches all instances, council already half-works this way, LLMs good at categorical R0/R1/R2
**Cons:** ~30 files, template backward compat (mitigated: add alongside, not replace in template)

### Approach 3: WSJF-AI numerical formula
**Source:** research-patterns.md Approach 3
**Summary:** Mathematical `WSJF-AI = CoD / Risk Score` with 1-5 scales
**Pros:** Mathematically rigorous
**Cons:** LLMs bad at consistent numeric scoring, agents will game scores, overhead

### Selected: 2
**Rationale:** Council already uses LLM-native cost language (gold standard exists). Approach 2 formalizes and propagates what already works. Risk categories (R0/R1/R2) are natural for LLM categorical judgment. Devil's mitigations incorporated: keep effort as $-cost metadata, template backward compat, priority inflation gate.

---

## Design

### New Concepts

**Risk Classification (R0/R1/R2):**
```
R0 = Irreversible: data loss, schema migration, security exposure, public API break
R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
```

**Impact×Risk Routing Matrix (Spark Phase 4):**

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| P0 | COUNCIL | HUMAN | AUTO |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN | AUTO | AUTO |

**AI-First P0/P1/P2 Definitions:**
```
P0 = Blocks revenue, users, or security RIGHT NOW (Cost of Delay: immediate)
P1 = High impact on product quality, including refactoring and testing (Cost of Delay: this week)
P2 = Nice-to-have, doesn't affect metrics this week (Cost of Delay: low)
```

**Key rule:** Implementation effort ($1-50) is NEVER a factor in priority assignment. Priority = pure Impact/Cost of Delay.

**Devil's Mitigations (incorporated):**
1. Keep effort field in spec but as "$1/$5/$10" not "days"
2. Template: ADD compute-cost alongside human-time (backward compat for human teams)
3. Max 5 P0 tasks in backlog simultaneously (priority inflation gate)
4. Refactoring/testing = P1 by default (never deprioritized)

### LLM-Native Mindset Block (standard for all agents making cost decisions)

Copy from council/architect.md (gold standard):
```markdown
## LLM-Native Mindset (CRITICAL!)

❌ "This refactoring would take a team 2-3 sprints"
✅ "Autopilot can refactor this in 2 hours with full test coverage"

Cost reference:
- Simple change (1-3 files): 15 min, ~$1
- Medium change (5-10 files): 1-2 hours, ~$5
- Large change (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50

NEVER deprioritize based on implementation effort.
Priority = Impact × Cost of Delay, not effort.
```

---

## UI Event Completeness

N/A — no UI elements.

---

## Drift Log

**Checked:** 2026-03-17 UTC
**Result:** no_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| All 30 Allowed Files | Verified present, unchanged | No action needed |

### References Updated
- No references needed updating — spec was written same day as plan.

---

## Implementation Plan

### Research Sources
- [OpenAI Harness Engineering](https://openai.com/index/harness-engineering/) — "humans steer, agents execute", tests/CI are the harness
- [Zen of AI Coding](https://nonstructured.com/zen-of-ai-coding/) — "Code is cheap", "Refactoring easy"
- [WSJF in SAFe](https://agility-at-scale.com/safe/lpm/wsjf-weighted-shortest-job-first/) — CoD/JobSize, constant JobSize = pure CoD
- Codebase scout: 47 findings in research-codebase.md
- Gold standard LLM-native block: `.claude/agents/council/architect.md:34-54`

### Task 1: Add AI-First Economic Model to CLAUDE.md

**Type:** prompt
**Files:**
  - modify: `CLAUDE.md:212` — insert new section BEFORE `## Key Rules` (after the `---` separator on line 212)
  - modify: `template/CLAUDE.md:275` — insert universal version at same location (before `## Key Rules` equivalent, after the `---` separator)

**Context:** CLAUDE.md is the top-level rules file read by ALL agents. Adding the AI-First Economic Model section here ensures every agent inherits the new cost framework. Root version is DLD-specific (AI-only language). Template version is universal (mentions both AI and human teams).

**Step 1: Add AI-First Economic Model section to root CLAUDE.md**

Insert the following block AFTER the `---` on line 212, BEFORE `## Key Rules` on line 214:

```markdown
## AI-First Economic Model

This project is maintained by AI agents. All cost/effort assessments MUST reflect compute reality, not human-team estimates.

### Cost Reference

| Change Size | Time | Cost | Example |
|-------------|------|------|---------|
| Simple (1-3 files) | 15 min | ~$1 | Fix typo, add field, update config |
| Medium (5-10 files) | 1-2 hours | ~$5 | New endpoint, refactor module |
| Large (20+ files) | 3-4 hours | ~$15 | Cross-domain change, new feature |
| Domain extraction | 1 day | ~$50 | Split monolith, new bounded context |

### Priority = Impact, NOT Effort

```
P0 = Blocks revenue, users, or security RIGHT NOW (Cost of Delay: immediate)
P1 = High impact on product quality, including refactoring and testing (Cost of Delay: this week)
P2 = Nice-to-have, doesn't affect metrics this week (Cost of Delay: low)
```

**Rule:** Implementation cost ($1-50) is NEVER a factor in priority. Priority = pure Impact / Cost of Delay.
**Rule:** Refactoring and testing = P1 by default. Never deprioritize because "effort is high" — effort is always low in AI-first.
**Rule:** Max 5 P0 tasks in backlog simultaneously (priority inflation gate).

### Risk Classification

```
R0 = Irreversible: data loss, schema migration, security exposure, public API break
R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
```

### Routing Matrix (Impact x Risk)

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| P0 | COUNCIL | HUMAN | AUTO |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN | AUTO | AUTO |

---

```

**Step 2: Add universal version to template/CLAUDE.md**

Insert the same section at the equivalent location in `template/CLAUDE.md` (BEFORE `## Key Rules`), but with the following differences:
- Replace "This project is maintained by AI agents." with "When AI agents maintain the codebase, cost/effort assessments MUST reflect compute reality. For human teams, use both compute-cost and traditional estimates."
- In the Cost Reference table, add a "Human Team" column: `| Simple (1-3 files) | 15 min | ~$1 | 1-2 hours | Fix typo, add field |`
- After "Priority = pure Impact / Cost of Delay" add: "(This applies regardless of whether agents or humans implement.)"

**Acceptance Criteria:**
- [ ] `grep "R0.*Irreversible" CLAUDE.md` returns a match
- [ ] `grep "R0.*Irreversible" template/CLAUDE.md` returns a match
- [ ] `grep "AI-First Economic Model" CLAUDE.md` returns a match
- [ ] Both files have the routing matrix table
- [ ] Root CLAUDE.md does NOT mention "human team" in the cost table
- [ ] Template CLAUDE.md DOES mention "human team" in the cost table

---

### Task 2: Add LLM-Native Mindset Blocks to 6 Missing Agents

**Type:** prompt
**Files:**
  - modify: `.claude/agents/architect/evolutionary.md:293-296` — replace "20% of each sprint" with compute-cost, add LLM-native block
  - modify: `.claude/agents/architect/dx.md:395` — add LLM-native block before `## Rules`
  - modify: `.claude/agents/architect/synthesizer.md:353-366` — replace Effort Estimate section
  - modify: `.claude/agents/board/coo.md:255` — add LLM-native block before `## Rules`
  - modify: `.claude/agents/board/cmo.md:250` — add LLM-native block before `## Rules`
  - modify: `.claude/agents/spark/patterns.md:28,81,107,133` — replace "time/effort" and "time estimate" with compute-cost, add LLM-native block
  - modify: `template/.claude/agents/architect/evolutionary.md` — same changes (template = add alongside, not replace)
  - modify: `template/.claude/agents/architect/dx.md` — same changes
  - modify: `template/.claude/agents/architect/synthesizer.md` — same changes (template = add alongside)
  - modify: `template/.claude/agents/board/coo.md` — same changes
  - modify: `template/.claude/agents/board/cmo.md` — same changes
  - modify: `template/.claude/agents/spark/patterns.md` — same changes (template = add alongside)

**Context:** 6 agents make cost/effort assessments but lack the LLM-native mindset block that council/architect.md already has (gold standard at lines 34-54). This task copies that block to all 6 agents and fixes human-time language.

**Gold standard block to copy (from `.claude/agents/council/architect.md:34-54`):**

```markdown
## LLM-Native Mindset (CRITICAL!)

You understand that this codebase is maintained by AI agents. Your cost/effort assessments MUST reflect this reality:

```
FORBIDDEN THINKING:
"This refactoring would take a team 2-3 sprints"
"We'd need to coordinate across multiple developers"
"The migration is too risky for the timeline"

CORRECT THINKING:
"Autopilot can refactor this in 2 hours with full test coverage"
"One Plan subagent + parallel Coder subagents handles this"
"LLM-driven migration: $5 compute, 30 minutes, zero coordination overhead"
```

Cost reference for your estimates:
- Simple refactoring (1-3 files): 15 min, ~$1
- Medium refactoring (5-10 files): 1-2 hours, ~$5
- Large refactoring (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50
```

**Step 1: Fix `.claude/agents/architect/evolutionary.md`**

1a. Replace line 294 `- 20% of each sprint allocated to debt` with:
```
- Continuous debt pay-down via LLM autopilot (~$5-15 per cycle)
```

1b. Insert the LLM-native mindset block AFTER line 19 (after `- You hate irreversible decisions — always ask "can we change our mind later?"`), before `## Your Thinking Style`:

```markdown

## LLM-Native Mindset (CRITICAL!)

You understand that this codebase is maintained by AI agents. Your cost/effort assessments MUST reflect this reality:

```
FORBIDDEN THINKING:
"This refactoring would take a team 2-3 sprints"
"We'd need to coordinate across multiple developers"
"The migration is too risky for the timeline"

CORRECT THINKING:
"Autopilot can refactor this in 2 hours with full test coverage"
"One Plan subagent + parallel Coder subagents handles this"
"LLM-driven migration: $5 compute, 30 minutes, zero coordination overhead"
```

Cost reference for your estimates:
- Simple refactoring (1-3 files): 15 min, ~$1
- Medium refactoring (5-10 files): 1-2 hours, ~$5
- Large refactoring (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50

```

**Step 2: Fix `.claude/agents/architect/dx.md`**

Insert the LLM-native mindset block AFTER line 19 (after `- You're pragmatic, not dogmatic — innovation is OK, but budgeted`), before `## Your Thinking Style`:

Same block as Step 1b above.

**Step 3: Fix `.claude/agents/architect/synthesizer.md`**

Replace the `## Effort Estimate` section (lines 353-366) inside the template code block:

OLD (lines 353-366):
```
## Effort Estimate

**Setup (one-time):**
- Infrastructure: [X days]
- Boilerplate: [Y days]
- Tooling: [Z days]

**Per-feature velocity:**
- Simple feature: [A days]
- Complex feature: [B days]

**Technical debt paydown:**
- Estimated: [C hours/week]
```

NEW:
```
## Compute Cost Estimate

**Setup (one-time):**
- Infrastructure: [~$X]
- Boilerplate: [~$Y]
- Tooling: [~$Z]

**Per-feature velocity:**
- Simple feature (1-3 files): ~$1, 15 min
- Medium feature (5-10 files): ~$5, 1-2 hours
- Complex feature (20+ files): ~$15, 3-4 hours

**Technical debt paydown:**
- Continuous via autopilot: ~$5-15 per cycle
```

**Step 4: Fix `.claude/agents/board/coo.md`**

Insert the LLM-native mindset block AFTER line 33 (after the closing ``` of "Your Thinking Style"), before `## Kill Question`:

```markdown

## LLM-Native Mindset (CRITICAL!)

You understand that this project uses AI agents for execution. Your capacity/effort assessments MUST reflect this reality:

```
FORBIDDEN THINKING:
"We need to hire 3 developers for this"
"This would take a team 2-3 sprints"
"We don't have enough people"

CORRECT THINKING:
"5 parallel autopilot slots can execute this in hours"
"Agent capacity: 2 Claude + 1 Codex concurrent, $1-50 per task"
"Barrels = humans who steer, Ammunition = agent compute slots"
```

Cost reference for your estimates:
- Simple task: 15 min, ~$1
- Medium task: 1-2 hours, ~$5
- Large task: 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50

```

**Step 5: Fix `.claude/agents/board/cmo.md`**

Insert the LLM-native mindset block AFTER line 34 (after the closing ``` of "Your Thinking Style"), before `## Kill Question`:

```markdown

## LLM-Native Mindset (CRITICAL!)

You understand that this project uses AI agents for execution. Your ROI and effort assessments MUST reflect compute costs, not human-team estimates:

```
FORBIDDEN THINKING:
"Content creation takes a team weeks"
"We need to hire a designer for this"
"Implementation cost makes this channel unviable"

CORRECT THINKING:
"Agent can generate and test content variations for ~$5"
"Brandbook agent creates full brand identity for ~$15"
"Implementation cost is negligible — focus on channel ROI"
```

Cost reference for your estimates:
- Simple task: 15 min, ~$1
- Medium task: 1-2 hours, ~$5
- Large task: 3-4 hours, ~$15

```

**Step 6: Fix `.claude/agents/spark/patterns.md`**

6a. Replace line 28 `4. **Complexity Estimate** — How hard to implement? (time/effort)` with:
```
4. **Compute Cost Estimate** — How much to implement? ($-cost, risk level)
```

6b. Replace all 3 occurrences (lines 81, 107, 133) of:
```
### Complexity
**Estimate:** {Easy/Medium/Hard} — {time estimate}
**Why:** {Rationale based on research}
```
with:
```
### Compute Cost
**Estimate:** ~${cost} ({risk_level}: R0/R1/R2)
**Why:** {Rationale based on research — files affected, blast radius}
```

6c. Insert the LLM-native mindset block AFTER line 19 (after `- You cite sources for each pattern`), before `## Your Role`:

Same core block adapted for patterns scout context:

```markdown

## LLM-Native Mindset (CRITICAL!)

You understand that this codebase is maintained by AI agents. Your complexity/effort comparisons MUST reflect compute costs, not human-team estimates:

```
FORBIDDEN THINKING:
"This approach would take a team 2 weeks"
"Too complex for the timeline"

CORRECT THINKING:
"Approach A: ~$5 compute, 1 hour. Approach B: ~$15 compute, 3 hours"
"Complexity affects risk level (R0/R1/R2), not priority"
```

Cost reference for your estimates:
- Simple (1-3 files): 15 min, ~$1
- Medium (5-10 files): 1-2 hours, ~$5
- Large (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50

```

**Step 7: Apply template versions**

For each of the 6 template files, apply the SAME changes as the root files, with one key difference:
- In the LLM-native mindset block, change the opening line from "You understand that this codebase is maintained by AI agents." to "When AI agents maintain the codebase, your cost/effort assessments should reflect compute reality. For human teams, include both compute-cost and traditional time estimates."
- For evolutionary.md template: change line 294 to `- 20% of each sprint allocated to debt (or continuous via LLM autopilot: ~$5-15 per cycle)` (ADD alongside, not replace)
- For synthesizer.md template: keep both formats in the Effort Estimate section (add compute-cost as alternative, keep "[X days]" with additional "[~$X]"):

```
## Effort Estimate

**Setup (one-time):**
- Infrastructure: [X days] / [~$X compute]
- Boilerplate: [Y days] / [~$Y compute]
- Tooling: [Z days] / [~$Z compute]

**Per-feature velocity (AI agents):**
- Simple feature (1-3 files): ~$1, 15 min
- Medium feature (5-10 files): ~$5, 1-2 hours
- Complex feature (20+ files): ~$15, 3-4 hours

**Per-feature velocity (human team):**
- Simple feature: [A days]
- Complex feature: [B days]

**Technical debt paydown:**
- Human team: [C hours/week]
- AI agents: ~$5-15 per autopilot cycle
```

- For patterns.md template: keep both formats for complexity:
```
### Compute Cost
**Estimate:** ~${cost} ({risk_level}: R0/R1/R2) / {Easy/Medium/Hard} for human teams
**Why:** {Rationale based on research — files affected, blast radius}
```

**Acceptance Criteria:**
- [ ] `grep -l "LLM-Native Mindset" .claude/agents/architect/evolutionary.md .claude/agents/architect/dx.md .claude/agents/architect/synthesizer.md .claude/agents/board/coo.md .claude/agents/board/cmo.md .claude/agents/spark/patterns.md` returns all 6 files
- [ ] `grep "20% of each sprint" .claude/agents/architect/evolutionary.md` returns 0 results
- [ ] `grep "X days" .claude/agents/architect/synthesizer.md` returns 0 results (the template section now says "$X")
- [ ] `grep "time estimate" .claude/agents/spark/patterns.md` returns 0 results
- [ ] `grep "time/effort" .claude/agents/spark/patterns.md` returns 0 results
- [ ] Template files have "LLM-Native Mindset" block AND keep human-time references
- [ ] `grep "20% of each sprint" template/.claude/agents/architect/evolutionary.md` still returns a match (backward compat)

---

### Task 3: Fix Effort Language in Skills + Add Routing Matrix

**Type:** prompt
**Files:**
  - modify: `.claude/skills/spark/feature-mode.md:265-291` — add Impact x Risk routing matrix to Phase 4
  - modify: `.claude/skills/spark/completion.md:91-93` — add Risk field to backlog entry format
  - modify: `.claude/skills/architect/retrofit-mode.md:285` — replace "small | medium | large" with compute-cost
  - modify: `.claude/skills/architect/greenfield-mode.md:40` — "compute capacity" not "team Y"
  - modify: `.claude/skills/brandbook/completion.md:50-80` — add compute-cost alongside Day 1/2/3
  - modify: `.claude/skills/bootstrap/SKILL.md:137,301` — add compute budget alongside hours
  - modify: `.claude/agents/spark/devil.md:28,207` — quantify ROI in $
  - modify: `.claude/agents/council/synthesizer.md:184,190` — standardize effort to $-cost format
  - modify: `.claude/agents/audit/synthesizer.md:176` — define S/M/L in compute terms
  - modify: `template/.claude/skills/spark/feature-mode.md` — same (add routing matrix)
  - modify: `template/.claude/skills/spark/completion.md` — same (add Risk field)
  - modify: `template/.claude/skills/architect/retrofit-mode.md` — add alongside
  - modify: `template/.claude/skills/architect/greenfield-mode.md` — add alongside
  - modify: `template/.claude/skills/brandbook/completion.md` — add alongside
  - modify: `template/.claude/skills/bootstrap/SKILL.md` — add alongside
  - modify: `template/.claude/agents/spark/devil.md` — add alongside
  - modify: `template/.claude/agents/council/synthesizer.md` — add alongside
  - modify: `template/.claude/agents/audit/synthesizer.md` — add alongside

**Context:** This task fixes effort language in skills that control how specs are written, how decisions are routed, and how audits report complexity. The routing matrix in Phase 4 is the centerpiece change — it formalizes Impact x Risk routing that currently uses informal criteria.

**Step 1: Add routing matrix to `.claude/skills/spark/feature-mode.md`**

Replace lines 265-291 (Phase 4: DECIDE section, from `## Phase 4: DECIDE` through `→ Architect updates blueprint → retry from Phase 3`):

OLD:
```markdown
## Phase 4: DECIDE

Route based on feature scope, clarity, and risk:

### AUTO (you decide)
- Feature is within blueprint constraints
- Scope is clear from dialogue
- No controversial trade-offs
- Devil scout's verdict is "Proceed"
→ Select best approach, move to Phase 5

### HUMAN (ask user)
- Multiple approaches with no clear winner
- Scope unclear after dialogue
- Devil scout suggests simpler alternative
→ Present 2-3 approaches, user chooses

### COUNCIL (escalate)
- Controversial (Devil scout says "Proceed with caution")
- Cross-domain impact (affects 3+ domains)
- Major architectural decision
→ `/council` (5 experts + cross-critique)

### ARCHITECT (escalate)
- Blueprint gap (domain missing, rule missing)
- Blueprint contradiction (research conflicts with blueprint)
→ Architect updates blueprint → retry from Phase 3
```

NEW:
```markdown
## Phase 4: DECIDE

### Impact x Risk Routing Matrix

Assign Priority (P0/P1/P2) and Risk (R0/R1/R2) from research, then route:

```
Risk Classification:
R0 = Irreversible: data loss, schema migration, security exposure, public API break
R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
```

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---|---|---|---|
| P0 | COUNCIL | HUMAN | AUTO |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN | AUTO | AUTO |

### AUTO (you decide)
- Matrix says AUTO
- Feature is within blueprint constraints
- Devil scout's verdict is "Proceed"
→ Select best approach, move to Phase 5

### HUMAN (ask user)
- Matrix says HUMAN
- Multiple approaches with no clear winner
- Scope unclear after dialogue
→ Present 2-3 approaches, user chooses

### COUNCIL (escalate)
- Matrix says COUNCIL
- Cross-domain impact (affects 3+ domains)
- Major architectural decision
→ `/council` (5 experts + cross-critique)

### ARCHITECT (escalate)
- Blueprint gap (domain missing, rule missing)
- Blueprint contradiction (research conflicts with blueprint)
→ Architect updates blueprint → retry from Phase 3
```

**Step 2: Add Risk field to `.claude/skills/spark/completion.md`**

Replace the backlog entry format (lines 91-93):

OLD:
```
| ID | Task | Status | Priority | Feature.md |
|----|------|--------|----------|------------|
| FTR-XXX | Task name | queued | P1 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

NEW:
```
| ID | Task | Status | Priority | Risk | Feature.md |
|----|------|--------|----------|------|------------|
| FTR-XXX | Task name | queued | P1 | R2 | [FTR-XXX](features/FTR-XXX-YYYY-MM-DD-name.md) |
```

**Step 3: Fix `.claude/skills/architect/retrofit-mode.md`**

Replace line 285 `**Effort estimate:** small | medium | large` with:
```
**Compute cost:** ~$1 (1-3 files) | ~$5 (5-10 files) | ~$15 (20+ files)
**Risk:** R0 | R1 | R2
```

**Step 4: Fix `.claude/skills/architect/greenfield-mode.md`**

Replace line 40 `- Constraints from Board ("budget X, team Y, deadline Z")` with:
```
- Constraints from Board ("budget X, compute capacity Y agents, deadline Z")
```

**Step 5: Fix `.claude/skills/brandbook/completion.md`**

Add compute-cost annotations to the Day 1/2/3 headers (lines 50, 59, 66). Change:
- `## Day 1: Foundation (2-3 hours)` to `## Day 1: Foundation (~$3-5 compute or 2-3 hours manual)`
- `## Day 2: Visual Core (3-4 hours)` to `## Day 2: Visual Core (~$5-10 compute or 3-4 hours manual)`
- `## Day 3: Store & Marketing (2-3 hours)` to `## Day 3: Store & Marketing (~$3-5 compute or 2-3 hours manual)`

Note: "Day 1/2/3" are SEQUENCING markers (in-scope for out-of-scope list: "Project lifecycle stages"), the hours are the effort part we are adding compute-cost to.

**Step 6: Fix `.claude/skills/bootstrap/SKILL.md`**

6a. Replace line 137 `- **Constraints:** "How many hours per week? What's the budget?"` with:
```
- **Constraints:** "How many hours per week? What's the compute budget? What's the total budget?"
```

6b. Replace line 301 `- Time: {hours per week}` with:
```
- Time: {hours per week}
- Compute budget: {$ per month for AI agents, if applicable}
```

**Step 7: Fix `.claude/agents/spark/devil.md`**

7a. Replace line 28 `4. **Complexity Estimate** — How hard to implement? (time/effort)` — WAIT: devil.md does NOT have this line. Checking actual content... Devil.md line 28 is `4. **What Breaks** — Side effects, dependencies at risk`. No change needed here.

Instead, add a cost-awareness note. After line 5 (the `effort: high` frontmatter), no change needed to frontmatter. Instead, add to the output template (after line 100, inside the `### Alternative 2` template block). Actually, the devil.md file already uses abstract terms (High/Medium/Low) not human-time estimates. The key finding F-32/F-33 refers to the example output section.

Replace the example line 207:
```
**Verdict:** Alternative 1 (soft warning) might solve 80% of need with 5% of effort. Validate with user first.
```
with:
```
**Verdict:** Alternative 1 (soft warning) might solve 80% of need with ~$1 compute (~5% of full implementation cost). Validate with user first.
```

**Step 8: Fix `.claude/agents/council/synthesizer.md`**

The council synthesizer already uses "$-cost" format in its example (lines 254-270: "10 minutes, ~$1", "30 minutes, ~$2", etc.). The template fields at lines 184 and 190 say `effort: "LLM estimate"` which is correct (it prompts for LLM-native estimates).

No changes needed to the YAML template — the existing `effort: "LLM estimate"` format naturally produces $-cost output as shown in the example. Verified: the example at lines 220-293 already uses correct format.

However, to make the intent explicit, add a comment after line 183 (inside the YAML template). Replace:
```yaml
    effort: "LLM estimate"

recommended_changes:
```
with:
```yaml
    effort: "$-cost estimate (e.g., '15 min, ~$1')"

recommended_changes:
```

And replace line 190:
```yaml
    effort: "LLM estimate"
```
with:
```yaml
    effort: "$-cost estimate (e.g., '1 hour, ~$5')"
```

And replace line 207:
```yaml
total_effort_estimate: "Combined LLM estimate for all changes"
```
with:
```yaml
total_effort_estimate: "Combined $-cost estimate for all changes (e.g., '2 hours, ~$10')"
```

**Step 9: Fix `.claude/agents/audit/synthesizer.md`**

Replace line 176 `| 1 | {item} | {category} | {persona(s)} | {file:line} | small/medium/large |` with:
```
| 1 | {item} | {category} | {persona(s)} | {file:line} | ~$1 / ~$5 / ~$15 |
```

**Step 10: Apply template versions**

For each template file, apply the same changes as root, with backward-compat differences:

- **template/.claude/skills/spark/feature-mode.md:** Same routing matrix addition as Step 1.
- **template/.claude/skills/spark/completion.md:** Same Risk column addition as Step 2.
- **template/.claude/skills/architect/retrofit-mode.md:** Change line to `**Effort estimate:** small (~$1) | medium (~$5) | large (~$15)` and add `**Risk:** R0 | R1 | R2` (keep original T-shirt sizes, add $-cost in parentheses).
- **template/.claude/skills/architect/greenfield-mode.md:** Same change as Step 4.
- **template/.claude/skills/brandbook/completion.md:** Same change as Step 5 (keep both formats).
- **template/.claude/skills/bootstrap/SKILL.md:** Same change as Step 6.
- **template/.claude/agents/spark/devil.md:** Same change as Step 7.
- **template/.claude/agents/council/synthesizer.md:** Same change as Step 8.
- **template/.claude/agents/audit/synthesizer.md:** Change to `| 1 | {item} | {category} | {persona(s)} | {file:line} | small (~$1) / medium (~$5) / large (~$15) |` (keep T-shirt sizes, add $-cost).

**Acceptance Criteria:**
- [ ] `grep "Impact.*Risk" .claude/skills/spark/feature-mode.md` returns a match (routing matrix present)
- [ ] `grep "Risk" .claude/skills/spark/completion.md` returns a match (Risk column in backlog format)
- [ ] `grep "small | medium | large" .claude/skills/architect/retrofit-mode.md` returns 0 results (replaced with $-cost)
- [ ] `grep "team Y" .claude/skills/architect/greenfield-mode.md` returns 0 results
- [ ] `grep "compute" .claude/skills/brandbook/completion.md` returns matches
- [ ] `grep "compute budget" .claude/skills/bootstrap/SKILL.md` returns a match
- [ ] `grep "\\$-cost estimate" .claude/agents/council/synthesizer.md` returns matches
- [ ] `grep "~\\$1.*~\\$5.*~\\$15" .claude/agents/audit/synthesizer.md` returns a match
- [ ] Template files preserve original language alongside new compute-cost language

### Execution Order

```
Task 1 (CLAUDE.md) → Task 2 (6 agents) → Task 3 (skills + remaining agents)
```

Task 1 must go first because it establishes the canonical definitions (R0/R1/R2, routing matrix, cost reference) that Tasks 2 and 3 reference.

Tasks 2 and 3 could theoretically run in parallel since they touch different files, but sequential is safer for review.

### Dependencies

- Task 2 depends on Task 1 (agents reference CLAUDE.md definitions)
- Task 3 depends on Task 1 (skills reference CLAUDE.md routing matrix)
- Task 2 and Task 3 are independent of each other (different file sets)

---

## Flow Coverage Matrix (REQUIRED)

| # | Change | Covered by Task | Status |
|---|--------|-----------------|--------|
| 1 | CLAUDE.md AI-First Economic Model | Task 1 | new |
| 2 | template/CLAUDE.md universal version | Task 1 | new |
| 3 | 6 agents get LLM-native mindset blocks | Task 2 | new |
| 4 | "X days"/"sprints" removed from agents | Task 2 | new |
| 5 | Impact×Risk routing matrix in Phase 4 | Task 3 | new |
| 6 | Risk field in backlog format | Task 3 | new |
| 7 | T-shirt sizing defined in compute terms | Task 3 | new |
| 8 | Bootstrap adds compute budget field | Task 3 | new |
| 9 | Devil quantifies ROI in $ | Task 3 | new |

**GAPS:** None. All 47 findings from codebase scout mapped to tasks.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | No human-time estimates in .claude/ agents | `grep -rn "X days\|hours/week\|person-day" .claude/agents/` | 0 results (excluding FORBIDDEN blocks) | deterministic | codebase scout | P0 |
| EC-2 | No "sprint" language in agents | `grep -rn "sprint" .claude/agents/` | 0 results (excluding FORBIDDEN blocks) | deterministic | codebase scout | P0 |
| EC-3 | All 6 target agents have LLM-native block | `grep -l "LLM-Native Mindset" .claude/agents/architect/evolutionary.md .claude/agents/architect/dx.md .claude/agents/architect/synthesizer.md .claude/agents/board/coo.md .claude/agents/board/cmo.md .claude/agents/spark/patterns.md` | 6 files found | deterministic | codebase scout | P0 |
| EC-4 | Risk classification in CLAUDE.md | `grep "R0.*Irreversible" CLAUDE.md` | Found | deterministic | patterns scout | P0 |
| EC-5 | Routing matrix in spark feature-mode | `grep "Impact.*Risk" .claude/skills/spark/feature-mode.md` | Found | deterministic | patterns scout | P1 |
| EC-6 | Risk field in backlog format | `grep "Risk" .claude/skills/spark/completion.md` | Found | deterministic | patterns scout | P1 |
| EC-7 | Template has compute-cost alongside (not replacing) human-time | `grep -c "compute\|\\$" template/.claude/agents/architect/synthesizer.md` | ≥1 match | deterministic | devil scout | P1 |
| EC-8 | Patterns agent uses compute-cost not "time estimate" | `grep "time estimate" .claude/agents/spark/patterns.md` | 0 results | deterministic | codebase scout | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 | LLM-Judge: 0 | Total: 8

### TDD Order
1. EC-1, EC-2 (grep for old patterns → should find them before fix)
2. EC-3 (check missing blocks → add them)
3. EC-4, EC-5, EC-6 (check new artifacts → add them)
4. EC-7, EC-8 (verify template strategy)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Grep finds no human-time patterns | `grep -rn "X days\]\|hours/week\|person-day\|20% of each sprint" .claude/agents/ --include="*.md" \| grep -v FORBIDDEN \| grep -v "❌"` | exit 0, empty output | 10s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | All 6 agents have LLM-native block | None | `for f in .claude/agents/architect/{evolutionary,dx,synthesizer}.md .claude/agents/board/{coo,cmo}.md .claude/agents/spark/patterns.md; do grep -q "LLM-Native Mindset" "$f" && echo "OK: $f" || echo "MISSING: $f"; done` | All 6 show "OK" |
| AV-F2 | CLAUDE.md has Risk Classification | None | `grep -c "R0.*R1.*R2\|Risk Classification" CLAUDE.md` | ≥1 |
| AV-F3 | Routing matrix in Phase 4 | None | `grep -A5 "Impact.*Risk" .claude/skills/spark/feature-mode.md` | Shows P0/P1/P2 × R0/R1/R2 matrix |

### Verify Command (copy-paste ready)

```bash
# Smoke: no human-time patterns
echo "=== AV-S1: Human-time patterns ===" && grep -rn "X days\]\|hours/week\|person-day\|20% of each sprint" .claude/agents/ --include="*.md" | grep -v FORBIDDEN | grep -v "❌" | head -5 && echo "FAIL: found human-time patterns" || echo "PASS"

# Functional: LLM-native blocks
echo "=== AV-F1: LLM-native blocks ===" && for f in .claude/agents/architect/{evolutionary,dx,synthesizer}.md .claude/agents/board/{coo,cmo}.md .claude/agents/spark/patterns.md; do grep -q "LLM-Native Mindset" "$f" && echo "OK: $f" || echo "MISSING: $f"; done

# Functional: Risk Classification
echo "=== AV-F2: Risk Classification ===" && grep -c "R0" CLAUDE.md && echo "PASS" || echo "FAIL"

# Functional: Routing matrix
echo "=== AV-F3: Routing matrix ===" && grep -c "Impact.*Risk" .claude/skills/spark/feature-mode.md && echo "PASS" || echo "FAIL"
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [x] AI-First Economic Model added to CLAUDE.md (root + template)
- [x] Risk Classification (R0/R1/R2) defined
- [x] Impact×Risk routing matrix in Spark Phase 4
- [x] 6 agents have LLM-native mindset blocks
- [x] All human-time language replaced in .claude/ agents
- [x] Template has compute-cost alongside human-time (backward compat)
- [x] All tasks from Implementation Plan completed

### Tests
- [x] All eval criteria (EC-1 through EC-8) pass
- [x] Coverage not decreased

### Acceptance Verification
- [x] AV-S1 passes (no human-time patterns)
- [x] AV-F1 passes (all 6 agents have blocks)
- [x] AV-F2 passes (Risk Classification in CLAUDE.md)
- [x] AV-F3 passes (routing matrix present)

### Technical
- [x] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
