# Tech: [TECH-087] Simplify Bug Hunt — Remove Embedded Framework Agents

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-15

## Problem

Bug Hunt pipeline has TOC + TRIZ agents (Step 3) that operate at the wrong abstraction level. They receive code-level findings and try to build system-level analysis. Round 4 data: +20% findings at 2x cost. The Framework Analysis gate in validator creates a 4-attempt recovery ladder that adds complexity without proportional value.

TOC/TRIZ will be moved to a dedicated `/triz` skill (FTR-088) where they get proper system-level inputs.

## What Changes

### Remove from pipeline
- Step 3 (TOC + TRIZ parallel launch) — removed entirely
- Framework Analysis gate in validator — removed
- Recovery ladder (4 attempts) — removed
- Framework Analysis section in spec template — removed
- `## Framework Analysis` requirement in spec-assembler — removed

### Renumber steps
```
BEFORE (8 steps):              AFTER (6 steps):
Step 0: Scope Decomposer      Step 0: Scope Decomposer
Step 1: 6 Personas x N zones  Step 1: 6 Personas x N zones
Step 2: Findings Collector     Step 2: Findings Collector
Step 3: TOC + TRIZ (REMOVE)    --- removed ---
Step 4: Spec Assembler         Step 3: Spec Assembler (simplified)
Step 5: Validator              Step 4: Validator (simplified)
Step 6: Report Updater         Step 5: Report Updater
Step 7: Solution Architects    Step 6: Solution Architects
```

### Simplify spec-assembler
- Input: only FINDINGS_FILE (no more TOC_FILE, TRIZ_FILE)
- Template: no `## Framework Analysis` section
- Simpler, fewer failure modes

### Simplify validator
- Remove structural gate for Framework Analysis
- Remove entire recovery ladder (was only needed for missing Framework Analysis)
- Keep: relevance filtering, dedup, grouping — unchanged

## Impact

- Pipeline cost: -$3-5 per run (2 fewer opus agents)
- Pipeline complexity: -30% (no recovery ladder, simpler spec template)
- Pipeline reliability: higher (fewer steps = fewer failure points)
- Bug finding quality: unchanged (personas are the primary mechanism)

## Allowed Files
1. `.claude/agents/bug-hunt/orchestrator.md` — remove Step 3, renumber 4-7 to 3-6
2. `.claude/agents/bug-hunt/spec-assembler.md` — remove TOC/TRIZ inputs, simplify template
3. `.claude/agents/bug-hunt/validator.md` — remove Framework Analysis gate, remove recovery ladder ref
4. `.claude/skills/spark/bug-mode.md` — update pipeline overview, step table, report template, checklist
5. `.claude/skills/spark/completion.md` — verify no Framework Analysis references
6. `template/.claude/agents/bug-hunt/orchestrator.md` — mirror
7. `template/.claude/agents/bug-hunt/spec-assembler.md` — mirror
8. `template/.claude/agents/bug-hunt/validator.md` — mirror
9. `template/.claude/skills/spark/bug-mode.md` — mirror

### Files to DELETE (agents no longer used in pipeline)
10. `.claude/agents/bug-hunt/toc-analyst.md` — moves to /triz skill (FTR-088)
11. `.claude/agents/bug-hunt/triz-analyst.md` — moves to /triz skill (FTR-088)
12. `template/.claude/agents/bug-hunt/toc-analyst.md` — mirror
13. `template/.claude/agents/bug-hunt/triz-analyst.md` — mirror

**Note:** Don't delete yet if FTR-088 not done — just remove references from orchestrator.

## Definition of Done
- [ ] Orchestrator has 6 steps (0-6), no Step 3 framework launch
- [ ] Spec-assembler reads only FINDINGS_FILE
- [ ] Validator has no Framework Analysis gate
- [ ] Recovery ladder removed from orchestrator
- [ ] Report template has no `## Framework Analysis` section
- [ ] Pipeline overview in bug-mode.md updated
- [ ] All changes mirrored in template/
- [ ] No references to toc-analyst or triz-analyst in bug-hunt pipeline files
