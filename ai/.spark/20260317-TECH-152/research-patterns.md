# Pattern Research -- AI-First Economic Model for DLD Framework

**Feature:** TECH-152 -- Switch from human-centric effort estimation to AI-first economic model
**Date:** 2026-03-17
**Scout:** patterns

---

## Current State Analysis

### Where Effort/Time Metrics Appear Today

After codebase audit, effort/time references cluster in these areas:

1. **Spark Pattern Scout** (`agents/spark/patterns.md`) -- Complexity estimates use "Easy -- 1-2 hours", "Medium -- 4-6 hours", "Hard -- 8-10 hours"
2. **Council Pragmatist** (`agents/council/pragmatist.md`) -- Already uses LLM-native cost: "$0.50", "$3", "$1.50", "$6"
3. **Council Architect** (`agents/council/architect.md`) -- Already uses LLM-native cost: "15 min, ~$1" through "1 day, ~$50"
4. **Council Product** (`agents/council/product.md`) -- Already uses LLM-native cost: "$1", "$0.50", "$5", "$3"
5. **Council Synthesizer** (`agents/council/synthesizer.md`) -- Uses "effort: LLM estimate" in blocking_issues and recommended_changes
6. **Planner** (`agents/planner.md`) -- Size checks (files, LOC) but no time estimates
7. **Spark Feature Mode** (`skills/spark/feature-mode.md`) -- Phase 4 routes on scope/risk/clarity, NOT on effort
8. **Spec Template** -- `Priority: P0/P1/P2` without explicit effort dimension

**Key finding:** Council agents already operate in AI-first mode (dollar costs, minutes). The gap is primarily in Pattern Scout (hours-based estimates) and the absence of a formal priority framework that acknowledges effort=const.

---

## Approach 1: Pure Impact Priority (Drop Effort Entirely)

### Description

Remove all effort/time estimation from all skills. Priority = Cost of Delay only. P0/P1/P2 mapped to business impact tiers with no effort dimension.

### Priority Framework

```
P0 = Revenue/Data loss risk, system down, security breach
P1 = User-facing value, competitive advantage, technical debt with blast radius
P2 = Nice-to-have, cleanup, optimization
```

### How It Changes Each Decision Point

**Council decisions:** Synthesizer drops `effort` field from blocking_issues and recommended_changes. Decision based purely on severity hierarchy (already exists: critical > high > medium > low). No change needed to expert weight logic -- security still trumps all, architect vs pragmatist still prefers simpler.

**Architect decisions:** Architect already thinks in LLM cost ("$2", "$5", "$15"). Removing effort means removing the residual "hours" language but keeping the "$" cost. Architect's concern shifts fully to "blast radius" and "reversibility" -- both already in their wheelhouse.

**Spark Phase 4 routing:** Currently routes on scope/risk/clarity, NOT effort. This approach validates the existing design -- Phase 4 already ignores effort. No change needed.

**Devil's advocate critiques:** Devil already focuses on risk and alternatives. "5% of effort" language in examples needs updating to "5% of risk" or "5% of cost". Devil's Simpler Alternatives section remains valuable -- it captures "skip this entirely" which is the most powerful AI-first optimization.

### Pros

- Simplest to implement -- mostly deletion
- Matches reality: 90% of tasks are ~$1, effort is noise
- Council already mostly works this way
- Eliminates false precision (human hour estimates for AI work)
- Forces focus on "should we do this at all?" not "how long"

### Cons

- Loses signal about architectural risk (a $1 task that corrupts data vs a $1 task that changes a string)
- P0/P1/P2 is coarse -- two P1 tasks with very different risk profiles get equal priority
- "Just delete" approach may lose nuance that matters in edge cases
- Pragmatist loses her "effort_saved" metric -- her YAGNI argument becomes purely qualitative

### Edge Cases Where It Fails

1. **"Simple" migration that breaks everything:** A one-line schema change costs $1 in compute but has massive blast radius. Pure impact scoring misses that the priority should consider irreversibility.
2. **Parallel task saturation:** With 5 slots, pure impact means all P1 tasks are equal. No way to prefer the "safer" P1 when slots are scarce.
3. **Refactoring decisions:** Pragmatist's "400 LOC vs 20 LOC" argument loses its dollar anchor. She can still argue complexity but without quantitative backing.

---

