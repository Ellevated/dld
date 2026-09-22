---
name: diary-recorder
description: "DEPRECATED: diary entries are written inline by the autopilot loop. Kept as the format reference only."
model: haiku
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

---

<!-- include: _shared/output-conventions.md — generated from .claude/agents/_shared/output-conventions.md by .claude/scripts/expand-agent-includes.mjs; edit the source and re-run -->
# Output Conventions (all agents)

Calibration for Claude Opus 5 / Sonnet 5 defaults. These models write longer,
narrate more, and delegate more eagerly than the models this framework was built for.

## Length

Match the length of what you write — both chat replies and files on disk — to what the
task needs. Cover the substance; do not pad with filler sections, redundant summaries,
restated context, or boilerplate. A report that says everything in half the words is a
better report, not a lazier one.

## Scope

Deliver what was asked, at the scope intended. Make routine judgment calls yourself, and
check in only when different readings of the request would lead to materially different
work. If the request seems mistaken or a better approach exists, say so in a sentence and
continue with the task as asked rather than quietly narrowing, widening, or transforming
it. Finish the whole task, and stop short of actions clearly beyond what was asked.

## Verification

You verify your own work; that is expected and needs no instruction. Do not add extra
verification passes, do not re-read your output to "double-check" it, and never spawn a
subagent to review what you just produced. Deterministic gates (hooks, tests, CI) are the
verification layer — trust them instead of duplicating them in prose.

## Delegation

Delegate to a subagent only for large tasks that are genuinely independent and
parallelizable, such as a wide multi-file investigation. Do not delegate work you can
finish yourself in a handful of tool calls. If one subagent can do it, use one rather
than several.

## Corrections

Only correct an earlier statement when the error would change the reader's code,
conclusions, or decisions. State the correction plainly and move on. For slips that
change nothing, fix and continue without narrating it.
<!-- /include: _shared/output-conventions.md -->
