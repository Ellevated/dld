# Feature: [BUG-099] Observability & Diagnostic Visibility for Hooks

**Status:** done | **Priority:** P1 | **Date:** 2026-02-17

## Why

When hooks misbehave, there's no way to diagnose the problem. Current logging is limited to `logHookError()` which only captures exceptions to `~/.cache/dld/hook-errors.log`. Normal hook decisions (allow/deny/ask) are invisible. Debugging hook issues requires reading source code and guessing.

## Context

- 8 hooks, each makes decisions that affect Claude Code behavior
- `logHookError()` exists but only fires on catch blocks
- No debug mode, no decision tracing, no timing info
- Hook stdout is reserved for protocol (JSON decisions) — can't use it for logging
- ADR-004: hooks must never crash, so debug logging must also be fail-safe
- Previous bug fixes (BUG-102-120) would have been faster with observability

---

## Scope

**In scope:**
- Debug mode via environment variable `DLD_HOOK_DEBUG=1`
- Decision logging to stderr (doesn't interfere with stdout protocol)
- Structured log format: hook name, input summary, decision, reason, timing
- Debug log file when `DLD_HOOK_LOG_FILE` is set

**Out of scope:**
- Metrics collection / telemetry
- Dashboard or UI for hook logs
- Structured logging library (use console.error for simplicity)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

1. `template/.claude/hooks/utils.mjs` — add debug logger functions
2. `template/.claude/hooks/pre-bash.mjs` — add debug tracing to main()
3. `template/.claude/hooks/pre-edit.mjs` — add debug tracing to main()
4. `template/.claude/hooks/prompt-guard.mjs` — add debug tracing to main()
5. `template/.claude/hooks/validate-spec-complete.mjs` — add debug tracing
6. `template/.claude/hooks/post-edit.mjs` — add debug tracing to main()
7. `template/.claude/hooks/session-end.mjs` — add debug tracing to main()
8. `template/.claude/hooks/run-hook.mjs` — add timing wrapper

**FORBIDDEN:** All other files.

---

## Environment

nodejs: true
docker: false
database: false

---

## Approaches

### Approach 1: stderr-based debug logger (Selected)

**Summary:** Add a `debugLog()` function to utils.mjs that writes to stderr when `DLD_HOOK_DEBUG=1`. Each hook calls `debugLog()` at decision points. Zero overhead when disabled (early return on env check).

**Pros:**
- stderr doesn't interfere with hook stdout protocol
- Zero overhead when disabled (env check is O(1))
- No dependencies
- Grep-friendly structured format

**Cons:**
- stderr may be swallowed by Claude Code (but visible when running hooks manually)

### Approach 2: File-based debug log

**Summary:** Always write debug info to a rotating log file.

**Pros:** Persistent, always available
**Cons:** File I/O on every hook call, disk space concerns, more complex

### Selected: 1

**Rationale:** stderr is the standard debug channel. When `DLD_HOOK_DEBUG=1` is set, user explicitly wants debug output. File logging is opt-in via `DLD_HOOK_LOG_FILE`.

---

## Design

### Debug Logger API

```javascript
// utils.mjs additions
const DEBUG = process.env.DLD_HOOK_DEBUG === '1';
const LOG_FILE = process.env.DLD_HOOK_LOG_FILE || null;

export function debugLog(hookName, event, data = {}) {
  if (!DEBUG) return;
  const entry = {
    ts: new Date().toISOString(),
    hook: hookName,
    event,
    ...data,
  };
  const line = JSON.stringify(entry);
  try {
    process.stderr.write(line + '\n');
    if (LOG_FILE) {
      writeFileSync(LOG_FILE, line + '\n', { flag: 'a' });
    }
  } catch {
    // fail-safe: debug logging must never crash hook
  }
}

export function debugTiming(hookName) {
  if (!DEBUG) return { end: () => {} };
  const start = performance.now();
  return {
    end: (decision) => {
      const ms = (performance.now() - start).toFixed(1);
      debugLog(hookName, 'complete', { decision, ms });
    },
  };
}
```

### Usage in hooks

```javascript
// pre-bash.mjs
import { debugLog, debugTiming } from './utils.mjs';

function main() {
  const timer = debugTiming('pre-bash');
  try {
    const data = readHookInput();
    const command = getToolInput(data, 'command') || '';
    debugLog('pre-bash', 'input', { command: command.slice(0, 100) });

    // ... existing logic ...

    if (blocked) {
      debugLog('pre-bash', 'deny', { pattern: matcher.toString(), command: command.slice(0, 100) });
      timer.end('deny');
      denyTool(message);
      return;
    }

    debugLog('pre-bash', 'allow');
    timer.end('allow');
    allowTool();
  } catch (e) {
    timer.end('error');
    logHookError('pre_bash', e);
    allowTool();
  }
}
```

### Log Format

```jsonl
{"ts":"2026-02-17T10:00:00.000Z","hook":"pre-bash","event":"input","command":"git push origin develop"}
{"ts":"2026-02-17T10:00:00.005Z","hook":"pre-bash","event":"allow"}
{"ts":"2026-02-17T10:00:00.005Z","hook":"pre-bash","event":"complete","decision":"allow","ms":"5.2"}
```

---

## Implementation Plan

### Task 1: Add debug logger to utils.mjs

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/utils.mjs`
**Acceptance:**
  - `debugLog(hookName, event, data)` exported
  - `debugTiming(hookName)` exported
  - No-op when `DLD_HOOK_DEBUG` is not set
  - Writes to stderr when enabled
  - Writes to file when `DLD_HOOK_LOG_FILE` is set
  - Wrapped in try/catch (fail-safe)

### Task 2: Add debug tracing to pre-bash and pre-edit

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/pre-bash.mjs`
  - modify: `template/.claude/hooks/pre-edit.mjs`
**Acceptance:**
  - Each hook logs: input summary, decision, timing
  - pre-bash: logs command (truncated to 100 chars) and which pattern matched
  - pre-edit: logs file path, LOC count, decision reason
  - Zero behavior change when debug disabled

### Task 3: Add debug tracing to remaining hooks

**Type:** code
**Files:**
  - modify: `template/.claude/hooks/prompt-guard.mjs`
  - modify: `template/.claude/hooks/validate-spec-complete.mjs`
  - modify: `template/.claude/hooks/post-edit.mjs`
  - modify: `template/.claude/hooks/session-end.mjs`
  - modify: `template/.claude/hooks/run-hook.mjs`
**Acceptance:**
  - All hooks log input + decision + timing when debug enabled
  - run-hook.mjs logs which hook file is being loaded and timing
  - Zero behavior change when debug disabled

### Task 4: Tests for debug logging

**Type:** test
**Files:**
  - modify: `template/.claude/hooks/__tests__/utils.test.mjs` (if BUG-097 done)
  - OR create: `template/.claude/hooks/__tests__/debug.test.mjs`
**Acceptance:**
  - debugLog writes to stderr when DLD_HOOK_DEBUG=1
  - debugLog is no-op when DLD_HOOK_DEBUG is unset
  - debugTiming measures elapsed time
  - All tests pass

### Execution Order

1 → 2 → 3 → 4

---

## Tests (MANDATORY)

### What to test
- [ ] debugLog no-op when DLD_HOOK_DEBUG unset
- [ ] debugLog writes JSON to stderr when enabled
- [ ] debugTiming returns elapsed ms
- [ ] File logging works when DLD_HOOK_LOG_FILE set
- [ ] Hooks still produce correct protocol output with debug enabled

### How to test
- Unit: test debugLog/debugTiming functions directly
- Integration: spawn hook with DLD_HOOK_DEBUG=1, capture stderr

### TDD Order
1. Write debug logger → test → 2. Add tracing to hooks → integration test

---

## Definition of Done

### Functional
- [ ] `DLD_HOOK_DEBUG=1` enables debug output on all 7 hooks
- [ ] Debug output is structured JSON on stderr
- [ ] `DLD_HOOK_LOG_FILE=/path` writes debug log to file
- [ ] Zero overhead when disabled

### Tests
- [ ] Debug logger unit tests pass
- [ ] Integration test: hook with debug enabled still produces correct output

### Technical
- [ ] No new dependencies
- [ ] All hooks remain fail-safe (ADR-004)
- [ ] LOC limits respected (utils.mjs must stay under 400 LOC)

---

## Autopilot Log
[Auto-populated by autopilot during execution]
