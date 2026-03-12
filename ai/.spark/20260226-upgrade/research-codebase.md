# Codebase Research — /upgrade Skill

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `check-sync.sh` | `scripts/check-sync.sh:1` | Shows divergence between `template/.claude` and `.claude` via comm + line count diff | Extend: add version-aware mode, write to upgrade report |
| `create-dld index.js` | `packages/create-dld/index.js:154` | Sparse-clone → `cpSync(template/, dest, recursive)` — the canonical copy logic | Pattern: same git sparse checkout for upgrade fetch |
| `installation-guide.md` | `template/ai/installation-guide.md:74` | Full LLM protocol: scan → diff → confirm → install → verify | Pattern: exact phase sequence for /upgrade skill |
| `CHANGELOG.md version header` | `CHANGELOG.md:9` | `## [3.9] - 2026-02-22` format; `packages/create-dld/package.json` has `"version": "3.9.0"` | Source of truth: current installed version |
| `hooks.config.mjs excludeFromSync` | `template/.claude/hooks/hooks.config.mjs:85` | Explicit list of files excluded from sync: localization, template-sync, git-local-folders, CUSTOMIZATIONS, settings.local.json | Import directly: this is the merge/skip list for /upgrade |
| `pre-edit.mjs checkSyncZone()` | `template/.claude/hooks/pre-edit.mjs:94` | Checks if edited file is in `.claude/` or `scripts/` sync zones (minus excludeFromSync) | Pattern: same logic for "safe to overwrite vs ask" |
| `release/SKILL.md step 3.5` | `template/.claude/skills/release/SKILL.md:177` | Updates `packages/create-dld/package.json` version as part of release flow | Import: /upgrade can read version from same location |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| Upgrade from 3.5 (manual prompt) | `CHANGELOG.md:113` | Manual upgrade steps: download 8 files via `gh api`, update settings.json, delete old files | Direct predecessor — /upgrade automates exactly this |
| installation-guide scan→diff→confirm | `template/ai/installation-guide.md:11` | 5-step LLM protocol for install: scan, show diff, confirm, install, summary | Identical structure for /upgrade (same phases, different context) |
| retrofit framework-upgrade trigger | `template/.claude/skills/retrofit/SKILL.md:17` | "Framework upgrade — project started on DLD v1, now v2 exists" — explicitly listed as a retrofit trigger | Overlap: /upgrade is a focused version of this use case |
| docs/upgrade-paths.md | `docs/getting-started/upgrade-paths.md:1` | Tier upgrade paths (Quick→Standard→Power) — manual shell steps | Pattern: /upgrade automates the DLD framework version upgrade, not tier upgrade |

