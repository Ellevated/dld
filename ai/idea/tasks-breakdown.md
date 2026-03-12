# DLD Launch — Детерминированная разбивка задач

## Принципы разбивки

- Каждая задача = 1 autopilot run
- Чёткий input → output
- Конкретные файлы
- Критерии done
- Max 2 часа на задачу

---

## Phase 1: STRUCTURE (блокер для остального)

### TECH-001: Split autopilot.md into modules
**Input:** `template/.claude/skills/autopilot/SKILL.md` (1192 lines)
**Output:** 5-6 файлов по ~150-200 LOC каждый
**Files to create:**
```
template/.claude/skills/autopilot/
├── SKILL.md           # Core: trigger, phases, handoff (~200 LOC)
├── worktree.md        # Worktree setup & cleanup (~150 LOC)
├── subagents.md       # Subagent dispatch rules (~150 LOC)
├── testing.md         # Smart testing, scope protection (~150 LOC)
├── migrations.md      # DB migrations (stack-specific, optional)
└── finishing.md       # Pre-done checklist, PR rules (~100 LOC)
```
**Done when:** Each file < 400 LOC, main SKILL.md imports others
**Estimate:** 2h

---

### TECH-002: Remove hardcode from autopilot
**Input:** TECH-001 output files
**Changes:**
- [ ] `/Users/desperado/.local/bin/uv` → detect package manager or use `pip`
- [ ] Supabase-specific → move to optional `migrations.md` or remove
- [ ] Any absolute paths → relative or configurable
**Done when:** No personal paths, no stack-specific hardcode in core files
**Estimate:** 1h

---

### TECH-003: Clean CLAUDE.md template
**Input:** `template/CLAUDE.md`
**Changes:**
- [ ] Remove: `Python 3.12 + FastAPI + Supabase + aiogram 3.x`
- [ ] Replace with: `{Your stack here}` placeholder
- [ ] Remove Russian text (translate or remove)
- [ ] Keep structure, make universal
**Done when:** Copy-paste ready for any stack
**Estimate:** 30min

---

### TECH-004: Add MCP setup instructions
**Input:** Current state (MCP mentioned but no setup docs)
**Output:** `docs/setup/mcp-servers.md` or section in README
**Content:**
- What MCP servers DLD uses (Context7, Exa)
- How to configure
- Optional vs required
**Done when:** New user can setup MCP from docs
**Estimate:** 1h

---

### TECH-005: Add hooks examples
**Input:** Hooks mentioned but no examples
**Output:** `template/.claude/hooks/` with examples
**Files:**
```
template/.claude/hooks/
├── README.md           # What hooks are, how to use
├── pre-commit.example  # Example pre-commit hook
└── post-push.example   # Example post-push hook
```
**Done when:** Examples work, paths are relative
**Estimate:** 30min

---

### TECH-006: GitHub community files
**Input:** None exist
**Output:** Root level files
**Files:**
```
LICENSE                    # MIT
CONTRIBUTING.md            # How to contribute (docs, examples, translations)
CODE_OF_CONDUCT.md         # Contributor Covenant
.github/ISSUE_TEMPLATE/
├── bug-report.md
├── feature-request.md
├── question.md
└── success-story.md
.github/PULL_REQUEST_TEMPLATE.md
```
**Done when:** All files created, GitHub recognizes them
**Estimate:** 1h

---

## Phase 2: CONTENT (translation)

### TECH-007: Translate foundation docs
**Input:** `docs/foundation/` (if exists) or `docs/00-*.md`
**Files:**
- `00-bootstrap.md`
- Any foundation/ subdirectory files
**Done when:** Full English, no Russian, same structure
**Estimate:** 1h

---

### TECH-008: Translate architecture docs (01-08)
**Input:** `docs/01-principles.md` through `docs/08-metrics.md`
**Output:** Same files, English
**Done when:** 8 files translated
**Estimate:** 2h

---

### TECH-009: Translate process docs (09-14)
**Input:** `docs/09-onboarding.md` through `docs/14-suggested-domains.md`
**Output:** Same files, English
**Done when:** 6 files translated
**Estimate:** 1.5h

---

### TECH-010: Translate LLM workflow docs (15-19)
**Input:** `docs/15-skills-setup.md` through `docs/19-living-architecture.md`
**Output:** Same files, English
**Done when:** 5 files translated
**Estimate:** 1.5h

---

### TECH-011: Translate all skills
**Input:** `template/.claude/skills/*/SKILL.md` (9 skills)
**Output:** Same files, English
**Skills:** bootstrap, spark, autopilot, council, audit, reflect, review, claude-md-writer, scout
**Done when:** All 9 SKILL.md files in English
**Estimate:** 2h

---

### TECH-012: Translate all agent prompts
**Input:** `template/.claude/agents/**/*.md`
**Output:** Same files, English
**Agents:** planner, coder, tester, debugger, reviewer, documenter + council (5 experts)
**Done when:** All agent prompts in English
**Estimate:** 1h

---

## Phase 3: README & LAUNCH CONTENT

