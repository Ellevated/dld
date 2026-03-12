# Feature: [TECH-131] Devil Scout Structured Eval Assertions

**Status:** done | **Priority:** P1 | **Date:** 2026-02-22

## Why

Devil scout produces edge cases as prose tables and P0/P1/P2 checklists. Facilitator manually rewrites them into spec's `## Tests` section — losing structure, input specificity, and priority. Structured assertions flow directly from Devil into spec Eval Criteria without lossy rewriting.

## Context

- Depends on TECH-130 (Eval Criteria format defined)
- Current Devil output: `## Edge Cases` table (devil.md:104-111) + `## Tests Needed` P0/P1/P2 (132-145)
- Facilitator maps Devil findings in Phase 5 WRITE (facilitator.md)
- EDD pattern: assertion-based evals (promptfoo, DeepEval, LMUnit)

---

## Scope

**In scope:**
- Replace Devil's `## Edge Cases` + `## Tests Needed` with `## Eval Assertions`
- Update facilitator mapping rule for Devil → Spec EC IDs
- Keep `## What Breaks?` section unchanged

**Out of scope:**
- Spec template change (TECH-130)
- Other scout output formats

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] spark-facilitator.md reads Devil output in Phase 3 (SYNTHESIZE) and Phase 5 (WRITE)

### Step 2: DOWN — what depends on?
- [x] Devil scout reads feature description and codebase scout report

### Step 3: BY TERM
- [x] `## Edge Cases` — only in devil.md
- [x] `## Tests Needed` — only in devil.md
- [x] `Test Priority` — devil.md Edge Cases table column

### Step 4: CHECKLIST
- [x] No test files affected

### Verification
- [x] All found files added to Allowed Files

---

## Allowed Files

1. `template/.claude/agents/spark/devil.md` — replace output format
2. `template/.claude/agents/spark/facilitator.md` — update mapping rule

**Sync after:**
- `.claude/agents/spark/devil.md`
- `.claude/agents/spark/facilitator.md`

---

## Environment
nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Minimal — just rename sections
Rename `## Edge Cases` → `## Eval Assertions`, keep same table columns.
**Pros:** Tiny change
**Cons:** Still lacks structured Input/Expected fields

### Approach 2: Full structured assertions (Selected)
New table format with DA-IDs, concrete Input, Expected Behavior, Type column.
**Pros:** Machine-parseable, direct mapping to EC-IDs
**Cons:** More prompt change, may affect Devil output quality

### Selected: 2
**Rationale:** The whole point is machine-parseable assertions. Minimal rename doesn't achieve EDD goal.

---

## Design

### New Devil Output Format (replaces lines 104-145 in devil.md)

```markdown
## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | {edge case} | {concrete input} | {expected} | High | P0 | deterministic |
| DA-2 | {edge case} | {concrete input} | {expected} | Med | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | {component} | {file}:{line} | {what to verify} | P0 |

### Assertion Summary
- Deterministic: {N} | Side-effect: {N} | Total: {N}
```

### Facilitator Mapping Rule

Phase 5 WRITE: Devil's `DA-1` → Spec's `EC-N` (renumbered sequentially), preserving source: `Source: devil scout DA-1`.

---

## Implementation Plan

### Task 1: Update devil.md output format
**Type:** code
**Files:** modify: `template/.claude/agents/spark/devil.md`
**Pattern:** Replace `## Edge Cases` (104-111) and `## Tests Needed` (132-145) with `## Eval Assertions`
**Acceptance:** Devil output template has DA-IDs, structured Input/Expected columns

### Task 2: Update facilitator.md mapping
**Type:** code
**Files:** modify: `template/.claude/agents/spark/facilitator.md`
**Pattern:** Phase 5 WRITE references eval assertions, maps DA → EC
**Acceptance:** Facilitator has explicit mapping rule documented

### Task 3: Sync template -> .claude/
**Type:** code
**Files:** sync 2 files
**Acceptance:** Files identical between template/ and .claude/

### Execution Order
1 -> 2 -> 3

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Devil output has structured assertions | Run devil scout on sample feature | Output contains `## Eval Assertions` with DA-IDs | deterministic | user requirement | P0 |
| EC-2 | DA IDs are sequential | Devil output with 3+ edge cases | IDs are DA-1, DA-2, DA-3 (sequential) | deterministic | format spec | P1 |
| EC-3 | Side-Effect Assertions present | Devil finds side effects | Output has `### Side-Effect Assertions` table | deterministic | format spec | P1 |

### Coverage Summary
- Deterministic: 3 | Integration: 0 | LLM-Judge: 0 | Total: 3

### TDD Order
1. EC-1 -> verify output format
2. EC-2, EC-3 -> verify structure

---

## Definition of Done

### Functional
- [ ] Devil scout outputs `## Eval Assertions` with DA-IDs
- [ ] Facilitator maps DA → EC in Phase 5
- [ ] `## What Breaks?` section unchanged

### Tests
- [ ] All eval criteria pass
- [ ] No regressions

### Technical
- [ ] Template files synced to .claude/

---

## Autopilot Log
[Auto-populated by autopilot during execution]
