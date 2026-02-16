# Board — Greenfield Mode (8-Phase Protocol)

Self-contained protocol for Greenfield Mode. Extracted from SKILL.md.

---

## Purpose

Define business architecture from scratch for a new project.

**Input:** `ai/idea/*` from Bootstrap
**Output:** `ai/blueprint/business-blueprint.md`

**When to use:** After `/bootstrap` completes, for new projects.

---

## Phase 1: BRIEF (Facilitator)

Read `ai/idea/*` from Bootstrap. Form agenda from `open-questions.md`.
Assign each director their focus area.

```
Output: ai/board/board-agenda.md
```

### Phase 2: RESEARCH (6 directors, parallel, isolated)

Each director receives:
- `ai/idea/*` (shared context)
- `board-agenda.md` (their focus)
- Instruction: "min 5 search queries, of which 2 deep research"

**Each director does NOT see others' conclusions.**

Dispatch 6 parallel agents (each has its own persona file in `agents/board/`):
```yaml
# All 6 in parallel — each director is a dedicated agent with full persona
Task tool:
  description: "Board: CPO research"
  subagent_type: board-cpo          # → agents/board/cpo.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CPO section from board-agenda.md]
    Output file: ai/board/research-cpo.md

Task tool:
  description: "Board: CFO research"
  subagent_type: board-cfo          # → agents/board/cfo.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CFO section from board-agenda.md]
    Output file: ai/board/research-cfo.md

Task tool:
  description: "Board: CMO research"
  subagent_type: board-cmo          # → agents/board/cmo.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CMO section from board-agenda.md]
    Output file: ai/board/research-cmo.md

Task tool:
  description: "Board: COO research"
  subagent_type: board-coo          # → agents/board/coo.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [COO section from board-agenda.md]
    Output file: ai/board/research-coo.md

Task tool:
  description: "Board: CTO research"
  subagent_type: board-cto          # → agents/board/cto.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CTO section from board-agenda.md]
    Output file: ai/board/research-cto.md

Task tool:
  description: "Board: Devil research"
  subagent_type: board-devil        # → agents/board/devil.md
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [Devil section from board-agenda.md]
    Output file: ai/board/research-devil.md
```

```
Output: ai/board/research-{role}.md × 6
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Each director sees ANONYMOUS research from others:
- "Research A: [content]" (NOT "CFO said...")
- Labels instead of names → reduces anchoring bias

Dispatch 6 parallel agents (same personas, Phase 2):
```yaml
# All 6 in parallel — same directors, now with anonymous peer research
Task tool:
  description: "Board: CPO critique"
  subagent_type: board-cpo          # → agents/board/cpo.md
  prompt: |
    PHASE: 2
    ANONYMOUS RESEARCH:
    - Research A: [content of research-cfo.md]
    - Research B: [content of research-cmo.md]
    - Research C: [content of research-coo.md]
    - Research D: [content of research-cto.md]
    - Research E: [content of research-devil.md]
    Output: ai/board/critique-cpo.md

# ... same pattern for cfo, cmo, coo, cto, devil
# Each receives 5 ANONYMOUS peer reports (all except their own)
# Labels A-E are randomized, NOT in role order
```

```
Output: ai/board/critique-{role}.md × 6
```

### Phase 4: SYNTHESIS (Synthesizer, opus)

Read all 12 files (6 research + 6 critique). Build 2-3 strategy alternatives.

For each strategy — detailed structure:
- Core idea + rationale (with citations from research)
- Channels (CMO), Unit Economics (CFO), Org Model (COO)
- Risks (Devil), Tech considerations (CTO), UX (CPO)
- If strategies conflict → Evaporating Cloud

```yaml
Task tool:
  description: "Board: synthesis"
  subagent_type: board-synthesizer  # → agents/board/synthesizer.md
  prompt: |
    Read: ai/board/research-*.md, ai/board/critique-*.md, board-agenda.md
    Build 2-3 strategy alternatives. For each: ...
    Output: ai/board/strategies.md
```

```
Output: ai/board/strategies.md
```

### Phase 5: PRESENTATION (→ human, 80% attention)

Show `strategies.md` to founder. Each decision has research citation.
Founder critiques: "this is good, redo this, cut this."

```
Output: ai/board/founder-feedback-R{N}.md
```

### Phase 6: ITERATE (round 2-3)

ALL 6 directors go again:
- Receive: previous research + cross-critique + founder feedback
- Research AGAIN with new data (min 5 queries)
- Cross-critique repeats on new research
- Synthesis again

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
Write Business Blueprint from template (see SKILL.md for template).

**Step 3: EDIT** (opus)
Check cross-section consistency. Add cross-references. Remove contradictions.

**Step 4: VALIDATE** (ai-based, haiku)
- Revenue model with concrete numbers?
- Each channel backed by research data?
- Org model: agent/human/hybrid for each process?
- Risks with mitigations?
- Unit economics filled?
- No empty sections, TBD, TODO?
GATE: pass / reject → Step 2

```
Output: ai/blueprint/business-blueprint.md
```

### Phase 8: REFLECT

- LOCAL: "Next Board: ask about X earlier"
- PROCESS: "Cross-critique found gap that research missed — strengthen CMO prompt"
- META: "What questions did founder ask that weren't in agenda?"
- No UPSTREAM (Board is top level, upstream = founder only)

```
Output: ai/reflect/process-improvements.md (Board is top level — no upstream, only meta)
```
