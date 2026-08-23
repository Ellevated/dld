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
      - [x] Measure it — **done 2026-08-23**, n=62 clean Opus 5 runs (there were 7
            when this was written). Result below: the Step 0 hypothesis holds, and
            the share is bigger than expected.

### Step 1 measurement, 2026-08-23 — the spawn architecture is 82% of the bill

62 Opus 5 runs carrying session-scope telemetry, against 7 available on 2026-07-27.

| | |
|---|---|
| correlation(session cache_creation, cost) | **0.945** |
| median $ per 1M cache_creation tokens | $19.91 |
| session cache_creation, median | 898,306 |
| main-loop cache_creation, median | 119,468 |
| **subagent share of context built, median** | **82%** |
| session cache_read, median | 19,152,254 |
| cost split | opus-5 67% / sonnet-5 33% / haiku 0% |

Step 0 said cost tracks cache_creation almost linearly and hit rate says nothing.
At n=62 that is no longer an impression: r = 0.945. Four fifths of every dollar is
spent building subagent contexts — not on the main loop, and not on Opus 5 thinking
longer. **The model is not what got expensive. Re-priming it 20+ times per spec is.**

That reframes the "is Opus 5 worth it" question, which the delivery numbers otherwise
answer badly. Measured over the same boundary:

| | before 2026-07-26 | from 2026-07-26 |
|---|---|---|
| $ per delivered spec | $10.31 | **$38.18** |
| runs per delivered spec | 1.41 | **1.71** |
| machine-hours per delivered spec | 0.76 | **1.66** |
| share of spend on runs that delivered nothing | 16% | **44%** |
| burn rate per machine-minute | $0.319 | $0.419 |

Read alone, that table says the accidental 4-6 configuration beat the intended one and
we should roll back. Read with the correlation above, it says something different: the
burn *rate* barely moved (1.3x). What moved is how long a spec takes and how much
context gets rebuilt along the way — and 82% of the rebuilding is an architecture that
exists because a 200K model could not hold a spec in one context. A 1M model can.

So the lever is spawn count, not model choice. Folding one dispatch out of three per
task removes roughly a third of the subagent context, and cost follows cache_creation
at r = 0.945. Downgrading the model attacks the 1.3x and leaves the 5.4x untouched.

Method note so this is reproducible rather than quoted: run durations come from
`task_log`, cost and token scopes from the per-run JSON in `scripts/vps/logs/`, joined
on project + start timestamp (log filenames are host-local, task_log is UTC). Runs
killed before `ResultMessage` log `cost_usd: 0` — 29% of the Opus 5 era against 6%
before it — so unpriced runs are charged at their own period's median burn rate rather
than dropped, which would have flattered August by understating exactly its worst runs.

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
- [x] **7. Cheap wins + harvesting** — done 2026-07-30. Rules and prompt archaeology out
      of the hot path (≈5k tokens/session), the Step 4 refusal gap closed, golden coverage
      4 → 29 agents. The plan's premise for cutting *skills* did not survive: harvesting
      reads subagent traces and skills have none. See "Step 7 result" below.
- [x] **5. Ablation** — done 2026-07-30. The first measurement on the *quality* axis
      rather than the cost axis. `planner.md` cut 77%, measured against its golden
      dataset by two independent instruments. See "Step 5 result" below.
- [x] **11. The skill sweep was run** — 2026-08-02..03. It produced no quality number
      and four defects in the instrument, plus the finding that ends this approach:
      **a skill that reads a codebase cannot be measured against a repository that has
      none.** See "Step 11 result" below. Follow-ups it created:
      - [ ] Re-point the spark eval set at a real project. The AwardyBot clone is proven
            (`BUG-1415`, cited lines verified by hand); the four remaining tasks need
            checking for applicability there before a full two-arm run.
      - [ ] `ai/board/` and `ai/architect/` were only checked for Morning Briefing
            leftovers with a PowerShell glob — the same tool that missed `ai/blueprint/`
            on the first pass. Re-check properly.
      - [ ] `lifecycle.py` calls `backlog.md` "a human-authored view" in a comment;
            `callback.py` calls it "a render". Behaviour is right, the comments disagree.
      - [ ] Worked examples in `review`, `debugger`, `codebase`, `coroner`,
            `cartographer` still carry another product's domains. Editing an example
            changes what it anchors — Step 6 measured that, so this one is measured, not
            guessed.

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

**Shipped from this round:** `planner` (Step 5) and `devil`, both byte-identical to the
prompts that were scored. `coder` and `review` stay as they are — one regressed, the other
produced noise.

