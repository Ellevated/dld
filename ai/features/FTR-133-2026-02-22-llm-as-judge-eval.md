# Feature: [FTR-133] LLM-as-Judge Eval Type for Tester Agent

**Status:** done | **Priority:** P2 | **Date:** 2026-02-22

## Why

When features involve LLM interactions (prompt generation, agent behavior, text quality), deterministic tests can't measure output quality. LLM-as-Judge is industry standard (Pydantic, DeepEval, promptfoo all support it). Adding `llm-judge` eval type to specs enables rubric-based quality scoring during autopilot execution.

## Context

- Depends on TECH-130 (Eval Criteria format with `llm-judge` type column)
- Current tester (tester.md:154 LOC) only runs `./test fast` and pytest
- No LLM-based evaluation exists in DLD
- EDD research: 5-dimension scoring (Completeness, Accuracy, Format, Relevance, Safety)
- Industry: Pydantic LLM-as-Judge guide, DeepEval GEval, promptfoo llm-rubric

---

## Scope

**In scope:**
- New `eval-judge` agent (template/.claude/agents/eval-judge.md)
- New `eval-judge.mjs` script — parse Eval Criteria from spec, extract llm-judge entries
- Update tester.md — dispatch eval-judge for llm-judge criteria
- Update subagent-dispatch.md and model-capabilities.md

**Out of scope:**
- Agent prompt eval suite (FTR-134)
- Deterministic eval running (already works via `./test`)
- Custom eval metrics beyond 5-dimension scoring

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] Tester agent — will dispatch eval-judge
- [x] Task loop Step 2 — consumes tester output

### Step 2: DOWN — what depends on?
- [x] Eval Criteria format from TECH-130
- [x] Spec files in ai/features/ with llm-judge entries

### Step 3: BY TERM
- [x] `llm-judge` — new term, not in codebase
- [x] `eval-judge` — new agent name
- [x] `subagent_type` — subagent-dispatch.md

### Step 4: CHECKLIST
- [x] No test files affected

### Verification
- [x] All files added to Allowed Files

---

## Allowed Files

1. `template/.claude/agents/eval-judge.md` — NEW: judge agent
2. `template/.claude/scripts/eval-judge.mjs` — NEW: spec parser
3. `template/.claude/agents/tester.md` — add eval criteria testing section
4. `template/.claude/skills/autopilot/subagent-dispatch.md` — add eval-judge
5. `template/.claude/rules/model-capabilities.md` — add effort routing row

**Sync after:**
- All 5 files → .claude/

---

## Environment
nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: Standalone eval-judge agent via Task tool (Selected)
Tester dispatches eval-judge agent for each llm-judge criterion. Agent returns structured score.
**Pros:** Uses existing subagent pattern, model routing, no raw API calls
**Cons:** Cost per eval (sonnet call)

### Approach 2: Inline evaluation in tester
Tester itself acts as judge using system prompt.
**Pros:** No new agent
**Cons:** Tester is sonnet/medium effort — judging needs higher effort, mixed responsibilities

### Selected: 1
**Rationale:** Separation of concerns. Judge = dedicated agent with rubric focus.

---

## Design

### eval-judge.md Agent (~75 LOC)

```yaml
model: sonnet
effort: high
tools: Read
```

Input: criterion_id, input, actual_output, rubric, threshold
Process: Score on 5 dimensions (0.0-1.0 each)
Output: `{criterion_id, score, pass, dimensions, reasoning}`

### eval-judge.mjs Script (~80 LOC)

```bash
node .claude/scripts/eval-judge.mjs <spec_path> --type llm-judge
# Output: JSON array of eval criteria objects with type=llm-judge
```

Parses `## Eval Criteria` section, filters for `llm-judge` type rows, returns structured JSON.

### Tester Integration

New section in tester.md after Smart Testing:

```markdown
## Eval Criteria Testing

When spec has ## Eval Criteria with llm-judge entries:
1. Parse: node eval-judge.mjs {spec_path} --type llm-judge
2. For each criterion:
   - Run feature input through implementation
   - Capture actual output
   - Dispatch eval-judge agent with rubric + threshold
3. Include results in tester output
```

---

## Implementation Plan

### Task 1: Create eval-judge.md agent
**Type:** code
**Files:** create: `template/.claude/agents/eval-judge.md`
**Pattern:** Standard agent frontmatter + 5-dimension scoring rubric
**Acceptance:** Agent prompt is < 75 LOC, has clear input/output format

### Task 2: Create eval-judge.mjs script
**Type:** code
**Files:** create: `template/.claude/scripts/eval-judge.mjs`
**Pattern:** Parse markdown tables, extract EC rows with type=llm-judge, output JSON
**Acceptance:** `node eval-judge.mjs sample-spec.md --type llm-judge` returns JSON array

### Task 3: Update tester.md
**Type:** code
**Files:** modify: `template/.claude/agents/tester.md`
**Pattern:** Add "## Eval Criteria Testing" section after line 31
**Acceptance:** Tester has instructions for dispatching eval-judge

### Task 4: Update dispatch + capabilities
**Type:** code
**Files:** modify: `template/.claude/skills/autopilot/subagent-dispatch.md`, `template/.claude/rules/model-capabilities.md`
**Pattern:** Add eval-judge row to both tables
**Acceptance:** eval-judge listed in agent tables

### Task 5: Sync template -> .claude/
**Type:** code
**Files:** sync all modified files
**Acceptance:** Files identical

### Execution Order
1 -> 2 -> 3 -> 4 -> 5

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | eval-judge.mjs parses spec | Spec with 2 llm-judge EC rows | JSON array with 2 objects | deterministic | user requirement | P0 |
| EC-2 | eval-judge.mjs filters by type | Spec with mixed types | Only llm-judge rows returned | deterministic | design | P0 |
| EC-3 | eval-judge.mjs handles no matches | Spec with only deterministic ECs | Empty JSON array | deterministic | edge case | P1 |

### LLM-Judge Assertions

| ID | Input | Rubric | Threshold | Source | Priority |
|----|-------|--------|-----------|--------|----------|
| EC-4 | "Explain how authentication works in this app" | Response is technically accurate, uses project terminology, no hallucinations, < 200 words | 0.7 | EDD research | P1 |

### Coverage Summary
- Deterministic: 3 | Integration: 0 | LLM-Judge: 1 | Total: 4

### TDD Order
1. EC-1, EC-2, EC-3 -> script parsing
2. EC-4 -> end-to-end judge flow

---

## Definition of Done

### Functional
- [ ] eval-judge agent exists with 5-dimension scoring
- [ ] eval-judge.mjs parses specs and extracts llm-judge criteria
- [ ] Tester agent dispatches eval-judge for llm-judge entries

### Tests
- [ ] All eval criteria pass
- [ ] No regressions

### Technical
- [ ] All files < 400 LOC
- [ ] Template files synced to .claude/

---

## Autopilot Log
[Auto-populated by autopilot during execution]
