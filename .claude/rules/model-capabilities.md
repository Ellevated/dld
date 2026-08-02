---
paths:
  - ".claude/agents/**"
  - ".claude/skills/**"
  - "template/.claude/agents/**"
  - "template/.claude/skills/**"
  - "scripts/vps/claude-runner.py"
  - "scripts/vps/run-agent.sh"
---

# Model Capabilities (Claude Opus 5 / Sonnet 5)

Reference for agents about current model capabilities.
Last updated: 2026-07-30 — verified against platform.claude.com, not from memory.

---

## Active Models

| Role | Model ID | Pricing (in/out per Mtok) |
|------|----------|---------------------------|
| Main loop, deep reasoning, review | `claude-opus-5` | $5 / $25 |
| Implementation, research, orchestration | `claude-sonnet-5` | **$2 / $10 through 2026-08-31**, then $3 / $15 |
| Formatting, collection, listing | `claude-haiku-4-5-20251001` | $1 / $5 |
| **Not routed** — see below | `claude-fable-5` | $10 / $50 |

**Claude Opus 5** — released 2026-07-24. Step-change over Opus 4.8, not incremental:
frontier intelligence at half the cost of Fable 5, same price as Opus 4.8. (Both halves
verified 2026-07-27 against the pricing page.)

**Claude Sonnet 5 is on introductory pricing until 2026-08-31** — $2/$10 rather than
$3/$15. Every sonnet-vs-opus cost comparison made before September is working from a
number 33% too high. The date is the point: this row expires.

**Previous:** Opus 4.8 (`claude-opus-4-8`) — superseded, still available for rollback.

### Fable 5 — deliberately not routed

`claude-fable-5` (GA 2026-06-09) is Anthropic's most capable widely released model:
1M context, 128k output, adaptive thinking always on and impossible to disable. This
row exists so the decision is visible; an omission reads as "nobody looked yet".

Three reasons it stays unrouted, in order of weight:

1. **2× Opus 5 on both axes against a fan-out architecture.** Bughunt alone is 6
   personas × 2-4 zones; council and architect are ~10 dispatches each. The place
   this framework spends money is the number of contexts built, which is exactly
   where doubling the rate hurts most.
2. **Its knowledge cutoff is *older* than Opus 5's** — Jan 2026 against May 2026.
   Item 7 below tells every agent to search only for things after ~May 2026. On
   Fable 5 that instruction silently under-searches four months of reality.
3. **Turns run long.** Anthropic's migration guidance is to raise client timeouts
   before switching. `TIMEOUT_SECONDS` is 5400 and already forced `planner` down
   from xhigh (BUG-1101).

**The one defensible experiment**, if it is ever wanted: `AUTOPILOT_MODEL=claude-fable-5`
on a single large spec, measured against the Opus 5 baseline in
`docs/opus5-skills-review.md`. The lever exists without a code change. Fable 5's claim is
first-shot correctness, which attacks debugger retry cycles — if it removes them, 2× the
token price can still be cheaper per completed spec. Raise the timeout first.

> **2026-07-25:** VPS pipeline switched 4.8 → 5. `scripts/vps/claude-runner.py`
> pins `MODEL = AUTOPILOT_MODEL` env (default `claude-opus-5`). Rollback without
> code change: `AUTOPILOT_MODEL=claude-opus-4-8`.

---

## Key Capabilities

| Feature | Opus 5 | Sonnet 5 |
|---------|--------|----------|
| Context window | **1M (default AND maximum)** — no smaller variant | **1M** |
| Max output tokens | 128K | **128K** |
| Thinking | **On by default** (adaptive) | **On by default** (adaptive) |
| Effort levels | low / medium / high / **xhigh** / max | low / medium / high / **xhigh** / max |
| Default effort | `high` | `high` |
| Reliable knowledge cutoff | **May 2026** | **Jan 2026** |
| Safety classifiers (`stop_reason: "refusal"`) | **Yes** | No |
| Prompt cache minimum | **512 tokens** (was 1024) | 1024 tokens |
| Fast mode | Yes, API only — $10/$50 per Mtok (research preview) | — |

**Long context:** Opus 5 keeps instruction following, tool calling and reasoning
consistent across the whole 1M window. No "front-load the important stuff" tricks needed.

