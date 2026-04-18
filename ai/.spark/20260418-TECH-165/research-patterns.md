# Pattern Research — TECH-165: Anthropic Pipeline Optimization

## Context

Three logically independent workstreams bundled under one optimization goal:
1. **SDK Upgrade** — `claude-runner.py` patch (0.1.48 → 0.1.63), ~2-3 files
2. **Model Routing** — 5 agents Opus → Sonnet + effort tuning, ~5-10 agent files
3. **Prompt Caching** — env var + system prompt cleanup + usage logging, ~5-10 files

---

## Approach A: One Spec, Three Sections

**Pattern origin:** TECH-055, TECH-065 — multi-concern specs unified by a single delivery theme.

### Description
Single `TECH-165` spec file with three `## Section` blocks, each with own tasks. Autopilot executes all tasks sequentially. One PR, one backlog row.

### Pros
- Single backlog entry — visible as one initiative, not three disconnected items
- Shared context in spec header (why we're optimizing, overall goal)
- TECH-055 precedent: 6 tasks across 4 concerns, delivered cleanly as one spec
- One autopilot session, one callback verification, one status transition

### Cons
- Rollback granularity: if SDK upgrade breaks something, you can't revert only that section without reverting the whole spec's commit history
- Larger blast radius per spec (R1 across all three domains)
- Harder to parallelize across multiple autopilot slots (one slot blocked on 12+ tasks)
- If autopilot gets blocked on section 2 (model routing), sections 1 and 3 are stranded

### Compute Cost
**Estimate:** ~$5-8 (R1: medium risk)
**Why:** 10-15 files total, single autopilot session, no parallelism possible. Blast radius is config + infra layer.

### Precedent Match
TECH-055 had 6 tasks, 4 concerns (bug fix + script + reviewer + tracking). All logically "review pipeline hardening". Tasks were sequential with explicit dependency graph inside the spec. Delivered cleanly. **This is the closest match to TECH-165.**

---

## Approach B: Three Separate Specs (TECH-165/166/167)

**Pattern origin:** FTR-146/147/148 — Orchestrator Phases 1/2/3, sequential with explicit inter-spec dependencies.

### Description
Three independent specs: TECH-165 (SDK Upgrade), TECH-166 (Model Routing), TECH-167 (Prompt Caching). Each has its own backlog entry, can be queued and executed independently.

### Pros
- Atomic rollback per concern — SDK upgrade breaks? Revert TECH-165 only
- Three autopilot slots can run in parallel (true independence at code level)
- Cleaner review surface: autopilot and reviewer focus on one concern at a time
- Risk isolated per spec: SDK upgrade is R0 (infra change), routing is R2 (config), caching is R1

### Cons
- FTR-146/147/148 precedent required genuine sequential dependency (Phase 2 needed Phase 1 infra). TECH-165/166/167 have NO code-level dependencies between them — three separate specs with no real ordering constraint feels arbitrary.
- Three backlog rows for one optimization initiative — backlog pollution, harder to track completion of the "optimization goal" as a whole
- Three autopilot sessions, three callbacks, three status verifications — overhead without proportional value for this scale
- Cognitive overhead: someone reading the backlog sees three TECH tasks without knowing they're one initiative

### Compute Cost
**Estimate:** ~$5 per spec × 3 = ~$15 total (but parallelizable to ~$5 wall-clock if all three slots used)
**Why:** Each spec is 2-5 files, independently bounded. Three separate autopilot dispatches.

### Precedent Match
FTR-146/147/148 split because Phase 2 literally couldn't start without Phase 1 infra existing. TECH-165's three workstreams have no such hard dependency — splitting them mimics the pattern without the underlying justification.

---

## Approach C: Umbrella Spec + 3 Sub-Specs

**Pattern origin:** BUG-083, BUG-084 — Bug Hunt grouped specs. Umbrella provides context, sub-specs are independently executable units.

### Description
`TECH-165.md` as a lightweight index (goal, rationale, links). Three sub-specs: `TECH-165/task-1-sdk-upgrade.md`, `TECH-165/task-2-model-routing.md`, `TECH-165/task-3-prompt-caching.md`. Each sub-spec is an independent autopilot target.

### Pros
- Preserves grouped identity (TECH-165 as an initiative)
- Independent rollback per sub-spec
- True parallelism: three autopilot slots
- Sub-spec scope constraints keep each session small

### Cons
- Bug Hunt pattern was designed for audit scenarios with many findings (29 sub-specs in BUG-084, 6 in BUG-083). Overhead justified there because findings were async-discovered. Here the scope is known upfront.
- Three sub-specs for 10-15 total files is disproportionate overhead
- Non-standard for TECH tasks: every TECH spec in history is a single flat file
- Autopilot needs to understand umbrella→sub-spec navigation, adding fragility
- Backlog needs three rows anyway (sub-specs need own entries) — same pollution as Approach B

### Compute Cost
**Estimate:** ~$20 (additional orchestration overhead: umbrella creation + 3 sub-spec scaffolding + non-standard navigation logic)
**Why:** Structural overhead disproportionate to workstream size. Bug Hunt pattern requires persona-based analysis infra that doesn't apply here.

### Precedent Match
BUG-083/084 used this for 6 and 29 findings respectively — scale justified the pattern. Three predefined workstreams do not.

---

## Comparison Matrix

| Criteria | A: One Spec | B: Three Specs | C: Umbrella+Sub |
|----------|-------------|----------------|-----------------|
| Backlog clarity | High (1 row) | Medium (3 rows) | Medium (3 rows) |
| Rollback granularity | Low | High | High |
| Autopilot parallelism | None | Full | Full |
| DLD precedent fit | Strong (TECH-055) | Weak (no real dependency) | Weak (wrong scale) |
| Spec authoring overhead | Low | Medium | High |
| Risk isolation per unit | Low (all in one) | High | High |
| Historical success rate | Proven | Untested for this case | Untested for TECH |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach A — One Spec, Three Sequential Sections

### Rationale

The deciding factor is the **DLD precedent signal**, not abstract principles. TECH-055 is the canonical reference: six tasks across four concerns (bug fix, pre-check script, reviewer enhancements, tracking template), all "review pipeline hardening". It was delivered as a single spec with a task dependency graph inside. The spec succeeded because the concerns shared a logical theme and the tasks were small enough to complete in one autopilot session.

TECH-165 has the same structure: three concerns sharing a logical theme ("Anthropic pipeline optimization"), each small enough individually (2-10 files), with no code-level interdependencies that require sequential spec delivery.

Approach B's FTR-146/147/148 precedent doesn't apply here. Those phases split because Phase 2 infra literally didn't exist until Phase 1 completed. SDK Upgrade, Model Routing, and Prompt Caching can each be implemented today without the others — splitting them creates artificial sequencing and backlog noise.

Approach C is pattern-misuse. The umbrella+sub-specs structure was designed for Bug Hunt because findings are discovered dynamically, parallelism across 6-29 items is necessary, and each finding has a different owner agent. Three predefined workstreams don't need that scaffolding.

Key factors:
1. **Precedent fit** — TECH-055 (6 tasks, 4 concerns, one spec) is the direct analog. It works.
2. **Backlog hygiene** — one optimization initiative = one backlog row. Three rows for a ~$5-8 compute task is administrative overhead without value.
3. **Rollback risk is acceptable** — each section within the spec can get its own commit (as in TECH-055 where each task had an atomic commit). Per-commit rollback works even inside one spec.

### Trade-off Accepted

We accept lower rollback granularity at the spec level (can't revert just "SDK upgrade" without looking at commit history). This is mitigated by the DLD practice of one atomic commit per task — even inside one spec, each section's tasks produce independent commits. If SDK upgrade breaks, the specific commit is reverted, not the entire spec.

We also accept no cross-slot parallelism. Given the small compute cost (~$5-8 for the full spec), the parallelism benefit of Approach B ($15 total but potentially $5 wall-clock) doesn't justify three separate specs.

### Implementation Guidance for the Spec

Structure the single TECH-165 spec with:
- Three `## Section N: {Name}` blocks, each with own `## Tasks` subsection
- Explicit execution order: Section 1 (SDK Upgrade) → Section 2 (Model Routing) → Section 3 (Prompt Caching) — order by risk, not dependency
- Each task gets an atomic commit (per DLD rule)
- `## Allowed Files` covers all three sections upfront (no surprises mid-execution)

---

## Research Sources

- `ai/features/TECH-055-2026-02-01-auto-review-agent.md` — Multi-concern single spec: 6 tasks, 4 concerns (bug fix + script + reviewer + tracking). Direct analog for TECH-165 structure.
- `ai/features/TECH-065-2026-02-02-enhanced-mcp-integration.md` — Multi-concern single spec: 6 tasks (config + script + docs + CLI + README). Confirms pattern viability for ~7 file changes.
- `ai/features/FTR-146-2026-03-10-multi-project-orchestrator-phase1.md` + FTR-147/148 — Counter-example: multi-spec split only when genuine Phase N→N+1 infra dependency exists. TECH-165's workstreams have no such dependency.
- `ai/features/BUG-083/BUG-083.md` (referenced) + BUG-084 — Umbrella+sub-specs pattern: justified only for Bug Hunt scale (6-29 findings, async discovery, multi-agent personas). Inapplicable to 3 predefined workstreams.
- `ai/backlog.md` — Confirms all historical TECH specs are flat single files. No precedent for TECH umbrella+sub-spec pattern.
