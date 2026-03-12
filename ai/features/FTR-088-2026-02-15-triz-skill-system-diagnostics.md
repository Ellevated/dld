# Feature: [FTR-088] /triz Skill — System-Level Diagnostics with TOC + TRIZ

**Status:** queued | **Priority:** P2 | **Date:** 2026-02-15

## Problem

TOC (Theory of Constraints) and TRIZ (Theory of Inventive Problem Solving) are powerful frameworks designed for SYSTEM-level analysis. In bug-hunt they were misapplied to code-level findings — wrong abstraction level. Round 4 data: marginal +20% at 2x cost.

These frameworks need proper inputs: architecture, git history, churn metrics, co-change patterns — the level Goldratt and Altshuller designed for.

## Solution

New `/triz` skill that operates at system level. Not "analyze these 72 bugs" but "where is the system sick and why?"

## Activation

| Trigger | Skill |
|---------|-------|
| `/triz` | Direct |
| "триз", "здоровье системы", "где ограничение?" | Russian |
| "system health", "bottleneck", "where is the constraint?" | English |
| "triz analysis", "system diagnostics" | English |

## Pipeline

```
/triz [target_path] [optional: specific question]
  │
  Phase 1: DATA COLLECTION (automated, single agent)
  ├── git log --stat --since=6months → file change frequency
  ├── git log co-change analysis → files that change together
  ├── LOC per module/directory
  ├── Read architecture.md, CLAUDE.md, dependency maps
  ├── Test file coverage (test files per module)
  └── Error patterns from CI logs (if available)
  │
  Phase 2: TOC ANALYST (opus, effort=max)
  ├── Input: Phase 1 data (metrics + architecture)
  ├── Identify MODULE-level UDEs:
  │   "Module X changes 3x/week but has 0 tests"
  │   "Files A,B,C always change together (hidden coupling)"
  │   "Module Y has highest churn but lowest test coverage"
  ├── Build CRT from module-level UDEs
  ├── Find core constraint:
  │   physical: "no CI for module X"
  │   policy: "no contract tests between X and Y"
  │   paradigm: "team treats X as legacy, won't invest"
  ├── Evaporating Clouds for key architecture conflicts
  └── Exploitation/Elevation strategy
  │
  Phase 3: TRIZ ANALYST (opus, effort=max)
  ├── Input: Phase 1 data + TOC output (sequential, not parallel)
  ├── IFR: "System deploys without breaking downstream"
  ├── Technical contradictions:
  │   "Module X must change fast AND be stable for dependents"
  │   "API must evolve AND stay backward-compatible"
  ├── Physical contradictions:
  │   "Config must be centralized (SSOT) AND distributed (independence)"
  │   "Tests must be thorough (safety) AND fast (feedback loop)"
  ├── Separation principles → architecture patterns:
  │   in time → feature flags, blue-green deploy
  │   in space → API boundaries, module extraction
  │   in condition → circuit breakers, fallbacks
  │   in scale → caching layers, read replicas
  └── 40 principles → concrete architectural suggestions
  │
  Phase 4: SYNTHESIS (opus, effort=high)
  ├── Merge TOC constraint + TRIZ resolutions
  ├── Prioritize by leverage (Meadows' leverage points)
  ├── Create actionable recommendations
  └── Output: system health report
```

## Key Design Decisions

### TRIZ reads TOC output (sequential, not parallel)
Unlike bug-hunt where TOC+TRIZ ran in parallel on same data, here TRIZ runs AFTER TOC. Reason: TRIZ contradictions are more powerful when informed by TOC's constraint identification. "The constraint is coupling between X and Y" → TRIZ: "How to separate X and Y without losing consistency?"

### Data collection is automated
Phase 1 uses git commands and file reads — no LLM reasoning needed. Pure data extraction. Can be a sonnet agent or even a bash script.

### Output is strategic, not tactical
Bug-hunt outputs: "fix null check in line 42"
/triz outputs: "extract module X from monolith, add contract testing"

These are ARCHITECTURAL decisions that may feed into:
- `/spark` for creating feature specs
- `/council` for debating approach
- `/spark bug-hunt` for deep-diving into specific modules

## Interaction with Other Skills

```
/triz → "module X is the constraint, coupling with Y"
    ↓
/spark bug-hunt src/modules/X → "concrete bugs in X"
    ↓
/autopilot → fixes bugs
    ↓
/triz → "constraint shifted to Y" (progress check)
```

Strategic cycle (monthly) feeding tactical execution (daily).

## Agents Needed

