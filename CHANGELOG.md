# Changelog

All notable changes to DLD (Double-Loop Development) methodology.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [3.13] - 2026-03-29

### Added
- **Callback status enforcement (ADR-018)** — after every autopilot task, the orchestrator callback now verifies that both the spec file and `ai/backlog.md` are marked with the correct status. If the LLM missed the update (Edit tool failure, context overflow, max-turns exit), it auto-fixes and commits to develop. Success → `done`, failed pueue → `blocked`.
- **Orphan slot watchdog** — orchestrator now detects stale `compute_slots` entries (crash, restart, external kill) and releases them automatically each cycle, preventing permanent deadlocks where no new tasks could be dispatched.
- **Immediate OpenClaw wake** — after writing a pending-event for the conversation layer, the orchestrator now triggers an immediate wake instead of waiting up to 5 minutes for the next cron cycle.

### Changed
- **Orchestrator rewritten in Python** (ARCH-161) — replaced the bash + Telegram stack with a clean Python daemon (`orchestrator.py`, `callback.py`, `event_writer.py`). Removes Telegram dependency, adds structured SQLite state, proper error handling, and multi-layer label resolution.
- **Runner limits increased** — autopilot `TIMEOUT` raised from 30 → 60 minutes, `MAX_TURNS` from 30 → 80. Complex tasks (20+ files) were hitting the ceiling before merge.
- **Cycle notifications silenced** — intermediate Telegram notifications suppressed during `spark → autopilot → qa → reflect` cycle; only the final summary fires. Reduces noise when running multiple projects in parallel.
- **Spark always outputs `queued`** — removed `draft` from Spark output. Draft is manual-override only; Spark-created specs are always immediately ready for autopilot.
- **`/upgrade` protects custom scripts** — removed `scripts/` from `SAFE_GROUPS` so project-specific VPS scripts are never overwritten by framework upgrades.

### Fixed
- **`resumed` tasks were never picked up** — `scan_backlog()` only matched `queued`; the recovery flow (`blocked → resumed → in_progress`) was silently broken. Now matches `queued|resumed` case-insensitively.
- **`blocked` status preserved on Success** — when autopilot itself sets a spec to `blocked` (test failure, merge conflict) and exits with code 0, the callback no longer overwrites it to `done`.
- **Callback pueue socket mismatch** (BUG-164) — resolved race where the callback process couldn't reach the pueue socket. Agent output is now read from log files (Layer 1) and DB (Layer 2), with pueue CLI as last resort.
- **OpenClaw wake timeout** (BUG-163) — reduced blocking timeout from 30 → 5 seconds, downgraded to DEBUG level. Was adding 23+ seconds to every callback cycle.
- **Worktree stale branch cleanup** (TECH-149) — autopilot finishing phase now explicitly removes the feature branch after merge; stale worktrees no longer accumulate in `.worktrees/`.
- **Claude settings permissions** — moved `defaultMode` into the `permissions` block where Claude Code expects it; added `bypassPermissions` to template.

### Architecture
- **ADR-018: Callback status enforcement** — LLM-instructional status updates are inherently unreliable. The callback layer is now the enforcement point: it reads files after completion and corrects any mismatch deterministically, without LLM involvement.
- **Inbox scan case-insensitive** — `**Status:** new` matching now uses `re.IGNORECASE` for consistency with the rest of the status-matching layer.
- **Status enum validation** — `_VALID_STATUSES` frozenset gates all auto-fix writes; invalid values are rejected before touching files.

---

## [3.12] - 2026-03-02

### Added
- **Mock ban hook (ADR-013)** — deterministic hard-block of mock patterns (`jest.mock`, `vi.mock`, `MagicMock`, `@patch`, `sinon.stub`, etc.) in `tests/integration/`. LLM agents mock 38% more than humans (MSR 2026); this hook makes mocking in integration tests impossible, not just discouraged.
- **Integration test convention** — `docs/10-testing.md` updated with Testcontainers examples (Python + Node.js), allowed vs forbidden patterns table, and mutation testing section.
- **Integration test enforcement in agents** — coder agent now has Integration Test Check (Gate 5), tester agent routes DB/infra changes to integration tests, task-loop has Step 2a (conditional integration test check).
- **Mutation testing setup** — `stryker.config.mjs` template + weekly CI job (`mutation-test`) for measuring real test quality beyond coverage.
- **44 hook tests** — 10 new mock ban tests (all patterns, allow/deny, message content) added to pre-edit test suite.

