---
name: planner
description: Detailed implementation planning with UltraThink - creates bite-sized tasks with full code examples
agent: .claude/agents/planner.md
---

# Planner Skill (Internal Subagent)

Transforms feature specs into executable bite-sized tasks.

> **Architecture v3.4:** Plan is an INTERNAL SUBAGENT called by Autopilot.
> Users don't call this directly — Autopilot invokes Plan in PHASE 1.
> The agent file `.claude/agents/planner.md` is the source of truth.

**⚠️ Status ownership:** Plan does NOT change status. Spark sets `queued`.

## Invocation (by Autopilot only)

Autopilot dispatches Plan agent in PHASE 1:

```yaml
Task tool:
  description: "Plan for {TASK_ID}"
  subagent_type: "planner"
  prompt: |
    INPUT:
      SPEC_PATH: {spec_path}
      TASK_ID: {task_id}
```

Plan adds `## Detailed Implementation Plan` to spec but does NOT change status.

## Edge Cases

**No spec found:**
```
No feature spec found. Run `spark` first.
```

**Plan already exists:**
```
Spec already has plan. Options:
1. Run `autopilot` to execute
2. `plan --force` to regenerate
```

**Complex feature (>10 tasks):**
Split into phases in plan.

## Pre-flight Check

Before creating plan:

1. **Find spec:** `ai/features/TYPE-XXX-*.md`
2. **Verify status is `queued`** — Spark already set it
3. If status is `draft` → spec is incomplete, ask Spark first

## Output

After plan added to spec, return to Autopilot:

```yaml
status: plan_added
tasks_count: N
```

**Note:** Plan does NOT change status. Status was already `queued` (set by Spark).

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
warnings: []
next_step: "Run `autopilot` to execute"
```
