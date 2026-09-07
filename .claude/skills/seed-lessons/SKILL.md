---
name: seed-lessons
description: Seed ai/lessons/ from archive. Reads BUG/FTR/TECH/ARCH specs, understands what was learned, writes structured lessons. Triggers on: seed lessons, засей уроки, заполни банк уроков, populate lessons bank.
---

# Seed Lessons

Read every spec in `ai/archive/` (or `ai/features/` if no archive) — across ALL types
(BUG, FTR, TECH, ARCH) — understand what was learned, and write structured lessons
to `ai/lessons/`.

**You ARE the LLM.** Read each file with understanding — not keyword matching.

> **Why all four types (2026-05-10, upstreamed from Dowry 2026-09-07):** the first
> version ingested BUG specs only, so the bank held nothing but post-mortems. FTR
> (feature-pattern), TECH (tech-decision) and ARCH (arch-decision) capture what worked,
> which is what a planner needs before it repeats a shape that already failed elsewhere.

---

## Lesson Types

Each lesson belongs to ONE of four types, derived from the source spec prefix:

| Spec prefix | Lesson type | What it captures |
|-------------|-------------|------------------|
| `BUG-*` | `bug-fix` | What broke + how to prevent recurrence |
| `FTR-*` | `feature-pattern` | Reusable feature/UX/agent pattern that worked |
| `TECH-*` | `tech-decision` | Implementation/refactor decision worth remembering |
| `ARCH-*` | `arch-decision` | Architecture choice with trade-offs |

