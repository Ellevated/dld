# Agent Roles: Roles in DLD v3.0

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         SPARK                                       │
│   Idea → Socratic Dialogue → Research (Exa/Context7) → Spec        │
└─────────────────────────────────────────────────────────────────────┘
                              ↓ auto-handoff
┌─────────────────────────────────────────────────────────────────────┐
│                        AUTOPILOT                                    │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 0: Worktree + CI check + baseline                      │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 1: PLAN SUBAGENT (ultrathink → detailed tasks)         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 2: FOR EACH TASK (fresh subagent per task!)            │  │
│  │                                                              │  │
│  │   CODER → TESTER → DOCUMENTER → TWO-STAGE REVIEW → COMMIT   │  │
│  │              ↓ fail                         ↓ needs_refactor │  │
│  │          DEBUGGER ←────────────────────────────┘             │  │
│  └──────────────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │ PHASE 3: Final verify → merge → push → cleanup               │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                              ↓ stuck (3+ retries)                  │
│                          COUNCIL                                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Spark (Specification)

**Skill:** `/spark`
**Model:** Opus (deep analysis)

### What it does
1. **Socratic Dialogue** — 5-7 deep questions (one at a time)
2. **Research** — Exa (patterns, examples) + Context7 (official docs)
3. **5 Whys** — for bugs (root cause before spec)
4. **Spec** — `ai/features/TYPE-XXX.md` with Allowed Files

### Boundaries (from "Planner")

| Spark asks | Spark decides on its own |
|------------|--------------------------|
| "What problem are we solving?" | Technical approach |
| "Who is the user?" | Implementation patterns |
| "What's the minimum scope?" | API design |
| "How will we verify it works?" | Timings, retries |

### Result
```
ai/features/FTR-XXX-YYYY-MM-DD-name.md
├── Why / Context
├── Scope (in/out)
├── Allowed Files (STRICT!)
├── Approaches (with Research Sources)
├── Implementation Plan
└── Definition of Done
```

### Auto-handoff
After spec → automatically launches Autopilot (no manual step).

---

## Plan Subagent (Detailing)

**Type:** Subagent in Autopilot
**Model:** Opus + ultrathink

### When it activates
If spec doesn't contain `## Detailed Implementation Plan`.

### What it does
1. **Ultrathink** — deep analysis of spec + codebase
2. **Decomposition** — breaks down into atomic tasks
3. **Acceptance criteria** — for each task
4. **Execution order** — dependencies between tasks

### Result
Adds to spec:
```markdown
## Detailed Implementation Plan

### Task 1: Create model
Type: code | Files: create src/domains/X/models.py | Acceptance: ...

### Task 2: Add repository
Type: code | Files: create src/domains/X/repository.py | Acceptance: ...

### Execution Order
1 → 2 → 3
```

---

## Coder (Implementation)

**Type:** Fresh subagent per task
**Model:** Sonnet (90% capability, 2x speed)

### What it does
1. Reads task from the plan
2. **Checks Allowed Files** — file not in list = STOP
3. Uses Research Sources from spec
4. Writes code + tests
5. Returns `files_changed`

### Key points
- **Fresh context** — each task = new subagent
- **No gold plating** — only what's in spec
- **Allowlist enforcement** — not in list = blocked

### LLM-Friendly Gates
- ≤400 LOC per file (600 for tests)
- ≤5 exports in `__init__.py`
- Import direction: `shared ← infra ← domains ← api`

---

## Tester (Verification)

**Type:** Fresh subagent per task
**Model:** Sonnet

### Smart Testing
Doesn't run everything — selects based on `files_changed`:

| Changed file | Tests to run |
|--------------|--------------|
| `src/domains/seller/prompts/*` | `./test llm -k seller` |
| `src/domains/buyer/*` | `pytest tests/test_buyer_*.py -n auto` |
| `src/infra/db/*` | `./test fast` |

### Scope Protection
```
TEST FAILED
  │
  ├─ Related to files_changed?
  │   └─ YES → DEBUGGER → fix
  │
  └─ NOT related?
      └─ DON'T FIX! Log: "⚠️ Out-of-scope: test_X. SKIPPED."
```

Doesn't fix others' bugs — only what it broke.

---

## Debugger (Root Cause)

**Type:** Fresh subagent (called on fail)
**Model:** Opus (deep analysis)

### When it activates
Tester fails + in-scope failure.

### What it does
1. Analyzes traceback
2. 4-phase debugging: Reproduce → Isolate → Root Cause → Hypothesis
3. Returns `fix_hypothesis` + `affected_files`

### Limits
- Max 3 debug loops per task
- After 3 → Council escalation

---

## Two-Stage Review

### Stage 1: Spec Reviewer
**Model:** Sonnet

**Question:** "Does the code match the spec EXACTLY?"

| Result | Action |
|--------|--------|
| `approved` | → Stage 2 |
| `needs_implementation` | → CODER adds |
| `needs_removal` | → CODER removes excess |

### Stage 2: Code Quality Reviewer
**Model:** Opus
**Skill:** `/review`

**Question:** "Architecture, duplication, quality?"

| Result | Action |
|--------|--------|
| `approved` | → COMMIT |
| `needs_refactor` | → CODER fix → re-review (max 2) |

### Commit Gate
```
⛔ NO COMMIT without BOTH reviewers approved!

Only path:
  SPEC REVIEWER: approved
    → CODE QUALITY REVIEWER: approved
      → COMMIT
```

---

## Documenter

**Type:** Runs in main context
**Model:** Sonnet

### What it does
1. Checks — do docs need updating?
2. Updates: README, ARCHITECTURE.md, ADR
3. Writes Autopilot Log in spec

### When it skips
- Files `.claude/*`, `*.md` — no tests, no docs needed

---

## Council (Escalation)

**Skill:** `/council`
**Model:** Opus (5 experts)

### When it activates
- Debug loop > 3
- Refactor loop > 2
- Architecture decision needed

### Composition
| Expert | Focus |
|--------|-------|
| Product Manager | UX, user journey, edge cases |
| Architect | DRY, SSOT, dependencies |
| Pragmatist | YAGNI, complexity, feasibility |
| Security | OWASP, attack surfaces |
| **Synthesizer** | Final decision |

### Returns
```yaml
decision: solution_found | architecture_change | needs_human
solution: "..."
fix_steps: [...]
```

---

## Model Routing (Cost Optimization)

| Agent | Model | Rationale |
|-------|-------|-----------|
| Spark | Opus | Deep analysis, architecture |
| Plan | Opus + ultrathink | Task decomposition |
| Coder | Sonnet | 90% capability, 2x speed |
| Tester | Sonnet | Running tests, parsing |
| Debugger | Opus | Root cause analysis |
| Spec Reviewer | Sonnet | Spec matching |
| Code Quality Reviewer | Opus | Architecture review |
| Documenter | Sonnet | Routine updates |
| Council | Opus | Complex decisions |

**Savings:** Sonnet for routine → 50%+ cost reduction.

---

## Summary: Mapping concept → implementation

| Concept (original) | DLD v3.0 Implementation |
|--------------------|-------------------------|
| Planner | **Spark** + **Plan Subagent** |
| Developer | **Coder** (fresh per task) |
| Tester | **Tester** + Smart Testing + Scope Protection |
| Supervisor | **Autopilot orchestrator** + **Two-Stage Review** |
| Anti-looping | **Debug/Refactor limits** → **Council escalation** |

---

**Back:** [01-double-loop.md](01-double-loop.md) — the two loops concept
**To practice:** [../00-bootstrap.md](../00-bootstrap.md) — how to start a project
