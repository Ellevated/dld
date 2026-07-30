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

### Correction, same day: the "thrashing" framing was an artefact

Both numbers above are main-loop-scope fields being read as if they described the
session. Recomputed session-wide (`_session_totals`, commit d414895) across 34 runs
that carry a model breakdown:

| cost | session cache_creation | session hit rate |
|---|---|---|
| $0.34 | 25,408 | 0.91 |
| $2.22 | 87,816 | 0.96 |
| $22.57 | 709,690 | 0.97 |
| $26.19 | 1,256,266 | 0.97 |
| **$58.57** | **6,496,128** | **0.72** |

The $58 run is **0.72**, not 0.50, and every run — cheap or ruinous — sits at 0.87–0.98.
There is no thrashing mode. Cost tracks **cache_creation volume** almost linearly, and
hit rate says nothing. The mechanism is not poor reuse; it is **how many distinct agent
contexts get built at all**. Same conclusion, honest reason.

### And the drift was everywhere

Of 34 runs with a model breakdown, **27 ran subagents on `claude-opus-4-6`** — including
runs whose main loop was correctly pinned to 4-8, i.e. subagents two generations behind
a pin that read as correct. Only **7 runs, all after the 2026-07-26 CLI fix, are
genuinely Opus 5**.

That is the real baseline problem: almost all historical telemetry describes a different
model generation. Step 1 measures against those 7 runs, not against the 40.

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
- [ ] **1. Autopilot** — does context isolation still earn its cost at 1M?
      - [x] Telemetry made trustworthy first (d414895): session scope published
            alongside main-loop scope, subagent model drift detected. Both corrections
            above came out of it.
      - [x] Loop change, 2026-07-27 (77d5b09): spec-reviewer folded into the loop.
            4 dispatches per task → 3. See "What the agents' contents changed" below.
      - [ ] Measure it: **session cache_creation per completed spec** on the next
            real specs, against the clean Opus 5 baseline below. Hit rate is not the
            metric — it stays high regardless.

### What the agents' contents changed, 2026-07-27

The plan going in was "one long-lived agent instead of six". Reading what the
agents actually carry changed that to a single removal.

**Removed — `spec-reviewer`.** 150 lines of pure procedure: read the spec, compare
requirement by requirement, flag missing or extra. Its two unique checks were
already covered deterministically — TODO/FIXME by `pre-review-check.py` in Step 3a,
Allowed Files by the pre-edit hook and the callback guard. What remained is a
comparison the loop is better placed to make, holding both the spec and the diff
since PHASE 1.

**Kept — `tester`.** Queued for removal on the same cost argument, then reading
`tester.md` reversed it: test-selection tables per domain and infra path, the
immutable-test rules for `tests/contracts/` and `tests/regression/`, eval-judge
dispatch for `llm-judge` criteria. That is a knowledge module, not ceremony, and
inlining 214 lines into every task is the prompt bloat this review exists to avoid.

**Kept — `review`.** The one place independence is load-bearing: an author cannot
see their own duplication. Measured at 0.883 defect recall in the ADR-029 eval.

The lesson generalises to steps 2–4: the question is never "how many agents" but
**does this agent carry knowledge or independence the caller lacks**. A step that
only re-derives the caller's position is paying cache creation for nothing.

### Clean Opus 5 baseline (7 runs, 2026-07-26..27)

| project | exit | cost | session cache_creation |
|---|---|---|---|
| dowry-mc | 0 | $0.69 | 33,508 |
| dowry | 0 | $0.77 | 20,949 |
| dowry | 0 | $1.14 | 57,213 |
| dowry | 0 | $2.35 | 89,402 |
| dowry | 0 | $4.46 | 117,202 |
| dowry | 0 | $13.04 | 715,761 |
| dowry | 0 | $20.13 | 1,304,315 |

