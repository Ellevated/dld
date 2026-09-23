# Devil's Advocate — TECH-223 (callback verdict-first wake, 429 handling, no-CI-wait headless)

Scope note: three sub-features (a/b/c) share one callback.py/claude-runner.py blast radius but
have almost no shared risk surface. Treated separately below, cross-references called out.

---

## Why Not

### (a) Argument 1 — reordering callback steps touches an "ALWAYS exit 0" contract that nothing tests for order

**Concern:** `callback.py`'s docstring invariant is "Always exit 0. Every step in try/except" —
each of the seven steps is independently wrapped and independently allowed to fail. Nothing in
the current design assumes steps run in a particular relative order except by construction: Step 5
(`write_event_for_skill` → Hermes wake) currently runs *before* Step 7 (`verify_status_sync`, the
lifecycle write). Moving the wake to fire after the verdict is exactly right per the bug report,
but it means Step 5's code now depends on a value only Step 7 produces — coupling two blocks that
were deliberately independent try/except islands.

**Evidence:** `callback.py:307-362` — Step 5 currently reads only `skill`/`status`/`task_label`
from Step 4's `extract_agent_output`. Step 7's `verify_status_sync` call computes `target` (done vs
blocked) *inline* in the `try` block at line 341-360 — that logic is not returned, not stored on a
module-level var, and `verify_status_sync` itself returns `None` (it writes, it does not report
back what it wrote). To pass "the verdict" to the wake, either (1) `verify_status_sync` grows a
return value it has never needed in five specs of history (ADR-023/025/TECH-194/197/207/220/221 all
call it for its side effect only), or (2) callback re-reads `lifecycle.read_lifecycle()` after the
write to discover what landed — a second read that can itself race a concurrent writer between the
write and the read.

**Impact:** Medium — not a correctness break (both orders still exit 0), but a real one: swallowing
the verdict silently reproduces exactly the TECH-526/BUG-523 bug in a new shape if the re-read
races or `verify_status_sync` NOOPs (Rule 7 already-done, circuit-open, not-in-project — all real,
frequent NOOPs at `callback_sync.py:87-118`). A wake fired after a NOOP still needs to say
something coherent, and "done/blocked + reason" has no NOOP case defined.

**Counter:** Make `verify_status_sync` return the `(status, reason)` it decided (a `_Audit` object
already carries both — it is emitted, not returned) rather than re-reading. Explicitly define the
NOOP wake message ("no status change: <reason>") so it isn't silently skipped or silently identical
to the old "autopilot done" behaviour for a NOOP case.

### Argument 2 — QA artifact "of this run" has no run identity to key on

**Concern:** `write_event_for_skill` (`callback.py:190-214`) picks the QA artifact via
`sorted(p.glob("ai/qa/[0-9]*-*.md"))[-1]` — newest by filename sort, which is a timestamp prefix.
That is already "this run's artifact" in the common case (QA just finished, its file is the
newest). The bug is real only in a race: two QA runs for different specs finish close together and
callback for run A fires after run B's file lands. There is no `pueue_id` or `spec_id` embedded in
the QA filename to disambiguate deterministically — `ai/qa/` filenames are QA's own choice, not
callback's.

