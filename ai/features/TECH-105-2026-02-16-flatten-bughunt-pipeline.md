# Feature: [TECH-105] Flatten Bug Hunt Pipeline — Remove Orchestrator

**Status:** done | **Priority:** P1 | **Date:** 2026-02-16

## Problem

Bug Hunt pipeline has a nesting depth problem:

```
Current:  Spark (L0) → orchestrator (L1) → persona agents (L2) ← FAILS
Step 6:   Spark (L0) → solution-architects (L1)               ← WORKS
```

Claude Code Task tool is limited to ~1 level of nesting. The orchestrator at Level 1 cannot spawn subagents at Level 2. Pipeline degrades: orchestrator does analysis itself (violating its "thin delegator" design from BUG-084).

Step 6 already proves the solution: Spark launches agents directly at Level 1.

## Root Cause

The orchestrator was introduced as BUG-084 prevention — a tool-restricted agent that CANNOT skip steps because it has no Read/Write tools. In practice:
1. Task nesting limit makes it unable to delegate either
2. It degrades to doing analysis directly — the exact behavior it was designed to prevent
3. The abstraction layer costs ~$5 (Opus orchestrator context) with negative value

## Solution: Spark = Orchestrator + File Gates

**Principle:** Replace tool-restriction defense with file-gate defense.

### What changes

| Before | After |
|--------|-------|
| Orchestrator manages Steps 0-5 | Spark manages Steps 0-6 directly |
| Step-skipping prevented by tool restriction | Step-skipping prevented by file gates |
| Steps 0-5 at nesting Level 2 (broken) | ALL steps at nesting Level 1 (proven) |
| Orchestrator agent exists | Orchestrator agent DELETED |
| Two pipeline sections in bug-mode.md | One unified pipeline |

### File Gates (step-skipping prevention)

Each step produces an output that the next step requires:

```
Step 0 → writes zones.yaml        → Step 1 reads zones.yaml
Step 1 → writes findings/*.yaml   → Step 2 reads findings/
Step 2 → writes findings-summary  → Step 3 reads summary
Step 3 → writes umbrella spec     → Step 4 reads spec
Step 4 → writes validator output  → Step 5 reads validator
Step 5 → updates report           → Step 6 reads groups
```

**Between each step, Spark verifies:** `Glob({expected_path})` → file exists? → proceed : error.

This is equivalent to the "6 levels of anti-corner-cutting" from the retrofit spec (file gates, not tool gates).

### Context Flooding Prevention (ADR-008)

Step 1 launches 6×N agents in parallel. Without protection, responses flood Spark's context.

**Solution (already proven in Step 6):**
1. Launch all persona agents with `run_in_background: true`
2. Each agent returns `{task_id, output_file}` (~50 tokens)
3. Poll convention paths with Glob until all files appear
4. Spark never reads full agent responses into its context

**Context math:**
- Before: 6×N agents × ~15K tokens = 90-180K in orchestrator context
- After: 6×N × ~50 tokens = 300-600 tokens in Spark context

## New Pipeline (bug-mode.md rewrite)

```
Spark: Pre-flight → cost estimate → SESSION_DIR setup
  ↓
Step 0: Spark → scope-decomposer (Level 1) → zones.yaml
  ↓ [file gate: zones.yaml exists?]
Step 1: Spark → 6 personas × N zones (Level 1, background) → findings/
  ↓ [file gate: ≥3 findings per zone?]
Step 2: Spark → findings-collector (Level 1) → summary.yaml
  ↓ [file gate: summary.yaml exists?]
Step 3: Spark → spec-assembler (Level 1) → umbrella spec
  ↓ [file gate: spec file exists?]
Step 4: Spark → validator (Level 1) → validator-output.yaml
  ↓ [file gate: validator output exists?]
Step 5: Spark → report-updater (Level 1) → updated spec + ideas.md
  ↓ [file gate: groups available?]
Step 6: Spark → solution-architects × M (Level 1, background) → standalone specs
  ↓
Spark: Handoff → backlog → autopilot
```

All steps use the same pattern:
```
1. Verify input file gate (previous step output)
2. Launch agent(s) via Task at Level 1
3. Verify output file gate (this step's output)
4. Proceed to next step
```

## Detailed Changes

### 1. DELETE orchestrator agent

Remove both copies:
- `template/.claude/agents/bug-hunt/orchestrator.md`
- `.claude/agents/bug-hunt/orchestrator.md`

### 2. REWRITE bug-mode.md: "Execution" section

Replace the "Execution — Delegate to Orchestrator" section (lines ~170-250) with direct Spark pipeline management. Move pipeline logic from orchestrator.md into bug-mode.md as Spark instructions.

