---
paths:
  - ".claude/agents/**"
  - ".claude/skills/**"
---

# Model Capabilities (Claude Opus 5 / Sonnet 5)

Reference for agents about current model capabilities.
Last updated: 2026-07-31 — verified against platform.claude.com, not from memory.

---

## Active Models

| Role | Model ID | Pricing (in/out per Mtok) |
|------|----------|---------------------------|
| Main loop, deep reasoning, review | `claude-opus-5` | $5 / $25 |
| Implementation, research, orchestration | `claude-sonnet-5` | **$2 / $10 through 2026-08-31**, then $3 / $15 |
| Formatting, collection, listing | `claude-haiku-4-5-20251001` | $1 / $5 |
| Highest capability, 2× Opus 5 — route deliberately | `claude-fable-5` | $10 / $50 |

**Claude Opus 5** — released 2026-07-24. Step-change over Opus 4.8, not incremental:
frontier intelligence at half the cost of Fable 5, same price as Opus 4.8.

**Claude Sonnet 5 is on introductory pricing until 2026-08-31** — $2/$10 rather than
$3/$15. Every sonnet-vs-opus cost comparison made before September is working from a
number 33% too high. The date is the point: this row expires.

**Claude Fable 5** (GA 2026-06-09) is Anthropic's most capable widely released model:
1M context, 128k output, adaptive thinking always on and impossible to disable. Three
facts decide whether it earns 2× Opus 5 in your project: its knowledge cutoff is
**Jan 2026**, *older* than Opus 5's; its turns run long enough that Anthropic's migration
guidance is to raise client timeouts before switching; and its claim is first-shot
correctness, which pays off exactly where your cost sits in retry cycles. Fan-out
architectures feel the doubled rate hardest, because their spend is the number of contexts
built. Measure it on one real task against your own baseline rather than routing it by
reputation.

**Previous:** Opus 4.8 (`claude-opus-4-8`) — superseded, still available for rollback.

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

**Sonnet 5 also has 1M and 128K**, not the 200K/64K of the previous Sonnet generation.
This matters beyond the numbers: any "fan out because one agent cannot hold the codebase"
argument was sized against the old window and is worth re-checking, and so is any
`max_tokens` tuned against 64K.

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

**Re-measure your harness timeout when you change models, not just your prompts.**
A wall-clock limit is calibrated against how long a run took on the model in use when
someone picked the number, and nothing makes it complain when that stops being true —
it just starts killing work. A newer model that thinks longer per turn and takes more
turns can multiply run duration several times over while every spec, prompt and ceiling
stays exactly as it was, so the regression looks like "our specs got too big" and is not.
Before blaming scope, join run durations to their outcomes and compare the periods either
side of the model change: if the upper decile of runs that *succeed* is sitting near the
limit, the limit is the defect. Raise it, then re-run any effort sweep you deferred
because of it.

> **Frontmatter is the SSOT, this table is documentation.** When you change an agent's
> `model:` or `effort:`, change its row here in the same commit, or the next reader routes
> work from a stale table. Where the two disagree, the frontmatter is what runs.

| Agent Role | Model | Effort | Rationale |
|------------|-------|--------|-----------|
| planner | opus | high | Deep analysis. `xhigh` is available but lengthens turns — hold at `high` if your harness has a wall-clock limit |
| review (Code Quality Gate) | **opus** | **low** | Opus 5 finds real bugs at high rate per pass with few false positives, **and accuracy holds at lower effort**. Direct Anthropic recommendation |
| debugger | opus | high | Root cause analysis. Not `max` — max causes overthinking on structured tasks |
| council experts | opus | high | Anthropic: reserve `max` for "genuinely frontier problems" |
| triz toc-analyst, triz-analyst | opus | high | Same rationale |
| architect/synthesizer | opus | high | Same rationale |
| coder | sonnet | high | Sonnet 5 is strong on coding. Before raising to `xhigh` for multi-file refactors, measure it — the one effort sweep run on this framework found *lower* effort winning |
| scout, spark-research, spark-codebase | sonnet | high | Exploratory tool calling and detailed search is where Anthropic names higher effort as paying off |
| spark-devil | sonnet | high | Judgment on a proposal, not tool-heavy — the `scout` rationale does not transfer. Sweep low/medium/high before assuming high is right |
| audit personas (6): accountant, archaeologist, cartographer, coroner, geologist, scout | sonnet | high | 7 dispatches per deep-mode run. Coroner and accountant are defect-finders, so they are candidates for opus/low by the measurement below; the four that do mapping are candidates for medium |
| audit/synthesizer | sonnet | high | Merge task, not frontier reasoning |
| tester | sonnet | medium | Execution-focused |
| eval-judge | sonnet | high | Rubric-based evaluation. **Do not lower without re-running your golden pairs** — this is the measuring instrument, and moving it breaks comparability with every score recorded before |
| analyzer, comparator | sonnet | **high** | Stated, deliberately *not* swept. Both are measuring instruments — `comparator` is the blind pairwise judge used to score prompt ablations, `analyzer` reads benchmark output — so moving their level invalidates comparison with every score already recorded, the same caveat that protects `eval-judge`. `high` is what they inherited by omission; writing it down turns an accident into a decision without changing behaviour |
| bughunt personas (6) | **opus** | **low** | Defect-finding. **Measured:** opus/low scored **0.883** defect recall against sonnet/xhigh at **0.767** on the same eval — the intuitive answer was backwards. Reproduce it before assuming higher effort helps you |
| bughunt spec-assembler, validator | sonnet | medium | Structured assembly/triage |
| board directors, architect personas | sonnet | medium | Research + structured report |
| synthesizers (board, triz) | sonnet | medium | Merge/format |
| facilitators (architect/board), council-synthesizer | sonnet | **medium** | Process keeping is not a reasoning task — `max` here is pure waste |
| triz data-collector | sonnet | medium | Shell + aggregation |
| documenter | **sonnet** | **high** | Greps the whole tree for stale references and judges BREAKING vs REFACTOR — exploratory tool use, which is where higher effort pays |
| bughunt scope-decomposer / findings-collector / report-updater | haiku | — | Format-heavy, clear patterns. **`effort:` has no meaning here** — see below |

