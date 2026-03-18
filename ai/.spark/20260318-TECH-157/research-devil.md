# Devil's Advocate — Wake OpenClaw Immediately After Pending-Event Write (TECH-157)

## Why NOT Do This?

### Argument 1: `openclaw` binary is not on PATH in the callback environment
**Concern:** `pueue-callback.sh` runs under the Pueue daemon with a minimal environment.
The script sources `scripts/vps/.env` (which only contains `TELEGRAM_BOT_TOKEN`,
`TELEGRAM_CHAT_ID`, `DB_PATH`) and the local `venv/bin`. The `openclaw` binary does not
appear in any standard location: not in `/home/dld/.local/bin/`, `/usr/local/bin/`,
`/usr/bin/`, or the venv. Without explicit PATH injection, `command -v openclaw` will fail
silently — and `|| true` will swallow it, leaving us with a silent no-op. We'd believe the
wake is firing while it never does.
**Evidence:** `scripts/vps/.env` contains only 3 vars. Glob of `/home/dld/.local/bin/openclaw*`,
`/usr/local/bin/openclaw*`, `/usr/bin/openclaw*` all return empty. No PATH-setting for openclaw
in `orchestrator.sh` or `pueue-callback.sh`.
**Impact:** High
**Counter:** Locate the actual `openclaw` binary path (likely `~/.nvm/`, or a non-standard
install dir), then either add it to PATH in `.env` or use the full absolute path in the call:
`/path/to/openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" || true`.
Guard with `if command -v openclaw &>/dev/null || [[ -x "$OPENCLAW_BIN" ]]; then`.

---

### Argument 2: `openclaw gateway wake` can hang for 2 minutes and block Pueue's callback pipeline
**Concern:** The cron history in `~/.openclaw/cron/runs/03b6b7fb-*.jsonl` shows that OpenClaw
gateway responses sometimes take **120 seconds**: three consecutive runs logged `durationMs:
120146`, `120134`, `115836`. If `openclaw gateway wake` also blocks waiting for a gateway
response, the pueue-callback.sh execution will stall for 2 minutes. Pueue serializes callbacks
— the next task cannot complete while a callback is hanging. With 3 concurrent agents and a
chain of autopilot→QA→reflect, three callbacks can stack, blocking the queue for 6+ minutes.
**Evidence:** `~/.openclaw/cron/runs/03b6b7fb-fe18-4405-b3d1-f27d59eb7f09.jsonl` lines 11-13:
`durationMs: 120146`, `120134`, `115836`. These are LLM inference timeouts, but they confirm
the gateway HTTP endpoint can be unresponsive for sustained periods. `openclaw.json:152-159`:
gateway on port 18789, mode local, bind loopback — HTTP call with no documented timeout flag.
**Impact:** High
**Counter:** Run the wake in a background subshell with an explicit timeout:
`timeout 5 openclaw gateway wake --mode now 2>>"$CALLBACK_LOG" &` (background + timeout 5s).
`|| true` alone does NOT protect against hanging — it only handles non-zero exit codes.

---

### Argument 3: `--mode now` semantics are unknown — could trigger immediate LLM inference, not just "ring the doorbell"
**Concern:** `wakeMode: "now"` in the cron job definition controls when the scheduled job fires.
But `openclaw gateway wake --mode now` as a CLI call is undocumented in the codebase —
there is zero usage of this command in any script, no man page, no source. If `wake --mode now`
triggers a full LLM inference cycle synchronously (as the cron job does at 10-120 seconds each),
the callback will block. Conversely, if it's a pure "ring doorbell" HTTP ping (<100ms), the
risk is low. We cannot verify this from available evidence.
**Evidence:** `grep -r "openclaw gateway" /home/dld/projects/dld` returns zero results in any
script. The only reference is in the inbox file `done/20260318-openclaw-wake-on-cycle-complete.md`
(which is the feature request itself). No help text or flag reference found.
**Impact:** High — unknown surface area
**Counter:** Before implementing, run `openclaw gateway wake --help` to document behavior.
If synchronous inference: use background + timeout. If pure HTTP ping: safe to run inline.

---

### Argument 4: Cron + immediate wake creates double-processing with a tight race window
**Concern:** The cron job fires every 5 minutes. If wake fires at T=0 (callback) and cron
fires at T=0 to T=5 (scheduled), both will see the same `pending-events/*.json` files.
OpenClaw reads them and calls `--mark-processed` atomically per `openclaw-artifact-scan.py:136-140`
(rename to `processed-events/`). But rename is not atomic against two concurrent readers: if
cron wakes OpenClaw at T=4:50 and the callback wake hits at T=5:01, two OpenClaw sessions may
both call `--mark-processed` before either rename completes. Result: duplicate cycle reports to
the user.
**Evidence:** `openclaw-artifact-scan.py:136-140` — `event_file.rename(target)` for each `.json`
in `events_dir.glob("*.json")`. No file lock, no atomic test-and-rename. Current cron schedule:
`everyMs: 300000` (every 5 minutes), confirmed in `cron/jobs.json`.
**Impact:** Medium — duplicate notifications are annoying but not data-corrupting
**Counter:** The race window is narrow (OpenClaw must be processing at the exact moment the
callback fires). Accept the risk for MVP; if duplicates observed, add a `.lock` file guard or
use `os.replace()` + existence check before rename.

