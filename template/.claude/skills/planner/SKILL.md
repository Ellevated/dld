---
name: planner
description: Detailed implementation planning with UltraThink - creates bite-sized tasks with full code examples
agent: .claude/agents/planner.md
---

# Planner Skill (Internal Subagent)

Validates spec against current codebase, verifies solutions via Exa, produces executable tasks.

> **Architecture v3.4:** Plan is an INTERNAL SUBAGENT called by Autopilot.
> Users don't call this directly — Autopilot ALWAYS invokes Plan in PHASE 1.
> The agent file `.claude/agents/planner.md` is the source of truth.
>
> **ALWAYS runs** — even if spec already has Implementation Plan.
> Specs can be stale (codebase changed since writing).

**⚠️ Status ownership:** Plan does NOT change status. Spark sets `queued`.

## Invocation (by Autopilot only)

Autopilot ALWAYS dispatches Plan agent in PHASE 1:

```yaml
Task tool:
  description: "Plan: validate + refine {TASK_ID}"
  subagent_type: "planner"
  prompt: |
    INPUT:
      SPEC_PATH: {spec_path}
      TASK_ID: {task_id}

    ALWAYS RUN — even if spec already has Implementation Plan.
    Planner re-validates spec against CURRENT codebase state,
    verifies solutions via Exa research, and creates/updates tasks.
```

Plan validates spec, creates/updates `## Detailed Implementation Plan`, does NOT change status.

## What Planner Does (3 core jobs)

1. **Drift Check (MANDATORY)** — ALWAYS runs, classifies drift:
   - `none`: All files exist, no significant changes → continue
   - `light`: Line shifts, renames, file moves → AUTO-FIX references + add Drift Log
   - `heavy`: Files deleted, API incompatible, >50% changed → COUNCIL ESCALATION
2. **Solution Verification** — search Exa to verify proposed approach is still the best
3. **Task Generation** — produce detailed, executable tasks with full code

## Edge Cases

**No spec found:**
```
No feature spec found. Run `spark` first.
```

**Complex feature (>10 tasks):**
Split into phases in plan.

## Pre-flight Check

Before creating plan:

1. **Find spec:** `ai/features/TYPE-XXX-*.md`
2. **Verify status is `queued`** — Spark already set it
3. If status is `draft` → spec is incomplete, ask Spark first

## Output

After plan added/updated in spec, return to Autopilot:

```yaml
status: plan_ready | blocked
tasks_count: N
drift_items: N  # files changed since spec was written
drift_action: none | auto_fix | council_escalation
drift_log_added: true | false
solution_verified: true | false  # Exa confirmed approach
warnings: []
```

**Note:** Plan does NOT change task status. Status was already `queued` (set by Spark).

## Structure Validation (ARCH-211)

When creating tasks, validate LLM-friendly architecture:

### File Count per Task
- Max 3 files modified per task
- If more needed → split into subtasks

### LOC Estimation
For each new file in plan:
- Estimate LOC (count lines in code blocks)
- If > 300 LOC → add note: "Consider splitting"
- If > 400 LOC → MUST split into multiple files (600 for tests)

### Domain Boundary Check
Each task should stay within one domain:
- ✅ Task modifies `src/domains/billing/*.py`
- ⛔ Task modifies both `src/domains/billing/` AND `src/domains/campaigns/`

Exception: cross-domain refactoring tasks (explicitly labeled)

### New File Location
Verify new files go to correct location:
- `src/domains/` for business logic
- `src/infra/` for infrastructure
- `src/shared/` for shared utilities
- NEVER `src/services/`, `src/db/`, `src/utils/`

## Migration Task Template (Git-First)

When task involves SQL migration, agent uses this template:

```markdown
### Task N: Migration — [Description]

**Type:** migration
**Files:**
- Create: `db/migrations/YYYYMMDDHHmmss_description.sql`

**Step 1: Write migration SQL**
[actual SQL]

**Step 2: Validate migration (NO APPLY!)**
```bash
# Use your migration linter: squawk, sqlfluff, etc.
lint db/migrations/*.sql
```

**Step 3: Check for destructive operations**
- [ ] No DROP TABLE/COLUMN/INDEX
- [ ] No TRUNCATE
- [ ] No DELETE FROM

**Step 4: Commit migration file**
⛔ DO NOT apply! CI applies after push.
```

## Output Format

After agent completes, skill reports:

```yaml
status: plan_ready | blocked
tasks_count: N
drift_items: N
drift_action: none | auto_fix | council_escalation
drift_log_added: true | false
solution_verified: true | false
warnings: []
next_step: "Continue autopilot execution"
```
