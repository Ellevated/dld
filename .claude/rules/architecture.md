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
| ADR-005 | Effort routing per agent | 2026-02 | Opus 4.6 effort parameter: max for planning/council, high for coding/review, medium for testing, low for logging. (2026-06: under Opus 4.8, overthinking is governed by the effort parameter; routing levels unchanged — see ADR-028.) |
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
| ADR-019 | Model routing rebalance for Opus 4.7 era | 2026-04 | Opus 4.7 on structured merge/format tasks overthinks without quality gain. Synthesizers (audit/board/triz) → sonnet high. Formatters (documenter, bughunt scope-decomposer/findings-collector/report-updater, diary-recorder) → haiku low. Est. 30–40% cost reduction at same quality. See `rules/model-capabilities.md`. (2026-06: rationale predates Opus 4.8. Routing logic retained — sonnet/haiku downgrades remain a cost win; no 4.8 benchmark yet justifies reverting. See ADR-028.) |
| ADR-020 | No headless loop wrapper from inside Claude Code | 2026-04 | `scripts/autopilot-loop.sh` invokes `claude --print` subprocess without `--setting-sources` → subagents don't resolve, costs explode (BUG-327: 117 turns, $50, FAIL). Interactive `/autopilot` uses native Agent/Skill tools in current session. VPS orchestrator uses Agent SDK (setting_sources loaded). The bash wrapper is kept only for manual operator use outside Claude Code. |
| TECH-166 | Callback implementation guard: git-diff verify before mark-done | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-167 | Spark canonical `## Allowed Files` + `<!-- callback-allowlist v1 -->` marker | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-168 | Callback test suite (unit + integration + regression) | 2026-05 | См. dld-orchestrator.md§9 |
| TECH-169 | Orchestrator circuit-breaker on mass-demote (>3/10min) | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-170 | **[SUPERSEDED ~2026-05-21]** Implementation guard sees feature-branch commits (`--all`). Guard переписан на чистый origin/develop-gate `_is_done_on_develop` — без `--all`, done только при коммите на origin/develop. См. `docs/orchestrator/status-model.md#guard` |
| TECH-171 | Guard structured audit log (JSONL per verify_status_sync call) | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-172 | Single status write path: callback is the only writer | 2026-05 | См. dld-orchestrator.md§6 |
| TECH-174 | Manual spec verification protocol (operator checklist) | 2026-05 | См. dld-orchestrator.md§8 |
| TECH-176 | **[SUPERSEDED ~2026-05-21]** Guard auto-close path: detect "already merged before started_at" via `_spec_has_merged_implementation`. Auto-close + `_spec_has_merged_implementation` убраны при редизайне guard на origin/develop-gate. См. `docs/orchestrator/status-model.md#guard` |
| ADR-029 | Opus 5 era rebalance: (a) main loop + all agents re-pinned to `claude-opus-5` / `claude-sonnet-5`; (b) effort sweep — `max` reserved for genuinely frontier work only (Anthropic: max causes overthinking on structured tasks), facilitators max→medium, council/triz/debugger max→high; (c) `review` moved sonnet/xhigh → **opus/low** (Opus 5 code-review accuracy holds at low effort); (d) `_shared/output-conventions.md` added to every agent — length calibration, scope discipline, no self-verification, subagent damping. See `rules/model-capabilities.md`. | 2026-07 |
| ADR-021 | Hermes intake gate: orchestrator `scan_inbox` диспатчит только `Status: queued` (Hermes-promoted); `new`/`draft`/`clarifying`/`stale`/`rejected` игнорируются. Clean break, no auto-migration. | 2026-05 | TECH-181: business-gate перед Spark, разделение Hermes (бизнес) / Spark (техника) |
| ADR-022 | Hermes intake supervisor: Hermes — единственный writer статуса `queued` в `ai/inbox/`. QA, reflect, post-autopilot события и Telegram-бридж пишут intake-файлы со `Status: draft`; их артефакты живут в `ai/reflect/`, `ai/qa/` или внутри spec, но не в inbox со `queued`. SSOT по lifecycle — `ai/inbox/README.md`, статусы синхронизированы с regex в `scan_inbox` (`scripts/vps/orchestrator.py`). | 2026-05 | TECH-184: документационный слой поверх TECH-181 hard gate; единый язык вместо «OpenClaw» |
| ADR-023 | **[AMENDED by ADR-025]** **Lifecycle state SoT = git per-spec YAML.** Status и blocked_reason живут в `ai/lifecycle/{spec_id}.yaml`. callback = единственный writer через atomic git plumbing (private `GIT_INDEX_FILE` + CAS `git update-ref` + commit-tree) — never touches working tree. Markdown (backlog.md, spec body) — read-only render. "No dirty WT" invariant: `orchestrator.assert_clean_lifecycle_tree()` aborts startup если `ai/lifecycle/` грязный. Reader: filesystem glob `ai/lifecycle/*.yaml`. Bootstrap: orchestrator создаёт `lifecycle.create_initial()` для новых spec.md без yaml. Multi-machine: все узлы — readers через `git pull`. **Supersedes ADR-018** (callback больше не пишет markdown). **Closes BUG-185** (autostash race невозможна — WT не трогается). Удалён `marker_utils.py` (117 LOC), `_restore_callback_markers_from_head` (54 LOC), `verify_status_sync` старая (284 LOC, упрощена до ~50). **ADR-025 amendment:** Rule 7 теперь structural в `lifecycle.write_lifecycle`; `autopilot`/`spark` удалены из `_ALLOWED_WRITERS`. | 2026-05 | ARCH-186 — Council #2: 3 reject Issues / 1 approve; convergence Pragmatist+Security+Product на git-per-spec-yaml. См. ARCH-186 spec для full rationale. |
| ADR-024 | **claude-runner exit_code contract.** Once `ResultMessage(is_error=False)` is received, the run is considered successful regardless of subsequent SDK exceptions. Post-result exceptions are logged as WARNING (not ERROR) and recorded in `sdk_post_result_errors` for diagnostics, but do NOT override `exit_code=0`. Symmetric front-side guard: autopilot early-exits if Allowed Files have implementation commits newer than spec creation date (mirrors callback `_spec_has_merged_implementation`). | 2026-05 | BUG-188 — false-fail on post-ResultMessage Exception burned $258/week on retries. See spec for trace. |
| ADR-025 | **Lifecycle write-once-done invariant (Rule 7 structural).** Rule 7 переехала из `callback.verify_status_sync` в примитив `lifecycle.write_lifecycle`. Любая попытка `done → !done` (любым writer'ом) → `LifecycleAlreadyDoneError`. `autopilot` и `spark` удалены из `_ALLOWED_WRITERS` (autopilot сигналит через `task_status: complete` JSON; spark не имеет callers). Operator escape — `spec_operator force-done --by=operator` (сохраняется; `--by=autopilot`/`--by=spark` REMOVED из argparse choices, rc=5 при попытке demote done). Pre-commit hook ужесточён: ANY staged `ai/lifecycle/*.yaml` blocked unless `LIFECYCLE_WRITE_AUTHORIZED=1` (logged to audit via `event_writer.py`). Hook installation сделана idempotent в `setup-vps.sh --phase4-hooks` для всех VPS проектов. Skill prompts (coder, finishing, autopilot-git × root+template) содержат hard rule "NEVER git add ai/lifecycle/". Amends ADR-023. | 2026-05 | ARCH-193 + forensic on awardybot FTR-1078 (autopilot direct git add path confirmed). Council 4/4 approve_with_changes Variant 2-strict. |
| TECH-194 | **ARCH-193 follow-up — three delivery layers.** **Layer C (hook coverage):** `core.hooksPath` теперь absolute (`setup-vps.sh --phase4-hooks` + `install-hooks-all-worktrees.sh` migration helper); pre-commit wrapper резолвит guard через `git rev-parse --git-common-dir` → guard всегда найден из worktree независимо от состояния ветки (eliminates fail-open); `guard.mjs` резолвит `event_writer.py` относительно `import.meta.url` → audit event пишется для DLD repo из любого worktree. **Layer D (WT sync):** заменён `git checkout-index --force` на `git checkout HEAD -- <path>` в `_atomic_write` + `_atomic_write_file` — атомарно обновляет default `.git/index` и WT (раньше private GIT_INDEX_FILE оставлял staged deletion `D  `, ломал `assert_clean_lifecycle_tree` при рестарте оркестратора). Покрывает `write_lifecycle` И `create_initial`. **Layer E (dispatch gate):** callback Step 6 (qa+reflect dispatch) теперь gated на `task_status in ('blocked','needs_review')` — не сжигает ~$2.50/blocked задачу на ложный диспатч. **Tools:** `scripts/vps/install-hooks-all-worktrees.sh` (relative→absolute migration), `scripts/vps/cleanup-lifecycle-drift.sh` (one-shot recovery от dirty `ai/lifecycle/`). Amends ADR-023 + ADR-024 + ADR-025. | 2026-05 | Follow-up на ARCH-193 — наблюдения 25.05 за оркестратором показали 3 unblocked поверхностных слоя (autopilot direct commit bypassed hook, dowry/awardybot lifecycle drift, $2.61 burn на blocked). |
| ADR-026 | **Bootstrap parser safety contract.** `orchestrator.bootstrap_new_specs` (1) использует column-aware backlog parser `_parse_backlog` (находит header row + `---` divider, case-insensitive map по headers, сначала named `status` column, fallback — скан всех cells на valid enum); (2) при невозможности извлечь status fail'ится в `queued` (НЕ `done`), логирует WARNING `BOOTSTRAP_UNPARSABLE` + инкрементит `ai/.bootstrap-unparsable-count` (Hermes-monitored counter); (3) терминальные состояния (`done`, `blocked`) создаются ТОЛЬКО через callback/operator, никогда — bootstrap fallback'ом. Recovery от исторических bootstrap-as-done — narrow Rule 7 escape `lifecycle.recover_bootstrap_artifact` (валидирует 4-criteria signature: `status=done` ∧ `transitions=[]` ∧ `pueue_id=None` ∧ `finished_at=None`; raises `NotBootstrapArtifactError` иначе) + operator helper `scripts/vps/recover_bootstrap_as_done.py` (dry-run default). Multi-project drift visibility — `scripts/vps/lifecycle_audit.py` (READ-ONLY, 14 категорий: orphans/mismatches/dirty/counters/divergence). Closes lifecycle integrity gap left by ARCH-186/193 + TECH-194. | 2026-05 | TECH-195 — silent bootstrap-as-done на awardybot (TECH-1082, BUG-1074): positional regex с layout drift backlog'а на короткий формат `| ID | status | kind |` → fall-through к `status=done` → never dispatched + impossible to recover (Rule 7 blocks operator demote). |
| ADR-027 | Spec-first ID generation via lifecycle.create_initial CAS (Kafka pattern). Spark claims ID by attempting create_initial(by='spark'); LifecycleWriteRaceError triggers retry (max 5). `_ALLOWED_WRITERS_FOR_CREATE = {spark} | _ALLOWED_WRITERS` allows spark to invoke create_initial ONLY (not write_lifecycle — Rule 7 still protects status mutations). Residual risk: `--no-verify` / `core.hooksPath=` client-side hook bypass remains — defer to TECH-NNN server-side `pre-receive` enforcement. | 2026-05-27 | ARCH-196 — multi-master ID race elimination |
| ADR-028 | Opus 4.8 config alignment. claude-runner pins effort via `AUTOPILOT_EFFORT` env (default `high`; SDK enum `low\|medium\|high\|max`, no xhigh — xhigh is CLI/frontmatter-only). `model-capabilities.md` Effort Routing table synced to frontmatter SSOT: planner high, council max, coder high, triz analysts max, facilitators max. ADR-019 routing logic unchanged (sonnet/haiku downgrades remain a cost win). Template agent frontmatter caught up to ADR-019 (9 files). xhigh-for-agentic upside deferred pending TIMEOUT_SECONDS increase + benchmarks. | 2026-06 | TECH-203 — config/doc drift surfaced by Opus 4.8 audit; table diverged from frontmatter SSOT; template never received ADR-019 rebalance. |

---

## Limits

| What | Limit | Reason |
|------|-------|--------|
| LOC per file | 400 (600 for tests) | LLM context window |
| Exports in __init__.py | 5 | Explicit public API |
| Nesting depth | 3 levels | Readability |
| Function arguments | 5 | Cognitive load |