**Recommendation:** Build /upgrade as a standalone orchestrator skill. Reuse `check-sync.sh` logic for diff detection, `excludeFromSync` list from `hooks.config.mjs` as the protected-files registry, and the 5-phase structure from `installation-guide.md`. Do NOT reuse `/retrofit` — that's for project-level brownfield reassessment, not DLD framework sync.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
# Command used:
grep -r "check-sync\|template-sync\|sync.*zone\|excludeFromSync" . --include="*.md" --include="*.mjs"
```

| File | Line | Usage |
|------|------|-------|
| `scripts/check-sync.sh` | 1 | Defines the sync diff logic |
| `template/.claude/hooks/pre-edit.mjs` | 94 | `checkSyncZone()` reads `syncZones` + `excludeFromSync` from config |
| `template/.claude/hooks/hooks.config.mjs` | 85 | Defines `excludeFromSync` array (canonical list) |
| `template/.claude/rules/template-sync.md` | 1 | Documents the two-copy sync policy |
| `.claude/rules/template-sync.md` | 1 | Root copy of sync policy |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Function |
|------------|------|----------|
| `packages/create-dld/package.json` | `packages/create-dld/package.json:3` | `version` field — source of current DLD version |
| `CHANGELOG.md` | `CHANGELOG.md:9` | Latest `## [X.Y]` header — version confirmation |
| `template/` directory | `packages/create-dld/index.js:16` | `TEMPLATE_DIR = 'template'` — what gets copied |
| GitHub repo | `packages/create-dld/index.js:14` | `REPO_URL = 'https://github.com/Ellevated/dld.git'` — update source |
| `hooks.config.mjs` | line 85 | `excludeFromSync` — files to never overwrite |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "upgrade\|.dld-version\|dld.*version\|version.*dld" . --include="*.md" --include="*.mjs" --include="*.json" --include="*.sh"
```

| File | Line | Context |
|------|------|---------|
| `CHANGELOG.md` | 113 | `### Upgrade from 3.5` — manual upgrade instructions |
| `CHANGELOG.md` | 118 | Paste-this-prompt for upgrading hooks v3.5→v3.6 |
| `template/.claude/skills/retrofit/SKILL.md` | 17 | `Framework upgrade -- project started on DLD v1` |
| `docs/getting-started/upgrade-paths.md` | 1 | Full upgrade-paths doc (tier upgrades, not DLD version) |
| `packages/create-dld/package.json` | 3 | `"version": "3.9.0"` — canonical DLD version |
| `template/CLAUDE.md` | heading | `## Project Context System (v3.9)` — version in content |

No `.dld-version` file found anywhere. Version tracking is currently split: `packages/create-dld/package.json` + CHANGELOG headers. No version marker is written into the user's project directory at install time.

### Step 4: CHECKLIST — Mandatory folders

- [ ] `tests/**` — 0 test files for sync/upgrade logic (hooks have `__tests__/` but no upgrade tests)
- [ ] `db/migrations/**` — N/A (not a db project)
- [ ] `ai/glossary/**` — 0 files (no glossary for upgrade domain yet)
- [ ] `template/.claude/skills/upgrade/` — does NOT exist (new skill to create)
- [ ] `.claude/skills/upgrade/` — does NOT exist

### Step 5: DUAL SYSTEM check

N/A for upgrade logic itself.

BUT: the /upgrade skill will read from TWO sources:
1. GitHub `template/` (new version) — sparse clone
2. User's `.claude/` and `scripts/` (current version)