The `devil` call was the founder's, and it is worth recording why a tie shipped: quality
is measured-equal, the prompt is 69% smaller, and the anchoring rows above say the example
was not neutral — it fixed the alternative count at two in every run. A tie on quality plus
a real token saving plus evidence of a narrowing effect is a decision, not a coin flip.

### Step 7 result — the cheap wins, and a premise that did not survive, 2026-07-30

Run as four parallel tracks. Two delivered what was expected, one delivered the opposite
of what was expected, and one was structurally impossible — recorded in that order.

**The premise that failed.** The plan was to unblock cutting `autopilot` and `spark`
(68.9 KB and 58.5 KB of skill prompt, the hottest path there is — a skill lives in the
main loop and is re-primed on every compaction, while an agent prompt is paid once per
spawn) by harvesting golden datasets. It cannot work. **Harvesting reads subagent
transcripts, and skills do not run as subagents** — they execute in the main loop and
have no Task trace at all. A golden for a skill is an entire session, not an input/output
pair. This was a wrong assumption in the plan, not a shortfall in the data.

**The rubric is the required half.** `eval-agents.mjs:90-91` skips any pair without a
rubric; the output file is optional and marked "for human reference". So harvesting
automates the half that does not gate, and the half that does — what counts as the
technically correct approach, what plausible-but-wrong answers to penalise — is judgment
that cannot be mined. 306 harvested pairs carry 1852 `TODO(human)` markers, ~6.1 each.

**What harvesting is still worth.** Coverage 4 → 29 agents; `coder` 3 → 117 pairs. And
the inputs stop being fiction: the four shipped goldens are synthetic, built on an
invented "TECH-042 Add API rate limiting" spec against a FastAPI project that does not
exist. 205 of the harvested pairs carry a real spec, inlined because the original
worktree path dies with the run.

One number needs care: `coder`'s 117 pairs are **14 unique specs** — autopilot dispatches
per *task*, and ARCH-362 alone contributed 33.

**Traces are written under the SDK too — settled, not assumed.** Every transcript found
locally carried `entrypoint: "cli"`, which looked like a limit and was only a reflection
of where the runs came from. Confirmed two ways: a live headless probe
(`claude --print --output-format stream-json` with `CLAUDE_CODE_ENTRYPOINT=sdk-py`) wrote
`subagents/agent-*.jsonl` with `entrypoint: sdk-py, isSidechain: true`; and the bundle
shows the write is unconditional — the path builder has no branch on entrypoint, and the
only persistence gate (`shouldSkipPersistence`) resolves to four causes, none reachable
here. One of them is the `--no-session-persistence` flag, which `claude_agent_sdk` 0.1.81
cannot even emit. So the VPS, where the volume is, does produce harvestable traces.

Two corrections to the harvest's own account of itself. The registered agent is
`agentType`, which is always present; `customAgentType` exists only on the
in-process-teammate branch and duplicates it — the fallback carries ordinary subagents,
not the primary. And **the retention story was wrong**: 592 metas without bodies is real,
but `cleanupPeriodDays` cannot produce it. Deletion goes by mtime, the body is newer than
its meta in 978 of 978 pairs, so the meta would go first — and none of the 592 is older
than the 30-day default. Compaction is the first suspect and is unconfirmed. **Unexplained
supply loss in the harvest input remains open**, and raising `cleanupPeriodDays` will not
fix what has not been diagnosed.

**Module Headers, measured rather than read.** Step 6 explained `coder`'s regression by
the cut of its Module Headers section, on the strength of `golden-002.rubric.md:7`
requiring one. Counting the actual repositories says the convention is conditional:

| | with `Module:` |
|---|---|
| PLPilot `_shared/content/*.ts` | 18 / 18 |
| PLPilot `migrations/*.sql` | 0 / 74 |
| PLPilot `tests/*.ts` | 0 / 75 |

Applicable in 1 of 5 curated pairs, inapplicable in 3. The synthetic rubric demanded it
unconditionally. **Step 6's conclusion may be an artefact of the synthetic dataset**, and
five rubrics are now curated to zero TODOs specifically to re-run that measurement. Not
run yet — that is a separate, paid decision.

**Prompt ballast: less than assumed, contradictions: more.** An inventory of 111 files /
812 KB found 4.7 KB of genuine archaeology. The 36 KB of "suspicious" material turned out
to be live instructions duplicated across persona files — and folding them into
`@_shared/` would save **zero tokens**, because the include expands into the prompt. It
is a drift fix, not a context fix. Six real defects were worth more than the bytes:

