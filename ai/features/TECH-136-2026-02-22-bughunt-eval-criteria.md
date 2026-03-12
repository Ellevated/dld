# Feature: [TECH-136] Bug Hunt Eval Criteria (ADR-012 Compliance)
**Status:** done | **Priority:** P1 | **Date:** 2026-02-22

## Why
Bug Hunt solution-architect generates freeform "Definition of Done" checklists while feature-mode specs use structured Eval Criteria (ADR-012). This breaks the EDD pipeline traceability: tester can't machine-parse bug fix criteria, and persona findings (F-001) lose connection to verification tests.

## Context
Devil's advocate analysis (PROCEED WITH CAUTION): bug fixes are simpler than features — full EC machinery (LLM-Judge, Integration, TDD Order) is over-engineering. Recommended: simplified deterministic-only EC format with F-N→EC-N mapping. ~15 lines of template, not 55.

Hook `validate-spec-complete.mjs` already supports dual detection (Eval Criteria priority, Tests fallback) — no hook changes needed.

---

## Scope
**In scope:**
- Replace "Definition of Done" in solution-architect spec template with simplified Eval Criteria
- Deterministic assertions only (no LLM-Judge, no Integration for bug fixes)
- F-N → EC-N source mapping for traceability
- Simplified Coverage Summary (no TDD Order — fix is known)

**Out of scope:**
- Changing bug-hunt pipeline steps (0-6)
- Adding devil's advocate to bug-hunt (personas ARE the diverse analysis)
- Migrating existing bug specs (backward compat already works)
- Full feature-mode EC format (over-engineering for bugs)

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `template/.claude/skills/spark/bug-mode.md` — orchestrates solution-architect dispatch (Step 6)
- `template/.claude/agents/bug-hunt/report-updater.md` — references DoD in report update
- `template/.claude/agents/tester.md` — parses spec for eval criteria
- `template/.claude/hooks/validate-spec-complete.mjs` — validates spec structure

### Step 2: DOWN — what depends on?
- `template/.claude/agents/bug-hunt/validator.md` — provides F-N findings as input
- ADR-012 definition in `template/.claude/rules/architecture.md`

### Step 3: BY TERM — grep entire project
- `grep -rn "Definition of Done" template/.claude/agents/bug-hunt/` → solution-architect.md:91
- `grep -rn "Definition of Done" template/.claude/skills/spark/` → bug-mode.md (Quick Bug template)

### Step 4: CHECKLIST — mandatory folders
- [x] No tests to break (prompt-only change)
- [x] No migrations needed
- [x] No glossary needed

### Verification
- [x] All changed files in Allowed Files
- [x] No conflicts with existing code

---

## Allowed Files
**ONLY these files may be modified during implementation:**

**Modified files:**
1. `template/.claude/agents/bug-hunt/solution-architect.md` — Replace DoD template with Eval Criteria
2. `.claude/agents/bug-hunt/solution-architect.md` — Sync from template (template-sync rule)

**FORBIDDEN:** All other files. Hook and tester already support Eval Criteria format.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** N/A (template infrastructure)
**Cross-cutting:** ADR-012 (Eval Criteria over freeform Tests)
**Data model:** None

---

## Approaches

### Approach 1: Simplified Bug EC Format (selected)
**Source:** Devil's advocate analysis, feature-mode.md Eval Criteria template
**Summary:** Replace 4-line DoD checklist with simplified Eval Criteria table — deterministic assertions only, F-N→EC-N mapping, Coverage Summary. No TDD Order, no LLM-Judge, no Integration sections.
**Pros:** Machine-parseable, traceable to findings, consistent with EDD pipeline, minimal prompt bloat (+15 lines)
**Cons:** Less structured than feature-mode EC (intentionally simpler)

### Approach 2: Full Feature-Mode EC Format (rejected)
**Source:** feature-mode.md lines 438-465
**Summary:** Copy full EC template with all 3 assertion types, TDD Order, Coverage Summary.
**Pros:** 100% format consistency with feature specs
**Cons:** Over-engineering (DA-1): bugs don't need LLM-Judge or TDD Order. +55 lines prompt bloat (DA-4).