**Sonnet 5 also has 1M and 128K** — corrected 2026-07-27; this table said 200K/64K for
two days. It matters more than a typo: `coder`, `scout`, the spark scouts and all six
audit personas run on sonnet, and any "fan out because one agent cannot hold the
codebase" argument was being applied to them on the strength of a number that was wrong.
Re-check any `max_tokens` sized against 64K.

**The two cutoffs differ.** Sonnet 5 is Jan 2026, four months behind Opus 5. Item 7 in
"What Agents Should Know" is written for Opus 5; on a sonnet agent the search threshold
is Jan 2026, not May.

---

## Effort Routing Strategy

Anthropic's guidance for Opus 5: *"Start with `high`, the default, and adjust based on
your evals: use `low` and `medium` liberally as your primary control for token cost and
response time wherever quality holds, step up to `xhigh` for demanding coding and agentic
work. If you carried effort settings over from an earlier model, run a fresh effort sweep."*

Their level table names `low` as the level for **subagents** specifically.

> **Frontmatter is the SSOT, this table is documentation.** Where they disagreed on
> 2026-07-27 the table was wrong, not the agents — both disagreements are corrected
> below. When you change an agent's `model:` or `effort:`, change this row in the same
> commit, or the next reader routes work from a stale table.

| Agent Role | Model | Effort | Rationale |
|------------|-------|--------|-----------|
| autopilot main loop (claude-runner) | opus | **high** | Long-horizon agentic coding. **Not xhigh:** `xhigh` is not in the SDK enum (`_VALID_EFFORT` in `claude-runner.py`, ADR-028), so setting it silently falls back to `high`. This row said xhigh and described a config that could not exist |
| planner | opus | high | Deep analysis. Held at high (not xhigh) for the 90-min TIMEOUT_SECONDS budget (BUG-1101). A harness constraint, not a quality finding — revisit if the timeout rises |
| review (Code Quality Gate) | **opus** | **low** | Opus 5 finds real bugs at high rate per pass with few false positives, **and accuracy holds at lower effort**. Direct Anthropic recommendation — replaces sonnet/xhigh (ADR-029) |
| debugger | opus | high | Root cause analysis. Down from max — max causes overthinking on structured tasks |
| council experts | opus | high | Down from max. Anthropic: reserve max for "genuinely frontier problems" |
| triz toc-analyst, triz-analyst | opus | high | Down from max, same rationale |
| architect/synthesizer | opus | high | Down from max |
| coder | sonnet | high | Sonnet 5 is strong on coding. The note "xhigh only for multi-file refactors" described a switch nothing implements — the only measured effort result in this repo found *lower* effort winning, so raising it needs a golden dataset first (`test/agents/coder/` has 3 pairs) |
| scout, spark-research, spark-codebase | sonnet | high | Exploratory tool calling and detailed search is where Anthropic names higher effort as paying off |
| spark-devil | sonnet | high | Judgment on a proposal, not tool-heavy — the `scout` rationale does not transfer. Has a golden dataset (`test/agents/devil/`); sweep low/medium/high before assuming high is right |
| audit personas (6): accountant, archaeologist, cartographer, coroner, geologist, scout | sonnet | high | 7 dispatches per deep-mode run, previously undocumented. Coroner and accountant are defect-finders and are candidates for opus/low by the ADR-029 result; the mapping four are candidates for medium |
| audit/synthesizer | sonnet | high | Down from xhigh — merge task, not frontier reasoning |
| tester | sonnet | medium | Execution-focused |
| eval-judge | sonnet | high | Rubric-based evaluation. **Do not lower without re-running the golden pairs** — this is the measuring instrument, and moving it breaks comparability with every recorded score |
| analyzer, comparator | sonnet | **high** | Stated 2026-08-02, deliberately *not* swept. Both are measuring instruments — `comparator` is the blind pairwise judge used to score prompt ablations, `analyzer` reads benchmark output — so moving their level invalidates comparison with every score already recorded, the same caveat that protects `eval-judge`. `high` is what they inherited by omission; writing it down turns an accident into a decision without changing behaviour |
| bughunt personas (6) | **opus** | **low** | Defect-finding. **Measured:** opus/low scored 0.883 defect recall against sonnet/xhigh at 0.767 (ADR-029 eval). This row said sonnet/medium for two months after the frontmatter changed |
| bughunt spec-assembler, validator | sonnet | medium | Down from high — structured assembly/triage |
| board directors, architect personas | sonnet | medium | Down from high — research + structured report |
| synthesizers (board, triz) | sonnet | medium | Merge/format |
| facilitators (architect/board), council-synthesizer | sonnet | **medium** | Down from max. Process keeping is not a reasoning task — max here was pure waste. (`spark-facilitator` was deleted 2026-07-27 — dispatched by nothing) |
| triz data-collector | sonnet | medium | Shell + aggregation |
| documenter | **sonnet** | **high** | Greps the whole tree for stale references and judges BREAKING vs REFACTOR — exploratory tool use, which is where higher effort pays. Was haiku/low while unwired; wired into PHASE 3 on 2026-07-27 |
| bughunt scope-decomposer / findings-collector / report-updater | haiku | — | Format-heavy, clear patterns. **`effort:` has no meaning here** — see below |

