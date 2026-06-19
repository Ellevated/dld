# Feature: [TECH-203] Effort + ADR + template config alignment for Opus 4.8

**Priority:** P1 | **Date:** 2026-06-19

> **Lifecycle state** is tracked in `ai/lifecycle/{spec_id}.yaml` (ARCH-186).

⚠️ **Size warning:** 12 allowed files (9 are template agent-frontmatter syncs —
mechanical). R2 except `claude-runner.py` (R1, prod runtime — guarded below).

## Why

Config/doc drift surfaced by the Opus 4.8 audit (2026-06-19,
`memory/reference_opus-4-8-prompting-guide.md`):

1. **claude-runner main loop sets no effort** (`claude-runner.py:193-217`
   `ClaudeAgentOptions` has no `effort`). On 4.8 the default is `high`, so the
   autopilot silently runs at `high` — correct, but unpinned. If the SDK/CLI
   default shifts, behavior drifts. Pin it explicitly. (Founder decision
   2026-06-19: pin `high`, not `xhigh` — see SDK enum note below; no cost bump.)
2. **`model-capabilities.md` Effort Routing table diverged from frontmatter**
   (the SSOT per project rule). Table says planner `xhigh`/coder `medium`/
   council `xhigh`; actual frontmatter is planner `high`/coder `high`/council
   `max`. Anyone consulting the table gets wrong info.
3. **ADR-005/ADR-019 are justified by Opus 4.6/4.7 behavior** ("overthinking").
   Under 4.8 overthinking is governed by the effort parameter, not by
   downgrading the model. The ADRs need a 4.8 note — but the routing logic
   (synthesizers→sonnet, formatters→haiku) is a cost win and must NOT be
   reverted without 4.8 benchmarks (devil C-3).
4. **10 root↔template agent-frontmatter divergences** — template never received
   the ADR-019 rebalance, so new projects deploy on stale (pricier, 4.7-era)
   routing.

## Context

- **SDK effort enum (verified, `claude_agent_sdk` 0.1.63 `types.py:1264`):
  `low | medium | high | max` — NO `xhigh`.** The Claude Code CLI / frontmatter
  surface DOES accept `xhigh` (used pervasively in DLD frontmatter, resolved by
  the CLI for subagents). The `ClaudeAgentOptions.effort` path (claude-runner
  main loop) is limited to the SDK enum → main loop can pin at most `high`.
  This is exactly why we pin `high`, and it must be documented to prevent a
  future "set xhigh in claude-runner" attempt that would 400/TypeError.
- review.md (content + frontmatter) is owned by TECH-201 — excluded here.
- Devil C-2: planner `high→xhigh` risks the 90-min `TIMEOUT_SECONDS` budget
  (already a pain point, BUG-1101). **Resolution: keep planner `high`; fix the
  TABLE to match frontmatter (high), not the reverse.** xhigh deferred to a
  future spec that also raises the timeout.
- Devil C-4: do NOT sync `architecture.md`/`model-capabilities.md`/`dependencies.md`
  into template (DLD-specific ADRs). Only sync the 9 universal agent files.

---

## Scope
**In scope:**
- `claude-runner.py`: add `AUTOPILOT_EFFORT` env (default `high`), validate ∈
  {low,medium,high,max}, pass to `ClaudeAgentOptions(effort=...)`.
- `model-capabilities.md` (root only): sync Effort Routing table to actual
  frontmatter SSOT; add 4.8 notes (effort default `high`; SDK enum lacks
  `xhigh` vs CLI accepts it; thinking adaptive-only/off-by-default via effort).
- `architecture.md` (root only): amend ADR-005 + ADR-019 with a 4.8 note
  (effort governs overthinking; routing logic unchanged); add ADR-028 recording
  the 4.8 alignment + the claude-runner effort pin + SDK-enum constraint.
