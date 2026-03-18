# Pattern Research — ARCH-161: Orchestrator Radical Rewrite

## Context

Rewriting `orchestrator.sh` + `pueue-callback.sh` from bash to Python.
The orchestrator is a systemd daemon with a 300s poll loop that:
- Scans projects for inbox files and queued backlog specs
- Submits tasks to Pueue (groups: claude-runner, codex-runner, gemini-runner)
- Maintains slot accounting in SQLite
- The callback fires on Pueue task completion and dispatches QA/Reflect follow-ups

Existing Python already in the stack: `db.py`, `claude-runner.py`, `notify.py` (asyncio-based SDK runner).

---

## Approach 1: Thin Synchronous Python Wrapper

**Source:** [Python subprocess docs](https://docs.python.org/3/library/subprocess.html) + [Architecting Python Background Process Automation](https://www.technetexperts.com/python-process-automation/)

### Description
Direct line-by-line translation from bash to Python using `subprocess.run()` for all pueue calls, `signal.signal()` for SIGTERM, and a `while True / time.sleep(POLL_INTERVAL)` main loop. The callback becomes a standalone `callback.py` CLI script called by pueue. No asyncio, no threads — pure sequential execution per cycle, matching the existing bash mental model exactly.

### Pros
- Zero conceptual overhead — same control flow as bash, just Python syntax
- Easy to read for anyone familiar with the bash original
- No event loop or concurrency primitives to reason about
- Signal handling with `signal.signal()` + a stop flag is trivially correct
- `subprocess.run()` handles all pueue calls; return codes map 1:1 to bash `$?`
- The callback script stays a standalone CLI tool — no refactoring of pueue.yml
- db.py is already pure synchronous SQLite; no impedance mismatch
- Fastest to implement: ~80% is mechanical bash→Python translation

### Cons
- Git pull during the scan cycle blocks the entire process (currently also blocking in bash, but this becomes visible)
- No structured error handling — exceptions propagate unless explicitly caught per call
- Can't do parallel project scans without threads (currently sequential in bash too)
- `subprocess.run()` captures pueue output into memory — fine for current scale, not for 1000+ tasks
- Harder to add non-blocking features later without architectural refactor

### Compute Cost
**Estimate:** ~$5 (R1: medium risk)
**Why:** ~8-10 files affected (orchestrator.py, callback.py, run-agent.sh wrapper, service files, tests). R1 because the callback is on the hot path for every task completion — a regression silently breaks slot tracking and QA dispatch.

### Example Source
```python
import subprocess, signal, time, sys

_stop = False

def _handle_signal(signum, frame):
    global _stop
    _stop = True

signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)

while not _stop:
    sync_projects()
    for project_id, project_dir in get_projects():
        scan_inbox(project_id, project_dir)
        scan_backlog(project_id, project_dir)
    time.sleep(POLL_INTERVAL)
```

---

## Approach 2: Asyncio Daemon with Structured Concurrency

**Source:** [roguelynn.com — asyncio graceful shutdowns](https://roguelynn.com/words/asyncio-graceful-shutdowns/) + [oneuptime.com — Python graceful shutdown Kubernetes](https://oneuptime.com/blog/post/2025-01-06-python-graceful-shutdown-kubernetes/view)

### Description
Full asyncio rewrite: `asyncio.run(main())` entry point, `loop.add_signal_handler()` for SIGTERM, `asyncio.Event` as the stop signal, and `asyncio.create_subprocess_exec()` for pueue calls. Projects can be scanned concurrently via `asyncio.gather()`. The callback script keeps its CLI interface but is internally async. Matches the existing `claude-runner.py` pattern which already uses asyncio.

### Pros
- Consistent with `claude-runner.py` — same concurrency model across the Python stack
- `loop.add_signal_handler()` is the correct asyncio-native way to handle SIGTERM (vs signal.signal() which has race conditions in async contexts)
- `asyncio.gather(*[process_project(p) for p in projects])` makes parallel scanning trivial
- Structured error handling with `try/except` inside each coroutine — one failing project doesn't abort others
- Non-blocking pueue calls via `asyncio.create_subprocess_exec()` — loop stays responsive during git pulls
- `asyncio.Event` stop flag integrates cleanly with `await asyncio.sleep(POLL_INTERVAL)` (wake on event vs timeout)
- Easier to add inotify/file-watch triggers later (replace sleep with event)

### Cons
- Known CPython bug: `asyncio.create_subprocess_exec` + cancellation has a race condition (cpython#103847, still open as of 2026-01-12). Mitigation: don't cancel in-flight pueue calls, let them complete
- Asyncio subprocess signal propagation: SIGINT sent to parent propagates to child pueue processes unless `preexec_fn=os.setpgrp` is used
- The callback (called by pueue daemon) runs in a fresh process, so asyncio adds overhead there with no benefit — callback should stay synchronous
- More complex to debug than synchronous: tracebacks are async, tools like `asyncio.TaskGroup` require Python 3.11+
- `asyncio.Event` stop flag doesn't interrupt `await asyncio.sleep()` immediately on Python < 3.12 without explicit cancellation

### Compute Cost
**Estimate:** ~$10 (R1: medium-high risk)
**Why:** Same files as Approach 1 plus async plumbing. The cpython subprocess bug requires careful testing — R1 because blast radius covers slot management on every task dispatch. Extra ~$5 vs Approach 1 for the async scaffolding and bug mitigation.

### Example Source
```python
import asyncio, signal

async def main():
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop_event.set)

    while not stop_event.is_set():
        await asyncio.gather(
            *[process_project(pid, pdir) for pid, pdir in await get_projects()]
        )
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=POLL_INTERVAL)
        except asyncio.TimeoutError:
            pass  # normal — next cycle

asyncio.run(main())
```

---

## Approach 3: Replace Pueue with Python-Native Process Management

**Source:** [concurrent.futures ThreadPoolExecutor + subprocess](https://www.technetexperts.com/python-process-automation/) + [quasiqueue multiprocess library](https://github.com/tedivm/quasiqueue)

### Description
Eliminate Pueue entirely. Use `concurrent.futures.ThreadPoolExecutor` (or `asyncio.create_subprocess_exec` with a semaphore) to manage concurrency limits per provider group. Each agent run becomes a `Future` (or async task) tracked in an in-memory dict. A SQLite-backed callback mechanism replaces pueue's callback hook — the thread itself updates DB state on completion. The pueue CLI dependency disappears.

### Pros
- Single language stack — no Pueue version dependency, no pueue.yml config
- Concurrency limits trivially enforced with `Semaphore` or `ThreadPoolExecutor(max_workers=N)`
- Task completion callbacks are just `future.add_done_callback()` — no external process, no separate callback.py
- Structured logging in Python — single log stream, no separate pueue log parsing
- No pueue label parsing (`project_id:SPEC-ID`) — can use typed dataclasses directly
- Removes the "resolve label from pueue status --json" fragility in the current callback

### Cons
- **Loses Pueue's persistence**: in-memory queue vanishes on crash/restart; bash orchestrator is resilient because pueue persists tasks across daemon restarts
- **Loses Pueue's observability**: `pueue status`, `pueue log`, `pueue pause` are operator tools used daily — losing them forces building equivalent introspection
- **Loses Pueue's process isolation**: pueue runs each task as a separate OS process with its own stdin/stdout captured independently; ThreadPoolExecutor threads share address space and can interfere
- **Loses Pueue groups**: the group model (claude-runner: 2 slots, codex-runner: 1 slot) maps directly to `ThreadPoolExecutor(max_workers=N)` but group-level pause/resume is non-trivial
- Claude SDK runner (`claude-runner.py`) already manages its own asyncio loop — nesting asyncio in a ThreadPoolExecutor is a known antipattern
- Full rewrite: not just orchestrator.py but also run-agent.sh, systemd service, monitoring runbooks, operator scripts

### Compute Cost
**Estimate:** ~$25 (R2: high risk)
**Why:** 20+ files affected. Blast radius includes: run-agent.sh, pueue-callback.sh, pueue.yml, systemd service, all scripts that call `pueue status`, operator runbooks, monitoring. Losing pueue persistence means a crashed orchestrator can silently lose queued tasks — R2 because rollback requires re-queuing from scratch.

### Example Source
```python
from concurrent.futures import ThreadPoolExecutor, Future
import subprocess

executor = ThreadPoolExecutor(max_workers=2)  # per-group

def run_agent_blocking(project_dir, provider, skill, task_cmd) -> dict:
    result = subprocess.run(
        ["python3", "claude-runner.py", project_dir, task_cmd, skill],
        capture_output=True, text=True
    )
    return {"exit_code": result.returncode, "stdout": result.stdout}

def on_complete(future: Future, project_id: str, spec_id: str):
    result = future.result()
    db.release_slot(...)
    db.update_project_phase(...)
    dispatch_qa_if_needed(...)

future = executor.submit(run_agent_blocking, project_dir, provider, skill, task_cmd)
future.add_done_callback(lambda f: on_complete(f, project_id, spec_id))
```

---

## Comparison Matrix

| Criteria | Approach 1: Thin Sync | Approach 2: Asyncio | Approach 3: No Pueue |
|----------|----------------------|---------------------|----------------------|
| Complexity | Low | Medium | High |
| Maintainability | High | High | Medium |
| Performance | Sufficient | Better | Sufficient |
| Reliability | High (Pueue persists) | High (Pueue persists) | Low (in-memory loss) |
| Operator UX | High (pueue status) | High (pueue status) | Low (custom tooling needed) |
| Blast Radius | Medium | Medium | High |
| Signal Handling | Simple (flag) | Correct (loop.add_signal_handler) | Simple (flag) |
| Error Isolation | Manual per-call | Coroutine-level | Future-level |
| Testability | High | Medium | Medium |
| Migration Risk | Low | Low-Medium | High |
| Compute Cost | ~$5 | ~$10 | ~$25 |
| Risk Level | R1 | R1 | R2 |
| Dependencies | subprocess, signal | asyncio, signal | concurrent.futures |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 1 — Thin Synchronous Python Wrapper (with one targeted asyncio borrow)

### Rationale

The orchestrator is a **300s poll loop** that calls pueue ~5 times per project per cycle and sleeps the rest of the time. It is fundamentally I/O-sequential by design: git pull one project, scan inbox, check backlog, move on. Parallelism across projects would be nice but is not required — the bash version has run sequentially for months without throughput issues.

The callback (`pueue-callback.sh`) is a **stateless CLI script** fired by pueue daemon on task completion. It does 6 database operations and sends a Telegram message. This executes in under 2 seconds. There is no benefit to asyncio here.

Given this, Approach 1 is the correct fit:

1. **Mechanical translation reduces risk**: The bash logic is battle-tested over hundreds of real task cycles. A line-by-line Python translation preserves the logic, making the diff reviewable. An asyncio rewrite introduces new failure modes (CPython subprocess cancellation bug, event loop teardown races) that are orthogonal to the actual goal.

2. **Signal handling is simpler than it appears**: `signal.signal(SIGTERM, handler)` with a `_stop` flag works correctly for a poll loop because the flag is checked between `subprocess.run()` calls — there are no long-running coroutines to cancel. The asyncio `loop.add_signal_handler()` advantage only matters if you have `await`-points that need interruption.

3. **Pueue must stay**: Approach 3 was researched and rejected. Pueue persistence across daemon restarts is load-bearing behavior — the orchestrator can restart without losing queued tasks. This is demonstrated by the existing `.run-now-{project_id}` trigger mechanism surviving orchestrator restarts.

**One borrow from Approach 2**: The callback's "dispatch QA/Reflect" logic currently uses inline `pueue status --json | python3 -c "..."` for deduplication checks. In Python, this becomes a clean `subprocess.run(["pueue", "status", "--json"])` + `json.loads()` with proper error handling — no asyncio needed.

### Trade-off Accepted

We give up parallel project scanning (Approach 2's `asyncio.gather`). With 3-5 active projects and a 300s cycle, sequential scanning adds at most 5-10 seconds of latency per cycle — imperceptible. If project count grows past ~20, an asyncio rewrite of the main loop is a contained, incremental change.

We give up full Python-native task management (Approach 3). The operational value of `pueue status`, `pueue log`, and `pueue pause --group` is non-negotiable for a production system that runs 24/7 with minimal operator attention.

---

## Research Sources

- [Python subprocess docs](https://docs.python.org/3/library/subprocess.html) — subprocess.run() patterns for pueue CLI wrapping
- [roguelynn.com — asyncio graceful shutdowns](https://roguelynn.com/words/asyncio-graceful-shutdowns/) — loop.add_signal_handler() vs signal.signal() trade-offs
- [oneuptime.com — Python graceful shutdown Kubernetes/systemd](https://oneuptime.com/blog/post/2025-01-06-python-graceful-shutdown-kubernetes/view) — production signal handling patterns for daemon processes
- [CPython issue #103847](https://github.com/python/cpython/issues/103847) — asyncio.create_subprocess_exec cancellation race condition (open, 2026-01-12)
- [Architecting Python Background Process Automation](https://www.technetexperts.com/python-process-automation/) — concurrent.futures vs asyncio subprocess trade-offs
- [Nukesor/pueue](https://github.com/Nukesor/pueue) — Pueue v4.0.4 feature set confirming group/persistence/callback model
- [Python Concurrency Showdown 2026](https://medium.com/@sizanmahmud08/python-concurrency-showdown-asyncio-vs-threading-vs-multiprocessing-which-should-you-choose-in-31205161899a) — asyncio best for high-concurrency I/O; overkill for low-frequency poll loops
