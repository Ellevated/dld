# Architect — Greenfield Mode (8-Phase Protocol)

Self-contained protocol for Greenfield Mode. Extracted from SKILL.md.

---

## Purpose

Design system architecture from scratch based on business decisions.

**Input:** `ai/blueprint/business-blueprint.md` from Board
**Output:** `ai/blueprint/system-blueprint/` (6 files)

**When to use:** After `/board` completes, for new projects.

---

## FORBIDDEN ACTIONS (ADR-007/008/009/010)

```
⛔ NEVER store agent responses in orchestrator variables
⛔ NEVER pass full agent output in another agent's prompt
⛔ NEVER use TaskOutput to read agent results
⛔ NEVER read output_file paths from background agents

✅ ALL Task calls use run_in_background: true
✅ Agents WRITE their output to ai/architect/ files
✅ Agents READ peer files themselves (via Read tool)
✅ File gates (Glob) verify completion between phases
```

---

## Phase 1: BRIEF (Facilitator)

Read Business Blueprint. Extract:
- Domains implied by business ("subscriptions + billing + Telegram → 3 domains min")
- Data needs ("money → Money type, subscriptions → lifecycle states")
- Integration needs ("Telegram API, payment provider, email")
- Constraints from Board ("budget X, team Y, deadline Z")
- Open questions ("Board decided 'subscriptions' — but what type? Stripe? Internal?")

Assign each persona their focus.

```
Output: ai/architect/architecture-agenda.md
```

### Phase 2: RESEARCH (7 personas + devil, parallel, isolated, background)

Each receives:
- Business Blueprint (context)
- `architecture-agenda.md` (their focus)
- Instruction: "min 5 queries, 2 deep research"

**Do NOT see each other's conclusions.**

Dispatch 8 parallel background agents (each has its own persona file in `agents/architect/`):
```yaml
# All 8 in parallel, ALL background — each persona is a dedicated agent
Task tool:
  description: "Architect: domain research"
  subagent_type: architect-domain      # → agents/architect/domain.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents of ai/blueprint/business-blueprint.md]
    AGENDA: [Domain section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-domain.md

Task tool:
  description: "Architect: data research"
  subagent_type: architect-data        # → agents/architect/data.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Data section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-data.md

Task tool:
  description: "Architect: ops research"
  subagent_type: architect-ops         # → agents/architect/ops.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Ops section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-ops.md

Task tool:
  description: "Architect: security research"
  subagent_type: architect-security    # → agents/architect/security.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Security section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-security.md

Task tool:
  description: "Architect: evolutionary research"
  subagent_type: architect-evolutionary # → agents/architect/evolutionary.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Evolutionary section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-evolutionary.md

Task tool:
  description: "Architect: DX research"
  subagent_type: architect-dx          # → agents/architect/dx.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [DX section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-dx.md

Task tool:
  description: "Architect: LLM research"
  subagent_type: architect-llm         # → agents/architect/llm.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [LLM section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-llm.md

Task tool:
  description: "Architect: Devil research"
  subagent_type: architect-devil       # → agents/architect/devil.md
  run_in_background: true
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Devil section from architecture-agenda.md]
    OUTPUT: Write your research to ai/architect/research-devil.md
```

**⏳ FILE GATE:** Wait for ALL 8 completion notifications, then verify:
```
Glob("ai/architect/research-*.md") → must find 8 files
If < 8: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

**Anonymous label shuffling (between Phase 2 and Phase 3):**
```
Create ai/architect/anonymous/
Copy research files with shuffled random labels: peer-A.md through peer-H.md
Mapping is random each run to prevent anchoring bias
Each persona knows which label is theirs (to exclude from review)
```

```
Output: ai/architect/research-{role}.md × 8
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Each persona reads ANONYMOUS research via Read tool (NOT passed in prompt):
Labels A-H instead of names → reduces anchoring bias.

Dispatch 8 parallel background agents (same personas, Phase 2):
```yaml
# All 8 in parallel, ALL background — same personas, now reading anonymous peer research
Task tool:
  description: "Architect: domain critique"
  subagent_type: architect-domain      # → agents/architect/domain.md
  run_in_background: true
  prompt: |
    PHASE: 2 (Cross-Critique)
    Read your initial research: ai/architect/research-domain.md
    Read anonymous peer files from ai/architect/anonymous/:
    - peer-A.md through peer-G.md (7 files — your own is excluded, you are label {X})
    For each peer: agree/disagree, gaps, ranking.
    OUTPUT: Write critique to ai/architect/critique-domain.md

# ... same pattern for data, ops, security, evolutionary, dx, llm, devil
# Each receives 7 ANONYMOUS peer reports (all except their own)
# Labels A-H are randomized, NOT in role order
```

