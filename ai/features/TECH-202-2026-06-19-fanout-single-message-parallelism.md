# Feature: [TECH-202] Fan-out parallelism: run_in_background fixes + single-message dispatch

**Priority:** P1 | **Date:** 2026-06-19

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).

⚠️ **Size warning:** 12 allowed files (8 are the same one-line guidance snippet
added to fan-out dispatch blocks). Homogeneous, R2, prompt-only.

## Why

Per the Opus 4.8 prompting guide (`memory/reference_opus-4-8-prompting-guide.md`,
"Controlling subagent spawning"), 4.8 spawns fewer subagents by default and the
behavior is steerable only with explicit prompting. Concurrency across Task
calls is realized only when the calls are emitted **in the same assistant turn** —
calls issued in separate turns serialize. DLD's fan-out skills (spark 4 scouts,
architect 8 personas ×2 rounds, council 4 experts ×2, bughunt 6 personas × N
zones) never instruct "emit all Task calls in one message", so on 4.8 they risk
silent serialization — fan-out skills feel slower and "less parallel" than on 4.7.

Two skills additionally have an outright bug: their dispatch blocks omit
`run_in_background: true` entirely, so they will run **foreground sequential**
on 4.8:
- `agents/spark/facilitator.md` Phase 2 (4 scouts) — verified no `run_in_background`.
- `skills/architect/retrofit-mode.md` (8 agents) — verified zero `run_in_background`
  (its greenfield twin has it; retrofit drifted).

## Context

- Verified 2026-06-19: only these 2 files lack `run_in_background`. The other
  fan-out skills (`spark/feature-mode.md`, `bughunt/pipeline.md`,
  `council/SKILL.md`, `architect/greenfield-mode.md`) already have the flag —
  they only need the single-message line.
- Devil verdict (this session): **Proceed-narrow.** Concurrency has a harness
  cap (excess Task calls queue, they do not error), so single-message is safe.
  The canonical snippet states the cap explicitly to stay honest. We do NOT
  claim to change headless SDK internals — this is prompt guidance only.
- bughunt `pipeline.md:70` "For each zone Z and persona P" loop framing invites
  one-at-a-time dispatch — reword to "compute matrix, emit all in one turn".

---

## Scope
**In scope:**
- Add `run_in_background: true` to the dispatch Task blocks in
  `spark/facilitator.md` (Phase 2) and `architect/retrofit-mode.md` (both copies).
- Add the canonical single-message guidance snippet to every fan-out dispatch
  block: spark (facilitator + feature-mode), architect (greenfield + retrofit),
  council (SKILL), bughunt (pipeline) — both copies.
- Reword bughunt `pipeline.md` loop framing to matrix-then-emit.

**Out of scope:**
- Any change to `claude-runner.py` / Agent SDK internals (no code).
- ADR-007/008/009/010 file-write + zero-read pattern — KEEP unchanged; this
  spec adds emission guidance, not reception changes.
- Effort/model frontmatter (TECH-203).

---

## Impact Tree Analysis

### Step 1: UP — who runs these dispatch blocks?
- Facilitators/skills during interactive AND headless (orchestrator) runs.
  Guidance is model-facing; no runtime contract changes.

### Step 2: DOWN — dependencies
- Agent/Task tool semantics; existing file-gate + `run_in_background` pattern.

### Step 3: BY TERM
- `grep -rn "run_in_background" .claude/agents/spark/facilitator.md .claude/skills/architect/retrofit-mode.md` → expect ≥1 after fix (currently 0).
- `grep -rln "SINGLE assistant message" .claude template` → expect all fan-out files after change.
- `grep -n "For each zone Z and persona P" .claude/skills/bughunt/pipeline.md` → 0 after reword.

### Step 4: CHECKLIST
- [ ] Both `.claude/` and `template/.claude/` copies edited.
- [ ] No change to forbidden-actions / file-gate blocks.

### Verification
- [ ] All fan-out dispatch blocks carry the single-message line; the 2 buggy
  files now have `run_in_background`.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `.claude/agents/spark/facilitator.md` — add run_in_background + single-message (modify)
