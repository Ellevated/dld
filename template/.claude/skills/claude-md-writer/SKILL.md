---
name: claude-md-writer
description: Writes and optimizes CLAUDE.md files following Anthropic 2025 best practices with 3-tier modular structure
---

# CLAUDE.md Writer — Best Practices 2025

Transforms CLAUDE.md files into token-efficient, modular documentation.

**Activation:** `claude-md-writer`, `optimize-claude-md`

## Golden Rules

| Rule | Limit | Why |
|------|-------|-----|
| CLAUDE.md | < 200 lines | Loads on EVERY request, burns tokens |
| Rules files | < 500 lines each | Conditional loading saves tokens |
| Critical first | Top 20 lines | LLM attention is front-weighted |
| No duplication | Use `@file` refs | Single source of truth |

## Memory Hierarchy (Load Priority)

```
1. Enterprise:      /Library/Application Support/ClaudeCode/CLAUDE.md
2. Project:         /path/to/project/CLAUDE.md
3. Rules (cond.):   .claude/rules/*.md (via paths: frontmatter)
4. User:            ~/.claude/CLAUDE.md
5. Local:           .claude/CLAUDE.local.md (gitignored)
```

## 3-Tier Documentation System

### Tier 1: Foundation (CLAUDE.md)
**Always loaded. < 200 lines. Universal rules only.**

Contains:
- Stack overview (1-2 lines)
- Key commands (5-10 lines)
- Architecture overview (diagram)
- Critical paths (what to load when)
- Forbidden patterns (3-5 items)

Does NOT contain:
- Code style rules (use ESLint/Prettier/Biome)
- Domain-specific logic (use rules/)
- Implementation details (use co-located docs)

### Tier 2: Component Rules (.claude/rules/)
**Conditional loading via `paths:`. < 500 lines each.**

```yaml
# .claude/rules/api-patterns.md
---
paths:
  - src/api/**
  - src/routes/**
---
# API Development Rules
...
```

Organize by domain:
- `database.md` — SQL patterns, migrations
- `testing.md` — test conventions, fixtures
- `deployment.md` — CI/CD, environments
- `{domain}.md` — domain-specific rules

### Tier 3: Feature (Co-located)
**Lives next to code. Loaded only when reading that code.**

Examples:
- `src/auth/AUTH.md` — auth-specific patterns
- `src/billing/BILLING.md` — billing logic

## Conditional Loading (paths: frontmatter)

```yaml
---
paths:
  - "src/domains/seller/**"   # exact match
  - "**/*_test.py"            # glob pattern
  - "*.sql"                   # extension match
---
```

Rules load ONLY when working with matching files.

## What Belongs Where

| Content Type | Location | Example |
|-------------|----------|---------|
| Universal rules | CLAUDE.md | "Never push to main" |
| Domain logic | .claude/rules/{domain}.md | Billing calculations |
| API patterns | .claude/rules/api.md | REST conventions |
| Test conventions | .claude/rules/testing.md | Fixture patterns |
| Deployment | .claude/rules/deploy.md | CI/CD steps |
| Feature-specific | src/{feature}/FEATURE.md | Auth flow details |
| Code style | .eslintrc / biome.json | Formatting rules |

## Anti-Patterns

| Don't | Do Instead |
|-------|------------|
| Duplicate content | `@file` reference |
| Code style in docs | ESLint/Prettier config |
| Negative-only rules | "Do X" not "Don't do Y" |
| > 200 lines CLAUDE.md | Split to rules/ |
| Inline SQL patterns | .claude/rules/database.md |
| API docs in main | .claude/rules/api.md |
| **Count manually** | Always `grep -c` / `wc -l` |

## Counting Rule (CRITICAL)

**NEVER count components manually** — always verify with commands:

```bash
# Tables
grep -c "CREATE TABLE" db/migrations/*.sql

# Tools (seller)
grep -c '"name":' src/domains/seller/tools/definitions/*.py | awk -F: '{sum+=$2} END {print sum}'

# FSM States
grep -c "= State()" src/domains/*/states.py

# Handlers (exclude tests)
ls src/domains/*/handlers/*.py | grep -v test | wc -l

# Keyboards
grep -c "def .*keyboard" src/domains/*/keyboards/*.py

# HTTP Endpoints
grep -c "@router\.\|@app\." src/api/**/*.py

# Prompt versions
ls src/domains/*/prompts/*.md | wc -l

# Lines in file
wc -l <file>
```

**Manual counting = wrong numbers = misleading docs.**

## Migration Checklist

When optimizing existing CLAUDE.md:

1. [ ] **Measure:** Count current lines
2. [ ] **Identify domain content:** SQL, API, testing, deployment
3. [ ] **Create rules files:** `.claude/rules/{domain}.md` with `paths:`
4. [ ] **Move content:** Domain → rules file
5. [ ] **Add references:** `@.claude/rules/domain.md` if needed
6. [ ] **Verify:** Main file < 200 lines
7. [ ] **Test:** Rules load only when expected

## Template: CLAUDE.md (< 200 lines)

```markdown
# CLAUDE.md
[Project name] — [1-line description]

**Stack:** [technologies]

**Commands:**
- `./test` — run tests
- `./build` — build project

---

## Architecture
[Diagram or 3-5 line overview]

## Contexts
| Task | Load |
|------|------|
| [domain1] | `.claude/rules/domain1.md` |
| [domain2] | `.claude/rules/domain2.md` |

## Key Rules
- [Critical rule 1]
- [Critical rule 2]
- [Critical rule 3]

## Forbidden
- [Anti-pattern 1]
- [Anti-pattern 2]

## Structure
[Brief project structure if needed]
```

## Template: Rules File (< 500 lines)

```markdown
---
paths:
  - "src/domains/billing/**"
  - "**/billing_*.py"
---

# Billing Rules

## Principles
...

## Patterns
...

## Examples
...
```

## Quality Checklist (Pre-Completion)

Before finishing optimization:

- [ ] CLAUDE.md < 200 lines
- [ ] Each rules file < 500 lines
- [ ] Critical content in first 20 lines
- [ ] No code style rules (use linter configs)
- [ ] No duplication (use @file refs)
- [ ] paths: frontmatter on all rules files
- [ ] Domain content moved to rules/
- [ ] Architecture diagram present
- [ ] Commands section complete

## Output

After optimization:
```yaml
status: complete
main_lines: [N] (was [M])
rules_files: [list]
tokens_saved: ~[estimate]%
```
