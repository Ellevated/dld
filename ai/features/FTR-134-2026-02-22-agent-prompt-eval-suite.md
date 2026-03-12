# Feature: [FTR-134] Agent Prompt Eval Suite

**Status:** done | **Priority:** P2 | **Date:** 2026-02-22

## Why

DLD agents are LLM prompts — prompt quality directly determines output quality. Currently there's no way to measure if agent prompts regressed after edits. Industry standard: golden input/output pairs + rubric-based scoring. This skill enables eval-driven prompt development for DLD's own agents.

## Context

- Depends on FTR-133 (eval-judge agent for rubric-based scoring)
- DLD has 22+ agents in `.claude/agents/` — prompts change frequently
- No regression detection for prompt quality changes
- Industry: promptfoo, Pydantic Evals, DeepEval all use golden datasets
- DLD-specific skill (NOT in template — only DLD needs to eval its own agents)
- Per template-sync rule: edit `.claude/` only, don't touch `template/`

---

## Scope

**In scope:**
- New `/eval` skill (`.claude/skills/eval/SKILL.md`)
- New `eval-agents.mjs` script — scans `test/agents/*/`, returns eval task list
- New golden datasets for 3 agents: devil, planner, coder (3 pairs each)
- ADR-012 entry in architecture.md
- CLAUDE.md skills table entry
- Localization triggers in `.claude/rules/localization.md`

**Out of scope:**
- Golden datasets for all 22+ agents (start with 3, expand organically)
- CI integration (manual `/eval` invocation for now)
- Automatic eval on every prompt change (future)

---

## Impact Tree Analysis

### Step 1: UP -- who uses?
- [x] User via `/eval` skill invocation
- [x] skill-writer — can run `/eval` after prompt changes

### Step 2: DOWN -- what depends on?
- [x] eval-judge agent from FTR-133
- [x] Golden datasets in test/agents/

### Step 3: BY TERM
- [x] `eval` — new skill name, check no conflicts
- [x] `eval-agents` — new script name
- [x] `test/agents/` — new directory

### Step 4: CHECKLIST
- [x] No existing test files affected (new directory)

### Verification
- [x] All files added to Allowed Files

---

## Allowed Files

1. `.claude/skills/eval/SKILL.md` — NEW: /eval skill
2. `.claude/scripts/eval-agents.mjs` — NEW: CLI scanner
3. `test/agents/devil/config.json` — NEW: devil eval config
4. `test/agents/devil/golden-001.input.md` — NEW: devil test input
5. `test/agents/devil/golden-001.output.md` — NEW: devil expected output
6. `test/agents/devil/golden-001.rubric.md` — NEW: devil scoring rubric
7. `test/agents/planner/config.json` — NEW: planner eval config
8. `test/agents/planner/golden-001.input.md` — NEW: planner test input
9. `test/agents/planner/golden-001.output.md` — NEW: planner expected output
10. `test/agents/planner/golden-001.rubric.md` — NEW: planner scoring rubric
11. `test/agents/coder/config.json` — NEW: coder eval config
12. `test/agents/coder/golden-001.input.md` — NEW: coder test input
13. `test/agents/coder/golden-001.output.md` — NEW: coder expected output
14. `test/agents/coder/golden-001.rubric.md` — NEW: coder scoring rubric
15. `.claude/rules/architecture.md` — MODIFY: add ADR-012
16. `CLAUDE.md` — MODIFY: add eval to skills table
17. `.claude/rules/localization.md` — MODIFY: add Russian triggers

**No sync needed** — DLD-specific, not in template.

---

## Environment
nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: Skill + CLI scanner + eval-judge dispatch (Selected)
/eval skill orchestrates: CLI scanner finds golden datasets, dispatches eval-judge per pair, aggregates results.
**Pros:** Reuses eval-judge from FTR-133, standard DLD skill pattern, extensible
**Cons:** Cost per eval run (N sonnet calls)

### Approach 2: Pure script-based eval (no skill)
Node.js script that runs evals directly via API.
**Pros:** Faster, cheaper
**Cons:** Bypasses DLD patterns, needs raw API key, no skill UX

### Selected: 1
**Rationale:** Consistent with DLD patterns. Reuses eval-judge agent. Skill UX is important.

---

## Design

### /eval Skill (~120 LOC)

