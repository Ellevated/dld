# Board — Retrofit Mode (8-Phase Protocol)

Self-contained protocol for Retrofit Mode. Triggered from `/retrofit` or explicit MODE: retrofit.

---

## Purpose

Reassess business strategy in context of existing code, architecture, and migration plan.

**Input:**
- `ai/audit/deep-audit-report.md` (code reality)
- `ai/blueprint/system-blueprint/` (TO-BE architecture from Architect)
- `ai/architect/migration-path.md` (migration waves)

**Output:** `ai/blueprint/business-blueprint.md`

**Key difference from Greenfield:** Board receives code/architecture context BEFORE strategizing. Directors evaluate business viability of existing codebase and migration plan, not a blank slate.

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store agent responses in orchestrator variables
⛔ NEVER pass full agent output in another agent's prompt
⛔ NEVER use TaskOutput to read agent results
⛔ NEVER read output_file paths from background agents

✅ ALL Task calls use run_in_background: true
✅ Agents WRITE their output to ai/board/ files
✅ Agents READ peer files themselves (via Read tool)
✅ File gates (Glob) verify completion between phases
```

---

### Degraded Mode

If director phases fail partially, continue with available data:

| Failed Phase | Action | Impact |
|-------------|--------|--------|
| Phase 2: 1-2 directors fail | Continue with available research (min 4 required) | Note missing perspectives in synthesis |
| Phase 2: 3+ directors fail | Abort — insufficient diversity for meaningful board | Report "Board aborted — too few director analyses" |
| Phase 3: 1-2 critiques fail | Continue synthesis with available critiques | Note missing cross-critiques |
| Phase 3: All critiques fail | Skip to synthesis using Phase 2 only | Synthesis notes "No cross-critique performed" |
| Phase 4: Synthesizer fails | Read research + critique files directly, present raw findings | No formatted strategies, show available director opinions |

Minimum viable board: 4 director research reports + synthesizer.

---

## Phase 1: BRIEF (Facilitator)

Read ALL three inputs. Extract:
- What the project actually IS (from audit — real usage, real state)
- What the architecture SHOULD become (from system blueprint — TO-BE)
- What the migration costs and risks are (from migration path — effort, dependencies)
- Open questions for each director (business implications of tech findings)

Assign each director their RETROFIT focus.

```
Output: ai/board/board-agenda.md
```

### Phase 2: RESEARCH (6 directors, parallel, isolated)

Each director receives:
- Deep Audit Report + System Blueprint + Migration Path (context)
- `board-agenda.md` (their focus)
- Instruction: "min 5 search queries, of which 2 deep research"

**Each director does NOT see others' conclusions.**

**RETROFIT QUESTIONS per director:**

| Director | Key Question |
|----------|-------------|
| **CPO** | "Which features are ACTUALLY used? Which are dead weight?" |
| **CFO** | "What's the burn rate of tech debt? Cost of NOT fixing?" |
| **CMO** | "Which features drive actual growth? Which are vanity metrics?" |
| **COO** | "What processes are broken? Where is agent/human mismatch?" |
| **CTO** | "Is current stack sustainable? Migration cost vs full rewrite?" |
| **Devil** | "What if we just rewrite from scratch? Is migration even worth it?" |

Dispatch 6 parallel agents (same agent files as greenfield, MODE: retrofit):
```yaml
# All 6 in parallel — MODE: retrofit changes their lens
Task tool:
  description: "Board: CPO research (retrofit)"
  subagent_type: board-cpo
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents of ai/audit/deep-audit-report.md]
    - SYSTEM BLUEPRINT: [summary of ai/blueprint/system-blueprint/ files]
    - MIGRATION PATH: [contents of ai/architect/migration-path.md]
    AGENDA: [CPO section from board-agenda.md]
    Output file: ai/board/research-cpo.md

Task tool:
  description: "Board: CFO research (retrofit)"
  subagent_type: board-cfo
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents]
    - SYSTEM BLUEPRINT: [summary]
    - MIGRATION PATH: [contents]
    AGENDA: [CFO section from board-agenda.md]
    Output file: ai/board/research-cfo.md

Task tool:
  description: "Board: CMO research (retrofit)"
  subagent_type: board-cmo
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents]
    - SYSTEM BLUEPRINT: [summary]
    - MIGRATION PATH: [contents]
    AGENDA: [CMO section from board-agenda.md]
    Output file: ai/board/research-cmo.md

Task tool:
  description: "Board: COO research (retrofit)"
  subagent_type: board-coo
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents]
    - SYSTEM BLUEPRINT: [summary]
    - MIGRATION PATH: [contents]
    AGENDA: [COO section from board-agenda.md]
    Output file: ai/board/research-coo.md

