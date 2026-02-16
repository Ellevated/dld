# Architect — Retrofit Mode (8-Phase Protocol)

Self-contained protocol for Retrofit Mode. Triggered from `/retrofit` or explicit MODE: retrofit.

---

## Purpose

Recover and redesign architecture from existing code based on audit findings.

**Input:** `ai/audit/deep-audit-report.md` from Deep Audit
**Output:** `ai/blueprint/system-blueprint/` (6 files) + `ai/architect/migration-path.md`

**Key difference from Greenfield:** No business-blueprint.md constraint. Architecture is recovered from code reality (audit), not designed from business goals. Board runs AFTER Architect in brownfield flow.

---

## Phase 1: BRIEF (Facilitator)

Read Deep Audit Report. Extract:
- Architecture reality (what modules/domains actually exist vs intended)
- Data model reality (actual schema, not designed schema)
- Technical debt hotspots (critical > high > medium from Coroner report)
- Integration landscape (what's connected, what's fragile)
- Pattern conflicts (where conventions clash)
- Missing elements (what SHOULD exist but doesn't — tests, docs, monitoring)

Assign each persona their RETROFIT focus.

```
Output: ai/architect/architecture-agenda.md
```

### Phase 2: RESEARCH (7 personas, parallel, isolated)

Each receives:
- Deep Audit Report (context — what code ACTUALLY is)
- `architecture-agenda.md` (their focus)
- Instruction: "min 5 queries, 2 deep research"

**Do NOT see each other's conclusions.**

**RETROFIT QUESTIONS per persona:**

| Persona | Key Question |
|---------|-------------|
| **Eric (Domain)** | "What bounded contexts EXIST in code? Where are boundaries violated?" |
| **Martin (Data)** | "What schema is ACTUALLY used? Where are inconsistencies?" |
| **Charity (Ops)** | "What monitoring EXISTS? What breaks first in prod?" |
| **Bruce (Security)** | "What's the CURRENT attack surface? What's already exposed?" |
| **Neal (Evolution)** | "Where has drift ALREADY happened? What to roll back vs accept?" |
| **Dan (DX)** | "Is current stack worth keeping? Where's the dev pain?" |
| **Erik (LLM)** | "Can agents work with THIS code? What blocks them?" |
| **Fred (Devil)** | "What assumptions about this code are WRONG? What if we rewrite?" |

Dispatch 8 parallel agents (same agent files as greenfield, MODE: retrofit):
```yaml
# All 8 in parallel — MODE: retrofit changes the questions they ask
Task tool:
  description: "Architect: domain research (retrofit)"
  subagent_type: architect-domain      # → agents/architect/domain.md
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents of ai/audit/deep-audit-report.md]
    AGENDA: [Domain section from architecture-agenda.md]
    Output: ai/architect/research-domain.md

Task tool:
  description: "Architect: data research (retrofit)"
  subagent_type: architect-data
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents of ai/audit/deep-audit-report.md]
    AGENDA: [Data section from architecture-agenda.md]
    Output: ai/architect/research-data.md

Task tool:
  description: "Architect: ops research (retrofit)"
  subagent_type: architect-ops
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [Ops section from architecture-agenda.md]
    Output: ai/architect/research-ops.md

Task tool:
  description: "Architect: security research (retrofit)"
  subagent_type: architect-security
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [Security section from architecture-agenda.md]
    Output: ai/architect/research-security.md

Task tool:
  description: "Architect: evolutionary research (retrofit)"
  subagent_type: architect-evolutionary
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [Evolutionary section from architecture-agenda.md]
    Output: ai/architect/research-evolutionary.md

Task tool:
  description: "Architect: DX research (retrofit)"
  subagent_type: architect-dx
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [DX section from architecture-agenda.md]
    Output: ai/architect/research-dx.md

Task tool:
  description: "Architect: LLM research (retrofit)"
  subagent_type: architect-llm
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [LLM section from architecture-agenda.md]
    Output: ai/architect/research-llm.md

Task tool:
  description: "Architect: Devil research (retrofit)"
  subagent_type: architect-devil
  prompt: |
    MODE: retrofit
    PHASE: 1
    DEEP AUDIT REPORT: [contents]
    AGENDA: [Devil section from architecture-agenda.md]
    Output: ai/architect/research-devil.md
```

```
Output: ai/architect/research-{role}.md × 8
```

### Phase 3: CROSS-CRITIQUE (Karpathy Protocol)

Same as Greenfield. Each persona sees ANONYMOUS research from others (A-G).
Each responds: agree/disagree + gaps + ranking.

Dispatch 8 parallel agents (same personas, Phase 2):
```yaml
# All 8 in parallel — same personas, now with anonymous peer research
Task tool:
  description: "Architect: domain critique"
  subagent_type: architect-domain
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

Read 16 files (8 research + 8 critique). Build 2-3 architecture alternatives.

**Retrofit-specific:** Each alternative MUST include:
- Domain Map (TO-BE) + delta from current (AS-IS from audit)
- Data Model (TO-BE) + migration steps from current schema
- Tech Stack recommendation (keep / change / replace for each component)
- Cross-Cutting Rules
- Agent Architecture
- Ops Model
- Risks (Devil)
- **Migration Path outline** (waves of changes, dependency order)

If alternatives conflict → Evaporating Cloud.

```yaml
Task tool:
  description: "Architect: synthesis (retrofit)"
  subagent_type: architect-synthesizer
  prompt: |
    MODE: retrofit
    Read: ai/architect/research-*.md, ai/architect/critique-*.md, architecture-agenda.md
    Also read: ai/audit/deep-audit-report.md (for AS-IS reference)
    Build 2-3 architecture alternatives. Each MUST include migration path outline.
    Output: ai/architect/architectures.md
```

```
Output: ai/architect/architectures.md (includes migration path outlines per alternative)
```

### Phase 5: PRESENTATION (→ human, 40% attention)

**!!! NO AUTO-DECIDE in retrofit. Human ALWAYS chooses.**

Present alternatives with:
- What changes from current code (delta from AS-IS)
- Migration effort per alternative (rough estimate)
- Risk per alternative (what can go wrong during migration)
- "Path of least resistance" vs "ideal architecture"

```
Output: ai/architect/founder-feedback-R{N}.md
```

### Phase 6: ITERATE (round 2-3)

Same as Greenfield. ALL 7 personas go again with feedback.
Full Phase 2-3-4-5 cycle.

Contradiction log: each conflict recorded, next round MUST address.

### Phase 7: WRITE (multi-step chain)

**Step 1: DATA CHECK** (deterministic)
```bash
node .claude/scripts/validate-architect-data.mjs ai/architect/
```
GATE: pass / fail → Phase 6

**Step 2: DRAFT** (sonnet)
System Blueprint — 6 files (TO-BE architecture):
```
ai/blueprint/system-blueprint/
├── domain-map.md          — bounded contexts + interfaces (TO-BE)
├── data-architecture.md   — schema + types + constraints (TO-BE)
├── api-contracts.md       — endpoints + auth + errors (TO-BE)
├── cross-cutting.md       — Money, Auth, Errors, Logging (AS CODE)
├── integration-map.md     — data flow between domains (TO-BE)
└── agent-architecture.md  — tools, context, evals, structured outputs
```

**Step 3: EDIT** (opus)
Cross-file consistency. Cross-references. Remove contradictions.

**Step 4: LLM-READY CHECK** (LLM Architect, sonnet)
Same checks as Greenfield.
GATE: pass / reject → Step 2

**Step 5: STRUCTURAL VALIDATE** (deterministic + haiku)
Same checks as Greenfield + additional:
- Each domain maps to EXISTING code (audit report sections)?
- Migration complexity assessed for each domain?
GATE: pass / reject → Step 2

**Step 6: MIGRATION PATH** (opus)
Create the migration path document from chosen architecture alternative:

```
Output: ai/architect/migration-path.md
```

Format:
```markdown
# Migration Path: AS-IS → TO-BE

**Created:** {date}
**Source:** Architect synthesis from deep audit

---

## Wave 1: Foundations (no features depend on these)

### MP-001: {Title}
**Type:** TECH | ARCH
**Priority:** P0
**Description:** {What needs to change and why}
**Current state:** {From audit — what exists now}
**Target state:** {From blueprint — what it should become}
**Files likely affected:** {rough list}
**Depends on:** none
**Risk:** low | medium | high
**Effort estimate:** small | medium | large

### MP-002: {Title}
...

---

## Wave 2: Domain Boundaries (after Wave 1)

### MP-003: {Title}
**Depends on:** MP-001, MP-002
...

---

## Wave 3: API Layer (after Wave 2)
...

---

## Exit Criterion
All items done → AS-IS converged with TO-BE → normal flow.
```

**Rules for migration path:**
- Waves = dependency order. Wave N+1 depends on Wave N.
- Each item = one Spark spec. Granular enough for single autopilot cycle.
- Items use MP- prefix (Migration Path), separate from FTR/BUG/TECH.
- Board can re-prioritize within waves but NOT break dependency order.

```
Output: ai/blueprint/system-blueprint/ + ai/architect/migration-path.md
```

### Phase 8: REFLECT

Same as Greenfield + retrofit-specific signals:
- LOCAL: Lessons for next Architect session
- UPSTREAM: Signals for Board (which runs NEXT in retrofit flow)
- PROCESS: What worked / didn't in architecture recovery
- META: "What did audit reveal that we couldn't anticipate?"

Flag audit findings that need business-level discussion for Board.

```
Output: ai/reflect/upstream-signals.md (append signals with target=board)
```