**Evidence:** `ai/qa/` glob pattern has no spec_id component visible from callback's side; the only
run-identifying data callback holds is `pueue_id` (Step 4's `extract_agent_output(pueue_id,
project_id)` already resolves a log file *by pueue_id* via `callback_logs._find_log_file`, which
proves the mechanism exists for run logs but was never extended to `ai/qa/*.md`).

**Impact:** Low probability (two QA runs finishing within the same glob-sort window), Medium
impact when it happens (Hermes gets pointed at the wrong artifact silently — worse than the "stale
artifact" bug it replaces, because it *looks* fixed).

**Counter:** Don't glob by mtime — extract_agent_output already parsed the run's own log
(`preview`/`task_status`); if QA's own final JSON echoes the artifact path it wrote (the same
pattern autopilot already uses for `task_status`), callback can key on that instead of trusting
glob order. Cheaper: filter the glob to filenames containing the resolved `spec_id` before taking
the last one — spec_id is already resolved for QA dispatch a few lines up in `_step6_dispatch_qa_reflect`, it is simply not threaded through to `write_event_for_skill`.

### (b) Argument 3 — "queued instead of blocked" is a THIRD callback-owned status transition that bypasses circuit-breaker accounting

**Concern:** Every status callback writes today is either `done` or `blocked`
(`callback_sync.verify_status_sync`, called only with `target in ("done","blocked")` from
`callback.py:341-360`). The circuit breaker's mass-demote detector (`callback_circuit.note_demote`,
wired at `callback_sync.py:361-362`) only fires on the `blocked` branch. A rate-limit exit code
that makes callback write `status="queued"` directly is a **new write path** that (1) does not go
through `verify_status_sync` at all — bypassing Rule 3 (project boundary), the allowlist/gate
check, and the audit log in one motion — or (2) if it does go through a modified
`verify_status_sync`, needs a third branch that the circuit breaker, the audit `_Audit.emit`
shape, and every consumer of `callback_decisions.verdict` (`'demote'|'sync'|'noop'|'circuit_open'`
per `schema.sql:80`) has never seen. Either way: a requeue-storm from a real outage (not a rate
limit — a genuine bad build that fails every run) could now round-trip through "queued" without
ever incrementing the demote counter that exists specifically to catch a mass-failure pattern and
pause the fleet.

**Evidence:** `callback_circuit.py` `CIRCUIT_THRESHOLD`/`CIRCUIT_WINDOW_MIN` gate on `demoted=1` rows
in `callback_decisions` (`schema.sql:75-89`); `orchestrator.reconcile_orphans` already writes
`status="queued"` for a *different* reason (dead pueue task, `lifecycle.py:331-350`, `by="orchestrator"`)
on the orchestrator's own poll cycle — a second, unrelated "callback path to queued" would give the
fleet two producers of the same state transition with two different audit trails and no shared
counter.

**Impact:** High — this is exactly the failure class the circuit breaker was built to catch
(TECH-169), and a rate-limit-shaped exit code is not guaranteed to only ever mean rate limit: any
future SDK error text that superficially matches the "session limit" string pattern (a typo'd
error message, a differently-worded 429 from a proxy) would silently route into the un-audited
requeue path instead of the audited blocked path.

**Counter:** Route through `verify_status_sync` (or a sibling using the same `_Audit` machinery)
with a real third target, `"queued"`, that: emits its own `callback_decisions.verdict` value (not
reusing `'demote'` or `'sync'`), and is EXCLUDED from `note_demote`'s counter by name, not by
accident. Cap it with its own counter, independent from circuit breaker's demote count (see Edge
Case 6 below) — a rate limit hit 3x in a row for the same spec is a different signal ("this spec's
prompt is unusually expensive" or "the fleet-wide limit never actually cleared") than 3 unrelated
specs demoted in 10 minutes.

### (c) Argument 4 — "never wait for CI in headless" guts a gate that is the *one* part of this pipeline proven to still be read

**Concern:** `PHASE-3-FINAL-TEST` in `.claude/skills/autopilot/SKILL.md:79-96` is explicit that the
TECH-206 CI-parity gate used to live in `autopilot-git.md` and was **measured never executing** —
0 of 198 transcripts opened that file, `CI_PARITY_REUSED`/`CI_PARITY_UNAVAILABLE`/`TESTED_TREE`
appear nowhere. It was moved into the always-loaded `SKILL.md` specifically to fix that. `./test
ci` is required at two points: `finishing.md` Step 1 (post-implementation) and Step 8 (CI-parity
merge gate, "Red → git reset --hard origin/develop, abort merge, needs_review, do NOT push") —
and it is also item 1 of the "Code Quality" section of the Pre-Done Checklist ("ALL items must be
checked"). "No waiting on CI in headless at all" is not a background/foreground tooling tweak; it
removes the one gate the fleet just spent effort making the model actually execute, for the
mode (headless VPS) where 100% of autopilot runs happen. QA's own CI check
(`.claude/skills/qa/SKILL.md` Step 0c) is explicitly informational/non-blocking already — the
proposal's target is `./test ci`, the *local* full-suite run, not GitHub Actions.

**Evidence:** the founder's own framing ("local CI takes 60-150 min") matches `./test ci` exactly —
GitHub Actions status is a single `gh run list` call (`qa/SKILL.md:110`), not a 60-150 min wait.
`BASH_DEFAULT_TIMEOUT_MS`/`BASH_MAX_TIMEOUT_MS` in `runner_loop.py:127-134` were already raised to
15/30 min specifically because a 325-423s test suite kept hitting the CLI's stock 120s/600s Bash
cap — but 30 min max is still shorter than the stated 60-150 min full suite, so the *existing*
mitigation is already insufficient for the workload the founder describes, independent of this
feature.

**Impact:** High — removing (or silently downgrading) `./test ci` from headless runs means the
fleet's only local build-breakage catch before merge to `develop` goes away for every VPS-dispatched
spec, on a fleet whose `develop` the dispatcher already documents as "red most of the time"
(`dispatcher/SKILL.md:136`) — i.e. the signal is already weak, and this makes it structurally
absent rather than weak.

**Counter:** Scope the founder's decision precisely before implementing: "no waiting on CI" should
mean *GitHub Actions* (remote, post-push, already informational everywhere it's checked), not
`./test ci` (local, pre-push, blocking-by-design). If the actual intent IS to drop `./test ci`
foreground blocking too, that is a distinct, much larger decision that needs its own spec, its own
Allowed Files review of `finishing.md`+`SKILL.md`+`task-loop.md` in **both** `.claude/` and
`template/.claude/`, and a replacement signal for "did the merge break the build" (background
`./test ci` with a result posted to the NEXT dispatch pass, à la async CI, is plausible — but that
is new infrastructure, not "mechanically close background tools").

---

## Edge Cases

### EC-1 — rate limit hit AFTER the run already committed and pushed (salvage already ran)
**Scenario:** Autopilot completes tasks 1-3 of 5, is mid-task-4 when the 429 arrives on the next
API call. `_salvage_if_needed` (`claude-runner.py:150-171`) already runs on any non-zero exit and
pushes the worktree branch — this is not new behaviour, salvage runs regardless of *why* the exit
was non-zero. The new piece is only: does the requeue safely resume?
`orchestrator_queue.reconcile`/`reconcile_if_implemented` (via `gate_ancestry.branch_state`) already
distinguishes "nothing pushed" (`fresh`) from "branch ahead of develop" (`continue`) and sets
`CLAUDE_CONTINUE_BRANCH` — but that env var is **not read by `worktree-setup.md` or
`autopilot-git.md` in either tree** (`dependencies.md` explicitly flags this: "NOT currently read by
either prompt… both detect an existing pushed branch independently via `git ls-remote`"). So branch
continuation on requeue is already the existing, load-bearing, but *prompt-driven* mechanism — a
rate-limit requeue inherits whatever reliability that mechanism has today, gains nothing extra,
and (b)'s claim that requeue "re-runs safely" needs to cite that existing path, not assume a new one.
**Assertion:** DA-1 — spec X salvaged at task 4/5 with branch `feature/X` 3 commits ahead of
`origin/develop`; requeue dispatches a fresh worktree session for X; assert the new session's first
`git ls-remote --heads origin feature/X` finds the pushed branch and the new worktree checks it out
(not a fresh branch from develop) — i.e. tasks 1-3 are NOT redone.

### EC-2 — five_hour vs seven_day limit conflated into one "resets_at"
**Scenario:** `rateLimitType: "five_hour"` and a weekly `seven_day` cap are two different windows
with two different reset horizons (hours vs potentially days). A single `resets_at` field and a
single "pause dispatch until resets_at" behaves identically for both in code, but the founder's
"reactive only, no proactive throttling" decision was likely reasoned about the 5-hour case (a
half-day fleet stall is tolerable; a multi-day stall driven by a weekly cap silently eating the
whole week's compute budget is a different conversation the founder hasn't explicitly had here).
**Assertion:** DA-2 — 429 body carries `rateLimitType: "seven_day"`, `resetsAt` = epoch 6 days out;
assert the alert message names the limit type and the multi-day duration explicitly (not just "session
limit, resuming at HH:MM" — that phrasing reads as "later today" even when it's Thursday).

### EC-3 — resets_at missing or unparseable
**Scenario:** The CLI's own transcript format for this message is not a stable, versioned API
contract — a CLI point release could change the JSON shape, drop the field, or emit it in a
different unit (seconds vs ISO vs epoch-ms). `handle_sdk_exception`'s generic branch
(`runner_loop.py:274-281`) is exactly where an unparsed 429 lands today — `exit_code=1`,
`result_text=err_str`. Any new parser needs a defined fallback distinct from "pretend it's not a
rate limit" (which reproduces today's confusing exit-1) and "pause forever" (which is worse than
today).
**Assertion:** DA-3 — stderr contains the 429 phrase but no parseable `resetsAt`; assert exit_code
is still the new rate-limit code (so callback still requeues rather than blocks), AND the alert /
run-log field explicitly says `resets_at: unknown` rather than a fabricated timestamp, AND dispatch
pause falls back to a bounded default (e.g. re-check in 1h) rather than never resuming.

### EC-4 — several runs hit the limit simultaneously (thundering herd at reset, one alert)
**Scenario:** With 5 compute slots, a rate limit mid-afternoon can strand up to 5 concurrent runs.
"One alert" needs de-duplication logic that does not exist anywhere in `event_writer.py` today —
`notify()` fires unconditionally per call, `notify_circuit_event` is the only existing
"one event class, many possible triggers" precedent, and it doesn't dedupe either (each `open`/
`reset`/`heal` transition fires its own wake). Five callback processes running near-simultaneously
(pueue fires callbacks per finished task, not serialized) racing to be "the one that alerts" is
a real concurrency problem, not a hypothetical — `is_circuit_open()`/`_trip_circuit()` already
solved a structurally identical problem for the demote case using SQLite as the coordination point;
a rate-limit alert needs the same, or 5 separate Hermes wakes for the same event, each burning an
`hermes -z` invocation and Telegram message.
**Assertion:** DA-4 — 3 callback invocations for 3 different specs all classify their run's failure
as rate-limit within a 10-second window; assert exactly one Hermes wake fires and the other two are
recorded (audit log) as suppressed-duplicate, not silently dropped.

**Thundering herd at reset (second half of EC-4):** all N stranded specs are `queued` simultaneously
and `resets_at` is identical for all of them — the dispatcher's "start it" step
(`dispatcher/SKILL.md` §4, "at most two dispatches per pass") already caps this to 2/cycle, so a
literal simultaneous restart of 5 runs is *already* prevented by the existing dispatcher cadence —
this is one place the existing design accidentally already mitigates the new risk. Worth confirming
in implementation that the requeue path doesn't bypass the dispatcher (e.g. if the orchestrator's
own `scan_queued` — not the dispatcher — auto-dispatches queued specs directly, the 2/pass cap does
not apply there). **This needs a direct answer, not an assumption** — see Questions.

### EC-5 — the LLM dispatcher is itself a Claude run, and shares quota with the fleet it dispatches
**Scenario:** `.claude/skills/dispatcher/SKILL.md` frontmatter is `model: claude-sonnet-5`, invoked
by `~/ops/dispatcher.sh` every 15 minutes (referenced but not vendored in this repo — outside
`scripts/vps/`). This is confirmed to run on the same Max subscription as the autopilot fleet (it
is a Claude Code skill invocation, not the Hermes chat agent, which per project memory runs on
`gpt-5.6-terra` specifically to avoid this exact OAuth-Max collision). A fleet-wide 429 stops the
dispatcher from running its next pass at all — no briefing, no dispatch, no "we are paused" report
either, since the dispatcher's own report step (§5) never executes. The fleet doesn't just stall,
it goes **silent about the fact that it's stalled** unless the alert in (b) is independent of the
dispatcher (it is — `event_writer.notify` is called from `callback.py`, a separate process) — but
there is nothing today that would tell the dispatcher itself "don't bother running your pass, we're
inside a rate-limit window", so it will keep firing every 15 minutes, each attempt itself consuming
whatever quota exists (small, but non-zero, and each failed dispatcher pass is itself a 429 that
needs the same handling this feature is building for autopilot — cron-invoked `claude --print`
doesn't go through `claude-runner.py`/pueue/callback at all).
**Assertion:** DA-5 — fleet-wide 429 active (`resets_at` future); assert the dispatcher's own
invocation path (cron → `claude --print` or equivalent, NOT pueue) either (a) checks a shared
"rate-limited until" marker before spending a dispatcher pass, or (b) is explicitly out of scope
and the spec says so — today's proposal describes callback/runner (pueue-fired) handling only, and
the dispatcher's separate invocation mechanism is not touched by any of (a)/(b)/(c).

### EC-6 — Oleg's interactive sessions share the same quota
**Scenario:** `CLAUDE.md` (project rules) explicitly names "Interactive `/spark` workflow: Run
`/spark` interactive sessions from ONE machine at a time" as a *contention* convention already —
this means interactive usage against the same Max subscription is a known, existing shared-resource
problem, just not previously in terms of the numeric 429 budget. If the fleet's autopilot burns the
5-hour window at 13:31 (as the founder's example shows), an interactive session Oleg starts at
13:45 hits the same wall with no DLD-side handling at all (interactive Claude Code surfaces the
429 in its own UI, unrelated to this pipeline) — but the *fleet's* reactive-only, no-throttle
design means nothing backs off to leave headroom for interactive use, and nothing in this proposal
tells Oleg "the fleet already used the window" before he starts typing.
**Assertion:** SA-style, not DA — see Side Effects below; this is a coupling to surface, not a
testable pipeline behaviour, since interactive sessions are outside claude-runner/callback.

### EC-7 — a spec that hits the limit repeatedly (infinite requeue loop)
**Scenario:** Two distinct causes produce the same symptom — (1) genuinely bad luck (dispatched
right as a 5-hour window resets and immediately re-consumed by other work), and (2) a spec whose
prompt/task shape is unusually expensive and reliably exhausts remaining quota every time it's
tried. `lifecycle_git._build_yaml_content` (`lifecycle_git.py:94-179`) has no attempt counter field
today — `transitions` records `{from, to, at, by, pueue_id}` but **not `reason`** per-entry (only a
single top-level `blocked_reason` that the next write overwrites). Detecting "this spec requeued on
rate-limit 3 times running" from lifecycle YAML alone is not possible without a schema change; the
alternative — scanning `task_log` for repeated matching `exit_code` per `task_label` — works but is
a second source of truth for the same fact, with its own risk of drifting from lifecycle (the exact
failure class ADR-023 replaced).
**Assertion:** DA-6 — same spec_id requeued via rate-limit exit code 3 times within, say, 24h;
assert the 3rd requeue is NOT silently identical to the 1st — either it escalates to `blocked` with
a distinct reason ("repeated_rate_limit — likely expensive spec, not transient"), or it is visibly
flagged in the dispatcher briefing (`dispatch_summary.py` `_spec_problem`) so a human/dispatcher
notices before a 4th attempt.

### EC-8 — removing background tools breaks legitimate uses
**Scenario:** `finishing.md` 7.5 POST-DEPLOY VERIFY polls a URL every 10s for up to 120s — that's a
foreground poll loop, not background, and unaffected. But QA's own remit
(`qa/SKILL.md` "Interact with the product through its UI (Playwright), API (curl), CLI, or bot")
plausibly needs to start a dev server and interact with it while it's running — a legitimate
`run_in_background: true` use that a blanket "close background tools mechanically" would also
remove, alongside the illegitimate "background the test suite and end the turn" use the founder
is targeting. `ALLOWED_TOOLS` (`runner_cli.py:119-131`) is an **allowlist of tool names**
(`Bash`, `Read`, …) — there is no separate "Monitor" or "BashOutput" tool in that list to
selectively disallow; backgrounding is a parameter on the `Bash` tool call itself
(`run_in_background: true`), not a distinct tool. If the SDK/CLI has no `disallowed_tools`-level
knob for "Bash tool but never with run_in_background=true", the "mechanical" half of (c) may not
be achievable at all without either removing `Bash` entirely (breaks everything) or an
environment/CLI flag that does not appear in `ClaudeAgentOptions` as currently used in
`runner_loop.py:99-140` (no such field is set there today).
**Assertion:** DA-7 — a QA run legitimately backgrounds a `npm run dev` server to test against it,
then continues interacting foreground; assert this still works after whatever mechanical
enforcement ships, i.e. the enforcement is scoped to "test-suite-shaped long Bash calls", not to
`run_in_background` as a parameter — otherwise this is a prompt-rule dressed as a "mechanical" one
and inherits the 0/198 measured-ignored failure mode from Argument 4.

### EC-9 — prompt-only rules the autopilot already ignores
**Scenario:** Already measured, not hypothetical: `autopilot-git.md` opened in 0/198 transcripts;
QA ended 5/15 runs on "waiting for CI in background" despite `qa/SKILL.md` Step 0c being a single
non-looping `gh run list` call, not a wait loop — meaning the model is *inventing* background-wait
behaviour the prompt never asked for, not failing to follow an existing background-wait
instruction. A new prompt paragraph saying "never wait on CI in headless" competes with the same
attention budget that already lost 0/198 and 5/15. If the "mechanical" half of (c) (EC-8) turns out
not to be achievable, the whole of (c) degrades to exactly this failure class.
**Assertion:** DA-8 — after shipping the prompt-only half of (c) alone (no mechanical enforcement),
re-measure over the next N QA/autopilot runs whether "waiting for CI in background" recurs; if it
does at a similar rate, the prompt-only path is confirmed dead on arrival and mechanical enforcement
is not optional.

---

## Hidden Coupling

| Coupling | Detail |
|---|---|
| **Verdict must be returned, not re-derived** | `verify_status_sync` (`callback_sync.py:304-380`) returns `None`. (a) needs it to hand back `(status, reason)` — every existing caller (just `callback.py:354`) is unaffected by adding a return value, but any future re-read-after-write pattern races a concurrent writer. |
| **Rule 7 / CAS retries interact with wake timing** | `write_lifecycle` can raise `LifecycleAlreadyDoneError` (Rule 7 structural save) or exhaust `MAX_CAS_RETRIES` (`LifecycleWriteRaceError`, uncaught in `_write_status`'s except clause — only `LifecycleAlreadyDoneError` and generic `Exception` are handled, and `LifecycleWriteRaceError` **is** an `Exception` so it's caught, but the audit line says `error:write_failed:...` not a verdict). Any wake keyed to "the verdict" must define what it says when the write itself failed — today that's a NOOP for the wake question, not "done" or "blocked". |
| **Circuit breaker is currently the only "pause claude-runner" mechanism** | `callback_circuit._pueue_pause`/`_pueue_resume` (TECH-169) already pause/resume the `claude-runner` pueue group on mass-demote. (b)'s "dispatch pauses until resets_at" needs the SAME group-pause primitive or a second one — if it's the same `pueue pause --group claude-runner` call, a circuit-breaker `_trip_circuit` firing *during* a rate-limit pause window (plausible: rate limit → some in-flight runs finish with real bugs, not 429s → demotes accumulate) races two independent "why are we paused" reasons against one boolean pueue state, and whichever resumes first (heal timer vs resets_at) wins regardless of whether the other condition still holds. |
| **`orchestrator.reconcile_orphans` already writes `status="queued"`** | `lifecycle.py:331-350`, `by="orchestrator"`, reason `"orphaned from crash"`. (b) adds a second, `by="callback"` producer of the same target status for a different reason. Both run on different triggers (orchestrator poll cycle vs pueue callback) — a spec could theoretically be reconciled to queued by orchestrator AND independently written to queued by callback's rate-limit path for the same underlying dead run, producing two `transitions` entries and two audit trails for one event. |
| **`dispatch_summary._recent_verdicts`** | Reads `task_log.status`/`exit_code` directly (`dispatch_summary.py:162-169`) and is the dispatcher's "Last runs" section. A new rate-limit exit code changes what the dispatcher sees in its briefing without any dispatcher-prompt update — the dispatcher will report a rate-limited run under "Last runs" using its raw exit_code with no framing, unless `dispatch_summary.py` (or the SKILL.md prompt) is taught what that code means. |
| **`_EXIT_REASONS` feeds salvage's commit message** | `runner_result.py:27-33` maps exit_code → the human-readable reason baked into salvage's `wip({spec_id}): salvaged after {reason}` commit message (`claude-runner.py:167`, `salvage.py:209`). A new rate-limit exit code needs an entry here or every rate-limited salvage commit reads `wip(X): salvaged after exit N` instead of something legible — small, but it's the only audit trail a human reviewing `git log` on the feature branch gets. |
| **`classifier_refusals` table precedent** | The refusal-detection feature (ADR-029/model-capabilities.md) built a *dedicated* SQLite table rather than overloading `sdk_post_result_errors`, specifically because the two measure different things and share no columns. A rate-limit event (category, resets_at, five_hour vs seven_day) has the same shape mismatch against both existing tables — worth a `rate_limit_events` table rather than stuffing fields into `task_log.output_summary` as a formatted string, which is what `_EXIT_REASONS`-style handling would otherwise default to. |
| **Two `.claude` trees** | `runner_loop.py`/`runner_cli.py`/`callback*.py` live only in `scripts/vps/` (root-only — `template/` has no orchestrator per `template-sync.md`). (a) and (b) are pure root-only changes, zero downstream blast radius. (c), however, touches `finishing.md` + `SKILL.md` (PHASE-3-FINAL-TEST) + `task-loop.md`, which **do** exist in `template/.claude/skills/autopilot/` — any change to the CI-wait behaviour needs the same template-sync discipline as everything else in that tree (`scripts/check-tree-sync.py`), and a downstream project's `./test`/`./test ci` cost profile (unknown — could be 5 min, could be 3h) is not something this DLD-repo-specific proposal has evidence for. Shipping (c) to template on DLD's own 60-150 min measurement risks solving DLD's problem while quietly changing behaviour for all 10 downstream fleets. |

---

## Verdict

**Recommendation:** Proceed with changes.

**Reasoning:** (a) is a real bug fix (verdict silently mismatched from Hermes's message is a
correctness bug, not a design risk) and should ship, but needs `verify_status_sync` to return its
decision rather than have the wake re-derive or re-read it. (b) is well-motivated (a documented,
measured incident, 2 specs blocked + dispatcher passes lost) but as scoped it creates an
unaudited third lifecycle-write path that bypasses the exact circuit-breaker machinery built for
this class of failure — it needs its own counted, audited target state, not a bare `write_lifecycle(...,
"queued", ...)` call. (c) is the highest-risk of the three: "never wait for CI in headless" as
stated would remove the one quality gate just proven (by measurement) to finally be executing, and
the "mechanical" enforcement it promises may not be achievable at the tool-parameter level the SDK
exposes today — confirm that before promising it in the spec's Allowed Files.

**Conditions for success:**
1. (a) — `verify_status_sync`/`callback_sync` returns `(status, reason)`; wake fires from that
   return value, with an explicit NOOP message defined; QA artifact selection keys on resolved
   `spec_id`, not mtime-sort alone.
2. (b) — the rate-limit requeue gets its own `callback_decisions.verdict` value, excluded from (not
   silently invisible to) circuit-breaker demote counting; a per-spec repeated-rate-limit counter
   (new `transitions[].reason` field or a `rate_limit_events` table) exists before this ships, so
   EC-7's infinite-loop case has a floor; the dispatcher's own 15-minute invocation path (EC-5) is
   either handled or explicitly declared out of scope in the spec.
3. (c) — scope is written down precisely as "remote/GitHub Actions CI only" OR, if `./test ci`
   itself is in scope, that is split into its own spec with `finishing.md`/`SKILL.md` PHASE-3-
   FINAL-TEST changes reviewed against TECH-206's history and ported to `template/` under
   `template-sync.md` discipline. Confirm whether the SDK/CLI exposes any mechanism to disallow
   `run_in_background` on `Bash` specifically before writing "mechanical" enforcement into the spec
   — if it does not, say so and ship the prompt rule anyway, but track DA-8 as the experiment that
   tells you whether it worked, given the 0/198 and 5/15 precedent.