Task tool:
  description: "Board: CTO research (retrofit)"
  subagent_type: board-cto
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents]
    - SYSTEM BLUEPRINT: [summary]
    - MIGRATION PATH: [contents]
    AGENDA: [CTO section from board-agenda.md]
    Output file: ai/board/research-cto.md

Task tool:
  description: "Board: Devil research (retrofit)"
  subagent_type: board-devil
  prompt: |
    MODE: retrofit
    PHASE: 1
    CONTEXT:
    - DEEP AUDIT: [contents]
    - SYSTEM BLUEPRINT: [summary]
    - MIGRATION PATH: [contents]
    AGENDA: [Devil section from board-agenda.md]
    Output file: ai/board/research-devil.md
```

```
Output: ai/board/research-{role}.md × 6
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Same as Greenfield. Each director sees ANONYMOUS research from others (A-E).
Labels instead of names → reduces anchoring bias.

```
Output: ai/board/critique-{role}.md × 6
```

### Phase 4: SYNTHESIS (Synthesizer, opus)

Read 12 files (6 research + 6 critique). Build 2-3 strategy alternatives.

**Retrofit-specific:** Each strategy MUST address:
- **KEEP:** What existing features/business lines to preserve
- **CHANGE:** What to pivot, modify, or re-prioritize
- **DROP:** What to sunset or remove (dead features, vanity metrics)
- **Migration priorities:** Which waves from migration-path.md are business-critical
- **Investment split:** How much to invest in stabilization vs new features

If strategies conflict → Evaporating Cloud.

```yaml
Task tool:
  description: "Board: synthesis (retrofit)"
  subagent_type: board-synthesizer
  prompt: |
    MODE: retrofit
    Read: ai/board/research-*.md, ai/board/critique-*.md, board-agenda.md
    Also read: ai/architect/migration-path.md (for wave context)
    Build 2-3 strategy alternatives. Each MUST include KEEP/CHANGE/DROP.
    Output: ai/board/strategies.md
```

```
Output: ai/board/strategies.md
```

### Phase 5: PRESENTATION (→ human, 80% attention)

**!!! NO AUTO-DECIDE in retrofit. Human ALWAYS chooses.**

Present strategies with:
- What stays, what changes, what gets dropped
- Migration investment vs feature investment split
- Risk of each strategy for existing users/revenue
- Concrete next steps per strategy

```
Output: ai/board/founder-feedback-R{N}.md
```

### Phase 6: ITERATE (round 2-3)

Same as Greenfield. ALL 6 directors go again with feedback.

NOT "only affected re-research" — ALL go again.

Contradiction log: each problem recorded.
Next round MUST address each item.

### Phase 7: WRITE (multi-step chain)

**Step 1: DATA CHECK** (deterministic gate)
```bash
node .claude/scripts/validate-board-data.mjs ai/board/
```
GATE: pass / fail → Phase 6

**Step 2: DRAFT** (sonnet)
Write Business Blueprint from template (see SKILL.md).
Includes RETROFIT-specific sections:
- **KEEP decisions** (existing business lines to preserve)
- **CHANGE decisions** (pivots, re-prioritization)
- **DROP decisions** (features/lines to sunset)
- **Migration priority** (which waves are business-critical)
- **Investment split** (stabilization % vs features %)

**Step 3: EDIT** (opus)
Cross-section consistency. Cross-references. Remove contradictions.

**Step 4: VALIDATE** (ai-based, haiku)
Same checks as Greenfield + additional:
- KEEP/CHANGE/DROP decisions present and justified?
- Migration priorities aligned with migration-path.md waves?
- Investment split (stabilization vs features) defined?
- No contradiction between DROP decisions and migration items?
GATE: pass / reject → Step 2

**Step 5: MIGRATION RE-PRIORITY** (optional, opus)
If Board strategy changes migration priorities:
- Re-order items within waves (NOT break dependency order)
- Flag items that are now P0 for business reasons
- Flag items that can be deferred or dropped

```
Output: ai/blueprint/business-blueprint.md
Output: ai/architect/migration-path.md (updated priorities, if Board changed them)
```

### Phase 8: REFLECT

- LOCAL: "Next Board: ask about X earlier"
- PROCESS: "Cross-critique found gap — strengthen prompt"
- META: "What did audit reveal that changed our business assumptions?"
- No UPSTREAM (Board is top level in both greenfield and retrofit)

```
Output: ai/reflect/process-improvements.md
```
