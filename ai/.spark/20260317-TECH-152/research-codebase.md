# Codebase Research: Human-Centric Effort Estimation in DLD Framework

**Scout:** Codebase Scout
**Date:** 2026-03-17
**Scope:** ALL skills, agents, rules, templates — exhaustive search

---

## Summary

Found **47 distinct findings** across **28 files**. The framework already has partial LLM-native mindset (council/SKILL.md lines 37-38 is the gold standard), but it's inconsistent — many files still use human-era estimation patterns (days, sprints, team-based language). Priority system (P0-P3) is sound for severity triage and should be KEPT, but effort estimation and cost framing need systematic replacement.

---

## Category 1: Effort Estimates in Human Time Units (days/hours/weeks)

### F-01: Architect Synthesizer — "X days" effort template
**File:** `.claude/agents/architect/synthesizer.md` lines 353-365
**Also:** `template/.claude/agents/architect/synthesizer.md` (same lines)
```markdown
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
**Problem:** Uses human-era "days" for setup/features and "hours/week" for debt. An agent pipeline measures in compute-$ and wall-clock minutes, not person-days.
**Fix:** Replace with `$X compute / ~N minutes wall-clock` format consistent with council's LLM-native mindset.

### F-02: Architect Evolutionary — "20% of each sprint"
**File:** `.claude/agents/architect/evolutionary.md` line 294
**Also:** `template/.claude/agents/architect/evolutionary.md`
```markdown
- 20% of each sprint allocated to debt
```
**Problem:** "Sprint" is a human Scrum artifact. Agent pipelines don't have sprints.
**Fix:** Replace with compute-budget or per-cycle allocation language.

### F-03: Architect Synthesizer — "Per-feature velocity"
**File:** `.claude/agents/architect/synthesizer.md` line 360
```markdown
**Per-feature velocity:**
- Simple feature: [A days]
- Complex feature: [B days]
```
**Problem:** "Velocity" in days is human-Scrum language.
**Fix:** Replace with `compute cost per feature` + `wall-clock estimate`.

### F-04: Bootstrap SKILL — "How many hours per week?"
**File:** `.claude/skills/bootstrap/SKILL.md` line 137
**Also:** `template/.claude/skills/bootstrap/SKILL.md` line 143
```markdown
- **Constraints:** "How many hours per week? What's the budget?"
```
**Problem:** Asks founder about human time commitment. This is a LEGITIMATE business question (founder's personal time), but should be framed alongside compute capacity.
**Fix:** Keep the hours question (it's about founder's availability) but ADD "What's your compute/API budget?" alongside it.

### F-05: Bootstrap SKILL — "Time: {hours per week}"
**File:** `.claude/skills/bootstrap/SKILL.md` line 301
**Also:** `template/.claude/skills/bootstrap/SKILL.md` line 308
```markdown
- Time: {hours per week}
```
**Problem:** Template captures only human time. Should also capture compute budget.
**Fix:** Add `- Compute budget: {$/month}` field.

### F-06: Bootstrap SKILL — "In 2 weeks" + "ML recommendations"
**File:** `.claude/skills/bootstrap/SKILL.md` line 74
**Also:** `template/.claude/skills/bootstrap/SKILL.md`
```markdown
| MLP vs Resources | "In 2 weeks" + "ML recommendations" | "ML in 2 weeks? What's realistic?" |
```
**Problem:** Uses human-timeline framing for feasibility challenge. Should challenge based on compute cost + technical complexity, not calendar time.
**Fix:** Reframe as compute-cost challenge: "ML requires training data + compute. What's realistic given your data and API budget?"

### F-07: Brandbook completion — "Day 1/2/3" timeline
**File:** `.claude/skills/brandbook/completion.md` lines 50-74
**Also:** `template/.claude/skills/brandbook/completion.md`
```markdown
## Day 1: Foundation (2-3 hours)
## Day 2: Visual Core (3-4 hours)
## Day 3: Store & Marketing (2-3 hours)
## Week 2: Polish (optional)
```
**Problem:** Uses human work-day timeline with hour estimates. For an AI-generated brandbook, this should be compute-cost based.
**Fix:** Reframe as phases with compute cost, not human days.

### F-08: Board CFO — "12 months" CAC payback
**File:** `.claude/agents/board/cfo.md` lines 37, 40, 65
```markdown
"CAC payback < 12 months? If not — business doesn't live"
```
**Problem:** This is LEGITIMATE business language. CAC payback in months is standard unit economics — NOT human effort estimation. **KEEP AS-IS.**

### F-09: Architect retrofit mode — "Effort estimate: small | medium | large"
**File:** `.claude/skills/architect/retrofit-mode.md` line 285
**Also:** `template/.claude/skills/architect/retrofit-mode.md`
```markdown
**Effort estimate:** small | medium | large
```
**Problem:** T-shirt sizing is human-centric and vague. For agents, should be compute-cost range.
**Fix:** Replace with `**Compute cost:** ~$X-Y / ~N tasks` or keep S/M/L but define in agent terms.

### F-10: Audit synthesizer — "small/medium/large" effort column
**File:** `.claude/agents/audit/synthesizer.md` line 176
**Also:** `template/.claude/agents/audit/synthesizer.md`
```markdown
| 1 | {item} | {category} | {persona(s)} | {file:line} | small/medium/large |
```
**Problem:** Same T-shirt sizing without agent-cost grounding.
**Fix:** Define what S/M/L means in compute terms, or replace column.

### F-11: Council synthesizer — "total_effort_estimate" in hours/$
**File:** `.claude/agents/council/synthesizer.md` lines 207, 293
**Also:** `template/.claude/agents/council/synthesizer.md`
```markdown
total_effort_estimate: "Combined LLM estimate for all changes"
...
total_effort_estimate: "2 hours, ~$10 (including optional simplification)"
```
**Problem:** The template (line 207) is fine — says "LLM estimate". The example (line 293) is GOOD — uses "hours + $" which is already LLM-native. **KEEP but standardize format.**

### F-12: Board retrofit mode — "migration costs... effort, dependencies"
**File:** `.claude/skills/board/retrofit-mode.md` line 59
```markdown
- What the migration costs and risks are (from migration path — effort, dependencies)
```
**Problem:** "Effort" without qualifier defaults to human-mental-model.
**Fix:** Change to "compute cost and risk" or "agent-effort and dependencies".

---

## Category 2: LLM-Native Mindset Blocks (ALREADY GOOD — Reference Standard)

### F-13: Council SKILL — Gold standard LLM-native framing
**File:** `.claude/skills/council/SKILL.md` lines 37-38
```markdown
❌ "Refactoring will take a month of team work"
✅ "Refactoring = 1 hour LLM work, ~$5 compute"
```
**Status:** KEEP. This is the reference pattern all other files should follow.

### F-14: Council Architect agent — LLM-native cost reference
**File:** `.claude/agents/council/architect.md` lines 39-54
```markdown
❌ "This refactoring would take a team 2-3 sprints"
✅ "Autopilot can refactor this in 2 hours with full test coverage"