Commands:
- `/eval agents` — run all agent evals
- `/eval agents {name}` — eval single agent
- `/eval report` — summary of last run

Flow:
1. Run `node .claude/scripts/eval-agents.mjs` to get task list
2. For each golden pair:
   a. Read agent prompt from `.claude/agents/{name}.md`
   b. Read `golden-NNN.input.md` as input
   c. Dispatch agent with input (via Task tool)
   d. Capture actual output
   e. Dispatch eval-judge with `golden-NNN.rubric.md` + actual output
3. Aggregate scores per agent
4. Write report to `test/agents/eval-report.md`

### eval-agents.mjs Script (~150 LOC)

```bash
node .claude/scripts/eval-agents.mjs [agent-name]
# Output: JSON array of eval tasks
```

Scans `test/agents/*/`:
- Reads each `config.json` for agent metadata
- Finds `golden-NNN.{input,output,rubric}.md` files
- Returns structured task list

### config.json Format

```json
{
  "agent": "devil",
  "agent_path": ".claude/agents/spark/devil.md",
  "subagent_type": "spark-devil",
  "description": "Spark Devil's Advocate",
  "golden_count": 3
}
```

### Golden Dataset Structure

```
test/agents/{agent}/
  config.json
  golden-001.input.md     # Input context/task for agent
  golden-001.output.md    # Reference output (for human review, not exact match)
  golden-001.rubric.md    # Scoring rubric for eval-judge
  golden-002.input.md
  ...
```

### ADR-012: Eval Criteria over Freeform Tests

| ID | Decision | Date | Reason |
|----|----------|------|--------|
| ADR-012 | Eval Criteria over freeform Tests | 2026-02 | Structured eval criteria (deterministic + llm-judge) provide measurable, repeatable quality gates |

---

## Implementation Plan

### Task 1: Create eval-agents.mjs script
**Type:** code
**Files:** create: `.claude/scripts/eval-agents.mjs`
**Pattern:** Scan test/agents/*/, read config.json, glob golden files, return JSON
**Acceptance:** `node .claude/scripts/eval-agents.mjs` returns JSON array

### Task 2: Create golden datasets (devil, planner, coder)
**Type:** code
**Files:** create: 12 files in `test/agents/{devil,planner,coder}/`
**Pattern:** config.json + 1 golden pair (input/output/rubric) per agent
**Acceptance:** Each agent has config.json + golden-001.{input,output,rubric}.md

### Task 3: Create /eval skill
**Type:** code
**Files:** create: `.claude/skills/eval/SKILL.md`
**Pattern:** Standard skill format, orchestrates eval-agents.mjs + eval-judge dispatch
**Acceptance:** Skill has commands section, orchestration flow, output format

### Task 4: Update architecture.md + CLAUDE.md + localization.md
**Type:** code
**Files:** modify: 3 files
**Pattern:** Add ADR-012 row, eval skill to table, Russian triggers
**Acceptance:** All 3 files updated

### Execution Order
1 -> 2 -> 3 -> 4

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | eval-agents.mjs scans test/agents/ | Directory with 3 agent folders | JSON array with 3 task objects | deterministic | user requirement | P0 |
| EC-2 | eval-agents.mjs filters by agent name | `eval-agents.mjs devil` | JSON array with only devil tasks | deterministic | design | P0 |
| EC-3 | eval-agents.mjs handles missing directory | No test/agents/ | Empty array, no crash | deterministic | edge case | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-4 | Golden dataset exists | /eval agents devil | Report with scores per dimension | integration | design | P1 |

### Coverage Summary
- Deterministic: 3 | Integration: 1 | LLM-Judge: 0 | Total: 4

### TDD Order
1. EC-1, EC-2, EC-3 -> script scanning
2. EC-4 -> end-to-end eval flow

---

## Definition of Done

### Functional
- [ ] /eval skill exists with agents/report commands
- [ ] eval-agents.mjs scans test/agents/ and returns JSON task list
- [ ] 3 agents have golden datasets (devil, planner, coder)

### Tests
- [ ] All eval criteria pass
- [ ] No regressions

### Technical
- [ ] All files < 400 LOC
- [ ] ADR-012 in architecture.md
- [ ] Skill in CLAUDE.md table

---

## Autopilot Log
[Auto-populated by autopilot during execution]