### New agents (in .claude/agents/triz/)
1. `data-collector.md` — sonnet, effort=medium. Git analysis, file stats, architecture reading.
2. `toc-analyst.md` — opus, effort=max. **Adapted** from bug-hunt version. New input format: metrics instead of findings.
3. `triz-analyst.md` — opus, effort=max. **Adapted** from bug-hunt version. New input: metrics + TOC output. Sequential (reads TOC first).
4. `synthesizer.md` — opus, effort=high. Merges TOC+TRIZ into prioritized recommendations.

### Reused from bug-hunt (adapted)
- toc-analyst and triz-analyst prompts are the SAME frameworks but with different input sections and output expectations.

## Output Format

```markdown
# System Health Report: {Project Name}

**Date:** YYYY-MM-DD
**Target:** {path}
**Method:** TOC + TRIZ System Diagnostics

## System Metrics

### File Churn (last 6 months)
| Module | Changes | LOC | Tests | Churn Rate |
|--------|---------|-----|-------|------------|
| src/domains/X | 142 | 1200 | 3 | HIGH |
| src/domains/Y | 23 | 800 | 15 | LOW |

### Co-Change Clusters
- {file_a, file_b, file_c} — always change together (hidden coupling)

## TOC Analysis

### Core Constraint
{One-line constraint description}
**Type:** physical | policy | paradigm

### Current Reality Tree
{Causal chain from UDEs to root constraint}

### Evaporating Clouds
| Conflict | Hidden Assumption | Resolution |
|----------|-------------------|------------|

## TRIZ Analysis

### Ideal Final Result
"{The system ITSELF [does X] WITHOUT [cost/harm]}"

### Contradictions Found
| # | Type | Contradiction | Separation Principle | Solution |
|---|------|---------------|---------------------|----------|

### Unused Resources
{Information, time, space resources that could resolve contradictions}

## Recommendations (prioritized by leverage)

| # | Recommendation | Framework | Leverage | Effort |
|---|---------------|-----------|----------|--------|
| 1 | Extract module X behind API boundary | TRIZ: separation in space | HIGH | MEDIUM |
| 2 | Add contract testing X↔Y | TOC: exploit constraint | HIGH | LOW |
| 3 | ... | ... | ... | ... |

## Next Steps
- [ ] `/spark` spec for recommendation #1
- [ ] `/council` debate on recommendation #2
- [ ] `/spark bug-hunt src/domains/X` for tactical fixes
```

## Skill File Structure

```
.claude/skills/triz/
└── SKILL.md              — skill definition, activation, flow

.claude/agents/triz/
├── data-collector.md     — git analysis, metrics extraction
├── toc-analyst.md        — system-level TOC (adapted from bug-hunt)
├── triz-analyst.md       — system-level TRIZ (adapted, sequential after TOC)
└── synthesizer.md        — merge + prioritize recommendations
```

## Localization

Add to `.claude/rules/localization.md`:
```
| "триз", "здоровье системы", "где ограничение?", "системная диагностика" | `/triz` |
```

## Allowed Files
1. `.claude/skills/triz/SKILL.md` — new skill definition
2. `.claude/agents/triz/data-collector.md` — new agent
3. `.claude/agents/triz/toc-analyst.md` — new agent (adapted from bug-hunt)
4. `.claude/agents/triz/triz-analyst.md` — new agent (adapted from bug-hunt)
5. `.claude/agents/triz/synthesizer.md` — new agent
6. `.claude/rules/localization.md` — add Russian triggers
7. `template/.claude/skills/triz/SKILL.md` — mirror
8. `template/.claude/agents/triz/data-collector.md` — mirror
9. `template/.claude/agents/triz/toc-analyst.md` — mirror
10. `template/.claude/agents/triz/triz-analyst.md` — mirror
11. `template/.claude/agents/triz/synthesizer.md` — mirror
12. `template/.claude/rules/localization.md` — mirror (template uses example language)

## Definition of Done
- [ ] `/triz` skill activates on triggers
- [ ] Phase 1 extracts git churn, co-change, LOC, architecture data
- [ ] Phase 2 TOC analyst builds CRT from module-level UDEs
- [ ] Phase 3 TRIZ analyst finds contradictions informed by TOC output
- [ ] Phase 4 synthesizer produces prioritized recommendations
- [ ] Output is markdown report (not YAML, not backlog entries)
- [ ] Recommendations link to next steps (/spark, /council, /bug-hunt)
- [ ] Localization triggers added
- [ ] All files mirrored in template/