A spec produces ≤1 lesson. Skip specs that don't carry a transferable lesson
(pure docs updates, trivial tweaks). Mark them with `type=skip` in the index
instead of creating a file (so re-runs don't re-evaluate them).

---

## Taxonomy

Pick `class` based on lesson `type`. If nothing fits → `general`.

### `bug-fix` → `root_cause_class`

| Class | When to use |
|-------|-------------|
| `money-precision` | Wrong type/unit for money — float, rub instead of int kopecks |
| `race-condition` | Two concurrent writes hit the same row without locking |
| `ssot-violation` | Same data in two places that diverged |
| `migration-drift` | DB schema and code out of sync |
| `atomicity` | Multi-step operation left data half-written |
| `idempotency` | Retry/replay caused double write/charge |
| `boolean-trap` | bool field couldn't represent all states needed |
| `fsm-deadlock` | State machine stuck or made illegal transition |
| `cross-layer-import` | Import direction violated (domain→api, circular) |
| `pydantic-coercion` | Pydantic silently coerced wrong type |
| `case-mismatch` | snake_case vs camelCase mismatch between DB and code |
| `null-safety` | Missing None check crashed at runtime |
| `flood-wait` | TG/external API rate-limit handling missing |
| `silent-failure` | Operation reported success but did nothing |
| `prod-config-drift` | DEV behaves differently from PROD due to config |
| `general` | None of the above |

### `feature-pattern` → `pattern_class`

| Class | When to use |
|-------|-------------|
| `volume-cap` | Loops/agents need hard caps to prevent runaway cost |
| `confidence-gate` | Auto-approve only if confidence > threshold |
| `eval-driven` | Built eval set before shipping, used to gate prompts |
| `gradual-trust` | Manual review % decreases as accuracy validated |
| `safety-rails` | Hard stops, kill-switch, dry-run modes |
| `escalation-path` | Clear human handoff for blocked cases |
| `feature-flag` | Toggle to disable without redeploy |
| `agent-loop-pattern` | LLM + tools loop with budget + termination |
| `ux-flow` | User journey/dialog flow that converted well |
| `notification-design` | Push/digest pattern that drove right action |
| `general` | None of the above |

### `tech-decision` → `pattern_class`

| Class | When to use |
|-------|-------------|
| `migration-strategy` | How to ship a schema change safely |
| `observability-gap` | Added monitor/alert/SLO that caught real issue |
| `deploy-pattern` | CI/CD pattern (env separation, gating, rollback) |
| `subagent-orchestration` | Multi-agent dispatch / context isolation |
| `caching-strategy` | What to cache, where, TTL choice |
| `test-strategy` | Mock boundary, integration vs unit decision |
| `auth-pattern` | Cookie/header/JWT split for browser vs server |
| `data-pipeline` | ETL/batch/scheduler design choice |
| `error-handling-pattern` | Result/exception/retry/circuit-breaker |
| `infrastructure-choice` | Vendor/library/protocol selection |
| `general` | None of the above |

### `arch-decision` → `pattern_class`

| Class | When to use |
|-------|-------------|
| `bounded-context` | Domain boundary that paid off |
| `single-source-of-truth` | Where canonical state lives + why |
| `layered-architecture` | Import direction / responsibility split |
| `coupling-tradeoff` | Why coupling X and Y was right (or wrong) |
| `eventual-consistency` | Async/event-driven choice |
| `read-model-split` | CQRS-style read vs write model |
| `vendor-lockin` | Conscious lock-in trade-off |
| `cost-architecture` | Choice driven by unit economics |
| `team-topology` | Who owns what, code ownership |
| `general` | None of the above |

---

## Protocol

### Step 1: Find files

```bash
# Prefer archive
ls ai/archive/*.md 2>/dev/null | wc -l
# Fallback to features
ls ai/features/BUG-*.md ai/features/FTR-*.md ai/features/TECH-*.md ai/features/ARCH-*.md 2>/dev/null | wc -l
```

Report: "Found N specs in {dir} (BUG=B, FTR=F, TECH=T, ARCH=A). Starting."

### Step 2: For each spec — Read → Understand → Write

**Read the full file.** Title alone is not enough.

After reading, determine:
- **type** — derived from prefix (BUG→bug-fix, FTR→feature-pattern, TECH→tech-decision, ARCH→arch-decision)
- **domain** — billing / campaigns / buyer / seller / llm / db / security / api / storage / outreach / intelligence / publisher / content / kb / tg-pool / sales / marketing / leads / agents / general
- **class** — `root_cause_class` for bug-fix, `pattern_class` for the rest. Pick from the matching taxonomy section above.
- **rule** — one concrete actionable sentence:
  - bug-fix: prevention rule ("Use X instead of Y to prevent Z")
  - feature-pattern / tech-decision / arch-decision: lesson rule ("When facing X, do Y because Z")
- **severity** (bug-fix only) — critical / high / medium
- **impact** (non-bug only) — high (load-bearing pattern) / medium (situational) / low (niche)
- **keywords** — 3-6 specific terms from this spec (not the class name)
- **context** — 2-3 sentences: what was the situation, what was decided/fixed, what was the outcome

**Skip if no transferable lesson** — pure doc fix, trivial typo, status-only update.
Append to `ai/lessons/index.jsonl` with `{"id":"SKIP","spec":"BUG-XXX","reason":"docs-only"}`
and DO NOT create a file. This makes re-runs cheap.

**Next L-ID:**
```bash
ls ai/lessons/{domain}/ 2>/dev/null | grep -oE "L-[0-9]+" | sort -t- -k2 -n | tail -1
# Increment + zero-pad to 3 digits
```

**Write** `ai/lessons/{domain}/L-{NNN}.md`:

For `bug-fix`:
```markdown
---
id: L-{NNN}
type: bug-fix
domain: {domain}
root_cause_class: {class}
severity: {severity}
created: {YYYY-MM-DD}
occurrence_count: 1
related: [{SPEC-ID}]
---

# {root_cause_class}: {short title}

## Prevention Rule
{actionable sentence}

## Context
{2-3 sentences: what broke, why, what fixed it}

## Keywords
{term1, term2, term3}
```

For `feature-pattern` / `tech-decision` / `arch-decision`:
```markdown
---
id: L-{NNN}
type: {feature-pattern|tech-decision|arch-decision}
domain: {domain}
pattern_class: {class}
impact: {high|medium|low}
created: {YYYY-MM-DD}
occurrence_count: 1
related: [{SPEC-ID}]
---

# {pattern_class}: {short title}

## Lesson
{actionable sentence — when to apply, why it works}

## Context
{2-3 sentences: situation, decision, outcome}

## Keywords
{term1, term2, term3}
```

Create domain directory if missing.

**Append** to `ai/lessons/index.jsonl` (one line per lesson):
```json
{"id":"L-NNN","type":"...","domain":"...","class":"...","rule":"...","keywords":[...],"severity_or_impact":"...","related":["SPEC-ID"],"created":"YYYY-MM-DD","occurrence_count":1}
```

Log each lesson: `[DONE] L-001 billing/money-precision ← BUG-350`
Skipped: `[SKIP] BUG-XXX (docs-only)`

### Step 3: Deduplication

Before writing each lesson — check if `SPEC-ID` already in `index.jsonl`:
```bash
grep -c "SPEC-ID" ai/lessons/index.jsonl 2>/dev/null
```
If already present → skip with `[SKIP] SPEC-ID already indexed`.

### Step 4: Summary

```
Seeded: N lessons across M domains
By type: bug-fix(N), feature-pattern(N), tech-decision(N), arch-decision(N)
Skipped: K (already indexed) + L (no transferable lesson)
Domains: billing(N), campaigns(N), ...
```

---

## Rules

- Read the FULL spec before classifying — title is often misleading
- `rule` must be actionable: "Use X instead of Y", not "Be careful with money"
- For non-bug lessons, prefer `pattern_class` that captures the *transferable* idea, not the project-specific feature name
- Context must explain WHY (broken/decided), not just WHAT
- If archive is large (>50 files): process in batches of 20–30, commit after each batch
- For 100+ specs: parallelize via subagent classification (one JSONL row per spec) then materialize files in a single sweep
- Never overwrite existing lessons — only append
- Commit after completion: `git add ai/lessons/ && git commit -m "chore: seed lessons from archive"`
