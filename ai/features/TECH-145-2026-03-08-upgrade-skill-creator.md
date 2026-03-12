# Feature: [TECH-145] Upgrade skill-writer → skill-creator (Anthropic upstream parity)
**Status:** done | **Priority:** P1 | **Date:** 2026-03-08

## Why
DLD's `skill-writer` (245 LOC, created Jan 2026) is a simple create/update tool with no quality validation. Anthropic shipped a full `skill-creator` overhaul (March 2026) with eval-driven iteration, description optimization, and benchmark analysis. ETH Zurich (arXiv:2602.11988) found unvalidated context files reduce agent success by ~3% while increasing cost >20%. Our skills need measurable quality gates, not just structural validation.

## Context
- Anthropic's upstream: `anthropics/skills/skills/skill-creator/` — 480 LOC SKILL.md + 3 agents + scripts + eval-viewer
- DLD current: `template/.claude/skills/skill-writer/SKILL.md` — 245 LOC, no eval loop
- User decisions: rename to skill-creator, full DLD-native rewrite, .mjs scripts (no Python), hybrid frontmatter
- Template-sync rule: edit template/ first, then sync to .claude/

---

## Scope
**In scope:**
- Rename skill-writer → skill-creator (all references)
- Full SKILL.md rewrite: 4-mode structure (CREATE, EVAL, UPDATE, BENCHMARK)
- 2 new agents: comparator.md, analyzer.md
- eval-judge reuse as grader (no duplicate agent)
- 3 .mjs scripts: run-eval.mjs, improve-description.mjs, aggregate-benchmark.mjs
- references/schemas.md for JSON structures
- Hybrid frontmatter: add `project-agnostic` + `allowed-tools`, keep `model`
- Progressive disclosure guidance in CREATE mode
- Description optimization with trigger testing
- Upgrade migration: add skill-writer to deprecated list

**Out of scope:**
- HTML eval viewer (markdown reports only, per DLD convention)
- Python scripts (all .mjs per DLD Node.js stack)
- package_skill (no marketplace)
- Claude.ai / Cowork specific instructions (DLD = Claude Code only)
- Changes to /eval skill (separate concern)

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- `template/.claude/skills/reflect/SKILL.md` — 10 references to "skill-writer"
- `template/.claude/skills/autopilot/SKILL.md` — 1 reference
- `template/CLAUDE.md` — Skills table entry
- `CLAUDE.md` — Skills table entry
- `scripts/smoke-test.sh` — REQUIRED_SKILLS array
- `template/scripts/smoke-test.sh` — mirror
- `docs/15-skills-setup.md` — 3 references

### Step 2: DOWN — what depends on?
- eval-judge.md agent (reuse as grader)
- eval-agents.mjs pattern (structure reference for run-eval)
- Exa MCP (research in CREATE mode)

### Step 3: BY TERM — grep entire project
- `grep -rn "skill-writer"` → 17+ occurrences across 9 files
- `grep -rn "skill.creator"` → 0 (does not exist yet)
- `grep -rn "comparator\|analyzer"` agents → 0 (new files)

### Step 4: CHECKLIST
- [x] `scripts/smoke-test.sh` — line 154 REQUIRED_SKILLS
- [x] `template/scripts/smoke-test.sh` — mirror
- [x] `.claude/scripts/upgrade.mjs` — deprecated list
- [x] `docs/15-skills-setup.md` — 3 references
- [x] `.claude/rules/localization.md` — add Russian trigger

### Verification
- After changes: `grep "skill-writer" . -r --include="*.md" --include="*.sh" --include="*.json"` = 0 results
- Smoke test passes: `./scripts/smoke-test.sh`

---

## Allowed Files
**ONLY these files may be modified during implementation:**