Anything Step 1 does is judged against these. Small specs are already cheap; the
question is the top of that table, where one bug fix costs $20 and builds 1.3M tokens
of context.
- [x] **2. Spark** — done 2026-07-27. Four scouts down to three, plus one dead agent
      removed. See "Step 2 result" below.
- [ ] **3. Council / architect / board** — keep the diversity, it is judgment rather
      than research. Cut only the scaffolding.
- [x] **4. Fable 5 + effort sweep** — done 2026-07-27. See "Step 4 result" below. The
      routing table turned out to contain three wrong facts, and the sweep found a
      refusal contract nobody had noticed.
- [x] **5. Ablation** — done 2026-07-30. The first measurement on the *quality* axis
      rather than the cost axis. `planner.md` cut 77%, measured against its golden
      dataset by two independent instruments. See "Step 5 result" below.

### Step 2 result — Spark, 2026-07-27

Same test as Step 1: does this agent carry knowledge or independence the caller lacks?

**Merged — `spark-external` + `spark-patterns` → `spark-research`.** Two agents, both
running Exa against the same feature, both ending in a recommendation, neither able to
see the other's. The proof was sitting in their own prompts: the worked example in
`external.md` concludes "aiogram 3.x — native async, built-in rate limiting", and the
worked example in `patterns.md` concludes "Approach 1, aiogram's built-in throttling is
the clear winner". Two scouts, two research passes, one answer — written by whoever
authored the prompts, without noticing they had converged. Best practices and
alternatives are two views of one search, so they are now one scout with one
recommendation instead of two that synthesis had to reconcile.

**Deleted — `spark-facilitator`.** 340 lines describing the 8-phase protocol, dispatched
by nothing: not by `feature-mode.md`, not by `SKILL.md`, not by the orchestrator's
`_ROUTE_SKILL_MAP`. Spark runs in the main loop. Worse than unused, it had drifted:
5 validation gates against feature-mode's 8, no Session Budget, no Gate 1b/7/8, and
`spec stays draft` on failure — a status `SKILL.md` says Spark never emits and the
orchestrator never picks up. A second copy of a protocol is a copy that will disagree
with the original; this one already did.

**Kept — `spark-codebase`.** Grep evidence across the tree, the Impact Tree, and the two
sections Gates 7 and 8 read directly (`## Historical Risks`, `## Verified References`).
Both gates auto-pass when it is missing, so losing it ships a spec with unverified
references. Knowledge plus a lot of file-reading volume that would otherwise land in the
main context.

**Kept — `spark-devil`.** Same reason autopilot keeps `review`: the author of a proposal
cannot see its holes. Its `DA-*`/`SA-*` assertions feed Gate 2 directly, and it is the
one scout with a golden dataset (`test/agents/devil/`).

Dispatches per feature spec: **4 → 3**. Prompt tree: **−1,208 lines** across both mirrors.

**Not done, deliberately.** The `## Example Output` blocks in `codebase.md` and
`devil.md` (188 lines of invented Telegram-bot content) are a candidate under Anthropic's
"tool usage examples in the prompt — redundant" guidance, and they risk anchoring specs
in an unrelated domain. But the Output Format template already specifies the structure,
so what an example adds is *calibration*, not format — and calibration is exactly what
cannot be judged by eye. `devil` has a golden dataset; that cut should be measured
against it, not made by feel. The merged scout carries no example block: keeping either
of the two converged examples would have re-created the duplication being removed.

### Step 4 result — models and effort, 2026-07-27

Everything below was verified against `platform.claude.com` rather than recalled. That
mattered: the routing table this framework routes by contained three factual errors.

**Sonnet 5 has a 1M context window and 128K max output**, not 200K/64K as the table
said. This is not a typo — it undercuts the review's own framing. "Fan out because one
agent cannot hold the codebase" was being applied to `coder`, `scout`, the spark scouts
and all six audit personas on the strength of a number that was wrong. Sonnet has had
the same 1M window as Opus 5 the whole time.