- `template/.claude/agents/spark/facilitator.md` — sync (modify)
- `.claude/skills/architect/retrofit-mode.md` — add run_in_background + single-message (modify)
- `template/.claude/skills/architect/retrofit-mode.md` — sync (modify)
- `.claude/skills/spark/feature-mode.md` — add single-message line (modify)
- `template/.claude/skills/spark/feature-mode.md` — sync (modify)
- `.claude/skills/architect/greenfield-mode.md` — add single-message line (modify)
- `template/.claude/skills/architect/greenfield-mode.md` — sync (modify)
- `.claude/skills/council/SKILL.md` — add single-message line (modify)
- `template/.claude/skills/council/SKILL.md` — sync (modify)
- `.claude/skills/bughunt/pipeline.md` — single-message + reword loop framing (modify)
- `template/.claude/skills/bughunt/pipeline.md` — sync (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD meta (agent/skill prompts).
**Cross-cutting:** none.
**Data model:** none.

---

## Historical Risks

<!-- lessons-binding v1 -->

none (no `ai/lessons/` bank).

---

## Approaches

### Approach 1: run_in_background fixes + single-message guidance everywhere (SELECTED)
**Source:** Opus 4.8 guide "Controlling subagent spawning".
**Summary:** Fix the 2 missing flags; add one canonical guidance line to all
fan-out dispatch blocks with an explicit concurrency-cap note.
**Pros:** Restores parallelism; low risk (prompt-only, harness queues excess).
**Cons:** 12 files (mostly identical line).

### Approach 2: Only fix the 2 run_in_background bugs
**Cons:** Leaves the systemic single-message gap → 4.8 may still serialize
multi-turn dispatch.

### Selected: 1
**Rationale:** The 2 flag fixes are unambiguous bugs; the guidance line is a
safe, high-value addition that addresses the documented 4.8 behavior.

---

## Design

### Canonical single-message snippet (add above each dispatch block)
```
> **Emit all Task calls in a SINGLE assistant message** (multiple tool calls in
> one turn). They run concurrently only when emitted together — calls in
> separate turns serialize. Do not launch-then-wait per agent. The harness caps
> concurrent agents and queues the rest, so emitting many at once is safe.
```

### run_in_background fix (facilitator Phase 2, retrofit-mode)
Add `run_in_background: true` to each Task block, matching the
`feature-mode.md` / `greenfield-mode.md` pattern. Do NOT alter the existing
file-gate / zero-read sections.

### bughunt pipeline.md reword
"For each zone Z and persona P: Task: ..." → "Compute the full persona×zone
matrix first, then emit EVERY Task call in ONE assistant message (6 × N calls in
one turn). After launching all in one turn, wait for completion notifications."

---

## Implementation Plan

### Task 1: run_in_background fixes (4 files)
**Type:** code
**Files:** `spark/facilitator.md`, `architect/retrofit-mode.md` (both copies).
**Acceptance:** each dispatch Task block has `run_in_background: true`.

### Task 2: single-message guidance in all fan-out blocks (8 files)
**Type:** code
**Files:** feature-mode, greenfield-mode, council/SKILL, bughunt/pipeline (both
copies) + the 2 from Task 1 also get the line.
**Acceptance:** every fan-out dispatch block carries the canonical snippet.

### Task 3: bughunt pipeline loop reword (2 files)
**Type:** code
**Files:** `bughunt/pipeline.md` (both copies).
**Acceptance:** "For each zone Z and persona P" framing replaced with
matrix-then-emit.

### Execution Order
1 → 2 → 3

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | facilitator bg fix | `grep -c "run_in_background" .claude/agents/spark/facilitator.md template/.claude/agents/spark/facilitator.md` | each ≥1 | deterministic | E-3 | P0 |
| EC-2 | retrofit bg fix | `grep -c "run_in_background" .claude/skills/architect/retrofit-mode.md template/.claude/skills/architect/retrofit-mode.md` | each ≥1 | deterministic | verify | P0 |
| EC-3 | single-message present | `grep -rl "SINGLE assistant message" .claude template/.claude` | ≥12 files | deterministic | E-1 | P0 |
| EC-4 | loop framing removed | `grep -rn "For each zone Z and persona P" .claude template/.claude` | 0 matches | deterministic | E-2 | P1 |
| EC-5 | file-gate untouched | `grep -c "FILE GATE\|file gate\|Glob" .claude/skills/spark/feature-mode.md` | unchanged (≥1) | deterministic | scope guard | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 0 | LLM-Judge: 0 | Total: 5 (min 3) ✓

### TDD Order
1. EC-1/EC-2 (bg flags) → edit → pass
2. EC-3 (snippet) → edit → pass
3. EC-4 (reword) → edit → pass

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | markdown intact | `head -5 .claude/agents/spark/facilitator.md` | frontmatter ok | 5s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | bg flags added | repo | EC-1 + EC-2 commands | each file ≥1 |
| AV-F2 | snippet rolled out | repo | EC-3 command | ≥12 files |

### Verify Command

```bash
grep -c "run_in_background" .claude/agents/spark/facilitator.md .claude/skills/architect/retrofit-mode.md   # each ≥1
grep -rl "SINGLE assistant message" .claude template/.claude | wc -l                                          # ≥12
grep -rn "For each zone Z and persona P" .claude template/.claude || echo "OK: loop framing reworded"
```

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] facilitator Phase 2 + retrofit-mode have run_in_background (both copies)
- [ ] All fan-out dispatch blocks carry the single-message snippet
- [ ] bughunt pipeline loop framing reworded

### Tests
- [ ] EC-1..EC-5 pass

### Technical
- [ ] root/template parity for all 6 fan-out files
- [ ] No change to forbidden-actions / file-gate / zero-read blocks

---

## Autopilot Log
[Auto-populated by autopilot during execution]
