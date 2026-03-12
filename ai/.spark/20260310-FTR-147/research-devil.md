# Devil's Advocate — Multi-Project Orchestrator Phase 2: Architecture & Reliability

**Focus:** Risk analysis for Phase 2 components before spec is written
**Phase 1 status:** in_progress (FTR-146) — Phase 2 builds ON TOP of an unfinished Phase 1
**Core concern:** Phase 2 is being speced while Phase 1 is still being built

---

## Why NOT Do This?

### Argument 1: Phase 1 Is Not Done — Phase 2 Is Premature

**Concern:** FTR-146 is marked `in_progress`. The spec lists 16 new files to create in
`scripts/vps/`. None of them exist on disk yet. Phase 2 adds 7 more components on top of a
foundation that hasn't been validated end-to-end. We are designing a second floor before the
first floor walls are standing.

**Evidence:** `ai/features/FTR-146-2026-03-10-multi-project-orchestrator-phase1.md` status is
`in_progress`. `Glob("scripts/vps/**/*")` returns no files — the entire scripts/vps/ directory
is absent from the working tree. The Phase 1 fitness gate ("Bot responds to /status") has
not been confirmed reached.

**Impact:** High

**Counter:** Specing Phase 2 is fine if the spec is treated as future work. But it must NOT
be started until Phase 1 passes its fitness gate. Add an explicit gate: "Phase 2 requires
FTR-146 status = done AND /status command verified on live VPS."

---

### Argument 2: The Audit Night Mode Cost Will Blow Up

**Concern:** Deep audit = 6 personas × Opus 4.6 ($5/$25 per MTok). A 10K LOC project
costs ~$8-15 per deep audit run. 3 projects × nightly = $30-45/night. Over a month =
$900-1350/month just in audit cost — on top of the $200/month Claude Max subscription.
Claude Max has 5-hour session limits, not token limits; but if the night reviewer launches
audit as a subprocess (which it must, since `claude --print` invokes a fresh session), each
deep audit consumes a fresh 5-hour window. 3 projects = 3 windows consumed nightly.

**Evidence:** `deep-mode.md:218-228` documents minimum operation counts: Cartographer 20 reads,
Archaeologist 25 reads, etc. for a 10K LOC project. At 30K+ LOC the spec says "multiply by 2-2.5x".
DLD itself has 400+ files. A deep audit of DLD would consume a very large context window.
The `deep-mode.md` protocol runs 6 parallel persona agents via `run_in_background: true` — each
is a separate Claude process, each potentially running for 10-30 minutes.

**Impact:** High

**Counter:** Night reviewer MUST use light mode audit, not deep mode. Deep mode is for
retrofit/brownfield forensics, not nightly incremental scanning. Define "night mode" as:
(1) targeted zone audit (e.g., only changed files in last 24h via `git diff --name-only HEAD~1`)
or (2) rotating zone schedule (Mon: security, Tue: tests, Wed: architecture, Thu: billing, etc.).
Never run deep mode on a schedule.

---

### Argument 3: Finding Deduplication Has No Implementation Path

**Concern:** Night 1 finds 25 bugs. User approves 3 for fixing. Night 2 runs and finds the
same 25 bugs (22 still unfixed). User gets 25 Telegram notifications again at 3am. This is
not a design detail to figure out later — it is the core UX problem that makes the feature
usable or unusable. Without deduplication, the night reviewer is a spam machine.

**Evidence:** No deduplication mechanism exists anywhere in `scripts/vps/`. The audit skill
(`SKILL.md`, `deep-mode.md`) produces a fresh report each run with no reference to previous
reports. There is no findings database, no hash-based dedup, no "already filed" status. The
closest concept is `ai/features/*.md` files (specs), but audit findings are not mapped to spec
IDs — they are freeform markdown reports.

**Impact:** High

**Counter:** Before implementing, define the dedup schema: findings must have stable IDs
(SHA of file:line:issue-type), stored in SQLite `night_findings` table with status
(new/approved/rejected/fixed/ignored). Night 2 only sends NEW findings (not in table) or
REOPENED ones (was fixed, regressed). This adds a findings DB that is non-trivial to design.

---

### Argument 4: The QA Fix Loop Has No Termination Condition

**Concern:** QA finds bug → autopilot fixes → QA runs again → fix introduced new bug → QA
finds → autopilot fixes → ... This can run indefinitely at 3am, burning API budget, filling
the backlog with cascading specs, and leaving the project in an inconsistent state. There is
no max iteration count, no rollback plan, no "stop and alert human" trigger in the described
design.

