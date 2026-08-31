---
paths:
  - ".claude/rules/domains/**"
domain: {name}
path: src/domains/{name}/
---

<!--
This is the placeholder every real domain rule is copied from. Its own `paths:`
keeps it out of unrelated sessions — it is only relevant while authoring domain
rules. When you copy it, REPLACE `paths:` with the globs of the domain's own
code, e.g.:

paths:
  - "src/domains/{name}/**"
  - "tests/**/{name}/**"

A rules file with no `paths:` key loads into EVERY session forever, even one
with other frontmatter keys — `domain:`/`path:` below are metadata, not
loading conditions. Four unmarked files cost AwardyBot 37k tokens per session
for 25 days before anyone noticed.
-->


# {Name} Domain

## Purpose

{1-2 sentences about what this domain does}

---

## Entities

| Entity | File:line | Description |
|--------|-----------|-------------|
| {Entity} | {file}:{line} | {description} |

---

## Public API

| Function | Signature | Description |
|----------|-----------|-------------|
| {func}() | `async def {func}(...) -> Result[T, E]` | {what it does} |

---

## Domain Patterns

- {pattern 1}
- {pattern 2}

---

## Forbidden in this Domain

- {forbidden 1}
- {forbidden 2}

---

## Glossary Reference

See `ai/glossary/{domain}.md` for terms and rules.

---

## Change History

| Date | What | Task | Who |
|------|------|------|-----|
| YYYY-MM-DD | Created domain | {TASK-ID} | spark |