Cost reference:
- Simple refactoring (1-3 files): 15 min, ~$1
- Medium refactoring (5-10 files): 1-2 hours, ~$5
- Large refactoring (20+ files): 3-4 hours, ~$15
- Full domain extraction: 1 day, ~$50
```
**Status:** KEEP. This is the model other agents should copy.

### F-15: Council Pragmatist agent — LLM-native cost reference
**File:** `.claude/agents/council/pragmatist.md` lines 51-55
```markdown
- Simple fix in simple code: 5 min, ~$0.50
- Simple fix in complex code: 30 min, ~$3 (LLM gets confused)
- Adding feature to simple code: 15 min, ~$1.50
- Adding feature to over-engineered code: 1 hour, ~$6
```
**Status:** KEEP. Good LLM-native framing.

### F-16: Council Security agent — LLM-native cost reference
**File:** `.claude/agents/council/security.md` lines 50-55
```markdown
- Input validation (per endpoint): 5 min, ~$0.50
- Auth check addition: 10 min, ~$1
- SQL injection fix: 15 min, ~$1.50
- Full OWASP top-10 scan: 30 min, ~$5
- Rate limiting implementation: 1 hour, ~$4
```
**Status:** KEEP. Good LLM-native framing.

---

## Category 3: Human-Team Language in Agent Prompts

### F-17: Council Architect — "team 2-3 sprints" (in FORBIDDEN block)
**File:** `.claude/agents/council/architect.md` line 40
```markdown
"This refactoring would take a team 2-3 sprints"
```
**Status:** This is already in the FORBIDDEN block. **KEEP — it's the anti-pattern example.**

### F-18: Council Security — "dedicated security sprint" (in FORBIDDEN block)
**File:** `.claude/agents/council/security.md` line 41
```markdown
"This requires a dedicated security sprint"
```
**Status:** Already FORBIDDEN. **KEEP as anti-pattern example.**

### F-19: Board COO — "barrels vs ammunition" human team framing
**File:** `.claude/agents/board/coo.md` lines 30, 40, 66
```markdown
"Barrel or ammunition? (can they own end-to-end or just execute?)"
"Talent bottleneck: barrels vs ammunition"
```
**Problem:** "Barrels vs ammunition" is Rabois's framework for HUMAN team topology. For an AI-first company, the equivalent is "orchestrator vs subagent" or "pipeline capacity vs compute budget".
**Fix:** Add LLM-native reframe alongside human-team version (COO still needs to reason about the human-agent mix).

### F-20: Board COO — "hiring" and "team" language
**File:** `.claude/agents/board/coo.md` lines 40, 49
```markdown
"If you can't separate agent work from human work, you'll hire for the wrong roles."
"Organizational design: functional, product-based, matrix?"
```
**Problem:** This is LEGITIMATE for Board-level business strategy. **KEEP but ensure agent-capacity reasoning is primary, human hiring is secondary.**

### F-21: Architect greenfield — "budget X, team Y, deadline Z"
**File:** `.claude/skills/architect/greenfield-mode.md` line 40
**Also:** `template/.claude/skills/architect/greenfield-mode.md`
```markdown
- Constraints from Board ("budget X, team Y, deadline Z")
```
**Problem:** "Team Y" implies human team size as constraint. For agent-first, constraint should be "compute budget, pipeline parallelism, API rate limits".
**Fix:** Change to "budget X, compute capacity Y, deadline Z".

### F-22: Architect facilitator — "Budget constraints"
**File:** `.claude/agents/architect/facilitator.md` line 106
```markdown
- Budget constraints: [Infra cost limits]
```
**Status:** This is about infrastructure cost — LEGITIMATE. **KEEP.**

---

## Category 4: Spark Decision Logic (AUTO/HUMAN/COUNCIL Routing)

### F-23: Spark feature-mode — Priority question "P0/P1/P2?"
**File:** `.claude/skills/spark/feature-mode.md` line 121
**Also:** `.claude/agents/spark/facilitator.md` line 48
**Also:** `template/.claude/skills/spark/feature-mode.md` line 121
```markdown
8. **Priority:** "How urgent is this? P0/P1/P2?"
```
**Problem:** P0/P1/P2 as urgency tiers is standard severity classification. However, asking HUMANS to assign priority assumes human judgment is needed for routing. In AI-first model, priority should derive from business impact + compute cost, not human "urgency feeling".
**Fix:** Reframe as "What's the business impact if this isn't done?" → auto-derive priority from impact analysis.

### F-24: Spark feature-mode — AUTO/HUMAN/COUNCIL routing criteria
**File:** `.claude/skills/spark/feature-mode.md` lines 269-291
```markdown
### AUTO (you decide)
- Feature is within blueprint constraints
- No controversial trade-offs
- Devil scout's verdict is "Proceed"

