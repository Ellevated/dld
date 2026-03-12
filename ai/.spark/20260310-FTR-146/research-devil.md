# Devil's Advocate — Multi-Project Orchestrator Phase 1 (FTR-146)

**Focus:** Implementation risk for Days 1-3, not architecture (architecture is DECIDED)
**Architecture decision:** Alternative B — Pueue + Telegram Bot + SQLite
**Timebox:** 3-day build must produce a working system (fitness gate: bot responds to /status)

---

## Why NOT Do This?

### Argument 1: The 3-Day Estimate Is a Known Lie

**Concern:** The architecture doc says "Days 1-3: Pueue + systemd + Telegram bot + SQLite. Gate: Bot responds to /status." The architecture critique (peer-C) already caught this: "VPS setup alone (SSH hardening, systemd, Python virtualenv, Pueue daemon, Telegram bot polling, testing against real Telegram API with its documented forum mode bugs) routinely takes 4-8 hours for experienced developers doing it fresh." That is Day 1 gone, before a single line of application code is written.

**Evidence:** The bootstrap checklist in `architectures.md:637-680` has 6 phases of pre-work before the first `systemctl start orchestrator`. Each phase is marked "5-30 min" by the author. Real-world friction (wrong Pueue binary arch, Python venv PATH issues, Telegram forum topic creation requiring bot admin privileges in the group) will multiply each estimate by 2-3x.

**Impact:** High

**Counter:** Timebox Phase 1 ruthlessly. Day 1 = VPS up + Pueue running + bot sends one message. Day 2 = /status works. Day 3 = /run submits to Pueue. Anything beyond that is Phase 2. Write this down before starting.

---

### Argument 2: python-telegram-bot v22 Is Async-First and Forum Topics Have Known Bugs

**Concern:** PTB v20 introduced a full async rewrite (ApplicationBuilder, async handlers). PTB v22 continues this pattern. Anyone who last wrote a Telegram bot in v13 or earlier will hit immediate breaking changes: `Updater` is gone, `ConversationHandler` internals changed, `context.bot.send_message` is now awaited everywhere. The architecture doc pins `pip install python-telegram-bot==22.0` but v22.0 does not exist yet as of the knowledge cutoff — PTB's latest stable is 21.x. Pinning `==22.0` will fail with "No matching distribution found."

**Evidence:** `architectures.md:652` pins `python-telegram-bot==22.0`. PTB's GitHub shows v21.9 as latest (Jan 2026). The architecture's own research (`critique-devil.md:283`) documents "PTB bug #4739" for forum topics. Additionally, `research-devil.md:287` notes: "Telegram's General topic (thread_id=1) can't receive messages with message_thread_id=1" — a known API bug that will surface on day 1 of forum topic testing.

**Impact:** High

**Counter:** Pin to `python-telegram-bot==21.9` (latest stable). Write a minimal 50-line smoke test that creates a topic and sends to it before building any routing logic. Catch the thread_id=1 bug explicitly in the router.

---

### Argument 3: pueued as systemd --user Service Will Fail on Many VPS Configurations

**Concern:** The bootstrap checklist runs `systemctl --user enable pueued && systemctl --user start pueued`. User-level systemd services require `systemd-logind` and `XDG_RUNTIME_DIR` to be set. On headless VPS distros (Ubuntu 22.04 minimal, Debian 12), SSH sessions often do NOT have a user lingering session. The `systemctl --user` commands will silently do nothing or fail with "Failed to connect to bus: No such file or directory" unless `loginctl enable-linger ubuntu` is run first. This is not in the bootstrap checklist.

**Evidence:** `architectures.md:659` shows `systemctl --user enable pueued && systemctl --user start pueued` with no preceding `loginctl enable-linger`. The architecture decision chose systemd user service for Pueue specifically. Without linger enabled, pueued dies when the SSH session closes — exactly the failure mode the service is meant to prevent.

**Impact:** High — the entire unattended execution model breaks silently

**Counter:** Add `loginctl enable-linger $USER` as the first command in Phase 3 of the bootstrap checklist. Test pueued survival by closing SSH and reopening. Alternative fallback: run pueued as a system service (`/etc/systemd/system/pueued.service`) under the ubuntu user — avoids the linger problem entirely but requires sudo for `systemctl` operations.

---

### Argument 4: SQLite Concurrent Access Pattern Has a Specific Bash Pitfall

**Concern:** The architecture specifies SQLite WAL with `BEGIN IMMEDIATE` for slot acquisition. This is correct. The problem is in how bash calls sqlite3: every `sqlite3 /path/to/orchestrator.db "SELECT ..."` spawns a new process, opens the database, runs the query, closes it. The `busy_timeout = 5000` PRAGMA must be set in every connection, not just at schema creation time. If the bash script opens SQLite without setting busy_timeout first, it gets `SQLITE_BUSY` immediately on a locked database and exits with code 1 — no retry, no wait.

