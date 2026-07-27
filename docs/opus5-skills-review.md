# Skills review for the Opus 5 generation

Living document. Started 2026-07-27.

## Why

DLD's skills were designed against Opus 4.5 → 4.8: a 200K context window and a model
that did not verify its own work. Almost every architectural choice in the framework
is a workaround for one of those two facts — fresh subagent per task so context stays
clean, worktree isolation, four scouts instead of one reader, explicit verification
steps at every gate.

Opus 5 has a 1M window as its *default and maximum*, verifies itself unprompted, and
delegates to subagents more readily than it should. Anthropic removed **over 80% of
Claude Code's own system prompt** for this generation with no measurable loss on their
coding evals.

The sharpest version of the problem: **the VPS had never once run a 1M model until
2026-07-26.** A `claude` binary frozen since March silently served `claude-opus-4-6`
to every orchestrated run. We spent months tuning workarounds for a constraint, fixed
the constraint yesterday, and have not revisited a single workaround since.

This is not a cleanup. The question is what the skills should look like when the model
they drive thinks differently.

## Measured, 2026-07-27

| | |
|---|---|
| Prompt tree | 116 files, 865 KB, **~220k tokens** (`.claude/skills` + `.claude/agents`) |
| Files containing "verif" | **54** |
| Agent types per autopilot **task** | 6 — planner, coder, tester, spec-reviewer, review, debugger |
| Spawns per 5-task spec | **20+**, each reading context cold |
| Fan-out in council / architect | 10 dispatches each |
| Cache-read tokens in one production run | 19.6M |
| Fable 5 placement in routing | none |

## Step 0 result — two of the four suspicions did not survive measurement

Recorded here rather than quietly dropped, because the wrong version of this list was
about to drive edits across 116 files.

**"54 files contain verification scaffolding" was wrong.** That number came from a
substring match on `verif`. The 194 occurrences are almost entirely deterministic
gates (CI, coverage, file gates, "no uncommitted changes before force-removal"),
grep-evidence discipline ("no path cited as a reuse target without a verifying command
and its actual output"), and security domain content. Anthropic's guidance says to
*keep* deterministic gates; grep-evidence is anti-hallucination, not self-verification.
A precise match for the actual anti-pattern finds **3 hits, two of which are the
instruction that suppresses it** (`_shared/output-conventions.md`, added by ADR-029).
There is no verification-scaffolding problem.

**"~220k tokens of prompt with duplication" was half wrong.** The tree is 831 KB /
~212k tokens, but near-duplicate blocks across files total **13 KB — 1%**. The volume
is not redundancy. And skills load on demand, so the tree size is not what any single
session pays.

**What the money actually is.** 40 production runs, from the run logs:

| | tokens | share |
|---|---|---|
| cache_read (context re-read) | 74,864,547 | **89%** |
| cache_creation (context written) | 9,170,161 | 10% |
| input (genuinely new) | 53,202 | **0%** |

Healthy runs sit at hit rate 0.91–0.96 with cache_creation of 67–125k. The dowry-mc
timeout that cost **$58.57** shows cache_creation of **6,244,651** at hit rate **0.50**
— cache thrashing, an order of magnitude off every healthy run. cache_creation bills at
a premium; that single number is most of the $58.

Each subagent spawn primes a new cache prefix, and each compaction invalidates it. A
5-task spec is 20+ spawns. The cost is not what the prompts say — it is **how many times
we re-prime a model that no longer needs re-priming**.

## What now works against us

Revised after Step 0. Two items removed, one sharpened.

1. **Re-priming, not prompting.** 20+ spawns per spec, each building a fresh cache
   prefix on a model that could have held the whole spec in one context. This is where
   every dollar is, and it is pure 200K-era design.
2. **Fan-out as a research pattern.** Four scouts existed because one agent could not
   hold the codebase. It can now. Fan-out for *judgment* (council, devil's advocate)
   is a different thing and keeps its value — the two must stop being one pattern.
3. **Fable 5 is unplaced.** A model shipped and the routing table does not know it.

Open oddity, not yet explained: one awardybot run logged **1 turn and $26.19** against
78k cache_read. Either a cost mis-attribution or something expensive happening in a
single turn. Worth a look before trusting per-run cost as a metric.

## Plan

Ordered by where money burns, not by what is easiest.

- [x] **0. Inventory** — done 2026-07-27. Killed two of the four suspicions and
      located the cost precisely (see Step 0 result above). The prompts are not the
      problem; the spawn architecture is.
- [ ] **1. Autopilot** — does context isolation still earn its cost at 1M? The target
      metric is now specific: cache_creation per spec and cache hit rate, against the
      0.91–0.96 / 67–125k baseline of healthy runs. Hypothesis: one long-lived agent
      instead of six. This is where the money burns.
- [ ] **2. Spark** — four scouts down to however many are actually needed. The Gate 1b
      spec-size limiter added 2026-07-26 is a bandage over specs bloated by the
      multi-agent design itself.
- [ ] **3. Council / architect / board** — keep the diversity, it is judgment rather
      than research. Cut only the scaffolding.
- [ ] **4. Fable 5** placement + a fresh effort sweep.

## How it stays honest

Measured, not tasted. The eval harness works: `test/agents/review/` scored ADR-029 at
opus/low **0.883** against sonnet/xhigh **0.767** on defect recall. Rewriting prompts
by feel is the reliable way to make them worse without noticing.

Every step that changes a prompt gets a golden dataset before the change, not after.