- Sync 9 template agent files to root frontmatter (ADR-019 rebalance):
  audit/synthesizer, board/synthesizer, triz/synthesizer, planner,
  diary-recorder, documenter, bug-hunt/{findings-collector,report-updater,
  scope-decomposer}.

**Out of scope:**
- review.md (TECH-201 owns it).
- Bumping any agent's effort UP (e.g. planner→xhigh) — table follows frontmatter.
- Reverting ADR-019 routing (synthesizers/formatters stay sonnet/haiku).
- Syncing architecture.md / model-capabilities.md / dependencies.md INTO template.
- night-mode (TECH-204), recall prompts (TECH-201), fan-out (TECH-202).

---

## Impact Tree Analysis

### Step 1: UP — who reads these?
- `claude-runner.py` effort → every autopilot/qa/reflect session main loop.
- `model-capabilities.md` → referenced by ADR-019 + claude-runner comment +
  humans/agents checking routing.
- template agent files → new DLD projects via template.

### Step 2: DOWN
- `claude_agent_sdk.ClaudeAgentOptions(effort=...)` (enum-validated).

### Step 3: BY TERM
- `grep -n "AUTOPILOT_EFFORT\|effort=" scripts/vps/claude-runner.py`
- `grep -n "Opus 4.7 era\|Opus 4.6" .claude/rules/architecture.md`

### Step 4: CHECKLIST
- [ ] No template architecture.md/model-capabilities.md/dependencies.md edits.
- [ ] claude-runner change validated against installed SDK signature.
- [ ] dependencies.md "Last Update" row added (claude-runner effort).

### Verification
- [ ] Table matches frontmatter for planner/coder/council/synthesizers.

---

## Allowed Files

<!-- callback-allowlist v1: backticked paths only, one per row. -->

ONLY the files listed below may be modified during implementation.

- `scripts/vps/claude-runner.py` — AUTOPILOT_EFFORT env + ClaudeAgentOptions(effort) (modify)
- `.claude/rules/model-capabilities.md` — sync table to frontmatter + 4.8 notes (modify)
- `.claude/rules/architecture.md` — amend ADR-005/019 + add ADR-028 (modify)
- `.claude/rules/dependencies.md` — Last Update row for claude-runner effort (modify)
- `template/.claude/agents/planner.md` — frontmatter max→high (sync) (modify)
- `template/.claude/agents/audit/synthesizer.md` — opus/max→sonnet/xhigh (sync) (modify)
- `template/.claude/agents/board/synthesizer.md` — opus/max→sonnet/high (sync) (modify)
- `template/.claude/agents/triz/synthesizer.md` — opus/high→sonnet/high (sync) (modify)
- `template/.claude/agents/diary-recorder.md` — sonnet/medium→haiku/low (sync) (modify)
- `template/.claude/agents/documenter.md` — sonnet/medium→haiku/low (sync) (modify)
- `template/.claude/agents/bug-hunt/findings-collector.md` — sonnet/medium→haiku/low (sync) (modify)
- `template/.claude/agents/bug-hunt/report-updater.md` — sonnet/medium→haiku/low (sync) (modify)
- `template/.claude/agents/bug-hunt/scope-decomposer.md` — sonnet/medium→haiku/low (sync) (modify)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** orchestrator (claude-runner) + DLD meta (rules, agent frontmatter).
**Cross-cutting:** none (config/doc).
**Data model:** none.

---

## Historical Risks

<!-- lessons-binding v1 -->

none (no `ai/lessons/` bank). Related memory: `claude-runner-90min-timeout`
(why planner stays `high`, not `xhigh`).

---

## Approaches

### Approach 1: Pin effort=high, table follows frontmatter, minimal ADR note, sync 9 template files (SELECTED)
**Source:** Opus 4.8 guide + audit + devil critique (this session).
**Summary:** Conservative alignment — no cost bumps, no routing reverts, SSOT
made consistent, template caught up.
**Pros:** Low risk; fixes drift; documents the SDK xhigh constraint.
**Cons:** Doesn't capture the guide's xhigh-for-agentic upside (deferred).