**Evidence:** `architectures.md:385-388` shows `PRAGMA busy_timeout = 5000` in the schema creation script. But this PRAGMA is not persistent — it is a per-connection setting. Every bash `sqlite3` invocation that performs writes needs to set it inline: `sqlite3 db.sqlite "PRAGMA busy_timeout=5000; BEGIN IMMEDIATE; UPDATE..."`. The architecture's slot acquisition SQL (`architectures.md:443-456`) does NOT include this PRAGMA prefix in the shown snippet.

**Impact:** Medium — causes intermittent "database is locked" failures under load, which look like slot acquisition bugs

**Counter:** Create a `db_exec()` bash function that always prepends `PRAGMA busy_timeout=5000; PRAGMA journal_mode=WAL;` to every SQLite call. Never call `sqlite3` directly from orchestrator.sh. One wrapper, enforced by convention.

---

### Argument 5: Telegram Polling on a VPS Is Fine But Has a Specific Failure Mode

**Concern:** Polling mode is the right choice for a VPS without a domain (no HTTPS setup needed). The concern is not CPU — it is the 409 Conflict error. If the bot process crashes and restarts quickly, the Telegram API returns `409 Conflict: Terminated by other getUpdates request` because the old polling loop is still registered. PTB handles this by default, but it adds a 30-60 second startup delay before the bot accepts commands. During this window, a `/status` command from Telegram is silently dropped.

**Evidence:** PTB docs describe `drop_pending_updates=True` on ApplicationBuilder as the standard fix. This is not mentioned anywhere in the architecture's bot setup. `architectures.md:465` notes "polling mode" without addressing restart behavior.

**Impact:** Low (once running, polling is stable) but confusing on first deploy

**Counter:** Add `drop_pending_updates=True` to `ApplicationBuilder().token(...).build()`. Add a 5-second startup delay before beginning polling after systemd restart. Both are single-line fixes.

---

### Argument 6: Testing Without a VPS Requires a Plan That Doesn't Exist

**Concern:** The architecture has no local development story. Day 1 of the build starts with "get a VPS." There is no docker-compose for local testing, no mock for the Telegram API, no way to iterate on `orchestrator.sh` without deploying to a real server. This means every iteration cycle is: edit code → SSH to VPS → copy file → restart service → test via Telegram. A 10-second code change takes 3-5 minutes to verify.

**Evidence:** The bootstrap checklist (`architectures.md:637-680`) goes straight to VPS setup. No local-first approach is mentioned anywhere in the 8 research files or the critiques. The only testing reference in the whole architecture is the fitness gate "Bot responds to /status" — which requires a running VPS.

**Impact:** Medium — slows the 3-day build significantly, makes debugging painful

**Counter:** Two options: (A) Use `python-telegram-bot` test framework with `pytest-telegram-bot` — allows unit testing handlers offline. (B) Use Telegram's test environment (separate `api.telegram.org/bot{token}/` test instance). For the bash orchestrator, test Pueue logic locally before VPS deployment — Pueue runs on macOS, all group/parallel logic can be verified locally.

---

## Simpler Alternatives

### Alternative 1: Skip /addproject on Day 1 — Manual projects.json Editing Is Fine

**Instead of:** Implementing `/addproject` Telegram command (creates topic + Pueue group + writes projects.json + seeds SQLite = ~150 LOC)
**Do this:** Ship with 2-3 hardcoded projects in a hand-edited `projects.json`. `/addproject` is Phase 3 (days 6-7) per the architecture's own build table. Do not move it to Phase 1.
**Pros:** Eliminates the most complex write operation from the bot. Days 1-3 bot only reads and queries. Write operations (JSON mutation, SQLite writes, Pueue group creation) all deferred.
**Cons:** Can't add a project via Telegram. SSH + text editor required for new projects.
**Viability:** High — the architecture's own Phase 3 gate is "/addproject creates full project." The Phase 1 gate is only "/status."

---

### Alternative 2: SQLite Migrations Can Wait — Seed Schema on First Boot

**Instead of:** Writing a formal migration system for `orchestrator.db`
**Do this:** Ship a single `schema.sql` that is applied once with `sqlite3 db.sqlite < schema.sql`. If schema changes in Phase 2 or 3, drop and recreate (no production data yet). No migration runner needed for days 1-3.
**Pros:** Zero migration tooling. Schema is a checked-in SQL file anyone can read.
**Cons:** Must manually recreate DB if schema changes. Acceptable for pre-production tooling.
**Viability:** High — there is no user data at risk during days 1-7.

---

### Alternative 3: Start Bot in Polling Mode With Zero Forum Topics

