# Operations Architecture Research

**Persona:** Charity (Operations Engineer) — Honeycomb lens
**Focus:** Deployment, observability, SLOs, production readiness
**Date:** 2026-05-23
**Scope:** scripts/vps/ contour — systemd daemon, pueue, callback, lifecycle, orchestrator

---

## Research Conducted

**Note:** Exa credits were exhausted (HTTP 402). All analysis is drawn from
direct codebase inspection — 8 files read in full or in substantial part,
cross-referenced against the deep-audit report (85 findings) and the
architecture agenda. This is the most authoritative source available: the
actual production code running on the VDS today.

Files analyzed:
- `scripts/vps/callback.py` (1374 LOC) — 19 bare `except Exception` grep, audit path, `verify_status_sync` logic
- `scripts/vps/lifecycle.py` (602 LOC) — `_run()`, `_atomic_write`, `_push_best_effort`, `_cas_loop`, log levels
- `scripts/vps/orchestrator.py` (667 LOC) — `bootstrap_new_specs`, `startup_reconcile`, `_setup_logging`
- `scripts/vps/db.py` (531 LOC) — schema, `_MIGRATIONS_APPLIED`, tables
- `scripts/vps/event_writer.py` — Hermes wake, `notify_circuit_event`
- `pyproject.toml` — testpaths gap (`["tests"]` not `["tests","scripts/vps/tests"]`)
- `.github/workflows/test.yml` — CI scope (callback.py ≥65% only)
- `~/.claude/projects/-root/memory/dld-orchestrator.md` — operational flow

**Total research basis:** 8 files, ~5000 lines of production code

---

## Kill Question Answer

**"How will you know this broke in production?"**

**Scenario:** `bootstrap_new_specs` silently flips 15 specs to `done` at 11:17.
No alert fires. At 16:00 — four hours and forty-three minutes later — a human
notices by accident.

**What actually happened, step by step:**

1. **Alert fires:** Nothing. There is no alert. The only signal is a `log.info`
   line in orchestrator.log: `"BOOTSTRAP: created lifecycle.yaml for %s status=done"`.
   Repeated 15 times in 30 seconds.

2. **First look:** `journalctl -u dld-orchestrator --since "11:15"`. You see 15
   consecutive BOOTSTRAP lines with `status=done`. But you only look at this
   if you already know something is wrong. Nobody looked.

3. **Diagnosis:** You grep `callback-audit.jsonl` for spec IDs. You find
   `already_done_terminal` entries — the audit log has been faithfully recording
   that these specs were "already done" on every subsequent callback. Perfectly
   accurate records of a corrupted state. Nobody reads the audit log in real time.

4. **Mitigation:** Manual `spec_operator.py` to revert each lifecycle yaml.
   There is no rollback command. There is no "undo bootstrap". Each spec
   requires a separate `write_lifecycle` call with `by="operator"`.

5. **Resolution:** Fix bootstrap_new_specs to gate through `_is_done_on_develop`.
   But this is the fifth time a fix has been applied to this contour. Without
   observability proving the fix worked, we'll know about the sixth failure the
   same way we knew about this one: a human notices by accident.

**Observability gaps preventing this path from being smooth:**

- No rate metric on BOOTSTRAP operations. 15 bootstraps in 30 seconds is
  completely normal-looking in the logs. There is no alarm threshold.
- No derived metric from the audit JSONL. The data exists; no one reads it.
- No health check endpoint. There is no way to ask "is the orchestrator
  currently healthy?" without reading raw log files.
- `_push_best_effort` logs at DEBUG. If the push fails — if git origin never
  gets the corrected lifecycle state — you see nothing at INFO level.
- 5-hour detection gap: the system has no SLO for "spec status must not drift
  from expected for more than N minutes."

---

## AS-IS Observability Inventory

This is the complete list of what currently exists.

### What Exists

**Structured logs (partial):**

```
orchestrator.py: JSON-formatted daily-rotating file (/var/log/dld-orchestrator/orchestrator.log)
callback.py:     Unstructured append-mode file (scripts/vps/callback-debug.log) + stderr
lifecycle.py:    Inherits callback/orchestrator logger, no dedicated log
```

Note: orchestrator uses `'{"ts":"...","level":"...","msg":"..."}'` format — this
is JSON, but msg is an unstructured freeform string. There are no structured
fields on individual events (no `spec_id`, `project_id`, `operation` as
top-level JSON keys). Grepping for a spec ID requires substring search through
msg strings.

**Audit JSONL:**

`scripts/vps/callback-audit.jsonl` — one line per `verify_status_sync` call.
Fields: project_id, spec_id, pueue_id, target_status, verdict, reason,
code_loc, test_loc, code_commits, allowed_files, started_at, elapsed_ms.

This is the highest-quality data in the system. It is never read automatically.
There is no dashboard, no alert, no tail process watching it.

**SQLite tables:**

| Table | Purpose | Read by |
|-------|---------|---------|
| `compute_slots` | Slot occupancy | orchestrator, callback |
| `task_log` | Per-task record with pueue_id, branch, status, exit_code | callback, orchestrator |
| `project_state` | Phase per project | orchestrator, callback |
| `callback_decisions` | Circuit breaker verdicts | circuit breaker logic |
| `sdk_post_result_errors` | Post-result SDK exceptions | nobody in real time |
| `night_findings` | Night reviewer output | orchestrator morning cycle |