### HUMAN (ask user)
- Multiple approaches with no clear winner
- Scope unclear after dialogue

### COUNCIL (escalate)
- Controversial
- Cross-domain impact (affects 3+ domains)
```
**Problem:** Routing criteria don't consider compute cost as a factor. A feature that costs $500 in compute should route differently than one that costs $5.
**Fix:** Add compute-cost thresholds to routing: e.g., >$50 estimated compute → HUMAN confirmation required.

### F-25: Spark feature-mode — "Kill Question" with time framing
**File:** `.claude/skills/spark/feature-mode.md` line 124
```markdown
11. **Kill Question:** "If we do nothing — what happens in 3 months?"
```
**Problem:** "3 months" is fine as business impact horizon. **KEEP — this is business reasoning, not effort estimation.**

---

## Category 5: Priority System (P0-P3)

### F-26: Audit SKILL — P0/P1 definitions
**File:** `.claude/skills/audit/SKILL.md` lines 276-282
**Also:** `template/.claude/skills/audit/SKILL.md`
```markdown
### P0 (Immediate)
...
### P1 (Soon)
```
**Problem:** P0/P1 as severity/urgency tiers is standard and NOT human-centric. However, "Soon" is vague.
**Fix:** Define P0/P1 in terms of business impact, not human urgency feeling. E.g., P0 = "blocks revenue or security breach", P1 = "degrades UX or blocks next feature".

### F-27: Devil agent — P0/P1/P2 severity ratings
**File:** `.claude/agents/spark/devil.md` lines 110-112
```markdown
| DA-1 | {edge case} | {concrete input} | {expected} | High | P0 | deterministic |
| DA-2 | {edge case} | {concrete input} | {expected} | Med | P1 | deterministic |
| DA-3 | {edge case} | {concrete input} | {expected} | Low | P2 | deterministic |
```
**Problem:** The High/Med/Low + P0/P1/P2 mapping is SOUND for test severity. **KEEP — this is about test importance, not effort.**

### F-28: Backlog — Priority column in INTERNAL section
**File:** `ai/backlog.md` line 40
```markdown
| ID | Задача | Status | Priority | Feature.md |
```
**Problem:** Priority column exists but uses P0-P3 scale. This is standard and should be KEPT, but consider adding a `Cost` column for compute estimates.

### F-29: Backlog — Impact stars in LAUNCH/GROWTH sections
**File:** `ai/backlog.md` lines 15-34
```markdown
| TECH-063 | Publish create-dld to NPM | done | ⭐⭐⭐⭐⭐ |
```
**Problem:** Star-based impact rating is fine but doesn't capture compute cost. **Low priority fix — backlog format is user-facing.**

---

## Category 6: Patterns Scout — "Complexity Estimate" in Human Terms

### F-30: Patterns agent — "Complexity Estimate: Easy/Medium/Hard — time estimate"
**File:** `.claude/agents/spark/patterns.md` lines 28, 81, 107, 133
**Also:** `template/.claude/agents/spark/patterns.md`
```markdown
4. **Complexity Estimate** — How hard to implement? (time/effort)
...
**Estimate:** {Easy/Medium/Hard} — {time estimate}
```
**Problem:** "Time/effort" and "time estimate" default to human framing. Agent implementation cost should be in compute-$ and number of tasks.
**Fix:** Change to `**Compute estimate:** {$X} — {N tasks, ~M minutes}` or at least `{Easy/Medium/Hard} — {compute cost}`.

### F-31: Patterns agent — Comparison Matrix has no cost row
**File:** `.claude/agents/spark/patterns.md` lines 141-151
```markdown
| Complexity | {rating} | {rating} | {rating} |
| Maintainability | {rating} | {rating} | {rating} |
| Performance | {rating} | {rating} | {rating} |
```
**Problem:** Comparison matrix lacks "Compute cost to implement" and "Compute cost to maintain" rows.
**Fix:** Add `| Implementation cost ($) |` and `| Ongoing compute cost ($) |` rows.

---

## Category 7: Devil's Advocate — ROI/Effort Arguments

### F-32: Devil agent — "Adds Complexity Without Clear ROI"
**File:** `.claude/agents/spark/devil.md` line 177
```markdown
### Argument 1: Adds Complexity Without Clear ROI
```
**Problem:** ROI framing is CORRECT for devil's advocate. But "ROI" should be reframed from human-effort-based to compute-cost-based. Example devil output says "200+ LOC, ongoing maintenance" — maintenance cost should be in $ not vague "ongoing".
**Fix:** Devil should quantify maintenance cost in compute terms: "200 LOC = ~$2/month in maintenance compute when changes needed".

### F-33: Devil agent — "5% of effort" comparison
**File:** `.claude/agents/spark/devil.md` line 207
```markdown
**Verdict:** Alternative 1 (soft warning) might solve 80% of need with 5% of effort.
```
**Problem:** "5% of effort" is relative but doesn't specify whose effort. Should be "5% of compute cost" explicitly.
**Fix:** Change example to "~$0.50 compute vs ~$10 compute".

---

## Category 8: Architect Agents Missing LLM-Native Cost Blocks

### F-34: Architect DX agent — "Innovation Token Budget" (metaphor)
**File:** `.claude/agents/architect/dx.md` lines 45, 149
```markdown
1. **Innovation Token Budget**
...
**Token Budget:** 3 tokens for this project
```
**Problem:** "Innovation tokens" is a human-team metaphor (choose N new technologies). Not a compute cost issue. **KEEP — it's about architectural complexity, not effort estimation.**

### F-35: Architect Ops agent — "Error Budget"
**File:** `.claude/agents/architect/ops.md` lines 207-209
```markdown
**Error Budget:**
- [What happens when budget is exhausted]
```
**Problem:** SRE error budgets are infrastructure concepts, not human effort. **KEEP AS-IS.**

### F-36: Architect DX agent — "ROI calculation" for tech choices
**File:** `.claude/agents/architect/dx.md` line 41
```markdown
If it's curiosity, it better come with an ROI calculation.
```
**Problem:** ROI is fine, but DX agent lacks LLM-native mindset block that council agents have. Should add one.
**Fix:** Add LLM-native mindset block with cost references for DX decisions.

### F-37: Architect Evolutionary — No LLM-native mindset block
**File:** `.claude/agents/architect/evolutionary.md`
**Problem:** Missing the `## LLM-Native Mindset (CRITICAL!)` block that council agents have. Uses "sprint" language (line 294).
**Fix:** Add LLM-native mindset block.