- `bughunt/SKILL.md` claimed it writes inbox items directly and "finishes after inbox +
  push". `completion.md` says the opposite and the code agrees with `completion.md`. The
  frontmatter `description` carried the dead model too.
- 8 architect personas demanded "minimum 5 search queries / NO RESEARCH = INVALID
  ANALYSIS" while `@_shared/search-cascade.md`, included in the same prompt, permits
  answering from knowledge. This file's own guidance says conflicting instructions
  degrade output on this generation.
- `architect/llm.md` said "TWO phases" above three PHASE branches it implements;
  `architect/SKILL.md` priced 8 personas as opus when 7 are sonnet; `retrofit-mode.md`
  contradicted itself on persona count; the OpenClaw → Hermes rename (ADR-022, 2026-05)
  was never finished in template.

Root savings: **−16.5 KB from rules, −3.75 KB from prompts ≈ 5k tokens per session.**

**The refusal gap from Step 4 is closed.** An unrecovered classifier decline is now
`exit 4` → pueue Failed → spec blocked, with its own telemetry table (a refusal raises no
exception and is not billed, so it landed in no existing counter). A decline the CLI
already re-served on a fallback model deliberately does **not** fail the run — that is the
BUG-188 mistake that cost $258/week. Two research findings outrank the fix: `fallbacks`
cannot be passed through `ClaudeAgentOptions` and **does not need to be** — CLI 2.1.220
already carries the `server-side-fallback-2026-07-01` beta header and emits
`system/model_refusal_fallback`, which is the only path by which the refusal *category*
reaches us, since the SDK drops `stop_details`. And there are five categories, not four.

**A hazard created by this step.** `harvest-goldens.py` inlines verbatim source from
whatever projects ran locally. The first harvest was 15.5 MB across five repositories,
including a client CRM report and a personal job search — and this repository is public.
The tree is gitignored; the tool ships, its output must not. Curate into `test/agents/`
by hand.

**One instrument is quietly broken.** `check-research-stack.py` runs its drift check only
`if live:` — when Exa is unreachable the check is skipped and the script still reports on
other things. Silent degradation is the exact failure mode that script exists to catch.

### Step 8 result — the skill-ablation blocker was wrong, 2026-08-01

Step 7 closed the question of cutting `autopilot` and `spark` — the two hottest prompts
in the tree, because a skill lives in the main loop and is re-primed on every compaction
— with "a golden for a skill is an entire session, not an input/output pair". That is
true of *harvesting*, which reads subagent transcripts. It is not true of measurement.

**`run-eval.mjs` runs a whole skill.** It shells out to
`claude --print --setting-sources=project -p "/<skill> <prompt>"` and
`aggregate-benchmark.mjs` consumes the per-iteration summaries. It was ported into root
on 2026-07-31 — the day *after* Step 7 concluded skills could not be measured. The
blocker was a day out of date when it was written down.

What was missing was not the instrument but two things around it:

- **Isolation.** `run-eval.mjs` ran the skill in the current directory. Evaluating
  `/spark` there claims a real ID, writes a real spec and a real lifecycle record;
  evaluating `/autopilot` commits and pushes. Added `--cwd`, implemented as the child
  process's working directory — the CLI has **no `--cwd` flag** (checked against 2.1.220;
  `rules/dependencies.md` claimed otherwise for `night-reviewer.sh`, which has used `cd`
  for a while).
- **Eval sets.** `.claude/skills/{spark,autopilot}/evals/evals.json`, written against
  failures this repo actually had rather than invented ones: the oversized-spec split
  (the 90-minute run that merged zero lines), the Allowed Files boundary (the two
  baseline planner runs that planned edits outside it), loop discipline (which steps may
  dispatch a subagent), and a spec id that does not exist. Autopilot needs a spec to run
  at all, so two fixtures ship with it — one clean, one carrying the dependency trap that
  the ablation caught a real planner rationalising its way around.

Not run. A sweep is a paid, hours-long operation and the founder makes that call; the
point of this step is that it is now a decision rather than a blocker.

### Step 9 result — two prompt defects, and the check that should have found them

Both were found by reading, which is the problem. Both are decidable by grep.

**The Spark allowlist linter had drifted from the parser it claims to mirror.** Phase 5.5
carried four regexes transcribed into prose under the heading "regex SSOT — must match
callback.py v2". It did not match: `callback.py` accepts numbered-list entries and the
prompt rejected them — and a rejection there ran `rm -f` on the spec. So the failure mode
was *deleting a spec the pipeline would have accepted*, while leaving its
`ai/lifecycle/*.yaml` behind as an orphan and burning the id.

