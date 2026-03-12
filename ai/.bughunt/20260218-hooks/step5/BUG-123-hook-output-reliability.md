# BUG-123 — Hook Output Reliability

**Priority:** P1
**Group:** Hook Output Reliability
**Findings:** F-009 (outputJson race condition), F-010 (missing EPIPE handler)
**Affected files:**
- `.claude/hooks/utils.mjs` (lines 94–101)

---

## Summary

Two related reliability bugs in `outputJson()` can cause deny/block decisions to be silently lost, turning them into implicit allows. Both are security-critical because every `denyTool()`, `askTool()`, `blockPrompt()`, and `postBlock()` call flows through `outputJson()`.

---

## Root Cause Analysis

### F-009: Race Condition — setTimeout fires before write callback

```javascript
// utils.mjs:94-101 — CURRENT (BROKEN)
function outputJson(data) {
  try {
    process.stdout.write(JSON.stringify(data) + '\n', () => process.exit(0));
  } catch {
    process.exit(0); // pipe closed early — exit anyway
  }
  setTimeout(() => process.exit(0), 500); // safety net  ← can fire first
}
```

**What goes wrong:**

`process.stdout.write()` is non-blocking. Its completion callback (`() => process.exit(0)`) fires only after the data has been flushed to the pipe. The `setTimeout(500ms)` runs concurrently. Under backpressure (slow pipe reader, large JSON payload, or memory pressure), the 500ms timeout can fire before the write callback, terminating the process before the deny JSON is delivered. From Claude Code's perspective, the hook exited without writing a deny response — the operation is allowed.

**Trigger conditions:**
- Slow or congested pipe between hook process and Claude Code
- Large `denyTool` payloads (long reason strings with many files)
- System under memory pressure causing write buffer backpressure

### F-010: Missing EPIPE/SIGPIPE Handler — hook crash = implicit allow

```javascript
// utils.mjs — CURRENT: no stdout error handler anywhere in module
// (no process.stdout.on('error', ...) call exists)
```

**What goes wrong:**

If Claude Code closes the read end of the pipe while the hook is writing (e.g., user cancels, Claude Code exits, or pipe is broken), Node.js emits an unhandled `'error'` event on `process.stdout`. With no `process.stdout.on('error', ...)` handler, this becomes an uncaught exception, crashing the hook with a non-zero exit code and an error stack trace on stderr.

Claude Code receives: hook process exited with non-zero status, no valid JSON on stdout.
Claude Code behavior: treats crashed hook as allow (fail-open). The deny decision is silently lost.

**Trigger conditions:**
- User hits Ctrl+C while a hook is mid-write
- Claude Code process restart while hook write is in flight
- Any broken pipe condition between hook and Claude Code

---

## Affected Files

| File | Line | Role |
|------|------|------|
| `.claude/hooks/utils.mjs` | 94–101 | `outputJson()` — all deny/ask paths |
| `.claude/hooks/utils.mjs` | 109–116 | `denyTool()` calls `outputJson()` |
| `.claude/hooks/utils.mjs` | 118–131 | `askTool()` calls `outputJson()` |
| `.claude/hooks/utils.mjs` | 133–139 | `blockPrompt()` calls `outputJson()` |
| `.claude/hooks/utils.mjs` | 141–147 | `postBlock()` calls `outputJson()` |

All hooks that use deny/ask decisions are affected:
- `.claude/hooks/pre-edit.mjs` (file allowlist enforcement, LOC limits)
- `.claude/hooks/pre-bash.mjs` (git command blocking)
- `.claude/hooks/prompt-guard.mjs` (complexity guard)
- `.claude/hooks/post-edit.mjs` (post-edit blocking)

---

## Fix Description

### Fix 1 — Clear setTimeout in write callback (F-009)

