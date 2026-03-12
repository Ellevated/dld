# Devil's Advocate — FTR-148 Multi-Project Orchestrator Phase 3

## Why NOT Do This?

### Argument 1: Gemini CLI Does Not Exist as a Headless Tool
**Concern:** "Gemini CLI" is not a shipping product for headless agent execution. Google has `gcloud` and the Gemini API, but there is no `gemini` CLI analogous to `claude --print --output-format json`. The existing `codex-runner.sh` works because OpenAI's Codex CLI ships with `--sandbox workspace-write --json`. Gemini has no equivalent binary. Building a Gemini runner means wrapping the REST API in a bash script — which is a different abstraction level entirely.
**Evidence:** `run-agent.sh` currently has only two cases: `claude` and `codex`. There is zero Gemini scaffolding anywhere in `scripts/vps/`. The `codex-runner.sh` calls `codex exec "$TASK" --sandbox workspace-write --json` — this assumes an opinionated CLI with DLD-compatible task interface. Gemini does not expose this.
**Impact:** High
**Counter:** If Gemini is wanted, scope it as "Gemini API wrapper" (a Python script like `gemini-runner.py` calling the REST API), not "Gemini CLI." Rename the feature to "Multi-Provider API Support" and build a proper runner. This doubles the implementation scope.

---