Replaced by `.claude/scripts/validate-allowlist.mjs`, with
`scripts/vps/tests/test_allowlist_parity.py` (23 cases, including every v1 spec in
`ai/features/`) asserting that linter and parser extract identical paths forever. Two
things came out of writing it:

- The prompt-era rules were stricter than the parser on four of six checks and had no
  rule for the one shape that actually breaks the pipeline: an allowlist made entirely of
  bookkeeping paths, which `strip_bookkeeping_paths` empties, so the implementation guard
  can never confirm the spec was done. That is now `ALLOWLIST_E007`.
- The first draft flagged every backticked filename in a reason field as a lost path,
  which failed real specs on sentences like "imports `gate_logic.parse_allowed_files`".
  Only entry-shaped lines — list items and table rows — can lose an entry. Prose names
  references. Worth recording because a linter's own false-positive rate decides whether
  anyone leaves it switched on.

**`docs/18-spec-template.md` was a second, stale copy of the spec template.** It taught
`## Allowed Files` as a *table*, which the parser does not read at all; it carried
`**Status:** draft` after status moved to lifecycle YAML, and a checklist item reading
"Status is `draft` (not `queued`)" — the opposite of what Spark emits. Confirmed live:
the linter finds `ARCH-001` losing four paths to exactly that table shape. Deleted;
README points at the canonical template in `feature-mode.md`.

**The routine.** `.claude/scripts/check-prompt-integrity.mjs` — dead agents, scripts a
prompt tells an agent to run that do not exist, unresolved `@`-includes, and frontmatter
with no `model:`/`effort:`. It reproduces mechanically what Steps 4 and 7 found by hand
(the dead-agent class, the seven dangling script references, `analyzer`/`comparator`
inheriting effort by omission, four haiku agents carrying an inert `effort:`), and it
found one thing nobody had: **`bughunt-solution-architect` has no dispatch site at all.**
Its only mention in the tree is a row in the effort-routing table. CLAUDE.md advertises
bughunt as producing "standalone grouped specs" — that is this agent's job, and nothing
calls it.

**Resolved 2026-08-02, and the first reading of it was wrong.** The agent was not
forgotten; its function was deliberately removed. `skills/bughunt/completion.md` states
plainly "Does NOT create specs directly" — intake moved behind the Hermes gate
(ADR-021/022), so bughunt now saves a report and stops. The agent is the tail of a design
that was retired, and `test/agents-harvested/` still holds eight golden pairs from when it
really did run.

So the defect was never "a dead agent". It was **CLAUDE.md describing behaviour the system
had stopped having** — and getting the report filename wrong too (`ai/bughunt/{date}-report.md`,
not `BUG-XXX-bughunt.md`). Anyone reading CLAUDE.md would expect fix specs to appear in the
queue after a bug hunt. They do not. Agent deleted from both trees, routing row dropped,
CLAUDE.md rewritten against `completion.md`, which is the contract.

The generalisable part: an unreachable agent is a *symptom*, and the check reports it as
one. What it points at is usually a document still promising the removed behaviour — which
is the expensive half, because prompts and humans both read those documents.

Wired into CI as reporting, not blocking: seven pre-existing findings remain open, and
failing the build on them would teach everyone to ignore a red check. Suppressions go in
`prompt-integrity-baseline.json` and must carry a reason.

The generalisation, which is the part worth keeping: **the prompt tree had no automated
check of any kind.** Every rot found in this document was found by a person reading files.
Grep-decidable facts should never cost a review cycle.

### Step 10 result — closing what the check found, 2026-08-01..02

Step 9 shipped `check-prompt-integrity.mjs` and left its findings open on the argument
that failing a build on pre-existing debt teaches people to ignore red. Working through
them turned out to be worth more than the checker: **every one of the four was a promise
the system had stopped keeping, and none of them failed loudly.**

| Finding | What it actually was |
|---|---|
| `agents/review.md` runs `check_domain_imports.py` | The oldest architectural rule in CLAUDE.md — `shared → infra → domains → api` — had **no machine check at all**. The reviewer hit a missing file and fell back to reading |
| `agents/review.md` runs `check_docs_sync.py` | Same, for the "Documentation Sync" gate |
| `architect/{evolutionary,synthesizer}` run `check-dependencies.sh` | Not an instruction at all — a *fitness-function example* proposing a script to write. It describes exactly what `check_domain_imports.py` now does |
| `reflect-aggregator` unreachable | `/reflect` Step 1.5 read `cross-level-patterns.md`, a file only that agent writes, and nothing dispatched it. The file has never existed |

