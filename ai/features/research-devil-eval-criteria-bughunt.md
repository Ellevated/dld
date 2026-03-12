# Devil's Advocate — Add Eval Criteria to Bug Hunt Specs

## Verdict: PROCEED WITH CAUTION

**TL;DR:** The proposal has merit but requires careful scoping. The EC format provides measurable quality gates, but bug-fix specs need a SIMPLIFIED subset, not the full feature machinery. Backward compatibility is actually fine. The real risk is prompt bloat and cognitive overhead in solution-architect.

---

## DA-1: Bug Fixes vs Features — Different Species

**Concern:** Bug fix specs are fundamentally simpler than feature specs. They have a KNOWN correct behavior (the opposite of the bug), while features have AMBIGUOUS expected behavior. Adding full Eval Criteria machinery (LLM-Judge type, Integration Assertions, Coverage Summary) to bug fixes is like bringing a rocket launcher to a knife fight.

**Evidence:**
- Solution-architect template (line 91): Current "Definition of Done" has 4 checkboxes — simple, measurable, directly tied to the fix
- Feature-mode Eval Criteria (lines 438-466): 3 assertion types, Coverage Summary, TDD Order, minimum 3 criteria — complex machinery designed for ambiguous requirements
- Bug-118 "Definition of Done" (lines 217-229): 9 specific, measurable conditions. These ARE eval criteria — just not in EC-N format.

**Impact:** Medium

