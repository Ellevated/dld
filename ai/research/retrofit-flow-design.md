# DLD Retrofit Flow — Design Specification

**Date:** 2026-02-16
**Status:** SPEC (approved for implementation)
**Context:** How DLD integrates into existing projects + lifecycle reassessment

---

## 1. Key Insight

**Retrofit is not "for someone else's code". It's a lifecycle phase for ANY project.**

Evidence: PLPilot was bootstrapped on DLD v1 (bootstrap -> spark -> autopilot) and still:
- 246 commits / 8 days, 132 tasks
- 50+ bugs + 40+ TECH tasks from bootstrap debt
- Float money found 4x (ADR written but not enforced)
- Auth inconsistencies 3x (no unified strategy)
- Bot 1,547 LOC / 0 tests (no architecture phase)
- Each bootstrap feature -> ~1.5 fixes after

**Reasons ANY project may need retrofit:**
1. **Framework evolution** -- project started on DLD v1, now v2 exists with Board/Architect
2. **Pivot** -- business direction changed, code diverges from new goal
3. **Organic growth** -- implicit decisions accumulate, conventions drift
4. **Technical progress** -- new tools/patterns make old decisions suboptimal

**Analogy:** Like a vehicle inspection. Not because the car is bad -- because any car requires periodic checks.

---

## 2. Design Decisions

Six fundamental decisions, agreed with founder:

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | Retrofit = MODE or FLOW? | **Both (C)** | Flow defines sequence, skills switch internal behavior |
| 2 | Audit depth? | **Two modes: light + deep** | Deep for retrofit, burns tokens but recovers full map |
| 3 | Separate agents per mode? | **No -- one agent, conditional logic** | PHASE detection in prompt, like existing agents |
| 4 | Architect output format? | **Blueprint = TO-BE + migration-path.md** | AS-IS is the code itself; don't document separately |
| 5 | Board output format? | **Same business-blueprint.md format** | Spark shouldn't know greenfield vs retrofit |
| 6 | New Spark mode? | **No -- Spark works from TZ** | Architect provides detailed migration plan, Spark executes |

---

## 3. Greenfield vs Brownfield: Inverted Order

```
         BROWNFIELD (retrofit)                GREENFIELD (new project)

1. Deep Audit (bottom-up)             1. Bootstrap (top-down)
   "what do we have?"                    "what do we want?"
         |                                      |
2. Architect Recovery                  2. Board
   "document code reality,                "business strategy"
    design realistic TO-BE"                      |
         |                             3. Architect
3. Board Recovery                         "system architecture"
   "business context + priorities"               |
         |                             4. Spark -> Autopilot
4. Stabilization                          "features one by one"
   "close gaps, no new features"
         |
5. Normal flow (Spark -> Autopilot)
   "now like greenfield"
```

**Why inverted:** In brownfield, code is the ONLY source of truth. You must understand what's built before making business or architecture decisions about it.

---

## 4. Deep Audit Design

### Phase 0: Codebase Inventory (Deterministic, Not LLM)

**Why:** LLM-based file discovery covers only ~70% of files (research: AST vs LLM knowledge graphs, 2025). Phase 0 guarantees 100%.

**Approach: Hybrid (two layers)**

| Layer | Tool | What | Coverage |
|-------|------|------|----------|
| 1. File inventory | Node.js (glob + fs.stat) | All files, LOC, sizes, directories | 100% guaranteed |
| 2. Symbol extraction | tree-sitter (opt-in per language) | Functions, classes, imports, exports, signatures | Depends on installed grammars |

**Dependencies (opt-in per project stack):**
```bash
npm install tree-sitter                    # core parser
npm install tree-sitter-python             # for Python projects
npm install tree-sitter-typescript         # for TS projects
# only install grammars for YOUR languages
```

**Graceful degradation:** If grammar not installed for a language → Layer 2 falls back to regex-based extraction (less precise but functional).

**Output:** `ai/audit/codebase-inventory.json`