---

## Category 9: Agents WITHOUT LLM-Native Mindset Blocks

The following agents work on cost/effort topics but LACK the LLM-native mindset block:

### F-38: Architect Evolutionary agent
**File:** `.claude/agents/architect/evolutionary.md`
**Missing:** No LLM-native mindset block. Uses "sprint" (line 294).

### F-39: Architect DX agent
**File:** `.claude/agents/architect/dx.md`
**Missing:** No LLM-native mindset block. Has ROI language but no compute-cost framing.

### F-40: Architect Synthesizer agent
**File:** `.claude/agents/architect/synthesizer.md`
**Missing:** No LLM-native mindset block. Has "Effort Estimate" section in human-days (F-01).

### F-41: Board COO agent
**File:** `.claude/agents/board/coo.md`
**Missing:** No LLM-native mindset block. Has human team topology language.

### F-42: Board CMO agent
**File:** `.claude/agents/board/cmo.md`
**Missing:** No LLM-native mindset block. Uses "time to ROI" and "content production cost" (line 51).

### F-43: Spark Patterns agent
**File:** `.claude/agents/spark/patterns.md`
**Missing:** No LLM-native mindset block. Uses "time estimate" for complexity (F-30).

---

## Category 10: Template/.claude/ Duplicates

All findings that appear in `.claude/` also appear in `template/.claude/` (per template-sync rule). Files that need changes in BOTH locations:

