# TECH-038: Diary Records Successes (not just problems)

**Status:** queued | **Priority:** P2 | **Date:** 2026-01-29

## Why

Current diary-recorder only captures problems (bash_instead_of_tools, test_retry, escalation_used). Reflexion pattern teaches: agents learn from BOTH successes and failures. Recording what worked enables:
- Planner can repeat successful patterns
- /reflect can identify "golden paths" (approaches that always work)
- Success frequency data helps prioritize which patterns to enshrine in CLAUDE.md

## Context

Research sources (Jan 2026):
- ReMe framework (NeurIPS 2025): learns from success patterns + failure triggers + comparative insights
- Reflexion pattern: persistent memory stores both positive and negative outcomes
- A-Mem: Zettelkasten-style notes include "what worked" alongside "what failed"

Current diary triggers: `bash_instead_of_tools | test_retry | escalation_used`
Target: add `first_pass_success | research_useful | pattern_reused`

---

## Scope

**In scope:**
- Add 3 new success triggers to diary-recorder
- Add success event detection in autopilot main loop
- Update diary entry format for successes

**Out of scope:**
- Changing diary directory structure
- Complex metrics/analytics
- Auto-generating rules from successes (that's /reflect's job)

## Impact Tree Analysis

### Step 1: UP — who uses?
- `diary-recorder.md` is called by autopilot
- Diary entries read by `/reflect`

### Step 2: DOWN — what depends on?
- Diary-recorder writes to `ai/diary/`
- Reflect reads from `ai/diary/`

### Step 3: BY TERM
- `diary-recorder` referenced in subagent-dispatch.md (dispatch template)

### Verification
- All found files in Allowed Files ✓

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/agents/diary-recorder.md` — add success triggers and format
2. `.claude/skills/autopilot/subagent-dispatch.md` — add success trigger dispatch conditions

**FORBIDDEN:** All other files.

## Environment

nodejs: false
docker: false
database: false

## Design

### New Success Triggers

| Trigger | When | What to Record |
|---------|------|----------------|
| `first_pass_success` | Coder + Tester pass on first attempt (no debug loop) | Which pattern/approach worked, files changed |
| `research_useful` | Coder explicitly used Exa research source in code | Which query found useful result, source URL |
| `pattern_reused` | Planner found relevant diary entry and applied it | Which diary entry helped, how it was applied |

### Detection Logic (in autopilot main loop)

```
After task completes:
  IF tester passed AND debug_attempts == 0:
    → trigger: first_pass_success
    → record: task name, pattern used, files

After coder completes:
  IF coder output references Research Source URL:
    → trigger: research_useful
    → record: query, source URL, how used

After planner completes:
  IF planner output mentions diary constraint:
    → trigger: pattern_reused
    → record: diary entry ID, how applied
```

### Success Entry Format

```markdown
# Session: {task_id} — {date}

## Success
- {auto-detected success description}

## What Worked
- Pattern: {what approach succeeded}
- Files: {files_changed}
- Source: {Exa URL if research_useful}

## Reuse Hint
- {when to apply this pattern again}
```

### Index Row (success)

```markdown
| {date} | {task_id} | success | {brief description} | pending | [->](ai/diary/{date}-{task_id}-success.md) |
```

## Implementation Plan

### Task 1: Add Success Triggers to diary-recorder.md

**Type:** code
**Files:**
- Modify: `.claude/agents/diary-recorder.md`

**What to do:**
1. Add 3 new triggers to "When Called" section: `first_pass_success`, `research_useful`, `pattern_reused`
2. Add new input field: `success_detail` (pattern, source, reuse hint)
3. Add success entry output format (separate from problem format)
4. Add success index row format (type: `success` instead of `problem`)
5. Update Rules section: successes should be brief, factual, and include reuse hint

**Acceptance:**
- 3 new triggers documented
- Success entry format defined
- Index row format includes success type

### Task 2: Add Success Detection to subagent-dispatch.md

**Type:** code
**Files:**
- Modify: `.claude/skills/autopilot/subagent-dispatch.md`

**What to do:**
Add dispatch conditions for success triggers after existing Diary Recorder dispatch template:

```yaml
# Success: first pass (no debug loop)
IF tester passed AND debug_attempts == 0:
  Task tool:
    subagent_type: "diary-recorder"
    prompt: |
      task_id: "{TASK_ID}"
      problem_type: first_pass_success
      success_detail: "Task {N}/{M} passed on first attempt"
      files_changed: [...]
```

Add similar templates for `research_useful` and `pattern_reused`.

**Acceptance:**
- 3 success dispatch conditions added
- Each has clear detection logic
- Dispatch template matches diary-recorder input format

### Execution Order

Task 1 → Task 2

---

## Definition of Done

### Functional
- [ ] diary-recorder has 3 new success triggers
- [ ] Success entry format is defined
- [ ] subagent-dispatch has success detection logic
- [ ] Index row distinguishes success from problem

### Technical
- [ ] No regressions in diary-recorder flow
- [ ] No regressions in autopilot dispatch flow

## Autopilot Log
