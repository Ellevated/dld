# Board — Greenfield Mode (8-Phase Protocol)

Self-contained protocol for Greenfield Mode. Extracted from SKILL.md.

---

## Purpose

Define business architecture from scratch for a new project.

**Input:** `ai/idea/*` from Bootstrap
**Output:** `ai/blueprint/business-blueprint.md`

**When to use:** After `/bootstrap` completes, for new projects.

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

## Phase 1: BRIEF (Facilitator)

Read `ai/idea/*` from Bootstrap. Form agenda from `open-questions.md`.
Assign each director their focus area.

```
Output: ai/board/board-agenda.md
```

### Phase 2: RESEARCH (6 directors, parallel, isolated, background)

Each director receives:
- `ai/idea/*` (shared context)
- `board-agenda.md` (their focus)
- Instruction: "min 5 search queries, of which 2 deep research"

**Each director does NOT see others' conclusions.**

Dispatch 6 parallel background agents (each has its own persona file in `agents/board/`):
```yaml
# All 6 in parallel, ALL background — each director is a dedicated agent
Task tool:
  description: "Board: CPO research"
  subagent_type: board-cpo          # → agents/board/cpo.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CPO section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-cpo.md

Task tool:
  description: "Board: CFO research"
  subagent_type: board-cfo          # → agents/board/cfo.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CFO section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-cfo.md

Task tool:
  description: "Board: CMO research"
  subagent_type: board-cmo          # → agents/board/cmo.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CMO section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-cmo.md

Task tool:
  description: "Board: COO research"
  subagent_type: board-coo          # → agents/board/coo.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [COO section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-coo.md

Task tool:
  description: "Board: CTO research"
  subagent_type: board-cto          # → agents/board/cto.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [CTO section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-cto.md

Task tool:
  description: "Board: Devil research"
  subagent_type: board-devil        # → agents/board/devil.md
  run_in_background: true
  prompt: |
    PHASE: 1
    CONTEXT: [contents of ai/idea/*]
    AGENDA: [Devil section from board-agenda.md]
    OUTPUT: Write your research to ai/board/research-devil.md
```

**⏳ FILE GATE:** Wait for ALL 6 completion notifications, then verify:
```
Glob("ai/board/research-*.md") → must find 6 files
If < 6: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

**Anonymous label shuffling (between Phase 2 and Phase 3):**
```
Create ai/board/anonymous/
Copy research files with shuffled random labels: peer-A.md through peer-F.md
Mapping is random each run to prevent anchoring bias
Each director knows which label is theirs (to exclude from review)
```

```
Output: ai/board/research-{role}.md × 6
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Each director reads ANONYMOUS research via Read tool (NOT passed in prompt):
- Labels instead of names → reduces anchoring bias

Dispatch 6 parallel background agents (same personas, Phase 2):
```yaml
# All 6 in parallel, ALL background — same directors, now reading anonymous peer research
Task tool:
  description: "Board: CPO critique"
  subagent_type: board-cpo          # → agents/board/cpo.md
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial research: ai/board/research-cpo.md
    Read anonymous peer files from ai/board/anonymous/:
    - peer-A.md through peer-E.md (5 files — your own is excluded, you are label {X})
    For each peer: agree/disagree, gaps, ranking.
    OUTPUT: Write critique to ai/board/critique-cpo.md

# ... same pattern for cfo, cmo, coo, cto, devil
# Each receives 5 ANONYMOUS peer reports (all except their own)
# Labels A-F are randomized, NOT in role order
```

**⏳ FILE GATE:** Wait for ALL 6 completion notifications, then verify:
```
Glob("ai/board/critique-*.md") → must find 6 files
If < 6: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

```
Output: ai/board/critique-{role}.md × 6
```

### Phase 4: SYNTHESIS (Synthesizer, opus, background)

Synthesizer reads all 12 files via Read tool (NOT passed in prompt):

```yaml
Task tool:
  description: "Board: synthesis"
  subagent_type: board-synthesizer  # → agents/board/synthesizer.md
  run_in_background: true
  prompt: |
    Read all files:
    - ai/board/research-*.md (6 research files)
    - ai/board/critique-*.md (6 critique files)
    - ai/board/board-agenda.md
    Build 2-3 strategy alternatives. For each: ...
    OUTPUT: Write strategies to ai/board/strategies.md
```

**⏳ FILE GATE:** Verify `ai/board/strategies.md` exists.
**Orchestrator reads ONLY `strategies.md`** for presenting to founder.

For each strategy — detailed structure:
- Core idea + rationale (with citations from research)
- Channels (CMO), Unit Economics (CFO), Org Model (COO)
- Risks (Devil), Tech considerations (CTO), UX (CPO)
- If strategies conflict → Evaporating Cloud

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

ALL 6 directors go again using same ADR-compliant pattern:
- ALL Task calls use `run_in_background: true`
- Directors READ previous research + critique + founder feedback via Read tool
- Research AGAIN with new data (min 5 queries)
- Cross-critique repeats with anonymous file reads
- Synthesis again (background, reads files)
- File gates between each phase

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