### Rename (modify existing)
1. `template/.claude/skills/reflect/SKILL.md` — update 10 "skill-writer" → "skill-creator" references
2. `.claude/skills/reflect/SKILL.md` — mirror
3. `template/.claude/skills/autopilot/SKILL.md` — update 1 reference
4. `.claude/skills/autopilot/SKILL.md` — mirror
5. `template/CLAUDE.md` — Skills table row
6. `CLAUDE.md` — Skills table row
7. `scripts/smoke-test.sh` — REQUIRED_SKILLS array
8. `template/scripts/smoke-test.sh` — mirror
9. `docs/15-skills-setup.md` — 3 references
10. `.claude/rules/localization.md` — add skill-creator alias

### Rewrite (delete old, create new)
11. `template/.claude/skills/skill-creator/SKILL.md` — new skill (was skill-writer)
12. `.claude/skills/skill-creator/SKILL.md` — mirror

### New agents (create)
13. `template/.claude/agents/comparator.md` — blind A/B comparison agent
14. `.claude/agents/comparator.md` — mirror
15. `template/.claude/agents/analyzer.md` — benchmark pattern analysis agent
16. `.claude/agents/analyzer.md` — mirror

### New scripts (create)
17. `template/.claude/scripts/run-eval.mjs` — run skill against test prompts
18. `.claude/scripts/run-eval.mjs` — mirror
19. `template/.claude/scripts/improve-description.mjs` — description trigger optimization
20. `.claude/scripts/improve-description.mjs` — mirror
21. `template/.claude/scripts/aggregate-benchmark.mjs` — multi-run variance analysis
22. `.claude/scripts/aggregate-benchmark.mjs` — mirror

### New references (create)
23. `template/.claude/skills/skill-creator/references/schemas.md` — JSON schemas for eval data
24. `.claude/skills/skill-creator/references/schemas.md` — mirror

### Upgrade migration (modify)
25. `.claude/scripts/upgrade.mjs` — add skill-writer to deprecated files list

**New files allowed:** 13-24 (12 new files: 2 agents × 2 copies + 3 scripts × 2 copies + 1 reference × 2 copies)

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: true
docker: false
database: false

---

## Blueprint Reference

**Domain:** DLD Framework (meta-tooling)
**Cross-cutting:** Template-sync (edit template first, then sync)
**Data model:** N/A (no data entities)

---

## Approaches

### Approach 1: Lean Rename + Eval Phase
**Source:** Devil scout Alternative 1
**Summary:** Rename + eval as new phase using eval-judge. No new agents/scripts.
**Pros:** Fastest (4-6h), zero new agents
**Cons:** No blind A/B, no iteration, no description optimizer

### Approach 2: Phased — SKILL.md + Agents Now, Scripts Later
**Source:** Patterns scout Approach 4
**Summary:** Rename + SKILL.md + 2 agents now, scripts as TECH-146
**Pros:** Ships 80% now, explicit TECH-146
**Cons:** Scripts deferred, description optimizer deferred

### Approach 3: Full DLD-Native (One Shot)
**Source:** External + Patterns Approach 2
**Summary:** Complete: rename + SKILL.md + 2 agents + 3 .mjs scripts + description optimizer + schemas
**Pros:** Complete parity. No tech debt. Description optimizer = unique value.
**Cons:** 16-20h. `claude -p` dependency for optimizer.

### Selected: 3
**Rationale:** User explicitly chose full DLD-native implementation. "Never cut corners" principle. Complete parity with Anthropic upstream, adapted to DLD idioms.

---

## Design

### 4-Mode Structure (SKILL.md)

```
skill-creator
├── CREATE mode — new skill/agent with eval-driven iteration loop
│   ├── Capture Intent (interview)
│   ├── Research (Exa + Context7)
│   ├── Write Draft (SKILL.md + agents)
│   ├── Test Cases (evals/evals.json)
│   ├── Run + Grade (eval-judge as grader)
│   ├── Compare (comparator: blind A/B)
│   ├── Analyze (analyzer: pattern surfacing)
│   ├── Improve (rewrite based on feedback)
│   └── Repeat until satisfied
├── EVAL mode — test existing skill against prompts
│   ├── Load test cases
│   ├── Spawn runs (with-skill vs baseline)
│   ├── Grade outputs
│   └── Report results (markdown)
├── UPDATE mode — optimize CLAUDE.md, rules, agents (preserved from v1)
│   ├── Preservation Checklist
│   ├── Three-Expert Gate (Karpathy/Sutskever/Murati)
│   └── Write changes
└── BENCHMARK mode — variance analysis across multiple runs
    ├── Run N iterations
    ├── Aggregate (aggregate-benchmark.mjs)
    ├── Analyze patterns
    └── Report (benchmark.md)
```

