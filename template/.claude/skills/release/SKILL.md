---
name: release
description: Automated documentation updates — CHANGELOG, README, docs. Fully automatic, no confirmations.
model: sonnet
---

# Release — Automated Documentation Updates

Analyzes git history and automatically updates CHANGELOG, README, and documentation files.

**Activation:** `/release` or `/release 3.8` (with explicit version)

---

## When to Use

- After merging features to main/develop
- Before creating a release tag
- Weekly documentation maintenance
- After significant changes

---

## Process

### PHASE 1: COLLECT

**Step 1.1: Find Base Commit**

```bash
git log -1 --format=%H CHANGELOG.md
```

If CHANGELOG.md doesn't exist, use first commit or last tag.

**Step 1.2: Extract Current Version**

Read `CHANGELOG.md` → parse latest version header (e.g., `## [3.7] - 2026-02-14`)

**Step 1.3: Collect New Commits**

```bash
git log --oneline BASE_COMMIT..HEAD
```

**Step 1.4: Collect Changed Files**

```bash
git diff --stat BASE_COMMIT..HEAD
```

**Step 1.5: Filter Commits**

Skip:
- `ai/**` files (internal development)
- Merge commits (prefix "Merge")
- `.gitignore`-d files
- `docs:` prefix commits (already documented)

---

### PHASE 2: ANALYZE

**Step 2.1: Parse Commits**

Map Conventional Commits prefixes to CHANGELOG categories:

| Prefix | Category |
|--------|----------|
| `feat:` | Added |
| `fix:` | Fixed |
| `refactor:` | Changed |
| `BREAKING CHANGE:` | Breaking Changes |
| `security:` | Security |
| `perf:` | Changed |
| `test:` | Skip |
| `docs:` | Skip |
| `chore:` | Changed (if user-facing) |
| `build:` | Architecture |
| `ci:` | Architecture |

**Step 2.2: Group Related Commits**

Detect patterns:
- Same ticket ID: `BUG-084-01`, `BUG-084-02`, ..., `BUG-084-29` → single entry
- Same scope: `fix(hooks): X`, `fix(hooks): Y` → single entry
- Same component: multiple commits touching same domain

**Step 2.3: Rewrite to User-Facing**

Technical → User-Facing:

| Technical | User-Facing |
|-----------|-------------|
| `fix(hooks): add chmod check` | **Hooks** — fix permissions error on Windows |
| `feat(agents): add toc analyst` | **Bug Hunt** — TOC Analyst for constraint analysis |
| `refactor(coder): split into modules` | **Coder agent** — improved modularity (internal) |

**Step 2.4: Determine Version Bump**

Auto-detect (unless explicit version arg):
- BREAKING CHANGE → MAJOR (3.7 → 4.0)
- `feat:` → MINOR (3.7 → 3.8)
- `fix:`, `chore:` → PATCH (3.7.0 → 3.7.1)

If user provided version (e.g., `/release 3.8`) → use that, warn if downgrade.

**Step 2.5: Check README Sections**

Read `README.md` and identify sections needing updates:
- Version badge (first line or top)
- Skills table (if new skill added)
- Project structure (if new directories)
- Feature descriptions (if major changes)