### Selected: 1
**Rationale:** Devil's advocate correctly identifies that bug fixes have KNOWN correct behavior — the opposite of the bug. Simplified format provides traceability and machine-parseability without unnecessary complexity.

---

## Design

### Eval Criteria Template for Bug Fix Specs

Replace lines 91-96 in solution-architect.md:

**Current (Definition of Done):**
```markdown
## Definition of Done
- [ ] All findings in group fixed
- [ ] Regression test added per finding
- [ ] No new failures
- [ ] Impact tree verified (grep = 0 stale refs)
```

**New (Eval Criteria):**
```markdown
## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Finding | Scenario | Expected Behavior | Priority |
|----|---------|----------|-------------------|----------|
| EC-1 | F-001 | {what was broken} | {correct behavior after fix} | P0 |
| EC-2 | F-005 | {what was broken} | {correct behavior after fix} | P0 |
| EC-3 | - | Regression: no new failures | All existing tests pass | P0 |

### Coverage Summary
- Deterministic: {N} | Total: {N} (min 3, one per finding + regression)
```

### Mapping Rules
- Each finding F-N → at least one EC-N (1:1 minimum)
- Priority derived from severity: critical/high → P0, medium → P1, low → P2
- EC for regression always included (P0)
- Source traceability: Finding column links EC back to validator output

---

## Flow Coverage Matrix (REQUIRED)

| # | Flow Step | Covered by Task | Status |
|---|-----------|-----------------|--------|
| 1 | Solution-architect reads validator findings | - | existing |
| 2 | Generates spec with Eval Criteria | Task 1 | changed |
| 3 | Hook validates spec structure | - | existing (dual detection) |
| 4 | Tester parses Eval Criteria | - | existing |
| 5 | Template synced to .claude/ | Task 1 | changed |

**GAPS:** None.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | solution-architect template has Eval Criteria section | Read solution-architect.md | Contains `## Eval Criteria (MANDATORY)` header | deterministic | user requirement | P0 |
| EC-2 | EC table has Finding column for traceability | Read solution-architect.md template | Table columns include `Finding` with F-N reference | deterministic | devil DA-2 | P0 |
| EC-3 | Coverage Summary present | Read solution-architect.md template | Contains `### Coverage Summary` with min 3 | deterministic | ADR-012 | P0 |
| EC-4 | No Definition of Done checklist | Read solution-architect.md | No `## Definition of Done` section with checkboxes | deterministic | user requirement | P1 |
| EC-5 | Template sync — root matches template | diff template/.claude/.../solution-architect.md .claude/.../solution-architect.md | Files identical | deterministic | template-sync rule | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 0 | LLM-Judge: 0 | Total: 5 (min 3)

### TDD Order
1. EC-1 (Eval Criteria header present) -> verify after edit
2. EC-2 (Finding column) -> verify table structure
3. EC-3 (Coverage Summary) -> verify section
4. EC-4 (No DoD) -> verify removal
5. EC-5 (Template sync) -> verify after copy

---

## Implementation Plan

### Task 1: Replace DoD with Eval Criteria in solution-architect
**Type:** code
**Files:**
  - modify: `template/.claude/agents/bug-hunt/solution-architect.md`
  - modify: `.claude/agents/bug-hunt/solution-architect.md`
**Acceptance:**
  - Lines 91-96 replaced with Eval Criteria template from Design section
  - Table has columns: ID, Finding, Scenario, Expected Behavior, Priority
  - Coverage Summary section present with "min 3, one per finding + regression"
  - No "Definition of Done" section remains
  - Root .claude/ copy identical to template

### Execution Order
1

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass

### Technical
- [ ] No regressions
- [ ] All files < 400 LOC

---

## Autopilot Log
[Auto-populated by autopilot during execution]