**Counter:** Use a SIMPLIFIED EC format for bug fixes. Drop LLM-Judge (bugs don't involve LLM evaluation), drop TDD Order (bug fixes already have tests-last in practice). Keep only:
- Deterministic Assertions (regression checks)
- Coverage Summary (minimal: just regression count)
- NO Integration Assertions unless the bug is an integration bug
- NO LLM-Judge — bugs are deterministic

---

## DA-2: Source Attribution Chain Mismatch

**Concern:** Feature-mode has a clear chain: devil produces DA-N → facilitator maps to EC-N. Bug-hunt has a DIFFERENT chain: personas produce CR-001/SEC-001 → validator groups → solution-architect writes spec. The EC-N format assumes a devil's advocate as the source. Bug-hunt has NO devil's advocate step.

**Evidence:**
- Devil agent template (lines 104-122): Produces `DA-N` rows with Risk, Priority, Type
- Facilitator template (feature-mode line 438-466): Maps DA-N → EC-N with source attribution
- Solution-architect template (lines 8-40): Receives VALIDATOR_FILE with grouped findings, no devil input

**Impact:** High

**Counter:**
1. **Option A (minimal):** Solution-architect generates EC-N rows from findings WITHOUT source attribution. Source field can say "bug-hunt-finding-F-009" instead of "devil scout". This breaks uniformity with feature specs but is honest.
2. **Option B (add devil step):** Insert a devil's advocate agent AFTER validator, BEFORE solution-architect. Devil reads grouped findings, produces DA-N edge cases for the group. This matches feature-mode pattern but adds a new step to bug-hunt pipeline.
3. **Recommended:** Option A for now. Bug-hunt findings are ALREADY devil's advocate output (6 diverse personas found them). No need for another devil step.

---

## DA-3: Backward Compatibility — Actually Fine

**Concern:** Existing bug-hunt specs use "Definition of Done". Will validate-spec-complete.mjs still work? Will tester agent choke?

**Evidence:**
- validate-spec-complete.mjs lines 125-181: `checkTests()` function has DUAL DETECTION
  - Priority 1: Check for `## Eval Criteria` (new format)
  - Priority 2: Check for `## Tests` (legacy format)
  - If neither → error
- Line 154: `if (/^## Eval Criteria/m.test(content))` — regex check for new format
- Lines 160-180: Fallback to legacy `## Tests` section
- Tester agent (line 151): "When spec has `## Eval Criteria` with `llm-judge` type entries" — implies it handles both formats

**Impact:** Low (already solved)

**Counter:** No mitigation needed. The validation hook already supports both formats. Tester agent already has conditional logic. New bug-hunt specs can use Eval Criteria, old specs continue to work. This is NOT a breaking change.

---

## DA-4: Prompt Bloat in Solution-Architect

**Concern:** Solution-architect already has a complex job (Impact Tree, Root Cause, Fix Approach, Allowed Files, Research). Adding Eval Criteria template increases prompt size from ~125 lines to ~180 lines (44% increase). Risk: quality drop in other sections due to cognitive overload.

**Evidence:**
- Solution-architect template: 125 lines currently
- Feature-mode Eval Criteria section: ~55 lines of template + examples
- ADR-005: Effort routing — solution-architect is `effort: high` (not max), model is opus
- Opus 4.6 128K output capacity — prompt size is not a technical limit

**Impact:** Medium

**Counter:**
1. **Simplify the template** — bug-fix EC format should be ~20 lines, not 55
2. **Drop TDD Order** — bugs don't follow TDD (fix first, then regression test)
3. **Drop Coverage Summary** — just count regression tests
4. **Keep only Deterministic Assertions** — one table, EC-N rows
5. **Total addition: ~25 lines** instead of 55 → manageable

---

## DA-5: Natural Eval Criterion — "The Bug Is Fixed"

**Concern:** Bug fixes have a NATURAL eval criterion: the bug no longer reproduces. Feature specs need eval criteria because "does it work?" is ambiguous. Bug fix behavior is NOT ambiguous — the spec literally describes the broken behavior and the correct behavior. Why formalize what's already clear?

**Evidence:**
- BUG-118 Definition of Done (lines 217-229): Every checkbox is a REGRESSION CHECK
  - "grep `startsWith(dirPrefix)` returns 0 results"
  - "`git commit-graph` no longer triggers the hook"
  - "Manual verification: glob `/*` only matches direct children"
- BUG-102 Definition of Done (lines 79-87): Every checkbox is a PASS/FAIL test
  - "prompt-guard uses `blockPrompt()` instead of `askTool()`"
  - "No redundant process.exit(0) after denyTool/blockPrompt calls"

**Impact:** High (philosophical question)

**Counter:** The FORM matters even if the content is obvious. Structured EC format enables:
1. **Machine parsing** — eval-judge.mjs can extract and run EC-N rows automatically
2. **Consistency** — tester agent uses same logic for bugs and features
3. **Cross-referencing** — link EC-N back to F-N findings in validator output
4. **Coverage tracking** — ensure every high-severity finding has a regression test

The content (regression checks) is already there. EC format just makes it STRUCTURED and PARSEABLE.

---

## Simpler Alternatives

### Alternative 1: Definition of Done → Tests (No EC Format)

**Instead of:** Add Eval Criteria section with EC-N, Coverage Summary, etc.

**Do this:** Rename "Definition of Done" to "Tests" section. Keep checkboxes as-is. No EC-N IDs, no tables.

**Pros:**
- Zero template change
- Backward compatible (already supported by validation hook)
- Simple, clear, works

**Cons:**
- Not machine-parseable (eval-judge.mjs can't extract test cases)
- No source attribution (can't trace which finding triggered which test)
- No priority tracking (all tests treated equally)
- No consistency with feature specs (different format for same purpose)

**Viability:** High — but loses the BENEFIT of structured format

---

### Alternative 2: Minimal EC Format (Deterministic Only)

**Instead of:** Full EC format with 3 assertion types, Coverage Summary, TDD Order

**Do this:** Single table with EC-N, Scenario, Expected Behavior, Source (finding ID), Priority

**Pros:**
- Simple (one table, ~10 lines of template)
- Machine-parseable (eval-judge can extract)
- Source attribution (traces to F-N findings)
- Consistent with feature specs (same format, subset of types)
- Minimal prompt increase (~15 lines)

**Cons:**
- Loses Integration/LLM-Judge types (but bugs don't need them)
- No Coverage Summary (but count is implicit from table row count)
- No TDD Order (but bugs don't follow TDD anyway)

**Viability:** High — **RECOMMENDED**

---

### Alternative 3: Hybrid — DoD for Simple Bugs, EC for Complex Bugs

**Instead of:** Force all bug fixes to use EC format

**Do this:** Keep "Definition of Done" for simple bugs (1-2 files, <10 LOC). Use Eval Criteria only for complex bugs (multi-file, integration, >50 LOC).

**Pros:**
- Flexibility — simple bugs stay simple
- Proportional complexity — only big bugs get EC overhead
- Gradual migration — no rush to convert existing specs

**Cons:**
- Inconsistency — two formats in circulation
- Ambiguous threshold — who decides "complex"?
- Validator needs to classify bug complexity (new step)
- More cognitive load for reviewers (which format should this be?)

**Viability:** Low — complexity outweighs benefit

---

**Verdict on Alternatives:** Alternative 2 (Minimal EC Format) is the sweet spot. Structured, parseable, consistent, but not over-engineered.

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| solution-architect prompt | template/.claude/agents/bug-hunt/solution-architect.md:91-96 | "Definition of Done" template needs replacement | Replace with simplified Eval Criteria template |
| validate-spec-complete.mjs | template/.claude/hooks/validate-spec-complete.mjs:125-150 | Already handles dual format but might need config update | None (already supports both) |
| tester agent | template/.claude/agents/tester.md:151 | Already handles Eval Criteria conditionally | None (already supports both) |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| eval-judge.mjs script | parser | Low | Bug specs with EC format become parseable (benefit, not risk) |
| Existing bug specs | format | None | Backward compat already built into validation |
| Feature specs | consistency | Medium | If bug EC format differs from feature EC, docs must explain both | Document "EC for Bugs" vs "EC for Features" in architecture.md |

---

## Mitigations

### M-1: Simplified EC Template for Bugs

**Problem:** Full EC format (3 types, Coverage Summary, TDD Order) is over-engineered for bugs.

**Fix:** Create a bug-specific EC template with ONLY:

```markdown
## Eval Criteria

### Regression Tests

| ID | Finding | Scenario | Expected Behavior | Priority |
|----|---------|----------|-------------------|----------|
| EC-1 | F-009 | matchesPattern('ai/diary/sub/deep.md', 'ai/diary/*') | returns false | P0 |
| EC-2 | F-009 | matchesPattern('ai/diary/today.md', 'ai/diary/*') | returns true | P0 |
| EC-3 | F-017 | git commit-graph command | hook exits 0 (no check) | P0 |
| EC-4 | F-017 | git commit -m "msg" | hook runs impact tree check | P0 |

**Coverage:** 4 regression tests (min 1 per high-severity finding)
```

Total: ~15 lines. No TDD Order, no Integration/LLM-Judge types, no complex Coverage Summary.

---

### M-2: Source Attribution via Finding IDs

**Problem:** Bug-hunt has no devil's advocate, so EC source chain is broken.

**Fix:** Use Finding IDs (F-N) as source. Table includes "Finding" column mapping EC-N → F-N. Validator YAML already has F-IDs, solution-architect can reference them.

---

### M-3: Update ADR-012

**Problem:** ADR-012 currently says "Eval Criteria over freeform Tests" but doesn't specify bug-specific format.

**Fix:** Add to ADR-012:

```markdown
| ADR-012 | Eval Criteria over freeform Tests | 2026-02 | Structured eval criteria (deterministic + integration + llm-judge) provide measurable quality gates. **Bug fixes use simplified format:** regression tests only, no TDD Order, no LLM-Judge. Backward compat with legacy ## Tests. |
```

---

### M-4: Validation Hook Config (Optional)

**Problem:** If we want to enforce minimum EC count for bugs (like feature specs have min 3), config needs update.

**Fix:** Add to `hooks.config.mjs`:

```javascript
enforcement: {
  minTestCases: 3, // applies to both ## Tests and ## Eval Criteria
  minBugRegressionTests: 1, // per high-severity finding (new)
}
```

This is OPTIONAL — current validation already works, this just tunes thresholds.

---

## Recommended Scope (Minimal Viable Change)

**Core changes (MUST):**
1. Replace "Definition of Done" template in solution-architect.md with simplified Eval Criteria template (~15 lines)
2. Update ADR-012 to specify bug-specific EC format (1 sentence)
3. Add example to solution-architect template showing F-N → EC-N mapping

**Nice-to-have (SHOULD):**
4. Document bug EC format in CLAUDE.md or architecture.md (so users know the difference)
5. Update eval-judge.mjs to handle bug-specific EC format (if it doesn't already)

**Skip (WON'T):**
6. Add devil's advocate step to bug-hunt pipeline (overkill, findings are already scrutinized)
7. Create two-tier system (simple bugs = DoD, complex bugs = EC) — inconsistency not worth it
8. Change existing bug specs (backward compat already works)

---

## Risks Summary

| ID | Risk | Severity | Mitigated? |
|----|------|----------|------------|
| DA-1 | Over-engineering bug specs with feature machinery | Medium | Yes (M-1: simplified template) |
| DA-2 | Source attribution chain mismatch | High | Yes (M-2: use F-N IDs) |
| DA-3 | Backward compatibility breaks | Low | Already solved (dual detection) |
| DA-4 | Prompt bloat in solution-architect | Medium | Yes (M-1: 15 lines not 55) |
| DA-5 | Natural criterion ignored | High | Philosophy resolved (form enables tooling) |

---

## Questions to Answer Before Implementation

1. **Question:** Should eval-judge.mjs support the simplified bug EC format, or only the full feature format?
   **Why it matters:** If eval-judge can't parse bug specs, the structured format loses its main benefit (automation).

2. **Question:** Do we enforce minimum EC count for bug specs (e.g., min 1 EC per high-severity finding)?
   **Why it matters:** Without enforcement, solution-architect might write specs with zero regression tests.

3. **Question:** Should the "Finding" column in EC table be REQUIRED or optional?
   **Why it matters:** Traceability F-N → EC-N is valuable but adds cognitive load. Optional = flexible but inconsistent.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The proposal is sound but requires SCOPING DOWN. Full feature EC format is over-engineered for bugs. A simplified regression-test-only format (Alternative 2) delivers the benefits (structure, parseability, consistency) without the overhead (LLM-Judge, Integration Assertions, TDD Order, complex Coverage Summary).

**Conditions for success:**
1. Must use simplified EC template for bugs (~15 lines, not 55)
2. Must map EC-N to F-N findings (source attribution via Finding IDs)
3. Must update ADR-012 to document bug-specific format
4. Must verify eval-judge.mjs handles simplified format (or update it)
5. Must NOT add devil's advocate step to bug-hunt (findings are already scrutinized)
6. Must NOT break backward compatibility (already solved, just verify)

**Implementation estimate:** 1-2 hours (update 1 template, 1 ADR line, test validation hook).

**Risk level:** Low if scoped correctly, Medium if full feature format is used.

**Recommendation to user:** Go ahead with the simplified approach (Alternative 2). The structure is worth it, but keep it proportional to the problem.