Both missing checks are now written, with tests (33 and 17). Both are ast-based rather
than grep-based, and the import one shows why: `from ..users import models` inside
`domains/billing` is a cross-domain import in which neither the layer name nor the word
"domains" appears anywhere on the line. Both exit 0 where they do not apply — this repo
has neither `src/` nor `.env.example`, and a gate that fails where it is inapplicable
gets switched off everywhere, which is worse than not having it.

`reflect-aggregator` was deleted and its aggregation folded into the skill, by the Step 1
test: grouping signals by topic is neither knowledge the caller lacks nor a judgment that
needs independence — `/reflect` is already holding the file. `api-diff.sh` is the one case
where nothing was written: no equivalent exists, so the block now reads
`<your-api-diff-command>` with three concrete options named, instead of a filename that
looks like it ships.

**Two things this run says about the checker itself.**

Its false-positive shape is now known: it flags `./scripts/foo.sh` inside a *worked
example*, because an example of a command and a command are textually identical. The fix
was to stop writing examples that look like real invocations — which is better than
loosening the check.

And an unreachable agent is worth more as a pointer than as a cleanup. In both cases here
— `bughunt-solution-architect` and `reflect-aggregator` — the agent was the cheap half.
The expensive half was a document still describing the removed behaviour to everyone who
read it, prompts included.

Findings: 13 → 6. What remains is the routing group (`analyzer`/`comparator` with no
`effort:`, four haiku agents carrying an inert one) — deliberately left for the effort
sweep, since two of those are a decision about level rather than a cleanup.

**Unrelated rot found while running the tests**, both pre-existing, both now fixed:
`tests/unit/test_callback_allowlist_v1.py` asserted that numbered-list allowlists are
*ignored* — the very behaviour TECH-208 reversed without updating it, so it had been red
since. One commit left two stale artefacts behind: that test, and the Spark prompt from
Step 9. And `ruff` was failing repo-wide (13 lint errors, 17 unformatted files, 13 of
which nothing in this work had touched), meaning CI's `python-lint` job was already red.

### Step 11 result — the ablation finally ran, and measured the harness instead, 2026-08-02..03

Step 8 ended with "not run: a sweep is a paid, hours-long operation and the founder makes
that call". The call was made. The sweep did not produce a quality number, and the reason it
did not is worth more than the number would have been.

**Four defects in the instrument, each of which silently invalidated a run.** In order of
discovery:

| Defect | What it did |
| --- | --- |
| Timeout discarded all output | `execFileSync` gives `stdout: null` on ETIMEDOUT, so `err.stdout \|\| err.message` always reduced to the message. A run killed at exactly 900000 ms wrote a **26-byte** file reading `spawnSync claude ETIMEDOUT` — while the 29849-byte spec it had produced sat in the clone |
| The harness scored the wrong artifact | It judged stdout. Every deterministic assertion in spark's `evals.json` (`allowlist-parses`, `no-status-field`, `min-eval-criteria`) is a property of the **written spec**. `--print` prints only at the end, so the file exists long before any output does |
| `900s` was recorded as "the working floor" | It is the number the first baseline died at. Corrected to 2700000 |
| A clone could still push home | An eval run committed a spec and ran `git push` against the repo it was cloned from. It failed **only** because that origin was a non-bare repo with the branch checked out — git refusing, not isolation working |

Then a fifth, in the fix for the second: artifact capture read `git status --porcelain`, which
shows nothing committed. `/spark` commits every spec and lifecycle record it writes, so the
harness reported `artifacts: 1` for a run that had just produced **nine specs** in twelve
commits — the one file it found was an uncommitted counter. Same defect shape as the one it
was written to repair. It now captures the union of the working tree and `baseRef..HEAD`, and
lives in `.claude/scripts/lib/capture-artifacts.mjs` with five tests, because the first
version shipped unverified and was wrong.

**The finding that ends this line of work as designed: the eval set cannot be run here.**
Its five tasks — rate limiting on a public REST API, replacing an auth stack, a Wednesday
discount, a payment webhook — presuppose a product. DLD has no `src/`, no users, no orders.
Spark correctly refused all five, in every arm, with `blocked / PREMISE_UNVERIFIED`.

That is not a null result, it is an unusable instrument: the assertions are written assuming
a spec gets created, so **the set rewards the arm that invents itself a task and penalises
the one that refuses honestly.** Both behaviours appeared. On the same prompt, a 16.5 KB
CLAUDE.md arm wrote nine specs by redefining the task; a 7.3 KB arm returned `blocked` with
three options and a reason. By the set's own scoring the first wins.