## Approach 2: Impact + Risk (Replace Effort with Risk)

### Description

Priority = Impact (P0/P1/P2). Add a separate Risk dimension that captures what actually matters in AI-first execution: not "how long" but "what could go wrong."

### Priority Framework

```
Impact (WHY):          Risk (HOW SAFELY):
P0 = Critical          R0 = Irreversible (data loss, schema break, security)
P1 = High value        R1 = High blast radius (3+ files, cross-domain, public API)
P2 = Nice-to-have      R2 = Contained (1-2 files, single domain, internal)
```

**Routing matrix:**

| Impact \ Risk | R0 (Irreversible) | R1 (Blast radius) | R2 (Contained) |
|---------------|--------------------|--------------------|-----------------|
| P0 | COUNCIL (must get right) | HUMAN (quick review) | AUTO (just do it) |
| P1 | COUNCIL | AUTO | AUTO |
| P2 | HUMAN (why risk it?) | AUTO | AUTO |

### How It Changes Each Decision Point

**Council decisions:** Synthesizer gets a Risk score alongside severity. "Blocking issue from security, severity critical, risk R0" gives more actionable signal than severity alone. Council can differentiate "critical but reversible" (fix quickly) from "critical and irreversible" (think carefully).

**Architect decisions:** Risk dimension maps perfectly to architect's existing concerns: blast radius (R1), data integrity (R0), domain boundaries (R1). Architect's language shifts from "effort: 30 minutes, ~$2" to "risk: R2 -- contained to billing domain, reversible."

**Spark Phase 4 routing:** The routing matrix above replaces the current ad-hoc routing. Instead of "Cross-domain impact (affects 3+ domains) -> COUNCIL", the rule becomes "R0 or R1 with P0 -> COUNCIL." More precise, less ambiguous.

**Devil's advocate critiques:** Devil's "Impact: High/Medium/Low" becomes "Risk: R0/R1/R2" with concrete criteria. Devil's Simpler Alternatives section gains a new lever: "Alternative reduces risk from R1 to R2" -- this is a more powerful argument than "saves 3 hours."

### Pros

- Captures what actually matters: blast radius, reversibility, data safety
- Natural fit for devil's advocate ("this is R0 -- irreversible!")
- Cleaner routing logic than current ad-hoc Phase 4 rules
- Pragmatist can argue "R2 alternative exists" instead of "saves effort"
- Council gets a concrete risk score for each issue
- "Risk budget" concept: don't burn all 5 slots on R0 tasks simultaneously

### Cons

- Risk assessment itself takes judgment -- agents might misjudge R0 vs R1
- Two dimensions (Impact x Risk) means more states than one dimension
- Risk scores need calibration -- what counts as "irreversible" exactly?
- Adds overhead to spec template (Risk field alongside Priority)

### Edge Cases Where It Fails

1. **Risk disagreement:** Architect says R1, Pragmatist says R2. Need tiebreaker rule (default to higher risk? Use council?).
2. **Novel technology:** New dependency with unknown blast radius. R1 by default? R0 as precaution?
3. **Cumulative risk:** 5 R2 tasks in parallel is fine. But 5 R2 tasks touching the same file? Effective risk compounds.

---

## Approach 3: WSJF-AI (Adapted Formula)

### Description

Mathematical priority formula adapted for AI-first execution:

```
WSJF-AI = Cost of Delay / Risk Score

Cost of Delay = (User Impact + Revenue Impact + Time Criticality)
  - Each scored 1-5
  - User Impact: how many users affected, how badly
  - Revenue Impact: direct revenue at risk or unlocked
  - Time Criticality: deadline, competitive pressure, dependency chain

Risk Score = (Architectural Complexity + Blast Radius + Reversibility)
  - Each scored 1-3
  - Architectural Complexity: 1=single file, 2=cross-file, 3=cross-domain
  - Blast Radius: 1=contained, 2=domain-wide, 3=system-wide
  - Reversibility: 1=trivially reversible, 2=migration needed, 3=data loss possible
```

**Example scoring:**

| Task | UI + Rev + Time = CoD | Arch + Blast + Rev = Risk | WSJF-AI |
|------|------------------------|---------------------------|---------|
| Fix IDOR vulnerability | 5+4+5 = 14 | 1+1+1 = 3 | 4.67 |
| Add campaign budgets | 3+4+2 = 9 | 2+2+2 = 6 | 1.50 |
| Refactor event sourcing | 1+1+1 = 3 | 3+3+2 = 8 | 0.38 |

