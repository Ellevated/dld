---
name: coder
description: Write/modify code for autopilot tasks
agent: .claude/agents/coder.md
---

# Coder Skill (Wrapper)

Invokes coder subagent for writing/modifying code within a single task.

> **Architecture:** This skill is a WRAPPER over `.claude/agents/coder.md`.
> The agent file is the source of truth for the coder prompt.

## When to Use

**Internal:** Called by autopilot for each task in implementation plan

**Standalone:** Rarely used directly — prefer using autopilot workflow

## Invocation

```yaml
Task tool:
  description: "Implement task N"
  subagent_type: "coder"
  prompt: |
    TASK: {task description from plan}
    ALLOWED FILES: {from spec}

    Execute and report files_changed: [list]
```

## Output

```yaml
files_changed:
  - path/to/file1.py
  - path/to/file2.py
status: completed | blocked
```

## Module Headers

Follow the convention **where the surrounding files already use it**. If the directory you
are editing carries module headers, a file you add or substantially change gets one, and
one you touch keeps its `Uses` / `Used by` accurate. If it does not, adding one imports a
convention the file does not use.

Never fill in a header on a file you were not otherwise changing — that is documenting code
you did not touch, which `@_shared/minimal-code.md` rules out.

### Module Header Format

```python
"""
Module: {module_name}
Role: {one-line purpose}
Source of Truth: {what is authoritative — SQL RPC, this file, etc.}

Uses:
  - {module}: {what classes/functions}

Used by:
  - {module}: {for what purpose}

Why here: {context if non-obvious}
"""
```

Add a `Glossary:` line only in a project that has `ai/glossary/`.

## Post-Change Verification (MANDATORY)

After modifying a file:

1. If changed term/naming:
   ```bash
   grep -rn "{old_term}" . --include="*.py" --include="*.sql" --include="*.ts"
   ```
   Result must be 0.

2. If changed API/signature:
   ```bash
   grep -rn "{function_name}" . --include="*.py"
   ```
   All calls updated?

3. If added new term, and the project keeps a glossary:
   → Add it to `ai/glossary/{domain}.md`. No glossary, nothing to update.

## Notes

- Coder MUST respect File Allowlist from spec
- Coder MUST use Edit/Write tools, not Bash
- Coder outputs only file paths, not implementation details