**Evidence:** `FTR-146-2026-03-10-multi-project-orchestrator-phase1.md:185` shows the QA loop:
"QA FAIL → bugs written to `ai/inbox/` → cycle repeats." The cycle repeats without bound.
`qa-loop.sh` (git:f585ba5) exists but no termination logic was found. Autopilot can generate
new regressions — the DLD framework itself notes: "each feature → ~1.5 fixes" (PLPilot evidence
in MEMORY.md).

**Impact:** High

**Counter:** Hard limit: MAX_QA_ITERATIONS=3 per spec. After 3 FAIL cycles, status = `blocked`,
human notification required. Also: QA fix loop should only run for bugs filed by THAT QA run
(by spec ID), not all inbox bugs. Otherwise QA run for FTR-001 triggers fixes for FTR-002's
bugs.

---

### Argument 5: CLAUDE.md Context Switching Is Underdocumented and Behavior Is Opaque

**Concern:** The proposal mentions `claude --cwd /path/to/project` as the context switching
mechanism. The specific behavior when global `~/.claude/CLAUDE.md` AND project-level `CLAUDE.md`
both exist is not documented by Anthropic. Does it merge? Does project override global? If merge,
in what order? If a project's CLAUDE.md defines an MCP server that conflicts with the global
one, what happens? These are not rhetorical questions — they determine whether every managed
project behaves correctly or silently misloads its context.

**Evidence:** Phase 1 codebase scout (`research-codebase.md:279-290`) notes this exact issue:
"Claude Code loads `{project}/CLAUDE.md` as project context" and "Every managed project must be
a DLD project (has `CLAUDE.md`, `ai/backlog.md`, `.claude/settings.json`)." The question of
global+local merge is raised but not answered. `Grep("CLAUDE_CODE_CONFIG_DIR")` in the codebase
finds no implementation — the pattern is planned but untested. `--cwd` is also not verified to
exist as a Claude CLI flag; the git history shows `CLAUDE_PROJECT_DIR` env var used instead.

**Impact:** Medium

**Counter:** Before Phase 2 implementation, document the exact tested behavior: run
`claude --cwd /tmp/test-project "print your CLAUDE.md context"` with both global and project
CLAUDE.md present and observe what is loaded. Write the result as a verified fact in
`scripts/vps/README.md` before building any context-switching logic on top of it.

---

### Argument 6: Groq API Is a New External Dependency With Unproven Reliability

**Concern:** Groq does not have the same enterprise SLA as Anthropic. Adding Groq as the voice
transcription provider introduces a dependency that can go down, hit rate limits, or change
pricing mid-month. The original FTR-146 spec explicitly listed "Voice inbox via whisper.cpp —
Phase 3" and deferred it. Phase 2 proposes Groq API instead of the whisper.cpp local-first
approach, swapping a local dependency for a cloud one without analyzing the tradeoff.

**Evidence:** `FTR-146` spec scope section explicitly: "Voice inbox via whisper.cpp (Phase 3)"
— out of scope. `research-external.md:55-63` documents that whisper.cpp requires OGG→WAV
conversion via ffmpeg. Groq's Whisper API has documented rate limits: 20 requests/minute,
7,200 requests/day on the free tier; ~$0.111/hour on paid. For Russian + English
code-switching, Groq's Whisper large-v3 is the best available model, but code-switching
(switching mid-sentence between Russian and English) is a known weak point — accuracy drops
30-50% in mixed-language segments per academic benchmarks.

**Impact:** Medium

**Counter:** Two options: (A) whisper.cpp local as originally planned — no rate limit,
no monthly cost, works offline, handles Russian better with `--language ru` flag.
(B) Groq with explicit fallback: if Groq returns HTTP 429 or 5xx, fall back to a queued retry,
not a silent failure. If going with Groq, test Russian + English code-switching accuracy before
committing to it as the production transcription path.

---

## Simpler Alternatives

### Alternative 1: Night Reviewer = Git Diff Audit, Not Deep Audit

