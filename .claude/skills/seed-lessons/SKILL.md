---
name: seed-lessons
description: Seed ai/lessons/ from archive. Reads every BUG spec, understands the bug, writes structured lessons. Triggers on: seed lessons, засей уроки, заполни банк уроков, populate lessons bank.
---

# Seed Lessons

Read every BUG spec from `ai/archive/` (or `ai/features/` if no archive),
understand what went wrong, and write structured lessons to `ai/lessons/`.

**You ARE the LLM.** Read each file with understanding — not keyword matching.

---

## Taxonomy (root_cause_class)

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

If nothing fits → `general`.

---

## Protocol

### Step 1: Find files

```bash
ls ai/archive/*.md 2>/dev/null | grep -i "BUG-" | wc -l
# If 0: try ai/features/
ls ai/features/*.md 2>/dev/null | grep -i "BUG-" | wc -l
```

Report: "Found N BUG files in {dir}. Starting."

### Step 2: For each BUG file — Read → Understand → Write

**Read the full file.** Title alone is not enough.

After reading, determine:
- **domain** — billing / campaigns / buyer / seller / llm / db / security / api / storage / general
- **root_cause_class** — from taxonomy above (read the WHOLE spec to decide)
- **prevention_rule** — one concrete sentence: what should be done differently. Extract from the spec's resolution/fix section if present, otherwise write from understanding.
- **severity** — critical (data loss, money, security) / high (user-facing breakage) / medium (edge case)
- **keywords** — 3-6 specific terms from this bug (not the taxonomy class name)

**Next L-ID:**
```bash
ls ai/lessons/{domain}/ 2>/dev/null | grep -oE "L-[0-9]+" | sort -t- -k2 -n | tail -1
# Increment + zero-pad to 3 digits
```

**Write** `ai/lessons/{domain}/L-{NNN}.md`:
```markdown
---
id: L-{NNN}
domain: {domain}
root_cause_class: {root_cause_class}
severity: {severity}
created: {YYYY-MM-DD}
occurrence_count: 1
related: [{BUG-ID}]
---

# {root_cause_class}: {short title from spec}

## Prevention Rule
{one concrete sentence}

## Context
{2-3 sentences: what broke, why, what fixed it}

## Keywords
{term1, term2, term3}
```

Create domain directory if missing.

**Append** to `ai/lessons/index.jsonl`:
```json
{"id":"L-NNN","domain":"...","root_cause_class":"...","prevention_rule":"...","keywords":[...],"severity":"...","related":["BUG-ID"],"created":"YYYY-MM-DD","occurrence_count":1}
```

Log each lesson: `[DONE] L-001 billing/money-precision ← BUG-350`

### Step 3: Deduplication

Before writing each lesson — check if `BUG-ID` already in `index.jsonl`:
```bash
grep -c "BUG-ID" ai/lessons/index.jsonl 2>/dev/null
```
If already present → skip with `[SKIP] BUG-ID already indexed`.

### Step 4: Summary

```
Seeded: N lessons across M domains
Skipped: K (already indexed)
Domains: billing(N), campaigns(N), ...
```

---

## Rules

- Read the FULL spec before classifying — title is often misleading
- prevention_rule must be actionable: "Use X instead of Y", not "Be careful with money"
- Context must explain WHY it broke, not just what broke
- If archive is large (>50 files): process in batches of 20, commit after each batch
- Never overwrite existing lessons — only append
- Commit after completion: `git add ai/lessons/ && git commit -m "chore: seed lessons from archive"`