None of these tables are exposed as metrics. No tooling watches row counts.
`callback_decisions` has a circuit breaker that fires at 3 demotes in 10
minutes — but the threshold detection is reactive (inside callback.py), not
observable from outside.

**Event/notification layer:**

`event_writer.py` writes JSON files to `ai/openclaw/pending-events/` and
optionally wakes Hermes. Events exist for: autopilot done/failed, qa done/failed,
reflect done, circuit_breaker open/reset/heal. No event for: bootstrap_new_specs
volume, push failure, WT sync failure, lifecycle write race, orchestrator poll
cycle duration.

**Systemd:**

`dld-orchestrator.service` (user unit). Available via `journalctl -u
dld-orchestrator`. No watchdog timeout configured (confirmed by absence of
`WatchdogSec=` in service template). Restarts via `Restart=on-failure`.

**CI:**

`.github/workflows/test.yml` — runs on push to develop/main. Covers:
callback.py unit + integration + regression. Coverage gate: callback.py ≥65%.
lifecycle.py (602 LOC), orchestrator.py (667 LOC): **zero coverage gate**.
`scripts/vps/tests/` (~100 tests): **not in CI** (`pyproject.toml:19` says
`testpaths = ["tests"]`).

### What Does NOT Exist

- Prometheus/statsd metrics endpoint
- Any dashboard (Grafana, Datadog, or even a simple HTML page)
- SLOs or SLIs defined for any operation
- Alert rules with defined thresholds
- Runbooks linked from alerts (there are no alerts)
- Health check endpoint (HTTP or otherwise)
- Distributed trace IDs correlating pueue task → runner → callback → lifecycle write
- `_push_best_effort` visibility at INFO or above
- Rate alerting on bootstrap volume
- Audit JSONL reader/aggregator
- Timeout on git plumbing calls in `lifecycle._run()`
- Watchdog for orchestrator poll loop health

---

## The 3 AM RCA: Today's Incident + 4 Previous

### Today's Incident (2026-05-23 11:17)

**Root cause (operational):** `bootstrap_new_specs` reads `ai/backlog.md` from
working tree (WT). The WT copy contained stale `done` status for 15 specs.
`active_status.get(spec_id, "done")` returns `"done"` as default for specs
whose status row is in the archive section. 13 lifecycle YAMLs created in
~30 seconds, all with `status=done`.

**Why it took 5 hours to detect:**
- No metric counting bootstrap operations per cycle
- No alert on "N specs bootstrapped with status=done in M minutes"
- `callback-audit.jsonl` faithfully records `already_done_terminal` for every
  subsequent callback call on these specs. Nobody reads the audit log.
- The only human-visible signal was incorrect Hermes notification messages
  and missing task dispatches (specs that should have been queued were silently
  "done"). This is a **lagging indicator** requiring human pattern recognition.

**What a leading indicator would look like:**
- Counter: `bootstrap_ops_total{status="done"}` incremented 15 times in 30s
- Alert: `rate(bootstrap_ops_total{status="done"}[5m]) > 3` fires in 2 minutes

### BUG-188 (2026-05-20) — claude-runner false-fail

**Operational symptom:** Successful autopilot runs marked as failed. Retries
burn compute budget (~$258/week at peak). Detection: somebody noticed the
sdk_post_result_errors table growing.

**Observability gap:** `sdk_post_result_errors` table exists but has no alert
threshold. A dashboard showing error rate over time would have caught this in
hours, not days.

### ARCH-186 (2026-05-16) — lifecycle SoT migration

**Operational symptom:** Post-merge, `_render_and_commit_backlog` was disabled
(lifecycle.py:208 NOTE comment) but `callback.py:1187` still calls it. Stale
`backlog.md` WT caused awardybot/wb to have dirty `ai/lifecycle/` WTs.

**Observability gap:** `assert_clean_lifecycle_tree` fires at startup and aborts
— it is the backstop against dirty WT. But this is **reactive**: the daemon
won't restart after a dirty WT until someone manually cleans it. No proactive
check that WT has stayed clean between restarts.

### BUG-185 / BUG-974 — autostash race

**Operational symptom:** callback.py autostash pop restores an old
DLD-CALLBACK-MARKER block on top of newly-written lifecycle state. Status
appears correct but reverts on next git operation.

**Observability gap:** No version counter on lifecycle writes. No alert on
`lifecycle.yaml version decreasing` (which is impossible in the CAS model —
version always increases — but the pre-ARCH-186 markdown model had no
versioning at all).

### TECH-166 / TECH-176 / TECH-177 — gate false-blocked

**Operational symptom:** Specs remain `blocked` even after work is merged.
Detection: human looks at backlog and notices specs that should be done.

**Observability gap:** `verify_status_sync` emits `blocked` verdict to
audit JSONL. If rate of `blocked` verdict increases above baseline, something
is wrong with the gate. No alert exists. The audit JSONL contains this data.

### Pattern across all 5 incidents

Every incident shared the same failure path:

1. Something changes silently (bootstrap, migration, gate logic)
2. Data is written to a log or table that proves the problem is happening
3. Nobody reads that data in real time
4. A human notices by accident hours later
5. Fix is applied, which correctly addresses the symptom
6. No observability is added to detect the same class of problem next time