### How It Changes Each Decision Point

**Council decisions:** Synthesizer calculates WSJF-AI for each issue. Instead of "security trumps all" (which is usually right but not always), the formula shows WHY: security issues have high CoD and low Risk. Dissenting opinions get a quantitative frame: "My concern has WSJF-AI of 3.2 vs the proposed approach at 1.8."

**Architect decisions:** Architect fills in Architectural Complexity and Blast Radius scores. These are already his domain. The formula gives him a way to say "this refactoring has WSJF-AI of 0.38 -- don't do it now" instead of "this is low priority."

**Spark Phase 4 routing:** Route based on WSJF-AI thresholds:
- WSJF-AI > 3.0 -> AUTO (high value, low risk)
- WSJF-AI 1.0-3.0 -> HUMAN (moderate)
- WSJF-AI < 1.0 -> Deprioritize or COUNCIL (low value relative to risk)
- Risk Score > 7 regardless of CoD -> COUNCIL (too risky for auto)

**Devil's advocate critiques:** Devil can argue against a feature by showing its WSJF-AI is low: "Cost of Delay is only 3 but Risk Score is 8 -- WSJF-AI = 0.38. This is not worth doing now." Quantitative devil is harder to dismiss.

### Pros

- Mathematically rigorous -- reproducible decisions
- Captures both dimensions (value and risk) in one number
- Enables automated prioritization in backlog
- Gives devil's advocate a powerful quantitative tool
- Natural ordering for slot allocation when 5 slots compete

### Cons

- Scoring overhead: 6 sub-scores per task is friction
- False precision: does "User Impact 3" vs "4" actually mean something?
- Agents may cargo-cult scores to get desired outcome
- Formula needs calibration -- is division the right operator? Should Risk be additive?
- Council experts might argue about scores instead of substance
- LLM agents are bad at consistent numerical scoring across sessions

### Edge Cases Where It Fails

1. **Score gaming:** Agent wants to build something, inflates User Impact to 5. No ground truth to validate.
2. **Anchoring bias:** First scored task anchors all subsequent scores. Task A gets Time Criticality 3, so Task B (slightly less critical) gets 2, even if objectively both are 4.
3. **Formula sensitivity:** CoD = 15, Risk = 3 gives WSJF-AI = 5.0. CoD = 15, Risk = 4 gives 3.75. One point of risk difference changes priority by 25%. Is that signal or noise?
4. **Non-comparable tasks:** "Fix IDOR" vs "add dark mode" -- scoring both on the same 1-5 scale forces false equivalence.

---

## Recommendation

**Approach 2: Impact + Risk** is the strongest choice.

### Rationale

1. **Already half-implemented.** Council agents already use dollar-cost language. Spark Phase 4 already routes on scope/risk/clarity. Approach 2 formalizes what already works rather than inventing new machinery.

2. **Right abstraction level for LLM agents.** LLMs are good at categorical judgment (R0/R1/R2) and bad at numerical precision (1-5 scores). Approach 2 uses categories. Approach 3's 6 numerical scores will be inconsistent across sessions.

3. **Devil's advocate becomes sharper.** "This is R0 -- irreversible" is a more powerful argument than "WSJF-AI is 0.38." Risk categories are intuitive; composite scores are not.

4. **Minimal disruption.** Changes are mostly language updates in existing files, plus a routing matrix for Phase 4. No new scoring infrastructure. No formula calibration. No numerical scoring training.

5. **Handles the real edge case.** The key edge case is "cheap task with catastrophic risk." P0+R0 goes to council. Pure Impact (Approach 1) would miss this. WSJF-AI (Approach 3) would catch it but with more overhead.

### What to Adopt from Other Approaches

- **From Approach 1:** Delete all "hours/days/weeks" language. Replace with dollar costs where helpful (Pragmatist, Architect already do this).
- **From Approach 3:** The CoD concept (User Impact + Revenue Impact + Time Criticality) is useful for P0/P1/P2 calibration -- not as scores, but as qualitative criteria for each tier.

---

## Impact on Each Skill

### Skills to Modify