**Rule:** effort is a *behavioral signal*, not a token budget. At low effort Claude still
thinks on genuinely hard problems — it just thinks less on easy ones.

**Haiku 4.5 does not support the `effort` parameter.** The supported list is Fable 5,
Mythos 5, Opus 5, Opus 4.8, Mythos Preview, Opus 4.7, Opus 4.6, Sonnet 5, Sonnet 4.6,
Opus 4.5 — Haiku is absent, and its adaptive thinking is "No". ADR-019's cost saving came
entirely from the sonnet→haiku swap; the effort half of that decision never did anything.

The four haiku agents carried `effort: low` in their frontmatter until 2026-08-02, when it
was removed — it had never been applied to anything, and a setting that looks like tuning
but is inert is worse than no setting: the next reader assumes the level was chosen and
measured. Do not add it back.

**Anthropic names `low` as the level for subagents specifically** — "simpler tasks that
need the best speed and lowest costs, such as subagents". Read that against the ADR-029
result before assuming any `high` in this table was chosen rather than inherited.

**Caching note:** changing effort mid-conversation invalidates the prompt cache prefix.
Pick a level per workload and hold it constant within a session.

---

## Behavior Changes — What To Remove From Prompts

Opus 5 changed enough that legacy scaffolding now actively costs quality. Anthropic
removed **over 80% of Claude Code's own system prompt** for Opus 5 / Fable 5 with no
measurable loss on their coding evals.

| Legacy pattern | Why it's now harmful | Do instead |
|---|---|---|
| "include a final verification step", "use a subagent to verify" | **Causes over-verification.** Opus 5 verifies its own work unprompted. Removing these cuts tokens with no quality loss | Delete. Trust the model; keep only deterministic gates (hooks, CI) |
| "double-check your answer", "re-verify before responding" | Compounds with built-in self-correction — pure cost | Delete |
| "only report high-severity issues", "be conservative", "don't nitpick" | Opus 5/Sonnet 5 follow this **literally** → recall drops. Looks like a capability regression, is a harness bug | "Report everything with confidence + severity; a separate pass filters" |
| Exhaustive rule repositories, repeated rules across system prompt + tool defs | Conflicting/duplicated instructions degrade output | Progressive disclosure — put detail in skills loaded on demand |
| Rigid prohibitions ("NEVER write multi-paragraph docstrings") | Over-constrains judgment | Guidance: "write code that reads like the surrounding code — match its comment density, naming, idiom" |
| Tool usage examples in the prompt | Redundant | Better tool *design*: expressive params, clear enums, instructions in the tool description |
| "After every N tool calls, summarize progress" | Sonnet 5 already gives good interim updates | Delete |

### New behaviors that need *adding* guidance

| Behavior | Mitigation |
|---|---|
| Responses and **written files run longer** | "Match the length of written documents to what the task needs: cover the substance, do not pad with filler sections, redundant summaries, or boilerplate." |
| Narrates agentic work more | Describe the cadence you want. Positive examples beat prohibitions |
| **Delegates to subagents more readily** | Explicit delegation rule or hard cap (see below) |
| Can expand task scope on its own | "Deliver what was asked, at the scope intended… stop short of actions clearly beyond what was asked" |
| Narrates its own corrections more | "Only correct an earlier statement when the error changes the user's code, conclusions, or decisions" |

