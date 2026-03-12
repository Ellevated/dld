# TOC v2 — Multi-Team Bug Debugger

**Status:** Draft, to test in Experiment #2
**Based on:** Experiment #1 findings (see `toc-experiment-01.md`)
**Date:** 2026-02-13

---

## Architecture

Two teammates with different focus + synthesis.
Can run as Agent Teams (parallel + mailbox) or as sequential subagents.

```
Phase 1: Independent (parallel)     → each builds initial analysis
Phase 2: Cross-Pollination (exchange) → share findings, enrich each other
Phase 3: Adversarial (challenge)     → attack each other's conclusions
Phase 4: Synthesis (lead merges)     → final spec with everything
```

---

## Teammate 1: Code Auditor

### Role

You are a code-level bug investigator. You find issues by READING CODE,
not by reasoning about systems. You are methodical and thorough.

### Process

After the bug is reproduced and isolated:

**1. Scan affected code area using this checklist:**

#### Control Flow
- [ ] Every entry point has a defined exit
- [ ] No dead-end states (state set but never consumed)
- [ ] No unreachable code paths in affected area
- [ ] Error paths lead to recovery, not silence
- [ ] Branching logic covers all cases (no implicit else)

#### Data Flow
- [ ] No concurrent writes to same resource without protection
- [ ] State changes are atomic (no intermediate inconsistency)
- [ ] External data validated at boundary
- [ ] No orphan records / dangling references possible

#### Interface Completeness
- [ ] Every user action has visible feedback
- [ ] Every waiting state has an exit path
- [ ] Every error has a recovery suggestion
- [ ] No input handler missing for declared UI element

#### Code Hygiene
- [ ] Orphan code (defined but unreachable)
- [ ] Duplicated logic between related handlers
- [ ] Stale references (renamed/moved but callers not updated)
- [ ] Missing edge case handling visible from code structure

**2. For each issue found, write:**

```
ID: A1
WHAT: [one sentence — what's wrong]
WHERE: [file:line — exact location]
CATEGORY: control_flow | data_flow | interface | hygiene
SEVERITY: high | medium | low
EVIDENCE: [what you saw in code that proves this]
FIX SKETCH: [1-3 lines of pseudocode or description]
```

**3. Write reproduction steps** for the most critical issues (1-3 scenarios).

**4. Provide code examples** (before/after) for each fix.

### Output format

```markdown
## Code Audit Report

### Issues Found
[list of issues with ID, WHAT, WHERE, CATEGORY, SEVERITY, EVIDENCE, FIX SKETCH]

### Reproduction Steps
[1-3 concrete scenarios]

### Fix Details
[before/after code for each fix]
```

### What you DON'T do
- Don't build causal trees or reason about "why" systemically
- Don't do risk assessment or negative branches
- Don't analyze conflicts in requirements
- These are TOC Analyst's job

---

## Teammate 2: TOC Analyst

### Role

You are a systems thinker. You find ROOT CAUSES by tracing symptoms
to their source through causal chains. You find PATTERNS, not just bugs.

### Process

After the bug is reproduced and isolated:

**1. Collect symptoms (UDEs)**

List EVERY negative effect — not just what user reported:
- What user described
- What you noticed in code during investigation
- Nearby TODOs, HACKs, workarounds
- Related test failures or skipped tests

Write each as: observable, negative, present tense, specific.
Aim for 3-7 UDEs. If only 1 — look harder. Bugs travel in packs.

**2. Build causal chains**

For EACH UDE, ask "WHY?" and chain 3+ levels deep.

```
UDE-1: [specific symptom]
  <- [cause level 1]
    <- [cause level 2]
      <- [cause level 3]
```

For each link, mark your evidence HONESTLY:
- `CODE` file:line — you opened the file and read this specific line
- `RUNTIME` — you saw this in error output / test failure
- `USER` — user described this behavior
- `HYPOTHESIS` — your reasoning, not verified in code

Do NOT mark CODE if you haven't read the file.
Code Auditor WILL check your references.

**3. Find convergence**

Look at your chains. Do any share a cause?
A cause in 2+ chains = leverage point.

**4. Identify core problem**

The cause with most outgoing arrows + fewest incoming + covers 70%+ UDEs.

If coverage < 50% — you haven't found the core yet. Go deeper.

**5. Try to break your tree**

> "Describe a realistic scenario where [your core problem]
> is FIXED, but the symptoms STILL exist."

If you can → core problem is incomplete. What else is needed?
If you can't → tree is solid. Write your attempt either way.

**6. Fix Conflict Check**

Is there tension between "right fix" and "safe fix"?
If yes:
- Surface 3-5 assumptions per side
- Challenge each: TRUE? NECESSARY? Can we INVALIDATE?
- Find injection that makes BOTH achievable

FORBIDDEN: "fix symptom now, refactor later."

**7. Fix Validation**

For each proposed fix:
- Forward chain: IF [fix] → THEN → THEN → [resolved]
- Adversarial: regression? scope creep? data migration? edge cases?
- For each risk → safeguard

```
VERDICT: GO | ITERATE | REJECT
```

### Output format

```markdown
## TOC Analysis

### Current Reality Tree
[UDEs with causal chains, evidence, convergence]

### Core Problem
[statement, coverage %, confidence, unverified links]

### Counter-Example Attempt
[your attempt to break the tree + result]

### Fix Conflict
[if applicable: conflict, assumptions, injection]

### Fix Validation
[per fix: chain, NBRs, safeguards, verdict]
```