```json
{
  "meta": {
    "project": "{name}",
    "scan_date": "{date}",
    "total_files": 87,
    "total_loc": 12450,
    "languages": {"python": 65, "javascript": 12}
  },
  "files": [
    {
      "path": "src/domains/billing/services.py",
      "language": "python",
      "loc": 245,
      "symbols": [
        {"name": "BillingService", "type": "class", "line": 15, "end_line": 134},
        {"name": "get_balance", "type": "method", "line": 25, "parent": "BillingService"}
      ],
      "imports": [{"from": "shared.result", "names": ["Result"]}],
      "exports": ["BillingService", "BillingError"]
    }
  ],
  "dependencies": {
    "src/domains/billing/services.py": ["shared/result.py", "infra/db.py"]
  },
  "stats": {
    "by_directory": {"src/domains/billing": {"files": 5, "loc": 890}},
    "largest_files": [{"path": "src/api/bot.py", "loc": 1547}],
    "no_tests": ["src/api/bot.py"]
  }
}
```

**Script:** `template/.claude/scripts/codebase-inventory.mjs`

```bash
node .claude/scripts/codebase-inventory.mjs src/ > ai/audit/codebase-inventory.json
```

**Size estimate (10K LOC):** ~50-80KB JSON, ~15-25K tokens when passed to personas.

---

### Two Modes

| Mode | Trigger | Agents | Cost | Use Case |
|------|---------|--------|------|----------|
| **Light** | `/audit`, "quick audit" | Single Explore agent | Low | Quick health check |
| **Deep** | From `/retrofit`, "deep audit" | 6 parallel + synthesizer | High (~1M tokens) | Full forensics for retrofit |

### Deep Audit: 6 Personas

Each persona reads the codebase through their own lens. All run in parallel, isolated.

| # | Persona | Lens | Output Sections |
|---|---------|------|-----------------|
| 1 | **Cartographer** | File structure, modules, dependencies, import graph | Project Stats, Architecture Map |
| 2 | **Archaeologist** | Patterns, conventions, conflicts between them | Pattern Inventory |
| 3 | **Accountant** | Tests, coverage, what's covered vs what's not | Test Coverage |
| 4 | **Geologist** | Data model, schema, migrations, types | Data Model |
| 5 | **Scout** | External integrations, APIs, SDKs, configs | External Integrations |
| 6 | **Coroner** | Tech debt, dead code, TODO/FIXME, red flags | Tech Debt Inventory, Red Flags |

### How Personas Use Inventory

Personas do NOT search for files — they receive inventory as a **checklist**.

| Persona | From inventory extracts | Deep-reads |
|---------|----------------------|------------|
| **Cartographer** | dependency graph, directory stats, module boundaries | Files at module boundaries, largest files |
| **Archaeologist** | symbol types, naming patterns, signatures | Files with conflicting patterns |
| **Accountant** | no_tests list, test vs source file coverage | Test files, untested modules |
| **Geologist** | type definitions, schema-related symbols | Migrations, type definition files |
| **Scout** | external imports, config files | API integration files, env references |
| **Coroner** | largest files, high symbol count (complexity) | Files with high complexity, TODO/FIXME via grep |

### Coverage Requirements (Anti-Corner-Cutting)

Based on research (LLM laziness quantification, forced materialization, citation-grounded analysis).

**Per persona — minimum operations (for ~10K LOC project):**

| Persona | Min Reads | Min Greps | Min Findings | Evidence Rule |
|---------|-----------|-----------|-------------|---------------|
| Cartographer | 20 files | 5 | 15 | file:line for each |
| Archaeologist | 25 files | 10 | 12 | file:line + quote |
| Accountant | 15 files | 5 | 10 | file:line + quote |
| Geologist | 15 files | 8 | 10 | file:line + quote |
| Scout | 10 files | 5 | 8 | file:line + quote |
| Coroner | 20 files | 10 | 15 | file:line + quote |

**Scaling:** For 30K+ LOC, multiply minimums by 2-2.5x.

**Quote-before-claim pattern (mandatory in all persona prompts):**
```
Before making ANY claim about the code:
1. Quote the relevant lines (exact text from Read)
2. State file:line reference
3. THEN make your claim
4. Explain how the quote supports your claim

NEVER cite from memory or training data — ONLY from files you Read in this session.
```

**Coverage verification (after all personas complete):**
```javascript
// validate-audit-coverage.mjs
// Every file from inventory must be mentioned by at least one persona
const missed = inventory.files.filter(f => !mentionedInAnyReport(f.path));
if (missed.length / inventory.files.length > 0.2) {
  return { pass: false, reason: `${missed.length} files not analyzed`, missed };
}
```