**Sonnet 5 is on introductory pricing** — $2/$10 through 2026-08-31, then $3/$15. Every
sonnet-vs-opus comparison in this repo has been using a figure 33% too high.

**Sonnet 5's knowledge cutoff is Jan 2026**, four months behind Opus 5's May 2026. The
rules file told every agent to search only for events after ~May 2026; on a sonnet agent
that under-searches a third of a year.

The one claim that held: Opus 5 really is half Fable 5's price on both axes, and
identical to Opus 4.8.

**Fable 5: not routed, and the table now says why.** 2× Opus 5 against an architecture
whose cost is the number of contexts built; a knowledge cutoff *older* than Opus 5's; and
turns long enough that Anthropic's migration guidance is to raise client timeouts first,
against a `TIMEOUT_SECONDS` that already forced `planner` down from xhigh. The decision
is recorded rather than left as an omission, because an omission reads as "not yet
looked at" and gets re-litigated. The one experiment worth running is named there too:
`AUTOPILOT_MODEL=claude-fable-5` on a single large spec — the lever exists without a code
change, and first-shot correctness attacks debugger retry cycles, which is where the
expensive runs in the baseline above actually go.

**The finding that was not on the agenda: refusals.** Opus 5 — not only Fable 5 — carries
safety classifiers that decline requests with `stop_reason: "refusal"` inside a **200 OK**.
One category is `cyber`, and Anthropic's own note on it reads "Benign cybersecurity work
can also trigger this category". Two agents run on opus and are prompted for precisely
that: `council-security` and `bughunt-security-auditor`. Nothing in `scripts/` or
`.claude/` matches `stop_reason`, `refusal`, or `fallbacks` — so a declined security
review returns 200 and flows onward as though it were the report. An empty security
review reads exactly like a clean one. Documented as an open gap; wiring up
`fallbacks: "default"` is a separate piece of work.

**Two routing disagreements**, both resolved in favour of the frontmatter, which is SSOT:

| | Frontmatter | Table said |
|---|---|---|
| bughunt personas ×6 | opus / low | sonnet / medium |
| autopilot main loop | `high` (`xhigh` is not in the SDK enum, so it silently falls back) | xhigh, "the one place xhigh earns its cost" |

The second is the sharper one: the table described a configuration that cannot exist.
The first meant the table still carried the rationale for an abandoned setting — while
opus/low is the *only* effort choice in this repo that was measured into (0.883 vs 0.767,
ADR-029).

**Newly documented, previously absent from the table:** six audit personas (7 dispatches
per deep run), the three spark scouts, and `analyzer`/`comparator` — which have no
`effort:` at all and inherit `high` by omission. An unstated effort is not a decision.

**`effort: low` on haiku has never done anything.** Haiku 4.5 is not in Anthropic's list
of effort-supporting models. ADR-019's cost saving came entirely from the sonnet→haiku
swap.

**Effort changes deliberately not applied.** Candidates exist — `audit-coroner` and
`audit-accountant` are defect-finders configured differently from the bughunt personas
doing the same job; four audit personas do mapping rather than judgment; `spark-devil` is
not tool-heavy and holds `high` on a rationale borrowed from `scout`. None were changed,
because the ADR-029 result is the entire argument for *not* reasoning about effort: it
found the intuitive answer backwards. `spark-devil` and `eval-judge` both have golden
datasets already; those two sweeps come first, and `eval-judge` carries a caveat that
outranks its saving — it is the measuring instrument, and moving it invalidates every
recorded score.

**Three dead agents found**, same profile as `spark-facilitator`: `documenter`,
`reflect-aggregator`, `diary-recorder` — zero dispatch sites between them. `documenter`
is the live question, since three docs describe it as a pipeline stage that does not run.
Left for a separate decision rather than folded in here.

### Step 5 result — ablation, 2026-07-30

