# TOC v1 — Bug Mode Enhancement (tested in Experiment #1)

**Status:** Tested on BUG-477, results in `toc-experiment-01.md`
**Tested:** 2026-02-13

This is the EXACT prompt used in experiment #1. Preserved for reproducibility.

---

## How to use

1. Add this file as `skills/spark/toc-layer.md`
2. In SKILL.md Module References add: `| toc-layer.md | CRT + conflict + validation | After ISOLATE, before spec |`
3. In bug-mode.md Phase 3 reference toc-layer.md instead of 5 Whys

---

## Prompt

### Step 1: Current Reality Tree (replaces 5 Whys)

5 Whys — linear: one chain, one root. Reality is a TREE.
Multiple symptoms often share a hidden common cause.

#### 1a. Collect all symptoms (UDEs)

Collect EVERY observable negative effect — not just the reported bug:

- The bug itself (what user reported)
- Related oddities noticed during ISOLATE phase
- Test failures, warnings, workarounds in nearby code
- Comments like "TODO", "HACK", "FIXME" near the bug

Format each as: observable, negative, present tense, specific.

```
UDE-1: [the reported bug — specific, with actual error/behavior]
UDE-2: [related symptom found during investigation]
UDE-3: [another related oddity]
```

Aim for 3-7 UDEs. If only 1 — look harder. Bugs rarely travel alone.

#### 1b. Build causal chains (for EACH UDE)

For each UDE, ask "WHY does this happen?"
Then for each cause — ask "WHY?" again. Go 3+ levels deep.

For EACH causal link A → B, verify:

- **Existence:** Can B happen WITHOUT A? If yes → link is WRONG
- **Sufficiency:** Is A ENOUGH to cause B? Or does B need A + something else?
- **Evidence:** What proves this link? Options:
  - `CODE`: file:line — you saw it in source
  - `RUNTIME`: error log, stack trace, test output
  - `USER`: user described this behavior
  - `HYPOTHESIS`: you THINK this is true but haven't verified

**HYPOTHESIS links are OK but must be marked.** Don't pretend you verified what you didn't.

#### 1c. Connect the branches

Look for where chains CONVERGE:

- Does cause X appear in chains for UDE-1 AND UDE-3?
- That's a leverage point — fixing X fixes multiple symptoms

#### 1d. Identify core problem

The core problem:

- Has MOST outgoing arrows (causes many effects)
- Has FEWEST incoming arrows (is near the root)
- Explains 70%+ of all UDEs
- Is ACTIONABLE (you can actually change it)

Output in spec:

```
CORE PROBLEM: [the deep cause where branches converge]
COVERAGE: X out of Y UDEs trace back to this = Z%
CONFIDENCE: high | medium | low
UNVERIFIED: [list HYPOTHESIS links]
```

### Step 2: Fix Conflict Check

Common conflict in bug fixing:

```
GOAL: Stable, working system
NEED A: Fix it properly     -> D: Refactor the root cause
NEED B: Fix it safely       -> D': Minimal change, low risk
CONFLICT: Big refactor (risky) vs Band-aid (doesn't fix root)
```

Check if YOUR fix has this tension:

1. Is there a conflict between the "right" fix and the "safe" fix?
2. If YES — surface assumptions (3-5 per side)
3. Challenge each: TRUE? NECESSARY? Can we INVALIDATE?
4. Find injection: approach that is BOTH proper AND safe

**FORBIDDEN: "fix the symptom now, refactor later."**

If fix is straightforward — write "No conflict" and move on.

### Step 3: Fix Validation

BEFORE writing spec, stress-test the fix:

1. State the fix in one sentence
2. Forward chain: IF [fix] -> THEN [effect] -> THEN [bug resolved]
3. Adversarial checks for EACH step:
   - **Regression:** What currently-working code depends on the broken behavior?
   - **Scope creep:** Does this fix touch more files than necessary?
   - **Data:** Existing data in production? Migration needed?
   - **Edge cases:** Fix works for ALL inputs or just reported case?
   - **Tests:** Will existing tests break? Correct or sign of wrong fix?
4. For each risk -> propose safeguard

```
VERDICT: GO | ITERATE | REJECT
```

### Rules

1. Every causal link needs EVIDENCE TYPE — CODE, RUNTIME, USER, or HYPOTHESIS
2. HYPOTHESIS is honest. Mark what you didn't verify.
3. Look for CONVERGENCE — multiple UDEs sharing a cause = the real find
4. No "fix symptom now, refactor later"
5. At least 2 negative branches in validation
6. These sections go into bug spec BEFORE "Fix Approach"

---

## Known Weaknesses (from experiment)

1. **Self-validation doesn't work** — LLM confirms own causal links (anchoring bias)
2. **Evidence marking unreliable** — tends to mark everything as CODE
3. **Misses infrastructure issues** — stays at user-symptom level, doesn't scan code broadly
4. **No code examples** in output (descriptive only)
5. **No reproduction steps** generated

These weaknesses led to v2 design (see `toc-v2-multiteam.md`).
