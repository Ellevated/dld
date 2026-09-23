# Codebase Research — TECH-223: Three Orchestrator Holes (2026-09-23)

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `runner_refusal._refusal_from_message` / `_refusal_summary` | `scripts/vps/runner_refusal.py:30-106` | Duck-typed, stdlib-only per-message classifier-decline detector; owns its own exit-code decision (exit 4), has its own telemetry table (`classifier_refusals`) and its own test file | **Pattern to clone** for rate-limit detection — same shape: inspect every SDK message in `runner_loop.consume`, collect events into `state`, summarize once, decide an exit code |
| `claude_agent_sdk.RateLimitEvent` / `RateLimitInfo` | installed SDK 0.1.81, `types.py:1180-1223`, exported from `claude_agent_sdk/__init__.py:99-101` | **Already-structured** message the CLI emits on every rate-limit transition: `status` (`allowed`\|`allowed_warning`\|`rejected`), `resets_at` (unix ts), `rate_limit_type` (`five_hour`\|`seven_day`\|...), `raw` dict | Import directly — `isinstance(message, RateLimitEvent)` in `consume()`, exactly parallel to the existing `AssistantMessage`/`ResultMessage` checks |
| `ResultMessage.api_error_status` | SDK `types.py:1165`, parsed at `message_parser.py:271` | HTTP status (e.g. 429) of the failing API call when `is_error=True`. **Currently read nowhere** — `runner_result.apply_result_message` (runner_result.py:193-222) ignores it entirely | Add one field read in `apply_result_message`; no transcript-file parsing needed for the common case |
| `db_decisions.py` + `db._delegate` pattern | `scripts/vps/db_decisions.py`, `db.py:335-358` | Pure-leaf table-writer pattern (`classifier_refusals`, `callback_decisions`) bound onto `db.<name>` via `functools.wraps` delegate | Clone for a new `rate_limit_pauses` (or similar) table if DB-backed persistence is chosen over a state file |
| `lifecycle.reconcile_orphans` | `scripts/vps/lifecycle.py:331-350` | Existing precedent for **demoting `in_progress` → `queued`** with `reason=...`, `by="orchestrator"` | Exact precedent for the "spec goes back to queued, not blocked" requirement in (b) — same `write_lifecycle(..., "queued", reason=..., by="callback")` shape |
| `callback_circuit._pueue_pause` / `_pueue_resume` | `scripts/vps/callback_circuit.py:76-124` | Best-effort `pueue pause/start --group claude-runner`, already wired to `event_writer.notify_circuit_event` | Reusable primitive for "dispatch pauses" — but see Risks: circuit breaker pauses the **runner group** (blocks execution), not dispatch decision-making, and is time-window-based (`count_demotes_since`), not absolute-timestamp-based |
| `.orchestrator-heartbeat` file pattern | `scripts/vps/orchestrator.py:350-354`, `.orchestrator.pid` (`:90-93`) | Existing convention: small plain-text/timestamp state files living next to `SCRIPT_DIR`, read by external monitors | Pattern to follow for a `paused_until` state file if a file (not DB table) is chosen |
| `callback_logs._find_log_file` mtime-sort | `scripts/vps/callback_logs.py:44` | `sorted(log_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)` — picks the **freshest by mtime**, not by name | Direct fix template for the (a) QA-artifact bug below — `write_event_for_skill`'s `qa_files`/`reflect_files` glob currently sorts by **name** |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| `runner_loop.handle_sdk_exception` dispatch | `scripts/vps/runner_loop.py:203-282` | Maps SDK exceptions → exit_code (2 connection, 3 process, 124 timeout, 1 generic), honoring ADR-024 (post-ResultMessage exceptions never fail a done run) | Any new rate-limit-triggered exception path must slot into this same dispatcher, and must NOT override exit_code=0 if `result_received and not result_is_error` (ADR-024) |
| `_EXIT_REASONS` map | `scripts/vps/runner_result.py:27-33` | `{124: timeout, 2: cli_connection_error, 3: cli_process_error, 4: classifier_refusal, 143: sigterm}` — feeds `_salvage_if_needed`'s reason string | Exit code 5 is unused anywhere in `scripts/vps/*.py` runner/callback space (checked; the only `rc == 5` is `spec_operator.py`'s unrelated `force-done` CLI, a different process's exit-code namespace) — free for a `rate_limited` reason if the design needs a dedicated code |
| `refusal["detected"]` / run-log block | `runner_result.build_log_data:225-314`, key `"refusal"` | Always-present dict in the run-log JSON, `{"detected": False}` when nothing happened, so an absent key can't be confused with "no runner support yet" | Same contract shape recommended for a `"rate_limit"` block |

