# Architecture

Architectural decisions and patterns for the project.

## Project Structure

```
src/
├── shared/     # Result, exceptions, types (NO business logic)
├── infra/      # db, llm, external (technical adapters)
├── domains/    # Business logic
└── api/        # Entry points (telegram, http, cli)
```

## Import Direction

```
shared ← infra ← domains ← api
       (NEVER in reverse)
```

**Rule:** Each layer can only import from layers to the left of it.

---

## Patterns (FOLLOW)

| Pattern | Where to apply | Example |
|---------|----------------|---------|
| Result[T, E] | All domain functions | `async def get_user() -> Result[User, UserError]` |
| Async everywhere | All IO operations | `async def`, `await` |
| Cents for money | All money-related | `amount: int` (not float, not Decimal) |
| Explicit errors | Domain boundaries | `UserNotFoundError`, not generic Exception |

---

## Anti-patterns (FORBIDDEN)

| What | Why | Instead |
|------|-----|---------|
| Float for money | Precision loss | int (cents) |
| Bare exceptions | Hides errors | Explicit error types |
| Cross-domain import | Coupling | Through infra or shared |
| File > 400 LOC | LLM-unfriendly | Split into modules |
| Circular imports | Architectural problem | Refactor dependencies |
| Shell SQL interpolation | SQL injection, no parameterization in bash | `python3 db.py <cmd>` with `?` placeholders |
| `datetime.utcnow()` | Deprecated Python 3.12+ | `datetime.now(tz=timezone.utc)` |

**Exception:** Bare `except Exception:` is ALLOWED in `.claude/hooks/` for fail-safe behavior.
Hooks must never crash — a crashing hook breaks Claude Code. See ADR-004.

---

## Shell Script Safety

| Rule | Why | Instead |
|------|-----|---------|
| NEVER interpolate variables in SQL strings | SQL injection (FTR-146 Task 3) | Python with parameterized queries (`?` placeholders) |
| Verify CLI flags against `--help` | Invalid flags + set -e = silent failures (FTR-146 Task 2) | `tool --help \| grep flag` before using |
| Prefer Python for scripts > 50 LOC | Shell is fragile, 75% failure rate in FTR-146 | Python with subprocess for shell commands |
| Use `set -euo pipefail` + test error paths | `set -e` has edge cases in pipes and subshells | Explicit `\|\| handle_error` for critical sections |
| Double-quote all variables | Word splitting, globbing bugs | `"$var"` not `$var` |

---

## ADR (Architecture Decision Records)

> **Orchestrator-specific decisions** (callback contract, guard, audit log) are documented in
> `~/.claude/projects/-root/memory/dld-orchestrator.md` §6. This file lists project-wide ADRs only;
> orchestrator details are forward-pointed below.

