# Feature: [TECH-130] Structured Eval Criteria in Spec Template

**Status:** done | **Priority:** P1 | **Date:** 2026-02-22

## Why

EDD-research (Feb 2026) shows industry consensus: structured eval criteria > freeform test checklists. Current `## Tests` section in Spark specs uses prose checkboxes that lose information between Devil scout -> Spec -> Planner. Structured eval criteria enable machine-parseable assertions, LLM-as-judge type, and direct mapping from Devil findings.

## Context

- ADR-012: Eval Criteria over freeform Tests
- EDD research: promptfoo, DeepEval, Braintrust all use structured assertions
- Current `## Tests` section (feature-mode.md:438-452) = 3 checkboxes + "How to test" + "TDD Order"
- Validators: `validate-spec-tests.mjs` (73 LOC) and `validate-spec-complete.mjs` Check 4 (127-151)
- hooks.config.mjs enforcement section (106-112)

---

## Scope

**In scope:**
- Replace `## Tests (MANDATORY)` template with `## Eval Criteria (MANDATORY)` in feature-mode.md
- Update validation scripts for dual-detection (new format + backward compat)
- Update hooks.config.mjs with new enforcement keys
- Update DoD and Gate 2 references

**Out of scope:**
- LLM-as-Judge runner (Wave 4 / TECH-133)
- Devil scout format change (Wave 2 / TECH-131)
- Migration of existing specs

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] `validate-spec-tests.mjs` — validates `## Tests` section
- [x] `validate-spec-complete.mjs` — Check 4 calls `checkTests()`
- [x] `hooks.config.mjs` — enforcement config
- [x] Planner agent reads `## Tests` to generate TDD tasks
- [x] Tester agent references test cases

### Step 2: DOWN — what depends on?
- [x] feature-mode.md template used by spark-facilitator

### Step 3: BY TERM — grep
- [x] `## Tests` across template/ — feature-mode.md, validate-spec-tests.mjs, validate-spec-complete.mjs
- [x] `requireTestsInSpec` — hooks.config.mjs
- [x] `minTestCases` — hooks.config.mjs, validate-spec-complete.mjs

### Step 4: CHECKLIST
- [x] tests/ — no changes to test files
- [x] Existing test/scripts/spark-state.test.mjs — unaffected

### Verification
- [x] All found files added to Allowed Files
- [x] Backward compat: old `## Tests` still validated

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/skills/spark/feature-mode.md` — replace Tests template, update Gate 2, update DoD refs
2. `template/.claude/scripts/validate-spec-tests.mjs` — dual-detection logic
3. `template/.claude/hooks/validate-spec-complete.mjs` — extend checkTests() for dual format
4. `template/.claude/hooks/hooks.config.mjs` — add enforcement keys
5. `template/.claude/rules/architecture.md` — ADR-012 entry

**Sync after:**
- `.claude/skills/spark/feature-mode.md`
- `.claude/scripts/validate-spec-tests.mjs`
- `.claude/hooks/validate-spec-complete.mjs`
- `.claude/hooks/hooks.config.mjs`
- `.claude/rules/architecture.md`

---

## Environment
nodejs: true
docker: false
database: false

---

## Blueprint Reference
**Domain:** DLD framework infrastructure
**Cross-cutting:** ADR-004 (fail-safe hooks), ADR-011 (Enforcement as Code)

---

## Approaches

### Approach 1: Replace Tests entirely
Remove `## Tests`, only support `## Eval Criteria`.
**Pros:** Clean, no dual logic
**Cons:** Breaks all existing specs

### Approach 2: Dual-detection with backward compat (Selected)
Support BOTH `## Eval Criteria` (priority) and `## Tests` (fallback).
**Pros:** Zero breakage, gradual migration
**Cons:** Slightly more validator logic

### Selected: 2
**Rationale:** Backward compat is critical — dozens of existing specs use `## Tests`.

---

## Design

### New Template Section (replaces lines 438-452 in feature-mode.md)

```markdown
## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | {scenario} | {input} | {expected behavior} | deterministic | {devil/user/blueprint} | P0 |

### Integration Assertions (if applicable)

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|

### LLM-Judge Assertions (if LLM-involved feature)

| ID | Input | Rubric | Threshold | Source | Priority |
|----|-------|--------|-----------|--------|----------|

### Coverage Summary
- Deterministic: {N} | Integration: {N} | LLM-Judge: {N} | Total: {N} (min 3)

### TDD Order
1. Write test from EC-1 -> FAIL -> Implement -> PASS
2. Continue by priority (P0 first)
```