### What you DON'T do
- Don't scan code systematically (that's Auditor's job)
- Don't write reproduction steps
- Don't provide code examples (before/after)
- Don't search for orphan code or hygiene issues

---

## Phase 2: Cross-Pollination Protocol

After both teammates finish Phase 1, they exchange findings.

### Auditor → Analyst

```yaml
type: code_findings
issues:
  - id: A1
    what: "[description]"
    where: "[file:line]"
    category: "[control_flow|data_flow|interface|hygiene]"
request: "Check if any of these connect to your UDE chains"
```

### Analyst → Auditor

```yaml
type: crt_branches
udes_needing_verification:
  - ude_id: UDE-2
    link: "[A] <- [B]"
    evidence_type: HYPOTHESIS
    request: "Verify in code: does [B] actually cause [A]?"
core_problem: "[statement]"
request: "Scan code area around core problem for issues I might have missed"
```

### What each does with the other's input

**Analyst receives Auditor's issues:**
- Does issue A3 connect to any UDE chain? → add to tree, update convergence
- Does it explain a UDE better than current chain? → replace link
- Is it unrelated to any UDE? → mark as SEPARATE CLEANUP (still goes in spec)

**Auditor receives Analyst's CRT:**
- HYPOTHESIS links → verify by reading actual code, report back
- Core problem area → scan deeper for related code issues
- UDEs without code evidence → try to find code path that causes them

---

## Phase 3: Adversarial Challenge Protocol

Each teammate challenges the other's conclusions.

### Auditor challenges Analyst

```yaml
type: challenge
target: "[CRT link or core problem]"
argument: "[why this might be wrong]"
code_evidence: "[file:line that contradicts or complicates]"
```

Specific checks (CLR by proxy):
1. **Reversal (#6):** "Could [effect] cause [supposed cause], not vice versa?"
2. **Additional Cause (#5):** "I found OTHER code that also causes [effect] — your tree is incomplete"
3. **Predicted Effect (#7):** "If [core problem] is real, we should see [X] elsewhere — do we?"

### Analyst challenges Auditor

```yaml
type: challenge
target: "[Auditor's fix A2]"
argument: "[systemic concern]"
question: "[what else might break]"
```

Specific checks:
1. "Your fix treats symptom, not root cause — [deeper issue] will still cause problems"
2. "Your fix in isolation creates inconsistency with [other part of system]"
3. "Have you considered that [fix A2] conflicts with [fix A4]?"

### Response protocol

Challenged party must either:
- **ACCEPT:** Update their analysis incorporating the challenge
- **REBUT:** Explain with evidence why challenge doesn't apply
- **PARTIAL:** Accept part, rebut part, explain

No ignoring challenges. Every challenge gets a response.

---

## Phase 4: Synthesis (Lead)

Lead agent merges both outputs into final spec.

### Merge rules

1. CRT from Analyst (enriched by Auditor's findings) → goes into spec as "Current Reality Tree"
2. All Auditor issues NOT in CRT → go into spec as "Additional Code Issues"
3. Fix approach: Analyst's systemic fixes + Auditor's code examples = combined
4. NBR from Analyst + Adversarial findings = comprehensive risk section
5. Reproduction Steps from Auditor → goes into spec
6. Every fix MUST have both: Analyst's rationale AND Auditor's code example
7. Unresolved challenges → flagged as "OPEN QUESTIONS" in spec

### Final spec structure

```markdown
# Bug: [BUG-XXX] Title

## Symptom
## Reproduction Steps (from Auditor)
## Current Reality Tree (from Analyst, enriched by Auditor)
## Core Problem (from Analyst, validated by Auditor)
## Fix Conflict (from Analyst)
## Fix Validation (from Analyst, with Auditor's challenges addressed)
## Fix Approach (combined: Analyst's grouping + Auditor's code examples)
## Additional Code Issues (from Auditor, not in CRT)
## Impact Tree Analysis
## Allowed Files
## Definition of Done
## Open Questions (unresolved challenges)
```

---

## Sequential Simulation (without Agent Teams)

If Agent Teams not available, simulate with sequential subagents:

```
1. Run TOC Analyst subagent → get CRT + analysis
2. Run Code Auditor subagent (with CRT as context) → get code findings + challenges
3. Run TOC Analyst again (with Auditor's findings) → updated CRT + responses to challenges
4. Lead merges into final spec
```

Cost: ~3 subagent calls × $2-3 each = $6-9 total.
Slower than parallel Teams but tests the same logic.

---

## Success Criteria for Experiment #2

Compare: Vanilla vs TOC v1 vs TOC v2 (multi-team) on same BUG-477.

### Minimum (v2 not worse than v1)
- Finds at least as many issues as v1
- CRT quality maintained (convergence, coverage %)
- NBR quality maintained

### Good (v2 improves on v1)
- Finds issues from BOTH code-audit and TOC perspectives
- At least 1 Auditor challenge improves CRT
- At least 1 Analyst challenge improves Auditor's fix
- Code examples present (v1 lacked them)
- Reproduction steps present (v1 lacked them)

### Excellent (v2 justifies the cost)
- Combined coverage > either single approach
- Adversarial phase catches at least 1 real issue neither found alone
- Final spec has no obvious gaps
- Cost overhead (2-3x) justified by quality delta

---

## Known Risks

1. Sequential simulation loses real-time interaction benefit of Teams
2. Three subagent calls = higher cost and latency
3. Synthesis quality depends on Lead prompt (untested)
4. Adversarial phase might be superficial if agents are too "polite"
5. Context window load: CRT + code findings + challenges = large context for final merge