| ID | Decision | Date | Reason |
|----|----------|------|--------|
| ADR-001 | Money in cents | 2026-01 | Avoid float precision errors |
| ADR-002 | Result instead of exceptions | 2026-01 | Explicit error handling |
| ADR-003 | Async everywhere | 2026-01 | Consistency, performance |
| ADR-004 | Bare exceptions in hooks | 2026-02 | Hooks are fail-safe infrastructure — must never crash |
| ADR-005 | Effort routing per agent | 2026-02 | Opus 4.6 effort parameter: max for planning/council, high for coding/review, medium for testing, low for logging |
| ADR-006 | No assistant prefilling | 2026-02 | Opus 4.6 removed prefilling support — use structured outputs or system prompts |
| ADR-007 | Caller-writes for subagent output | 2026-02 | Subagents can't reliably write files (0/36, GitHub #7032). Caller writes from response. |
| ADR-008 | Background fan-out for parallel agents | 2026-02 | `run_in_background: true` prevents context flooding. Responses go to temp files, not parent context. |
| ADR-009 | Background ALL pipeline steps | 2026-02 | Sequential foreground agents accumulate in orchestrator context. ALL steps use `run_in_background: true`. |
| ADR-010 | Orchestrator zero-read | 2026-02 | Orchestrator NEVER reads agent outputs directly (TaskOutput floods context, ~70K+). Collector subagent reads + summarizes. |
| ADR-011 | Enforcement as Code | 2026-02 | Process enforcement via JSON state + hooks + hard gates, not LLM memory. State files are SSOT for phase/task progress. |
| ADR-012 | Eval Criteria over freeform Tests | 2026-02 | Structured eval criteria (deterministic + integration + llm-judge) provide measurable, repeatable quality gates. Backward compat with legacy ## Tests. |
| ADR-013 | Mock ban in integration tests | 2026-03 | LLM agents mock 38% more than humans (MSR 2026). Hook hard-blocks mock patterns in tests/integration/. |
| ADR-014 | Data Architect gets agenda priority in /architect | 2026-03 | Cross-critique confirmed most impactful persona (SIGNAL-008) |
| ADR-015 | Devil uses Evaporating Cloud for contradiction resolution | 2026-03 | Formal resolution > freeform critique (SIGNAL-009) |
| ADR-016 | DDD linguistic test for domain names | 2026-03 | Technical terms masquerading as domains must be rejected (SIGNAL-010) |
| ADR-017 | SQL only via Python parameterized queries | 2026-03 | Shell interpolation = SQL injection (FTR-146 Task 3) |
| ADR-018 | **[SUPERSEDED by ADR-023]** Callback status enforcement via markdown editing. Worked but suffered from autostash race (BUG-185 = formerly BUG-974). Replaced by ADR-023 lifecycle SoT. Historical: LLM status updates unreliable, callback auto-fixed spec+backlog with implementation guard (TECH-166), auto-close path (TECH-176). Degrades open. См. dld-orchestrator.md§5 |
| ADR-019 | Model routing rebalance for Opus 4.7 era | 2026-04 | Opus 4.7 on structured merge/format tasks overthinks without quality gain. Synthesizers (audit/board/triz) → sonnet high. Formatters (documenter, bughunt scope-decomposer/findings-collector/report-updater, diary-recorder) → haiku low. Est. 30–40% cost reduction at same quality. See `rules/model-capabilities.md`. |
| ADR-020 | No headless loop wrapper from inside Claude Code | 2026-04 | `scripts/autopilot-loop.sh` invokes `claude --print` subprocess without `--setting-sources` → subagents don't resolve, costs explode (BUG-327: 117 turns, $50, FAIL). Interactive `/autopilot` uses native Agent/Skill tools in current session. VPS orchestrator uses Agent SDK (setting_sources loaded). The bash wrapper is kept only for manual operator use outside Claude Code. |
| TECH-166 | Callback implementation guard: git-diff verify before mark-done | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-167 | Spark canonical `## Allowed Files` + `<!-- callback-allowlist v1 -->` marker | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-168 | Callback test suite (unit + integration + regression) | 2026-05 | См. dld-orchestrator.md§9 |
| TECH-169 | Orchestrator circuit-breaker on mass-demote (>3/10min) | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-170 | Implementation guard sees feature-branch commits (`--all`) | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-171 | Guard structured audit log (JSONL per verify_status_sync call) | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-172 | Single status write path: callback is the only writer | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-174 | Manual spec verification protocol (operator checklist) | 2026-05 | См. dld-orchestrator.md§8 |
| TECH-176 | Guard auto-close path: detect "already merged before started_at" via `_spec_has_merged_implementation` (`--grep <spec_id>` ∩ `-- <allowed>`) | 2026-05 | См. dld-orchestrator.md§6 |
| ADR-021 | Hermes intake gate: orchestrator `scan_inbox` диспатчит только `Status: queued` (Hermes-promoted); `new`/`draft`/`clarifying`/`stale`/`rejected` игнорируются. Clean break, no auto-migration. | 2026-05 | TECH-181: business-gate перед Spark, разделение Hermes (бизнес) / Spark (техника) |
| ADR-022 | Hermes intake supervisor: Hermes — единственный writer статуса `queued` в `ai/inbox/`. QA, reflect, post-autopilot события и Telegram-бридж пишут intake-файлы со `Status: draft`; их артефакты живут в `ai/reflect/`, `ai/qa/` или внутри spec, но не в inbox со `queued`. SSOT по lifecycle — `ai/inbox/README.md`, статусы синхронизированы с regex в `scan_inbox` (`scripts/vps/orchestrator.py`). | 2026-05 | TECH-184: документационный слой поверх TECH-181 hard gate; единый язык вместо «OpenClaw» |
| ADR-023 | **Lifecycle state SoT = git per-spec YAML.** Status и blocked_reason живут в `ai/lifecycle/{spec_id}.yaml`. callback = единственный writer через atomic git plumbing (private `GIT_INDEX_FILE` + CAS `git update-ref` + commit-tree) — never touches working tree. Markdown (backlog.md, spec body) — read-only render. "No dirty WT" invariant: `orchestrator.assert_clean_lifecycle_tree()` aborts startup если `ai/lifecycle/` грязный. Reader: filesystem glob `ai/lifecycle/*.yaml`. Bootstrap: orchestrator создаёт `lifecycle.create_initial()` для новых spec.md без yaml. Multi-machine: все узлы — readers через `git pull`. **Supersedes ADR-018** (callback больше не пишет markdown). **Closes BUG-185** (autostash race невозможна — WT не трогается). Удалён `marker_utils.py` (117 LOC), `_restore_callback_markers_from_head` (54 LOC), `verify_status_sync` старая (284 LOC, упрощена до ~50). | 2026-05 | ARCH-186 — Council #2: 3 reject Issues / 1 approve; convergence Pragmatist+Security+Product на git-per-spec-yaml. См. ARCH-186 spec для full rationale. |
| ADR-024 | **claude-runner exit_code contract.** Once `ResultMessage(is_error=False)` is received, the run is considered successful regardless of subsequent SDK exceptions. Post-result exceptions are logged as WARNING (not ERROR) and recorded in `sdk_post_result_errors` for diagnostics, but do NOT override `exit_code=0`. Symmetric front-side guard: autopilot early-exits if Allowed Files have implementation commits newer than spec creation date (mirrors callback `_spec_has_merged_implementation`). | 2026-05 | BUG-188 — false-fail on post-ResultMessage Exception burned $258/week on retries. See spec for trace. |

---

## Limits

| What | Limit | Reason |
|------|-------|--------|
| LOC per file | 400 (600 for tests) | LLM context window |
| Exports in __init__.py | 5 | Explicit public API |
| Nesting depth | 3 levels | Readability |
| Function arguments | 5 | Cognitive load |