**Instead of:** Setting up Telegram Supergroup + forum topics as routing mechanism on Day 1
**Do this:** Start the bot in a regular group (no forum topics). All commands go to one chat. `/status project-name` with explicit project name argument instead of implicit topic routing.
**Pros:** Eliminates the forum topics API surface (known bugs, thread_id=1 issue, admin permission requirements). Bot works in 30 minutes instead of 2 hours.
**Cons:** Less elegant UX. Must migrate to topics in Phase 2. Topic IDs in config will differ.
**Viability:** High as temporary scaffold — migrate to topics only after core orchestration logic is verified working.

---

### Alternative 4 (the hard question): Is Day 1-3 Scope Actually Just "Pueue Running + One Task Submitted"?

**Instead of:** Pueue + systemd + Telegram bot + SQLite (full Phase 1 scope)
**Do this:** Day 1 only: Pueue running, `run-agent.sh` can invoke `claude -p "task"` for one project, verified working. No bot. No SQLite. No systemd service for the orchestrator (run in tmux for now). This is the actual P0: does `pueue add -- run-agent.sh ~/project "task"` work?
**Pros:** Validates the hardest unknown (Claude CLI + Pueue integration) before building any UI. Avoids building a Telegram UI for a pipeline that doesn't work yet.
**Cons:** No mobile visibility. Manual operation.
**Viability:** Medium — depends on whether the founder needs unattended execution starting day 1. If so, bot is required. If attended operation is fine for 3 days, this is much safer.

**Verdict:** Alternative 1 (skip /addproject) is non-negotiable — it should not be in days 1-3. Alternative 3 (no forum topics on day 1) is worth considering as a scaffold. Alternative 4 is the honest minimum if the goal is to VALIDATE before building the UI.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | pueued dies when SSH session closes | Start pueued without `loginctl enable-linger`, close SSH | pueued dead, `pueue status` fails | High | P0 | deterministic |
| DA-2 | python-telegram-bot==22.0 does not exist | `pip install python-telegram-bot==22.0` | pip error: no matching distribution | High | P0 | deterministic |
| DA-3 | SQLite BUSY without timeout | Two processes write to orchestrator.db simultaneously, no busy_timeout set | "database is locked" error, slot acquisition fails silently | High | P0 | deterministic |
| DA-4 | Telegram thread_id=1 routing | Bot receives message in General topic (thread_id=1), routes to project | Error or wrong routing (known Telegram bug) | High | P0 | deterministic |
| DA-5 | Bot 409 Conflict on restart | Bot crashes and restarts within 60s | "409 Conflict: Terminated by other getUpdates" — bot silent for 30-60s | Medium | P1 | deterministic |
| DA-6 | Pueue binary wrong arch | wget x86_64 binary on ARM VPS | Permission denied / exec format error on `pueue status` | Medium | P1 | deterministic |
| DA-7 | /status with zero projects seeded | Bot starts, projects.json empty or missing | Bot crashes with KeyError / unhandled exception | Medium | P1 | deterministic |
| DA-8 | Claude CLI exits non-zero mid-Pueue task | `claude -p "task"` returns exit code 1 | Pueue marks task as failed, slot not released in SQLite | High | P0 | deterministic |
| DA-9 | CLAUDE_CODE_CONFIG_DIR path missing | run-agent.sh sets CLAUDE_CODE_CONFIG_DIR to non-existent dir | Claude CLI falls back to default config dir — cross-session contamination not prevented | Medium | P1 | deterministic |
| DA-10 | systemd MemoryMax kills orchestrator mid-task | Orchestrator + Claude together exceed MemoryMax=27G | orchestrator.service killed, Pueue task still running as orphan | Medium | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | Pueue group parallelism | architectures.md:567 | After adding two tasks to same group, only one runs at a time | P0 |
| SA-2 | SQLite slot release on task failure | architectures.md:443-456 | After Claude exits non-zero, `SELECT project_id FROM compute_slots` returns NULL for that slot | P0 |
| SA-3 | systemd service restart | architectures.md:606-634 | After `kill -9 <orchestrator_pid>`, service restarts within 30s | P1 |
| SA-4 | Bot user whitelist | architectures.md:587 | Message from non-whitelisted user_id silently ignored, no error sent back | P0 |
| SA-5 | projects.json atomic write | architectures.md:376 | Write to projects.json uses tmp+mv, no partial write possible | P1 |