### Validator Logic (validate-spec-tests.mjs)

```javascript
// Check Eval Criteria first (new format)
if (/^## Eval Criteria/m.test(content)) {
  const section = extractSection(content, '## Eval Criteria');
  const ecRows = (section.match(/\|\s*EC-\d+/g) || []).length;
  if (ecRows < minEvalCriteria) { /* fail */ }
  if (!/### Coverage Summary/i.test(section)) { /* fail */ }
  if (!/### TDD Order/i.test(section)) { /* fail */ }
  // pass
} else if (/^## Tests/m.test(content)) {
  // existing logic unchanged
} else {
  // fail: missing both
}
```

---

## Implementation Plan

### Research Sources
- [Braintrust EDD](https://www.braintrust.dev/articles/eval-driven-development) — structured eval format
- [DeepEval](https://deepeval.com/docs/getting-started) — assertion patterns

### Task 1: Update feature-mode.md template
**Type:** code
**Files:** modify: `template/.claude/skills/spark/feature-mode.md`
**Pattern:** Replace lines 438-452, update DoD (461-462), update Gate 2 (505-512)
**Acceptance:** New template contains Eval Criteria with 3 assertion types

### Task 2: Update validate-spec-tests.mjs
**Type:** code
**Files:** modify: `template/.claude/scripts/validate-spec-tests.mjs`
**Pattern:** Dual-detection: `## Eval Criteria` first, `## Tests` fallback
**Acceptance:** Both formats validated correctly

### Task 3: Update validate-spec-complete.mjs
**Type:** code
**Files:** modify: `template/.claude/hooks/validate-spec-complete.mjs`
**Pattern:** Extend checkTests() with checkEvalCriteria() priority check
**Acceptance:** Specs with either format pass validation

### Task 4: Update hooks.config.mjs + ADR-012
**Type:** code
**Files:** modify: `template/.claude/hooks/hooks.config.mjs`, `template/.claude/rules/architecture.md`
**Pattern:** Add `requireEvalCriteria`, `minEvalCriteria` to enforcement; ADR-012 row
**Acceptance:** Config has new keys, ADR table updated

### Task 5: Sync template -> .claude/
**Type:** code
**Files:** sync 5 files from template/ to .claude/
**Acceptance:** `diff template/.claude/hooks/hooks.config.mjs .claude/hooks/hooks.config.mjs` = identical

### Execution Order
1 -> 2 -> 3 -> 4 -> 5

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | New spec with Eval Criteria | Spec file with `## Eval Criteria` + 3 EC rows | validate-spec-tests.mjs exits 0 | deterministic | user requirement | P0 |
| EC-2 | Old spec with Tests (backward compat) | Spec file with `## Tests` + 3 checkboxes | validate-spec-tests.mjs exits 0 | deterministic | backward compat | P0 |
| EC-3 | Spec missing both sections | Spec with neither `## Tests` nor `## Eval Criteria` | validate-spec-tests.mjs exits 1 | deterministic | validation | P0 |
| EC-4 | Eval Criteria with < 3 rows | Spec with `## Eval Criteria` + 2 EC rows | validate-spec-tests.mjs exits 1 with error | deterministic | enforcement | P1 |
| EC-5 | Missing Coverage Summary | Spec with `## Eval Criteria` but no `### Coverage Summary` | validate-spec-tests.mjs exits 1 | deterministic | enforcement | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 0 | LLM-Judge: 0 | Total: 5

### TDD Order
1. Write test from EC-1 -> FAIL -> Implement -> PASS
2. Continue: EC-2 (backward compat) -> EC-3, EC-4, EC-5

---

## Definition of Done

### Functional
- [ ] feature-mode.md has `## Eval Criteria (MANDATORY)` template
- [ ] Validators support both old (`## Tests`) and new (`## Eval Criteria`) formats
- [ ] hooks.config.mjs has `requireEvalCriteria` and `minEvalCriteria`
- [ ] ADR-012 registered

### Tests
- [ ] All eval criteria (EC-1 through EC-5) pass
- [ ] Existing test/scripts/*.test.mjs still pass
- [ ] Coverage not decreased

### Technical
- [ ] Tests pass (./test fast if applicable)
- [ ] All template files synced to .claude/
- [ ] No regressions

---

## Autopilot Log
[Auto-populated by autopilot during execution]