| Finding | template/.claude/ file |
|---------|----------------------|
| F-01 | `template/.claude/agents/architect/synthesizer.md` |
| F-02 | `template/.claude/agents/architect/evolutionary.md` |
| F-04, F-05, F-06 | `template/.claude/skills/bootstrap/SKILL.md` |
| F-07 | `template/.claude/skills/brandbook/completion.md` |
| F-09 | `template/.claude/skills/architect/retrofit-mode.md` |
| F-10 | `template/.claude/agents/audit/synthesizer.md` |
| F-11 | `template/.claude/agents/council/synthesizer.md` |
| F-21 | `template/.claude/skills/architect/greenfield-mode.md` |
| F-23 | `template/.claude/skills/spark/feature-mode.md` |
| F-30 | `template/.claude/agents/spark/patterns.md` |
| F-37-F-43 | All corresponding template agent files |

---

## Category 11: Backlog and Blueprint

### F-44: Backlog milestones use human calendar
**File:** `ai/backlog.md` lines 5-9
```markdown
| **LAUNCH** | Первый публичный релиз | 1 неделя | 1K stars |
| **GROWTH** | Community traction | 1 месяц | 10K stars |
| **STANDARD** | Стандарт де-факто | 1 год | O-1 виза |
```
**Problem:** Calendar deadlines are LEGITIMATE for business milestones. **KEEP — these are business targets, not effort estimates.**