**⏳ FILE GATE:** Wait for ALL 8 completion notifications, then verify:
```
Glob("ai/architect/critique-*.md") → must find 8 files
If < 8: launch extractor subagent for missing files (caller-writes fallback, ADR-007)
```

```
Output: ai/architect/critique-{role}.md × 8
```

### Phase 4: SYNTHESIS (Synthesizer, opus, background)

Synthesizer reads all 16 files via Read tool (NOT passed in prompt):

```yaml
Task tool:
  description: "Architect: synthesis"
  subagent_type: architect-synthesizer  # → agents/architect/synthesizer.md
  run_in_background: true
  prompt: |
    Read all files:
    - ai/architect/research-*.md (8 research files)
    - ai/architect/critique-*.md (8 critique files)
    - ai/architect/architecture-agenda.md
    Build 2-3 architecture alternatives. For each: ...
    OUTPUT: Write architectures to ai/architect/architectures.md
```

**⏳ FILE GATE:** Verify `ai/architect/architectures.md` exists.
**Orchestrator reads ONLY `architectures.md`** for presenting to founder.

For each architecture:
- Domain Map + interfaces
- Data Model + types
- Tech Stack (with DX rationale)
- Cross-Cutting Rules (as CODE, not text)
- Agent Architecture (tools, context, evals)
- Ops Model (deploy, monitor, rollback)
- Risks (Devil)

If architectures conflict → Evaporating Cloud.

```
Output: ai/architect/architectures.md
```

### Phase 5: PRESENTATION (→ human, 40% attention)

Founder verifies:
- "Does this match what Board decided?"
- "Stack adequate for my team?"
- "Complexity matches appetite from Bootstrap?"

Does NOT make technical decisions — validates business alignment.

```
Output: ai/architect/founder-feedback-R{N}.md
```

### Phase 6: ITERATE (round 2-3)

ALL 8 personas go again using same ADR-compliant pattern:
- ALL Task calls use `run_in_background: true`
- Personas READ previous research + critique + feedback via Read tool
- Full Phase 2-3-4-5 cycle with file gates between each phase

Contradiction log: each conflict recorded, next round MUST address.

### Phase 7: WRITE (multi-step chain)

**Step 1: DATA CHECK** (deterministic)
```bash
node .claude/scripts/validate-architect-data.mjs ai/architect/
```
GATE: pass / fail → Phase 6

**Step 2: DRAFT** (sonnet)
System Blueprint — 6 files:
```
ai/blueprint/system-blueprint/
├── domain-map.md          — bounded contexts + interfaces
├── data-architecture.md   — schema + types + constraints
├── api-contracts.md       — endpoints + auth + errors
├── cross-cutting.md       — Money, Auth, Errors, Logging (AS CODE)
├── integration-map.md     — data flow between domains
└── agent-architecture.md  — tools, context, evals, structured outputs
```

**Step 3: EDIT** (opus)
Cross-file consistency. Cross-references. Remove contradictions.

**Step 4: LLM-READY CHECK** (LLM Architect, sonnet)
- Tool descriptions don't overlap?
- APIs described for agent without source code?
- Structured outputs defined for LLM interactions?
- Context budget realistic?
- Eval strategy defined?
GATE: pass / reject → Step 2

**Step 5: STRUCTURAL VALIDATE** (deterministic + haiku)
- Every domain from Business Blueprint covered?
- Each domain has: Data Model + API + Integration?
- Cross-cutting defined: Money, Auth, Errors?
- No TBD/TODO/later?
GATE: pass / reject → Step 2

```
Output: ai/blueprint/system-blueprint/
```

### Phase 8: REFLECT

- LOCAL: "Next Architect: Data found gap in Phase 3 — strengthen prompt"
- UPSTREAM: "Board, assumption 'one subscription type' leads to 3× billing complexity — reconsider?"
- PROCESS: "Cross-critique found Domain vs Security conflict that synthesis missed"
- META: "What questions did founder ask that weren't in agenda?"

```
Output: ai/reflect/upstream-signals.md (append signals with target=board)
```