### TECH-013: Hero README
**Input:** Current `README.md` (Russian)
**Output:** New `README.md` (English, hero format)
**Structure:**
```markdown
# DLD: LLM-First Architecture

> Transform AI coding chaos into deterministic development

[badges]

## The Problem
90% debugging vs 6% features...

## Try Before You Dive (Comparison Prompt)
```
Ask Claude: "Analyze DLD methodology..."
```

## Quick Start (3 steps)
1. Clone/copy template
2. Run /bootstrap
3. Run /spark for first feature

## How It Works
[workflow diagram placeholder]

## Real Results
[examples links]

## Comparison
[table: DLD vs Cursor vs Superpowers]

## Documentation
[links to docs/]

## Contributing
[link to CONTRIBUTING.md]
```
**Done when:** README follows structure, all links work
**Estimate:** 2h

---

### TECH-014: Create COMPARISON.md
**Input:** Competitor analysis from bootstrap
**Output:** `COMPARISON.md`
**Content:**
- DLD vs Cursor (IDE vs methodology)
- DLD vs Superpowers (autonomy level)
- DLD vs Clean Architecture (human vs LLM)
- Feature comparison table
- When to use what
**Done when:** Fair, factual comparison
**Estimate:** 1h

---

### TECH-015: Create FAQ.md
**Input:** Anticipated questions from bootstrap
**Output:** `FAQ.md`
**Sections:**
- What is DLD?
- Who is it for?
- How long to learn?
- Does it work with [X stack]?
- How is it different from Superpowers?
- Can I use it with Cursor?
**Done when:** 10+ Q&A pairs
**Estimate:** 30min

---

### TECH-016: Draft HackerNews post
**Input:** product-brief.md, persona.md
**Output:** `ai/launch/hackernews-post.md`
**Format:** Show HN title + body (concise, no marketing speak)
**Done when:** Ready to copy-paste to HN
**Estimate:** 30min

---

### TECH-017: Draft Twitter thread
**Input:** product-brief.md, launch-strategy.md
**Output:** `ai/launch/twitter-thread.md`
**Format:** 8-10 tweets with placeholders for images
**Done when:** Ready to post (minus images)
**Estimate:** 30min

---

### TECH-018: Draft Reddit posts
**Input:** product-brief.md
**Output:** `ai/launch/reddit-posts.md`
**Posts for:**
- r/ClaudeAI
- r/programming
- r/opensource
**Done when:** 3 adapted posts ready
**Estimate:** 30min

---

## Phase 4: EXAMPLES

### TECH-019: Example 1 — Marketplace Launch
**Input:** Your real project
**Output:** `examples/marketplace-launch/README.md`
**Content:**
- What: SKU launch automation for marketplaces
- Problem it solved
- DLD principles used
- Results (if shareable)
- Structure diagram
**Done when:** Compelling story, shows DLD value
**Estimate:** 1.5h

---

### TECH-020: Example 2 — AI Autonomous Company
**Input:** Your real project
**Output:** `examples/ai-autonomous-company/README.md`
**Content:** Same structure as TECH-019
**Done when:** Compelling story
**Estimate:** 1.5h

---

### TECH-021: Example 3 — Content Factory
**Input:** Your real project
**Output:** `examples/content-factory/README.md`
**Content:** Same structure as TECH-019
**Done when:** Compelling story
**Estimate:** 1h

---

## Phase 5: BRANDING (optional Day 1)

### TECH-022: Workflow diagram
**Input:** Spark → Autopilot → Done flow
**Output:** `assets/workflow-diagram.png` or Mermaid in README
**Done when:** Visual shows DLD workflow clearly
**Estimate:** 30min

---

### TECH-023: Comparison table image
**Input:** COMPARISON.md table
**Output:** `assets/comparison-table.png`
**Done when:** Clean image for Twitter/README
**Estimate:** 30min

---

## Summary

| Phase | Tasks | Estimate |
|-------|-------|----------|
| 1. Structure | TECH-001 to TECH-006 | 6h |
| 2. Content | TECH-007 to TECH-012 | 9h |
| 3. README & Launch | TECH-013 to TECH-018 | 5h |
| 4. Examples | TECH-019 to TECH-021 | 4h |
| 5. Branding | TECH-022 to TECH-023 | 1h |

**Total: ~25h** (slightly over 20h budget)

---

## Execution Order (Dependencies)

```
TECH-001 → TECH-002 (autopilot split → clean)
    ↓
TECH-003, TECH-004, TECH-005, TECH-006 (parallel: template, MCP, hooks, GitHub)
    ↓
TECH-007 to TECH-012 (parallel: all translations)
    ↓
TECH-013 (Hero README - needs translated docs)
    ↓
TECH-014, TECH-015 (COMPARISON, FAQ - can parallel)
    ↓
TECH-016, TECH-017, TECH-018 (launch posts - can parallel)
    ↓
TECH-019, TECH-020, TECH-021 (examples - can parallel)
    ↓
TECH-022, TECH-023 (branding - last, optional)
    ↓
LAUNCH
```

---

## Priority if Time Crunch

**Must ship (15h):**
- TECH-001, 002, 003 (structure)
- TECH-007-012 (translation)
- TECH-013 (README)

**Should ship (5h):**
- TECH-006 (GitHub templates)
- TECH-014 (COMPARISON)
- TECH-016 (HN post)

**Can skip Day 1:**
- TECH-004, 005 (MCP, hooks docs)
- TECH-015 (FAQ)
- TECH-017, 018 (Twitter, Reddit)
- TECH-019-021 (examples - link to private repos?)
- TECH-022, 023 (branding)