### Changed
- **`hooks.config.mjs`** — added `mockBan` section (9 patterns, 3 integration test path matchers) and `requireIntegrationTests` enforcement flag.
- **`pre-edit.mjs`** — added `isIntegrationTest()`, `containsMockPattern()` helpers with fallback constants. Mock ban check runs between protected paths and plan-before-code gate.
- **`ci.yml`** — added `schedule` trigger (Monday 06:00 UTC) and `mutation-test` job.
- **Selection Algorithm** in tester agent — new step 4: "If file touches DB/infra → also run integration tests".

### Fixed
- **`@patch` regex** — changed `/\b@patch\b/` to `/@patch\b/` because `@` is not a word character, so `\b` before it never matches.

---

## [3.11] - 2026-03-01

### Added
- **Acceptance Verification system** — 3-layer verification pipeline ensuring code actually works in running systems, not just passes tests. Spark specs now include machine-executable `## Acceptance Verification` section (smoke + functional checks with copy-paste commands). Autopilot executes LOCAL VERIFY after every commit and POST-DEPLOY VERIFY after push. All results are non-blocking (warn only) for backwards compatibility.
- **`/upgrade` skill — INFRASTRUCTURE guard** — `upgrade.mjs` and `run-hook.mjs` now classified as INFRASTRUCTURE: never auto-applied via `--groups safe`, only via explicit `--files`. Prevents silent engine overwrites.
- **`/upgrade` skill — `--source` flag** — point upgrade to local template directory instead of GitHub (e.g., for monorepo setups or offline use).
- **Upgrade contract** — formal spec for upgrade engine behavior: PROTECTED, INFRASTRUCTURE, SAFE_GROUPS, rollback semantics. Lives in `.claude/contracts/upgrade-contract.md`.
- **`deprecated.json` manifest** — tracks removed/renamed files across versions; upgrade `--cleanup` automatically moves deprecated files to `.claude/.upgrade-trash/`.
- **Upgrade test suite** — 289-line test suite for upgrade engine (`scripts/__tests__/upgrade.test.mjs`).
- **`requireAcceptanceVerification` config flag** — hooks.config.mjs enforcement gate for AV section in specs (off by default, opt-in per project).

### Changed
- **`/upgrade` skill — PROTECTED expansion** — `hooks.config.mjs` added to PROTECTED set (was in SAFE_GROUPS, could be silently overwritten). User hook config is now always preserved across upgrades.
- **`/upgrade` skill — UPGRADE_SCOPE filter** — upgrade engine now only touches `.claude/` and `scripts/` files. Scaffolding (`pyproject.toml`, `ai/`, etc.) excluded entirely.
- **Upgrade rollback** — on validation failure after apply, engine auto-reverts via `git checkout -- .` and reports `rolled_back: true`.
- **autopilot-state.mjs** — added `verify` field to task state tracking (`VALID_STEPS` + `setPlan` task object).

### Fixed
- **`/upgrade` — hooks.config.mjs overwrite** — was listed in SAFE_GROUPS, silently wiping user hook customizations on every upgrade. Now PROTECTED.
- **Template `.gitignore`** — removed forced `ai/` and `brandbook/` entries from user project `.gitignore`. These are DLD-internal paths and should not be injected into user repos.

---

## [3.10] - 2026-02-26

### Added
- **`/upgrade` skill** — deterministic DLD framework updater: fetches latest template from GitHub, compares every file via SHA256, groups changes by category (agents, hooks, skills, rules, scripts), auto-applies safe groups, shows diff for conflicts. Never touches protected files (CLAUDE.md, localization.md, etc.)

### Changed
- **Cost estimates in skills** — `/spark`, `/board`, `/council`, `/architect`, `/triz` now show upfront cost estimates before launching multi-agent pipelines (~$2–15 depending on depth)
- **Degraded mode documentation** — all multi-agent skills document fallback behavior when MCP tools are unavailable (no silent degradation)