### F-45: Bootstrap — "Day 1/Day 2" action items
**File:** `.claude/skills/bootstrap/SKILL.md` lines 401-406, 532-584
**Also:** `template/.claude/skills/bootstrap/SKILL.md`
```markdown
### Must have (Day 1):
### Postponed (Day 30+):
## First Steps (Day 1)
→ Day 1: create structure
→ Day 2: /spark for first feature
```
**Problem:** "Day 1/Day 2" here refers to project lifecycle stages, not effort estimates. **KEEP — this is sequencing, not sizing.**

---

## Category 12: Cost Estimate Blocks (Compute-Native, KEEP)

These are already compute-cost framed and should be the STANDARD format:

| File | Lines | Format |
|------|-------|--------|
| `.claude/skills/spark/feature-mode.md` | 50-56 | `~$1-3` |
| `.claude/skills/council/SKILL.md` | 107-113 | `~$3-8` |
| `.claude/skills/bughunt/SKILL.md` | 63-67 | `~$30-50 typical` |
| `.claude/skills/board/SKILL.md` | 41-47 | `~$8-20` |
| `.claude/skills/architect/SKILL.md` | 49 | Has cost estimate section |

---

## Files NOT Needing Changes (Verified Clean)

- `.claude/skills/autopilot/` — Uses compute-native language throughout
- `.claude/skills/coder/SKILL.md` — No effort estimation
- `.claude/skills/review/SKILL.md` — No effort estimation
- `.claude/skills/reflect/SKILL.md` — No effort estimation
- `.claude/skills/qa/SKILL.md` — No effort estimation
- `.claude/agents/coder.md` — No effort estimation
- `.claude/agents/tester.md` — No effort estimation
- `.claude/agents/documenter.md` — No effort estimation (has "matrix" but it's documentation matrix)
- `.claude/agents/scout.md` — Clean
- `.claude/rules/architecture.md` — Clean (patterns/anti-patterns, no effort)
- `.claude/rules/dependencies.md` — Clean
- `.claude/rules/model-capabilities.md` — Clean (mentions cost but in API pricing context)
- `CLAUDE.md` (root) — Clean
- `template/CLAUDE.md` — Clean

---

## Action Plan Summary

### HIGH PRIORITY (systematic impact on agent decisions)
1. **F-01, F-03:** Architect synthesizer effort template → compute-cost format
2. **F-09, F-10:** T-shirt sizing → define in compute terms
3. **F-30, F-31:** Patterns agent → compute-cost estimates
4. **F-32, F-33:** Devil agent → quantify in $ not vague "effort"
5. **F-37-F-43:** Add LLM-native mindset blocks to 6 agents missing them

### MEDIUM PRIORITY (improves consistency)
6. **F-02:** Remove "sprint" language from evolutionary agent
7. **F-04, F-05:** Bootstrap → add compute budget alongside human time
8. **F-21:** Architect greenfield → "compute capacity" not "team Y"
9. **F-24:** Spark routing → add compute-cost threshold to decision criteria
10. **F-07:** Brandbook → compute-cost phases not human days

### LOW PRIORITY (edge cases or already partially correct)
11. **F-06:** Bootstrap feasibility challenge framing
12. **F-12:** Board retrofit "effort" → "compute cost"
13. **F-19:** COO barrels/ammunition → add agent equivalent
14. **F-23:** Priority question reframe (subtle improvement)

### KEEP AS-IS (already correct or legitimate business language)
- F-08 (CFO CAC payback), F-13-F-16 (LLM-native blocks), F-17-F-18 (forbidden examples), F-20 (COO hiring), F-22 (infra budget), F-25 (kill question), F-26-F-29 (P0-P3 severity), F-34-F-35 (innovation/error budgets), F-44-F-45 (business milestones)
