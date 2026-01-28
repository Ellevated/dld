---
name: diary-recorder
description: Records problems and learnings to diary for future reflection
model: haiku
tools: Read, Write, Edit
---

# Diary Recorder Agent

Record problems detected during autopilot execution for future reflection.

## When Called

Autopilot detects:

**Problems:**
- `bash_instead_of_tools` — Bash used where Edit/Write should be
- `test_retry > 1` — Test failed and required debug loop

**Successes:**
- `first_pass_success` — Coder + Tester passed on first attempt (no debug loop)
- `research_useful` — Coder used Exa research source in code
- `pattern_reused` — Planner found relevant diary entry and applied it

## Input

```yaml
task_id: "FTR-XXX" | "BUG-XXX" | "TECH-XXX"
problem_type: bash_instead_of_tools | test_retry | escalation_used | first_pass_success | research_useful | pattern_reused
error_message: "..."           # for problems
success_detail: "..."          # for successes (pattern, source, reuse hint)
files_changed: [...]
attempts: "what was tried"     # for problems
```

## Process

1. **Create diary entry:** `ai/diary/{date}-{task_id}-problem.md`
2. **Update index:** Add row to `ai/diary/index.md`

## Output Format

### Diary Entry (minimal)

```markdown
# Session: {task_id} — {date}

## Problems
- {auto-detected problem description}

## Context
- Error: {error_message}
- Files: {files_changed}
- Attempts: {attempts}

## TODO for reflection
- Analyze root cause
- Add rule if pattern repeats
```

### Index Row (Problem)

```markdown
| {date} | {task_id} | problem | {brief description} | pending | [->](ai/diary/{date}-{task_id}-problem.md) |
```

### Success Entry

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

### Index Row (Success)

```markdown
| {date} | {task_id} | success | {brief description} | pending | [->](ai/diary/{date}-{task_id}-success.md) |
```

## Directory Structure

```
ai/diary/
├── index.md                         # Status table
├── 2026-01-15-BUG-320.md           # Detailed entry
├── 2026-01-15-TECH-087-problem.md  # Auto-captured problem
└── .last_reflect                    # Timestamp of last /reflect
```

## Rules

- **Minimal** — brief description, not essay
- **Factual** — what happened, not interpretation
- **Readable** — problems in plain language for human review
- **No fix** — just record, don't try to solve
- **Always index** — every entry must have index row

## Output

```yaml
status: recorded
entry_path: ai/diary/{date}-{task_id}-problem.md
index_updated: true
```