Step 0 measured the prompt tree on the **cost** axis and concluded "the prompts are not
the problem; the spawn architecture is". That conclusion is sound on its own axis and
still holds. It is also the wrong axis for the question Anthropic actually answered:
`CLAUDE_CODE_SIMPLE=1` did not save tokens, it made the model *reason better*. Instructions
were not merely costing money — they were suppressing capability. We had never measured
that, despite owning the instrument since ADR-029.

**Subject:** `planner.md`, the largest agent prompt (15.4 KB) and one of the four with a
golden dataset. Body cut 15.2 KB → 3.5 KB (**−77%**, Anthropic's order of magnitude).
Full prompt incl. shared modules 23.8 KB → 12.1 KB (−49%).

**Control.** Only `planner.md`'s own body varies. All four `@`-includes (`minimal-code`,
`context-loader`, `search-cascade`, `output-conventions`) are expanded into both arms by
`expand-agent.mjs` so the baseline arm is the real prompt verbatim rather than a
hand-transcription — verified present exactly once in each. Same model (opus), same
harness, same inline framing, 3 golden specs × 2 arms.

**What was cut:** the "Critical Context" preamble; Phase 3 "Ultrathink" (which contradicts
`model-capabilities.md`'s own rule never to ask this model to think harder); the 95-line
worked Python example in Phase 4; the 56-line Anti-Patterns section; 15 bullets of generic
"Code Must Be / Tests Must Be / Tasks Must Be"; the 8-bullet "Remember" recap. **What was
kept:** drift classification and its log format, the sync-zone rule, the Allowed Files
boundary, the output YAML contract, the lifecycle prohibition.

**Two instruments, because n=3 must not be decided by one judge's noise.**

| | baseline | minimal | Δ |
|---|---|---|---|
| Blind pairwise (`comparator`, arms hidden, base = A once and B twice) | 0.800 | **0.927** | +0.127 |
| Absolute rubric (`eval-judge`) | 0.850 | **0.910** | +0.060 |

Minimal wins **6 of 6** comparisons. Pairwise separates harder than absolute scoring, as
expected; both agree on direction and on ordering within every golden.

**The deterministic findings matter more than the scores.**

| | baseline | minimal |
|---|---|---|
| Tasks carrying a `**Type:**` field | **0 / 0 / 0** | 2 / 5 / 3 |
| Runs planning edits outside Allowed Files | **2 of 3** | **0 of 3** |
| Output size | — | 25–31% shorter |

Both were verified against the output text directly, not taken from a judge.

**Allowed Files is the serious one.** Baseline g002 planned `Add fakeredis[lua] to dev
dependencies` — `pyproject.toml` is not in that spec's Allowed Files. Baseline g003 wrote
`If src/domains/notifications/__init__.py does not exist, create it empty — a package
marker is not a code change`, rationalising the boundary away. Minimal, on the same spec,
climbed the ladder instead: *"adding a dependency requires editing pyproject.toml, which
is not in Allowed Files. The boundary forces a hand-rolled implementation"* — and wrote
its own fake. Same model, same task. The 15 KB prompt states the boundary in Phase 1, adds
a Phase 5 checklist item for it, and then breaks it twice; the 3.5 KB prompt states it
once, in bold, and holds. This is the Cherny thesis reproduced on our own code: 1194
numbered imperatives across the tree dilute, one principle stated once does not.

**A shipped defect fell out of the experiment.** `planner.md` Phase 4 says "create this
EXACT structure" and its template has no `**Type:**` field — while `feature-mode.md`'s
Implementation Plan template, which Spark writes and the rubric encodes, requires it. The
planner's worked example has drifted from the spec format it is supposed to produce, and
the example wins over the requirement every time: 0 occurrences in 3 runs. Baseline also
emitted `**Acceptance Criteria:**` where the contract says `**Acceptance:**` — same cause.

**Honest caveats.** (1) The minimal prompt was authored after reading the rubrics, so part
of its Format/Completeness win is that it was written against the correct contract while
baseline carries a drifted example — ablation and bug-fix are entangled here, and the
`**Type:**` delta belongs mostly to the bug. The contamination did not extend to EC-ID
referencing, which was checked and is comparable in both arms (11–13 occurrences each).
(2) n=3 goldens on one agent. This licenses shipping a change to `planner`, not a
tree-wide rewrite by feel. (3) Both judges are LLMs; the two deterministic rows above are
the part of this result that cannot drift.

**What this licenses next.** The same procedure on `coder`, `review` and `devil` — the
other three agents with golden datasets — before any of the 107 files without one are
touched. The rule from Step 1 still governs and now has evidence: cut procedure and
examples, keep knowledge, contracts and independence.

### Step 6 result — the same ablation on the other three, 2026-07-30

Run immediately after Step 5, same procedure, same blind pairwise instrument, arm
placement varied per golden. **The planner result did not generalise, and that is the
finding.**

| Agent | Cut | Blind pairwise, baseline → minimal | Wins |
|---|---|---|---|
| planner (Step 5) | −77% body | 0.800 → **0.927** | minimal 3/3 |
| coder | −25% | **0.877** → 0.793 | **baseline 2/3** |
| devil | −59% | 0.867 → 0.877 | 1/3 vs 2/3, means within noise |
| review | −34% | **0.89** → 0.85 | baseline 1/1 (**n=1**) |

Across all four agents baseline wins 4 of 7 comparisons. Anyone who had shipped a
tree-wide cut on the strength of Step 5 would have shipped a regression.

**Why coder lost, precisely.** I cut its Module Headers section — a 5-step workflow plus
a format block — reading it as procedure. `test/agents/coder/golden-002.rubric.md` line 7
requires *"module header with Uses/Used by"*, and CLAUDE.md documents it as a project
convention. The judge's reason for the 0.62/0.86 split is exactly that: one file carries
`Module:/Role:/Uses:/Used by:` and Google-style docstrings, the other has two inline
comments. **That was knowledge wearing procedure's clothing, and the measurement caught
what my reading did not.**

**Why devil is a tie, and what the deterministic rows say anyway.** Cutting its 114-line
`## Example Output` — the cut this document has been deferring since Step 2 for want of a
measurement — costs 59% of the prompt and moves quality by +0.010, i.e. nothing. But the
structural counts are not nothing:

| | baseline | minimal |
|---|---|---|
| Alternatives proposed | **2 / 2 / 2** | **3 / 3 / 3** |
| Side-effect (SA-*) assertions | 3 / 2 / 2 | 4 / 3 / 4 |

The baseline's example shows exactly two alternatives, and the baseline produced exactly
two every single time. The example did not calibrate the output, it **anchored** it —
which is the argument Step 2 could not make without running this.

**Review is not evidence.** One golden pair, a 0.04 margin, and the judge's own account
says both arms found all six planted defects and cleared all three decoys, with the
verdict turning on a single severity label. That is noise. It also holds the only measured
recall baseline in the repo (0.883, ADR-029), so it is the last prompt that should be
touched on a hunch.

**What this changes.** The rule from Step 1 — *does this carry knowledge or independence
the caller lacks* — survives, but Step 5 made it look like a licence to cut. It is not.
The rule is only decidable **per agent, against a golden dataset**; four agents produced
four different answers, and the one I was most confident about going in (coder — surely
those numbered steps are filler) was the one that regressed. 107 files have no golden
dataset. None of them should be cut until they do.

**Shipped from this round:** `planner` only (Step 5, byte-identical to what was measured).
`coder` and `review` stay as they are. `devil`'s example block is a defensible cut on
token cost at measured-equal quality — recorded as a recommendation, not taken
unilaterally, because a tie is a judgment call and not a result.

## How it stays honest

Measured, not tasted. The eval harness works: `test/agents/review/` scored ADR-029 at
opus/low **0.883** against sonnet/xhigh **0.767** on defect recall. Rewriting prompts
by feel is the reliable way to make them worse without noticing.

Every step that changes a prompt gets a golden dataset before the change, not after.