### Agent Architecture

```
skill-creator (orchestrator)
├── eval-judge (REUSE) — grader role: rubric-based scoring
├── comparator (NEW) — blind A/B comparison
└── analyzer (NEW) — benchmark pattern analysis
```

- **eval-judge** already has 5-dimension rubric scoring. For skill grading, dispatch with skill-quality rubric (structure, clarity, protection, activation, completeness).
- **comparator** receives two outputs (A/B) without knowing which is old/new. Returns winner + reasoning.
- **analyzer** reads benchmark data, surfaces patterns aggregate stats hide (always-pass assertions, high-variance evals, time/token tradeoffs).

### Script Architecture

All scripts in `.claude/scripts/` as `.mjs` (Node.js 18+ ESM):

1. **run-eval.mjs** — Takes skill path + evals.json → dispatches `claude -p` for each test prompt → captures outputs to workspace dir
2. **improve-description.mjs** — Takes skill path + 20 trigger queries → 60/40 train/test split → iterates description → validates on test set
3. **aggregate-benchmark.mjs** — Takes workspace/iteration-N → reads grading.json files → computes mean ± stddev → writes benchmark.json + benchmark.md

### Frontmatter Template (Updated)

```yaml
---
name: skill-name
description: Third-person description. Triggers on keywords: keyword1, keyword2
model: opus|sonnet|haiku          # DLD: effort routing (ADR-005)
project-agnostic: false           # NEW: true = works across any project
allowed-tools:                    # NEW: security + cost control
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Bash
---
```

### Progressive Disclosure Guidance

Skills created by skill-creator follow 3-level loading:
1. **Metadata** (~100 tokens): name + description in frontmatter — always in context
2. **Body** (<500 lines): SKILL.md instructions — loaded when skill triggers
3. **Resources** (unlimited): scripts/, references/, assets/ — loaded on demand

### Description Optimization Flow

```
1. Generate 20 trigger queries (10 positive, 5 negative, 5 edge)
2. User reviews queries via markdown table
3. Split 60% train / 40% test
4. Run improve-description.mjs:
   - Evaluate current description (3 runs per query for reliability)
   - Claude proposes improved description with extended thinking
   - Re-evaluate on train set
   - Validate on held-out test set
   - Accept if test accuracy improves
5. Max 5 iterations
6. Report before/after accuracy
```

---

## Implementation Plan