### Subagent damping (Opus 5 delegates eagerly)

```text
Delegate to a subagent only for large tasks that are genuinely independent and
parallelizable, such as a wide multi-file investigation. Do not delegate work you can
finish yourself in a handful of tool calls, and do not use subagents to verify or
double-check your own work. If one subagent can complete the task, use one rather than
several, and keep spawn counts low.
```

---

## Breaking Changes

### Classifier refusals arrive as success — Opus 5, not just Fable 5

**Opus 5 and Fable 5 carry safety classifiers that can decline a request.** The decline
is `stop_reason: "refusal"` in a normal **HTTP 200** response, with a `category` field
naming the policy area. It is not an error and nothing in this repo looks for it.

The categories, and Anthropic's own caveat on each:

| Category | Anthropic's note |
|---|---|
| `cyber` | "Benign cybersecurity work **can also trigger** this category" |
| `bio` | "Beneficial life sciences work can also trigger this category" |
| `frontier_llm` | "Benign machine learning work can also trigger this category" |
| `general_harms` | "Benign work might sometimes trigger this category" |

**Why this is ours and not hypothetical.** Two agents run on opus and are prompted for
exactly the `cyber` category: `council-security` (OWASP, attack surfaces, vulnerability
analysis) and `bughunt-security-auditor` (OWASP Top 10, injection, SSRF, auth bypass).
A refusal from either returns 200 and flows onward as if it were their report — an empty
security review that reads as a clean one. `architect-security` runs on sonnet, which has
no classifiers, so it is unaffected today but would be if it were ever moved to opus.

The full category list is `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`,
`general_harms`. `stop_details` is always present on a refusal but `category` and
`explanation` are `null` when the decline maps to no named area — branch on `stop_reason`,
never on the inner fields.

#### What `claude-runner` now catches

`scripts/vps/claude-runner.py` inspects every SDK message (`_refusal_from_message`) and
publishes a `refusal` block in the run log — always present, so an absent key means an
older runner rather than a clean run:

| Field | Meaning |
|---|---|
| `detected` | any decline was seen at all |
| `declines` | raw declines (`stop_reason == "refusal"`) |
| `fallbacks_served` | declines the CLI re-ran on another model |
| `unrecovered` | `declines - fallbacks_served`, floored at 0 |
| `categories` | refusal categories, when the SDK surfaced any |
| `events` | up to 10 raw events (source, category, explanation, models) |

**Exit contract:** `unrecovered > 0` → **exit 4** (`classifier_refusal` in `_EXIT_REASONS`),
only ever upgrading from 0 so a timeout or process error keeps its more specific code.
Pueue records the failure, callback routes the spec to `blocked`, and salvage still pushes
whatever the run built. A decline the CLI re-ran on a fallback model produced a real
answer, so it does **not** fail the run — it is warned and recorded exactly like
`model_drift`, because that is what it is: output from a model we did not pin. Failing it
would re-run a finished spec, which is the BUG-188 mistake. ADR-024 is untouched: it
governs SDK exceptions raised *after* a successful `ResultMessage`; this is an in-stream
observation, and the BUG-188 branch still assigns no exit code.

Telemetry lands in its own `classifier_refusals` table (`db.log_classifier_refusal`,
created by `_ensure_migrations` so deployed databases pick it up) — deliberately not
`sdk_post_result_errors`, which measures post-`ResultMessage` SDK drift and has no columns
for category or fallback model.

#### What is still not caught

- **The category, on the decline itself.** `claude_agent_sdk` 0.1.81 (what
  `requirements.txt` resolves to) exposes `stop_reason` on `AssistantMessage` and
  `ResultMessage`, and drops `stop_details` — the dataclasses have no such field, so the
  parser discards it. The category survives only on the CLI's
  `system` / `model_refusal_fallback` message, which the SDK keeps whole as
  `SystemMessage(subtype=…, data=…)` with `data["apiRefusalCategory"]`. So a *recovered*
  refusal is categorised and an *unrecovered* one is not. Recovering it would need
  `include_partial_messages` and reading raw `message_delta` events — a per-token message
  flood through the heartbeat writer, not worth the category string.
