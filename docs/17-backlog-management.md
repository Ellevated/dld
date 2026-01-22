# Backlog Management

How to manage tasks for LLM-driven development.

---

## File Structure

```
ai/
├── backlog.md          # Active tasks (single table)
├── features/           # Feature specs
│   ├── FTR-001-*.md
│   ├── BUG-002-*.md
│   └── ...
├── ideas.md            # Future ideas (no commitment)
└── archive/            # Completed specs (optional)
```

---

## Backlog Structure (STRICT)

```markdown
# Backlog

## Очередь

| ID | Задача | Status | Priority | Feature.md |
|----|--------|--------|----------|------------|
| FTR-001 | Add user auth | done | P1 | [FTR-001](features/FTR-001-*.md) |
| BUG-002 | Fix login crash | queued | P0 | [BUG-002](features/BUG-002-*.md) |

---

## Статусы
- draft — спека пишется
- queued — готова к выполнению
- in_progress — в работе
- blocked — нужен человек
- done — завершено

---

## Архив
Completed tasks moved to `ai/archive/`

---

## Ideas
See `ai/ideas.md`
```

### Rules:

1. **ONE table only** — LLM gets confused with multiple tables
2. **No sub-sections** — No "## Bugs", "## Features" groupings
3. **New tasks → end of table** — Always append, never insert

---

## ID Protocol (MANDATORY)

Before creating any spec, determine the next ID:

### Step 1: Determine type

| Type | When |
|------|------|
| FTR | New feature |
| BUG | Bug fix |
| REFACTOR | Code refactoring |
| ARCH | Architecture decision |
| SEC | Security |
| TECH | Technical debt |

### Step 2: Find max ID

```bash
# Search backlog for existing IDs
grep -oE 'FTR-[0-9]+' ai/backlog.md | sort -t- -k2 -n | tail -1
# Output: FTR-181

# Next ID: FTR-182
```

### Step 3: Create spec file

```
ai/features/{TYPE}-{ID}-{YYYY-MM-DD}-{slug}.md
```

Example: `ai/features/FTR-182-2026-01-05-user-auth.md`

---

## Status Lifecycle

```
draft → queued → in_progress → done
                      ↓
                  blocked → resumed → in_progress
```

| Status | Who sets | Meaning |
|--------|----------|---------|
| draft | Spark | Spec being written |
| queued | Plan | Ready for autopilot |
| in_progress | Autopilot | Currently executing |
| blocked | Autopilot | Needs human |
| resumed | Human | Ready to continue |
| done | Autopilot | Completed |

---

## Sync Rule (CRITICAL)

Status must match in TWO places:

1. **Feature file:** `**Status:** queued`
2. **Backlog table:** `| FTR-001 | ... | queued | ... |`

If they differ → LLM gets confused.

---

## Adding a Task

### Spark creates:

1. Spec file in `ai/features/`
2. Backlog row with `status: draft`

```markdown
| FTR-182 | Add user auth | draft | P1 | [FTR-182](features/FTR-182-2026-01-05-user-auth.md) |
```

### Plan updates:

- Status: `draft → queued`
- In BOTH places (spec file + backlog)

### Autopilot updates:

- Status: `queued → in_progress → done`
- In BOTH places

---

## Priority Levels

| Priority | Meaning | Autopilot behavior |
|----------|---------|-------------------|
| P0 | Critical | Pick first |
| P1 | High | Pick after P0 |
| P2 | Medium | Pick after P1 |
| P3 | Low | Pick last |

Autopilot picks tasks in priority order, then by position in table.

---

## Archiving

When backlog grows too large (>50 items):

```bash
# Create archive folder
mkdir -p ai/archive/features

# Move done specs
mv ai/features/*-done-*.md ai/archive/features/

# Or archive old specs by date
find ai/features -name "*.md" -mtime +30 -exec mv {} ai/archive/features/ \;
```

Update backlog:
- Remove done rows older than 30 days
- Add note: "Archived specs in `ai/archive/`"

---

## Ideas vs Backlog

| File | Purpose | Commitment |
|------|---------|------------|
| `backlog.md` | Active tasks with specs | Yes |
| `ideas.md` | Future possibilities | No |

Ideas format:

```markdown
# Ideas

## Feature Ideas
- [ ] Dark mode support
- [ ] Export to PDF
- [ ] Mobile app

## Technical Improvements
- [ ] Switch to PostgreSQL
- [ ] Add Redis caching

## Research
- [ ] Evaluate GraphQL
```

When idea becomes real → create spec via Spark → add to backlog.

---

## LLM Instructions

Add to CLAUDE.md:

```markdown
## Backlog

- Single table in `ai/backlog.md`
- New tasks → append to end
- Status sync: feature file + backlog row
- ID protocol: find max, add +1
```

Add to Spark SKILL.md:

```markdown
## Pre-Completion Checklist

1. [ ] ID determined by protocol
2. [ ] Spec file created
3. [ ] Backlog row added with status=draft
4. [ ] Both places have same status
```
