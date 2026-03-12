# TECH-150: Reflect Diary Synthesis — March 2026

**Status:** done | **Priority:** P2 | **Date:** 2026-03-12

## Context
- Entries analyzed: FTR-146 Task 1 (success), FTR-146 Task 2 (problem), FTR-146 Task 3 (problem), FTR-146 Task 4 (problem)
- Corrections analyzed: 1 entry (2026-02-16, template-sync)
- Upstream signals analyzed: SIGNAL-008, SIGNAL-009, SIGNAL-010 (process learnings)
- Period: 2026-02-16 — 2026-03-12

## Findings

### Patterns Found (threshold 2+ = consider, 3+ = MUST add)

| Pattern | Frequency | Source | Action |
|---------|-----------|--------|--------|
| Shell script safety issues (SQL injection, invalid flags, set -e pitfalls) | 3 | diary Tasks 2, 3, 4 | **MUST** add shell scripting rules |
| Code review catches recurring quality bugs (DRY, bare exceptions, deprecated APIs) | 2 | diary Tasks 3, 4 | Add guardrails |
| Python wrapper > bash for DB ops | 2 | Task 1 (success with db.py), Task 3 (failure with shell) | Reinforce in rules |
| Architect process learnings (Data persona, Devil technique, DDD test) | 3 | upstream SIGNAL-008,009,010 | **MUST** add ADRs |

### Anti-Patterns Found

| Anti-Pattern | Frequency | Source | Action |
|--------------|-----------|--------|--------|
| Shell string interpolation for SQL | 2 | diary Task 3 + Exa/OWASP | Add to FORBIDDEN |
| Using deprecated Python APIs (utcnow) | 1 | diary Task 4 | Add to anti-patterns |
| Unverified CLI tool flags (jq --argi) | 1 | diary Task 2 | Add guidance |
| Bare exceptions outside hooks | 1 | diary Task 4 | Already covered (ADR-004) |

### User Preferences Found

| Preference | Frequency | Source | Action |
|------------|-----------|--------|--------|
| Parameterized SQL everywhere | 2 | Task 1 (success), Task 3 (failure) | Reinforce |

### Process Learnings (upstream signals)

| Learning | Source | Action |
|----------|--------|--------|
| Data Architect persona most impactful (ranked best by 5/7) | SIGNAL-008 | ADR-014 |
| Devil needs formal contradiction naming (Evaporating Cloud) | SIGNAL-009 | ADR-015 |
| Domain names must pass DDD linguistic test | SIGNAL-010 | ADR-016 |

## Proposed Changes

### 1. `.claude/rules/architecture.md` — New "Shell Script Safety" section

**Pattern:** 3 out of 4 diary problems were shell script issues during FTR-146 orchestrator development.
**Frequency:** 3 occurrences (MUST add threshold met)
**Exa Research:** Parameterized queries universally recommended. `set -e` has documented edge cases with pipes/subshells. jq flag compatibility varies between versions.
**Sources:**
- https://runebook.dev/en/articles/sqlite/printf/percentq (parameterized queries > interpolation)
- https://zarak.fr/devops/bash-handle-errors/ (set -e final guide, edge cases)
- http://jbrot.com/blog/dash_e_problems.html (set -e edge case in subshells)
- https://oneuptime.com/blog/post/2026-01-24-bash-set-e-error-handling/view (set -e best practices 2026)

**Add new section after "Anti-patterns (FORBIDDEN)":**
```markdown
## Shell Script Safety

| Rule | Why | Instead |
|------|-----|---------|
| NEVER interpolate variables in SQL strings | SQL injection (FTR-146 Task 3) | Python with parameterized queries (`?` placeholders) |
| Verify CLI flags against `--help` | Invalid flags + set -e = silent failures (FTR-146 Task 2) | `tool --help \| grep flag` before using |
| Prefer Python for scripts > 50 LOC | Shell is fragile, 75% failure rate in FTR-146 | Python with subprocess for shell commands |
| Use `set -euo pipefail` + test error paths | `set -e` has edge cases in pipes and subshells | Explicit `\|\| handle_error` for critical sections |
| Double-quote all variables | Word splitting, globbing bugs | `"$var"` not `$var` |
```

### 2. `.claude/rules/architecture.md` — Add to Anti-patterns table

**Add rows:**
```markdown
| Shell SQL interpolation | SQL injection, no parameterization in bash | `python3 db.py <cmd>` with `?` placeholders |
| `datetime.utcnow()` | Deprecated Python 3.12+ | `datetime.now(tz=timezone.utc)` |
```

### 3. `.claude/rules/architecture.md` — Add ADRs

**Add to ADR table:**
```markdown
| ADR-014 | Data Architect gets agenda priority in /architect | 2026-03 | Cross-critique confirmed most impactful persona (SIGNAL-008) |
| ADR-015 | Devil uses Evaporating Cloud for contradiction resolution | 2026-03 | Formal resolution > freeform critique (SIGNAL-009) |
| ADR-016 | DDD linguistic test for domain names | 2026-03 | Technical terms masquerading as domains must be rejected (SIGNAL-010) |
| ADR-017 | SQL only via Python parameterized queries | 2026-03 | Shell interpolation = SQL injection (FTR-146 Task 3) |
```

### 4. `CLAUDE.md` — Shell Script Section (NEW, ~4 lines)

**Pattern:** 3/4 diary problems were shell script issues — MUST add (threshold 3+ met)

**Add after "### Migrations — Git-First ONLY" section:**
```markdown
### Shell Scripts (scripts/vps/)
- Header: `#!/usr/bin/env bash` + `set -euo pipefail`
- SQL: ALWAYS through `python3 db.py <command>`, never shell interpolation
- Variables: quote all `"$var"`, no bare `$var`
- CLI flags: verify flag exists in tool version before using
```

## Allowed Files

| File | Change Type |
|------|-------------|
| `CLAUDE.md` | Add shell scripts section (~4 lines) |
| `.claude/rules/architecture.md` | Add Shell Script Safety section, anti-patterns, ADR-014 through ADR-017 |

## Definition of Done

- [ ] `skill-creator` applied changes
- [ ] CLAUDE.md stays under limit after changes
- [ ] `.claude/rules/architecture.md` stays under 400 LOC
- [ ] Diary entries marked as done in index.md
- [ ] .processed.log updated with entry IDs

## Integration

**What `/skill-creator` does with reflect output:**
1. Reads the reflect spec (proposed changes)
2. Applies changes to CLAUDE.md and .claude/rules/
3. Validates files stay within limits
4. Creates a commit with the integrated changes

**Next step:** Run `/skill-creator` with this spec as input.

## After Integration

Update diary entries status in index.md:
```bash
# Change all 4 FTR-146 entries from pending to done
# Append to .processed.log:
echo "FTR-146-task1" >> ai/diary/.processed.log
echo "FTR-146-task2" >> ai/diary/.processed.log
echo "FTR-146-task3" >> ai/diary/.processed.log
echo "FTR-146-task4" >> ai/diary/.processed.log
```
