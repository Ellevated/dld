---
name: diary-recorder
description: "DEPRECATED: Diary entries are now written inline by autopilot (ADR-007). This file is kept as format reference only."
model: sonnet
effort: medium
tools: Read, Write, Edit
---

# Diary Recorder — DEPRECATED

> **Why deprecated:** Subagents can't reliably write files (ADR-007, 0/36 success rate).
> Diary entries are now written inline by autopilot orchestrator in task-loop Step 6.5.
> See: `template/.claude/skills/autopilot/task-loop.md`

## Format Reference

These formats are used by autopilot inline writes and by `/reflect` for reading.

### Index Row (`ai/diary/index.md`)

```
| {YYYY-MM-DD} | {TASK_ID} | {type} | {brief description} | {debug_N} | {files_N} | {status} |
```

**Types:** success, problem, escalation, regression, escaped_defect
**Statuses:** pending, done
**Columns:** debug_N = debug_attempts count, files_N = files_changed count

### Problem Detail File (`ai/diary/{YYYY-MM-DD}-{TASK_ID}-task{N}-problem.md`)

```markdown
# {TASK_ID} Task {N}/{M} — {YYYY-MM-DD}

## Problem
- {auto-detected problem description}

## Context
- Error: {error_message}
- Files: {files_changed}
- Attempts: {what_was_tried}

## TODO for reflection
- Analyze root cause
- Add rule if pattern repeats
```

### Escaped Defect Entry

```markdown
# {TASK_ID} — {YYYY-MM-DD}

## Escaped Defect
- Bug found after merge from {escaped_from}
- Found by: {found_by}

## Context
- Symptom: {error_message}
- Root cause: {brief analysis}
- Files: {files_changed}

## Why Review Missed It
- {what check was missing}

## Action Required
- Add check to prevent recurrence (see ai/diary/escaped-defects.md)
```

## Rules (preserved from original)

- **Minimal** — brief description, not essay
- **Factual** — what happened, not interpretation
- **Readable** — problems in plain language for human review
- **No fix** — just record, don't try to solve
- **Always index** — every entry must have index row