```javascript
// utils.mjs — FIXED
function outputJson(data) {
  // Register EPIPE handler before any write attempt (F-010)
  process.stdout.on('error', () => process.exit(0));

  // Clear the safety-net timeout when the write callback confirms delivery
  const t = setTimeout(() => process.exit(0), 500); // safety net
  try {
    process.stdout.write(JSON.stringify(data) + '\n', () => {
      clearTimeout(t); // write confirmed — cancel the race
      process.exit(0);
    });
  } catch {
    clearTimeout(t);
    process.exit(0); // pipe closed synchronously — exit anyway
  }
}
```

**Key changes:**
1. `const t = setTimeout(...)` — store the handle before write (timing-safe)
2. `clearTimeout(t)` inside write callback — cancels the race condition
3. `clearTimeout(t)` in catch block — prevents dangling timeout on sync throw

### Fix 2 — Add process.stdout EPIPE handler at module top-level (F-010)

```javascript
// utils.mjs — add near top of module, after imports
// Fail-safe: if parent closes pipe while we write, exit cleanly (not crash)
// Without this, EPIPE throws uncaught exception → hook crash → implicit allow (ADR-004)
process.stdout.on('error', () => process.exit(0));
```

**Placement:** Must be at module top-level (not inside `outputJson`) so it is registered before any write is attempted. The handler in `outputJson` shown above is belt-and-suspenders — the top-level registration covers the case where the pipe breaks before `outputJson` is called.

### Why process.exit(0) on EPIPE?

Per ADR-004: hooks are fail-safe infrastructure. A crashed hook with non-zero exit breaks Claude Code. Exit 0 with no stdout output = silent allow, which is the same as what Claude Code would see from a clean no-op hook. This is the least-harm failure mode when the communication channel itself is broken.

---

## Impact Tree

### Upstream (who depends on outputJson being reliable?)
- Every deny decision in every hook
- File allowlist enforcement (`pre-edit.mjs`: spec-based denials)
- LOC limit enforcement (`pre-edit.mjs`: ask on large files)
- Git command blocking (`pre-bash.mjs`: deny destructive git ops)
- Prompt complexity guard (`prompt-guard.mjs`: ask on multi-task prompts)
- Post-edit blocking (`post-edit.mjs`)
- Protected path enforcement (`pre-edit.mjs`)

### Downstream (what does outputJson depend on?)
- `process.stdout` — Node.js built-in, no external deps
- `JSON.stringify` — synchronous, no concerns

### Risk if NOT fixed
- Any deny decision can silently become an allow under pipe pressure
- Hook crashes on EPIPE lose the deny decision entirely
- Security boundary of the hook system is unreliable in degraded environments

---

## Definition of Done

- [ ] `process.stdout.on('error', () => process.exit(0))` added at module top-level in `utils.mjs`
- [ ] `outputJson()` stores `setTimeout` handle and clears it in write callback
- [ ] `outputJson()` clears `setTimeout` handle in catch block
- [ ] Existing tests continue to pass
- [ ] New test: pipe that closes early does not crash hook (exits 0)
- [ ] New test: slow pipe reader does not cause deny→allow race

---

## Test Requirements

```javascript
// Test: EPIPE handler — pipe closes while write in flight
test('outputJson exits cleanly on EPIPE, does not throw', async () => {
  // Spawn hook, immediately close the read side of the pipe
  // Assert: hook exits with code 0 (not non-zero crash)
  // Assert: no unhandled exception on stderr
});

// Test: setTimeout cleared by write callback (no lingering 500ms hang)
test('outputJson does not hang 500ms after successful write', async () => {
  // Measure time from write to process exit
  // Assert: exits in < 100ms when pipe is healthy
});

// Test: deny decision survives slow pipe reader
test('deny decision delivered to slow pipe reader', async () => {
  // Read from pipe with 200ms delay
  // Assert: received JSON is { "decision": "block" } (or deny equivalent)
  // Assert: data not truncated
});
```

---

## Change History

| Date | What | Task | Who |
|------|------|------|-----|
| 2026-02-18 | Spec created from Bug Hunt 20260218-hooks | BUG-123 | bughunt |