---

### Argument 5: Per-project wake fires even when autopilot/QA/reflect runs for OTHER projects
**Concern:** Step 6.8 already conditions event writes on `"$SKILL" == "autopilot" || "qa" || "reflect"`.
The proposed wake would also be conditioned on `EVENT_FILE` being written. However, the
`openclaw gateway wake` call has no per-project argument in the feature request — it sends a
global wake to OpenClaw. If project `awardybot` finishes its autopilot, OpenClaw wakes for the
`dld` cron session, which then scans `dld`'s pending-events and finds nothing new (it's checking
the wrong project). OpenClaw currently only has a single cron job mapped to the `dld` project
session (`topic:7`). Multi-project wake is unsupported today.
**Evidence:** `cron/jobs.json`: only one job `dld-openclaw-artifact-check`, `sessionKey:
"agent:main:telegram:group:-1003730735152:topic:7"`. No job for awardybot, dowry, plpilot.
**Impact:** Low for now (only `dld` project has an OpenClaw artifact check job), but escalates
when other projects are onboarded.
**Counter:** Accept current limitation. Document: wake is only meaningful for the project whose
OpenClaw cron session exists. For TECH-157 scope (`dld` project only), this is fine.

---

## Simpler Alternatives

### Alternative 1: HTTP ping directly to the gateway instead of CLI
**Instead of:** `openclaw gateway wake --mode now` (unknown behavior, unknown binary path)
**Do this:** `curl -s --max-time 3 -X POST http://localhost:18789/wake \
  -H "Authorization: Bearer b4a2751ec3b74972eb5456450e2c61616b8feae6dbae8af8" \
  2>>"$CALLBACK_LOG" &`
**Pros:** `curl` is always on PATH. Max-time 3 protects against hang. Runs in background.
Gateway port and auth token are known from `openclaw.json`. No binary discovery needed.
**Cons:** Gateway REST API endpoint path (`/wake`) is not documented — may not exist or have
different path. We'd need to reverse-engineer or test the actual endpoint.
**Viability:** Medium — needs one-time endpoint verification

### Alternative 2: Touch a sentinel file that OpenClaw polls
**Instead of:** Active CLI wake
**Do this:** `touch "${EVENT_DIR}/.wake-signal"` immediately after writing `EVENT_FILE`.
Add OpenClaw cron schedule: reduce `everyMs` from 300000 to 30000 (30 seconds). Remove sentinel
after each cron scan.
**Pros:** Zero external binary dependency. Zero network call. Zero hang risk. Fully idempotent.
**Cons:** Still up to 30 second latency (vs near-zero with wake). Requires OpenClaw config change.
**Viability:** High — solves the latency problem partially (30s vs 5min) with zero risk

### Alternative 3: Accept the 5-minute cron lag, solve the actual problem differently
**Instead of:** Reducing latency via wake
**Do this:** Don't add wake at all. Instead fix the real pain: the user has to wait 5 minutes
to see cycle completion. Solve this by having OpenClaw's cron message be sent as a
Telegram reply *to the original command message*, making it contextually obvious even with delay.
**Pros:** Zero risk. Zero code. No binary dependency.
**Cons:** 5 minute lag remains a real UX issue when 3 agents run sequentially (full cycle = 45+
minutes, losing 15 minutes to cron lag).
**Viability:** Low — the latency problem is real

