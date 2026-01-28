# TECH-037: Cross-Task Memory Feed (Planner reads Diary)

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-29

## Why

When autopilot runs 10 specs sequentially, task 7 doesn't know about problems from tasks 1-6. If task 3 failed because of pattern X, tasks 4-10 should be aware. Currently planner starts fresh every time with zero memory of recent issues.

Adding diary reading to planner Phase 0 creates a feedback loop: problems captured → planner reads them → avoids repeating them.

## Context

Research sources (Jan 2026):
- Reflexion pattern: persistent memory across trials feeds into next iteration
- A-Mem (NeurIPS 2025): dynamic memory organization for evolving agent context
- LangGraph LoopAgent: state management carries across iterations

Current planner: `Context → Read Spec → Drift Check → Research → Codebase → Think → Generate`
Target: `Context + **Diary Memory** → Read Spec → Drift Check → Research → Codebase → Think → Generate`

---

## Scope

**In scope:**
- Add diary reading to planner Phase 0
- Read last 5-10 diary entries from index
- Extract warnings relevant to current task (matching files, patterns, libraries)
- Feed warnings into planning as constraints

**Out of scope:**
- Changing diary format (separate TECH-038)
- Semantic search over diary (simple grep/read is enough)
- Auto-applying diary learnings to specs

## Impact Tree Analysis

### Step 1: UP — who uses?
- `planner.md` is invoked by autopilot via subagent-dispatch.md

### Step 2: DOWN — what depends on?
- Planner reads: spec file, Allowed Files, architecture.md, dependencies.md
- New: will also read `ai/diary/index.md` and recent entries

### Step 3: BY TERM
- `planner` referenced in subagent-dispatch.md, planner/SKILL.md

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/agents/planner.md` — add diary reading to Phase 0

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### Diary Memory in Phase 0

Add to planner Phase 0 (Load Project Context), after existing context loading:

```markdown
**Load recent diary (cross-task memory):**
1. Read `ai/diary/index.md`
2. Find last 5 entries with status `pending` (most recent problems)
3. For each entry:
   - Does it mention files in our Allowed Files? → HIGH relevance
   - Does it mention same libraries/patterns? → MEDIUM relevance
   - Unrelated? → SKIP
4. For HIGH/MEDIUM entries, read full diary file
5. Extract constraints:
   - "Pattern X caused failure in TECH-YYY → avoid or handle explicitly"
   - "Library Y has known issue Z → check before using"

Use constraints in Phase 3 (Ultrathink) Risk Assessment.
```

**Key design decision:** Read index only (lightweight), deep-read only relevant entries. No semantic search needed — file/library name matching is sufficient.

## Implementation Plan

### Task 1: Add Diary Memory to Planner Phase 0

**Type:** code
**Files:**
- Modify: `.claude/agents/planner.md`

**What to do:**
Add to Phase 0 (after existing context loading, before Phase 1):

```markdown
**Load recent diary (cross-task memory):**
1. Read `ai/diary/index.md` — find last 5 pending entries
2. Check relevance: match files/libraries against current spec's Allowed Files
3. For relevant entries: read full diary file, extract warnings
4. Feed warnings into Phase 3 Risk Assessment as known constraints

If `ai/diary/index.md` doesn't exist → skip (no diary yet).
```

Add to Phase 3 (Ultrathink) a new section:
```markdown
**Known Issues (from diary):**
- {constraint from diary entry}
- {constraint from diary entry}
```

**Acceptance:**
- Phase 0 includes diary reading step
- Phase 3 has "Known Issues" section
- Graceful skip if no diary exists

### Execution Order

Task 1 (single task)

---

## Definition of Done

### Functional
- [ ] Planner Phase 0 reads diary index
- [ ] Relevance matching works (file/library name matching)
- [ ] Known issues feed into Phase 3 Risk Assessment
- [ ] Graceful skip when no diary exists

### Technical
- [ ] No regressions in planner flow

## Autopilot Log