### Research Sources
- [Anthropic skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) — upstream reference for all 4 modes
- [ETH Zurich: Evaluating AGENTS.md](https://www.sri.inf.ethz.ch/publications/gloaguen2026agentsmd) — validation of eval-driven approach
- [Anthropic blind A/B comparison pattern](https://github.com/anthropics/skills/blob/main/skills/skill-creator/agents/comparator.md) — comparator agent design

### Task 1: Rename skill-writer → skill-creator (atomic)
**Type:** code
**Files:**
  - modify: `template/.claude/skills/reflect/SKILL.md` (10 refs)
  - modify: `.claude/skills/reflect/SKILL.md` (mirror)
  - modify: `template/.claude/skills/autopilot/SKILL.md` (1 ref)
  - modify: `.claude/skills/autopilot/SKILL.md` (mirror)
  - modify: `template/CLAUDE.md` (Skills table)
  - modify: `CLAUDE.md` (Skills table)
  - modify: `scripts/smoke-test.sh` (REQUIRED_SKILLS)
  - modify: `template/scripts/smoke-test.sh` (mirror)
  - modify: `docs/15-skills-setup.md` (3 refs)
  - modify: `.claude/rules/localization.md` (add trigger)
  - modify: `.claude/scripts/upgrade.mjs` (deprecated list)
  - delete: `template/.claude/skills/skill-writer/`
  - delete: `.claude/skills/skill-writer/`
**Pattern:** Find-and-replace "skill-writer" → "skill-creator" + verify grep = 0
**Acceptance:** `grep -r "skill-writer" . --include="*.md" --include="*.sh" --include="*.json" --include="*.mjs"` returns 0. `./scripts/smoke-test.sh` passes.

### Task 2: Write SKILL.md (4-mode structure)
**Type:** code
**Files:**
  - create: `template/.claude/skills/skill-creator/SKILL.md`
  - create: `.claude/skills/skill-creator/SKILL.md` (mirror)
**Pattern:** [Anthropic skill-creator SKILL.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md) adapted to DLD idioms
**Acceptance:** < 500 LOC. Has: CREATE mode with eval loop, EVAL mode, UPDATE mode with Three-Expert + Preservation Checklist, BENCHMARK mode. Frontmatter has name, description, model, project-agnostic, allowed-tools.

### Task 3: Create comparator agent
**Type:** code
**Files:**
  - create: `template/.claude/agents/comparator.md`
  - create: `.claude/agents/comparator.md` (mirror)
**Pattern:** [Anthropic comparator.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/agents/comparator.md) — blind A/B with rubric
**Acceptance:** Has frontmatter (name, description, model: sonnet, tools: Read). Blind comparison (doesn't know which is old/new). Returns winner + reasoning + rubric scores.

### Task 4: Create analyzer agent
**Type:** code
**Files:**
  - create: `template/.claude/agents/analyzer.md`
  - create: `.claude/agents/analyzer.md` (mirror)
**Pattern:** [Anthropic analyzer.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/agents/analyzer.md) — benchmark pattern analysis
**Acceptance:** Has frontmatter. Reads benchmark data. Surfaces: non-discriminating assertions, high-variance evals, time/token tradeoffs. Output: JSON array of observation strings.

### Task 5: Create references/schemas.md
**Type:** code
**Files:**
  - create: `template/.claude/skills/skill-creator/references/schemas.md`
  - create: `.claude/skills/skill-creator/references/schemas.md` (mirror)
**Pattern:** [Anthropic schemas.md](https://github.com/anthropics/skills/blob/main/skills/skill-creator/references/schemas.md) — adapted for DLD
**Acceptance:** Defines JSON schemas for: evals.json, grading.json, benchmark.json, timing.json. Each with field descriptions and examples.

### Task 6: Create run-eval.mjs script
**Type:** code
**Files:**
  - create: `template/.claude/scripts/run-eval.mjs`
  - create: `.claude/scripts/run-eval.mjs` (mirror)
**Pattern:** Port of Anthropic's run_eval.py → Node.js ESM. Uses `claude -p` subprocess.
**Acceptance:** Takes --skill-path and --evals-path. Runs each eval prompt via `claude -p`. Captures output to workspace dir. Reports pass/fail. Pre-flight: `command -v claude || exit 1`.

### Task 7: Create improve-description.mjs script
**Type:** code
**Files:**
  - create: `template/.claude/scripts/improve-description.mjs`
  - create: `.claude/scripts/improve-description.mjs` (mirror)
**Pattern:** Port of Anthropic's improve_description.py → Node.js ESM.
**Acceptance:** Takes --skill-path and --eval-set (JSON). 60/40 train/test split. Max 5 iterations. Reports accuracy before/after. Pre-flight: `command -v claude || exit 1`.

### Task 8: Create aggregate-benchmark.mjs script
**Type:** code
**Files:**
  - create: `template/.claude/scripts/aggregate-benchmark.mjs`
  - create: `.claude/scripts/aggregate-benchmark.mjs` (mirror)
**Pattern:** Port of Anthropic's aggregate_benchmark.py → Node.js ESM.
**Acceptance:** Takes workspace/iteration-N path. Reads grading.json files. Computes mean, stddev, min, max for pass_rate, time, tokens. Writes benchmark.json + benchmark.md.

### Execution Order
1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

Task 1 first (rename clears the path). Task 2 is the core SKILL.md. Tasks 3-5 are supporting files. Tasks 6-8 are scripts (can be parallel).

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User says "create a skill for X" | Task 2 (CREATE mode) | new |
| 2 | skill-creator interviews user | Task 2 (Capture Intent) | new |
| 3 | skill-creator writes SKILL.md draft | Task 2 (Write Draft) | new |
| 4 | skill-creator generates test cases | Task 2 (Test Cases) | new |
| 5 | Test runs execute (with-skill vs baseline) | Task 6 (run-eval.mjs) | new |
| 6 | Grader evaluates outputs | Task 2 (dispatches eval-judge) | existing |
| 7 | Comparator does blind A/B | Task 3 (comparator agent) | new |
| 8 | Analyzer surfaces patterns | Task 4 (analyzer agent) | new |
| 9 | User reviews results (markdown) | Task 2 (EVAL mode report) | new |
| 10 | skill-creator improves skill | Task 2 (Improve phase) | new |
| 11 | Loop repeats until satisfied | Task 2 (iteration logic) | new |
| 12 | User says "update CLAUDE.md" | Task 2 (UPDATE mode) | existing |
| 13 | Three-Expert Gate compresses | Task 2 (preserved from v1) | existing |
| 14 | User says "benchmark this skill" | Task 2 (BENCHMARK mode) | new |
| 15 | Multiple runs aggregate | Task 8 (aggregate-benchmark.mjs) | new |
| 16 | Description optimization | Task 7 (improve-description.mjs) | new |
| 17 | Smoke test validates rename | Task 1 (smoke-test.sh) | existing |
| 18 | /upgrade cleans old skill-writer | Task 1 (upgrade.mjs deprecated) | existing |

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Rename completeness | `grep -r "skill-writer"` | 0 results | deterministic | codebase scout | P0 |
| EC-2 | Smoke test passes | `./scripts/smoke-test.sh` | exit 0 | deterministic | codebase scout | P0 |
| EC-3 | SKILL.md LOC limit | `wc -l SKILL.md` | ≤ 500 | deterministic | architecture rules | P0 |
| EC-4 | Frontmatter has all fields | Parse YAML | name, description, model, project-agnostic, allowed-tools present | deterministic | user decision | P0 |
| EC-5 | Comparator agent structure | Parse comparator.md | Has frontmatter + Input + Process + Output + Rules | deterministic | agent template | P1 |
| EC-6 | Analyzer agent structure | Parse analyzer.md | Has frontmatter + Input + Process + Output + Rules | deterministic | agent template | P1 |
| EC-7 | run-eval.mjs pre-flight | Run without claude CLI | Clear error message, exit 1 | deterministic | devil scout | P1 |
| EC-8 | improve-description.mjs pre-flight | Run without claude CLI | Clear error message, exit 1 | deterministic | devil scout | P1 |
| EC-9 | Template-sync | Diff template vs root | All mirrored files identical (except DLD customizations) | deterministic | template-sync rule | P1 |

### Integration Assertions

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-10 | Skill installed | `/skill-creator create test-skill` | Interview starts, draft generated | integration | external scout | P1 |
| EC-11 | Upgrade with old skill-writer | Run `/upgrade` on project with skill-writer dir | Old dir removed, new dir present | integration | codebase scout | P2 |

### LLM-Judge Assertions

| ID | Input | Rubric | Threshold | Source | Priority |
|----|-------|--------|-----------|--------|----------|
| EC-12 | Generated SKILL.md from CREATE mode | Structure clarity, activation triggers, protective sections | 0.7 | external scout | P2 |

### Coverage Summary
- Deterministic: 9 | Integration: 2 | LLM-Judge: 1 | Total: 12 (min 3 ✓)

### TDD Order
1. EC-1 (rename grep) → EC-2 (smoke test) → EC-3 (LOC) → EC-4 (frontmatter)
2. EC-5, EC-6 (agent structure) → EC-7, EC-8 (script pre-flight)
3. EC-9 (template-sync) → EC-10 (integration) → EC-11, EC-12 (advanced)

---

## Acceptance Verification (MANDATORY)

### Smoke Checks (process alive)

| ID | Check | Command / Action | Expected | Timeout |
|----|-------|-----------------|----------|---------|
| AV-S1 | Smoke test passes | `./scripts/smoke-test.sh` | exit 0 | 30s |
| AV-S2 | No stale references | `grep -r "skill-writer" . --include="*.md" --include="*.sh" --include="*.mjs"` | 0 results | 10s |

### Functional Checks (business logic)

| ID | Check | Setup | Action | Expected |
|----|-------|-------|--------|----------|
| AV-F1 | CREATE mode activates | New session | Say "create a skill for X" | skill-creator interview starts |
| AV-F2 | UPDATE mode activates | New session | Say "update CLAUDE.md rules" | UPDATE mode with Three-Expert Gate |
| AV-F3 | run-eval.mjs runs | Mock evals.json | `node .claude/scripts/run-eval.mjs --help` | Usage output, no crash |
| AV-F4 | aggregate-benchmark.mjs runs | Mock workspace | `node .claude/scripts/aggregate-benchmark.mjs --help` | Usage output, no crash |

### Verify Command (copy-paste ready)

```bash
# Smoke
./scripts/smoke-test.sh
grep -r "skill-writer" . --include="*.md" --include="*.sh" --include="*.mjs" --include="*.json" | grep -v node_modules | grep -v .git

# Functional
node .claude/scripts/run-eval.mjs --help
node .claude/scripts/improve-description.mjs --help
node .claude/scripts/aggregate-benchmark.mjs --help
wc -l template/.claude/skills/skill-creator/SKILL.md
```

### Post-Deploy URL
```
DEPLOY_URL=local-only
```

---

## Definition of Done

### Functional
- [ ] skill-creator CREATE mode works: interview → draft → test → grade → compare → improve → repeat
- [ ] skill-creator EVAL mode works: run prompts → grade → report
- [ ] skill-creator UPDATE mode works: Three-Expert Gate + Preservation Checklist preserved
- [ ] skill-creator BENCHMARK mode works: N runs → aggregate → analyze → report
- [ ] Description optimization works: 20 queries → train/test → iterate → report
- [ ] All 4 modes documented in SKILL.md with clear activation triggers

### Tests
- [ ] All eval criteria (EC-1 through EC-12) pass
- [ ] Coverage not decreased

### Acceptance Verification
- [ ] All Smoke checks (AV-S*) pass locally
- [ ] All Functional checks (AV-F*) pass locally
- [ ] Verify Command runs without errors

### Technical
- [ ] Tests pass (`./test fast` if available)
- [ ] No regressions
- [ ] Template-sync: all mirrored files consistent
- [ ] `grep "skill-writer"` = 0 across entire repo

---

## Autopilot Log

- **2026-03-08**: Completed all 8 tasks in worktree
  - Task 1: Renamed skill-writer → skill-creator across 9 files (grep = 0)
  - Task 2: Wrote new SKILL.md (426 LOC, 4 modes: CREATE/EVAL/UPDATE/BENCHMARK)
  - Task 3: Created comparator.md agent (blind A/B, rubric scoring)
  - Task 4: Created analyzer.md agent (post-hoc + benchmark analysis)
  - Task 5: Created references/schemas.md (5 JSON schemas)
  - Task 6: Created run-eval.mjs (skill test runner via claude -p)
  - Task 7: Created improve-description.mjs (trigger accuracy optimizer)
  - Task 8: Created aggregate-benchmark.mjs (multi-run variance analysis)
  - All eval criteria (EC-1 through EC-9) passed
  - Smoke test: 9/9 passed
  - Merged to develop, pushed
