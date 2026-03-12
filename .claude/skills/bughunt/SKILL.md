---
name: bughunt
description: Deep multi-agent bug analysis. 6 personas × N zones → findings report + inbox items for Spark. Triggers on keywords: bug hunt, deep analysis, охота на баги, баг-хант, командный аудит багов
---

# Bug Hunt — Standalone Deep Analysis Skill

Multi-agent pipeline for systematic bug detection across codebase zones.

**Activation:** `bughunt`, `bug hunt`, `deep analysis`, `охота на баги`

## When to Use

- Complex/systemic bugs affecting >5 files
- Proactive quality sweep of a module or domain
- User explicitly requests "bug hunt" or "deep analysis"
- Post-refactoring verification

**Don't use:** Simple bugs (<5 files) → use `/spark` Quick Bug Mode instead.

## Architecture

Bughunt manages ALL pipeline steps directly at Task nesting Level 1.
Reuses existing agents from `.claude/agents/bug-hunt/`.

**Output:** Report + N inbox files (NOT backlog entries — Spark creates specs).

```
Step 0: scope-decomposer → zones.yaml
Step 1: 6 personas × N zones (background fan-out) → findings/
Step 2: findings-collector → summary.yaml
Step 3: spec-assembler → umbrella report
Step 4: validator → grouped findings
Step 5: report-updater → final report
Step 6: Create N inbox files (one per finding group)
```

## Modules

| Module | Content |
|--------|---------|
| `pipeline.md` | Full 7-step pipeline with file gates and ADR compliance |
| `completion.md` | Inbox output format, commit + push, cleanup |

**Flow:** `SKILL.md → pipeline.md → completion.md`

---

## STRICT RULES

- **READ-ONLY for source code** — Bughunt NEVER modifies application files
- **No backlog entries** — Bughunt writes to inbox, Spark creates specs
- **No autopilot handoff** — Bughunt finishes after inbox + push
- **All agents background** — ADR-009 compliance
- **File gates** — Each step verifies previous step's output before proceeding

## Headless Mode

When `[headless]` marker present in prompt:
- Skip cost confirmation (already approved via Telegram)
- Proceed directly with pipeline

## Cost Estimate

~$15/zone (6 Sonnet personas) + ~$10 fixed (validator + architects) = **~$30-50 typical**

Print estimate before launch (non-blocking — don't wait for confirmation).