**This is the operational definition of "we can't manage what we can't see."**

---

## TO-BE: Metrics Catalog

The following metrics can all be derived from data that already exists in
the system. No new instrumentation infrastructure is required for most of them —
just emit the numbers from code that already runs.

### Tier 1: Critical (detect today's incident in < 5 minutes)

**M-01: bootstrap_ops_rate**
```
Name: bootstrap_ops_total
Type: Counter
Labels: project_id, status (queued|done|in_progress)
Source: orchestrator.py bootstrap_new_specs(), after lifecycle.create_initial()
Why critical: 15 bootstrap-as-done in 30s is the incident. Alert threshold:
              rate(bootstrap_ops_total{status="done"}[5m]) > 5
```

**M-02: lifecycle_write_latency**
```
Name: lifecycle_write_duration_ms
Type: Histogram (buckets: 100, 500, 1000, 5000, 30000)
Labels: spec_id, operation (write|create_initial), result (ok|race|timeout)
Source: lifecycle._cas_loop(), measure wall time per attempt
Why critical: 8 git plumbing calls with no timeout can hang forever.
              p99 > 5000ms → something is blocking
```

**M-03: push_failure_rate**
```
Name: lifecycle_push_failures_total
Type: Counter
Labels: project_id, repo
Source: lifecycle._push_best_effort() — currently logs at DEBUG, change to
        emit a counter AND log at WARNING
Why critical: push failure = ADR-023 multi-machine convergence silently broken.
              Any push failure in a 1-hour window needs to be visible.
```

**M-04: verify_status_sync_verdict_rate**
```
Name: callback_verdict_total
Type: Counter
Labels: project_id, verdict (done|blocked|noop), reason
Source: callback._emit_audit() — the data is already there in JSONL form.
        Add counter emission alongside JSONL write.
Why critical: rate(callback_verdict_total{verdict="blocked"}[30m]) trending up
              = gate is rejecting commits. Detect _subject_implements regressions.
```

**M-05: callback_execution_latency**
```
Name: callback_duration_ms
Type: Histogram
Labels: project_id, result (done|blocked|noop|error)
Source: callback.main(), measure from entry to exit
Why critical: callback is synchronous pueue blocker. If it hangs,
              no new tasks dispatch. p99 > 30s = incident.
```

### Tier 2: Leading Indicators (catch problems before they cascade)

**M-06: pueue_slot_occupancy**
```
Name: pueue_slots_occupied
Type: Gauge
Labels: provider (claude-runner|codex-runner|gemini-runner)
Source: orchestrator main loop, before try_acquire_slot
Why: Slot leak (BUG-162 pattern) visible before it blocks all dispatches
```

**M-07: circuit_breaker_state**
```
Name: circuit_breaker_state
Type: Gauge (0=closed, 1=half-open, 2=open)
Labels: (none)
Source: callback.is_circuit_open()
Why: Binary state → leading indicator if you also track demote_rate
```

**M-08: demote_rate (the real circuit-breaker leading indicator)**
```
Name: callback_demote_total
Type: Counter
Labels: project_id, reason
Source: callback.verify_status_sync(), every time verdict changes from
        in_progress/queued → blocked
Why: Circuit breaker fires at 3/10min. Demote rate at 1/10min is a warning.
     Watch the slope, not just the threshold.
```

**M-09: orchestrator_poll_cycle_duration**
```
Name: orchestrator_poll_cycle_ms
Type: Histogram
Labels: cycle_phase (scan_inbox|scan_queued|bootstrap|dispatch)
Source: orchestrator main loop, wrap each phase in a timer
Why: If poll cycle takes > 60s, the 5-minute dispatch loop becomes 10-minute.
     Tasks wait longer. No one currently knows if cycles are slow.
```

**M-10: git_push_latency_per_project**
```
Name: git_push_duration_ms
Type: Histogram
Labels: project_id
Source: lifecycle._push_best_effort(), currently fire-and-forget
Why: Push latency > 30s on a slow remote causes WT-sync races to compound
```

**M-11: cas_retry_count**
```
Name: lifecycle_cas_retries_total
Type: Counter
Labels: spec_id, attempt_number
Source: lifecycle._cas_loop() already logs at WARNING on attempt 2/3
        Add counter emission
Why: Multiple CAS retries = concurrent writes = multiple machines or callbacks
     competing. Leading indicator of split-brain.
```

**M-12: bootstrap_volume_per_cycle**
```
Name: orchestrator_bootstrap_per_cycle
Type: Gauge (reset each cycle)
Labels: project_id
Source: orchestrator.bootstrap_new_specs(), count per invocation
Why: > 10 bootstraps in a single cycle is suspicious (normal is 0-2).
     This is the direct detection metric for today's incident.
```

### Tier 3: Diagnostic Metrics (useful for postmortems, not alerting)

**M-13: spec_age_by_status**
```
Name: lifecycle_spec_age_hours
Type: Gauge
Labels: project_id, status
Source: lifecycle.list_by_status() + updated_at timestamp
Why: spec in status=in_progress for > 24h = orphan (same class as BUG-162).
     Run as nightly check.
```

