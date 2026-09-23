# External Research — TECH-223 (orchestrator reliability: wake-order, rate limits, background tasks)

Environment confirmed by the feature description: `claude_agent_sdk` 0.1.81 driving Claude Code CLI
**2.1.280**, model `claude-opus-5-5`, Claude Max subscription OAuth. All version gates below are checked
against 2.1.280 unless noted; where a doc entry carries a `min-version` older than 2.1.280, the feature
is present on this fleet.

---

## Findings per question

### 1. Background-task / timeout controls in print/SDK mode

**Source:** [Environment variables](https://code.claude.com/docs/en/env-vars) — code.claude.com, CLI ≥2.1.182 for the ceiling var.

| Variable | Default | Semantics |
|---|---|---|
| `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` | `600000` (10 min) | In `-p`/SDK mode, max time Claude Code waits **after the final turn** for background *subagents and workflows* whose result is part of the output. `0` = wait indefinitely. Separate from the 5‑second grace period for plain background shells. |
| `BASH_DEFAULT_TIMEOUT_MS` | `120000` (2 min) | Default per-call Bash timeout. |
| `BASH_MAX_TIMEOUT_MS` | `600000` (10 min) | Ceiling the model can request for a single Bash call. Per the doc: *"the effective ceiling is the larger of this and `BASH_DEFAULT_TIMEOUT_MS`."* No absolute hard cap is stated on this official page (a third-party mirror, mintlify.com/VineeTagarwaL-code/claude-code, claims a 600,000 ms hard max — that page is not an Anthropic source and conflicts with a real-world config in [GitHub #26660](https://github.com/anthropics/claude-code/issues/26660) that sets `BASH_MAX_TIMEOUT_MS=7200000`, 2h). **Caution:** #26660 (filed 2026-02-18, no resolution found) reports `BASH_DEFAULT_TIMEOUT_MS`/`BASH_MAX_TIMEOUT_MS` being silently ignored or randomly alternating between 5/10 min regardless of configured value, on Windows and WSL — unconfirmed as fixed on 2.1.280. **Do not rely on raising these to cover a 60–150 min CI run**; matches the founder's own decision to not wait on CI at all.
| `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` | unset | Set to `1` to disable background-task functionality. Documented on [Run subagents in foreground or background](https://code.claude.com/docs/en/subagents) (also mirrored at `sub-agents.md`): *"If you set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` to `1`, Claude Code runs the subagent in the foreground, in every kind of session and whether or not fork mode is on."* It **takes precedence over fork mode**. Separately, [Tools reference](https://code.claude.com/docs/en/tools-reference) states for the Bash tool: *"setting `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` disables auto-backgrounding along with the rest of the background task functionality."* This is the closest thing to a documented kill-switch for the whole feature class (subagents, workflows, auto-backgrounded and explicit `run_in_background` Bash calls).

**This is exactly the "any `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` or equivalent" the founder asked about — it exists and is official.** Caveat from real-world reports, not the doc: [GitHub #73453](https://github.com/anthropics/claude-code/issues/73453) (filed against 2.1.198–2.1.220) found the var was *not* honored for `Workflow`-tool children or `CLAUDE_CODE_FORK_SUBAGENT` forks in some builds, only for plain `Agent`-tool subagent spawns — worth a smoke test on 2.1.280 before relying on it for anything beyond Bash/plain subagents.

**Fine-grained alternative — permission rules**, [Configure permissions](https://code.claude.com/docs/en/permissions):
- A scoped deny rule `Bash(run_in_background:true)` blocks only the backgrounding parameter, leaving Bash itself usable. Table confirms parameter-scoped deny syntax: `Tool(param:value)`.
- A bare-name deny `"Monitor"` (in `permissions.deny`, or `disallowedTools`/`disallowed_tools` on the SDK) removes the **Monitor tool** from Claude's context entirely — Claude never sees it, so it cannot end a turn on "I'll send the final report later" via Monitor. Confirmed on [Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions): `disallowed_tools=["Bash"]` removes the whole tool definition from the request; the same applies to any bare tool name including `Monitor`.

### 2. How rate limits surface to `claude_agent_sdk` (Python)

**Source:** [claude-agent-sdk-python `message_parser.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/message_parser.py) and [Agent SDK reference — Python](https://code.claude.com/docs/en/agent-sdk/python).

There is a typed **`RateLimitEvent`** message, added in [PR #648](https://github.com/anthropics/claude-agent-sdk-python/pull/648):
```python
Message = AssistantMessage | UserMessage | SystemMessage | ResultMessage | StreamEvent | RateLimitEvent

@dataclass
class RateLimitInfo:
    status: Literal["allowed", "allowed_warning", "rejected"]
    resets_at: int | None
    rate_limit_type: str | None   # "five_hour" | "seven_day" | ...
    utilization: float | None
    overage_status: str | None
    overage_resets_at: int | None
    overage_disabled_reason: str | None
    raw: dict
```
Emitted by the CLI (confirmed present since v2.1.45 per a test-file comment in the SDK repo) whenever rate-limit status changes for **subscription users**. This is the field set that matches the founder's observed JSONL exactly: `quotaLimits.status`, `resetsAt`, `rateLimitType`, `overageStatus`, `overageDisabledReason` all map 1:1 to `RateLimitInfo`.

**Version gotcha, important for this codebase:** before this type existed, `parse_message()` raised on an unknown `rate_limit_event` type and **killed the whole `receive_messages()` async generator** — [Issue #583](https://github.com/anthropics/claude-agent-sdk-python/issues/583). That means detection code that isinstance-checks for `RateLimitEvent` is a no-op (or worse, a crash) unless the installed `claude_agent_sdk` build actually contains PR #648. **Verify this directly against the pinned `claude_agent_sdk==0.1.81`** (`python -c "from claude_agent_sdk import RateLimitEvent"`) rather than assuming — this was not confirmed from search results.

**`ResultMessage` fields relevant to detecting the hard usage-limit case** ([Agent SDK reference — Python](https://code.claude.com/docs/en/agent-sdk/python)):
```python
@dataclass
class ResultMessage:
    subtype: str          # "success" | "error_during_execution" | "error_max_turns" | ...
    is_error: bool
    api_error_status: int | None   # HTTP status of the failing API call, None on success
    result: str | None
    errors: list[str] | None
    ...
```
`api_error_status` was added in [PR #923](https://github.com/anthropics/claude-agent-sdk-python/pull/923), surfacing a field the **CLI emits since v2.1.110** on the final `result` line. Critically, the PR's own E2E test reproduces exactly the founder's symptom:
> `subtype: "success"` + `is_error: true` is the only signal of an API failure on the result message... when the CLI ends a turn with `is_error=True` it exits with code 1, so the SDK transport raises `ProcessError` **after** the `ResultMessage` is yielded.
```
Fatal error in message reader: Command failed with exit code 1 (exit code: 1)
[error] subtype='success' is_error=True api_error_status=400
```
This is a structural match for "generic `Command failed with exit code 1`, empty stderr" — **the `ResultMessage` with `api_error_status=429` is emitted on stdout before the process-level exception, and the runner must collect it there rather than trusting the exit code alone.** `claude-runner.py` needs to consume the async generator inside a try/except that keeps whatever `ResultMessage` was already yielded, exactly as PR #923's test does.

**Does the CLI retry a subscription 429?** Official: [Error reference](https://code.claude.com/docs/en/errors) documents `CLAUDE_CODE_MAX_RETRIES` (default 10, capped 15 as of v2.1.186) and `CLAUDE_CODE_RETRY_WATCHDOG` (set `1` to retry `429`/`529` **capacity** errors indefinitely in unattended/CI sessions, v2.1.199+). This applies to transient/capacity 429s. Real-world evidence ([GitHub #64328](https://github.com/anthropics/claude-code/issues/64328), [#5454](https://github.com/anthropics/claude-code/issues/5454)) shows the **hard subscription usage-limit** rejection (`"You've hit your session limit"`, `quotaLimits.status:"rejected"`) is delivered as an immediate synthetic assistant message + terminal result with **no retry spinner at all** — distinct from the transient/capacity class the retry watchdog targets, and not officially documented as a separate non-retried class (inferred from issue evidence, not stated outright by Anthropic). **This matches the "reactive only" decision already taken**: retrying a hard quota rejection before `resetsAt` cannot succeed, so fail-fast-then-requeue is the correct behavior, not a gap to work around.

### 3. Documented pattern for headless/CI use re: long-running commands

**Source:** [Run Claude Code programmatically](https://code.claude.com/docs/en/headless) — code.claude.com.

The official headless page states the mechanics but not a prescriptive "never background dependent work" rule:
> "If Claude starts a background Bash task during a `claude -p` run... that shell is terminated about five seconds after Claude has returned its final result and stdin has closed... Background subagents and workflows are exempt from the five-second grace because their result is part of the final output, so `claude -p` waits for them to complete [up to `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`]."

No official page states "don't background work you depend on" as an explicit best practice for `-p`/SDK use — this is an implication of the above mechanics (plain backgrounded Bash is killed, not awaited; only subagents/workflows are awaited, and only up to a ceiling), not a documented rule per se. A third-party but directionally consistent source, [picklog.cc — "claude -p Background Tasks"](https://picklog.cc/blog/claude-p-background-tasks) (2026-08-04, not an Anthropic source, cite with that caveat): *"Save `run_in_background` for work whose completion the run does not depend on, because in print mode nothing re-invokes the model to check on it."*

The headless doc also documents `--bare` as the **recommended mode for scripted/SDK calls**, which skips hook/plugin/MCP/CLAUDE.md auto-discovery for determinism — worth checking whether `claude-runner.py` uses it, since DLD's skills rely on plugins and hooks and would presumably need `--bare` avoided or reproduced explicitly.

### 4. System prompt preset vs custom in non-interactive runs, re: background tasks

**Source:** [Modifying system prompts](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts) — code.claude.com.

- SDK default (no `system_prompt` set) is a **minimal prompt** — tool-calling only, no Claude Code coding guidelines. `claude -p` (bare CLI) defaults to the **full** `claude_code` preset automatically; the **Agent SDK does not** — you must explicitly pass `system_prompt={"type": "preset", "preset": "claude_code"}` to match CLI behavior. DLD's runner does this per the feature description, correctly.
- `append` on the preset is documented as *"the lowest-risk customization... nothing is removed"* — this is the mechanism for the QA-specific "never assume background work will be checked" prompt rule the founder wants, via `system_prompt={"type": "preset", "preset": "claude_code", "append": "..."}` or CLI `--append-system-prompt`.
- Documented gotcha ([GitHub #17576](https://github.com/anthropics/claude-code/issues/17576), resolved in docs): the `claude_code` preset does **not** auto-load `CLAUDE.md`; `setting_sources=["project"]` must also be set. Worth checking `claude-runner.py` explicitly, since project-level rules (this repo's `CLAUDE.md`, `.claude/rules/*`) not reaching the model would be a silent behavior gap orthogonal to the background-task bug.
- **No official source ties system-prompt choice (preset vs custom) to background-task frequency or the Bash-auto-background threshold.** Background-tasking is controlled at the tool/CLI layer (`CLAUDE_CODE_AUTO_BACKGROUND_TIMEOUT_MS`, fork-mode defaults, `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`), independent of which system prompt variant is in use — answering "not found" for a documented causal link between the two, beyond the trivial fact that the preset's own text includes general tool-usage instructions.

---

## Approaches

### Approach 1: Mechanical shutoff for autopilot, prompt rule for QA (founder's stated direction)
**Source:** synthesis of [subagents/foreground-background doc](https://code.claude.com/docs/en/subagents), [permissions doc](https://code.claude.com/docs/en/permissions), [modifying-system-prompts doc](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts).
**Description:** For autopilot's `claude-runner.py` invocation, set `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` (env, via the SDK's subprocess env or `--settings`) **and** add `disallowed_tools=["Monitor"]` (belt-and-suspenders, since #73453 shows the env var alone wasn't fully honored for every background path on some 2.1.19x–2.1.22x builds). For QA, leave background tasks on but append a system-prompt rule via `system_prompt={"type":"preset","preset":"claude_code","append": "<QA-specific instruction>"}` telling the model that headless mode never re-invokes it, so it must not end a turn assuming a background/Monitor task will be checked later.
**Used in production by:** This is Anthropic's own documented mechanism (`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS`, `disallowed_tools`, preset+append) — no third-party production report of this exact combination, but each primitive is first-party and version-gated (2.1.182+ / 2.1.198+ / all ≤2.1.280 fleet version).
**Pros:** Matches the founder's decision exactly (mechanical for autopilot, prompt for QA); uses only documented, versioned knobs; low blast radius (runner config + one settings/env change per skill).
**Cons:** `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` forcing Bash foreground means a long CI-style command that autopilot still tries to run inline will now block up to `BASH_MAX_TIMEOUT_MS` and then hard-fail inside the turn (loud, not silent — good) but does **not** by itself stop autopilot from attempting CI inline; the real fix for "never wait on CI" is a prompt/skill-level instruction to dispatch CI asynchronously (e.g., a separate pueue task) rather than inline Bash, which this env var alone cannot enforce. Reported unreliability of the disable-var on Workflow/fork children (#73453) needs a smoke test on 2.1.280 before trusting it in production.
**Compute cost:** ~$1–3 (R1) — `claude-runner.py` (env/SDK options), `autopilot` skill prompt (add "never invoke CI as inline foreground Bash" + Monitor-avoidance rule), `qa` skill prompt (append rule). 3–5 files, no schema/migration risk.
**Example:** `ClaudeAgentOptions(disallowed_tools=["Monitor"], env={"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"})` for autopilot vs. `ClaudeAgentOptions(system_prompt={"type":"preset","preset":"claude_code","append": "Headless mode: never assume a backgrounded task or Monitor tool call will be followed up..."})` for QA.

### Approach 2: Permission-rule scoping only (no full background shutoff)
**Description:** Instead of the blunt `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1`, use scoped deny rules: `Bash(run_in_background:true)` to block the specific parameter and a bare `Monitor` deny to remove the tool, while leaving subagent/workflow backgrounding untouched.
**Used in production by:** Documented primitive ([permissions doc](https://code.claude.com/docs/en/permissions)), no known large-scale production report of this specific combination.
**Pros:** More surgical — doesn't touch subagent backgrounding at all, so future use of subagents inside autopilot isn't collaterally disabled; avoids the #73453 uncertainty about whether the blunt env var is honored for every path.
**Cons:** Leaves `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS` (10 min default) still governing subagent/workflow waits — a stuck subagent-based Task/Monitor combination could still eat 10 minutes before the CLI kills it and moves on, which is closer to but not exactly "never wait." Requires two separate rules instead of one var, more surface to keep in sync.
**Compute cost:** ~$1 (R1) — same files as Approach 1, smaller settings diff.
**Example:** `permissions.deny: ["Monitor", "Bash(run_in_background:true)"]` in the project/skill-scoped settings JSON passed via `--settings`.

*A third "wait longer via `BASH_MAX_TIMEOUT_MS`" approach was considered and ruled out*: even if the undocumented-cap concern in `env-vars` turns out to be a non-issue (no absolute ceiling stated officially, and #26660 shows configs up to 7,200,000 ms in the wild), 150 minutes of CI is an explicit non-goal per the founder's decision, and the reliability bug in #26660 (timeout value silently ignored/randomized, unconfirmed fixed on 2.1.280) makes it an unsafe primary mechanism regardless.

---

## Comparison Matrix

| Criteria | Approach 1 (mechanical shutoff + prompt rule) | Approach 2 (scoped permission rules only) |
|---|---|---|
| Complexity | Low | Low |
| Maintainability | High — one documented env var per runner mode | Medium — two rules to keep in sync, subagent path untouched |
| Coverage of found holes | High (Bash background + Monitor both closed for autopilot) | Medium (Bash + Monitor closed; subagent/workflow wait ceiling still live) |
| Matches founder's stated split (autopilot mechanical / QA prompt) | Yes, directly | Partially — doesn't fully "mechanically close" background for autopilot |
| Dependencies | None beyond CLI ≥2.1.198 (already on 2.1.280) | None beyond CLI ≥2.1.182 |
| Risk of unverified CLI bugs | Medium (#73453 uncertainty on Workflow/fork paths) | Low-medium (same uncertainty doesn't apply, since it never relies on the disable var) |

---

## Recommendation

**Selected:** Approach 1, with Approach 2's `Monitor` bare-deny kept as the belt-and-suspenders addition (i.e., 1+2 combined, not either/or).

**Rationale:** `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is the only primitive Anthropic documents as covering the whole background-task surface in one setting, and it directly answers the founder's "mechanically closed if the CLI allows it" question — it does. Layering the `Monitor` deny on top costs nothing and hedges against the one confirmed gap in that var's coverage (#73453, Workflow/fork children on some 2.1.19x–2.1.22x builds). QA's system-prompt-append path is the documented, lowest-risk way to add an instruction without touching the preset's built-in tool/safety guidance.

**Key factors:**
1. Every primitive used is first-party and version-gated at or below CLI 2.1.280 (the fleet's pinned version), so nothing here requires an upgrade.
2. The real risk this research surfaces is not "does the knob exist" but "is it honored" — #73453 and #26660 are both open/unconfirmed reliability bugs in the exact mechanisms recommended, so a smoke test on 2.1.280 (run a spec that would previously have backgrounded a long Bash call, confirm it now blocks/fails loud instead) belongs in the same PR as the config change.
3. None of these knobs solve "autopilot must never invoke CI inline" by themselves — that is a prompt/skill-level instruction (dispatch CI as a separate async job, don't run it as foreground Bash inside the turn), which `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` only makes *safe* (loud foreground timeout instead of silent background loss) rather than *correct* (still blocks the turn for up to `BASH_MAX_TIMEOUT_MS`).

**Trade-off accepted:** Giving up subagent-level parallelism for autopilot runs while `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` is set — if autopilot ever wants to fan out to background subagents deliberately (not the current holes, but a future capability), this setting has to be scoped off before that lands.

**Confidence:** Medium — the documented semantics are solid (official docs, clear version gates), but two real-world reliability gaps in the exact mechanisms (#73453 for the disable-var's coverage, #26660 for Bash timeout vars being ignored) are open/unconfirmed against CLI 2.1.280 specifically. A short smoke test against the pinned CLI would raise this to High before shipping.

---

## Research Sources

- [Environment variables](https://code.claude.com/docs/en/env-vars) — code.claude.com — `CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS`, `BASH_DEFAULT_TIMEOUT_MS`, `BASH_MAX_TIMEOUT_MS`, `CLAUDE_CODE_MAX_RETRIES`, `CLAUDE_CODE_RETRY_WATCHDOG` semantics and defaults.
- [Run subagents in foreground or background / Subagents](https://code.claude.com/docs/en/subagents) — code.claude.com — `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` precedence over fork mode, foreground/background selection rules per CLI version.
- [Tools reference](https://code.claude.com/docs/en/tools-reference) — code.claude.com — Bash auto-background behavior, Monitor tool description, `disallowedTools` mechanics.
- [Configure permissions](https://code.claude.com/docs/en/permissions) — code.claude.com — bare-name vs scoped deny rules, `Bash(run_in_background:true)` parameter-scoped deny example.
- [Agent SDK permissions](https://code.claude.com/docs/en/agent-sdk/permissions) — code.claude.com — `disallowed_tools` removing a tool definition from the request entirely.
- [Run Claude Code programmatically (headless)](https://code.claude.com/docs/en/headless) — code.claude.com — background-task-at-exit mechanics, `--bare` recommendation for scripted/SDK calls.
- [Modifying system prompts](https://code.claude.com/docs/en/agent-sdk/modifying-system-prompts) — code.claude.com — minimal-default vs `claude_code` preset, `append`, `setting_sources` requirement for `CLAUDE.md`.
- [Error reference](https://code.claude.com/docs/en/errors) — code.claude.com — retry-vs-fail-fast behavior, `CLAUDE_CODE_RETRY_WATCHDOG` targeting 429/529 capacity errors specifically.
- [claude-agent-sdk-python `message_parser.py`](https://github.com/anthropics/claude-agent-sdk-python/blob/main/src/claude_agent_sdk/_internal/message_parser.py) — github.com/anthropics — `rate_limit_event` → `RateLimitEvent` parsing, `ResultMessage` field wiring.
- [Agent SDK reference — Python](https://code.claude.com/docs/en/agent-sdk/python) — code.claude.com — `ResultMessage`/`RateLimitEvent` dataclass shapes, `subtype` values.
- [PR #648 — feat: add typed RateLimitEvent message](https://github.com/anthropics/claude-agent-sdk-python/pull/648) — github.com/anthropics — `RateLimitEvent`/`RateLimitInfo` field names, CLI v2.1.45+ origin.
- [PR #923 — feat: surface api_error_status on ResultMessage](https://github.com/anthropics/claude-agent-sdk-python/pull/923) — github.com/anthropics — `api_error_status` field, CLI v2.1.110+ origin, and the exact "ResultMessage yielded then ProcessError on exit 1" pattern matching this feature's symptom.
- [Issue #583 — MessageParseError on rate_limit_event crashes receive_messages()](https://github.com/anthropics/claude-agent-sdk-python/issues/583) — github.com/anthropics — version gotcha: unhandled `rate_limit_event` kills the message generator on SDK builds predating #648.
- [Issue #73453 — headless -p run exits early, bg wait ceiling not applied](https://github.com/anthropics/claude-code/issues/73453) — github.com/anthropics — reliability gap in `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` coverage for Workflow/fork subagent paths on 2.1.198–2.1.220.
- [Issue #89495 — -p mode Bash auto-background tells model "You will be notified" but never delivers](https://github.com/anthropics/claude-code/issues/89495) — github.com/anthropics — corroborates `CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1` as a working per-run mitigation for the exact silent-data-loss pattern in case (c).
- [Issue #26660 — BASH_DEFAULT_TIMEOUT_MS ignored](https://github.com/anthropics/claude-code/issues/26660) — github.com/anthropics — open, unresolved as found; timeout env vars unreliable as of 2026-02-18, version unconfirmed fixed.
- [Issue #64328 — Workflow harness retries indefinitely on 429 rate_limit, session-limit case](https://github.com/anthropics/claude-code/issues/64328) — github.com/anthropics — direct evidence of the hard-usage-limit 429 JSONL shape (`error:"rate_limit"`, `apiErrorStatus:429`, "You've hit your session limit") arriving without the retry-spinner behavior documented for capacity 429s.
- [Issue #64030 — CLI surfaces transient 429 with no backoff, distinct from hard usage limit](https://github.com/anthropics/claude-code/issues/64030) — github.com/anthropics — contrasts transient rate_limit_error (which the docs say gets retried) against the different, harder subscription-quota case.
- [Issue #17576 — Conflicting default logic between claude_code preset and CLAUDE.md loading](https://github.com/anthropics/claude-code/issues/17576) — github.com/anthropics — confirms the preset does not auto-load `CLAUDE.md`; resolved in current docs.

Where a conclusion rests on GitHub issue evidence rather than an explicit Anthropic doc statement (e.g., "hard usage-limit 429 is not retried," "the disable-var has known coverage gaps"), that is called out inline above as inferred, not officially stated.