### Deep Audit Output

```
ai/audit/
  report-cartographer.md    (persona 1)
  report-archaeologist.md   (persona 2)
  report-accountant.md      (persona 3)
  report-geologist.md       (persona 4)
  report-scout.md           (persona 5)
  report-coroner.md         (persona 6)
  deep-audit-report.md      (synthesizer -- consolidated)
```

### Deep Audit Report Structure

```markdown
# Deep Audit Report

**Date:** {today}
**Project:** {project name from CLAUDE.md}
**Files scanned:** {count}
**LOC:** {total}

---

## 1. Project Stats
{LOC, files, languages, dependencies, git stats}

## 2. Architecture Map
{Modules, import graph, layers, actual vs intended structure}

## 3. Pattern Inventory
{Patterns used, where they conflict, consistency score}

## 4. Data Model
{Real schema from code/migrations, types, constraints}

## 5. Test Coverage
{What's covered, what's not, coverage gaps}

## 6. Tech Debt Inventory
{Categorized: critical/high/medium/low, rough priority}

## 7. External Integrations
{APIs, services, SDKs, how they're used}

## 8. Red Flags
{Critical problems requiring immediate attention}

---

## For Architect
{Key findings that Architect personas should focus on}
```

---

## 5. Migration Path: Key New Artifact

The ONLY truly new artifact that doesn't exist in greenfield.

**Created by:** Architect synthesizer (Phase 4)
**Consumed by:** Board (for re-prioritization) + Spark (for spec generation)

### Format

```markdown
# Migration Path: AS-IS -> TO-BE

**Created:** {date}
**Source:** Architect synthesis from deep audit
**Board priority:** {date of Board review, if done}

---

## Wave 1: Foundations (no features depend on these)

### MP-001: {Title}
**Type:** TECH | ARCH
**Priority:** P0
**Description:** {What needs to change and why}
**Current state:** {What exists now}
**Target state:** {What it should become}
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
All items done -> AS-IS converged with TO-BE -> normal flow.
```

### Rules
- **Waves = dependency order.** Wave N+1 depends on Wave N.
- **Each item = one Spark spec.** Granular enough for single autopilot cycle.
- **Board can re-prioritize** within waves but NOT break dependency order.
- **Items use MP- prefix** (Migration Path), not FTR/BUG/TECH -- different namespace.

---

## 6. Orchestrator: `/retrofit` Skill

### Phase Flow with Gates

```
/retrofit
    |
    +-- Phase 1: DEEP AUDIT
    |   |-- Phase 0: Run codebase-inventory.mjs (deterministic, 100% coverage)
    |   |     node .claude/scripts/codebase-inventory.mjs src/ > ai/audit/codebase-inventory.json
    |   |-- Dispatch 6 parallel audit agents (each receives inventory)
    |   |-- !!! WAIT FOR ALL 6 -- do NOT proceed if any still running
    |   |-- COVERAGE CHECK: node .claude/scripts/validate-audit-coverage.mjs
    |   |     FAIL (< 80% files covered) -> re-run under-covered personas
    |   |-- Dispatch audit-synthesizer (reads 6 reports + inventory)
    |   |-- !!! WAIT for synthesizer
    |   +-- EXIT GATE: deep-audit-report.md exists + has all 8 sections
    |       GATE METHOD: node .claude/scripts/validate-audit-report.mjs
    |       FAIL -> re-run failed agents
    |
    +-- Phase 2: ARCHITECT (retrofit mode)
    |   |-- ENTRY GATE: deep-audit-report.md passes structural check
    |   |-- Dispatch architect-facilitator with MODE: retrofit
    |   |-- (Facilitator runs full 8-phase Architect process internally)
    |   |-- Facilitator presents 2-3 alternatives
    |   |-- HUMAN CHOOSES architecture alternative (no auto-decide)
    |   |-- Write chain -> system-blueprint/ + migration-path.md
    |   +-- EXIT GATE: 6 blueprint files + migration-path.md exist
    |       GATE METHOD: node .claude/scripts/validate-architect-data.mjs
    |       FAIL -> re-run write chain
    |
    +-- Phase 3: BOARD (retrofit mode)
    |   |-- ENTRY GATE: system-blueprint/ passes structural check
    |   |-- Dispatch board-facilitator with MODE: retrofit
    |   |-- (Facilitator runs full 8-phase Board process internally)
    |   |-- Board may re-prioritize migration-path.md
    |   |-- HUMAN CHOOSES strategy (80% attention)
    |   |-- Write chain -> business-blueprint.md
    |   +-- EXIT GATE: business-blueprint.md exists
    |       GATE METHOD: node .claude/scripts/validate-board-data.mjs
    |       FAIL -> re-run write chain
    |
    +-- Phase 4: HUMAN REVIEW
    |   |-- Present: all blueprints + migration path + Board decisions
    |   |-- Human: approve / adjust / reject
    |   +-- EXIT GATE: explicit human approval
    |       REJECT -> back to Phase 2 or 3 with feedback
    |
    +-- Phase 5: STABILIZATION
    |   |-- For each wave in migration-path.md:
    |   |     For each item in wave:
    |   |       /spark (Blueprint-Initiated, Mode B) -> spec
    |   |       /autopilot -> execute (full pipeline, NO shortcuts)
    |   |     Wave N+1 starts ONLY when Wave N complete
    |   |-- Loop: if new problems found -> signal to Architect
    |   +-- EXIT GATE: all migration items done OR human says "enough"
    |
    +-- Phase 6: NORMAL FLOW
        +-- Blueprints in place -> Spark/Autopilot as greenfield
```