**Instead of:** Running full audit skill nightly (6 personas × Opus × 3 projects)
**Do this:** Audit only files changed in the last 24 hours:
```bash
git -C $project_path diff --name-only HEAD~1 | head -20 > /tmp/changed-files.txt
claude --cwd $project_path -p "/audit changed files: $(cat /tmp/changed-files.txt)"
```
Light mode audit on 5-15 changed files instead of the full codebase.
**Pros:** $0.10-0.50/night instead of $8-15/night. Faster (10 min vs 45 min). Findings
are directly tied to recent changes — no deduplication needed (yesterday's bugs weren't in today's diff).
**Cons:** Misses systemic bugs that aren't in recent changes. Not a full codebase health check.
**Viability:** High — this is what most CI systems do. Full audit = monthly or before release.

---

### Alternative 2: QA Fix Loop = Single Pass, Not Recursive

**Instead of:** Recursive QA loop (QA → fix → QA → fix → ...)
**Do this:** QA runs once after autopilot. If FAIL: bugs are filed as new inbox items and
user is notified. The NEXT orchestrator cycle picks them up naturally. No automated re-queue.
**Pros:** Eliminates infinite loop risk entirely. Natural rate limiting (one cycle per poll
interval). User stays informed at each step.
**Cons:** Fixes take one more orchestrator cycle (5-15 min delay). Less "autonomous" feel.
**Viability:** High — this is actually what Phase 1 already does. "QA Fix Loop" as a named
feature is just the existing flow with a new name.

---

### Alternative 3: Nexus Integration = Read-Only, Not Deployment

**Instead of:** Full Nexus MCP integration (discovery + secrets + deploy sync)
**Do this:** Read-only Nexus list_projects call to populate `projects.json` on setup.
One `node bin/nexus.js list-projects` call during `setup-vps.sh`. Output: projects.json.
No ongoing Nexus dependency at runtime.
**Pros:** Nexus MCP server does not need to run on VPS. No Node.js service to manage.
No MCP transport setup on VPS.
**Cons:** Projects added to Nexus after initial setup don't auto-appear. Manual projects.json
update still needed for new projects.
**Viability:** High — Nexus is a dev-machine tool. The VPS orchestrator doesn't need
live Nexus access; it just needs the initial project list.

---

### Alternative 4: Approve/Reject = Single Digest, Not 25 Individual Messages

**Instead of:** 25 individual Telegram messages for 25 findings
**Do this:** One nightly digest message with numbered findings. User replies "/approve 1 3 7"
or "/reject all". Bot parses the reply and queues selected findings.
**Pros:** One notification per night (not 25 buzzes). Telegram rate limit not hit. UX matches
daily digest pattern users are familiar with.
**Cons:** Slightly more complex reply parsing in bot. Can't approve/reject asynchronously.
**Viability:** High — this is the only viable UX for >5 findings.

---

**Verdict:** Full Phase 2 scope (10 components) is too large for a single phase. Split:
- **Phase 2a (critical path):** Night Reviewer (git-diff mode only) + Groq Whisper voice
  (with whisper.cpp fallback)
- **Phase 2b (reliability):** QA Fix Loop termination + Finding deduplication DB + Digest
  UX for approve/reject
- **Phase 2c (integration):** Nexus read-only setup + Claude context switching verification

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Deep audit on 30K LOC project triggers cost explosion | `night_reviewer` runs `/audit deep` on DLD (400+ files) | Should run light/zone audit, NOT deep mode | High | P0 | deterministic |
| DA-2 | QA fix loop infinite cycle | QA FAIL → autopilot fix → QA FAIL again (3 times) | Loop terminates at max_iterations, status → blocked, human notified | High | P0 | deterministic |
| DA-3 | Night 2 deduplication | Night 1 finds 25 bugs (22 unfixed). Night 2 runs. | Only 3 new/changed findings sent to Telegram, not 25 again | High | P0 | deterministic |
| DA-4 | Groq API 429 during voice transcription | Groq returns HTTP 429 rate limit | Request queued for retry, user notified "voice queued", no silent drop | High | P0 | deterministic |
| DA-5 | Groq API down (5xx) | Groq returns HTTP 503 | Fallback to whisper.cpp local OR graceful failure: "Voice inbox unavailable, send text" | High | P0 | deterministic |
| DA-6 | Russian + English code-switching in voice | User says "запусти autopilot для FTR-147 в проекте dld" | Transcription preserves "autopilot", "FTR-147", "dld" verbatim (English terms in Russian sentence) | High | P0 | deterministic |
| DA-7 | 25 findings notification flood | Night reviewer produces 25 new findings | Single digest message with numbered list, NOT 25 individual messages | High | P0 | deterministic |
| DA-8 | CLAUDE.md merge behavior — global + project | `claude --cwd /path/project` with both global CLAUDE.md and project CLAUDE.md present | Project CLAUDE.md ADDS to global, does not override; hooks from both are active | Med | P1 | deterministic |
| DA-9 | Nexus MCP server not running on VPS | orchestrator calls Nexus for project discovery | Graceful fallback: read projects.json directly, log warning, do not crash | Med | P1 | deterministic |
| DA-10 | Auto-approve digest reply parsing | User replies "/approve 1 3 7" to a 25-item digest | Bot queues findings 1, 3, 7 exactly — no off-by-one, no queuing wrong IDs | Med | P1 | deterministic |
| DA-11 | Phase 2 starts before Phase 1 gate | `phase2_enable` flag set, Phase 1 /status command not verified | Gate check blocks Phase 2 activation until Phase 1 fitness gate confirmed | High | P0 | deterministic |
| DA-12 | Voice message longer than Groq's file size limit | User sends 5-minute voice message (~3MB OGG) | Groq API accepts up to 25MB; confirm 5-min OGG stays well below limit | Low | P2 | deterministic |
| DA-13 | Claude Max 5-hour limit during concurrent night ops | Night reviewer + 2 autopilot tasks running simultaneously | System detects approaching limit (API error) and queues remaining work for next window | High | P0 | deterministic |
| DA-14 | SQLite stale lock from crashed night reviewer | Night reviewer crashes mid-audit, SQLite slot not released | Slot recovery: if slot held >30min with no heartbeat, auto-release | High | P0 | deterministic |
| DA-15 | Context switching to wrong project directory | orchestrator sets `--cwd /project-a` but runs backlog task from project-b | All file writes, git commits, spec reads go to correct project directory | High | P0 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | Phase 1 orchestrator.sh | scripts/vps/orchestrator.sh (to be created) | Adding night reviewer cron does not change daytime polling interval or QA dispatch | P0 |
| SA-2 | SQLite compute_slots table | scripts/vps/db.py:release_slot | Night reviewer completing does not release a slot belonging to a running autopilot task | P0 |
| SA-3 | Telegram bot rate limits | scripts/vps/telegram-bot.py | 25-finding digest = 1 Telegram message, not 25 (global 30 msg/sec bot limit) | P0 |
| SA-4 | pueue-callback.sh | scripts/vps/pueue-callback.sh | Night reviewer task completion triggers correct callback, not project autopilot callback | P1 |
| SA-5 | projects.json integrity | scripts/vps/projects.json | Nexus project discovery (write path) does not corrupt manually-set topic_id values | P1 |

### Assertion Summary
- Deterministic: 15 | Side-effect: 5 | Total: 20

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| compute_slots table | scripts/vps/db.py (new) | Night reviewer runs as a "project" that consumes a slot. If it crashes, slot is orphaned — no existing stale-slot recovery in Phase 1 schema | Add `acquired_at` heartbeat + stale-slot recovery cron (>30min unheartbeated slot → release) |
| orchestrator.sh main loop | scripts/vps/orchestrator.sh (new) | Night reviewer adds a scheduled trigger (2am cron or sleep loop). If the cron job races with the main loop's QA dispatch, two Claude processes fight over the same project slot | Night reviewer must acquire slot via same SQLite `try_acquire_slot()` as autopilot — no bypass |
| Telegram bot message rate | scripts/vps/telegram-bot.py (new) | 25 individual finding messages in a loop = 25 API calls in <1 second = 429 Too Many Requests | Enforce single digest per audit run. Max 1 message per project per night-review event |
| autopilot-loop.sh | scripts/autopilot-loop.sh:15 | QA fix loop files bugs to inbox, which triggers inbox-processor, which triggers spark, which creates specs, which trigger autopilot. The loop is already implicit in Phase 1 — Phase 2 just makes it explicit and potentially faster | MAX_QA_ITERATIONS env var must be checked BEFORE filing bugs to inbox |
| `claude --cwd` context isolation | global `~/.claude/CLAUDE.md` | If global CLAUDE.md defines MCP servers (Exa, Context7) and project CLAUDE.md does not, the VPS project sessions inherit developer MCP tools — which may not be installed on VPS | VPS should have a minimal global CLAUDE.md without dev-machine MCP servers |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| Groq Whisper API | external HTTP | High — single point of failure for voice inbox; no on-device fallback defined | Implement whisper.cpp fallback. Groq = primary, local = fallback on 429/5xx |
| Claude Max 5-hour session limit | API constraint | High — multiple agents × 3 projects per night could saturate the limit before morning | Implement a token budget tracker in SQLite; halt new tasks when within 20% of estimated limit window |
| Nexus MCP server | process | Medium — requires Node.js service on VPS; not currently in Phase 1 setup | Use read-only CLI (`node bin/nexus.js list-projects`) at setup time only, not at runtime |
| `claude --cwd` flag | Claude CLI | Medium — flag may not exist or may behave differently than `CLAUDE_PROJECT_DIR` env var; neither is verified on live VPS | Verify exact CLI interface before building context-switching on it. Test with: `claude --cwd /tmp/test --print "what is your cwd?"` |
| findAll deduplication hash | new SQLite table | Medium — fingerprinting audit findings requires stable finding IDs across runs. Audit report format can change between DLD versions, breaking the hash | Define finding ID = SHA256(project_id + zone + file_path + line_range). Store in `night_findings` table. Never include finding description text in hash (it changes) |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** What is the verified behavior of `claude --cwd /path` when global `~/.claude/CLAUDE.md` and project `CLAUDE.md` both exist?
   **Why it matters:** If global overrides project, managed projects ignore their DLD context and the whole orchestration breaks silently. Must be tested on the actual VPS before writing context-switching code.

2. **Question:** Does `audit deep` (6 personas × Opus) fit within the Claude Max 5-hour session window for a 30K+ LOC codebase?
   **Why it matters:** If it does not, the night reviewer will time out mid-audit every night, producing partial reports and consuming a full session window. Must be profiled before committing to deep audit mode.

3. **Question:** What is the finding deduplication schema? Specifically: how is a "same finding" identified across two audit runs that produce different report text?
   **Why it matters:** Without a stable finding ID, every night audit re-reports every existing finding. The entire UX value of the night reviewer depends on getting this right.

4. **Question:** What happens when MAX_QA_ITERATIONS is reached? Rollback the autopilot changes? Leave them in place? File a human-review task?
   **Why it matters:** If the loop terminates but leaves partially-fixed code in the project, the next cycle's autopilot builds on broken state. Need a defined behavior (rollback to pre-loop git sha, or leave + block + notify).

5. **Question:** Is Nexus MCP server installed and running on the VPS? What is the setup command?
   **Why it matters:** If Nexus is not on the VPS, the entire "project discovery via Nexus" component is blocked. Nexus lives at `~/dev/nexus` on the dev machine. Deploying it to VPS requires `npm link` or a separate deployment step not in Phase 1 setup.

6. **Question:** Is Phase 2 explicitly gated on Phase 1 completion?
   **Why it matters:** Designing Phase 2 while Phase 1 is not running in production means Phase 2 assumptions about Phase 1 APIs (SQLite schema, Telegram bot commands, orchestrator.sh interface) may drift. Every week Phase 1 is unfinished is a week of Phase 2 assumption drift.

---

## Final Verdict

**Recommendation:** Proceed with caution — but split scope first

**Reasoning:** Phase 2 contains 7 components of genuinely different risk levels. Three are high-risk enough to block the entire phase if misdesigned (night reviewer cost model, QA loop termination, finding deduplication). The other four (Groq Whisper, approve/reject UX, Nexus integration, Claude context switching) are medium-risk implementation questions. Grouping all 7 into one phase creates a spec where any one unsolved hard problem blocks the entire delivery.

The strongest argument against is **cost**: deep audit on 3 projects nightly at $8-15/run = up to $45/night = $1350/month. This makes the Night Reviewer feature cost more than the Claude Max subscription 6x over. This alone makes the current design non-viable. Until the git-diff-targeted-zone alternative is validated as sufficient, the Night Reviewer component should not move past design.

The second strongest argument: **Phase 1 is not done**. Phase 2 should not be in `in_progress` status until Phase 1 reaches its fitness gate on a live VPS.

**Conditions for success:**
1. Phase 1 fitness gate must be verified (/status responds on live VPS) before any Phase 2 code is written
2. Night Reviewer must use git-diff zone audit (not deep audit) — cost cap at ~$0.50/night, not $15/night
3. Finding deduplication schema must be designed as a SQLite schema BEFORE any audit scheduling code is written — this is the hardest design problem in the entire phase
4. QA Fix Loop must have hard MAX_QA_ITERATIONS=3 with blocked+notify behavior on exhaustion — no unbounded loops
5. Approve/reject must use digest format (one message per project per night) not individual messages per finding
6. Groq Whisper must have whisper.cpp local fallback — not an optional enhancement, a required safety net
7. `claude --cwd` behavior must be tested and documented before building context-switching — it may not work as assumed