**Rule:** effort is a *behavioral signal*, not a token budget. At low effort Claude still
thinks on genuinely hard problems — it just thinks less on easy ones.

**Haiku 4.5 does not support the `effort` parameter.** The supported list is Fable 5,
Mythos 5, Opus 5, Opus 4.8, Mythos Preview, Opus 4.7, Opus 4.6, Sonnet 5, Sonnet 4.6,
Opus 4.5 — Haiku is absent, and its adaptive thinking is "No". An `effort:` line in a
haiku agent's frontmatter is inert; the saving from routing work to haiku comes entirely
from the model swap.

The haiku agents here carried one until it was removed. A setting that looks like tuning
but is inert is worse than no setting: the next reader assumes the level was chosen and
measured. Do not add it back.

**Anthropic names `low` as the level for subagents specifically** — "simpler tasks that
need the best speed and lowest costs, such as subagents". Read that against the 0.883
result above before assuming any `high` in this table was chosen rather than inherited.

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

**Cutting a prompt is a change like any other — measure it.** The same ablation run against
four agents with golden datasets moved one up sharply, moved one *down*, and produced noise
on the other two. The prompt everyone was most confident about cutting was the one that
regressed, because a numbered procedure turned out to encode a project convention. Cut
procedure and examples; keep knowledge, contracts and independence — and check per agent
rather than tree-wide.

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
naming the policy area. It is not an error, so nothing detects it unless you look.

The categories, and Anthropic's own caveat on each:

| Category | Anthropic's note |
|---|---|
| `cyber` | "Benign cybersecurity work **can also trigger** this category" |
| `bio` | "Beneficial life sciences work can also trigger this category" |
| `frontier_llm` | "Benign machine learning work can also trigger this category" |
| `general_harms` | "Benign work might sometimes trigger this category" |

**Why this is not hypothetical.** Two agents here run on opus and are prompted for exactly
the `cyber` category: `council-security` (OWASP, attack surfaces, vulnerability analysis)
and `bughunt-security-auditor` (OWASP Top 10, injection, SSRF, auth bypass). A refusal from
either returns 200 and flows onward as if it were their report — **an empty security review
reads exactly like a clean one.** `architect-security` runs on sonnet, which has no
classifiers, so it is unaffected today but would be if it were ever moved to opus.

The full category list is `cyber`, `bio`, `frontier_llm`, `reasoning_extraction`,
`general_harms`. `stop_details` is always present on a refusal but `category` and
`explanation` are `null` when the decline maps to no named area — branch on `stop_reason`,
never on the inner fields.

**The CLI already retries for you, and that has a cost.** Claude Code arms server-side
fallback itself (`anthropic-beta: server-side-fallback-2026-07-01`) and re-runs a refused
request on another model. So a recovered refusal produces a real answer — from a model you
did not pin. Treat it as model drift, not as a failure. An *unrecovered* refusal is the one
that silently returns nothing useful. (`--fallback-model` is a different mechanism, for
overloaded or unavailable models, not classifier routing.)

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
   content, suspect a classifier decline rather than a bad prompt. Interactively there is
   no signal beyond the symptom; if you run agents headlessly, log `stop_reason` yourself

---

## Model Routing (SSOT in agent frontmatter)

**Rule:** model is defined ONCE in agent frontmatter `model:`.
Never hardcode a model in skill dispatch — use `subagent_type` only.
Frontmatter aliases (`opus`/`sonnet`/`haiku`) resolve to the latest build the CLI supports.