### Triggers for `/retrofit`

| Trigger | Description |
|---------|-------------|
| Explicit `/retrofit` | User triggers manually |
| "retrofit", "brownfield" | Natural language |
| Bugfix/feature ratio > 1:1 | Reflect pipeline signal |
| Major pivot | Board escalation |
| Framework upgrade (DLD v1 -> v2) | User triggers |
| `/triz` shows systemic constraint | Diagnostic signal |

---

## 7. Reliability Framework (Anti-Corner-Cutting)

### Problem: Where Claude Code Cuts Corners

| Risk | Example | Prevention |
|------|---------|------------|
| Early synthesis | 2/6 agents done, starts writing | WAIT FOR ALL rule |
| Skipping steps | "This is trivial, no tests" | "Skipping = VIOLATION" |
| Batching | 29 specs in 1 pass | One task at a time |
| Self-deciding | "Obviously option A" | No auto-decide in retrofit |

### Three Levels of Protection

**Level 1: Explicit WAIT instructions (in every prompt)**

```
!!! MANDATORY: Wait for ALL {N} agents to complete before proceeding.
DO NOT start synthesis/next phase while agents are still running.
DO NOT start synthesis after first 2-3 agents -- wait for ALL.
Violation of this rule invalidates the entire phase output.
```

Present in: Audit orchestration, Architect facilitator, Board facilitator.

**Level 2: File-based gates (deterministic)**

```bash
# After audit
node .claude/scripts/validate-audit-report.mjs ai/audit/deep-audit-report.md

# After architect
node .claude/scripts/validate-architect-data.mjs ai/architect/

# After board
node .claude/scripts/validate-board-data.mjs ai/board/
```

Scripts check: required files exist + required sections present + no empty/TBD content.
These are NOT AI judgment -- pure structural checks.

**Level 3: No auto-decide in retrofit**

In Spark greenfield, AUTO mode lets Spark choose approach for simple features.
In retrofit: **ALWAYS HUMAN.** Every architecture choice, every Board strategy, every migration path approval -- human decides.

Retrofit stakes are too high for auto-decide. One wrong architectural choice can invalidate the entire migration.

**Level 4: Inventory-based coverage verification**

Phase 0 produces deterministic file inventory. After all audit personas complete, `validate-audit-coverage.mjs` checks every file from inventory is mentioned by at least one persona. Coverage < 80% → reject, re-run under-covered personas.

**Level 5: Quote-before-claim evidence requirement**

Research (citation-grounded code comprehension, 2025) shows that requiring LLMs to quote actual code before making claims prevents hallucination in 100% of cases where mechanical verification is applied. Every persona prompt includes mandatory quote-before-claim pattern.

