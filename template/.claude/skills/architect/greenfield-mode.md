# Architect — Greenfield Mode (8-Phase Protocol)

Self-contained protocol for Greenfield Mode. Extracted from SKILL.md.

---

## Purpose

Design system architecture from scratch based on business decisions.

**Input:** `ai/blueprint/business-blueprint.md` from Board
**Output:** `ai/blueprint/system-blueprint/` (6 files)

**When to use:** After `/board` completes, for new projects.

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

### Phase 2: RESEARCH (7 personas, parallel, isolated)

Each receives:
- Business Blueprint (context)
- `architecture-agenda.md` (their focus)
- Instruction: "min 5 queries, 2 deep research"

**Do NOT see each other's conclusions.**

Dispatch 7 parallel agents + devil (each has its own persona file in `agents/architect/`):
```yaml
# All 8 in parallel — each persona is a dedicated agent with full identity
Task tool:
  description: "Architect: domain research"
  subagent_type: architect-domain      # → agents/architect/domain.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents of ai/blueprint/business-blueprint.md]
    AGENDA: [Domain section from architecture-agenda.md]
    Output: ai/architect/research-domain.md

Task tool:
  description: "Architect: data research"
  subagent_type: architect-data        # → agents/architect/data.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Data section from architecture-agenda.md]
    Output: ai/architect/research-data.md

Task tool:
  description: "Architect: ops research"
  subagent_type: architect-ops         # → agents/architect/ops.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Ops section from architecture-agenda.md]
    Output: ai/architect/research-ops.md

Task tool:
  description: "Architect: security research"
  subagent_type: architect-security    # → agents/architect/security.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Security section from architecture-agenda.md]
    Output: ai/architect/research-security.md

Task tool:
  description: "Architect: evolutionary research"
  subagent_type: architect-evolutionary # → agents/architect/evolutionary.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Evolutionary section from architecture-agenda.md]
    Output: ai/architect/research-evolutionary.md

Task tool:
  description: "Architect: DX research"
  subagent_type: architect-dx          # → agents/architect/dx.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [DX section from architecture-agenda.md]
    Output: ai/architect/research-dx.md

Task tool:
  description: "Architect: LLM research"
  subagent_type: architect-llm         # → agents/architect/llm.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [LLM section from architecture-agenda.md]
    Output: ai/architect/research-llm.md

Task tool:
  description: "Architect: Devil research"
  subagent_type: architect-devil       # → agents/architect/devil.md
  prompt: |
    PHASE: 1
    BUSINESS BLUEPRINT: [contents]
    AGENDA: [Devil section from architecture-agenda.md]
    Output: ai/architect/research-devil.md
```

```
Output: ai/architect/research-{role}.md × 8
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Each persona sees ANONYMOUS research from others (labeled A-G, not by name).
Each responds: agree/disagree + gaps + ranking.

Dispatch 8 parallel agents (same personas, Phase 2):
```yaml
# All 8 in parallel — same personas, now with anonymous peer research
Task tool:
  description: "Architect: domain critique"
  subagent_type: architect-domain      # → agents/architect/domain.md
  prompt: |
    PHASE: 2
    ANONYMOUS RESEARCH:
    - Research A: [content of one peer's research]
    - Research B: [content of another peer's research]
    ... (7 anonymous peer reports, all except their own)
    Output: ai/architect/critique-domain.md

# ... same pattern for data, ops, security, evolutionary, dx, llm, devil
# Each receives 7 ANONYMOUS peer reports (all except their own)
# Labels A-G are randomized, NOT in role order
```

```
Output: ai/architect/critique-{role}.md × 8
```

### Phase 4: SYNTHESIS (Synthesizer, opus)

```yaml
Task tool:
  description: "Architect: synthesis"
  subagent_type: architect-synthesizer  # → agents/architect/synthesizer.md
  prompt: |
    Read: ai/architect/research-*.md, ai/architect/critique-*.md, architecture-agenda.md
    Build 2-3 architecture alternatives. For each: ...
    Output: ai/architect/architectures.md
```

Read 16 files (8 research + 8 critique). Build 2-3 architecture alternatives.

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

ALL 7 personas go again with previous research + critique + feedback.
Full Phase 2-3-4-5 cycle.

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
