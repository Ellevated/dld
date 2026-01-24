# Claude Code Hooks

Hooks intercept Claude Code actions for validation, automation, and guardrails.

## Overview

DLD uses Claude Code hooks to enforce project rules automatically:
- Block dangerous git operations
- Protect immutable test files
- Suggest proper workflows for complex tasks
- Auto-format code after edits

## Configuration

Hooks are configured in `.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [...],
    "PostToolUse": [...],
    "UserPromptSubmit": [...],
    "Stop": [...]
  }
}
```

## Available Hooks

### pre_bash.py

**Trigger:** Before any Bash command

**Purpose:** Block dangerous git operations

**Hard blocks (no override):**
- `git push ... main` — Use PR workflow instead
- `git clean -fd` — Destroys untracked files from parallel agents
- `git reset --hard` — Wipes uncommitted work
- `git push -f ... develop/main` — Protected branches

**Soft blocks (ask confirmation):**
- `git merge` without `--ff-only` — Suggests rebase-first workflow

---

### pre_edit.py

**Trigger:** Before Edit/Write operations

**Purpose:** Protect files and enforce limits

**Hard blocks:**
- Files in `tests/contracts/` or `tests/regression/` — Immutable tests
- Files not in spec's `## Allowed Files` — File allowlist enforcement

**Soft blocks:**
- Files approaching LOC limits (400 code / 600 tests)

**Spec detection:**
- Uses `CLAUDE_CURRENT_SPEC_PATH` env var
- Falls back to branch name inference (`feature/FTR-XXX` → `ai/features/FTR-XXX*.md`)

---

### post_edit.py

**Trigger:** After Edit/Write on Python files

**Purpose:** Auto-formatting and linting

**Actions:**
- Runs `ruff format` on modified Python files
- Shows lint warnings (non-blocking)

**Requirements:**
- `ruff` must be installed (`pip install ruff`)

---

### prompt_guard.py

**Trigger:** On user prompt submission

**Purpose:** Suggest proper workflows for complex tasks

**Soft blocks:**
- Complex feature requests without `/spark` or `/autopilot`

**Detection patterns:**
- "create new feature", "implement X", "add endpoint"
- Russian equivalents: "создай фичу", "добавь api"

**Skips if:**
- User already typed `/spark`, `/autopilot`, `/audit`, etc.

---

### session-end.sh

**Trigger:** When Claude Code session ends

**Purpose:** Cleanup and logging

---

### validate-spec-complete.sh

**Trigger:** Before bash commands (via PreToolUse)

**Purpose:** Ensure spec files are complete before execution

---

### utils.py

**Purpose:** Shared utilities for all hooks

**Key functions:**
- `allow_tool()` — Allow the operation
- `deny_tool(reason)` — Block with message
- `ask_tool(question)` — Ask user for confirmation
- `get_tool_input()` — Get input parameters for current tool
- `is_file_allowed(file_path)` — Check against spec allowlist
- `infer_spec_from_branch()` — Get spec path from git branch

## Hook Protocol

Hooks communicate via JSON to stdout:

```json
// Allow
{"allow": true}

// Deny
{"allow": false, "reason": "Explanation"}

// Ask user
{"allow": false, "ask": true, "question": "Continue?"}
```

## Creating Custom Hooks

1. Create new Python/Bash file in `.claude/hooks/`
2. Import utilities: `from utils import allow_tool, deny_tool, ask_tool`
3. Read input: `hook_input = read_hook_input()`
4. Process and output decision
5. Add to `.claude/settings.json` hooks section

**Example custom hook:**

```python
#!/usr/bin/env python3
"""Custom hook: block edits on Fridays."""

import datetime
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import allow_tool, ask_tool, read_hook_input

def main():
    read_hook_input()  # Required even if unused

    if datetime.datetime.now().weekday() == 4:
        ask_tool("It's Friday! Are you sure you want to make changes?")
    else:
        allow_tool()

if __name__ == "__main__":
    main()
```

## Debugging

Hook errors are logged to `/tmp/claude-hook-errors.log`.

To test a hook manually:

```bash
echo '{"tool_input": {"command": "git push origin main"}}' | python3 .claude/hooks/pre_bash.py
```