**M-14: audit_log_size_growth_rate**
```
Name: callback_audit_log_bytes_total
Type: Counter
Labels: (none)
Source: callback._write_audit(), add len(line) to counter on each write
Why: Audit log growing unboundedly. Detect when it hits disk limits before it does.
```

**M-15: sdk_post_result_error_rate**
```
Name: sdk_post_result_errors_per_hour
Type: Counter (derived from db table)
Labels: project_id
Source: already exists in db.sdk_post_result_errors. Add a periodic reader
        (cron or orchestrator loop) that emits the count since last check.
Why: BUG-188 — this table exists but nobody watches it. 
     > 5 errors/hour = $258/week retries reoccurring.
```

---

## TO-BE: SLOs

The system currently has no SLOs. Here is the minimal viable SLO set.

### SLO-1: Task Dispatch Latency

**What we're measuring:** Time from spec entering `status=queued` in lifecycle
YAML to task appearing in pueue queue.

**SLI:** `(count of tasks dispatched within 10 minutes) / (total tasks dispatched)`

**SLO:** 95% of queued specs dispatched within 10 minutes during operating hours.

**Why 10 minutes:** Orchestrator polls every 5 minutes. Two cycles is the
designed maximum. If it takes longer, something in `scan_queued` is broken.

**Measurement:** `lifecycle_spec_age_hours{status="queued"} > 0.17` (10 min)
counts as an SLO breach for that spec.

**Error budget:** 5% of tasks per month may exceed 10 minutes.
With 100 tasks/month, that's 5 late dispatches before paging.

---

### SLO-2: Callback Correctness

**What we're measuring:** Rate at which callback correctly resolves spec status
(verdict=done or verdict=blocked with valid reason) vs silently failing.

**SLI:** `callback_verdict_total{verdict=~"done|blocked"} /
         (callback_verdict_total{verdict=~"done|blocked|noop"} — noop_terminal)`

**SLO:** 99% of non-terminal callback invocations reach a definitive verdict.

**Why this matters:** 19 bare `except Exception` blocks mean a
large fraction of error paths silently return without emitting any verdict.
The SLI will drop if those exceptions start firing.

**Error budget:** 1% of callbacks may fail silently. With 200 callbacks/month:
2 silent failures before paging.

---

### SLO-3: Lifecycle Write Freshness (Multi-Machine Convergence)

**What we're measuring:** Whether lifecycle pushes succeed (ADR-023 convergence guarantee).

**SLI:** `1 - (lifecycle_push_failures_total / lifecycle_write_total)`

**SLO:** Zero push failures in any 24-hour window.

**Why zero-tolerance:** A push failure means remote HEAD diverges from local
HEAD. Next `git pull` on any machine will either conflict or silently lose the
write. This is the class of failure that causes split-brain status.

**Alert threshold:** ANY push failure in 1 hour → immediate page.

---

### SLO-4: Bootstrap Accuracy

**What we're measuring:** Rate at which bootstrap_new_specs creates lifecycle
YAMLs with correct status (should be `queued` for new specs, never `done` for
live active specs).

**SLI:** `bootstrap_ops_total{status!="done"} / bootstrap_ops_total`

**SLO:** Zero bootstrap-as-done for specs that appear in the active (non-archive)
section of backlog.md.

**Alert threshold:** `rate(bootstrap_ops_total{status="done"}[5m]) > 3`
fires an immediate page. This alert would have caught today's incident at 11:19.

---

### SLO-5: Orchestrator Liveness

**What we're measuring:** Is the orchestrator daemon alive and completing poll cycles.

**SLI:** `time_since_last_completed_poll_cycle`

**SLO:** Poll cycle completes at least once every 10 minutes, 99.9% of hours.

**Measurement:** Orchestrator writes a heartbeat file (or metric) at end of
each main loop iteration. If heartbeat is older than 10 minutes, daemon is
stuck or dead.

**Current gap:** No heartbeat mechanism exists. `systemd` will restart on
crash but not on hang (e.g., `_write_lock` deadlock from lifecycle timeout).

---

## TO-BE: Alert Rules

### Alert Runbook Template

Every alert below follows this structure:
```
Alert Name → Symptom → Immediate Action → Investigation → Resolution
```

### ALERT-001: MassBootstrapAsDone (CRITICAL)

**Condition:** `bootstrap_ops_total{status="done"}` increases by > 3 in 5 minutes

**Symptom:** Multiple live specs are being created with `status=done` in lifecycle,
meaning they will never be dispatched to autopilot.

**Immediate action (first 5 minutes):**
1. `grep "BOOTSTRAP.*status=done" /var/log/dld-orchestrator/orchestrator.log | tail -30`
2. Count affected spec IDs
3. Check `ai/backlog.md` — are these specs in the archive section or active section?
4. If active specs show as done: STOP orchestrator (`systemctl stop dld-orchestrator`)
   to prevent further dispatches on corrupted state

**Investigation:**
- Check `backlog.md` WT vs HEAD: `git diff HEAD -- ai/backlog.md`
- Check if `backlog.md` WT was manually edited just before incident
- Check if a `render_backlog.py` run produced incorrect output

**Resolution:**
- For each corrupted spec: `python3 spec_operator.py revert <spec_id> queued`
- Verify: `python3 -c "import lifecycle; print(lifecycle.read_lifecycle('.', 'SPEC-NNN'))"`
- Restart orchestrator: `systemctl start dld-orchestrator`
- File regression test for this scenario