### Approach 2: Bump planner→xhigh + claude-runner→xhigh + revisit ADR-019
**Cons:** xhigh invalid in SDK enum (main loop would break); planner xhigh
risks timeout; ADR-019 revert needs benchmarks. Rejected by devil.

### Selected: 1
**Rationale:** Maximizes correctness/safety; the aggressive upside needs a
timeout increase + benchmarks → separate future spec.

---

## Design

### claude-runner.py
```python
# near MODEL (line ~70)
AUTOPILOT_EFFORT = os.environ.get("AUTOPILOT_EFFORT", "high")
_VALID_EFFORT = {"low", "medium", "high", "max"}  # SDK enum — NO xhigh
if AUTOPILOT_EFFORT not in _VALID_EFFORT:
    AUTOPILOT_EFFORT = "high"  # fail-safe
# in ClaudeAgentOptions(...)
    effort=AUTOPILOT_EFFORT,
```
Add a comment: "xhigh is a CLI/frontmatter-only level; SDK enum is
low|medium|high|max. Subagents still resolve effort from their frontmatter."

### model-capabilities.md (root)
- Update Effort Routing table to match frontmatter: planner `high`, coder
  `high`, council experts `max`, council-synthesizer `max`, triz analysts
  `max`, synthesizers per actual (audit `xhigh`, board/triz `high`),
  facilitators `max`.
- Add note block: "**Opus 4.8 effort:** default `high` on all surfaces.
  CLI/frontmatter levels: low|medium|high|xhigh|max. **Agent SDK
  `ClaudeAgentOptions.effort` enum: low|medium|high|max (no xhigh)** — the
  claude-runner main loop pins `high` via `AUTOPILOT_EFFORT`. Thinking is
  adaptive-only and off by default; depth is controlled by effort, not the
  old `thinking budget` format."

### architecture.md
- ADR-005: append "(2026-06: under Opus 4.8, overthinking is governed by the
  effort parameter; routing levels unchanged — see ADR-028.)"
- ADR-019: append "(2026-06: rationale predates Opus 4.8. Routing logic
  retained — sonnet/haiku downgrades remain a cost win; no 4.8 benchmark yet
  justifies reverting. See ADR-028.)"
- Add ADR-028: "Opus 4.8 config alignment. claude-runner pins effort via
  AUTOPILOT_EFFORT (default high; SDK enum low|medium|high|max, no xhigh).
  model-capabilities.md table synced to frontmatter SSOT. ADR-019 routing
  unchanged. Template agent frontmatter caught up to ADR-019. xhigh-for-agentic
  upside deferred pending TIMEOUT_SECONDS increase + benchmarks."

### template agent frontmatter sync (9 files)
Set each template file's `model:`/`effort:` to match its root twin exactly.

---

## Implementation Plan

### Task 1: claude-runner effort pin
**Type:** code
**Files:** `scripts/vps/claude-runner.py`
**Acceptance:** `AUTOPILOT_EFFORT` env (default high, enum-validated) passed to
`ClaudeAgentOptions(effort=...)`; `python3 -c "import claude_agent_sdk;
import inspect; print('effort' in inspect.signature(claude_agent_sdk.ClaudeAgentOptions).parameters)"`
→ True (param exists). No xhigh.

### Task 2: rules docs (model-capabilities + architecture)
**Type:** code
**Files:** `.claude/rules/model-capabilities.md`, `.claude/rules/architecture.md`
**Acceptance:** table matches frontmatter; 4.8 + SDK-enum note present; ADR-005/
019 amended; ADR-028 added.

### Task 3: template frontmatter sync (9 files)
**Type:** code
**Files:** the 9 `template/.claude/agents/...` files listed in Allowed Files.
**Acceptance:** each template file frontmatter == its root twin.