### Argument 2: Nexus Runtime Dependency Creates a New SPOF
**Concern:** Phase 2 made Nexus optional-at-setup (setup-vps.sh lines 247-275 show it's a `set +e` optional step). Phase 3 proposes making the orchestrator query Nexus before each task. This promotes an optional dev tool to a required runtime dependency. If Nexus crashes, hangs, or its MCP server port is unavailable, every task dispatch blocks.
**Evidence:** Nexus runs as an MCP server (stdio transport, per `src/app/mcp-server.js`). It is NOT designed to be called as a subprocess from bash — it speaks MCP over stdio. The only CLI interface is `bootstrap list-projects` etc., which internally reads YAML files from `~/.nexus/projects/`. The `list-projects` command in `setup-vps.sh` line 252 calls `"${NEXUS_BIN}" list-projects --format json` — but looking at Nexus source (`src/app/cli/`), there is no `list-projects` CLI command. The actual `list_projects` is a MCP tool only (`src/app/tools/project-tools.js:83`). This means the setup-vps.sh Nexus integration is already broken by design — it calls a command that doesn't exist.
**Impact:** High
**Counter:** Keep Nexus as setup-time-only. For runtime SSOT, use SQLite (`project_state` table already exists). Add a `nexus sync` command that explicitly pushes Nexus data to SQLite at project registration time. Orchestrator reads only from SQLite. No runtime Nexus dependency.

---

### Argument 3: /addproject Command Is Solving the Wrong Problem
**Concern:** The pain is "editing JSON on a server is annoying." But `/addproject` via Telegram requires entering: project_id, filesystem path, topic_id, provider, auto_approve_timeout — all as structured data through a chat interface. Telegram is optimized for short messages, not form entry. A multi-step conversation bot is harder to implement than the JSON file it replaces.
**Evidence:** `projects.json.example` has 5 fields per project. `schema.sql:9-19` shows `project_state` has 7 columns. A Telegram command conversation to fill these requires: either a multi-message state machine (bot stores partial state between messages) or a single `/addproject saas-app /home/ubuntu/projects/saas-app 42 claude 30` command with 5+ positional arguments in the right order. Both are more error-prone than `cp projects.json.example projects.json && nano projects.json`.
**Evidence:** `telegram-bot.py:91-96` shows the existing `_resolve_project` function already handles args parsing. But extending it to a full conversation wizard requires PTB conversation handlers (ConversationHandler), which add ~100+ LOC and significant test surface.
**Impact:** Medium
**Counter:** Simpler alternative: `/addproject` as a single-line command with required args. Validate and write to `projects.json` + seed SQLite. No conversation wizard. Still better than SSH, just barely.

---

### Argument 4: Global Skills Version Conflict Is Unresolvable Without Explicit Policy
**Concern:** If `~/.claude/skills/` has DLD v4.0 skills and a project has `~/projects/old-app/.claude/skills/` with DLD v3.5 skills, Claude Code CLAUDE.md hierarchy means project-level overrides global. But the orchestrator's `claude-runner.sh` sets `--cwd "$PROJECT_DIR"` which loads the project's CLAUDE.md + skills first. If the project is stale, it runs old skills. If the project has no skills, it falls back to global. There is no version check, no conflict detection, no upgrade path.
**Evidence:** `claude-runner.sh:14-17` sets `CLAUDE_CODE_CONFIG_DIR` to project-local `.claude-config` dir. `global-claude-md.template` is installed at `~/.claude/CLAUDE.md` but contains no skill version info. The `template-sync.md` rule (`template/.claude/` vs `.claude/`) applies to the DLD repo, not to the 10 projects on VDS which each have their own DLD copy at different commit SHAs.
**Impact:** Medium
**Counter:** Add a `DLD_VERSION` marker to each project's CLAUDE.md header. Night reviewer checks for version drift and flags it. Or: global skills ONLY, projects have no local skills dir — enforce this in setup. This is a policy decision, not a technical one, but it must be made explicitly.

---

### Argument 5: VPS Setup Docs Go Stale Immediately — Don't Write Them
**Concern:** "VPS Setup Instructions — manual checklist" will be outdated on the next Phase (4, 5, etc.). `setup-vps.sh` already IS the setup documentation: it's executable, self-documenting, and always correct by definition. A separate markdown checklist is a second source of truth that will diverge. Every time a new Pueue group is added or a new systemd unit is created, someone has to remember to update the doc.
**Evidence:** `setup-vps.sh:139-143` configures Pueue groups. If Phase 3 adds a `gemini-runner` group, setup-vps.sh must change. If there's also a `SETUP.md`, that's two places. History says the markdown dies first.
**Impact:** Low
**Counter:** Add inline comments to `setup-vps.sh` explaining why each step exists. Keep the script as the only source. If human-readable steps are needed, auto-generate them from the script's `echo` output: `bash setup-vps.sh --dry-run`.

---

### Argument 6: Phase 3 Scope Is 4 Independent Features, Not One
**Concern:** "Task-level LLM routing + /addproject + Global skills + Nexus SSOT + VPS docs" have no shared implementation surface. They touch different files, different subsystems, different risk profiles. Bundling them into one spec means one autopilot run attempts all five, which historically leads to partial completion and ambiguous "done" state.
**Evidence:** Phase 1 (FTR-146) had 9 related tasks all touching `scripts/vps/` — they shared a schema, a runner, a bot. Phase 2 (FTR-147) had 7 tasks sharing Phase 1 infrastructure. Phase 3's 5 features are orthogonal: routing touches `run-agent.sh`, `/addproject` touches `telegram-bot.py`, global skills touches `~/.claude/`, Nexus touches `setup-vps.sh` + `db.py`, VPS docs touches nothing.
**Impact:** High
**Counter:** Split into 3 targeted tickets: (A) Task-level routing + new provider runner, (B) /addproject command, (C) Global skills policy + Nexus sync-at-setup (not runtime). Kill the VPS docs feature entirely — setup-vps.sh is the doc.

---

## Simpler Alternatives

### Alternative 1: Task-Level Routing via projects.json Field Only
**Instead of:** Orchestrator queries Nexus before each task to determine provider
**Do this:** Add `default_provider` and optional `task_overrides: {"FTR-*": "codex", "TECH-*": "claude"}` to `projects.json`. `scan_backlog()` in `orchestrator.sh` already reads provider from DB (line 170-177). Extend `seed_projects_from_json()` in `db.py` to store task_overrides as JSON column. Orchestrator pattern-matches spec_id against overrides.
**Pros:** Zero new dependencies. No Nexus at runtime. Already-existing provider resolution path just gets a pattern-match lookup. ~30 LOC change.
**Cons:** Less dynamic — changing routing requires editing JSON and reseeding. No UI for it.
**Viability:** High

### Alternative 2: /addproject as Single-Line Command (No Wizard)
**Instead of:** Multi-step Telegram conversation to register a project
**Do this:** `/addproject <id> <path> <topic_id> [provider=claude] [timeout=30]` — one message, validate args, write `projects.json` entry, trigger `sync_projects()` immediately. Returns confirmation or validation error.
**Pros:** ~50 LOC vs ~150 LOC for ConversationHandler. No bot state machine. Errors are explicit.
**Cons:** User must know syntax. No hand-holding. But: this is a solo founder tool, not a consumer product.
**Viability:** High

### Alternative 3: Skip Nexus Runtime SSOT Entirely
**Instead of:** Orchestrator queries Nexus before each task
**Do this:** `projects.json` remains SSOT. Add `/nexussync` bot command that calls `nexus list_projects` (via MCP subprocess) once, on demand, and updates `projects.json`. Orchestrator never touches Nexus.
**Pros:** Eliminates SPOF. Nexus stays optional. Runtime has zero new dependencies.
**Cons:** Manual sync step required after adding project in Nexus.
**Viability:** High — this is already how Phase 2 works (setup-time-only).

### Alternative 4: Global Skills = Symlinks, Not Policy
**Instead of:** Building version conflict detection and upgrade tooling
**Do this:** During `setup-vps.sh`, each project's `.claude/skills/` is a symlink to `~/.claude/skills/`. All projects share one skills version. Updating global skills updates all projects atomically.
**Pros:** Zero runtime logic. No version drift possible. Trivially correct.
**Cons:** Projects can't have project-specific skill overrides. Acceptable for a VDS orchestration context where all projects run the same DLD version.
**Viability:** High — 5 lines of `ln -sf` in setup-vps.sh per project.

**Verdict:** Alternatives 1+2+3 together deliver 90% of Phase 3's value at 20% of the complexity. Alternative 4 resolves global skills cleanly. The only justified full implementation is task-level routing (it has real value for cost optimization) — but it should use projects.json pattern matching, not Nexus queries. Nexus runtime SSOT should be rejected outright.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Provider routing: task override exists | spec_id=FTR-055, task_overrides={"FTR-*": "codex"} | `scan_backlog` dispatches to codex-runner group | High | P0 | deterministic |
| DA-2 | Provider routing: no override, project default | spec_id=BUG-012, project.provider=claude, no overrides | Dispatches to claude-runner group | High | P0 | deterministic |
| DA-3 | Provider routing: unknown provider in DB | project.provider="gemini" | Falls back to claude, logs warning, does NOT crash | High | P0 | deterministic |
| DA-4 | /addproject: valid single-line command | `/addproject myapp /home/ubuntu/myapp 42 claude 30` | Entry written to projects.json, SQLite seeded, confirmation sent | High | P0 | deterministic |
| DA-5 | /addproject: path does not exist on VDS | `/addproject myapp /nonexistent/path 42` | Rejected with error "path not found", projects.json unchanged | High | P0 | deterministic |
| DA-6 | /addproject: duplicate project_id | `/addproject saas-app ...` (already exists) | Rejected with "project_id already registered", no overwrite | High | P0 | deterministic |
| DA-7 | /addproject: topic_id already bound to other project | topic_id=42 is assigned to project A, register project B with same topic_id | Rejected with conflict error | Med | P1 | deterministic |
| DA-8 | Nexus CLI not installed on VDS | setup-vps.sh runs with nexus absent | Setup completes successfully, skips Nexus block, prints warning | High | P0 | deterministic |
| DA-9 | Nexus present but list-projects command missing | nexus binary exists, `nexus list-projects --format json` returns error | Setup continues, logs "Nexus integration skipped", does not fail | High | P0 | deterministic |
| DA-10 | Global skills symlink: project lacks local .claude/skills/ | Project has symlink to ~/.claude/skills/ | Orchestrator skill invocations use global version | Med | P1 | deterministic |
| DA-11 | Concurrent /addproject and orchestrator sync_projects | /addproject writes projects.json while orchestrator is mid-sync_projects | No data corruption, file lock or atomic write | High | P0 | deterministic |
| DA-12 | Task-level routing pattern match: ambiguous pattern | spec_id matches two patterns (e.g., "FTR-*" and "*-100") | First-match wins, deterministic ordering documented | Med | P1 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | scan_backlog provider resolution | orchestrator.sh:169-177 | Existing project-level provider still works after task-level routing added | P0 |
| SA-2 | seed_projects_from_json upsert | db.py:170-188 | Existing projects not wiped when /addproject adds new entry | P0 |
| SA-3 | telegram-bot cmd handlers | telegram-bot.py:374-393 | Existing /status /run /pause /resume unaffected by new /addproject handler | P0 |
| SA-4 | pueue group dispatch | run-agent.sh:43-54 | Adding gemini/new provider case doesn't break existing claude/codex dispatch | P0 |
| SA-5 | setup-vps.sh Nexus block | setup-vps.sh:247-275 | setup-vps.sh still completes successfully when nexus absent (set +e guard) | P1 |
| SA-6 | Night reviewer project lookup | night-reviewer.sh:87-99 | Night reviewer still resolves project path after /addproject registration | P1 |

### Assertion Summary
- Deterministic: 12 | Side-effect: 6 | Total: 18

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| scan_backlog provider resolution | orchestrator.sh:169-177 | Task-level routing requires per-spec provider lookup, not just project default | Extend provider resolution: check task_overrides before project default |
| seed_projects_from_json | db.py:170-188 | /addproject needs to write projects.json atomically + trigger seed; race with orchestrator's hot-reload | Use file lock (flock) on projects.json writes |
| compute_slots schema | schema.sql:21-28 | Task-level routing to Gemini requires new slot type; hardcoded INSERT seeds only claude+codex | Add migration path; schema.sql seeding is idempotent (INSERT OR IGNORE) — safe for new provider |
| setup-vps.sh Nexus block | setup-vps.sh:252 | `nexus list-projects --format json` command does NOT exist in Nexus CLI (only MCP tool) | Fix or remove this block; it is currently dead code that silently fails |
| pueue group for new provider | setup-vps.sh:137-142 | New provider (gemini) needs new pueue group with parallelism config | Add group creation to setup-vps.sh |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| Nexus CLI `list-projects` | API mismatch | High | This command does not exist. setup-vps.sh Nexus block is broken today. Fix before Phase 3. |
| Gemini CLI binary | availability | High | No shipping headless CLI. Must wrap Gemini REST API. Adds Python dep (google-generativeai) |
| projects.json file locking | data race | High | Orchestrator hot-reloads projects.json every 300s; /addproject writes it concurrently. Need flock |
| PTB ConversationHandler (if wizard) | complexity | Med | State machine adds 150+ LOC and PTB session state that survives bot restarts only with persistence backend |
| ~/.claude/skills/ symlinks | path coupling | Med | If VDS DLD clone is updated, all project symlinks must be re-created. One-time setup-vps.sh step sufficient |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Does Gemini CLI exist as a headless executable? If not, are we building a REST API wrapper?
   **Why it matters:** `gemini-runner.sh` cannot be written until we know what binary/interface exists. If it is an API wrapper, it needs API keys in `.env`, adds per-token billing (not Claude Max subscription), and requires `google-generativeai` Python package. The cost model changes fundamentally.

2. **Question:** Is Nexus `list-projects --format json` a real CLI command, or only an MCP tool?
   **Why it matters:** `setup-vps.sh:252` calls this command. Looking at `src/app/cli/` in Nexus source, there is no `list-projects` CLI command — only `health`, `keygen`, `setup`, `deploy`. This means the existing Nexus integration block in setup-vps.sh silently fails on every VDS setup. Must be fixed or removed before Phase 3 builds on top of it.

3. **Question:** Who registers new projects in practice? How often?
   **Why it matters:** If projects are registered once every few months, `/addproject` is over-engineering. The real friction is "I need to SSH to add a line to JSON." Is `/addproject` solving a weekly pain or a once-per-quarter edge case?

4. **Question:** What is the Nexus runtime SSOT feature actually providing that SQLite doesn't already provide?
   **Why it matters:** `project_state` table in SQLite already IS the runtime SSOT. `seed_projects_from_json` populates it from `projects.json` every 300 seconds. Nexus holds the same data (project name, path) but adds encryption and graph overhead. What data in Nexus is NOT in projects.json? API keys? If so, that's a secrets-fetch use case, not SSOT.

5. **Question:** Should task-level routing be per-spec-type pattern (e.g., "all TECH tasks → codex") or per-spec-ID (e.g., "TECH-055 specifically → codex")?
   **Why it matters:** Per-type is a 5-line projects.json extension. Per-spec-ID is a runtime lookup table requiring new DB columns. They have 10x implementation complexity difference.

---

## Final Verdict

**Recommendation:** Proceed with caution — but split and descope

**Reasoning:** Phase 3 as scoped is 4 independent features at different risk levels bundled together. Two features are ready to build (task-level routing via projects.json, /addproject as single-line command). One feature has a broken dependency today (Nexus CLI integration — `list-projects` command doesn't exist). One feature needs a policy decision not code (global skills = symlinks). One feature should be killed (VPS docs = setup-vps.sh is the doc).

The Gemini provider specifically needs a gate: confirm Gemini CLI exists as a headless binary OR explicitly scope as "Gemini REST API wrapper" with new Python runner, new `.env` keys, and per-token billing implications.

**Conditions for success:**
1. Fix or remove the broken Nexus CLI block in setup-vps.sh BEFORE building Phase 3 (it calls `nexus list-projects --format json` which does not exist)
2. Confirm Gemini provider interface: headless CLI binary or REST API wrapper — they are different implementations
3. Add `flock` on `projects.json` writes if `/addproject` is implemented — concurrent write with orchestrator hot-reload is a real race condition at 300s poll intervals
4. Explicitly decide: Nexus as setup-time-only (recommended) or runtime SSOT (requires making Nexus a required systemd service on VDS)
5. Split into 2-3 tickets: routing is independent of /addproject is independent of global skills
