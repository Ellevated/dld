# Pattern Research — OpenClaw Immediate Wake After Pending-Event Write

## Context

`pueue-callback.sh` (Step 6.8, lines 295-326) writes a JSON event file into
`ai/openclaw/pending-events/` after autopilot/qa/reflect completion.
Currently OpenClaw reads these files via cron (every ~5 min). Goal: eliminate
that lag by waking OpenClaw immediately after the file is written.

The callback is fail-safe by design (`|| true` everywhere, `set -uo pipefail`).
Any wake mechanism must not break that contract.

---

## Approach 1: Direct Blocking Wake (`|| true`)

**Source:** [Shell Scripting Best Practices for Production Systems](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view)

### Description
Call `openclaw gateway wake --mode now` directly after writing the event file,
redirecting stderr to the callback log and suffixing with `|| true`.
If `openclaw` is absent, slow, or errors out — the callback continues unaffected.
The cron remains untouched as a fallback for any missed wake.

### Code Shape
```bash
# After the cat > "$EVENT_FILE" <<EOF ... EOF block:
openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" || true
```

### Pros
- Zero architectural overhead — 3 lines, no new processes, no new dependencies
- Synchronous: if wake succeeds, OpenClaw is running before callback exits
- Failure is silent and safe — `|| true` preserves exit-0 contract
- Completely auditable: stderr goes to existing `$CALLBACK_LOG`
- Cron remains as fallback — no reliability regression

### Cons
- If `openclaw wake` has a slow startup or network call, it adds latency to the
  callback (pueue waits for callback to finish before marking task complete)
- If `openclaw` binary hangs (e.g., waiting on a lock), the callback hangs too
  until the shell's default timeout or a SIGTERM — `|| true` won't help a hanging
  process, only a failing one
- Relies on `openclaw` being on PATH inside the callback's environment

### Compute Cost
**Estimate:** ~$1 (R2: contained)
**Why:** Single-file change (pueue-callback.sh), 3 lines, no blast radius. Trivially rollbackable with one git revert.

### Example Source
From the existing callback pattern (lines 275-278):
```bash
python3 "$NOTIFY_PY" "$PROJECT_ID" "$MSG" 2>>"$CALLBACK_LOG" || {
    echo "[callback] WARN: notify.py failed" >&2
}
```
The `|| true` variant is even simpler — same fail-safe pattern already proven in this file.

---

## Approach 2: Background Wake (`&`)