**Level 6: Minimum operation counts**

Each persona has enforced minimums (files read, greps done, findings produced). Validator rejects reports below thresholds. Prevents "this looks fine" without evidence.

---

## 8. Mode Detection (Spark-Level Pattern)

All three systems use the same pattern as Spark: table in SKILL.md + separate mode files.

### Architect SKILL.md Mode Detection

```markdown
## Mode Detection

Architect operates in two modes:

| Trigger | Mode | Read Next |
|---------|------|-----------|
| After /board, "design system", "system architecture" | **Greenfield** | `greenfield-mode.md` |
| From /retrofit, "retrofit", "existing project", explicit MODE: retrofit | **Retrofit** | `retrofit-mode.md` |

**Default:** Greenfield (if unclear, ask user)

## Modules

| Module | When | Content |
|--------|------|---------|
| `greenfield-mode.md` | Mode = Greenfield | Current 8-phase process (moved from SKILL.md) |
| `retrofit-mode.md` | Mode = Retrofit | Modified questions, AS-IS focus, migration path |
| `write-chain.md` | Phase 7 | Multi-step blueprint write (shared between modes) |
```

### Board SKILL.md Mode Detection

```markdown
## Mode Detection

Board operates in two modes:

| Trigger | Mode | Read Next |
|---------|------|-----------|
| After /bootstrap, "business strategy" | **Greenfield** | `greenfield-mode.md` |
| From /retrofit, "retrofit", "strategy revision", explicit MODE: retrofit | **Retrofit** | `retrofit-mode.md` |

**Default:** Greenfield (if unclear, ask user)
```

### Audit SKILL.md Mode Detection

```markdown
## Mode Detection

Audit operates in two modes:

| Trigger | Mode | Description |
|---------|------|-------------|
| "quick audit", "audit", "check code" | **Light** | Fast scan, single agent |
| From /retrofit, "deep audit", "full audit" | **Deep** | Full forensics, 6 parallel agents |

**Default:** Light
```

---

## 9. Persona Changes for Retrofit Mode

### Architect Personas: Greenfield vs Retrofit

Each persona agent has conditional logic based on PHASE passed in prompt.

| Persona | Greenfield Questions | Retrofit Questions |
|---------|---------------------|-------------------|
| **Eric (Domain)** | "What bounded contexts to design?" | "What contexts EXIST in code? Where are boundaries violated?" |
| **Martin (Data)** | "What schema to design?" | "What schema is ACTUALLY used? Where are inconsistencies?" |
| **Charity (Ops)** | "How to deploy?" | "What monitoring exists? What breaks first in prod?" |
| **Bruce (Security)** | "What's the threat model?" | "What's the CURRENT attack surface? What's exposed?" |
| **Neal (Evolution)** | "How to protect from drift?" | "Where has drift ALREADY happened? What to roll back?" |
| **Dan (DX)** | "What stack to choose?" | "Is current stack worth changing? Where's the dev pain?" |
| **Erik (LLM)** | "How to design for agents?" | "Can agents work with THIS code? What blocks them?" |
| **Fred (Devil)** | "What could go wrong?" | "What assumptions about this code are WRONG?" |

### Board Directors: Greenfield vs Retrofit

| Director | Greenfield Questions | Retrofit Questions |
|----------|---------------------|-------------------|
| **CPO** | "Who is the customer?" | "Which features are ACTUALLY used? Which are dead?" |
| **CFO** | "What's the unit economics?" | "What's the burn rate of tech debt? Cost of NOT fixing?" |
| **CMO** | "Which channels?" | "Which features drive growth? Which are vanity?" |
| **COO** | "What's the operating model?" | "What processes are broken? Agent/human mismatch?" |
| **CTO** | "What tech constraints?" | "Is current stack sustainable? Migration cost vs rewrite?" |
| **Devil** | "What does nobody agree with?" | "What if we just rewrite from scratch? (extreme option)" |

---

## 10. Tool Permissions (Pattern B: Agents Write Own Files)

### Design Decision

**Pattern B:** Each agent writes its own output file directly.

Rationale:
- SKILL.md already designed for this (`Output: ai/architect/research-domain.md`)
- Architect has 8 personas -- facilitator would bottleneck if relaying all
- Simpler: agent knows what to write, writes, done
- Facilitator stays lean orchestrator