| Skill/Agent | File | Change | Scope |
|-------------|------|--------|-------|
| **spark/patterns** | `agents/spark/patterns.md` | Replace "Complexity Estimate: Easy -- 1-2 hours" with "Risk: R0/R1/R2 -- {rationale}" | Template + example |
| **spark/devil** | `agents/spark/devil.md` | Replace "Impact: High/Medium/Low" with "Risk: R0/R1/R2" in arguments; keep "Viability" in alternatives | Template + example |
| **spark/feature-mode** | `skills/spark/feature-mode.md` | Add Impact x Risk routing matrix to Phase 4; add Risk field to spec template header | Phase 4 + template |
| **spark/completion** | `skills/spark/completion.md` | Add Risk field to backlog entry format | Backlog format |
| **council/pragmatist** | `agents/council/pragmatist.md` | Replace "effort_saved" with "risk_reduced" in concerns; keep dollar costs | concerns template |
| **council/architect** | `agents/council/architect.md` | Replace "effort: LLM estimate" with "risk: R0/R1/R2" in concerns | concerns template |
| **council/product** | `agents/council/product.md` | Keep dollar costs for UX fixes; add risk dimension for user-facing changes | Minimal |
| **council/synthesizer** | `agents/council/synthesizer.md` | Replace "effort: LLM estimate" with "risk: R0/R1/R2" in blocking_issues/recommended_changes; add risk to total summary | Template |
| **planner** | `agents/planner.md` | Add Phase 3 Risk Assessment checklist: classify each task as R0/R1/R2 | Phase 3 |
| **board/SKILL.md** | `skills/board/SKILL.md` | No change -- Board operates at business level, not task level |  |
| **architect** | `skills/architect/` | No change -- Architect designs systems, not individual tasks | |

### Skills NOT Modified

| Skill/Agent | Reason |
|-------------|--------|
| **board** | Business architecture -- operates above task priority |
| **architect** | System design -- risk is inherent in domain/data decisions, not a separate score |
| **bootstrap** | Idea extraction -- no priority decisions |
| **audit** | Read-only analysis -- reports findings, doesn't prioritize |
| **scout** | Research -- no priority decisions |
| **coder** | Execution -- follows planner instructions |
| **tester** | Execution -- follows planner instructions |
| **review** | Quality gate -- no priority decisions |
| **bughunt** | Discovery -- reports findings, separate scoring in validator |

### New Artifacts

1. **Risk Classification Guide** (add to `CLAUDE.md` or `.claude/rules/`):
   ```
   R0 = Irreversible: data loss, schema migration, security exposure, public API break
   R1 = High blast radius: 3+ files, cross-domain, external dependency, state machine change
   R2 = Contained: 1-2 files, single domain, internal, trivially rollbackable
   ```

2. **Phase 4 Routing Matrix** (add to `skills/spark/feature-mode.md` Phase 4):
   ```
   P0+R0 -> COUNCIL
   P0+R1 -> HUMAN (quick review)
   P0+R2 -> AUTO
   P1+R0 -> COUNCIL
   P1+R1 -> AUTO
   P1+R2 -> AUTO
   P2+R0 -> HUMAN (why risk it for P2?)
   P2+R1 -> AUTO
   P2+R2 -> AUTO
   ```

3. **Backlog Entry Format** (update in `skills/spark/completion.md`):
   ```
   | ID | Task | Status | Priority | Risk | Feature.md |
   ```

### Migration Path

**Phase 1 (quick, low risk):** Update language in all agent templates. Replace "hours/days" with risk categories. Keep dollar costs where they already exist.

**Phase 2 (medium, contained):** Add routing matrix to Spark Phase 4. Add Risk field to spec template and backlog format.

**Phase 3 (validate):** Run 3-5 specs through updated pipeline. Check: do agents use R0/R1/R2 consistently? Does the routing matrix produce correct escalation decisions?

---

## Research Sources

- DLD codebase analysis: `agents/council/pragmatist.md`, `agents/council/architect.md` -- already contain LLM-native cost references
- DLD codebase analysis: `skills/spark/feature-mode.md` Phase 4 -- already routes on risk/scope, not effort
- SAFe WSJF framework -- Cost of Delay / Job Duration. When Duration -> const, WSJF -> CoD (confirms Approach 1's thesis)
- Risk-based prioritization in DevOps (blast radius, reversibility) -- common in deployment risk scoring