**Source:** [How to Handle Background Processes in Bash](https://oneuptime.com/blog/post/2026-01-24-bash-background-processes/view)

### Description
Detach `openclaw gateway wake` into a background subshell with `&`.
The callback does not wait for the wake command to complete — it proceeds
immediately. The wake happens asynchronously after the event file is written.

### Code Shape
```bash
# After event file write:
(openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" || true) &
```

### Pros
- Callback exits at full speed — zero latency added to pueue task completion
- Hung `openclaw` process cannot block callback
- Still fail-safe (`|| true` inside subshell)

### Cons
- Background process is a child of the callback script, which itself runs as a
  pueue callback subprocess. When pueue considers the callback done (exit 0),
  it may SIGHUP the process group, killing the background wake before it runs
- Disowning with `disown` helps but orphaned processes are harder to trace in logs
- Log ordering becomes non-deterministic — wake stderr may arrive after callback
  "done" log line, confusing debugging
- On a VPS with tight process limits, spurious background forks add noise
- Race: if openclaw polls pending-events before the background process has called
  wake, the event is still picked up by cron — background gives no reliability gain
  over Approach 1 in the success path, but adds complexity in the failure path

### Compute Cost
**Estimate:** ~$1 (R2: contained)
**Why:** Same single-file change. Slightly more complex shell quoting (subshell `()`). Risk is slightly higher due to pueue SIGHUP behavior on callback exit.

### Example Source
```bash
# Standard pattern from bash background process guide:
long_running_command &
pid=$!
# ... script continues without waiting
```
The subshell variant `(cmd) &` is preferred when you want to isolate exit codes.

---

## Approach 3: inotifywait Filesystem Watcher (Replace Cron)

**Source:** [How to Set Up inotifywait for File-Based Triggers on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-how-to-set-up-inotifywait-for-file-based-triggers-on-ubuntu/view)

### Description
Run a persistent `inotifywait -m -e close_write pending-events/` daemon (via
systemd or pueue) that fires the openclaw wake command whenever a new `.json`
file appears. Cron is eliminated; the watcher becomes the only trigger.

### Code Shape
```bash
# openclaw-watcher.sh (new systemd unit):
inotifywait -m -q -e close_write \
    --format '%f' "$PENDING_EVENTS_DIR" |
while read -r filename; do
    [[ "$filename" == *.json ]] || continue
    openclaw gateway wake --mode now 2>>"$LOG" || true
done
```

### Pros
- Truly event-driven — sub-second latency, no polling at all
- No callback modification needed — watcher is a separate process
- Handles burst correctly when multiple events fire rapidly
- Decoupled: callback and watcher don't share process space

### Cons
- New dependency: `inotify-tools` must be installed on every VPS
  (`sudo apt install inotify-tools`)
- inotify has kernel-level limits (`fs.inotify.max_user_watches`). On VPS with
  many Docker containers or Node.js processes, watches can be exhausted silently,
  causing dropped events with no error log
  ([inotify limits article](https://www.techtransit.org/inotify-limits-linux/))
- Watcher process itself must be supervised (systemd unit or pueue group).
  If it crashes, there is no fallback — unlike cron+Approach 1 which are additive
- More moving parts: new unit file, new script, setup-vps.sh changes,
  restart procedure for existing VPS
- inotify does not work over NFS or some bind mounts — not a current concern
  but a latent risk if storage is ever moved
- Race condition documented in inotify man page: event may be delivered after
  file is already renamed/deleted (not relevant here, but shows inotify's limits)

### Compute Cost
**Estimate:** ~$5 (R1: medium blast radius)
**Why:** New script + new systemd unit + setup-vps.sh modification + removal/modification of cron line + documentation update. 5-7 files affected. Requires VPS redeployment to take effect.

### Example Source
From [Unix StackExchange — inotifywait monitor mode](https://unix.stackexchange.com/questions/548509/reliability-of-inotifywait-loop):
```bash
inotifywait -m -q -r -e create --format '%w%f' "$watchpath" |
    while read -r path; do
        process "$path"
    done
```
Monitor mode (`-m`) avoids the re-registration race present in the loop+single-shot pattern.

---

## Approach 4: Named Pipe / FIFO Signal

**Source:** [Linux IPC Mastery: Pipes, FIFOs, Message Queues](https://support.tools/linux-pipes-ipc-mastery/)

### Description
Create a named FIFO (`mkfifo openclaw.wake`). The callback writes a byte to the
FIFO after writing the event file; OpenClaw's main loop `read`s from the FIFO
and wakes immediately. Eliminates both cron and inotifywait.

### Code Shape
```bash
# Callback (sender):
echo "wake" > /run/openclaw/wake.fifo || true

# OpenClaw daemon (receiver):
while read -r _ < /run/openclaw/wake.fifo; do
    process_pending_events
done
```

### Pros
- Kernel-mediated, zero polling, minimal latency
- No extra dependencies (`mkfifo` is POSIX)
- Clean producer/consumer contract

### Cons
- Requires OpenClaw to run as a persistent daemon with its own FIFO reader —
  the current model is cron-invoked, not daemon. This approach requires
  architectural change in OpenClaw itself
- FIFO write blocks if no reader is listening. `|| true` won't unblock a hanging
  write — needs `O_NONBLOCK` or a timeout, which requires Python/C, not bash
- FIFO path must be agreed upon by both sides and survive reboots
  (`/tmp` is wiped, `/run` is volatile)
- If OpenClaw is not running (crashed, not started), the write blocks the
  callback until SIGPIPE or timeout — much worse failure mode than Approach 1
- Significant implementation complexity for both callback and OpenClaw

### Compute Cost
**Estimate:** ~$15 (R1: high blast radius)
**Why:** Requires OpenClaw architecture change (daemon mode), FIFO management, callback modification, setup changes. 20+ files affected across two projects.

### Example Source
From [Process Synchronization with FIFOs](https://samuel.karp.dev/blog/2020/11/process-synchronization-with-fifos/) — demonstrates blocking behavior and the requirement for a persistent reader.

---

## Comparison Matrix

| Criteria | Approach 1: Direct `\|\| true` | Approach 2: Background `&` | Approach 3: inotifywait | Approach 4: FIFO |
|----------|-------------------------------|---------------------------|-------------------------|------------------|
| Latency reduction | High (sync wake) | High (async wake) | High (kernel event) | Very High |
| Callback latency added | Low (ms, fast binary) | None | None | Low-High (blocking risk) |
| Fail-safety | High | Medium (SIGHUP risk) | Low (no fallback) | Low (blocking write risk) |
| Complexity | Low | Low-Medium | Medium | High |
| New dependencies | None | None | inotify-tools | None |
| Cron fallback preserved | Yes | Yes | No (replaces cron) | No |
| Files affected | 1 | 1 | 5-7 | 20+ |
| Maintainability | High | Medium | Medium | Low |
| Testability | High | Medium | Medium | Low |
| Risk level | R2 | R2 | R1 | R1 |

**Rating scale:** Low / Medium / High / Very High

---

## Recommendation

**Selected:** Approach 1 (Direct Blocking Wake with `|| true`)

### Rationale

The Socratic brief already identified this as a "simple 3-line change" and that
framing is correct. The callback's design philosophy — established across its
entire 411-line body — is: attempt the operation, redirect errors to log, suffix
with `|| true`. Approach 1 is the only approach that is native to this existing
pattern.

The blocking concern (what if `openclaw wake` hangs?) is real but bounded.
`openclaw gateway wake --mode now` is designed to be a lightweight signal, not
a long-running operation. If the binary has a startup timeout of its own (as
most CLI tools do), worst case is a few seconds of extra callback latency — not
a hung callback. If that turns out to be a problem in practice, switching to
Approach 2 (background `&`) is a one-line delta.

Approach 2 (background) is seductive but introduces the pueue SIGHUP hazard:
pueue's callback mechanism fires the script and waits for exit. Background
children of a short-lived script are in the same session; when the session
leader exits, pueue may deliver SIGHUP to the group before the background wake
completes. This is a known, documented pueue footgun (see issue #236). Without
explicit `disown` + `nohup`, reliability of the background approach is lower
than it appears.

Approach 3 (inotifywait) is architecturally clean but solves a bigger problem
than we have. The cron+event-file model is working; its only flaw is 5-min lag.
Adding a new systemd unit, a new dependency, and eliminating the cron fallback
to fix a 5-min lag is disproportionate. The inotify watch limit risk on a shared
VPS is a concrete operational hazard.

Approach 4 (FIFO) requires OpenClaw to become a daemon — that is a separate
architectural decision outside the scope of this task.

Key factors:
1. **Minimal blast radius** — 1 file, 3 lines, zero new dependencies
2. **Preserves existing fail-safe contract** — `|| true` is already the law of this file
3. **Cron stays as fallback** — defense in depth, no reliability regression
4. **Proven pattern** — identical to how `notify.py` is called on line 275

### Trade-off Accepted

We accept that a slow or hung `openclaw wake` could add latency to the callback.
Mitigation: if `openclaw gateway wake` proves to be slow in practice, wrap with
`timeout 5 openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" || true` — a
one-word change.

We are not adopting inotifywait (Approach 3), accepting the trade-off that if
the direct wake fails (binary absent, permission error), the cron will still
catch the event within 5 minutes — which is the current baseline behavior.

---

## Research Sources

- [Shell Scripting Best Practices for Production Systems](https://oneuptime.com/blog/post/2026-02-13-shell-scripting-best-practices/view) — `|| true` and fail-safe callback patterns
- [How to Handle Background Processes in Bash](https://oneuptime.com/blog/post/2026-01-24-bash-background-processes/view) — `&` and SIGHUP behavior for background children
- [How to Set Up inotifywait for File-Based Triggers on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-how-to-set-up-inotifywait-for-file-based-triggers-on-ubuntu/view) — inotifywait monitor mode patterns
- [Reliability of inotifywait loop](https://unix.stackexchange.com/questions/548509/reliability-of-inotifywait-loop) — monitor mode vs loop race condition
- [Your Linux server is missing file changes — inotify limits](https://www.techtransit.org/inotify-limits-linux/) — inotify watch exhaustion in production
- [Linux IPC Mastery: Pipes, FIFOs](https://support.tools/linux-pipes-ipc-mastery/) — FIFO blocking semantics and failure modes
- [Process Synchronization with FIFOs](https://samuel.karp.dev/blog/2020/11/process-synchronization-with-fifos/) — FIFO requires persistent reader
- [Pueue Common Pitfalls — callback execution](https://github.com/Nukesor/pueue/wiki/Common-Pitfalls-and-Debugging) — pueue callback environment and process group behavior
