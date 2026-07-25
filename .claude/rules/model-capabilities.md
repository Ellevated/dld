# Model Capabilities (Claude Opus 5 / Sonnet 5)

Reference for agents about current model capabilities.
Last updated: 2026-07-25

---

## Active Models

| Role | Model ID | Pricing (in/out per Mtok) |
|------|----------|---------------------------|
| Main loop, deep reasoning, review | `claude-opus-5` | $5 / $25 |
| Implementation, research, orchestration | `claude-sonnet-5` | $3 / $15 |
| Formatting, collection, listing | `claude-haiku-4-5-20251001` | $1 / $5 |

**Claude Opus 5** — released 2026-07-24. Step-change over Opus 4.8, not incremental:
frontier intelligence at half the cost of Fable 5, same price as Opus 4.8.

**Previous:** Opus 4.8 (`claude-opus-4-8`) — superseded, still available for rollback.

> **2026-07-25:** VPS pipeline switched 4.8 → 5. `scripts/vps/claude-runner.py`
> pins `MODEL = AUTOPILOT_MODEL` env (default `claude-opus-5`). Rollback without
> code change: `AUTOPILOT_MODEL=claude-opus-4-8`.

---

## Key Capabilities

| Feature | Opus 5 | Sonnet 5 |
|---------|--------|----------|
| Context window | **1M (default AND maximum)** — no smaller variant | 200K |
| Max output tokens | 128K | 64K |
| Thinking | **On by default** (adaptive) | **On by default** (adaptive) |
| Effort levels | low / medium / high / **xhigh** / max | low / medium / high / **xhigh** / max |
| Default effort | `high` | `high` |
| Prompt cache minimum | **512 tokens** (was 1024) | 1024 tokens |
| Fast mode | Yes, API only — $10/$50 per Mtok | — |

**Long context:** Opus 5 keeps instruction following, tool calling and reasoning
consistent across the whole 1M window. No "front-load the important stuff" tricks needed.

---

## Effort Routing Strategy

Anthropic's guidance for Opus 5: *"Start with `high`, the default, and adjust based on
your evals: use `low` and `medium` liberally as your primary control for token cost and
response time wherever quality holds, step up to `xhigh` for demanding coding and agentic
work. If you carried effort settings over from an earlier model, run a fresh effort sweep."*

Their level table names `low` as the level for **subagents** specifically.

| Agent Role | Model | Effort | Rationale |
|------------|-------|--------|-----------|
| autopilot main loop (claude-runner) | opus | xhigh | Long-horizon agentic coding — the one place xhigh earns its cost |
| planner | opus | high | Deep analysis. Held at high (not xhigh) for the 90-min TIMEOUT_SECONDS budget (BUG-1101) |
| review (Code Quality Gate) | **opus** | **low** | Opus 5 finds real bugs at high rate per pass with few false positives, **and accuracy holds at lower effort**. Direct Anthropic recommendation — replaces sonnet/xhigh (ADR-029) |
| debugger | opus | high | Root cause analysis. Down from max — max causes overthinking on structured tasks |
| council experts | opus | high | Down from max. Anthropic: reserve max for "genuinely frontier problems" |
| triz toc-analyst, triz-analyst | opus | high | Down from max, same rationale |
| architect/synthesizer | opus | high | Down from max |
| solution-architect (bughunt) | opus | high | Fix design needs careful reasoning |
| coder | sonnet | high | Sonnet 5 is strong on coding. xhigh only for multi-file refactors |
| scout | sonnet | high | Research quality matters; tool use rises measurably at high/xhigh |
| audit/synthesizer | sonnet | high | Down from xhigh — merge task, not frontier reasoning |
| tester | sonnet | medium | Execution-focused |
| spec-reviewer | sonnet | medium | Checklist verification |
| eval-judge | sonnet | high | Rubric-based evaluation |
| bughunt personas (6) | sonnet | medium | Read + describe from a fixed perspective |
| bughunt spec-assembler, validator | sonnet | medium | Down from high — structured assembly/triage |
| board directors, architect personas | sonnet | medium | Down from high — research + structured report |
| synthesizers (board, triz) | sonnet | medium | Merge/format |
| facilitators (architect/board/spark), council-synthesizer | sonnet | **medium** | Down from max. Process keeping is not a reasoning task — max here was pure waste |
| triz data-collector | sonnet | medium | Shell + aggregation |
| documenter, bughunt scope-decomposer / findings-collector / report-updater | haiku | low | Format-heavy, clear patterns |

**Rule:** effort is a *behavioral signal*, not a token budget. At low effort Claude still
thinks on genuinely hard problems — it just thinks less on easy ones.

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
7. **Knowledge cutoff ~May 2026** — search only for events after that, exact versions/prices, or genuine uncertainty

---

## Model Routing (SSOT in agent frontmatter)

**Rule:** model is defined ONCE in agent frontmatter `model:`.
Never hardcode a model in skill dispatch — use `subagent_type` only.
Frontmatter aliases (`opus`/`sonnet`/`haiku`) resolve to the latest build the CLI supports.