**Step 2.6: Scan docs/**

Check `docs/` files referenced by changed files:
- Extract doc links from modified code
- Check if doc content is stale (version, API, examples)

---

### PHASE 3: EXECUTE

**All updates are automatic — no confirmations.**

**Step 3.1: Update CHANGELOG.md**

Prepend new version section:

```markdown
## [X.Y] - YYYY-MM-DD

### Added
- **Component** — user-facing description

### Changed
- **Component** — what changed and why

### Fixed
- **Component** — what was broken and how fixed

### Removed
- **Component** — removed and replacement

### Security
- **Component** — improvement description

### Architecture
- Technical changes affecting system structure

---
```

Update Version History table at bottom (if exists).

**Step 3.2: Update README.md**

- Version badge: `![Version](https://img.shields.io/badge/version-X.Y-blue)`
- Skills table: add new skill row
- Project structure: reflect new directories
- Feature descriptions: update if major changes

**Step 3.3: Update template/README.md**

Same as README.md if template has own README.

**Step 3.4: Update docs/ Files**

Only if provably stale:
- Version numbers
- API signatures
- Code examples
- CLI commands

**Step 3.5: Update package.json**

If `packages/create-dld/package.json` exists:
```json
{
  "version": "X.Y.Z"
}
```

---

### PHASE 4: REPORT

**Step 4.1: Show Summary**

```yaml
status: completed
version: X.Y
files_modified:
  - path: CHANGELOG.md
    lines_added: 45
    lines_changed: 2
  - path: README.md
    lines_changed: 8
  - path: template/README.md
    lines_changed: 8

changelog_preview: |
  ## [X.Y] - YYYY-MM-DD

  ### Added
  - **Feature** — description

  ### Fixed
  - **Component** — description
```

**Step 4.2: Suggest Next Steps**

```
Next steps:
1. Review changes: git diff
2. Commit: git add CHANGELOG.md README.md docs/ && git commit -m 'docs: release vX.Y'
3. Tag: git tag vX.Y
4. Push: git push && git push --tags
```

**DO NOT auto-commit or auto-tag.** Human reviews first.

---

## Edge Cases

| Case | Action |
|------|--------|
| No commits since last CHANGELOG | Exit with "Nothing new to document" |
| Only `ai/` changes | Exit with "Only internal changes, nothing to publish" |
| No CHANGELOG.md | Create from scratch with current version |
| No git tags | Use CHANGELOG.md last modification as base |
| Version arg conflicts | Use explicit arg, warn if downgrade |
| 100+ commits | Summarize by category ("15 bug fixes", "8 features") |
| README has no version badge | Skip badge update |
| No package.json | Skip package.json update |

---

## Filtering Rules (SSOT)

**Include:**
- `.claude/**` (if user-facing)
- `template/.claude/**`
- `template/**` (non-.claude)
- `docs/**`
- `packages/**`
- `src/**`

**Exclude:**
- `ai/**` (internal development)
- `test/**` (not user-facing)
- Merge commits
- `docs:` prefix commits (already documented)
- `.gitignore`-d files

---

## Commit Grouping Examples

**Example 1: Ticket ID**

```
BUG-084-01 fix(hooks): chmod check
BUG-084-02 fix(hooks): error message
...
BUG-084-29 fix(template): explain tiers
```

→ `**Template framework** — audit: 29 fixes (BUG-084)`

**Example 2: Same Scope**

```
fix(hooks): chmod check
fix(hooks): error log path
fix(hooks): Windows compatibility
```

→ `**Hooks** — improved error handling and cross-platform support`

**Example 3: Same Component**

```
feat(agents): add toc analyst
feat(agents): add triz analyst
feat(agents): add validator
```

→ `**Bug Hunt** — three new analysis agents (TOC, TRIZ, Validator)`

---

## Changelog Entry Format (Keep a Changelog 1.1.0)

```markdown
## [X.Y] - YYYY-MM-DD

### Added
- **Feature Name** — user-facing description
- **Component** — what's new

### Changed
- **Component** — what changed and why
- **Agent** — improvement description

### Fixed
- **Component** — what was broken and how fixed
- **Bug** — root cause and solution

### Removed
- **Component** — removed and replacement
- **Deprecated feature** — migration path

### Security
- **Component** — vulnerability fixed or improvement

### Breaking Changes
- **API** — old vs new behavior, migration steps

### Architecture
- Technical changes affecting system structure
- Refactorings, dependency updates (if user-impacting)

---
```

**Rules:**
- Date format: `YYYY-MM-DD`
- Version format: `[X.Y]` (brackets required)
- Entry format: `- **Component** — description` (em dash, not hyphen)
- Order: Added → Changed → Fixed → Removed → Security → Breaking Changes → Architecture
- Skip empty sections

---

## Quality Checklist

Before completing:

- [ ] All commits since last CHANGELOG analyzed
- [ ] Commits grouped logically (ticket ID, scope, component)
- [ ] Technical messages rewritten to user-facing
- [ ] Version bump follows semver (or explicit arg)
- [ ] CHANGELOG.md follows Keep a Changelog 1.1.0
- [ ] README.md sections updated (version, skills, structure)
- [ ] template/README.md synced (if exists)
- [ ] docs/ files updated only if provably stale
- [ ] package.json version updated (if exists)
- [ ] Next steps suggested (commit, tag, push)

---

## Output Format

```yaml
status: completed | blocked
version: X.Y
commits_analyzed: N
files_modified:
  - path: ...
    lines_added: N
    lines_changed: N
changelog_preview: |
  ...
next_steps: |
  1. Review: git diff
  2. Commit: git add ... && git commit -m 'docs: release vX.Y'
  3. Tag: git tag vX.Y
  4. Push: git push && git push --tags
```

---

## What NOT to Do

| Wrong | Correct |
|-------|---------|
| Auto-commit changes | Report, suggest commit command |
| Auto-create git tag | Suggest tag command |
| Auto-push to remote | Suggest push command |
| Ask for confirmation | Fully automatic analysis + updates |
| Include `ai/` changes | Filter out internal development |
| One line per commit | Group related commits |
| Use hyphens in entries | Use em dash (—) |
| Skip version in README | Update if badge exists |