**Recommendation:** Detect via `RateLimitEvent`/`api_error_status` (SDK-native, structured) as primary; do NOT design around parsing `~/.claude/projects/<slug>/<session>.jsonl` — that file is not read by the runner today (no `session_id`/transcript-path plumbing exists anywhere in `scripts/vps/`, verified by grep) and the SDK already exposes the same information structurally. Model the new detector module after `runner_refusal.py` (duck-typed, stdlib-only, its own tests) rather than folding it into `runner_result.py`, which has only 10 lines of LOC headroom left (see Risks).

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

**Source:** grep

```bash
grep -rn "write_event_for_skill\|event_writer\.notify\b" scripts/vps/*.py tests/ scripts/vps/tests/
```

Results: `write_event_for_skill` is defined and called only inside `callback.py` (no external caller — it's the Step 5 function). `event_writer.notify` has 3 call sites: `callback.py:208` (via `write_event_for_skill`), `callback_sync.py:284` (Rule 7 structural-save notify), `audit_digest.py:184` (unrelated digest skill). `event_writer.notify_circuit_event` is called only from `callback_circuit.py:151,176`.

| File | Line | Usage |
|------|------|-------|
| `scripts/vps/callback.py` | 190-214 | defines `write_event_for_skill`, calls `event_writer.notify` |
| `scripts/vps/callback.py` | 314 | calls `write_event_for_skill(project_path, skill, status, task_label)` — **Step 5**, before Step 7 |
| `scripts/vps/callback_sync.py` | 284-292 | separate `event_writer.notify` call for `rule_7_saved` (unaffected by this spec) |
| `scripts/vps/audit_digest.py` | 184 | unrelated skill, own `notify` call |

**No test file calls `write_event_for_skill` at all** — grepped `tests/` and `scripts/vps/tests/`, zero hits. This is a real test gap, not just an impact-tree leaf.

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `db.get_task_by_pueue_id`, `release_slot`, `finish_task`, `update_project_phase`, `get_project_state` | `scripts/vps/db.py` | called in `callback.main` steps 1-3, 5 |
| `callback_logs.extract_agent_output` | `scripts/vps/callback_logs.py` | Step 4, produces `skill/preview/task_status` consumed by both Step 5 and Step 7 |
| `callback_sync.verify_status_sync` | `scripts/vps/callback_sync.py:304-380` | Step 7 — **returns `None`**, writes lifecycle status as a side effect only; the final verdict (`done`/`blocked`) is not currently returned to the caller |
| `lifecycle.write_lifecycle` | `scripts/vps/lifecycle.py:97-138` | called from inside `callback_sync._write_status` (`callback_sync.py:255-298`) |
| `gate_ancestry.find_implementation` | `scripts/vps/gate_ancestry.py` | THE gate inside `_decide_status` (`callback_sync.py:181-249`) |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "write_event_for_skill\|event_writer\|notify_circuit_event" . --include="*.py" --include="*.md"
```

Results: ~60 hits across code, docs, specs, glossary. Key non-code hits:

| File | Line | Context |
|------|------|---------|
| `docs/orchestrator/status-model.md` | 170 | 7-step table: `5 \| event_writer.notify → Hermes` — placed **before** step 7 `verify_status_sync`, documenting the exact ordering bug as current behavior (stale doc, matches the code, needs correction together with the fix) |
| `docs/orchestrator/README.md` | 112-127 | Same 7-step pipeline diagram, same ordering, plus stale line numbers (`:1387-1535`) from the pre-TECH-216 monolithic `callback.py` (1438 LOC) — the whole block predates the module split and should be refreshed in the same change |
| `.claude/rules/dependencies.md` | "scripts/vps/callback.py" section | Documents `write_event_for_skill` as a kept function; accurate today, needs a note if Step 5 moves |

```bash
grep -rn "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS\|run_in_background\|Monitor" .claude/skills/autopilot .claude/skills/qa
```

| File | Line | Context |
|------|------|---------|
| `.claude/skills/autopilot/SKILL.md` | 182-186 | Prose-only rule "Проверки — только синхронно", cites the $58.80/night and ~$115/day incidents, points to `safety-rules.md` |
| `.claude/skills/autopilot/safety-rules.md` | 41-55 | Full "Ход не заканчивается ожиданием" section with the incident table (TECH-1450, BUG-1448 ×2) |
| `.claude/skills/qa/SKILL.md` | 67-120 | Step 0c "Check CI status (informational)" — CI failure is WARN-only, never blocks; **no existing text about ending the turn on a background Bash/Monitor task** — this is the gap (c) targets for QA |
| `template/.claude/skills/autopilot/SKILL.md`, `safety-rules.md` | mirror of root | identical prose (both trees carry the same warning already) |
| `template/.claude/skills/qa/SKILL.md` | mirror of root minus the root-only "Spec Verification Protocol" section | same CI-informational Step 0c |

### Step 4: CHECKLIST — Mandatory folders

- [x] `tests/` — `tests/integration/test_callback_blocked_no_dispatch.py`, `test_callback_circuit_breaker.py`, `test_worktree_hook_blocks.py`, `test_autopilot_no_status_write.py` reference `event_writer`/circuit, but none cover `write_event_for_skill` ordering
- [x] `scripts/vps/tests/` — `test_event_writer_wake.py` (107 LOC, tests `notify`'s hermes-wake plumbing only, not the callback ordering), `test_orchestrator.py` (1785 LOC, has `event_writer.notify` monkeypatches for the heartbeat-stale alert, unrelated), `test_lifecycle_done_terminal.py` (Rule 7)
- [x] `db/migrations/**` — N/A, this repo has no `db/migrations/`; schema changes go through `scripts/vps/schema.sql` + `db._MIGRATIONS` (idempotent DDL list, `db.py:35-78`)
- [x] `ai/glossary/**` — N/A in root DLD (glossary is a downstream/`/bootstrap` artifact per CLAUDE.md); `scripts/vps/lifecycle.py` docstring points to `ai/glossary/orchestrator.md`, which does not exist in this repo

### Step 5: DUAL SYSTEM check

Applies partially to (a): once the fix moves (or gates) the Hermes-wake event on the Step 7 verdict, there are briefly two "truths" during rollout — the OLD event shape (status from pueue exit, written at Step 5) and the NEW event shape (status from lifecycle verdict, written after Step 7). No other component reads `ai/openclaw/pending-events/*.json` except Hermes itself (`event_writer.wake_hermes` — the prompt tells Hermes to read only the one named file), so there is no second reader to keep in sync — this is a single-writer, single-reader pipeline. N/A beyond that — not a data-source migration.

For (b), `DISPATCH_MODE` is a genuine dual system already in production: `builtin` (`orchestrator.scan_queued`, code-gated) vs `llm` (`dispatch_summary.py` + `dispatch_one.py`, model-gated) — **default is `llm`** (`orchestrator.py:282`). Any "paused until resets_at" check must be respected by **both** paths or the currently-inactive-by-default `builtin` path silently diverges the next time someone flips the env var back.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `scripts/vps/callback.py` | 371 (limit 400, 29 lines room) | Step order, `write_event_for_skill` qa/reflect glob sort | modify |
| `scripts/vps/callback_sync.py` | 379 (limit 400, **21 lines room**) | `verify_status_sync` currently returns `None` — needed if the fix passes the verdict back to the caller instead of re-reading lifecycle | modify (tight budget) |
| `scripts/vps/event_writer.py` | 198 (limit 400) | Possibly the artifact-glob fix moves here instead of callback.py — no LOC pressure | modify (optional) |
| `scripts/vps/runner_result.py` | 390 (limit 400, **10 lines room**) | `apply_result_message` — `api_error_status` currently unread | modify (very tight — see Risks) |
| `scripts/vps/runner_loop.py` | 281 (limit 400, 119 lines room) | `consume()` — add `RateLimitEvent` isinstance check, mirroring the refusal check | modify |
| `scripts/vps/runner_refusal.py` | 113 (limit 400) | Reference pattern only — not modified, cloned | read-only (pattern) |
| new `scripts/vps/runner_ratelimit.py` (suggested name, not yet created) | 0 | Duck-typed detector module, same shape as `runner_refusal.py` | create (recommended over cramming into `runner_result.py`) |
| `scripts/vps/claude-runner.py` | 368 (limit 400, 32 lines room) | Wires a new sibling module the same way `runner_refusal` is wired (re-export block, `_salvage_if_needed`-style reason mapping) | modify |
| `scripts/vps/db.py` | 376 (limit 400, 24 lines room) | New delegate(s) if DB-table persistence chosen for the pause state | modify (optional path) |
| `scripts/vps/db_decisions.py` | 169 (limit 400) | New table writer, mirrors `log_classifier_refusal` | modify (optional path) |
| `scripts/vps/schema.sql` | 140 | New table DDL mirror of `classifier_refusals` | modify (optional path) |
| `scripts/vps/lifecycle.py` | 399 (limit 400, **1 line room** — essentially at ceiling) | No change expected — `write_lifecycle`/`reconcile_orphans` already support the "queued" requeue shape used as precedent | read-only (pattern), **do not add code here** |
| `scripts/vps/orchestrator.py` | 411 (baselined at 412 in `loc-limit-baseline.txt` — 1 line of headroom before the gate fails) | `scan_queued`/`_select_dispatchable_spec` — builtin-path pause check | modify (essentially zero LOC budget — will likely force a split or a sibling-module addition) |
| `scripts/vps/dispatch_summary.py` | 262 (limit 400) | Add a pause-state field to the LLM dispatcher's briefing (`build()`/`render()`) | modify |
| `scripts/vps/dispatch_one.py` | 118 (limit 400) | Hard-refuse dispatch if `now < paused_until` — mirrors the three existing "physics" refusals | modify |
| `scripts/vps/requirements.txt` | 3 | `claude-agent-sdk>=0.1.63,<0.2.0` — unverified whether 0.1.63 (the floor) carries `RateLimitEvent`; only 0.1.81 was inspectable locally | verify / possibly bump floor |
| `scripts/vps/runner_cli.py` | 131 (limit 400) | `ALLOWED_TOOLS` list + possible `disallowed_tools`/env wiring for (c) | modify |
| `.claude/skills/autopilot/SKILL.md` | 420 (limit — prompts have no LOC gate, but 400/600 convention still tracked in practice) | Already has the prose rule (182-186); needs the **mechanical** enforcement pointer (disallowed_tools/env) added | modify |
| `.claude/skills/autopilot/safety-rules.md` | 128 | Same section — add mechanical-enforcement note | modify |
| `template/.claude/skills/autopilot/SKILL.md` | 410 | Mirror of root — **must change together** (`.claude/rules/template-sync.md`) | modify |
| `template/.claude/skills/autopilot/safety-rules.md` | 128 | Mirror of root | modify |
| `.claude/skills/qa/SKILL.md` | 689 | Add prompt rule: never end turn on background Bash/Monitor, report tail goes into the file before finishing | modify |
| `template/.claude/skills/qa/SKILL.md` | 661 | Mirror of root | modify |
| `scripts/vps/runner_loop.py` build_options | (counted above) | `env=` dict already has a documented-precedent slot (`SKIP`, `BASH_DEFAULT_TIMEOUT_MS` overridable via `os.environ.get(...)`) — `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` fits the same pattern | modify |
| `docs/orchestrator/status-model.md` | — | 7-step table documents the current (buggy) Step 5-before-Step 7 order; stale line numbers throughout | modify |
| `docs/orchestrator/README.md` | — | Same pipeline diagram, same staleness | modify |
| `ai/experiments/` | — | CLAUDE.md rule: any change to "how the fleet runs" needs an experiment file in the same commit with baseline + threshold + check date | create (mandatory per CLAUDE.md) |

**Total:** ~24 files touched or created (13 production `.py`, 4 prompt files across 2 trees, 2 docs, 1 experiment file, plus test files below), **7471 LOC read across the directly-relevant production modules already** (see LOC table above for per-file counts).

### Test files needing updates

| File | LOC | What needs to change |
|------|-----|----------------------|
| `scripts/vps/tests/test_event_writer_wake.py` | 107 (limit 600) | New assertions for Step 5/7 ordering if the fix lands in `callback.py`/`event_writer.py` |
| `scripts/vps/tests/test_runner_models.py` | — (has the `loop_module` fixture + `TestBuildOptions`) | `_options()` helper and fake-SDK fixture (`fake_sdk` at line ~148) need a `RateLimitEvent` type added, same way `AssistantMessage`/`ResultMessage` are stubbed (lines 155-163) |
| `scripts/vps/tests/test_claude_runner_refusal.py` | 542 (limit 600, close) | Closest existing golden-path test for "detect X in message stream, set exit code Y, log telemetry Z" — model a new `test_claude_runner_ratelimit.py` on this file rather than growing it further |
| `tests/integration/test_callback_blocked_no_dispatch.py` | — | Covers callback_dispatch's merge-confirmed gate; may need a case for "rate-limited run never reaches Step 6/7 with a false blocked verdict" |
| `scripts/vps/tests/test_orchestrator.py` | 1785 (baselined) | If `scan_queued`/`_select_dispatchable_spec` gets a pause check, tests patch `orchestrator.<bare name>` — new test must follow that convention, not `orchestrator_queue.<name>` |
| new dispatch_one/dispatch_summary tests | — | No existing test file for either module found (`Glob scripts/vps/tests/test_dispatch*` — checked, none exist) — **this is a real gap**: the LLM-dispatch path (which is the *default*) has zero test coverage in `scripts/vps/tests/` |

```bash
# confirms no dispatch_* test file exists today:
ls scripts/vps/tests/ | grep -i dispatch
# (no output)
```

---

## Verified References

| Reference | Kind | Verify command | Result |
|-----------|------|----------------|--------|
| `callback.py` main() Step 5 at lines 307-316, Step 7 at 332-362 | line numbers | `sed -n '217,367p' scripts/vps/callback.py` (read directly) | confirmed — `write_event_for_skill` call is at line 314, `verify_status_sync` call is at line 354, inside the `if skill == "autopilot" and status in ("done", "failed")` block starting line 333 ✓ |
| `write_event_for_skill` | function name | `grep -n "def write_event_for_skill" scripts/vps/callback.py` | `callback.py:190` ✓ |
| `verify_status_sync` returns `None` | function contract | `grep -n "def verify_status_sync" -A5 scripts/vps/callback_sync.py` | `callback_sync.py:304`, no `return` statement with a value found in the body (`callback_sync.py:304-380`) ✓ |
| `event_writer.notify` signature | function signature | `grep -n "^def notify" -A7 scripts/vps/event_writer.py` | `event_writer.py:126-135`, 5 positional args `(project_path, skill, status, message, artifact_rel="")` ✓ |
| QA artifact glob sorts by name not mtime | code | `grep -n "qa_files = sorted" scripts/vps/callback.py` | `callback.py:200` `sorted(p.glob("ai/qa/[0-9]*-*.md"))` — no `key=` argument ✓ |
| QA report filenames are `{YYYY-MM-DD}-{slug}.md`, no seconds | naming convention | `ls ai/qa/ \| tail -20` and `grep -n "ai/qa/{YYYY-MM-DD}" .claude/skills/qa/SKILL.md` | `ai/qa/2026-07-28-TECH-211.md`, `2026-07-28-TECH-212.md`, `2026-07-28-TECH-215.md` — same-day reports sort by slug, not recency; `SKILL.md:543` confirms `ai/qa/{YYYY-MM-DD}-{area-slug}.md` is the mandated format ✓ |
| `callback_logs._find_log_file` sorts by mtime (fix precedent) | function | `grep -n "sorted(log_dir.glob" -n scripts/vps/callback_logs.py` | `callback_logs.py:44`: `sorted(log_dir.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)` ✓ |
| `DISPATCH_MODE` default is `llm` | env var default | `grep -n "DISPATCH_MODE = os.environ.get" scripts/vps/orchestrator.py` | `orchestrator.py:282`: `os.environ.get("DISPATCH_MODE", "llm")` ✓ |
| `scan_queued` only runs under `builtin` | code | `grep -n "if DISPATCH_MODE" -A3 scripts/vps/orchestrator.py` | `orchestrator.py:290-291` ✓ |
| No pause/circuit check inside `dispatch_one.py` or `dispatch_summary.py` | absence check | `grep -n "circuit\|pause\|paused" scripts/vps/dispatch_one.py scripts/vps/dispatch_summary.py` | no matches ✓ (confirms the gap) |
| `_pueue_pause`/`_pueue_resume` exist in `callback_circuit.py` | function | `grep -n "^def _pueue_pause\|^def _pueue_resume" scripts/vps/callback_circuit.py` | `callback_circuit.py:76`, `callback_circuit.py:103` ✓ |
| `lifecycle.reconcile_orphans` demotes to `"queued"` with `by="orchestrator"` | precedent | `grep -n "reconcile_orphans" -A12 scripts/vps/lifecycle.py \| grep write_lifecycle` | `lifecycle.py:346-348`: `write_lifecycle(repo_dir, spec_id, "queued", reason="orphaned from crash", by="orchestrator")` ✓ |
| `_ALLOWED_WRITERS` includes `"callback"` | constant | `grep -n "_ALLOWED_WRITERS = frozenset" scripts/vps/lifecycle_const.py` | `lifecycle_const.py:30`: `frozenset({"callback", "orchestrator", "operator", "qa", "audit", "migration"})` ✓ |
| `ResultMessage.api_error_status` field exists, unread by runner | SDK field + code gap | `grep -n "api_error_status" $(python3 -c "import claude_agent_sdk,os;print(os.path.dirname(claude_agent_sdk.__file__))")/types.py scripts/vps/*.py` | SDK: `types.py:1165` (field def) + `message_parser.py:271` (populated). `scripts/vps/*.py`: **zero matches** — confirmed unread ✓ |
| `claude_agent_sdk.RateLimitEvent`/`RateLimitInfo` exported | SDK export | `grep -n "RateLimit" $(python3 -c "import claude_agent_sdk,os;print(os.path.dirname(claude_agent_sdk.__file__))")/__init__.py` | `__init__.py:99-101` (import) and `:550-553` (`__all__`) ✓ |
| SDK message type string `"rate_limit_event"` → `RateLimitEvent` | parser routing | `grep -n '"rate_limit_event"' -A20 $(python3 -c "import claude_agent_sdk,os;print(os.path.dirname(claude_agent_sdk.__file__))")/_internal/message_parser.py` | `message_parser.py:292-312` ✓ |
| Installed SDK version is 0.1.81; `requirements.txt` floor is 0.1.63 | version | `pip show claude-agent-sdk` + `cat scripts/vps/requirements.txt` | `Version: 0.1.81` (local); `requirements.txt:2`: `claude-agent-sdk>=0.1.63,<0.2.0` — **whether 0.1.63 carries `RateLimitEvent` is NOT verified** (no changelog available locally; not verifiable without web access) — flagged as an open risk, not assumed |
| `ProcessError` raised on nonzero CLI exit with generic stderr | SDK internals | `grep -n "Command failed with exit code" $(python3 -c "import claude_agent_sdk,os;print(os.path.dirname(claude_agent_sdk.__file__))")/_internal/transport/subprocess_cli.py` | `subprocess_cli.py:703`: `ProcessError(f"Command failed with exit code {returncode}", exit_code=returncode, stderr="Check stderr output for details")` ✓ — matches founder's "generic 'Command failed with exit code 1', empty stderr" report |
| `ALLOWED_TOOLS` list has no `Monitor`/`BashOutput`/`KillShell` entries | tool list | `grep -n "ALLOWED_TOOLS = \[" -A15 scripts/vps/runner_cli.py` | `runner_cli.py:119-131`: `["Skill","Agent","Read","Write","Edit","Bash","Glob","Grep","WebFetch","WebSearch","NotebookEdit"]` ✓ |
| `permission_mode="bypassPermissions"` set unconditionally | runner config | `grep -n "permission_mode" scripts/vps/runner_loop.py` | `runner_loop.py:112`: `permission_mode="bypassPermissions"` — confirms `allowed_tools` has no gating effect today; only `disallowed_tools` (unset, `runner_loop.py` has no such kwarg passed) can mechanically block a tool ✓ |
| `disallowed_tools` field exists on `ClaudeAgentOptions`, described as enforced even when otherwise allowed | SDK docstring | `python3 -c "import inspect; from claude_agent_sdk import ClaudeAgentOptions; print(inspect.getsource(ClaudeAgentOptions))"` \| grep -A6 disallowed_tools | confirmed field + docstring: "removed from the model's context and cannot be used, even if they would otherwise be allowed" ✓ |
| `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` referenced only in the founder's report, not in this repo | env var | `grep -rn "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS" .` | no matches in repo — the env var is a CLI-native lever (external to this codebase), not currently set anywhere in `scripts/vps/runner_loop.py`'s `build_options` env dict ✓ (confirms it needs to be *added*, not fixed) |
| `.claude/skills/autopilot/SKILL.md:182-186` and `safety-rules.md:41-55` already forbid background waiting (prose only) | prompt text | `sed -n '178,190p' .claude/skills/autopilot/SKILL.md`; `sed -n '38,56p' .claude/skills/autopilot/safety-rules.md` | confirmed, prose-only, cites $58.80 (awardybot 21.08) / ~$115 (dowry 24.08) incidents and FTR-1515 in `.claude/skills/qa/SKILL.md`... (FTR-1515 reference is in this spec's own description, matches diary) ✓ |
| `ai/diary/corrections.md` already records this exact spec's Phase-1 discussion | diary | `sed -n '48,56p' ai/diary/corrections.md` | `corrections.md:48-55` — dated 2026-09-23, "During TECH-223", records the founder's correction that headless runs (day or night) never wait for CI, and that autopilot vs QA need different treatments — matches the task's Socratic insight verbatim ✓ |
| `ai/lessons/` exists but is empty | lessons bank | `find ai/lessons -type f` | only `.gitkeep`, no `index.jsonl`, no domain subfolders ✓ |
| `scripts/build-lessons-index.py` exists | seed script | `find . -iname build-lessons-index.py` | `./scripts/build-lessons-index.py`, `./template/scripts/build-lessons-index.py` ✓ |
| `loc-limit-baseline.txt` baselines `orchestrator.py` at 412 | LOC debt register | `cat scripts/vps/loc-limit-baseline.txt` | `scripts/vps/orchestrator.py 412` (current `wc -l` = 411, 1 line of headroom before the baseline itself needs raising) ✓ |
| No test file references `write_event_for_skill` | test coverage gap | `grep -rn "write_event_for_skill" tests/ scripts/vps/tests/` | no matches ✓ |
| No `dispatch_one`/`dispatch_summary` test file exists | test coverage gap | `ls scripts/vps/tests/ \| grep -i dispatch` | no output ✓ |
| Exit code 5 unused in runner/callback exit-code space | exit code namespace | `grep -rn "exit_code.*5\b\|== 5" scripts/vps/*.py` (excluding tests) | only hit is `scripts/vps/spec_operator.py` (`force-done` CLI's own `sys.exit(5)`, unrelated process/namespace) ✓ |

---

## Reuse Opportunities

### Import (use as-is)
- `claude_agent_sdk.RateLimitEvent`, `RateLimitInfo`, `RateLimitStatus`, `RateLimitType` — already exported, already parsed by the SDK from the CLI's `rate_limit_event` message type.
- `ResultMessage.api_error_status` — already a dataclass field on the message the runner already consumes.

### Extend (subclass or wrap)
- `runner_loop.consume()` — add a `RateLimitEvent` isinstance branch next to the existing `AssistantMessage`/`TaskNotificationMessage`/`ResultMessage` branches (`runner_loop.py:191-196`).
- `runner_loop.handle_sdk_exception()` — the `ProcessError` branch (`:227-242`) is where a rate-limit-triggered process exit currently lands generically; needs its own recognizable path if the SDK doesn't surface a `RateLimitEvent` before the process dies.
- `dispatch_one.dispatch()` — extend the existing three "physics" refusals (no slot / already live / no spec body, `dispatch_one.py:56-71`) with a fourth: paused-until-timestamp check, same `_fail(reason)` shape.
- `dispatch_summary.build()` — extend the returned dict with a `dispatch_paused_until` (or similar) field so the LLM dispatcher sees it in its briefing.

### Pattern (copy structure, not code)
- `runner_refusal.py` — structure to clone for a new rate-limit detector module (own file, stdlib-only, duck-typed, own `_summary` function, own tests).
- `db_decisions.py` + `db.py:335-358` delegate pattern — structure to clone if a DB table is chosen for pause-state persistence.
- `lifecycle.reconcile_orphans` — structure/call-shape to clone for the "back to queued" write.
- `callback_logs._find_log_file`'s mtime-sort — pattern to clone for the QA/reflect artifact-glob fix.
- `.orchestrator-heartbeat` / `.orchestrator.pid` file-state pattern — structure to clone if a file (not DB) is chosen for pause-state persistence.

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- scripts/vps/callback.py scripts/vps/callback_sync.py scripts/vps/event_writer.py
```

| Date (from log) | Commit | Summary |
|------|--------|---------|
| — | `4e1f493` | fix(alerts): Hermes снова будится — `hermes -z` вместо убранного `-q`, один файл события (touches `event_writer.py` directly — same file this spec's fix (a) touches) |
| — | (TECH-216 series) | split of monolithic `callback.py` (1438 LOC) into `callback_logs/dispatch/scope/circuit/sync.py` — explains why `docs/orchestrator/*.md` line numbers are stale |
| — | (TECH-222) | dead `_render_and_commit_backlog` + `import lifecycle` removed from `callback.py` — confirms `callback.py` no longer imports `lifecycle` directly (only via `callback_sync`) |

```bash
git log --oneline -10 -- scripts/vps/claude-runner.py scripts/vps/runner_loop.py scripts/vps/runner_result.py
```

| Date | Commit | Summary |
|------|--------|---------|
| — | `c3e70c8` | feat(runner): флот автопилота на Opus 5.5 — `claude-opus-5-5`, CLI не ниже 2.1.280 (EXP-011) — most recent runner change, touches `_MIN_CLI_VERSION` in `runner_cli.py` |
| — | ADR-031 (2026-08-23) | `TIMEOUT_SECONDS` 5400→10800, `MAX_TURNS` 120→300 — the harness constants this spec's (c) fix interacts with (a paused-for-rate-limit run should not also burn a 3-hour timeout slot) |

**Observation:** `event_writer.py` was touched *today* (2026-09-23, same session context, commit `4e1f493`) for an unrelated but adjacent bug (the `-q`→`-z` flag silently breaking Hermes wake for a month). That fix and this spec's (a) fix both land in the same small, high-traffic file — sequence the two changes to avoid a merge/rebase collision if they're worked in parallel.

---

## Historical Risks (from ai/lessons/)

_No lessons bank in this project yet — `ai/lessons/` contains only `.gitkeep`, no `index.jsonl`, no domain files. Run `python3 scripts/build-lessons-index.py` to seed from the archive._

The closest available substitute is in-repo prose, not a lessons-bank entry, and is cited above under Verified References: `ai/diary/corrections.md:48-55` (2026-09-23, this exact spec's Phase-1 discussion) and the incident table in `.claude/skills/autopilot/safety-rules.md:41-55` (TECH-1450/BUG-1448, $58.80 + ~$115 losses from exactly the background-task-ends-the-turn failure mode this spec's (c) targets).

---

## Risks

1. **Risk:** `runner_result.py` has only 10 lines of LOC headroom (390/400) and `callback_sync.py` only 21 (379/400) — both are exactly the files a naive implementation of (a) and (b) would grow first.
   **Impact:** CI's `check-loc-limit.sh` gate (blocking, ARCH-209) fails the build the moment either crosses 400, forcing an unplanned split mid-implementation.
   **Mitigation:** Design (b)'s detector as a new sibling module (`runner_ratelimit.py`, mirroring `runner_refusal.py`) rather than adding fields/functions to `runner_result.py`. For (a), prefer re-reading `lifecycle.read_lifecycle()` after Step 7 over changing `verify_status_sync`'s return contract, to keep `callback_sync.py` at or near its current size.

2. **Risk:** `orchestrator.py` is baselined at 412 LOC with the current file at 411 — one line of net growth fails the gate outright.
   **Impact:** Any builtin-path (`DISPATCH_MODE=builtin`) pause-check addition to `scan_queued`/`_select_dispatchable_spec` has effectively zero budget.
   **Mitigation:** Since `DISPATCH_MODE` defaults to `llm` and the builtin path is a documented rollback-only mechanism, consider implementing the pause check primarily in `dispatch_one.py`/`dispatch_summary.py` (both well under budget) and only adding a minimal one-line guard to `orchestrator.py`, accepting a baseline bump with the required changelog entry in `loc-limit-baseline.txt` if more room is needed.

3. **Risk:** Unverified minimum SDK version for `RateLimitEvent`. `requirements.txt` allows `>=0.1.63`, but only 0.1.81 was inspectable locally, and no changelog was available to confirm when `RateLimitEvent`/`api_error_status` were introduced.
   **Impact:** If the VPS or a fresh `pip install` resolves an older 0.1.6x that predates these fields, the detector silently never fires (no `RateLimitEvent` ever arrives, `api_error_status` stays `None`) — a repeat of exactly the "silent degradation" pattern named in this repo's own CLAUDE.md (`codebase-memory` called 0 times in 143 runs, etc.).
   **Mitigation:** Before relying on these fields, run `pip show claude-agent-sdk` on the actual VPS and/or bump the `requirements.txt` floor to the verified-present version; add a runtime guard (log a WARNING once if a whole run completes with no `RateLimitEvent` support detectable) rather than assuming.

4. **Risk:** `event_writer.notify` / `write_event_for_skill` has zero test coverage today (confirmed by grep — no test references it).
   **Impact:** A reordering fix for (a) has no regression net; a subtle mistake (e.g., double-firing the Hermes wake, or losing it entirely on the `rule_7_saved` NOOP path) would ship silently.
   **Mitigation:** Add a unit/integration test for `write_event_for_skill` and the Step 5/7 ordering as part of this spec, not as follow-up.

5. **Risk:** `dispatch_one.py` and `dispatch_summary.py` (the *default* dispatch path since `DISPATCH_MODE=llm`) have **no test file at all** in `scripts/vps/tests/`.
   **Impact:** A "paused until" check added there is unverifiable by CI; a regression in the pause logic (e.g., it never actually blocks dispatch, or blocks forever because `resets_at` is parsed wrong) would only be caught by an operator noticing on the VPS.
   **Mitigation:** This spec is a reasonable place to add the first test file for both modules, scoped narrowly to the new pause-check behavior rather than full coverage of everything else in those files.

6. **Risk:** `event_writer.py` was already modified today in an unrelated commit (`4e1f493`, `-q`→`-z` fix) — both that fix and this spec's (a) fix touch the same small file in the same session window.
   **Impact:** Sequencing collision / merge friction if worked as separate specs in parallel autopilot slots.
   **Mitigation:** Note the dependency explicitly in the spec header (`**AFTER** <that commit's spec ID if any>`) or simply implement (a) on top of current `develop` HEAD, which already includes `4e1f493`.

7. **Risk:** Both `.claude/` and `template/.claude/` copies of `autopilot/SKILL.md`, `autopilot/safety-rules.md`, and `qa/SKILL.md` must change together (`rules/template-sync.md`) — 6 prompt files total across 3 logical files × 2 trees.
   **Impact:** A fix applied only to root (as often happens under time pressure) silently leaves every downstream/template-derived project without the mechanical fix, reproducing the exact "undocumented divergence" pattern `template-sync.md` warns about.
   **Mitigation:** Edit `template/` first per the stated convention ("Universal improvement → template first, then sync to root"), since none of (a)/(b)/(c)'s prompt-level changes are DLD-specific.