Key sections to rewrite:
- **"Execution — Delegate to Orchestrator"** → **"Execution — Direct Pipeline (Steps 0-5)"**
- **"Pipeline Steps" table** — change "Managed by" column: all steps = Spark
- **"Orchestrator Returns"** → remove (no more orchestrator)
- **"Post-Orchestrator: File Verification"** → merge into each step's file gate

Keep unchanged:
- Pre-flight (already Spark-managed)
- Step 6 (already Spark-managed)
- Handoff logic (already Spark-managed)
- Bug Hunt Report Template
- All error handling/recovery logic (move from orchestrator.md to bug-mode.md)

### 3. UPDATE bug-mode.md: Overview diagram

```
Before:
  Spark → Orchestrator → Steps 0-5 → Spark → Step 6

After:
  Spark: Steps 0-6 (all direct, Level 1)
```

### 4. MOVE recovery logic

Move error handling from orchestrator.md into bug-mode.md:
- Per-step recovery table
- Fallback extraction from output_files
- Convention path polling for background agents
- Degradation rules (min 3 of 6 personas, etc.)

### 5. SESSION_DIR setup

Currently orchestrator creates SESSION_DIR. Move to Spark:
```
SESSION_DIR = ai/.bughunt/{YYYYMMDD}-{target_basename}/
```

### 6. Convention paths (unchanged)

Agent convention paths stay the same — agents don't know who orchestrates them:

| Step | Agent | Convention Path |
|------|-------|-----------------|
| 0 | scope-decomposer | `{SESSION_DIR}/step0/zones.yaml` |
| 1 | persona agents | `{SESSION_DIR}/step1/{zone_key}-{persona_type}.yaml` |
| 2 | findings-collector | `{SESSION_DIR}/step2/findings-summary.yaml` |
| 3 | spec-assembler | `ai/features/BUG-{ID}-bughunt.md` |
| 4 | validator | `{SESSION_DIR}/step4/validator-output.yaml` |
| 5 | report-updater | updates spec + `ai/ideas.md` |

No agent changes needed — only the caller changes (orchestrator → Spark).

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] bug-mode.md — Spark skill instructions for Bug Hunt
- [x] orchestrator.md — agent being deleted (2 copies)
- [x] CLAUDE.md — mentions bughunt-orchestrator in model capabilities table

### Step 2: DOWN — what depends on?
- [x] All 12 bug-hunt agents (unchanged — they don't know about orchestrator)
- [x] completion.md — Bug Hunt handoff (unchanged)
- [x] SKILL.md — mode detection routing (unchanged)

### Step 3: BY TERM — grep entire project
| Term | Files | Action |
|------|-------|--------|
| `bughunt-orchestrator` | bug-mode.md, orchestrator.md ×2, model-capabilities.md | Remove references |
| `orchestrator` | bug-mode.md, SKILL.md | Update descriptions |
| `Delegate to Orchestrator` | bug-mode.md | Rewrite section |
| `Post-Orchestrator` | bug-mode.md | Merge into step file gates |
| `Managed by.*orchestrator` | bug-mode.md | Change to Spark |

### Verification
- [x] All found files added to Allowed Files

## Research Sources
- ADR-008: Background fan-out — proven pattern for parallel agents
- Step 6 implementation — already works with Spark-direct pattern
- Retrofit spec: file gates as anti-corner-cutting mechanism
- BUG-084: Original step-skipping incident that motivated orchestrator

## Allowed Files
1. `template/.claude/skills/spark/bug-mode.md` — rewrite pipeline to Spark-direct
2. `template/.claude/agents/bug-hunt/orchestrator.md` — DELETE
3. `.claude/agents/bug-hunt/orchestrator.md` — DELETE (root copy)
4. `.claude/skills/spark/bug-mode.md` — sync from template
5. `template/.claude/rules/model-capabilities.md` — remove orchestrator from effort table
6. `.claude/rules/model-capabilities.md` — sync from template

## Definition of Done
- [ ] orchestrator.md deleted (both copies)
- [ ] bug-mode.md rewritten: Spark manages Steps 0-6 directly
- [ ] File gates between each step (Glob verification)
- [ ] Step 1 uses `run_in_background: true` (context flooding prevention)
- [ ] Recovery logic moved from orchestrator.md to bug-mode.md
- [ ] Convention paths unchanged (agents unaffected)
- [ ] model-capabilities.md updated (remove orchestrator row)
- [ ] Overview diagram updated
- [ ] `grep -r "bughunt-orchestrator" template/` returns 0 results
- [ ] Manual test: run Bug Hunt on small target, verify all 6 steps execute at Level 1