**Time to detect with alert:** < 5 minutes
**Time to detect without alert:** 4-5 hours (today's incident)

---

### ALERT-002: LifecyclePushFailure (CRITICAL)

**Condition:** `lifecycle_push_failures_total` increments at all (zero tolerance SLO)

**Symptom:** Lifecycle state committed locally but not pushed. Remote HEAD
is stale. Multi-machine consistency broken (ADR-023). Next pull may
conflict or silently overwrite local state.

**Immediate action:**
1. Check push failure message (now promoted to WARNING log, not DEBUG)
2. `git -C <project_dir> status` — is there a diverged branch?
3. Check network/SSH connectivity to git remote
4. Manual push: `git -C <project_dir> push origin develop`

**Investigation:**
- Check git remote reachability
- Check for concurrent pushes from other machines (CAS race extended to remote)
- Check if `_write_lock` prevented intra-process race but remote still diverged

**Resolution:**
- Fix network/auth issue, then: `git -C <project_dir> push origin develop --force-with-lease`
- Verify all lifecycle YAMLs in remote HEAD match local HEAD

**Time to detect with alert:** immediate
**Time to detect without alert:** until next multi-machine conflict (unknown)

---

### ALERT-003: CallbackGateBlockedRateHigh (WARNING)

**Condition:** `rate(callback_verdict_total{verdict="blocked"}[30m]) > 0.5/min`
(more than 30 blocked verdicts per hour sustained)

**Symptom:** Gate is rejecting a high fraction of completed autopilot runs.
Either commit subject convention mismatch (Root 3 from audit) or allowed-files
changes. Tasks are being re-queued and re-run, burning compute.

**Immediate action:**
1. Check audit JSONL: `tail -f callback-audit.jsonl | grep blocked`
2. Look at `reason` field: is it `no_impl_commits` or `no_allowed_files`?
3. Sample 3 affected spec IDs, look at their commits on develop

**Investigation:**
- If `reason=no_impl_commits`: commit subject convention mismatch
  - `git log --oneline develop | grep <spec_id>` — is the ID in subject?
  - Check if project uses `feat(domain): desc (SPEC-NNN)` trailer format
- If `reason=no_allowed_files`: spec has outdated allowed-files list

**Resolution:**
- Convention mismatch: update `_subject_implements` to accept both forms
- Allowed-files mismatch: update spec's `## Allowed Files` section

---

### ALERT-004: OrchestratorHeartbeatMissed (CRITICAL)

**Condition:** Heartbeat file not updated in > 10 minutes

**Symptom:** Orchestrator is stuck (deadlock, hung git call) or dead but systemd
hasn't detected it (hang vs crash distinction). No new tasks will dispatch.

**Immediate action:**
1. `systemctl status dld-orchestrator`
2. If running: `ps aux | grep orchestrator` — is it consuming CPU? (busy) or 0%? (hung)
3. If hung: `kill -9 <pid>` — systemd will restart

**Investigation:**
- Check for `_write_lock` held indefinitely (lifecycle hang)
- Check last log line before heartbeat stopped: what operation was running?
- Check `strace -p <pid>` if available — what syscall is blocking?

**Resolution:**
- Kill hung process, systemd restarts
- Add `timeout=30` to all `lifecycle._run()` calls (see Prevention section)

---

### ALERT-005: CircuitBreakerOpen (CRITICAL)

**Condition:** `circuit_breaker_state == 2`

**Symptom:** 3+ demotes in 10 minutes. All new autopilot completions are being
skipped. The circuit is protecting against runaway re-queue, but production
work has stopped.

**Immediate action:**
1. Check WHY demotes are happening: `grep "DEMOTE\|BLOCKED" callback-debug.log | tail -20`
2. Look at `callback_decisions` table: `SELECT * FROM callback_decisions WHERE demoted=1 ORDER BY ts DESC LIMIT 10;`
3. Identify the common pattern in blocked reasons
4. Fix the underlying cause (convention, allowed-files, etc.)
5. Then: `python3 callback.py --reset-circuit`

**Note:** Circuit breaker is a correct safety mechanism. This alert means "stop
and fix the root cause," not "reset the circuit immediately."

---

### ALERT-006: LifecycleWriteLatencyHigh (WARNING)

**Condition:** `lifecycle_write_duration_ms p99 > 5000ms` over 15-minute window

**Symptom:** Git plumbing calls in `_atomic_write` are slow. 8 subprocess calls
with no timeout can block the `_write_lock` for extended periods. Under lock,
all callback invocations queue behind it.

**Immediate action:**
1. Check git remote latency: `time git -C <project_dir> fetch origin --dry-run`
2. Check disk I/O on VPS: `iostat -x 1 5`
3. Check pueue for backed-up completions waiting for callback

**Investigation:**
- Is this one slow project or all projects?
- Is `git push` the slow step or `git fetch`?
- Is VPS under memory pressure? (`cat /proc/meminfo | grep Available`)

---

## Dashboard Design (Logical, Not Grafana JSON)

### Dashboard 1: Orchestrator Health (Primary On-Call View)

**Purpose:** Answer "is the orchestrator working right now?" in < 30 seconds.

**Panels:**

```
Row 1: LIVENESS
  [Gauge] Heartbeat age (seconds since last poll)  — GREEN < 5min, RED > 10min
  [Gauge] Circuit breaker state                    — GREEN=closed, RED=open
  [Gauge] Pueue slots occupied (per provider)      — number

Row 2: THROUGHPUT (last 1 hour)
  [Counter] Tasks dispatched                        — rate per hour
  [Counter] Tasks completed (done|failed)           — rate per hour
  [Counter] Bootstrap ops (by status)               — ALERT if done spikes

Row 3: CALLBACK VERDICTS (last 1 hour)
  [Stacked bar] verdict rate: done | blocked | noop — should be mostly done
  [Counter] Demote rate                             — leading circuit-breaker signal
  [Histogram] callback_duration_ms p50/p99          — latency health

Row 4: LIFECYCLE WRITES (last 1 hour)
  [Counter] write_lifecycle calls                   — normal operational volume
  [Counter] Push failures                           — should always be 0
  [Histogram] write_duration_ms p99                 — should be < 1000ms
  [Counter] CAS retries                             — > 0 means concurrent writers
```

---

### Dashboard 2: Spec Pipeline Health (For Daily Review)

**Purpose:** "Are specs moving through the pipeline correctly?"

```
Row 1: SPEC STATUS DISTRIBUTION (right now)
  [Pie] Count by status: queued | in_progress | blocked | done
  [Table] Specs in status=blocked > 24h (stale blocked)
  [Table] Specs in status=queued > 30min (dispatch failure)

Row 2: PIPELINE VELOCITY (last 7 days)
  [Line] Specs queued per day
  [Line] Specs done per day
  [Line] Blocked-to-done conversion rate (how often does blocked resolve?)

Row 3: GATE EFFECTIVENESS
  [Table] Top 5 block reasons by frequency
  [Line] Blocked rate per project (per day)
  [Gauge] Gate accuracy: % of done verdicts that are correctly done
          (measure: no subsequent re-queue of done specs)
```

---

### Dashboard 3: Incident Forensics (Postmortem View)

**Purpose:** "What happened during the incident?" — use audit JSONL as primary source.

```
Query: SELECT * FROM callback_audit WHERE ts BETWEEN ? AND ? ORDER BY ts
Annotate: circuit breaker open/close events
Annotate: bootstrap ops with status=done
Show: which specs changed status and when
Cross-reference: task_log for pueue durations
```

This dashboard doesn't exist as a live tool. What it does exist as is the
audit JSONL file. A minimal implementation: a Python script
`scripts/vps/audit_report.py --since "2026-05-23T11:00" --until "2026-05-23T16:00"`
that outputs the incident timeline. This is achievable in < 1 day of work.

---

## Prevention vs Detection Trade-offs

### Prevention (structural — prevents the bug from happening)

| Prevention | Addresses | Cost |
|-----------|-----------|------|
| `bootstrap_new_specs` reads HEAD not WT | Today's incident (Root 1) | 2 LOC change |
| `lifecycle._run()` timeout=30s | Hang detection, lock-up prevention | 1 LOC per call, 8 calls |
| `_push_best_effort` → log.WARNING | ADR-023 push failure visibility | 1 LOC change |
| `assert_clean_lifecycle_tree` pre-cycle check | WT drift detection proactively | ~10 LOC in orchestrator loop |

**When to prefer prevention:** When the fix is < 5 LOC and the failure mode
is clear. These four are all straightforward. Do them now.

**When NOT to rely on prevention alone:** When the failure mode has many
variants (e.g., split-brain has 6 variants across 5 incidents). Prevention
catches the known path; observability catches the unknown-unknown.

### Detection (observability — catches the bug fast when it happens anyway)

| Detection | Catches | Time-to-detect |
|-----------|---------|----------------|
| ALERT-001 (mass bootstrap-as-done) | Today's incident | < 5 min |
| ALERT-002 (push failure) | ADR-023 silent split-brain | immediate |
| ALERT-003 (blocked rate high) | Gate convention regression | < 30 min |
| ALERT-004 (heartbeat missed) | Orchestrator hang | < 10 min |
| ALERT-005 (circuit open) | Already exists — improve runbook | immediate |

**Key insight from today's incident:** Prevention would have stopped the
15 bootstrap-as-done from happening. But observability would have caught it
in 5 minutes instead of 5 hours even if prevention failed. In a system
with this level of accumulated complexity, you need both. Neither alone is
sufficient.

**The honest assessment:** The codebase has accumulated 5 rounds of "prevention"
fixes in this contour. Each fix correctly prevents the specific failure that
triggered it. None of them added observability. The sixth failure will be
caught the same way as the first five — by accident — unless observability is
added now.

---

## What Breaks First in Prod: Ordered Risk Register

Based on direct code analysis and the audit findings:

### Risk 1 — `lifecycle._run()` hangs under `_write_lock` (CRITICAL)

**Code:** `lifecycle.py:77-88` — subprocess.run() with no timeout.
8 git plumbing calls. Each can hang indefinitely if:
- Remote is unreachable (push)
- `.git/` is on a slow/full filesystem
- Another git process holds a lock on `.git/index`

**Impact:** `_write_lock` is a threading.Lock(). One hung subprocess holds
it indefinitely. Every subsequent callback invocation in the same process
blocks at `_write_lock` acquire. Orchestrator continues dispatching tasks.
Pueue completions pile up. All blocking. No alert fires.

**Detection:** Heartbeat monitoring (M-05, ALERT-004).
**Prevention:** `timeout=30` in `_run()`.

---

### Risk 2 — `_push_best_effort` silent failure (HIGH)

**Code:** `lifecycle.py:263-266` — `log.debug("push best-effort failed")`.

At INFO log level (production default), this line is invisible. Multi-machine
consistency (ADR-023) silently breaks. The next git pull on any other machine
that tries to read lifecycle state will either conflict (visible, causes FATAL)
or succeed-with-stale-data (invisible, causes wrong decisions).

**Detection:** Promote to WARNING + emit M-03 counter. ALERT-002.
**Prevention:** none needed — detection is sufficient given the push is best-effort.

---

### Risk 3 — Circuit breaker fires at wrong threshold under convention mismatch (HIGH)

**Code:** `callback.py:699-711` — `_subject_implements` rejects the
`feat(domain): desc (SPEC-NNN Task N)` format used by 460 commits in awardybot
vs 176 using the canonical `feat(SPEC-NNN):` format.

Under sustained awardybot autopilot load: every autopilot completion → callback
called → `_subject_implements` returns False → spec stays blocked → demote
recorded → 3 demotes in 10 minutes → circuit breaker opens → ALL callbacks
paused → all projects' autopilot completions unprocessed.

**This is a cross-project blast radius risk.** One project's commit convention
can circuit-break the entire VDS orchestrator.

**Detection:** ALERT-003 (blocked rate high) with per-project labels.
**Prevention:** Fix `_subject_implements` to accept trailer format.

---

### Risk 4 — `orchestrator.bootstrap_new_specs` reading stale WT (HIGH)

**Code:** `orchestrator.py:295` — `backlog_path.read_text()` reads WT,
not HEAD. Today's incident.

**Detection:** ALERT-001 (mass bootstrap-as-done).
**Prevention:** Change to read from HEAD: `git show HEAD:ai/backlog.md`.

---

### Risk 5 — `assert_clean_lifecycle_tree` blocks orchestrator restart (MEDIUM-HIGH)

**Code:** `orchestrator.py:363` — `lifecycle.assert_clean_lifecycle_tree(pdir)`
raises on dirty WT. Called in `startup_reconcile`.

awardybot and wb currently have dirty `ai/lifecycle/` WTs (audit finding #16).
This means: if the orchestrator is restarted right now, it will FATAL on
startup and will not restart automatically (Restart=on-failure only helps with
process crashes, not Python exceptions before the main loop starts... actually
`on-failure` does restart on non-zero exit, so this would loop-crash-restart).

But in the crash loop, no tasks dispatch. No alert fires for the crash loop.

**Detection:** Systemd unit crash monitoring (`systemctl is-failed`),
ALERT-004 heartbeat.
**Prevention:** Pre-commit check in WT-sync + nightly cron that verifies clean WT.

---

### Risk 6 — SQLite DB isolation missing (MEDIUM)

**Code:** `db.py:19` — `DB_PATH = os.environ.get("DB_PATH", str(Path(__file__).parent / "orchestrator.db"))`.

Any test that doesn't set `DB_PATH` writes to the production database.
`scripts/vps/tests/` has ~100 tests, `conftest.py` has no autouse fixture.
Running these tests in production environment (which currently happens manually
via `run-tests.sh`) can corrupt slot occupancy, task_log, callback_decisions.

**This is not theoretical.** The audit report notes this as an active risk.

**Detection:** Monitor slot occupancy gauge for unexpected spikes (M-06).
**Prevention:** autouse `tmp_db` fixture in `conftest.py` — trivial fix.

---

## Cross-Cutting Implications

### For Domain Architecture

The ops lens confirms the domain audit conclusion: callback.py cannot be
effectively observed because it has 7 responsibilities packed into one module.
Structured metrics require named operations. Operations require identifiable
boundaries. When a single 1374-LOC file handles gate + writer + parser +
audit + circuit-breaker + dispatcher + render, you cannot emit a metric
labeled `operation=gate` without it being a lie — the gate is interleaved
with all other logic.

**Implication for domain redesign:** Each bounded context gets its own
metrics namespace. The gate module emits gate metrics. The writer module
emits write metrics. This is a prerequisite for meaningful observability,
not a nice-to-have.

### For Data Architecture

The three-store status split (lifecycle YAML, backlog.md WT, spec body) means
that a metric like `lifecycle_spec_status_total{status="done"}` can disagree
with `backlog_spec_status_total{status="done"}` derived from backlog.md.

Until there is a single source of truth for status, any dashboard showing
spec counts will be potentially wrong and there is no way to know which
representation is authoritative at query time.

**Implication for data redesign:** SLO-4 (bootstrap accuracy) cannot be
reliably measured until bootstrap reads from HEAD, not WT.

### For API/CLI Design

The `spec_operator.py` tool (manual operator CLI) has no audit trail beyond
`by="operator"` in lifecycle YAML. During incident remediation, a human uses
this tool to revert corrupted specs. But there is no log of which human,
from which machine, at what time, changed what spec to what status.

**Recommendation:** `spec_operator.py` should emit an event via `event_writer`
on every state change, with timestamp, operator identity (hostname+user), and
old/new status. This costs < 5 LOC.

---

## Concerns & Recommendations

### Critical Issues

**[1] No alert on the most dangerous operation in the system.**
`bootstrap_new_specs` can corrupt all spec statuses in one cycle. Today
it did exactly that. Adding M-01 + ALERT-001 would have caught this at 11:19
instead of 16:00. This is the highest ROI ops work available right now.
**Fix:** Add a counter in `bootstrap_new_specs()`, emit to a persistent
counter file (since no Prometheus), alert via `notify_circuit_event()` analog.

**[2] `_push_best_effort` at DEBUG is a production safety defect.**
ADR-023 is a consistency guarantee. Silent push failure breaks that guarantee.
The code comment even names it "best-effort." But from an ops standpoint,
"best-effort with no visibility" is indistinguishable from "broken."
**Fix:** One-line change: `log.debug` → `log.warning`. Add M-03 counter.
Escalate in event_writer if push fails 3 times in 10 minutes.

**[3] No heartbeat = no hang detection.**
The orchestrator can be running (from systemd's perspective) but stuck inside
a git plumbing call that will never return. `Restart=on-failure` won't help
because the process hasn't failed. The only detection today is a human
noticing that no new tasks have dispatched in a while.
**Fix:** Write `scripts/vps/.orchestrator-heartbeat` with current timestamp
at end of each main loop iteration. Cron job every 5 minutes checks freshness.
Page if > 10 minutes stale. This is a 10-line change.

**[4] Audit JSONL is the best data source and nobody reads it.**
`callback-audit.jsonl` has project_id, spec_id, verdict, reason, elapsed_ms
per call. This is sufficient to reconstruct any incident. But today's incident
involved bootstrap, not callback, so the audit log shows the *symptoms*
(already_done_terminal on every subsequent call) not the *cause*.
**Fix:** Add audit logging to bootstrap_new_specs with same format. Then
build `audit_report.py` — a 50-line script that queries the JSONL and prints
a timeline. This alone transforms postmortems from "read 10 log files" to
"run one command."

### Important Considerations

**[5] Minimum viable observability stack.**
The system does not need Prometheus or Grafana. It needs:
- A heartbeat file (10 LOC)
- Counter files per metric (append-only, one line per increment) (20 LOC shared utility)
- A cron-based alerter that reads counter files and sends Hermes events (30 LOC)
- Bootstrap audit in same format as callback audit JSONL

Total implementation: ~100 LOC across 3 files. Can be done in one Spark spec.

**[6] The circuit breaker is the only existing "alert" and it fires too late.**
By the time the circuit opens (3 demotes in 10 minutes), you've already lost
30+ minutes of autopilot throughput and potentially burned compute retrying.
The circuit breaker is the correct *safety mechanism* but a poor *alert*
mechanism. The alert should fire at 1 demote in 10 minutes (warning) so you
can investigate before the circuit opens.

---

## Minimum Viable Ops Hardening (ordered by impact/cost)

This can be done independently of the architectural redesign.

| # | Change | Files | LOC | Incident Prevented/Detected |
|---|--------|-------|-----|---------------------------|
| 1 | `_push_best_effort`: log.debug → log.warning + event | lifecycle.py | 3 | ALERT-002: push failure visibility |
| 2 | Orchestrator heartbeat file write at end of each loop | orchestrator.py | 8 | ALERT-004: hang detection |
| 3 | Heartbeat monitor cron (Hermes event if stale > 10min) | new: heartbeat_monitor.py | 25 | ALERT-004 |
| 4 | Bootstrap counter: emit count to counter file | orchestrator.py | 10 | ALERT-001: mass bootstrap detection |
| 5 | Bootstrap audit: same JSONL format as callback audit | orchestrator.py | 15 | Incident forensics |
| 6 | `lifecycle._run()`: add timeout=30 | lifecycle.py | 8 calls × 1 LOC | Hang prevention |
| 7 | `audit_report.py`: CLI timeline tool | new file | 50 | Postmortem acceleration |
| 8 | Counter-based alert for blocked rate > threshold | new: simple_alerts.py | 40 | ALERT-003 |
| **Total** | | | **~160 LOC** | **5 of 6 critical alerts covered** |

This is achievable in two Spark specs without touching the architectural
decomposition. It does not require Prometheus, Grafana, or any new
infrastructure. It makes the system observable at production minimum-viable
level.

---

## References

- Google SRE Book — "Monitoring Distributed Systems" (Chapter 6): SLI/SLO/SLA hierarchy
- Charity Majors — "Observability vs Monitoring" (Honeycomb): observable systems debug unknown-unknowns
- Audit report: `ai/audit/deep-audit-report.md` — 85 findings, especially Root 4 (invisible infrastructure)
- Architecture agenda: `ai/architect/architecture-agenda.md` — Charity section, confirmed by code analysis
- `scripts/vps/callback.py:263-266` — `_push_best_effort` at DEBUG (confirmed by grep)
- `scripts/vps/lifecycle.py:77-88` — `_run()` without timeout (confirmed by read)
- `scripts/vps/orchestrator.py:295` — backlog WT read (confirmed by read)
- `pyproject.toml:19` — testpaths gap (confirmed by read)
- `.github/workflows/test.yml:54-66` — coverage gate callback only (confirmed by read)
