# Feature: [TECH-198] Heartbeat liveness fix + per-session reaper for wedged claude-runner sessions

**Priority:** P1 | **Date:** 2026-06-13

> **Lifecycle state** is tracked in `ai/lifecycle/TECH-198.yaml` (ARCH-186).
> Callback is the single writer; status/blocked_reason/transitions live there.

## Why

Incident 2026-06-13 (pueue #574, `awardybot:FTR-1185`): the autopilot session finished all work — feature branch merged to develop (`8eb4202d`) and **pushed to origin** — then the Agent SDK stream **wedged**. The model issued a batch of tool-calls in one `AssistantMessage` at 12:44:57, the tools executed (a commit landed at 12:54:23, 10 min later), and the **next** `AssistantMessage` never arrived — the stream stalled waiting on model output. The session stayed `Running` for ~30 min holding compute slot 1, until a manual `pueue kill 574`. The **only** automatic backstop is `TIMEOUT_SECONDS=5400` (90 min hard limit) — a wedged session burns a slot and Opus compute for up to 90 min before reaping.

Two independent defects enabled this:

1. **The per-session heartbeat lies about liveness.** `claude-runner._write_heartbeat` is called **only** inside the `AssistantMessage` branch (`claude-runner.py:258`, after `turn_count += 1`). During a long tool-execution phase (several Bash/tests/commits driven by one assistant turn) `updated_at` in `logs/{project}-{ts}.heartbeat.json` freezes even though the session is actively working — exactly what we saw (heartbeat froze 12:44:57, commit at 12:54:23). Consequences: (a) the heartbeat is **useless as a liveness signal** — you cannot safely kill on staleness because you'd reap working sessions; (b) it **misleads diagnosis** (it looked dead at 12:44 while the session was alive until 12:54).

2. **Nobody consumes the per-session heartbeat.** `heartbeat_monitor.py` watches **only** `scripts/vps/.orchestrator-heartbeat` (the orchestrator's own liveness, cron `*/5`). The `logs/*.heartbeat.json` files written per session are read by no one. There is no reaper that detects a `Running` claude-runner task whose heartbeat has gone stale and kills it.

Cost of doing nothing: every wedged session holds a compute slot (1 of 2 claude slots) and burns Opus until the 90-min timeout, with no early signal. Slots are the scarce resource — a single zombie halves claude throughput for up to 1.5h.

## Context

- **SDK loop** (`claude-runner.py:238-262`): `async for message in query(...)` under `async with asyncio.timeout(TIMEOUT_SECONDS)`. Message types seen: `AssistantMessage`, `TaskNotificationMessage`, `ResultMessage`, plus tool-result-bearing messages (`UserMessage`/`SystemMessage`). Heartbeat write is wired **only** into the `AssistantMessage` branch.
- **Heartbeat file** (`claude-runner.py:111-136`, `:163-167`): name = `{project_name}-{ts_label}.heartbeat.json`, where `project_name = Path(project_dir).resolve().name` and `ts_label = time.strftime("%Y%m%d-%H%M%S")` (**1-second resolution**). Fields: `turn`, `elapsed_s`, `last_tool`, `started_at` (ISO), `model`, `updated_at` (ISO). Written atomically (tmp + `os.replace`).
- **Kill path is clean.** On `pueue kill`, the daemon fires `callback.py` with `result="Failed"`; callback Step 1-2 (`callback.py:~1338-1349`) calls `db.release_slot(pueue_id)` + `db.finish_task(pueue_id, "failed", 1)` and updates project phase. **A reaper that calls `pueue kill` needs no slot/lifecycle bookkeeping of its own** — callback handles it. (Lifecycle: callback gate is fail-closed; a killed session with merged+pushed work auto-closes `done`, otherwise stays `queued`/`blocked` — correct, see FTR-1185 where callback auto-closed `done`.)
- **Existing watchdog is NOT a substitute.** `orchestrator.release_orphan_slots()` (BUG-162, `orchestrator.py:204-227`, every main-loop cycle) frees slots whose pueue task is **dead** (gone from `pueue status`). The reaper targets the opposite: a task that is **alive** (`Running`) but **wedged**. Different failure, different mechanism — no overlap.
- **pueue parsing prior art**: `orchestrator.get_live_pueue_ids()` (`orchestrator.py:109-139`) handles the `{"Running": {...}}` status-dict shape; `callback._skill_from_pueue_command()` (`callback.py:145-196`) parses `run-agent.sh <project_dir> <provider> <skill> <task>` from `command`/`original_command` and extracts project/skill; label format `{project_id}:{task_label}`.
- **event_writer signature is ambiguous and MUST be verified before wiring.** `heartbeat_monitor.py:44` calls `notify("dld", "ORCHESTRATOR_STALE: ...")` (2 positional args), but the scout read `event_writer.notify(project_path, skill, status, message, artifact_rel="")` (5-param). One is stale. **Task 2 must read `event_writer.py` and call `notify` with the actual current signature** — do not assume.

---

## Scope

**In scope:**
- **Layer A — heartbeat granularity** (`claude-runner.py`): update the heartbeat on **every** message in the SDK loop (not only `AssistantMessage`), so `updated_at` reflects real stream activity (tool-result messages between assistant turns keep it fresh). Preserve `turn`/`last_tool` semantics (`turn_count` still increments per `AssistantMessage`; `last_tool` still tracked from tool-use blocks).
- **Layer B — per-session reaper** (`heartbeat_reaper.py`, new): cron-driven. For each `Running` task in group `claude-runner`, locate its heartbeat file (match by project **and** cross-check `started_at` against the pueue `Running.start` to disambiguate same-project collisions), and if `updated_at` is stale beyond threshold AND a process-liveness cross-check confirms the session is idle → `pueue kill` + Hermes notify.
- **Reaper false-kill guards**: (1) **grace period** from task start (skip while too young / heartbeat not yet written); (2) **process-liveness cross-check** before kill — confirm no active tool subprocess / near-zero CPU under the runner's `claude` PID, so a single legitimately-long tool call (e.g. a 20-min test run that produces no SDK messages) is NOT reaped.
- `setup-vps.sh`: install the reaper cron alongside `heartbeat_monitor.py`.
- Regression tests for Layer A (heartbeat updates on tool-result messages) and Layer B (stale detection, grace skip, collision disambiguation, kill decision) — real files/processes, no mocks (ADR-013).

**Out of scope:**
- Raising/lowering `TIMEOUT_SECONDS` (90-min hard limit stays — palliative, untouched).
- Root-causing **why** the SDK stream wedges (model/CLI/SDK-level hang) — reaper treats it as a black box.
- Autopilot scope-creep / not-stopping-on-done — separate spec **BUG-199**.
- Reaping non-`claude-runner` groups (codex/gemini/night-reviewer) — claude-runner only for now; generalise later if needed.

---

## Impact Tree Analysis

### Step 1: UP — who uses?
- `claude-runner._write_heartbeat` — internal to `run_task`; entry-point script, no Python importers. ✓
- `heartbeat_reaper.py` (new) — invoked only by cron (setup-vps.sh). No importers. ✓
- `pueue kill` side-effect → `callback.py` main dispatch (already handles Failed/killed). ✓

### Step 2: DOWN — what depends on?
- Layer A → no new deps (same `_write_heartbeat`, called from more branches).
- Layer B reaper → `subprocess` (`pueue status --json`, `pueue kill`, `ps`/`/proc` for CPU/child check), `event_writer.notify`, stdlib `json`/`datetime`/`pathlib`. Reuses pueue-status parsing shape from `orchestrator.get_live_pueue_ids`.

### Step 3: BY TERM
- `_write_heartbeat(` → `claude-runner.py:111` (def), `:258` (call). Layer A adds call site(s) covering all messages.
- `.heartbeat.json` → `claude-runner.py:123` (writer). New reader: `heartbeat_reaper.py`.
- `heartbeat_monitor.py` → `setup-vps.sh:~147-156` (cron). Reaper cron added adjacent.

### Step 4: CHECKLIST
- Tests: `scripts/vps/tests/` (new `test_heartbeat_reaper.py`; extend runner heartbeat coverage). ✓
- `dependencies.md`: add `heartbeat_reaper.py` section + reverse-pointers (claude-runner heartbeat, event_writer, setup-vps cron). ✓
- No migrations / edge functions. ✓

### Step 5: DUAL SYSTEM
- Heartbeat is the data source; reaper the new reader. Layer A MUST land with/before Layer B — the reaper's safety (tight threshold) depends on the heartbeat being a truthful liveness signal. See Approaches.

---

## Approaches

**Layer A — where to write the heartbeat.** Chosen: write once per loop iteration (top of `async for`, for every message), updating `last_tool` when a tool-use block is seen and `turn_count` only on `AssistantMessage`. Rejected: adding a separate `UserMessage`-only branch — brittle to SDK message-type naming; "every message" is the simplest truthful signal.

**Layer B — extend `heartbeat_monitor.py` vs new script.** Chosen: **new `heartbeat_reaper.py`**. `heartbeat_monitor` is a global orchestrator-liveness check (10-min threshold, 2 args); the reaper is per-session, needs pueue enumeration + process introspection + kill authority — different blast radius and cadence. Keeping them separate keeps each small and auditable.

**Layer B — stale threshold.** This is the key tension and depends on Layer A:
- *Naïve high threshold (scout suggested 60 min)* — safe but slow; assumed the broken AssistantMessage-only heartbeat. Once Layer A lands, healthy sessions refresh the heartbeat on every tool result (seconds-to-minutes apart), so a much tighter threshold is safe.
- *Tight threshold (~15 min)* — would catch this incident in ~15 min instead of 90, BUT a single legitimately-long tool call (e.g. a 20-min test suite, no SDK messages during it) could trip it.
- **Chosen: moderate threshold (~25-30 min) + process-liveness cross-check before kill.** The cross-check (no live tool subprocess + near-zero CPU under the `claude` PID over a short sampling window) distinguishes "wedged" (idle, no children — the incident) from "running a long tool" (active child/CPU). With the cross-check, a tighter threshold is safe; without it, keep the threshold above the longest plausible single tool. Final threshold + grace values are a Task-1 decision to be justified in the spec body, defaulting to **GRACE=5min, STALE≈25min, cron `*/5`**. If the team prefers a no-introspection design, fall back to STALE=60min (still 30 min ahead of the hard timeout).

**Same-project collision.** `ts_label` is 1-second; two same-project sessions starting in the same second collide on the heartbeat filename (second overwrites first). Mitigation in scope: reaper cross-checks heartbeat `started_at` vs pueue `Running.start`; if no heartbeat file matches a `Running` task within tolerance, do NOT kill (fail-open — never reap on ambiguity). A follow-up to make `ts_label` unique (append pueue id / pid) is noted in Reflect, not done here.

---

## Tasks

1. **Layer A — heartbeat granularity** (`claude-runner.py`): move/duplicate the `_write_heartbeat` call so it fires for every message in the SDK loop; keep `turn_count` incrementing only on `AssistantMessage` and `last_tool` tracked from tool-use blocks. Verify `updated_at` advances during a multi-tool assistant turn.
2. **Layer B — reaper** (`heartbeat_reaper.py`, new): enumerate `Running` claude-runner pueue tasks; match heartbeat file by project + `started_at` cross-check; apply grace period; on stale-beyond-threshold + idle process cross-check → `pueue kill` + `event_writer.notify` (verify signature first). Fail-open on any ambiguity. Keep file < 400 LOC.
3. **Cron install** (`setup-vps.sh`): add reaper cron next to `heartbeat_monitor.py` (idempotent `crontab -l | grep -v ...; echo line` pattern), logging to `/var/log/dld-orchestrator/heartbeat-reaper.log`.
4. **Tests** (`scripts/vps/tests/`): Layer A — heartbeat `updated_at` advances on tool-result messages without a new AssistantMessage; Layer B — stale detection, grace-period skip, collision disambiguation (fail-open), idle-vs-busy process cross-check, kill decision. Real deps (ADR-013).
5. **Docs**: `dependencies.md` reaper section + reverse-pointers; note ts_label-uniqueness follow-up in `ai/reflect/upstream-signals.md`.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row.
     DO NOT EDIT THIS BLOCK manually after autopilot starts. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/claude-runner.py` — Task 1: per-message heartbeat write (modify)
- `scripts/vps/heartbeat_reaper.py` — Task 2: new per-session reaper (create)
- `scripts/vps/setup-vps.sh` — Task 3: reaper cron install (modify)
- `scripts/vps/tests/test_heartbeat_reaper.py` — Task 4: reaper tests (create)
- `scripts/vps/tests/test_claude_runner_heartbeat.py` — Task 4: Layer A heartbeat-granularity test (create)
- `.claude/rules/dependencies.md` — Task 5: reaper section + reverse-pointers (modify)
- `ai/reflect/upstream-signals.md` — Task 5: ts_label-uniqueness follow-up signal (modify)

---

## Tests

1. **Layer A — heartbeat advances during a multi-tool turn.** Drive `_write_heartbeat` from a simulated message sequence (AssistantMessage with N tool-use blocks → multiple tool-result messages, no second AssistantMessage); assert the heartbeat file's `updated_at` advances on the tool-result messages and `turn` stays at the AssistantMessage count. (Real file I/O, tmp dir.)
2. **Layer B — stale-beyond-threshold idle session is killed.** Given a fake `Running` claude-runner pueue task (stub `pueue status --json` via a real subprocess/fixture) and a heartbeat file with `updated_at` older than STALE and a matching `started_at`, with the process cross-check reporting idle → reaper issues `pueue kill <id>` and fires `notify`. Assert kill + notify called with correct id/args.
3. **Layer B — fresh session NOT killed.** Heartbeat `updated_at` within threshold → no kill.
4. **Layer B — grace period.** Task `Running.start` younger than GRACE (or no heartbeat file yet) → no kill, no error.
5. **Layer B — busy long-tool session NOT killed.** Heartbeat stale beyond threshold BUT process cross-check reports an active child / non-trivial CPU → no kill (false-kill guard).
6. **Layer B — same-second collision fail-open.** Two `Running` same-project tasks, one heartbeat file; reaper cannot unambiguously match `started_at` → does NOT kill either (fail-open).

---

## Blueprint Reference

Infrastructure reliability (DLD orchestrator). No business-blueprint domain. Hardens compute-slot availability — the scarce resource for the 2-claude-slot VPS pipeline. Relates to BUG-162 (orphan-slot watchdog, complementary) and TECH-197 (timeout observability — this adds early reaping before the 90-min timeout).