**What the refusing arm found instead.** `ai/blueprint/` did not describe DLD. Seven of its
eight files were **Morning Briefing Agent** — Clerk auth, Fly.io, Turso,
`/api/v1/workspaces/{workspaceId}`, $99/month — a product designed as a dogfooding exercise
on 2026-05-23 and never built. And `ai/blueprint/` is not an archive:

```
feature-mode.md:216 — If ai/blueprint/system-blueprint/ exists, ALL scouts receive it as CONSTRAINT.
feature-mode.md:258 — All approaches must respect blueprint.
feature-mode.md:794 — gate: "No contradictions with system blueprint?"
```

So every `/spark` run in this repository handed three scouts another product's architecture
as a binding constraint, then checked its own output for agreement with it. The prediction
one run wrote down — *"a run that trusted it would produce a confident, well-formed spec
against Clerk middleware, pass Gate 3 and Gate 6, and hand autopilot a 90-minute session
that merges zero lines"* — was fulfilled by the other arm on the next eval, which wrote
`FTR-221 — Identity store: expand-only clerk_user_id binding`, R0, `status: queued`. Its
blocking precondition was in the spec body; the dispatcher reads the YAML.

Seven files moved to `examples/morning-briefing-blueprint/`. The eighth,
`callback-lifecycle-contour.md`, was genuinely ours and is now in `docs/orchestrator/`.
**A blanket delete would have destroyed it** — the reason to read before removing.

**Two defect classes closed tree-wide rather than instance by instance.**

*A document promising what does not exist.* `ai/glossary/` and `.claude/contexts/` are
per-project artifacts this repo does not have, named unconditionally in coder, documenter and
context-updater. Worse, three **instruction** tables were pinned to one product's domains —
`billing`, `campaigns`, `seller`, `buyer`, `outreach`, down to `buyer/states.py`. Not
examples: `tester.md` selected which tests to run from that list, and `documenter` runs at
Step 3.5 of *every* autopilot spec. Rewritten positionally.

*Instructions arguing inside one prompt.* `coder.md` includes `minimal-code` ("don't add
docstrings to code you didn't change") and then required, under MANDATORY, "Header empty? →
Fill before working". Made conditional, **not cut** — Step 6 measured a regression when the
section was removed, and Step 7's own counts say the convention is conditional (18/18 in one
directory, 0/74 and 0/75 in two others). The rest of that axis is clean: all 57 agents
include `output-conventions`, none demands the self-verification it forbids.

Also swept: `{minimum 5 sources}` in six board directors and the spark research scout,
against the `search-cascade.md` they all include, which says answering from knowledge is
valid and **never to invent a URL**. A required count of URLs in the output schema rewards
producing URLs. Same class as the `NO RESEARCH = INVALID VERDICT` line Step 7 removed from
the architect personas and left in the four council experts.

**A field report, and the two defects behind it.** From awardybot: `completion.md` demanded a
hand-written row in `ai/backlog.md` and warned "Autopilot reads ONLY backlog — orphan spec
files are invisible to it". Both false since ARCH-186: `orchestrator.scan_queued` reads
`ai/lifecycle/*.yaml` and says so in its own docstring, and
`callback._render_and_commit_backlog` re-renders the file after every lifecycle write, so a
hand-written row races the renderer.

Digging for why an agent would do that found the cause two steps up. The ID protocol tells
Spark to `sys.path.insert(0, 'scripts/vps'); import lifecycle` — a module that ships **in
this repository only**, while `claude-runner.py:520` starts the agent with `cwd=project_path`.
awardybot has 471 lifecycle records and no `lifecycle.py` anywhere. So the import fails on
the step that claims the ID, two lines later the prompt says a backlog entry is MANDATORY and
its absence is DATA LOSS, and the agent does the only thing left. **Two defects, one path.**
Nothing was broken underneath — `bootstrap_new_specs` creates the record for any spec lacking
one — the prompt just never said so.

**Where the measurement moves.** Evaluating a skill against the framework repository measures
an empty kitchen. A clone of AwardyBot (origin detached, DLD's spark prompts laid over the
real code) was given the money-precision task and produced
`BUG-1415 — Копилка в миниаппе теряет копейки`, 23 KB, in 9.2 minutes. Verified by hand, not
by judge: `miniapp/src/lib/format.ts:25` `formatKopecks()` carries `maximumFractionDigits: 0`
exactly as cited, `kopecks_to_rub` is real. The root cause is arithmetic rather than restated
symptom — the balance is rounded once from the sum, history per row, so
`Σ round(aᵢ) ≠ round(Σ aᵢ)`. And it did not touch `ai/backlog.md`.