- **`fallbacks` cannot be passed from here.** It is a Messages API *body* parameter and
  `ClaudeAgentOptions` has no field for it; `betas` is typed
  `Literal["context-1m-2025-08-07"]` — one value, not an open list. Nothing is lost: the
  Claude Code CLI (verified 2.1.220) already arms server-side fallback itself, sending
  `anthropic-beta: server-side-fallback-2026-07-01` and retrying on refusal. That is why
  the fallback notice exists to be detected. `--fallback-model` is a different mechanism
  (overloaded/unavailable model), not classifier routing.
- **Subagent-scope granularity.** The run log says a decline happened, not which subagent
  hit it. Anthropic's own guidance is that `fallbacks` does not propagate into model calls
  made from inside tool execution, so per-agent attribution would need CLI support.
- **A refused request is not billed** when it arrives before any output, so cost telemetry
  will not show it either. The `classifier_refusals` row is the only counter.

### Opus 4.8 → Opus 5

| What | Impact | Action |
|------|--------|--------|
| Thinking **on by default** | `max_tokens` is a hard limit on thinking + text combined | Revisit `max_tokens` on any workload that ran thinking-off |
| `thinking: {"type":"disabled"}` **rejected at effort `xhigh`/`max`** → HTTP 400 | Breaking. Enforced per request | Either keep thinking disabled and drop effort to `high` or below, or drop the `thinking` field |
| Thinking-disabled artifacts | Model may emit a tool call as *text* (never runs, poisons history) or leak internal XML tags | Keep thinking **enabled** and control cost with low effort instead. Never add "do not think" rules — they increase tag leakage |

### Sonnet 4.6 → Sonnet 5

| What | Impact | Action |
|------|--------|--------|
| **New tokenizer: ~30% more tokens for the same text** | `max_tokens` tuned for 4.6 will truncate equivalent output | Raise `max_tokens`. Also re-check any token-based budgets and LOC heuristics |
| `temperature` / `top_p` / `top_k` non-default → **400 error** | Breaking, new for Sonnet-class | Remove them; steer tone via system prompt |
| Manual extended thinking (`budget_tokens`) removed → 400 | Breaking | Use adaptive thinking + effort |
| Adaptive thinking on by default | Same `max_tokens` concern as Opus 5 | Revisit budgets |
| More literal instruction following | Won't generalize an instruction across items | State scope explicitly: "apply to every section, not just the first" |

**Cross-model effort mapping when migrating:** Sonnet 5 @ medium ≈ Sonnet 4.6 @ high.
Sonnet 5 @ high ≈ Sonnet 4.6 @ max. Benchmark by observed thinking length, not effort name.

---

## What Agents Should Know

1. **Thinking is on and adaptive** — never ask the model to "think harder" or "think step by step"
2. **Effort is the depth control**, not prompt wording
3. **1M context on Opus 5** as default — large codebases fit entirely
4. **Self-verification is built in** — do not add verification steps
5. **Code review is a strength** — high recall per pass, holds at low effort
6. **Prompt caching automatic**; 512-token minimum on Opus 5. `ENABLE_PROMPT_CACHING_1H=1` extends TTL to 1h
7. **Knowledge cutoff differs by model** — Opus 5 is May 2026, **Sonnet 5 is Jan 2026**.
   Search for events after your own cutoff, exact versions/prices, or genuine uncertainty.
   Sonnet agents that assume the May date under-search four months
8. **A refusal is not an answer** — on opus, `stop_reason: "refusal"` comes back as a
   successful response. If output looks empty or evasive on security, bio, or ML-methods
   content, suspect a classifier decline rather than a bad prompt. On VPS runs the
   `refusal` block in the run log answers this directly; interactively there is no such
   signal, so the symptom is all you get

---

## Model Routing (SSOT in agent frontmatter)

**Rule:** model is defined ONCE in agent frontmatter `model:`.
Never hardcode a model in skill dispatch — use `subagent_type` only.
Frontmatter aliases (`opus`/`sonnet`/`haiku`) resolve to the latest build the CLI supports.