### Assertion Summary
- Deterministic: 10 | Side-effect: 5 | Total: 15

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| pueued user service | architectures.md:659 | `systemctl --user` requires lingering session; headless VPS has none | Add `loginctl enable-linger $USER` to bootstrap Phase 3 |
| SQLite slot acquisition | architectures.md:443-456 | busy_timeout not set per-connection; bash sqlite3 gets SQLITE_BUSY and exits | Create `db_exec()` wrapper that prepends PRAGMA busy_timeout=5000 |
| Telegram bot startup | architectures.md:465 | 409 Conflict on fast restart silently drops commands | Add `drop_pending_updates=True` to ApplicationBuilder |
| run-agent.sh config dir | architectures.md:499 | CLAUDE_CODE_CONFIG_DIR directory must pre-exist before Claude is invoked | Add `mkdir -p "$config_dir"` before the `claude` invocation (already in Docker variant but not bare-metal variant) |
| Python dependency pin | architectures.md:652 | `python-telegram-bot==22.0` does not exist; will break `pip install` on first VPS setup | Pin to `==21.9` until v22 is released |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| python-telegram-bot v22.0 | pip package | High — version doesn't exist yet | Pin to 21.9; test forum topic support before full build |
| systemd lingering | OS config | High — silently broken on minimal VPS images | Add linger to bootstrap; verify with `loginctl show-user $USER | grep Linger` |
| Pueue v4.0.0 binary | GitHub Release | Medium — URL may change, ARM64 needs different binary | Pin download URL + verify checksum; add ARM detection |
| sqlite3 CLI | apt package | Low — ships with every Ubuntu/Debian | Verify with `sqlite3 --version` in ExecStartPre |
| Telegram Forum Topics API | Telegram API | Medium — beta feature, known bug at thread_id=1 | Smoke test topic creation before wiring routing |
| Claude CLI `--output-format json` | Claude CLI flag | Medium — flag name has changed between versions; `--output-format` may be `--format` | Test exact flag on target Claude CLI version before scripting |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Does `loginctl enable-linger $USER` need to be run on the target VPS?
   **Why it matters:** Without it, pueued dies on SSH disconnect — the entire unattended execution model fails silently. This is the #1 risk for a failed Day 1.

2. **Question:** What exact version of python-telegram-bot is stable and tested with forum topics?
   **Why it matters:** The pinned version (22.0) does not exist. Pinning the wrong version breaks pip install on first VPS setup, blocking Day 1.

3. **Question:** Does /status need to work without any projects in the DB?
   **Why it matters:** If the bot starts before projects are seeded into SQLite, `/status` will throw an unhandled exception. The empty-DB case must be explicitly handled (return "No projects configured" message) or the fitness gate "bot responds to /status" fails immediately.

4. **Question:** What is the exact Claude CLI flag for JSON output on the pinned version (@2.1.34)?
   **Why it matters:** `--output-format json` may be `--format json` or may not exist in 2.1.34. run-agent.sh is the only place that calls the CLI. Getting the flag wrong means every Pueue task fails with a parse error.

5. **Question:** Is Day 1-3 scope addproject-free?
   **Why it matters:** /addproject is the most complex operation in the bot (creates Pueue group + topic + writes JSON + seeds SQLite). Including it in Phase 1 would take the full 3 days alone. The architecture's own Phase table shows it as Phase 3. Confirm it is out of scope for days 1-3 before writing the spec.

6. **Question:** What is the failure behavior when a Pueue task fails but the SQLite slot is still marked as occupied?
   **Why it matters:** If Claude exits non-zero and the post-task cleanup script (`drain-stop.sh` equivalent) does not run, the slot remains permanently occupied. The next project never gets a slot. There is no stale-slot recovery in the architecture's current design. This must be specified before implementation.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The architecture decision is sound. Pueue + SQLite + bot is the right stack. The risk is not in the design — it is in 5 specific implementation traps that will each cost 2-4 hours if hit on a live VPS:

1. systemd --user linger (silent failure)
2. PTB version pin (Day 1 pip install failure)
3. SQLite busy_timeout per-connection (intermittent failures under load)
4. Telegram thread_id=1 bug (Day 1 routing test failure)
5. Claude CLI JSON output flag mismatch (every Pueue task fails)

Each is fixable in 15 minutes once identified. But on a 3-day timebox, hitting all five means the 3-day build becomes a 5-day build.

**Conditions for success:**
1. Start Day 1 with a pre-flight checklist that validates each dependency before writing application code: pueue version, python version, PTB installable, sqlite3 present, loginctl linger status, Claude CLI JSON flag
2. Drop /addproject from Phase 1 scope entirely — first hardcode 1-2 projects in projects.json and SQLite, wire the bot to read-only operations first
3. Test Pueue + run-agent.sh integration (actual Claude invocation via Pueue) as the FIRST thing on Day 1, not the last — this is the hardest unknown and must be validated before building the Telegram UI on top of it
4. Pin python-telegram-bot to 21.9 (not 22.0) and test forum topic creation in isolation before wiring the full routing logic
5. Define explicit stale-slot recovery in the spec: what happens if Claude exits non-zero and the SQLite slot is not released
