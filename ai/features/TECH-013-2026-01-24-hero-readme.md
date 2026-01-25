# TECH: [TECH-013] Hero README

**Status:** queued | **Priority:** P1 | **Date:** 2026-01-24

## Problem

Current README.md is in Russian and not optimized for open source launch.
Need a compelling English README that explains DLD value proposition quickly.

## Solution

Rewrite README.md as a "hero" landing page for the GitHub repository.

---

## Scope

**In scope:**
- Complete rewrite of README.md in English
- Hero format with badges, quick start, workflow diagram
- Links to documentation

**Out of scope:**
- Creating actual workflow images (placeholder OK)
- Detailed documentation (links to docs/)

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `README.md` | modify | Complete rewrite |

**FORBIDDEN:** All other files.

---

## Design

### README Structure

```markdown
# DLD: LLM-First Architecture

> Transform AI coding chaos into deterministic development

[badges: license, version, docs]

## The Problem

90% debugging vs 6% features — the hidden cost of AI coding.
[Brief problem statement]

## Try Before You Dive

Ask any LLM:
```
Analyze DLD methodology from github.com/xxx/dld
Compare with your current approach
```

## Quick Start (3 steps)

1. Clone template
2. Run /bootstrap
3. Run /spark for first feature

## How It Works

[Workflow diagram: Spark → Autopilot → Done]

## Key Concepts

- Skills vs Agents
- Worktree isolation
- Spec-first development

## Documentation

- [Principles](docs/01-principles.md)
- [Project Structure](docs/03-project-structure.md)
- [Skills Setup](docs/15-skills-setup.md)

## Real Results

[Links to examples or testimonials]

## Comparison

| Feature | DLD | Cursor | Claude Code |
|---------|-----|--------|-------------|
| ...     | ... | ...    | ...         |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md)

## License

MIT
```

---

## Implementation Plan

### Task 1: Write Hero README

**Files:**
- Modify: `README.md`

**Steps:**
1. Read current README
2. Write new README following structure above
3. Add badges (license, etc.)
4. Add placeholder for workflow diagram
5. Link to documentation files
6. Add comparison table

**Acceptance:**
- [ ] English only
- [ ] Clear value proposition
- [ ] Quick start works
- [ ] All links valid

---

## Definition of Done

### Functional
- [ ] README in English
- [ ] Hero format applied
- [ ] Quick start clear
- [ ] All links work

### Technical
- [ ] Valid markdown
- [ ] Renders correctly on GitHub

---

## Autopilot Log

- **2026-01-25**: README already has hero format
  - Badges present (MIT, Claude Code, version)
  - Problem statement clear
  - Quick start (3 steps)
  - Workflow diagram (ASCII)
  - Key concepts explained
  - Comparison table included
  - All documentation links work
- No changes needed - already complete