**Applied uniformly to Spark, Architect, Board, Audit.**

### Write Safety Rules (in EVERY agent prompt with Write)

```
## WRITE RULES
- ONLY write to your designated output path: {specific path}
- NEVER modify files outside ai/ directory
- NEVER modify source code (src/), configs, or .claude/
- NEVER overwrite another agent's output file
```

### Complete Tool Map

#### Spark Agents

| Agent | Tools | Delta from current |
|-------|-------|--------------------|
| spark-external | Exa, Context7, Read, **Write** | +Write |
| spark-codebase | Read, Grep, Glob, Bash, **Write** | +Write |
| spark-patterns | Exa, Read, **Write** | +Write |
| spark-devil | Read, Grep, Glob, **Write** | +Write |
| spark-facilitator | Task, Read, Write, Grep | No change |

#### Architect Agents

| Agent | Tools | Delta from current |
|-------|-------|--------------------|
| 7 personas + devil | Read, Grep, Glob, Exa, **Write** | +Write |
| facilitator | **Task**, Read, **Write**, **Grep**, **Glob** | +Task, Write, Grep, Glob |
| synthesizer | Read, **Write** | +Write |

#### Board Agents

| Agent | Tools | Delta from current |
|-------|-------|--------------------|
| 5 directors + devil | Read, Exa, **Write** | +Write |
| facilitator | **Task**, Read, **Write**, **Grep**, **Glob** | +Task, Write, Grep, Glob |
| synthesizer | Read, **Write** | +Write |

#### Audit Agents (NEW)

| Agent | Tools | Why Bash |
|-------|-------|---------|
| cartographer | Read, Grep, Glob, Bash, Write | Import graph, LOC counting |
| archaeologist | Read, Grep, Glob, Write | -- |
| accountant | Read, Grep, Glob, Bash, Write | Test runners, coverage tools |
| geologist | Read, Grep, Glob, Write | -- |
| scout | Read, Grep, Glob, Bash, Write | Dependency tools, env checks |
| coroner | Read, Grep, Glob, Bash, Write | Dead code analysis |
| synthesizer | Read, Write | Reads 6 reports, writes consolidated |

---

## 11. Consistency Matrix

| Question | Answer | Verified |
|----------|--------|----------|
| Architect input in retrofit? | `ai/audit/deep-audit-report.md` instead of `business-blueprint.md` | YES |
| Board input in retrofit? | `deep-audit-report.md` + `system-blueprint/` + `migration-path.md` | YES |
| Spark input from stabilization? | Each migration-path item = task (Mode B: Blueprint-Initiated) | YES -- already in feature-mode.md Phase 1 |
| Autopilot changes? | None -- same task-loop | YES |
| migration-path.md creator? | Architect synthesizer in Phase 4 | YES |
| migration-path.md re-prioritizer? | Board can reorder within waves | YES |
| Blueprint format same? | Yes -- `system-blueprint/` always TO-BE | YES |
| Spark knows about retrofit? | No -- works from blueprint/specs regardless of origin | YES |
| Human involvement? | Phase 2 (Architect choice) + Phase 3 (Board choice) + Phase 4 (review) | YES |
| Architect rounds in retrofit? | 2-3, same as greenfield | YES |
| Board rounds in retrofit? | 2-3, same as greenfield | YES |
| Validation scripts reused? | Yes -- validate-architect-data.mjs, validate-board-data.mjs already referenced | YES |
| Pattern B consistent across all? | Yes -- Spark + Architect + Board + Audit all use Pattern B | YES |

---

## 12. Implementation File Map

### New Files to Create