### Fixed
- **Bug Hunt** — Definition of Done replaced with structured Eval Criteria format (ADR-012), enabling machine-parseable quality gates in Bug Hunt specs
- **Upgrade dirty-tree check** — untracked files no longer incorrectly block upgrade (was using `git status --porcelain`, now uses `git diff --quiet HEAD`)

---

## [3.9] - 2026-02-22

### Added
- **Eval-Driven Development (EDD)** — 5-wave methodology replacing freeform tests with structured evaluation criteria (ADR-012)
- **Structured Eval Criteria format** — machine-parseable `## Eval Criteria` section in specs with deterministic/integration/llm-judge assertion types, TDD order, and coverage summary
- **Devil structured assertions** — DA-N (deterministic) and SA-N (side-effect) table format replacing freeform edge case lists
- **Regression Flywheel** — automatic regression test generation from debugger root cause analysis
- **LLM-as-Judge eval type** — 5-dimension scoring (Completeness, Accuracy, Format, Relevance, Safety) with rubric-based evaluation
- **Agent Prompt Eval Suite** — `/eval` skill for testing agent prompt quality against golden datasets (3 agents × 3 pairs = 9 test cases)
- **eval-judge agent** — specialized agent for rubric-based output scoring with threshold validation
- **Brandbook v2** — complete brand identity system with anti-convergence principles, design tokens, and coder handoff
- **Enforcement as Code (ADR-011)** — JSON state files + hooks + hard gates for process enforcement
- **autopilot-state.mjs** — state management script for phase/task tracking
- **spark-state.mjs** — 8-phase state tracking for Spark sessions
- **test-wrapper.mjs** — Smart Testing with scope protection
- **eval-judge.mjs** — CLI parser for eval criteria extraction from specs

### Changed
- **Spark feature mode** — now writes `## Eval Criteria` instead of `## Tests`, with DA→EC mapping from devil scout
- **Devil scout** — outputs structured assertions (`## Eval Assertions` with DA-N/SA-N IDs) instead of freeform edge cases
- **Tester agent** — integrated eval criteria testing with deterministic/integration/llm-judge support
- **6 multi-agent skills** — migrated to ADR-007/008/009/010 zero-read pattern (spark, audit deep, bug hunt, council, architect, board)
- **Bug Hunt findings collector** — added caller-writes fallback for ADR-010 verification
- **Autopilot task loop** — integrated regression capture step after debug loops
- **Debugger agent** — now includes regression test spec in output
- **Spec validation** — dual-detection for `## Eval Criteria` (priority) and `## Tests` (fallback) for backward compatibility
- **Pre-edit hook** — enforces eval criteria minimums (3 criteria, coverage summary, TDD order)
- **validate-spec-complete hook** — extended with eval criteria validation

### Fixed
- **Planner ALWAYS runs** — resolved contradiction between autopilot files with WHY explanations and VIOLATION markers
- **Brandbook MCP detection** — simplified to ToolSearch + ask user instead of silent fallbacks