### Execution Order
1 → 2 → 3

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | effort wired | `grep -n "AUTOPILOT_EFFORT" scripts/vps/claude-runner.py` | ≥2 (env + option) | deterministic | design | P0 |
| EC-2 | no xhigh in runner | `grep -c "xhigh" scripts/vps/claude-runner.py` | 0 | deterministic | SDK enum | P0 |
| EC-3 | SDK accepts effort | `python3 -c "import inspect,claude_agent_sdk as s;print('effort' in inspect.signature(s.ClaudeAgentOptions).parameters)"` | True | deterministic | C-1 verify | P0 |
| EC-4 | ADR-028 added | `grep -c "ADR-028" .claude/rules/architecture.md` | ≥1 | deterministic | design | P1 |
| EC-5 | table planner=high | `grep -nE "planner.*\\| *high" .claude/rules/model-capabilities.md` | present | deterministic | SSOT sync | P1 |
| EC-6 | template planner synced | `grep -E "effort: high" template/.claude/agents/planner.md` | present (was max) | deterministic | ADR-019 | P1 |
| EC-7 | no template DLD-doc edits | `git diff --name-only` excludes `template/.claude/rules/` | true | deterministic | C-4 guard | P0 |
| EC-8 | template formatters→haiku | `grep -l "model: haiku" template/.claude/agents/{documenter,diary-recorder}.md template/.claude/agents/bug-hunt/{findings-collector,report-updater,scope-decomposer}.md` | all 5 | deterministic | ADR-019 | P1 |

### Coverage Summary
- Deterministic: 8 | Integration: 0 | LLM-Judge: 0 | Total: 8 (min 3) ✓

### TDD Order
1. EC-3 (verify SDK signature BEFORE editing) → then EC-1/EC-2
2. EC-4/EC-5 (docs)
3. EC-6/EC-7/EC-8 (template sync + guard)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | runner imports | `python3 -c "import ast;ast.parse(open('scripts/vps/claude-runner.py').read())"` | exit 0 | 10s |
| AV-S2 | SDK effort param exists | EC-3 command | True | 15s |

### Functional Checks

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | effort default resolves to high | unset AUTOPILOT_EFFORT | inspect resolved value | "high" |
| AV-F2 | template caught up | repo | EC-6 + EC-8 | all synced |

### Verify Command

```bash
python3 -c "import ast;ast.parse(open('scripts/vps/claude-runner.py').read());print('parse OK')"
python3 -c "import inspect,claude_agent_sdk as s;print('effort param:', 'effort' in inspect.signature(s.ClaudeAgentOptions).parameters)"
grep -n "AUTOPILOT_EFFORT" scripts/vps/claude-runner.py
grep -c "xhigh" scripts/vps/claude-runner.py   # expect 0
grep -c "ADR-028" .claude/rules/architecture.md
grep -E "effort: high" template/.claude/agents/planner.md && echo "template planner synced"
```

> **Note:** AV-S2/EC-3 require the SDK installed (use the orchestrator venv:
> `scripts/vps/venv`). If running outside venv, activate it first.

### Post-Deploy URL

```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] claude-runner pins effort via AUTOPILOT_EFFORT (default high, no xhigh)
- [ ] model-capabilities table matches frontmatter SSOT + 4.8/SDK note
- [ ] ADR-005/019 amended, ADR-028 added
- [ ] 9 template agent files synced to root frontmatter

### Tests
- [ ] EC-1..EC-8 pass (EC-3 confirms SDK signature before code change)

### Technical
- [ ] No edits to template/.claude/rules/ (DLD-specific guard, EC-7)
- [ ] ADR-019 routing logic unchanged (no synthesizer/formatter reverts)
- [ ] dependencies.md "Last Update" row added for claude-runner effort

---

## Autopilot Log
[Auto-populated by autopilot during execution]
