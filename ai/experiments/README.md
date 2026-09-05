# Experiments — changes that carry their own verdict

A change to how the fleet runs (prompt, agent frontmatter, runner config, orchestrator
policy) gets a file here **in the same commit that ships it**. The file states what should
move, by how much, and when to look. `scripts/check-experiments.py` fails when a stated
deadline passes with nothing written back.

## Why this exists

Every expensive discovery in this repo was made by accident, months late:

| Found | Had been true since | Cost of not knowing |
|---|---|---|
| Pueue resolved a March-frozen CLI → the fleet ran Opus 4.6 while the config said Opus 5 | 2026-03 | 4 months of every constant calibrated against the wrong model (ADR-031) |
| `codebase-memory` loaded into every run, called **0 times in 143 runs** | ~2026-05 | tool definitions in 12 agents' context, per run, for nothing |
| The CI-parity gate (TECH-206) lived in a file no run ever opened — 0 of 198 | 2026-06-21 | the improvised final phase it was written to prevent: 60–150 min/spec |
| Rules without `paths:` loading into every session | 2026-07 | 37k tokens/session × 25 days × 9 projects |

None of these were hard to measure. Nobody was asked to.

**The rule this encodes:** shipping a change is half the work. The other half is a number,
taken twice.

## Writing one

`ai/experiments/YYYY-MM-DD-slug.md`, flat front matter (parsed with stdlib — no pyyaml in
the gate, so it cannot fail open on a missing dependency):

```markdown
---
id: EXP-007
title: one line, what changed
opened: 2026-09-05
status: open
metric: what you will measure, and where it comes from
baseline: the numbers as of `opened`, taken with the command below
expected: the threshold that would make this a win — a number, not "better"
command: python3 scripts/metrics/run_metrics.py --split 2026-09-05 --project awardybot
check_after_runs: 15
check_after_date: 2026-09-20
verdict:
---

Body: what changed and why, what the mechanism is supposed to be, and — the part that
matters — **what you will do if the number does not move.** An experiment with no
"then what" is a wish.
```

`expected` must be falsifiable. "Runs get faster" is not a hypothesis; "timeout rate
≤ 25% and p50 ≤ 100 min over the next 15 autopilot runs" is.

`check_after_runs` counts autopilot runs from the orchestrator's own logs, so it survives
a quiet week. `check_after_date` is the backstop and works anywhere, including CI, where
there are no logs to count. Set both.

## Closing one

Re-run `command`, paste both numbers into `verdict:`, set `status:` to one of:

| Status | Means |
|---|---|
| `confirmed` | the metric moved past `expected` |
| `refuted` | it did not — the body says what happens to the change now |
| `inconclusive` | too few runs, or something else moved at the same time and the slices are not comparable |
| `abandoned` | the change was reverted or superseded before it could be measured |

`refuted` is a successful experiment. The failure mode this directory exists to prevent is
not a wrong hypothesis — it is an unexamined one.

**A `refuted` verdict that leaves the change in place needs a sentence saying why.**
"Keeping it, the cost is zero and the mechanism is still sound" is a legitimate answer;
silence is not.