**The generalisation.** Steps 5–8 assumed the subject of measurement is the prompt. It is the
prompt *plus the repository it runs against*. A skill that reads a codebase cannot be
evaluated where there is no codebase — and the framework repo is exactly that place. Skill
evals belong in a clone of a real project; DLD is the harness, not the workload.

### Step 12 result — the Spark ablation ran, and came out a draw, 2026-08-04

The first ablation to produce a number. Two arms of `/spark`, four tasks each, against two
isolated clones of AwardyBot differing in exactly four files.

**The eval set had to be rebuilt, and the reason is the mirror of Step 11's.** There the
five generic tasks presupposed a product the framework repo does not have, and Spark
correctly refused all five. Here they presuppose the *absence* of things AwardyBot already
has: two rate limiters exist, the payment webhook is fully implemented, cookies and refresh
tokens are already in place, and there is no order or clearance category to discount. The
webhook task was the worst of them — its assertion demands the spec require signature
verification, while the code records that the provider offers none, so the assertion
punishes the correct answer. A generic eval set does not port to a real repository in
either direction. The four replacements were each verified by grep before being written
down.

**Arm B is a good-faith cut, not a straw man.** 61.7 KB → 21.4 KB, −66%. Removed: the
`state.json` phase tracking, the cost estimate, the degraded-mode table, the `<GATE>`
checklist after every phase, the eight validation gates as a ritual, and the 310-line
`{placeholder}` spec template. Kept verbatim: every machine-read marker and format, the ID
CAS protocol, the session-budget numbers, the Impact × Risk matrix, and the reason the three
scouts are independent.

**Two prompt defects surfaced from reading the files end to end**, both of the class this
document keeps closing. `feature-mode.md:405` still ordered a backlog row written — a
survivor of the 2026-08-02 fix, 560 lines above the same file's own explanation of why the
backlog is never hand-edited. And `completion.md` ordered the spec **deleted** on a failed
allowlist lint while `feature-mode.md` ordered it **repaired**, with the reason: the id was
already claimed, so deleting orphans the lifecycle record. The second was fixed **in Arm A
as well as Arm B** — otherwise the cut arm would have won by carrying a bug fix, which is
the entanglement Step 5 had to confess to.

**The result.**

| | Arm A (full) | Arm B (−66%) |
|---|---|---|
| Specs produced | 4/4 | 4/4 |
| `validate-allowlist` exit 0 | 4/4 | 4/4 |
| Markers, no `**Status:**`, backlog untouched | ✓ | ✓ |
| Allowed Files entries, total | 44 (6/12/**22**/4) | 22 (9/5/3/5) |
| Paths neither real nor marked NEW | 1 | 0 |
| Wall clock | **59.7 min** | **69.1 min** (+16%) |
| Blind comparator wins | **2** (limiter, webhook) | **2** (kopecks, locale) |
| Mean score, normalised to 5 | 4.14 | 3.93 |

**What is settled: the contracts do not depend on the procedure.** Cutting two thirds of the
prompt broke none of them — eight specs, eight clean allowlist parses, every marker present,
no status in any body, the backlog untouched every time. They hold because they are named and
because a linter stands behind them, not because 300 lines of process surround them.

**What is not settled: quality.** 2–2, with means inside the noise at n=4. This is a draw,
not a win for either side, and reporting it as anything else would be the same
tasting-not-measuring the whole document exists to avoid.

**Two findings worth more than the score.**

*Scope creep is not a function of prompt length.* Both arms lost one round to it, and lost it
the same way. Arm B bundled an unrequested HTTP 200 → 503 change into a storage fix, citing a
provider retry schedule found in no file. Arm A answered a kopeck-sized bug report with 22
files across three bundled surfaces — past its own hard block of 15 — after its own
reproduction showed a ≈1093 ₽ discrepancy it then had to argue down to "a few kopecks". Each
arm's excursion was a real finding filed in the wrong place.

*The gates check what the template does not tell the model to write.* Both arms' bug specs
came out with no Acceptance Verification, and Arm A's with no Historical Risks either — not
because either arm skipped a step, but because the spec template in `bug-mode.md` contains
neither section, while Gates 1b, 6 and 7 live only in `feature-mode.md`, which the bug path
never enters. Both arms sit under this equally, so the comparison stays clean; as a defect in
DLD it outlives the experiment that found it.

**The practical read.** −66% of the prompt buys roughly 10k tokens per Spark dispatch at no
measured cost in quality, and costs 16% more wall clock — which matters against a fixed
`TIMEOUT_SECONDS = 5400`. Neither number alone decides it; the honest position is that the
cut is affordable and unproven, and the next thing to measure is whether the time penalty
holds on a larger n.