Dual-read consumers:
- `hooks.config.mjs` (new from GitHub) vs `hooks.config.local.mjs` (user's customization — DO NOT overwrite)
- `settings.json` (new from GitHub) vs user's `settings.json` (may have custom hooks — ASK before overwrite)
- `rules/localization.md` (user's custom language triggers — DO NOT overwrite)
- `CUSTOMIZATIONS.md` (user's documented customizations — READ but never overwrite)

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `template/.claude/skills/upgrade/SKILL.md` | 0 (new) | Main upgrade skill orchestrator | create |
| `template/.claude/rules/template-sync.md` | existing | Sync policy — may need version-tracking section | modify |
| `template/CLAUDE.md` | existing | Skills table — add upgrade row | modify |
| `.claude/CLAUDE.md` | existing | Skills table — add upgrade row | modify |
| `CHANGELOG.md` | 243 | Will get new entry for /upgrade release | read-only (for release skill) |
| `packages/create-dld/package.json` | 31 | Version source of truth | read-only |
| `scripts/check-sync.sh` | 69 | Sync diff logic — reuse as reference | read-only |
| `template/.claude/hooks/hooks.config.mjs` | 135 | `excludeFromSync` list — canonical protected files | read-only (imported by skill) |
| `template/ai/installation-guide.md` | 417 | Phase protocol for install/upgrade — reference | read-only |

**Total:** 2 files to create/modify, 7 reference files

---

## Reuse Opportunities

### Import (use as-is)

- `hooks.config.mjs.excludeFromSync` — exact list of files the skill must never overwrite. Currently: `localization.md`, `template-sync.md`, `git-local-folders.md`, `CUSTOMIZATIONS.md`, `settings.local.json`
- `create-dld/index.js` sparse-clone pattern — `git clone --depth 1 --filter=blob:none --sparse REPO_URL tmpdir` → `git sparse-checkout set template` — copy verbatim for fetching latest template
- `check-sync.sh` comm-based diff logic — the three sections (only in root, only in template, different line counts) map directly to upgrade report sections

### Extend (wrap or build on)

- `installation-guide.md` Phase 1 scan → adapt to "detect current DLD version" before Phase 1
- `check-sync.sh` line-count diff → extend with content hash diff for more reliable change detection (line count can be identical but content changed)

### Pattern (copy structure, not code)

- `CHANGELOG.md:113` (Upgrade from 3.5 prompt) — the manual upgrade prompt is the gold standard for what /upgrade must automate. Each step there becomes a phase in the skill.
- `release/SKILL.md` phase structure (Collect → Analyze → Execute → Report) — same 4-phase cadence works for /upgrade

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -10 -- template/ scripts/ packages/
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-02-24 | 769a2ae | Ellevated | fix(spark): add cost estimate, degraded mode, upgrade ADR block |
| 2026-02-24 | e64410a | Ellevated | fix(board): add cost estimate, degraded mode, ADR block in retrofit |
| 2026-02-23 | ce34df0 | Ellevated | fix(council,architect): add cost estimates and degraded mode docs |
| 2026-02-23 | 8be74ae | Ellevated | fix(triz): update cost estimate, add degraded mode docs |
| 2026-02-22 | 5e2fe59 | Ellevated | feat(bughunt): replace Definition of Done with structured Eval Criteria (ADR-012) |

**Observation:** Template is actively updated (3-4 commits/week). This confirms the need for /upgrade — projects initialized 2 weeks ago are already 2 minor versions behind.

```bash
git log --oneline -- packages/create-dld/
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| recent | b15b6f4 | Ellevated | chore: bump create-dld to v1.0.3 |
| recent | 06048ca | Ellevated | chore: bump create-dld to v1.0.2 |
| recent | ab67ab4 | Ellevated | fix(create-dld): use tilde versioning for prompts dependency |
| recent | 9cc22b1 | Ellevated | feat(ci): add npm publish workflow for create-dld |

**Observation:** `create-dld` package version (1.0.3) is decoupled from DLD framework version (3.9). Separate version schemes will complicate version detection. The skill should read framework version from CHANGELOG header or a to-be-created `.dld-version` file, not from `create-dld` package version.

---

## Template File Inventory

**Total template files:** 164
**template/.claude/ files:** 144 (109 `.md`, 33 `.mjs`, 2 `.json`)
**template/scripts/ files:** 6 (`.sh` only)

### Breakdown by category

| Category | Count | Path |
|----------|-------|------|
| Skills | ~20 SKILL.md + mode files | `template/.claude/skills/*/` |
| Agents | ~50 `.md` files | `template/.claude/agents/*/` |
| Hooks | 8 `.mjs` + 9 tests + package.json | `template/.claude/hooks/` |
| Scripts (validate/state) | 10 `.mjs` | `template/.claude/scripts/` |
| Tools | 1 `.mjs` | `template/.claude/tools/` |
| Rules | 6 `.md` | `template/.claude/rules/` |
| Settings | 1 `.json` | `template/.claude/settings.json` |
| Scripts (bash) | 6 `.sh` | `template/scripts/` |

---

## Key Design Decisions for /upgrade

### 1. Version Detection

No `.dld-version` file exists in user projects. Current options:
- **A** Create `.dld-version` file written by `create-dld` at init time (requires create-dld change)
- **B** Read `CHANGELOG.md` first line of installed version (unreliable — users may not have it)
- **C** Ask user "what version did you install?" (bad UX)
- **D** Skip version detection — always show full diff, let user decide what to apply

**Recommendation:** D for now (safest, no new files). Propose creating `.dld-version` as a TECH task for create-dld.

### 2. Protected Files (NEVER overwrite)

From `hooks.config.mjs:85` (`excludeFromSync`):
```
.claude/rules/localization.md        ← user's language triggers
.claude/rules/template-sync.md       ← sync policy (DLD-internal)
.claude/rules/git-local-folders.md   ← gitignore rules (DLD-internal)
.claude/CUSTOMIZATIONS.md            ← user's documented changes
.claude/settings.local.json          ← user's local settings override
```

Additional files to protect (not in excludeFromSync but obvious):
```
.claude/hooks/hooks.config.local.mjs ← user's hook overrides (if exists)
CLAUDE.md                            ← user has filled this with their project info
```

### 3. Merge Strategy by File Type

| File Type | Strategy | Reason |
|-----------|----------|--------|
| `.claude/agents/**/*.md` | Overwrite (confirm) | Pure framework prompts, users don't customize |
| `.claude/skills/**/*.md` | Overwrite (confirm) | Same |
| `.claude/hooks/*.mjs` | Overwrite (confirm) | Logic files, customization via config.local.mjs |
| `.claude/hooks/hooks.config.mjs` | Overwrite (confirm) | Defaults only — local overrides in config.local |
| `.claude/hooks/hooks.config.local.mjs` | SKIP | User's customization |
| `.claude/rules/*.md` (non-protected) | Overwrite (confirm) | Framework rules |
| `.claude/rules/localization.md` | SKIP | User's language |
| `.claude/CUSTOMIZATIONS.md` | SKIP | User's docs |
| `.claude/settings.json` | ASK (diff first) | May have user hook additions |
| `scripts/*.sh` | Overwrite (confirm) | Pure framework scripts |
| `template/CLAUDE.md` → user's `CLAUDE.md` | NEVER | User owns this file |

### 4. Skill Phase Structure

Mirrors `installation-guide.md` protocol (already designed for LLMs):
```
Phase 1: SCAN    — detect existing .claude/, read CUSTOMIZATIONS.md
Phase 2: FETCH   — sparse-clone latest template to /tmp
Phase 3: DIFF    — compare file-by-file (new files, changed files, deleted files)
Phase 4: CONFIRM — show report, ask user for approval
Phase 5: APPLY   — copy approved files, skip protected
Phase 6: VERIFY  — check hooks work, suggest restart
Phase 7: REPORT  — summary of what changed
```

---

## Risks

1. **Risk:** No version marker in user projects
   **Impact:** Cannot detect "how old is this install?" — no targeted changelog
   **Mitigation:** Show full diff always. As TECH task: add `.dld-version` write to `create-dld/index.js`

2. **Risk:** `settings.json` has user-added hooks (not in template)
   **Impact:** Overwriting silently removes user's custom hooks
   **Mitigation:** Always diff `settings.json`, never auto-overwrite — require explicit confirmation

3. **Risk:** User has modified `hooks.config.mjs` directly (instead of using `.local.mjs`)
   **Impact:** Their changes get wiped
   **Mitigation:** Check if `hooks.config.local.mjs` exists; if not, warn: "You may have customized hooks.config.mjs directly. Create hooks.config.local.mjs for safe upgrades."

4. **Risk:** Template has 144 `.claude/` files — full overwrite feels destructive
   **Impact:** User anxiety, possible mistakes
   **Mitigation:** Default to selective mode (only show changed files, not full list). Optional `--full` flag for all files.

5. **Risk:** create-dld package version (1.0.3) vs DLD framework version (3.9) are decoupled
   **Impact:** Version comparison is confusing — which version number matters?
   **Mitigation:** Skill uses only DLD framework version (CHANGELOG / to-be-created `.dld-version`). Ignore npm package version.

6. **Risk:** No tests for upgrade logic
   **Impact:** Regression risk if upgrade skill has bugs
   **Mitigation:** Add to test/smoke-test.sh after implementation. Integration test: create temp project → run /upgrade → verify key files updated.
