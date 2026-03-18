# External Research — Immediate Process Wake-Up After Event File Write (TECH-157)

## Best Practices

### 1. Write-Then-Notify: File First, Signal Second
**Source:** [Push vs. Pull Architectures in Real-Time Systems](https://systemdr.substack.com/p/push-vs-pull-architectures-in-real)
**Summary:** The canonical hybrid pattern writes the durable artifact first, then sends the immediate notification. The file is the source of truth; the notification is a latency optimization. If the notification is lost, the polling loop finds the file on the next cycle — no data loss.
**Why relevant:** This is precisely what TECH-157 needs. The event JSON file (already written in Step 6.8 of `pueue-callback.sh`) is the durable artifact. Adding a wake command afterward reduces latency from up to 5 min to near-zero without changing the reliability contract.

---

### 2. Fail-Safe Optional Commands via `|| true`
**Source:** [Shell Script Hack #11: Command Chaining — Clean Error Handling with && and ||](https://chandanbhagat.com.np/shell-script-hack-11-command-chaining-clean-error/)
**Summary:** In production shell scripts, appending `|| true` to an optional command prevents a non-zero exit code from propagating when the script uses `set -e`. The pattern is standard: `some_optional_cmd || true`. The existing `pueue-callback.sh` already applies this pattern extensively (notify.py, db.py, pueue status checks all use `|| true` or `|| { echo WARN; }`).
**Why relevant:** The wake command must not break the callback under any failure mode: missing PID file, stale PID, permission issues, orchestrator not running. `|| true` is the correct mechanism.

---

### 3. Bounded Execution via `timeout` for Synchronous CLI Calls in Callbacks
**Source:** [Timeout Handling in Bash: Preventing Hanging Scripts in Production](https://coderlegion.com/12372/timeout-handling-in-bash-preventing-hanging-scripts-in-production)
**Summary:** When a callback script makes a synchronous CLI call to a separate process, the call can block indefinitely if the target is unresponsive. GNU `timeout` (coreutils, available on all modern Linux) wraps the call: `timeout 5s some_command || true`. The `-k` flag sends SIGKILL after a grace period: `timeout --kill-after=2s 5s some_command || true`. Pueue runs callbacks synchronously — a hung wake command would stall the pueue daemon's callback execution.
**Why relevant:** Critical for this feature. The orchestrator wake must be wrapped with `timeout` (2–5 s is sufficient for a `kill -USR1`) to prevent the pueue callback from hanging if orchestrator.sh has stalled.

---

### 4. PID-File Pattern for Inter-Process Wake Signals
**Source:** [How can I wake a process from sleep status via signal or /proc?](https://unix.stackexchange.com/questions/252507/how-can-i-wake-a-process-from-sleep-status-via-signal-or-proc/252521)
**Source 2:** [Send `kill -SIGUSR1` to daemon process](https://stackoverflow.com/questions/78690427/send-kill-sigusr1-to-daemon-process)
**Summary:** The standard pattern for waking a known daemon from a shell script: (1) daemon writes its PID to a known file on startup; (2) the wake sender reads the PID, validates the process is alive, and sends `kill -USR1 <pid>`. The orchestrator already has a PID file at `scripts/vps/.orchestrator.pid`. SIGUSR1 is conventionally used for "reload/wake" (SIGHUP for config reload, SIGUSR1/2 for application-defined events). The receiving daemon must `trap` the signal. The guard `[[ -f "$PID_FILE" ]] && kill -0 "$PID" 2>/dev/null && kill -USR1 "$PID"` is the minimal safe form.
**Why relevant:** This is the exact mechanism needed. The PID file already exists. The orchestrator needs a `trap` for SIGUSR1 to break out of its `sleep $POLL_INTERVAL` early.

---

### 5. Cron as Authoritative Fallback, Push as Optimization
**Source:** [Data Pipeline Design Patterns: Push, Pull, and Poll Strategies Explained](https://medium.com/%40archie.kandala/data-pipeline-design-patterns-push-pull-and-poll-strategies-explained-ccc856f8412b)
**Source 2:** [Push and Pull Architecture: Event Triggers vs. Sensors in Data Pipelines](https://prefect.io/blog/push-and-pull-architecture-event-triggers-vs-sensors-in-data-pipelines)
**Summary:** In data engineering, a well-known hybrid design keeps a periodic polling schedule (cron/sensor) as the authoritative trigger for correctness, and adds push signals (events/triggers) purely as a latency reducer. The system must be idempotent — the consumer can be woken any number of times and must handle duplicate events gracefully. The orchestrator's `find ai/openclaw/pending-events/` scan is already idempotent (it moves/reads files atomically).
**Why relevant:** Confirms the approach: cron-poll as fallback guarantees correctness, wake signal reduces latency. No architectural change needed — only an additive optimization.

---

## Libraries/Tools

| Tool | Version | Pros | Cons | Use Case | Source |
|------|---------|------|------|----------|--------|
| `kill -USR1` + PID file | POSIX | Zero deps, instant, works in any shell | Requires PID file + trap in receiver | Wake a known daemon | [Unix SE](https://unix.stackexchange.com/questions/252507) |
| `inotifywait` (inotify-tools) | 3.22+ | Kernel-level event, no polling | Requires inotify-tools package, adds daemon complexity | Watch directory for new files | [How to Set Up inotifywait](https://oneuptime.com/blog/post/2026-03-02-how-to-set-up-inotifywait-for-file-based-triggers-on-ubuntu/view) |
| `timeout` (GNU coreutils) | 8.x+ | Standard on all Linux, prevents hangs | N/A | Bound synchronous CLI call in callback | [Baeldung timeout guide](https://www.baeldung.com/linux/bash-timeouts) |
| Named pipe (FIFO) | POSIX | Pure bash, no deps | Complex lifecycle, blocking by default | Two-process coordination | [SO: pause bash until signal](https://stackoverflow.com/questions/53745465) |

**Recommendation:** `kill -USR1` via existing PID file (`scripts/vps/.orchestrator.pid`). Zero new dependencies. The PID file is already written by orchestrator.sh. Add `trap` for SIGUSR1 in orchestrator.sh to interrupt `sleep`. Wrap the wake call with `timeout 5s ... || true` in `pueue-callback.sh`. No new infrastructure needed.

`inotifywait` is the "right" solution architecturally but adds a dependency, changes the orchestrator loop structure significantly, and provides no meaningful latency improvement over the signal approach given our constraints.

---

## Production Patterns

### Pattern 1: Write-Then-Signal with PID File
**Source:** [I Write a Linux Daemon in C: A Practical Guide](https://phb-crystal-ball.org/i-write-a-linux-daemon-in-c-a-practical-guide/)
**Description:** Producer: write durable artifact, then read PID from well-known file, validate process alive (`kill -0`), send SIGUSR1. Consumer daemon: traps SIGUSR1 to set a flag or interrupt sleep, then processes all pending files. Works even without the signal (daemon catches up on next poll).
**Real-world use:** Used by Nginx (SIGHUP for config reload), Unicorn/Puma web servers (SIGUSR1/2 for log rotation and rolling restart), systemd service managers.
**Fits us:** Yes — the orchestrator PID file already exists at `.orchestrator.pid`. The orchestrator's main loop does `sleep $POLL_INTERVAL` which can be interrupted by a signal trap.

---

### Pattern 2: Guarded Wake with `timeout` + `|| true`
**Source:** [Timeout Handling in Bash: Preventing Hanging Scripts in Production](https://coderlegion.com/12372/timeout-handling-in-bash-preventing-hanging-scripts-in-production)
**Description:** Any synchronous external call inside a callback (pueue runs callbacks synchronously, blocking the task completion mark) must be bounded. Pattern:
```bash
ORCH_PID_FILE="${SCRIPT_DIR}/.orchestrator.pid"
if [[ -f "$ORCH_PID_FILE" ]]; then
    ORCH_PID=$(cat "$ORCH_PID_FILE" 2>/dev/null || true)
    if [[ -n "$ORCH_PID" ]] && kill -0 "$ORCH_PID" 2>/dev/null; then
        timeout 5s kill -USR1 "$ORCH_PID" 2>/dev/null || true
        echo "[callback] Orchestrator wake signal sent (pid=${ORCH_PID})"
    else
        echo "[callback] Orchestrator not running — cron fallback active"
    fi
fi
```
**Real-world use:** Standard DevOps pattern for hook scripts (git hooks, CI callbacks, pueue callbacks).
**Fits us:** Yes — matches existing callback style exactly (all risky calls already use `|| true`).

---

### Pattern 3: Signal-Interrupted Sleep in Daemon Loop
**Source:** [Catching Signals in a Shell Script](https://www.zyzzyxdonta.net/posts/catching-signals-in-a-shell-script/)
**Description:** A bash daemon loop using `sleep N` can be made interruptible by trapping SIGUSR1 and killing the background sleep:
```bash
_WAKE_REQUESTED=false
trap '_WAKE_REQUESTED=true; kill "$_SLEEP_PID" 2>/dev/null || true' USR1

while true; do
    process_all_pending
    _WAKE_REQUESTED=false
    sleep "$POLL_INTERVAL" &
    _SLEEP_PID=$!
    wait "$_SLEEP_PID" || true  # returns immediately on signal
done
```
**Real-world use:** Common pattern in init scripts, watchdog daemons, and polling orchestrators (e.g., ArgoCD agent inner loop uses a similar select/signal pattern).
**Fits us:** Yes — orchestrator.sh has a `sleep $POLL_INTERVAL` at the end of its main loop. Adding a `trap USR1` + `kill sleep_pid` makes it interruptible without changing any other logic.

---

## Key Decisions Supported by Research

1. **Decision:** Use `kill -USR1` via PID file, not `inotifywait`
   **Evidence:** PID file already exists (`scripts/vps/.orchestrator.pid`). `kill` is POSIX, no deps. `inotifywait` requires package install and a persistent watcher process — unnecessary complexity for a system that already has polling. Same-host communication makes signal delivery reliable.
   **Confidence:** High

2. **Decision:** Wrap wake call with `timeout 5s ... || true` in callback
   **Evidence:** Pueue executes callbacks synchronously (confirmed in pueue source and wiki). A blocking wake call would stall the callback, delaying pueue's ability to mark the task complete and free the compute slot. `timeout` bounds the risk to 5 seconds maximum.
   **Confidence:** High

3. **Decision:** Add `trap USR1` to orchestrator.sh's sleep, not replace the polling loop
   **Evidence:** "Cron as authoritative fallback" pattern (Prefect, Medium data pipeline articles). The idempotent file-scan approach means correctness is already guaranteed by polling. The signal is purely a latency optimizer. Removing polling would make the system fragile to lost signals (e.g., orchestrator restart between signal send and processing).
   **Confidence:** High

4. **Decision:** Guard with `kill -0 $PID` before sending signal
   **Evidence:** Standard PID-file pattern (Unix SE answer, score 25). A stale PID file (orchestrator crashed, pid reused by another process) must not send signals to arbitrary processes. `kill -0` checks process existence without side effects.
   **Confidence:** High

---

## Research Sources

- [Push vs. Pull Architectures in Real-Time Systems](https://systemdr.substack.com/p/push-vs-pull-architectures-in-real) — hybrid push+poll design rationale
- [Shell Script Hack #11: Command Chaining](https://chandanbhagat.com.np/shell-script-hack-11-command-chaining-clean-error/) — `|| true` pattern for fail-safe optional commands
- [Timeout Handling in Bash: Preventing Hanging Scripts in Production](https://coderlegion.com/12372/timeout-handling-in-bash-preventing-hanging-scripts-in-production) — bounding synchronous CLI calls in callbacks
- [How can I wake a process from sleep status via signal or /proc?](https://unix.stackexchange.com/questions/252507/how-can-i-wake-a-process-from-sleep-status-via-signal-or-proc/252521) — `kill -USR1` + PID file mechanics
- [Catching Signals in a Shell Script](https://www.zyzzyxdonta.net/posts/catching-signals-in-a-shell-script/) — `trap` USR1 to interrupt sleep in daemon loop
- [Pueue Common Pitfalls and Debugging](https://github.com/Nukesor/pueue/wiki/Common-Pitfalls-and-Debugging) — pueue callback execution environment and blocking behavior
- [Data Pipeline Design Patterns: Push, Pull, and Poll Strategies Explained](https://medium.com/%40archie.kandala/data-pipeline-design-patterns-push-pull-and-poll-strategies-explained-ccc856f8412b) — confirms cron-as-fallback, push-as-optimization pattern
- [How to Set Up inotifywait for File-Based Triggers on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-how-to-set-up-inotifywait-for-file-based-triggers-on-ubuntu/view) — inotify alternative (rejected: adds dep, no benefit over signal approach)
- [Shell Scripting Best Practices for Production Systems](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/) — `set -euo pipefail` + safe error handling in production scripts
- [Send `kill -SIGUSR1` to daemon process](https://stackoverflow.com/questions/78690427/send-kill-sigusr1-to-daemon-process) — signal delivery from a different process with PID file
