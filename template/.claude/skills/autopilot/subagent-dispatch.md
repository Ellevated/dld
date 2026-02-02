# Subagent Dispatch

How to spawn and manage subagents in autopilot workflow.

**Execution Flow:** See `task-loop.md` for decision trees after each subagent.

## Agent Types

### Internal Agents (called only by Autopilot)

| Agent | subagent_type | Model | When |
|-------|---------------|-------|------|
| Plan | `planner` | opus | PHASE 1 (if no plan) |
| Coder | `coder` | sonnet | PHASE 2 per task |
| Tester | `tester` | sonnet | PHASE 2 per task |
| Debugger | `debugger` | opus | If Tester fails (max 3) |
| Spec Reviewer | `spec-reviewer` | sonnet | PHASE 2 per task |
| Diary Recorder | `diary-recorder` | haiku | On problems detected |

### External Agents (user OR Autopilot)

| Agent | subagent_type | Model | When |
|-------|---------------|-------|------|
| Scout | `scout` | sonnet | Research (optional) |
| Code Quality | `review` | opus | PHASE 2 per task |

**Model SSOT:** Defined in agent frontmatter (`agents/*.md:4`).

## Dispatch Templates

### Plan Subagent

```yaml
Task tool:
  description: "Create detailed plan for {TASK_ID}"
  subagent_type: "planner"
  prompt: |
    INPUT:
      SPEC_PATH: ai/features/{TASK_ID}-*.md
      TASK_ID: {task_id}
```

### Coder Subagent

```yaml
# First, export spec path for hooks
export CLAUDE_CURRENT_SPEC_PATH="ai/features/{TASK_ID}-*.md"

Task tool:
  subagent_type: "coder"
  prompt: |
    task: "Task {N}/{M} — {title}"
    type: {code|test|migrate}
    files:
      create: [{from task "Create:" entries}]
      modify: [{from task "Modify:" entries}]
    pattern: "{Research Source URL if any, else 'none'}"
    acceptance: "{from task acceptance criteria}"
```

### Tester Subagent

```yaml
Task tool:
  subagent_type: "tester"
  prompt: |
    files_changed: [{list}]
    task_scope: "{TASK_ID}: {current task description}"
```

### Debugger Subagent

```yaml
Task tool:
  subagent_type: "debugger"
  prompt: |
    failure:
      test: "{failed_test_name}"
      error: "{traceback}"
    files_changed: [{list}]
    attempt: {debug_attempts}
```

### Spec Reviewer

```yaml
Task tool:
  subagent_type: "spec-reviewer"
  prompt: |
    feature_spec: "ai/features/{TASK_ID}*.md"
    task: "Task {N}/{M} — {title}"
    files_changed:
      - path: "{path}"
        action: "{created|modified}"
```

### Code Quality Reviewer

```yaml
Task tool:
  subagent_type: "review"
  prompt: |
    TASK: {description}
    FILES CHANGED: {list}
```

### Diary Recorder (Problems)

```yaml
Task tool:
  subagent_type: "diary-recorder"
  prompt: |
    task_id: "{TASK_ID}"
    problem_type: {trigger}
    error_message: "{error}"
    files_changed: [...]
```

### Diary Recorder (Successes)

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

# Success: research was useful
IF coder output references Research Source URL:
  Task tool:
    subagent_type: "diary-recorder"
    prompt: |
      task_id: "{TASK_ID}"
      problem_type: research_useful
      success_detail: "Query: {query}, Source: {url}, Used in: {file}"
      files_changed: [...]

# Success: diary pattern reused
IF planner output mentions diary constraint:
  Task tool:
    subagent_type: "diary-recorder"
    prompt: |
      task_id: "{TASK_ID}"
      problem_type: pattern_reused
      success_detail: "Diary entry {entry_id} applied: {how}"
      files_changed: [...]
```

## Task Parsing Algorithm

Before dispatching to CODER, extract values from spec:

**Step 1:** Find current task
```
Read spec → find "## Implementation Plan"
Search for "### Task N:" where N = current task number
```

**Step 2:** Extract TASK description
```
TASK = title + context (first 2-3 sentences)
```

**Step 3:** Extract ALLOWED FILES
```
Find "## Allowed Files" → parse list
Files = [path1, path2, ...]
```

**Step 4:** Extract task-specific files
```
In "### Task N:" section, find "**Files:**"
Parse: "Create:", "Modify:", "Test:" entries
```

## Fresh Subagent Principle

Each task gets FRESH subagents — no shared context pollution!

**Why:**
- Context isolation → errors caught earlier
- No accumulated garbage
- Main context only sees: "Task N: completed, 3 files, tests pass"
- Model routing → cost optimization

**Result:** Subagent context dies after returning to main context.

## Model Routing Rationale

| Model | Use For | Why |
|-------|---------|-----|
| **Opus** | Plan, Debugger, Code Quality | Architecture decisions, root cause analysis |
| **Sonnet** | Coder, Tester, Spec Reviewer | 90% capability, 2x speed, cost-effective |
| **Haiku** | Diary Recorder | Fast, cheap for simple logging |
