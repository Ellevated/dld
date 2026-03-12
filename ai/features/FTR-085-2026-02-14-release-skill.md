# FTR-085: Release Skill — Automated Documentation Updates

**Status:** done | **Priority:** P1 | **Date:** 2026-02-14

## Problem

After making changes (features, fixes, refactoring), documentation gets out of sync:
- CHANGELOG.md not updated with new entries
- README.md version badge stale, feature list outdated
- docs/ files reference removed or renamed features
- Version History table in CHANGELOG.md not updated

Currently this is manual work. Forgetting to update one file = users see stale documentation.

## Solution

New `/release` skill — **fully automatic, zero-confirmation** documentation updater.

User codes → runs `/release` → all documentation updated in one pass. No approval gates, no questions asked.

**Zero external dependencies** — pure Claude Code skill (no git-cliff, no release-please, no npm packages).

## Research

Exa + Sequential Thinking research (Feb 14, 2026) evaluated:
- **git-cliff** (Rust) — fast CHANGELOG-only, no README/docs intelligence
- **release-please** (Google) — CI/CD-centric, npm-focused, overkill
- **semantic-release** — fully automated npm publish, too aggressive
- **AI changelog generators** — standalone tools, don't integrate with Claude Code
- **Claude Code skills** (claude-plugins.dev) — `readme-updater`, `maintaining-docs-after-changes`

**Decision:** Pure Claude Code skill. DLD users already have Claude Code. LLM understands context better than any template tool. Cost ~$1-3/run = negligible.

## Scope

### Create New Files

| File | Description |
|------|-------------|
| `template/.claude/skills/release/SKILL.md` | Universal skill prompt |

### Modify Existing Files

| File | Change |
|------|--------|
| `template/CLAUDE.md` | Add `/release` to Skills table |
| `template/.claude/rules/localization.md` | Add Spanish triggers for `/release` |
| `.claude/rules/localization.md` | Add Russian triggers for `/release` |

## Skill Design

### YAML Frontmatter

```yaml
---
name: release
description: Automated documentation updates — CHANGELOG, README, docs. Fully automatic, no confirmations.
model: sonnet
---
```

### Activation

- `/release` — update all documentation based on changes since last CHANGELOG entry
- `/release 3.8` — same, but use explicit version number
- Russian: "релиз", "подготовь релиз", "обнови доки"
- Spanish: "lanzamiento", "preparar lanzamiento", "actualizar docs"

### Algorithm

```
PHASE 1: COLLECT
├── 1.1 Read CHANGELOG.md → extract latest version + date
├── 1.2 Find base commit: git log that last modified CHANGELOG.md
├── 1.3 git log --oneline base..HEAD → all new commits
├── 1.4 git diff --stat base..HEAD → changed files summary
└── 1.5 Filter: skip ai/, skip merge commits, skip .gitignore-d

PHASE 2: ANALYZE
├── 2.1 Parse commits using Conventional Commits prefixes
│   ├── feat() → Added
│   ├── fix() → Fixed
│   ├── docs() → (skip — meta-docs don't go in changelog)
│   ├── refactor() → Changed
│   ├── BREAKING CHANGE → ⚠️ Breaking Changes
│   ├── security() → Security
│   └── chore() → (skip unless user-facing)
├── 2.2 Group related commits into single entries
│   └── e.g., BUG-084-01 through BUG-084-29 → "Template framework audit: 29 fixes"
├── 2.3 Rewrite technical commit messages → user-facing descriptions
│   └── "fix(hooks): BUG-084-29 actionable fix..." → "Improved hook error messages with actionable fix instructions"
├── 2.4 Auto-detect version bump:
│   ├── BREAKING CHANGE present → MAJOR bump
│   ├── feat() present → MINOR bump
│   └── only fix()/chore() → PATCH bump
│   └── Override: if user passed version arg, use that
├── 2.5 Read current README.md → identify sections that may need updates
│   ├── Version badge line → always update if version changed
│   ├── Skills table → if new skill added
│   ├── Project Structure → if structure changed
│   ├── Getting Started → if setup flow changed
│   └── Feature descriptions → if major features added/removed
└── 2.6 Scan docs/ for stale content
    └── Only check docs referenced by changed files

PHASE 3: EXECUTE (fully automatic)
├── 3.1 CHANGELOG.md
│   ├── Prepend new version section after "---" (line 7)
│   ├── Format: Keep a Changelog 1.1.0
│   ├── Categories: Added, Changed, Fixed, Removed, Security, Breaking Changes
│   ├── Each entry: "- **Component** — description"
│   ├── Add Architecture subsection if structural changes
│   └── Update Version History table at bottom
├── 3.2 README.md
│   ├── Update version badge: version-X.Y-green
│   ├── Update skills table if new skill added
│   ├── Update project structure if new directories
│   └── Update feature descriptions if major changes
├── 3.3 template/README.md
│   └── Same updates as README.md (if template has its own README)
├── 3.4 docs/ files
│   └── Update only if content is provably stale (old feature names, removed commands)
└── 3.5 packages/create-dld/package.json
    └── Update version field if it exists

PHASE 4: REPORT
├── 4.1 Show summary of all changes made
│   ├── Files modified (with line counts)
│   ├── New version number
│   └── Changelog entry preview
├── 4.2 Suggest next steps:
│   ├── "Review changes: git diff"
│   ├── "Commit: git add CHANGELOG.md README.md docs/ && git commit -m 'docs: release vX.Y'"
│   └── "Tag: git tag vX.Y"
└── 4.3 DO NOT auto-commit (user decides)
```

