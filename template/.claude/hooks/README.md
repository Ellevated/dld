# Claude Code Hooks

Hooks intercept Claude Code actions for validation, automation, and guardrails.

## Overview

DLD uses Claude Code hooks to enforce project rules automatically:
- Block dangerous git operations
- Protect immutable test files
- Suggest proper workflows for complex tasks
- Auto-format code after edits

**All hooks are Node.js (`.mjs`)** — no Python or Bash dependencies required.

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

All hook commands use the runner: `node .claude/hooks/run-hook.mjs <hook-name>`

## Available Hooks

### pre-bash.mjs

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

### pre-edit.mjs

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

### post-edit.mjs

**Trigger:** After Edit/Write on Python files

**Purpose:** Auto-formatting and linting

**Actions:**
- Runs `ruff format` on modified Python files
- Shows lint warnings (non-blocking)

**Requirements:**
- `ruff` must be installed (`pip install ruff`)

---

### prompt-guard.mjs

**Trigger:** On user prompt submission

**Purpose:** Suggest proper workflows for complex tasks

**Soft blocks:**
- Complex feature requests without `/spark` or `/autopilot`

**Detection patterns:**
- "create new feature", "implement X", "add endpoint"

**Skips if:**
- User already typed `/spark`, `/autopilot`, `/audit`, etc.

---

### session-end.mjs

**Trigger:** When Claude Code session ends

**Purpose:** Soft reminder about pending diary entries

---

### validate-spec-complete.mjs

**Trigger:** Before bash commands (via PreToolUse)

**Purpose:** Ensure Impact Tree checkboxes are filled before git commit

---

### run-hook.mjs

**Purpose:** Cross-platform hook runner with git worktree support

Resolves the main repo root (for worktree support) and dynamically
imports the specified hook. Used as the entry point in settings.json.

---

### utils.mjs

**Purpose:** Shared utilities for all hooks

**Key functions:**
- `allowTool()` — Allow the operation
- `denyTool(reason)` — Block with message
- `askTool(question)` — Ask user for confirmation
- `getToolInput()` — Get input parameters for current tool
- `isFileAllowed(filePath)` — Check against spec allowlist
- `inferSpecFromBranch()` — Get spec path from git branch

## Hook Protocol

Hooks communicate via JSON to stdout:

```json
// Allow (PreToolUse)
// Silent exit (exit code 0, no output)

// Deny (PreToolUse)
{"hookSpecificOutput": {"permissionDecision": "deny", "permissionDecisionReason": "..."}}

// Ask user (PreToolUse)
{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "..."}}

// Approve prompt (UserPromptSubmit)
{"decision": "approve"}

// Block prompt (UserPromptSubmit)
{"decision": "block", "reason": "..."}
```

## Creating Custom Hooks

1. Create new `.mjs` file in `.claude/hooks/`
2. Import utilities: `import { allowTool, denyTool, askTool } from './utils.mjs';`
3. Read input: `const data = readHookInput();`
4. Process and output decision
5. Add to `.claude/settings.json`: `"command": "node .claude/hooks/run-hook.mjs your-hook"`

**Example custom hook:**

```javascript
/**
 * Custom hook: block edits on Fridays.
 */
import { allowTool, askTool, readHookInput } from './utils.mjs';

function main() {
  readHookInput(); // Required even if unused

  if (new Date().getDay() === 5) {
    askTool("It's Friday! Are you sure you want to make changes?");
  } else {
    allowTool();
  }
}

main();
```

## Debugging

Hook errors are logged to `~/.cache/dld/hook-errors.log`.

To test a hook manually:

```bash
echo '{"tool_input": {"command": "git push origin main"}}' | node .claude/hooks/pre-bash.mjs
```

---

## Known Limitations

### API Content Filtering Errors

Some tool calls may fail with "Output blocked by content filtering policy" error from Anthropic API. **Hooks cannot intercept these errors** — they occur after the tool call is made.

**Mitigation:**
- CLAUDE.md contains tool preference rules (use Glob instead of Search, etc.)
- If autopilot encounters this error, it should retry with alternative tool
- See "Tool Preferences (API Error Prevention)" section in CLAUDE.md
