---
name: claude-md-writer
description: Write and optimize CLAUDE.md, rules, agent prompts, and skill prompts
---

# Claude MD Writer — System Documentation & Prompt Optimization

Applies changes to all system documentation: CLAUDE.md, rules, agent prompts, skill prompts.

**Activation:** `/claude-md-writer`

## Scope

| Target | Path | Limits |
|--------|------|--------|
| Foundation | `CLAUDE.md` | < 200 lines (loads every request) |
| Rules | `.claude/rules/*.md` | < 500 lines, `paths:` frontmatter |
| Agent prompts | `.claude/agents/*.md` | Concise, principle-based |
| Skill prompts | `.claude/skills/*/SKILL.md` | Action-oriented, minimal |

## Documentation Hierarchy

```
1. CLAUDE.md          — always loaded, universal rules only
2. .claude/rules/     — conditional (paths: frontmatter), domain-specific
3. .claude/agents/    — loaded per Task tool dispatch
4. .claude/skills/    — loaded per Skill tool invocation
5. Co-located (src/)  — loaded when reading nearby code
```

## 3-Tier System

### Tier 1: CLAUDE.md (< 200 lines, always loaded)
Stack, commands, architecture overview, critical rules, forbidden patterns.
NOT: code style (use linter), domain logic (use rules/), implementation details.

### Tier 2: Rules (.claude/rules/, conditional)
```yaml
---
paths:
  - "src/domains/billing/**"
---
```
Loads only when working with matching files. Organize by domain.

### Tier 3: Co-located (next to code)
`src/auth/AUTH.md` — loaded when reading nearby code.

## What Belongs Where

| Content | Location |
|---------|----------|
| Universal rules, commands | `CLAUDE.md` |
| Domain-specific logic | `.claude/rules/{domain}.md` |
| Agent execution behavior | `.claude/agents/{name}.md` |
| User-facing skill flow | `.claude/skills/{name}/SKILL.md` |
| Code style | Linter config (NOT docs) |

## Three-Expert Optimization Gate

When writing or editing ANY system documentation, apply:

### Karpathy (Remove redundancy)
- Does Claude already know this? (e.g., "use Edit tool to edit files" — obvious)
- Would removing this line make output worse? If no — remove.
- Telling HOW to think vs WHAT to achieve? Prefer WHAT.

### Sutskever (Unlock capability)
- Constraining instead of guiding? Principles > rigid procedures.
- Fighting the model's strengths? (e.g., rigid templates when free-form is better)
- Examples beat descriptions.

### Murati (Simplify UX)
- Can steps be eliminated or parallelized?
- Is the input/output format minimal?
- Does the user wait where they could get results immediately?

**Deletion test:** For every line — "If I remove this, will output get worse?" If no — remove.

## Prompt Quality Principles

- **Front-load** critical context — LLM attention is front-weighted
- **Principles > procedures** — "Be concise" beats 10 length rules
- **Show > tell** — one example beats a paragraph of description
- **Negative space** — "don't do X" only when counterintuitive
- **Trust the model** — don't explain what it already knows
- **Verify counts** — never count manually, use `wc -l` / `grep -c`

## Anti-Patterns

| Don't | Do |
|-------|-----|
| Duplicate across files | Single source of truth |
| Code style in docs | Linter config |
| Overspecify agent steps | Principles + examples |
| Count manually | `wc -l`, `grep -c` |
| > 200 lines CLAUDE.md | Split to rules/ |

## Process

1. Read input — spec from `/reflect` or direct request
2. Read current state of each target file
3. Apply Three-Expert Gate to each change
4. Apply changes — verify limits (line counts, no duplication)
5. Report what was changed

## Quality Checklist

- [ ] CLAUDE.md < 200 lines
- [ ] Rules files < 500 lines with `paths:` frontmatter
- [ ] Agent prompts: concise, principle-based, no redundancy
- [ ] Skill prompts: clear activation, focused process
- [ ] Critical content front-loaded (top 20 lines)
- [ ] No duplication across files

## Output

```yaml
status: complete
changes:
  - file: {path}
    action: {added|updated|removed}
    summary: {what changed}
```