### Filtering Rules

| Path Pattern | Action | Reason |
|-------------|--------|--------|
| `ai/**` | IGNORE | Internal dev kitchen, gitignored |
| `.claude/**` | INCLUDE only if user-facing | Agent/skill changes = features for users |
| `template/.claude/**` | INCLUDE | Universal changes = affect all DLD users |
| `template/**` (non-.claude) | INCLUDE | Template changes = user-facing |
| `docs/**` | INCLUDE | Documentation changes |
| `packages/**` | INCLUDE | npm package changes |
| `src/**` | INCLUDE | Source code changes |
| `test/**` | SKIP | Tests are internal |
| Merge commits | SKIP | Noise |
| `docs:` prefix commits | SKIP from changelog | Meta-documentation, circular |

### Commit Grouping Rules

Group commits that share the same ticket ID or scope:

```
BUG-084-01, BUG-084-02, ..., BUG-084-29
→ Single entry: "**Template audit** — 29 fixes across hooks, prompts, and documentation"

fix(hooks): X, fix(hooks): Y, fix(hooks): Z
→ Single entry: "**Hook improvements** — X, Y, and Z"
```

### Changelog Entry Format

```markdown
## [X.Y] - YYYY-MM-DD

### Added
- **Feature Name** — user-facing description

### Changed
- **Component** — what changed and why it matters to users

### Fixed
- **Component** — what was broken and how it's fixed now

### Removed
- **Component** — what was removed and what replaces it

### Security
- **Component** — security improvement description

### Architecture
- Technical changes that affect the system structure
```

### Edge Cases

| Situation | Behavior |
|-----------|----------|
| No commits since last CHANGELOG | Print "Nothing new to document" and exit |
| Only ai/ changes | Print "Only internal changes, nothing to publish" and exit |
| No CHANGELOG.md exists | Create it from scratch with header |
| No git tags | Use last CHANGELOG.md modification as base (already the plan) |
| Version arg conflicts with auto-detect | Use explicit arg, warn if downgrade |
| 100+ commits | Summarize by category, don't list each |
| README has no version badge | Skip badge update, don't add one |

## Allowed Files

| File | Action |
|------|--------|
| `template/.claude/skills/release/SKILL.md` | CREATE |
| `template/CLAUDE.md` | MODIFY (add skill to table) |
| `template/.claude/rules/localization.md` | MODIFY (add Spanish triggers) |
| `.claude/rules/localization.md` | MODIFY (add Russian triggers) |

## Definition of Done

- [ ] `template/.claude/skills/release/SKILL.md` created with full algorithm
- [ ] SKILL.md follows YAML frontmatter pattern (name, description, model)
- [ ] Skill is fully automatic — zero AskUserQuestion calls in the flow
- [ ] Template CLAUDE.md has `/release` in Skills table
- [ ] Localization triggers added (Russian + Spanish)
- [ ] SKILL.md < 400 LOC
- [ ] No external dependencies required

## Notes

- **Model: sonnet** — documentation work, not deep reasoning
- **No agent needed** — skill runs directly (like reflect), not via separate agent
- **No plan subagent** — algorithm is deterministic, defined in SKILL.md
- **Template-sync**: skill goes in template/ (universal), then synced to root
