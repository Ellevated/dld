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

## Module Headers Workflow (MANDATORY)

When working with a file:

1. OPENED → read module header
2. Header empty? → create before changes
3. MADE changes
4. RE-READ header → update if needed (Uses, Used by, Role)
5. SAVED

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

Glossary: ai/glossary/{domain}.md
"""
```

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

3. If added new term:
   → Add to corresponding ai/glossary/{domain}.md

## Notes

- Coder MUST respect File Allowlist from spec
- Coder MUST use Edit/Write tools, not Bash
- Coder outputs only file paths, not implementation details