### Architecture
- **ADR-007** — Caller-writes pattern for subagent output (agents can't reliably write files, caller writes from response)
- **ADR-008** — Background fan-out pattern (`run_in_background: true` prevents context flooding)
- **ADR-009** — Background ALL steps (sequential foreground agents accumulate context)
- **ADR-010** — Orchestrator zero-read (TaskOutput floods context, collector subagent reads + summarizes)
- **ADR-011** — Enforcement as Code (JSON state + hooks + hard gates, not LLM memory)
- **ADR-012** — Eval Criteria over freeform Tests (structured, machine-parseable, traceable)
- **EDD pipeline** — Spark (8 phases) → Devil (DA-N assertions) → Facilitator (DA→EC mapping) → Autopilot → Tester (EC validation)
- **Golden datasets structure** — `test/agents/{agent}/golden-NNN.{input,output,rubric}.md` for agent prompt evaluation
- **E2E verification** — FTR-135 example (API version endpoint) validates full EDD cycle

---

## [3.8] - 2026-02-19

### Fixed
- **Planner ALWAYS runs — hardened** — added WHY explanation and VIOLATION markers across all autopilot files. Planner re-reads codebase before every spec because prior specs make old plans stale

### Changed
- `skills/autopilot/subagent-dispatch.md` — WHY always block + ⛔ VIOLATION marker
- `skills/autopilot/SKILL.md` — Pre-flight Check: ⛔ skipping planner = VIOLATION
- `agents/planner.md` — Critical Context #5 expanded: re-read ALL Allowed Files

---

## [3.7] - 2026-02-14

### Added
- **Bug Hunt Mode in Spark** — multi-agent deep bug analysis integrated into `/spark` workflow
- **TOC Analyst agent** — Theory of Constraints analysis (Current Reality Tree, constraint identification)
- **TRIZ Analyst agent** — TRIZ analysis (contradictions, Ideal Final Result, inventive principles)
- **Validator agent** — filters findings by relevance, deduplicates, triages
- **Solution Architect agent** — creates atomic sub-specs per finding with Impact Tree
- **Umbrella specs** — `ai/features/BUG-XXX/` directory with sub-specs for complex bugs

### Changed
- Bug Hunt persona agents upgraded from Haiku to **Sonnet** (6 agents: code-reviewer, security-auditor, ux-analyst, junior-developer, software-architect, qa-engineer)
- Red Team agent replaced by **TOC Analyst** (theory-driven constraint analysis)
- Systems Thinker agent replaced by **TRIZ Analyst** (contradiction-driven inventive solutions)
- Bug mode now has two tracks: **Quick** (5 Whys, simple bugs) and **Bug Hunt** (multi-phase pipeline)
- Spark mode detection expanded to three modes: Feature, Quick Bug, Bug Hunt

### Removed
- Standalone `/bug-hunt` skill — functionality absorbed into Spark's Bug Hunt Mode
- Red Team agent (`bughunt-red-team`) — replaced by TOC Analyst
- Systems Thinker agent (`bughunt-systems-thinker`) — replaced by TRIZ Analyst

### Architecture
- Bug Hunt pipeline: Phase 1a (6 Sonnet personas) → Phase 1b (2 Opus frameworks) → Phase 2 (Opus validator) → Phase 3 (Opus solution architects) → Autopilot
- All bug-hunt agents moved to `template/.claude/agents/bug-hunt/` (universal, not DLD-specific)

---

## [3.6] - 2026-02-08

### Changed
- **Hooks rewritten from Python/Bash to Node.js** — zero Python dependency, cross-platform (macOS/Windows/Linux)
- All `.py` hooks → `.mjs` (ESM): `pre-bash`, `pre-edit`, `post-edit`, `prompt-guard`, `utils`
- All `.sh` hooks → `.mjs`: `session-end`, `validate-spec-complete`
- New `run-hook.mjs` — universal hook runner with git worktree support
- `settings.json` commands simplified: `node .claude/hooks/run-hook.mjs <hook-name>`

### Removed
- Python hook files (`.py`) — replaced by Node.js equivalents
- Bash hook files (`.sh`) — replaced by Node.js equivalents
- Python hook tests (`tests/test_*hook*.py`) — JS equivalents needed

### Migration
- **Existing users:** see `template/.claude/hooks/README.md` or run the upgrade prompt below
- **New users:** no action needed, template includes Node.js hooks

### Upgrade from 3.5

Paste this prompt into Claude Code in your project:

```
Upgrade DLD hooks to v3.6 (Node.js). Steps:

1. Download 8 files from DLD repo using gh CLI:
   for f in run-hook.mjs utils.mjs pre-bash.mjs pre-edit.mjs post-edit.mjs prompt-guard.mjs session-end.mjs validate-spec-complete.mjs; do
     gh api repos/Ellevated/dld/contents/template/.claude/hooks/$f --jq '.content' | base64 -d > .claude/hooks/$f
   done

2. Update .claude/settings.json — replace ALL hook commands with this format:
   "command": "node .claude/hooks/run-hook.mjs <hook-name>"
   Hook names: pre-bash, pre-edit, post-edit, prompt-guard, session-end, validate-spec-complete
   Remove all bash -c wrappers and python3 calls. See template/.claude/settings.json in the DLD repo for reference.

3. Delete old files: rm .claude/hooks/*.py .claude/hooks/*.sh

4. Test: echo '{"tool_input":{"command":"git push origin main"}}' | node .claude/hooks/pre-bash.mjs
   Expected: JSON with "permissionDecision": "deny"

Python is no longer required for hooks.
```

Or manually: copy all `.mjs` files from `template/.claude/hooks/` and update `settings.json`.

---

## [3.5] - 2026-02-08

### Added
- **Model capabilities rule** — `rules/model-capabilities.md` documents Opus 4.6 features, effort routing strategy, and breaking changes
- **Effort routing** — each agent now declares `effort:` level in YAML frontmatter (max/high/medium/low) for optimized cost/quality tradeoff
- **ADR-005** — Effort routing per agent: max for planning and council, high for coding and review, medium for testing, low for logging
- **ADR-006** — No assistant prefilling: Opus 4.6 removed prefilling support, use structured outputs instead

### Changed
- All 14 agent frontmatter files updated with `effort:` field
- Architecture rules updated with two new ADRs

### Compatibility
- **Claude Opus 4.6** (released Feb 5, 2026) — fully supported
- Adaptive thinking, 1M context window (beta), 128K output tokens
- Recommended CLI version: **2.1.36+**

---

## [3.4] - 2026-01-26

### Added
- **Bootstrap skill** — Day 0 discovery, unpack idea from founder's head
- **Claude-md-writer skill** — CLAUDE.md optimization with 3-tier modular system
- **Council decomposition** — 5 separate expert agents in `agents/council/`
- **Spark agent** — dedicated agent file for idea generation
- **Diary recorder** — auto-captures problems for future reflection
- **Wrapper skills** — tester/coder/planner as standalone invocable skills
- **Research tools** — Exa + Context7 MCP integration in agents
- **Scout skill** — isolated research agent for external sources
- **Reflect skill** — synthesize diary entries into CLAUDE.md rules

### Changed
- README rewritten as hero landing page with Mermaid diagrams
- All documentation translated to English
- Skills and agents fully translated to English

### Documentation
- Added FAQ.md with 20+ questions
- Added COMPARISON.md with fair alternatives analysis
- Added 3 example projects (marketplace, content factory, AI company)
- Added MCP setup guide for Context7 and Exa

---

## [3.2] - 2026-01-24

### Added
- GitHub community files (CONTRIBUTING, CODE_OF_CONDUCT, SECURITY)
- Issue and PR templates
- Hooks system with README documentation

### Changed
- Template CLAUDE.md translated to English

---

## [3.1] - 2026-01-23

### Added
- Autopilot skill split into 7 modular files
- Template sync from production project

### Changed
- Removed hardcoded project-specific references from template

---

## [3.0] - 2026-01-23

Initial public release of DLD methodology.

### Added
- **Core methodology** — Double-Loop Development concept
- **Project structure** — shared/infra/domains/api layers
- **Skills system** — spark, autopilot, council, audit
- **Agent prompts** — planner, coder, tester, reviewer, debugger
- **Documentation** — 19 methodology docs + 3 foundation docs
- **Template** — ready-to-use project template with CLAUDE.md

### Architecture
- Result pattern for explicit error handling
- Async everywhere for IO operations
- Money in cents (no floats)
- Max 400 LOC per file (LLM-friendly)
- Max 5 exports per `__init__.py`

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| 3.9 | 2026-02-22 | Eval-Driven Development (EDD) — structured eval criteria, LLM-as-Judge, agent eval suite, ADR-012 |
| 3.8 | 2026-02-19 | Planner ALWAYS runs — hardened with WHY + VIOLATION markers |
| 3.7 | 2026-02-14 | Bug Hunt Mode in Spark, TOC+TRIZ agents, multi-phase pipeline |
| 3.6 | 2026-02-08 | Hooks migrated to Node.js — zero Python dependency, cross-platform |
| 3.5 | 2026-02-08 | Opus 4.6 support, effort routing, model capabilities rule |
| 3.4 | 2026-01-26 | Bootstrap, Claude-md-writer, Council decomposition, English translation |
| 3.2 | 2026-01-24 | GitHub community files, Hooks system |
| 3.1 | 2026-01-23 | Autopilot modularization, Template sync |
| 3.0 | 2026-01-23 | Initial release |
