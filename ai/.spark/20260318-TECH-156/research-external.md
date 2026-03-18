# External Research — Silence Intermediate Notifications During Automated Pipeline Cycle

## Best Practices (5 with sources)

### 1. Notify Only on Terminal Pipeline State (Not Per-Step)
**Source:** [Notifications for workflow runs — GitHub Docs](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/monitoring-workflows/notifications-for-workflow-runs)
**Summary:** GitHub Actions lets users opt into "notify only when a workflow run has failed," suppressing intermediate job-level notifications entirely. The notification fires once, at the pipeline boundary, not per job. Individual jobs can use `if: failure()` guards to stay silent on success.
**Why relevant:** Our pipeline has four discrete steps (spark → autopilot → QA → reflect). Today each step fires a callback notification independently. The right boundary for a "cycle" notification is after the full sequence completes or fails — exactly the GitHub model.

---

### 2. Alert Inhibition — Suppress Child Alerts When Parent Is Active
**Source:** [How to Use Alertmanager Inhibition Rules — OneUptime](https://oneuptime.com/blog/post/2026-01-27-alertmanager-inhibition-rules/view)
**Summary:** Prometheus Alertmanager's inhibition rules: "when a parent (source) alert fires, matching child (target) alerts are silenced." Suppressed alerts still exist in state but are never delivered to receivers. GitLab SRE used this to suppress downstream service alerts when a root cause (DB/network down) is already firing, reducing on-call pages by ~60%.
**Why relevant:** A cycle started by OpenClaw is the "parent." Each pueue-callback completion is a "child." Child notifications should be inhibited while the parent cycle is active. Only errors that break the cycle entirely should punch through.

---

### 3. Environment Variable Toggle for Silent Mode — Universal UNIX Pattern
**Source:** [Bash Scripting Best Practices — OneUptime](https://oneuptime.com/blog/post/2026-02-13-bash-best-practices/view) + [Support disabling notifications — coder/coder #15513](https://github.com/coder/coder/issues/15513)
**Summary:** Production systems use env-var toggles for notification control: `[[ "${DEBUG:-}" == "true" ]] && set -x`, `CODER_NOTIFICATIONS_ENABLED=false`. The coder project shipped `CODER_NOTIFICATIONS_ENABLED` (default `true`) to let operators silence the notification subsystem without code changes. `NR_INSTALL_SILENT` controls the New Relic installer, `NUT_QUIET_INIT_UPSNOTIFY` controls the NUT daemon.
**Why relevant:** `pueue-callback.sh` already has a `SKIP_NOTIFY` flag (lines 238-263) used for `reflect` and secondary QA. Extending it to check a cycle-scoped sentinel is idiomatic and zero-risk. However: env vars set in the orchestrator/inbox-processor do NOT survive to `pueue-callback.sh` (different process). A file-based sentinel is required for cross-process signaling.

---

### 4. Sentinel File for Pipeline Ownership (Cross-Process Silent Mode)
**Source:** [Silent mode for the install script — New Relic](https://docs.newrelic.com/docs/apm/agents/php-agent/advanced-installation/silent-mode-install-script-advanced) + [NUT_QUIET_INIT_UPSNOTIFY — networkupstools/nut PR #2136](https://github.com/networkupstools/nut/pull/2136) + [How to prevent concurrent multi-stage pipelines — StackOverflow](https://stackoverflow.com/questions/67489823)
**Summary:** A file or env var is written by the process initiating a pipeline to suppress informational output in child processes while keeping error output active. The child process checks for the sentinel at the point of notification decision. This pattern is decades old in Unix tooling. File-based sentinels survive subprocess spawning (unlike env vars); Azure Pipelines "exclusive lock" uses the same ownership concept for full pipeline duration.
**Why relevant:** A file `ai/openclaw/cycle-{spec_id}.lock` written by the cycle initiator and checked by `pueue-callback.sh` before calling `python3 notify.py`. The lock holds for the full spark → autopilot → QA → reflect chain. The callback skips notification when the lock file exists AND the result is not an error.

---

### 5. Message Aggregator Pattern — Collect Then Deliver as One
**Source:** [Building a batched notification engine — Knock](https://knock.app/blog/building-a-batched-notification-engine) + [How to Create Message Aggregator — OneUptime](https://oneuptime.com/blog/post/2026-01-30-message-aggregator/view)
**Summary:** The Message Aggregator pattern (Enterprise Integration Patterns) collects individual messages by a correlation key until a "completeness" condition is met, then emits a single aggregated message. Knock's production implementation uses a correlation ID + batch window. Batch closes on explicit flush OR timeout; on close, one higher-density notification is delivered. Errors short-circuit: no buffering for critical paths.
**Why relevant:** In our pipeline the correlation key is the `spec_id`. Each step result is already being buffered as JSON event files in `ai/openclaw/pending-events/` (callback Step 6.8). When the final step (reflect) completes, OpenClaw reads those events and fires one summary message. This is the Message Aggregator pattern already partially in place — we just need to suppress the intermediate Telegram messages that currently deliver in parallel.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| Sentinel file (`cycle-{spec_id}.lock`) | — | Zero dependencies, atomic with `mkdir -p`, survives subprocess boundaries, readable by bash + Python | Requires cleanup on crash (trap EXIT / orchestrator watchdog) | Cycle ownership marker, cross-process suppress signal | [New Relic silent mode](https://docs.newrelic.com/docs/apm/agents/php-agent/advanced-installation/silent-mode-install-script-advanced) |
| SQLite column `cycle_owner` on `project_state` | — | Already using `db.py` + SQLite; crash-safe (stale lock visible in DB); queryable; SSOT | Requires schema migration; adds DB write per cycle start/end | Central cycle ownership store, crash-safe lock | Existing `db.py` / `schema.sql` |
| Env var `NOTIFY_CYCLE_OWNER` | — | Trivial, zero I/O | Does NOT survive subprocess boundaries — `pueue-callback.sh` is a fresh process per pueue task; env set by orchestrator is invisible to callback | Useless for cross-process suppression | [coder CODER_NOTIFICATIONS_ENABLED](https://github.com/coder/coder/issues/15513) |
| JSON event files (`ai/openclaw/pending-events/`) | — | Already implemented (callback Step 6.8); idempotent; readable by any process; OpenClaw already polls them | Requires file polling, not push; does not directly suppress notifications | Async event aggregation for OpenClaw summary message | Existing `pueue-callback.sh` Step 6.8 |

**Recommendation:** Sentinel file (`ai/openclaw/cycle-{spec_id}.lock`) for the first implementation. No schema change, no new dependencies. Already idiomatic with the existing event-file pattern in `ai/openclaw/`. Per-spec naming (not per-project) prevents cross-spec interference when two specs run concurrently on the same project. Migrate to SQLite column only if stale-lock crashes become a real operational problem.

---

## Production Patterns

### Pattern 1: GitHub Actions — Terminal-Only Notification via `if: failure()` + `workflow_run`
**Source:** [How to Configure GitHub Actions Notifications — OneUptime](https://oneuptime.com/blog/post/2026-02-02-github-actions-notifications/view)
**Description:** Individual jobs within a workflow have `if: failure()` conditions on their notify steps — intermediate steps are silent on success. A parent `workflow_run` event triggers a downstream "aggregator" workflow that fires one consolidated message with the final status. Two levels: step-level silence + pipeline-level summary.
**Real-world use:** Standard pattern in GitHub Actions; used by projects like facebook/react, kubernetes/kubernetes for PR CI notifications.
**Fits us:** Yes — maps directly. Intermediate pueue callbacks = individual jobs (silent when cycle lock present + step is not error). OpenClaw's final report = `workflow_run` aggregator (fires one message at cycle end after reading `pending-events/`).

---

### Pattern 2: Prometheus Alertmanager Inhibition Rules
**Source:** [Prometheus Alertmanager Best Practices — Sysdig](https://www.sysdig.com/blog/prometheus-alertmanager) + [How we improved on-call life by reducing pager noise — GitLab Blog](https://about.gitlab.com/blog/reducing-pager-fatigue-and-improving-on-call-life/)
**Description:** Source alert (parent) inhibits target alerts (children) when both share matching labels. Stateful: when the parent clears, children re-activate. GitLab SRE applied this to suppress downstream service alerts while a root cause alert is active, cutting on-call page volume by ~60%.
**Real-world use:** GitLab.com SRE (2022 blog post). Standard pattern in any Prometheus/Grafana monitoring stack with multi-service dependency chains.
**Fits us:** Conceptually yes. The analogy: `cycle_active=true` for a project inhibits intermediate notifications. The "parent clears" event is the reflect completion or a hard failure. Implementation is not Alertmanager, but the stateful suppression logic (`[[ -f cycle.lock ]]`) is the same principle.

---

### Pattern 3: Skill Allowlist in Callback (Current Pattern, Extend It)
**Source:** Existing `pueue-callback.sh` lines 238-263 (internal codebase)
**Description:** The existing callback already implements selective suppression via a `SKIP_NOTIFY` boolean that is set based on `$SKILL` value and task label patterns. `reflect` is always suppressed; secondary QA from inbox is suppressed. This is the allowlist/denylist pattern — whitelist the skills that notify, or blacklist those that don't.
**Real-world use:** Jenkins `post { success { ... } failure { ... } }` section — only specific outcome conditions trigger notifications. GitLab CI `only: [failure]` on notification jobs.
**Fits us:** Yes, and it's already in place. The extension: when a cycle lock file exists, add `spark`, `qa`, and `reflect` (the intermediate steps) to the suppression list, leaving only errors and `autopilot` (the main work step) as candidates. Or suppress all non-error notifications during cycle.

---

### Pattern 4: Sentinel File for Silent Mode (Cross-Process)
**Source:** [Silent mode for install script — New Relic](https://docs.newrelic.com/docs/apm/agents/php-agent/advanced-installation/silent-mode-install-script-advanced) + [NUT_QUIET_INIT_UPSNOTIFY — networkupstools/nut PR #2136](https://github.com/networkupstools/nut/pull/2136)
**Description:** A file (`NR_INSTALL_SILENT` file, or a `.quiet` sentinel) is created by the outer automation process before invoking child scripts. Each child script checks for the file at the notification decision point. If present, informational output is suppressed; error output is always active. Cleanup uses `trap EXIT` in bash. File naming conventions use the owning process ID or job ID to prevent cross-job interference.
**Real-world use:** New Relic PHP agent installer (Puppet/Chef automation at scale), Network UPS Tools daemon (Linux UPS management), Oracle Grid Infrastructure installer.
**Fits us:** Yes — directly applicable. `inbox-processor.sh` or the OpenClaw integration writes `ai/openclaw/cycle-{spec_id}.lock`; `pueue-callback.sh` checks it; orchestrator watchdog removes stale locks on restart.

---

## Key Decisions Supported by Research

1. **Decision:** Use cycle-scoped sentinel file, not a global notification toggle
   **Evidence:** Pattern 1 (GitHub) and Pattern 2 (Alertmanager) both scope suppression to a specific pipeline run, not globally. A global toggle would suppress error notifications — violating the hard requirement. Per-cycle scope is the production standard across all surveyed systems.
   **Confidence:** High

2. **Decision:** Errors always punch through — no suppression on failure
   **Evidence:** Every CI/CD system surveyed (GitHub Actions `if: failure()`, Alertmanager inhibition, Knock batch engine, Grafana grouping) delivers error notifications regardless of aggregation settings. The Knock batch engine explicitly short-circuits on errors (no buffering for critical paths). Universal convention: silence = in-progress/success, noise = problem.
   **Confidence:** High

3. **Decision:** Sentinel file in filesystem over env var for cross-process signaling
   **Evidence:** Env vars exported in the orchestrator shell do NOT reach `pueue-callback.sh` (Pueue spawns it as a fresh process with its own env). New Relic, NUT, and Oracle installers all use file-based sentinels for exactly this reason — cross-process signaling in bash pipelines where env inheritance is unreliable.
   **Confidence:** High

4. **Decision:** Suppression logic lives in `pueue-callback.sh`, not in `notify.py`
   **Evidence:** The callback is the single routing point for all skill completions. `notify.py` is a dumb transport. Suppression belongs at the routing decision layer — consistent with how `SKIP_NOTIFY` is already implemented for `reflect` (line 241) and secondary QA (line 248) in the existing callback. Adding one `[[ -f cycle.lock ]] && SKIP_NOTIFY=true` check follows the established pattern without touching the transport layer.
   **Confidence:** High

5. **Decision:** Cycle owner (inbox-processor or OpenClaw hook) writes the lock; reflect-success or any failure removes it
   **Evidence:** Azure Pipelines exclusive lock and DataOps.live pipeline lock patterns both tie lock lifetime to the full pipeline run. The lock must span the entire spark → autopilot → QA → reflect chain. Per-spec file naming (`cycle-{spec_id}.lock`) avoids interference between concurrent specs on the same project.
   **Confidence:** Medium (concurrent multi-spec cycles on same project is an edge case; the per-spec naming mitigates it, but the orchestrator's existing single-slot-per-project model already prevents true concurrency)

---

## Research Sources

- [Notifications for workflow runs — GitHub Docs](https://docs.github.com/en/actions/monitoring-and-troubleshooting-workflows/monitoring-workflows/notifications-for-workflow-runs) — "notify only on failure" model; pipeline-level vs job-level notification boundaries
- [How to Use Alertmanager Inhibition Rules — OneUptime](https://oneuptime.com/blog/post/2026-01-27-alertmanager-inhibition-rules/view) — parent-child alert suppression, stateful inhibition, label-matching
- [How we improved on-call life by reducing pager noise — GitLab Blog](https://about.gitlab.com/blog/reducing-pager-fatigue-and-improving-on-call-life/) — 60% pager noise reduction by grouping alerts by root cause; production SRE data
- [Building a batched notification engine — Knock](https://knock.app/blog/building-a-batched-notification-engine) — correlation ID + batch window, flush on completion, error short-circuit
- [Silent mode for the install script — New Relic](https://docs.newrelic.com/docs/apm/agents/php-agent/advanced-installation/silent-mode-install-script-advanced) — `NR_INSTALL_SILENT` file-based sentinel for cross-process notification suppression in Puppet/Chef automation
- [Support disabling notifications — coder/coder #15513](https://github.com/coder/coder/issues/15513) — `CODER_NOTIFICATIONS_ENABLED` env var, production feature flag for notification subsystem; also shows why env vars are the right abstraction for in-process control
- [NUT_QUIET_INIT_UPSNOTIFY — networkupstools/nut PR #2136](https://github.com/networkupstools/nut/pull/2136) — daemon-level quiet mode via env var and file, suppress informational noise while keeping errors active
- [Bash Scripting Best Practices — OneUptime](https://oneuptime.com/blog/post/2026-02-13-bash-best-practices/view) — env-var controlled behavior in bash; `set -euo pipefail`; process boundary considerations
- [Prometheus Alertmanager Best Practices — Sysdig](https://www.sysdig.com/blog/prometheus-alertmanager) — grouping, silencing, throttling, inhibition in production monitoring at scale
- [Group alert notifications — Grafana Docs](https://grafana.com/docs/grafana/latest/alerting/fundamentals/notifications/group-alert-notifications) — grouping reduces alert noise; error-severity alerts bypass grouping windows
- [How to Configure GitHub Actions Notifications — OneUptime](https://oneuptime.com/blog/post/2026-02-02-github-actions-notifications/view) — `if: failure()` step guards, `workflow_run` aggregation pattern
- [How to Create Message Aggregator — OneUptime](https://oneuptime.com/blog/post/2026-01-30-message-aggregator/view) — Message Aggregator EIP pattern, correlation ID, completeness check
