# 001: Windows Hooks Compatibility Fix

**Date:** 2026-01-27
**Type:** problem
**Status:** done
**Project:** MeMyselfAndI (but applies to ALL DLD projects on Windows)

---

## Problem

Claude Code hooks, originally configured on Mac, broke after transferring to Windows:
- `PreToolUse:Bash hook error`
- `Stop hook error: Failed with non-blocking status code: No stderr output`

## Root Causes

### 1. CRLF Line Endings
Windows creates files with CRLF (`\r\n`), but bash scripts require LF (`\n`).
```bash
# Check for CRLF:
cat -A script.sh  # ^M$ = CRLF, $ = LF (correct)

# Fix:
sed -i 's/\r$//' script.sh
```

### 2. `python3` vs `python`
On Windows (Git Bash/MSYS), Python is called `python`, not `python3`.
```json
// Wrong:
"command": "python3 .claude/hooks/hook.py"

// Correct:
"command": "python .claude/hooks/hook.py"
```

### 3. `/tmp/` Path
Unix `/tmp/` doesn't exist on Windows. Use `tempfile.gettempdir()`.
```python
# Wrong:
with open("/tmp/log.txt", "a") as f:

# Correct:
import tempfile
log_path = os.path.join(tempfile.gettempdir(), "log.txt")
```

### 4. `startswith("/")` for Absolute Paths
On Windows, paths start with drive letters (`D:\`), not `/`.
```python
# Wrong:
if file_path.startswith("/"):

# Correct:
if os.path.isabs(file_path):
```

### 5. `grep -c` Exit Code Bug
`grep -c` returns exit code 1 when count is 0, triggering `|| echo "0"` and producing "0\n0".
```bash
# Wrong:
count=$(grep -c "pattern" file 2>/dev/null || echo "0")

# Correct:
count=$(grep -c "pattern" file 2>/dev/null)
echo "${count:-0}"
```

### 6. Bash vs Python for Cross-Platform
Bash scripts have many Windows quirks. **Solution:** Use Python for all hooks.

## Solution Applied

Converted ALL bash hooks to Python:

| Original | Replacement |
|----------|-------------|
| `session-end.sh` | `session-end.py` |
| `validate-spec-complete.sh` | `validate-spec-complete.py` |

Updated `settings.json`:
```json
{
  "hooks": {
    "Stop": [{
      "hooks": [{
        "type": "command",
        "command": "python .claude/hooks/session-end.py"
      }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [
        { "command": "python .claude/hooks/pre_bash.py" },
        { "command": "python .claude/hooks/validate-spec-complete.py" }
      ]
    }]
  }
}
```

## Rule for Future

**When creating hooks for DLD projects:**
1. ALWAYS use Python, not bash
2. Use `os.path.isabs()` instead of `startswith("/")`
3. Use `tempfile.gettempdir()` instead of `/tmp/`
4. Use `python` not `python3` in commands
5. Test on both Mac and Windows before committing

## Files Changed

- `.claude/hooks/session-end.py` (new)
- `.claude/hooks/validate-spec-complete.py` (new)
- `.claude/hooks/pre_bash.py` (fixed `/tmp/` path)
- `.claude/hooks/pre_edit.py` (fixed `/tmp/` and `isabs()`)
- `.claude/hooks/prompt_guard.py` (fixed `/tmp/` path)
- `.claude/hooks/post_edit.py` (fixed `/tmp/` path)
- `.claude/settings.json` (updated commands)

## References

- GitHub Issue #10463: "Stop hook error" despite zero output
- Claude Code Hooks Documentation: https://code.claude.com/docs/en/hooks
