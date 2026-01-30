# Feature: [TECH-043] Fix Hooks in Worktrees

**Status:** done | **Priority:** P1 | **Date:** 2026-01-30

## Why

Hooks fail in git worktrees because they use relative paths (`.claude/hooks/...`). When Claude Code runs in `.worktrees/TECH-XXX`, the relative path doesn't resolve — the `.claude/` directory doesn't exist there.

This blocks autopilot workflow: worktree isolation is core to DLD, but broken hooks make it unusable.

## Context

**Error observed:**
```
PreToolUse:Bash hook error
Error: PreToolUse:Bash hook error: [python3 .claude/hooks/pre_bash.py 2>/dev/null]: No stderr output
```

**Root cause:**
1. `settings.json` defines hooks with relative paths:
   ```json
   "command": "python3 .claude/hooks/pre_bash.py 2>/dev/null"
   ```
2. Worktrees (`.worktrees/TECH-XXX/`) don't contain `.claude/` directory
3. Python hooks use `sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))` — fails if file doesn't exist

**Research (Exa):**
- `git rev-parse --show-toplevel` returns main repo root even from worktree
- Pattern: `$(git rev-parse --show-toplevel)/.claude/hooks/` works universally
- Claude Code hooks support shell expansion in commands

---

## Scope

**In scope:**
- Update `settings.json` to use dynamic paths
- Test hooks work in both main repo and worktrees

**Out of scope:**
- Changing hook logic
- Adding new hooks
- Python hook refactoring

---

## Impact Tree Analysis

### Step 1: Files affected
- `.claude/settings.json` — hook commands use relative paths

### Step 2: Dependencies
- All 4 Python hooks: `pre_bash.py`, `pre_edit.py`, `post_edit.py`, `prompt_guard.py`
- 2 Bash hooks: `validate-spec-complete.sh`, `session-end.sh`

### Verification
- [x] All affected files identified

---

## Allowed Files

**ONLY these files may be modified:**
1. `.claude/settings.json` — update hook commands

**FORBIDDEN:** All other files.

---

## Environment

nodejs: false
docker: false
database: false

---

## Approaches

### Approach 1: Dynamic path with git rev-parse

Replace relative paths with:
```json
"command": "python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/pre_bash.py\" 2>/dev/null"
```

**Pros:**
- Works in main repo and all worktrees
- No symlinks or copies needed
- Shell expansion happens at runtime

**Cons:**
- Slightly longer command strings
- Requires git to be available (always true for our use case)

### Approach 2: Symlink .claude in worktrees

Add to worktree setup:
```bash
ln -s "$(git rev-parse --show-toplevel)/.claude" .claude
```

**Pros:**
- No settings.json changes
- Transparent to hooks

**Cons:**
- Requires manual step in worktree creation
- Can cause confusion (which .claude is real?)
- Symlinks may not work on all systems

### Approach 3: Environment variable

Set `DLD_ROOT` in session and use in settings:
```json
"command": "python3 $DLD_ROOT/.claude/hooks/pre_bash.py"
```

**Pros:**
- Clean separation

**Cons:**
- Requires env setup (another failure point)
- Not sure if Claude Code expands env vars in settings.json

### Selected: Approach 1 + Windows fix

Dynamic path with `git rev-parse` + bash wrapper for cross-platform compatibility.

**Windows consideration:**
`git rev-parse --show-toplevel` returns forward slashes on Windows (`C:/Users/...`).
Using `bash -c '...'` wrapper ensures consistent path handling across platforms.

---

## Design

### Current `settings.json` (hooks section):
```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "python3 .claude/hooks/post_edit.py 2>/dev/null",
          "timeout": 15000
        }
      ]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "python3 .claude/hooks/pre_bash.py 2>/dev/null",
          "timeout": 5000
        },
        {
          "type": "command",
          "command": "bash .claude/hooks/validate-spec-complete.sh",
          "timeout": 3000
        }
      ]
    },
    {
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "python3 .claude/hooks/pre_edit.py 2>/dev/null",
          "timeout": 5000
        }
      ]
    }
  ],
  "UserPromptSubmit": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 .claude/hooks/prompt_guard.py 2>/dev/null",
          "timeout": 3000
        }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash .claude/hooks/session-end.sh",
          "timeout": 5000
        }
      ]
    }
  ]
}
```

### New `settings.json` (hooks section):

**Cross-platform approach with bash wrapper:**
```json
"hooks": {
  "PostToolUse": [
    {
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/post_edit.py\"' 2>/dev/null",
          "timeout": 15000
        }
      ]
    }
  ],
  "PreToolUse": [
    {
      "matcher": "Bash",
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/pre_bash.py\"' 2>/dev/null",
          "timeout": 5000
        },
        {
          "type": "command",
          "command": "bash -c 'bash \"$(git rev-parse --show-toplevel)/.claude/hooks/validate-spec-complete.sh\"'",
          "timeout": 3000
        }
      ]
    },
    {
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/pre_edit.py\"' 2>/dev/null",
          "timeout": 5000
        }
      ]
    }
  ],
  "UserPromptSubmit": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'python3 \"$(git rev-parse --show-toplevel)/.claude/hooks/prompt_guard.py\"' 2>/dev/null",
          "timeout": 3000
        }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "bash -c 'bash \"$(git rev-parse --show-toplevel)/.claude/hooks/session-end.sh\"'",
          "timeout": 5000
        }
      ]
    }
  ]
}
```

**Note:** `bash -c '...'` ensures shell expansion works consistently on macOS, Linux, and Windows (WSL/Git Bash).

---

## Implementation Plan

### Task 1: Update settings.json hook paths
**Type:** edit
**Files:** modify `.claude/settings.json`
**Acceptance:**
- [ ] All 6 hook commands use `$(git rev-parse --show-toplevel)` pattern
- [ ] Paths are properly quoted (spaces in paths)
- [ ] No syntax errors in JSON

### Task 2: Test in main repo
**Type:** test
**Acceptance:**
- [ ] All hooks fire correctly
- [ ] No "hook error" messages

### Task 3: Test in worktree
**Type:** test
**Acceptance:**
- [ ] Create worktree: `git worktree add .worktrees/test-hooks -b test/hooks-test`
- [ ] Run Claude Code from worktree
- [ ] Hooks execute without errors
- [ ] Clean up: `git worktree remove .worktrees/test-hooks`

### Execution Order
1 → 2 → 3

---

## Definition of Done

### Functional
- [ ] Hooks work in main repo
- [ ] Hooks work in worktrees
- [ ] No permission prompts or errors

### Technical
- [ ] settings.json is valid JSON
- [ ] All paths use dynamic resolution

---

## Risks

1. **Shell expansion not supported** — Claude Code might not expand `$(...)` in command strings
   - Mitigation: Using `bash -c '...'` wrapper forces shell interpretation
   - Test before merging

2. **Performance** — Running `git rev-parse` for every hook call
   - Mitigation: Command is very fast (<10ms); acceptable overhead

3. **Windows without bash** — Pure Windows (no WSL/Git Bash) won't have `bash`
   - Mitigation: Claude Code on Windows recommends WSL; Git Bash comes with Git for Windows
   - Document requirement in hooks README

---

## Rollback

If dynamic paths don't work:
1. Revert settings.json
2. Document: "Run Claude Code only from main repo root"
3. Consider Approach 2 (symlinks in worktree setup)
