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

## What now works against us

1. **"verification" in 54 files.** Anthropic is explicit: explicit verify steps make
   Opus 5 *over*-verify. Over-verification is turns; turns are the 90-minute timeout
   and the $58 run.
2. **Fan-out as a research pattern.** Four scouts existed because one agent could not
   hold the codebase. It can now. Fan-out for *judgment* (council, devil's advocate)
   is a different thing and keeps its value — the two must stop being one pattern.
3. **~220k tokens of prompt, with duplication.** The same rules live in SKILL.md, in
   the mode file, and in the agent prompt. Duplicated and conflicting instructions
   degrade Opus 5 directly.
4. **Fable 5 is unplaced.** A model shipped and the routing table does not know it.

## Plan

Ordered by where money burns, not by what is easiest.

- [ ] **0. Inventory** — walk all 116 files, list the specific instructions that hurt
      under Opus 5, grouped by the seven patterns in `.claude/rules/model-capabilities.md`.
      Read-only. Output is a list of edits, not an opinion.
- [ ] **1. Autopilot** — does context isolation still earn its cost at 1M? Hypothesis:
      one long-lived agent instead of six, no explicit verify steps. This is where the
      money burns.
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