**Verdict:** The feature is justified. The 5-minute cron lag is a real UX problem. But the current
proposal has two unacceptable risks: unknown binary path and unknown blocking behavior. The minimal
safe implementation requires: (1) locate binary, (2) run in background with timeout. Alternative 1
(direct HTTP) is cleaner if the gateway endpoint is documented. Alternative 2 (sentinel file) is
the safest fallback.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | openclaw not on PATH | callback fires, openclaw binary missing | callback exits 0, wake failure logged, event file still written | High | P0 | deterministic |
| DA-2 | openclaw gateway hangs | wake call takes >5s | callback continues within 5s (timeout or background kills it) | High | P0 | deterministic |
| DA-3 | Wake fires only after EVENT_FILE written | skill=autopilot, STATUS=done | wake call placed AFTER `cat > "$EVENT_FILE"` line | High | P0 | deterministic |
| DA-4 | Wake NOT fired when no event written | skill=spark, STATUS=done | no wake call executed (EVENT_FILE not written for spark) | Med | P1 | deterministic |
| DA-5 | Wake NOT fired for failed task without QA | skill=autopilot, STATUS=failed | no event file written (Step 6.8 condition), no wake call | Med | P1 | deterministic |
| DA-6 | Concurrent callbacks (two tasks finish simultaneously) | two callbacks executing in parallel | each wake call independent, no shared state, no deadlock | Med | P1 | deterministic |
| DA-7 | Double-processing race: cron fires within 1s of wake | pending-event file exists, cron cycle active | only one openclaw session processes events (second finds no .json files) | Med | P2 | deterministic |
| DA-8 | openclaw exits non-zero | wake returns exit code 1 | `|| true` swallows error, callback continues, error logged to CALLBACK_LOG | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | Event file write (Step 6.8) | pueue-callback.sh:315-325 | EVENT_FILE must be written BEFORE wake call — wake must not be in a branch that skips file write | P0 |
| SA-2 | QA + Reflect dispatch (Step 7) | pueue-callback.sh:333-405 | Wake call must not be placed inside Step 7 block — Step 7 runs only for autopilot, wake applies to qa/reflect too | P0 |
| SA-3 | Pueue task completion timing | pueue daemon | Callback must complete within pueue's callback timeout (unknown, likely 30-60s). Blocking wake breaks sequential task completion | P0 |
| SA-4 | callback-debug.log | pueue-callback.sh:30 | Wake attempt (success or failure) must be logged to CALLBACK_LOG for debuggability | P1 |

### Assertion Summary
- Deterministic: 8 | Side-effect: 4 | Total: 12

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| Pueue callback pipeline | pueue daemon (internal) | Blocking `openclaw gateway wake` stalls callback; Pueue waits for callback before marking task complete | Run wake in background: `... &` or with `timeout 5` |
| callback-debug.log | pueue-callback.sh:30,410 | Wake outcomes not traced if not explicitly logged | Add `echo "[callback] wake: ..."` before and after wake call |
| Multi-project support | cron/jobs.json | Only `dld` project has an OpenClaw cron job — wake for other projects is a no-op that logs an error | Document scope limitation; skip wake if project is not dld |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| `openclaw` CLI binary | PATH/executable | High | Must locate binary before implementation; add `OPENCLAW_BIN` to `.env` or use absolute path |
| OpenClaw gateway HTTP | network/port | High | Port 18789 loopback must be open; openclaw process must be running; `|| true` alone doesn't prevent hang |
| `openclaw-artifact-scan.py` rename | file atomicity | Medium | Two concurrent openclaw sessions may double-process; rename is not POSIX-atomic across filesystems |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** What is the absolute path of the `openclaw` binary on this VPS?
   **Why it matters:** The binary is not in any standard PATH directory. Without the path,
   the feature is a silent no-op. Run: `which openclaw || find /home/dld -name "openclaw" -type f 2>/dev/null | head -5`

2. **Question:** Does `openclaw gateway wake --mode now` block until inference completes, or is it a fire-and-forget HTTP ping?
   **Why it matters:** If blocking: must run in background with timeout. If fire-and-forget: safe inline.
   Run: `time openclaw gateway wake --mode now` on the VPS to measure actual duration.

3. **Question:** Is there a Pueue callback timeout, and what is it?
   **Why it matters:** If Pueue has a 30-second callback timeout and `openclaw gateway wake`
   hangs for 120 seconds, Pueue may kill the callback mid-execution, leaving the slot unreleased.
   Check: `pueue --help` or `pueue.yml` for `callback_timeout` setting.

4. **Question:** Should the wake be scoped per-project (only for projects that have an OpenClaw job)?
   **Why it matters:** Currently only `dld` has a cron job. Waking OpenClaw for `awardybot`
   autopilot completion is harmless today but adds noise as more projects onboard.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The feature solves a real latency problem (5-minute cron lag for cycle feedback).
The event file infrastructure is already correct. The single line addition is conceptually simple.
However, two unresolved risks require mitigation before merging:
(1) the `openclaw` binary path is not discoverable from the current codebase,
(2) blocking behavior is unconfirmed and cron history shows 2-minute timeouts are real.

**Conditions for success:**
1. Verify `openclaw` binary path before writing any code — if missing from PATH, add `OPENCLAW_BIN` to `.env` (P0)
2. Run wake in background subshell with explicit timeout: `timeout 5 ... 2>>"$CALLBACK_LOG" &` — `|| true` alone does NOT protect against blocking (P0)
3. Place wake call AFTER `cat > "$EVENT_FILE"` and INSIDE the same `if [[ -n "$PROJECT_PATH_FOR_EVENT" ...]]` block (P0)
4. Log wake attempt and outcome to `CALLBACK_LOG` for debuggability (P1)
5. Add DA-1 and DA-2 as integration tests once binary path is confirmed (P1)