### Step 13 result — the first rollout, and two of my own fixes that were wrong, 2026-08-04

The ablation's leftover finding — *"the gates check what the template does not tell the model
to write"* — turned out to understate it. Rolling the corrected Spark prompts to the first
managed project (awardybot) meant reading its gates rather than DLD's, and that produced a
sharper claim: **a bug spec written strictly to `bug-mode.md` could not be committed at all**,
in either repository.

Three gates reject it, and the template failed all three:

| Gate | What it wants | What the template shipped |
|---|---|---|
| `requirePlanBeforeCode` (Check 2) | `## Implementation Plan` with ≥1 `### Task N` | no such section |
| `requireEvalCriteria` (Check 4) | `## Eval Criteria` ≥3 rows + Coverage Summary, or `## Tests` | neither |
| Phase 5.5 allowlist linter | `<!-- callback-allowlist v1 -->` + bullet+backtick rows | numbered list, no marker |

Check 2 fires first, so the fix made on 2026-08-03 — which added Eval Criteria and Acceptance
Verification — never reached its own gate. **A partial fix to a gated path is indistinguishable
from no fix**, and it read as complete because the sections it added were the ones being
discussed at the time.

Verified by running: render the template into a filled spec, stage it in a throwaway repo
carrying the target's real `hooks.config.mjs`, pipe a `git commit` payload into
`validate-spec-complete.mjs`. Deny before, allow after, deny again when the plan section is
removed — the last step being the one that proves the gate is live rather than merely satisfied.

**Two of my own corrections were wrong, both from predicting instead of asking.**

*First*, `be8bc2a` removed the hand-written backlog row on the strength of `scan_queued`
reading the lifecycle YAMLs. True, but `bootstrap_new_specs` runs before it and refuses to
create a record for a spec the backlog does not name — so in a project where Spark cannot claim
the id, the row is the entire handshake. The correction was right about DLD and would have made
specs permanently invisible in all seven managed projects.

*Second*, the fix for that keyed the fallback on whether `scripts/vps/lifecycle.py` ships in the
repository. Also wrong: awardybot ships no such file, and `ai/lifecycle/TECH-1414.yaml` was
still written `updated_by: spark` on 2026-08-03, eight minutes ahead of the spec commit, then
dispatched as pueue_id 1041 with no backlog row in any ref. It reached the module over SSH,
through an escape hatch its own `feature-mode.md` documents.

Both versions asked *"what does this repository contain?"* when the answerable question is
*"did the claim land?"* — one command, `git cat-file -e HEAD:ai/lifecycle/{ID}.yaml`, correct in
every case. **A predicate over repository contents is a guess about the environment; a predicate
over HEAD is an observation.** That is the transferable part, and it is worth more than either
defect it replaced.

**On rolling out at all.** The survey said 0 of 4 Spark files matched the template in any of the
eight clones, which reads as pure drift and argues for a full sync. It is not: awardybot's
divergences include the SSH claim path above, a 4-scout configuration, and a caller-tests rule
in the Impact Tree earned from a real incident. A template-wide overwrite would have deleted all
three — which is what auto-`upgrade` did in May before it was removed. **Whole-file drift counts
are a measure of distance, not of value.** The patch was applied defect-by-defect instead
(`d3b50f305`), and the customizations were named in the commit message so the next reader knows
they were kept deliberately.

Not yet done: the end-to-end `/spark` run in awardybot, blocked on an unrelated local hazard —
`pre-commit` stashes unstaged changes and restores them with `git checkout -- .`, which fails on
a Cyrillic-named `.docx` held open by Word and leaves the restore half-finished. It silently
reverted three of the founder's uncommitted files twice before the pattern was clear; recovered
from pre-commit's own patch file, and the commit was then made from a detached worktree. Six
projects remain unpatched pending that verification.

## How it stays honest

Measured, not tasted. The eval harness works: `test/agents/review/` scored ADR-029 at
opus/low **0.883** against sonnet/xhigh **0.767** on defect recall. Rewriting prompts
by feel is the reliable way to make them worse without noticing.

Every step that changes a prompt gets a golden dataset before the change, not after.

**And check the instrument before trusting the reading.** Step 11 spent a paid sweep
discovering that the harness discarded output on timeout, scored stdout instead of the
files, and ran against a repository the tasks could not apply to. None of that failed
loudly: every run reported a status, wrote files, and exited 0. A green run from a broken
instrument is indistinguishable from a real result until someone opens the artifacts.

The corollary is about *where*, not just *what*: a skill that reads a codebase is measured
against a codebase. This repository is the harness. The workload lives in the projects it
drives.