| # | File | Type | Description |
|---|------|------|-------------|
| 1 | `skills/retrofit/SKILL.md` | skill | Orchestrator with phase gates |
| 2 | `skills/audit/SKILL.md` | skill (update) | Add deep mode, 6 personas |
| 3 | `skills/architect/greenfield-mode.md` | mode file | Current process moved from SKILL.md |
| 4 | `skills/architect/retrofit-mode.md` | mode file | Modified questions, audit input |
| 5 | `skills/board/greenfield-mode.md` | mode file | Current process moved from SKILL.md |
| 6 | `skills/board/retrofit-mode.md` | mode file | KEEP/CHANGE/DROP, audit input |
| 7 | `agents/audit/cartographer.md` | agent | File structure, deps |
| 8 | `agents/audit/archaeologist.md` | agent | Patterns, conventions |
| 9 | `agents/audit/accountant.md` | agent | Tests, coverage |
| 10 | `agents/audit/geologist.md` | agent | Data model, schema |
| 11 | `agents/audit/scout.md` | agent | External integrations |
| 12 | `agents/audit/coroner.md` | agent | Tech debt, dead code |
| 13 | `agents/audit/synthesizer.md` | agent | Consolidated report |
| 14 | `scripts/validate-audit-report.mjs` | script | Structural gate for audit |
| 15 | `scripts/codebase-inventory.mjs` | script | Phase 0: tree-sitter + glob inventory |
| 16 | `scripts/validate-audit-coverage.mjs` | script | Coverage check: inventory vs persona reports |

### Files to Update

| # | File | Change |
|---|------|--------|
| 15 | `skills/architect/SKILL.md` | Add mode detection table, slim down (move process to mode files) |
| 16 | `skills/board/SKILL.md` | Add mode detection table, slim down |
| 17 | `agents/architect/*.md` (10 files) | +Write in frontmatter, +retrofit questions section |
| 18 | `agents/board/*.md` (8 files) | +Write in frontmatter, +retrofit questions section |
| 19 | `agents/spark/*.md` (4 scouts) | +Write in frontmatter |
| 20 | `CLAUDE.md` | +retrofit in skills table + flow diagram |
| 21 | `rules/localization.md` | +Russian triggers for /retrofit and /audit deep |

### Summary

| Category | New | Updated | Total |
|----------|-----|---------|-------|
| Skills | 1 | 2 | 3 |
| Mode files | 4 | 0 | 4 |
| Audit agents | 7 | 0 | 7 |
| Existing agents | 0 | 22 | 22 |
| Scripts | 3 | 0 | 3 |
| Config (CLAUDE.md, localization) | 0 | 2 | 2 |
| **Total** | **15** | **26** | **41** |

---

## 13. Implementation Order (Waves)

### Wave 1: Tool Permission Fixes (foundation)
- Update frontmatter of all 22 existing agents (+Write, +Task for facilitators)
- No behavior change -- just enabling correct permissions

### Wave 2: Mode Files (extract + create)
- Extract greenfield process from Architect SKILL.md -> greenfield-mode.md
- Extract greenfield process from Board SKILL.md -> greenfield-mode.md
- Create Architect retrofit-mode.md
- Create Board retrofit-mode.md
- Update SKILL.md files with mode detection tables

### Wave 3: Audit Deep Mode + Phase 0
- Create `scripts/codebase-inventory.mjs` (Phase 0: hybrid tree-sitter + glob)
- Create `scripts/validate-audit-coverage.mjs` (inventory vs persona coverage check)
- Create 7 audit agent files (with Coverage Requirements + quote-before-claim)
- Update Audit SKILL.md with deep mode + Phase 0
- Create validate-audit-report.mjs (structural gate)

### Wave 4: Retrofit Orchestrator
- Create skills/retrofit/SKILL.md
- Update CLAUDE.md + localization.md

### Wave 5: Testing
- Run each skill manually to verify mode detection
- Test audit deep mode on a real codebase
- Test architect retrofit mode with audit output
- End-to-end: /retrofit on a test project

---

## 14. Open Items (future, NOT blocking)

| Item | Priority | Notes |
|------|----------|-------|
| Auto-trigger from reflect pipeline (bugfix/feature > 1:1) | Low | Needs reflect pipeline first |
| Stabilization progress tracking UI | Low | For long migrations |
| Partial retrofit (only audit + architect, skip board) | Low | For pure technical cleanup |
| Retrofit -> retrofit (re-assess after stabilization) | Low | Loop detection needed |

---

## 15. Links

- **Research:** `ai/research/dld-v2-flow-architecture.md` (main v2 design doc)
- **Diagram:** `ai/diagrams/retrofit-flow.excalidraw` (visual flow)
- **PLPilot evidence:** MEMORY.md (PLPilot stats)
