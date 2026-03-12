# Devil's Advocate — Deterministic DLD Upgrade Skill

## Why NOT Do This?

### Argument 1: The Chicken-and-Egg Bootstrap Problem
**Concern:** Every user who installed DLD before version tracking was added has no `.dld-version`, no checksum manifest, and no baseline. The upgrade script has no starting point — it cannot know what was modified vs what is "original template." A forced overwrite treats all their customizations as conflicts. A conservative skip leaves them unupgraded.
**Evidence:** `.dld-version` does not exist anywhere in the repo (Glob confirms). `template/.claude/CUSTOMIZATIONS.md` has only placeholder comments — meaning even DLD itself has never needed a real customization record. The mechanism for knowing "what the user changed" does not exist yet.
**Impact:** High
**Counter:** Ship `v1.0.0` tag + generate `.dld-version` during first `/upgrade` run by hashing all template files against current state. Treat everything that matches template exactly as "unmodified." Everything else = user-modified. First upgrade is lossy but honest.

---

### Argument 2: Renames Are Invisible to File-Diff Logic
**Concern:** 3-way merge assumes file identity is stable. When DLD renames `agents/spark/codebase.md` → `agents/spark/scout-codebase.md`, the script sees "old file deleted + new file added." It will NOT present this as a rename — it will silently delete the user's customized version and add the template's new file. User's changes in the renamed file are gone.
**Evidence:** The existing `check-sync.sh` at `template/scripts/check-sync.sh` uses `comm` on file lists — pure path comparison, zero rename detection. The same conceptual flaw will transfer to an upgrade script unless explicitly solved. DLD already has real renames in history (agents were restructured, `planner.md` exists in root agents but not in template).
**Impact:** High
**Counter:** Maintain an explicit rename manifest in `.dld-version` as a migration table: `{"renames": [{"from": "old/path", "to": "new/path", "version": "2.2.0"}]}`. Script checks this before diffing. Added overhead, but the only correct solution.

---

### Argument 3: Markdown Merge Produces Semantically Broken Prompts
**Concern:** A 3-way merge on `SKILL.md` or an agent prompt is structurally meaningless. Agent prompts are not code — they have implicit ordering, context dependencies, and semantic weight per paragraph. A line-level merge conflict in `agents/spark/external.md` could produce a grammatically valid but functionally incoherent prompt. Claude will process it without error but behave unexpectedly.
**Evidence:** `template/.claude/skills/spark/SKILL.md` is 135 LOC of structured prose with embedded YAML frontmatter, markdown headers, and code blocks. A diff3 merge on this file can produce output like: `<<<<<<< yours` inside a `## STRICT RULES` section, which Claude will read as literal instruction text. No test can catch behavioral regression from a merged prompt without an LLM-as-Judge eval.
**Impact:** High — Silent failure mode. No error, just degraded agent behavior.
**Counter:** Treat ALL `.md` files in `.claude/` as **non-mergeable**. Policy: if user modified it AND template changed it → show diff, require explicit human choice (keep mine / take theirs / open editor). Never auto-merge prompts.

---

### Argument 4: Network Dependency Makes This Unreliable as a Skill
**Concern:** The skill needs to fetch from GitHub to get the latest template. This introduces: (a) GitHub rate limits (60 req/hr unauthenticated), (b) network unavailability on flights/hotel WiFi/CI environments, (c) version drift if user is on a private fork or internal mirror.
**Evidence:** The existing scripts (`check-sync.sh`, `install-hooks.sh`) make zero network calls — they compare local `template/` against root `.claude/`. This is intentional: DLD ships with a local `template/` copy. The upgrade model must decide: "fetch from GitHub OR use local template copy." Using local copy means version = last `git pull`, not latest GitHub.
**Impact:** Medium
**Counter:** Two-mode design: (1) `--local` = compare against local `template/` directory (works offline, always available); (2) `--latest` = `git fetch` or `curl` GitHub API (requires network). Default to `--local` with explicit opt-in for `--latest`. This removes network as a hard dependency.

---

### Argument 5: "Upgrade" Is a Fear-Inducing Word With No Rollback Story
**Concern:** Users will not run `/upgrade` if they fear losing their customized hooks, modified skill prompts, or project-specific rules. Without a clear rollback story, adoption will be near zero. The CUSTOMIZATIONS.md mechanism is currently just a comment template with zero enforcement.
**Evidence:** `template/.claude/CUSTOMIZATIONS.md` lines 9-21: all sections are `<!-- Add your ... here -->` placeholders. The `hooks.config.mjs` has `excludeFromSync` for 5 specific files but no general mechanism for user-declared protected files. The pre-edit hook at `template/.claude/hooks/pre-edit.mjs:94` enforces sync zone warnings but cannot tell what IS a customization vs what IS drift.
**Impact:** High — Adoption risk. A feature nobody runs has zero value.
**Counter:** Mandatory pre-upgrade snapshot: `git stash` or commit all changes before upgrade runs. Upgrade script must fail with clear error if working tree is dirty. Rollback = `git stash pop` or `git revert`. This is the entire rollback story — leverage git, don't invent a new mechanism.

---

### Argument 6: Hooks Have a Node.js Version Dependency With No Runtime Check
**Concern:** `.mjs` hooks use ES module syntax and specific Node.js built-ins. If a user has Node 14 (below the 18+ requirement), new hooks from an upgrade will silently fail or crash. Claude Code's fail-safe ADR-004 means hook crashes are swallowed — the user gets no protection AND no error message.
**Evidence:** `template/.claude/hooks/package.json` specifies `"type": "module"` but no `"engines"` field. `CLAUDE.md` lists "Node.js 18+" as prerequisite but there is no runtime enforcement anywhere in the hook chain. `run-hook.mjs` exists but was not read — likely has no version guard either.
**Impact:** Medium — Affects users who haven't updated Node.js
**Counter:** Add to upgrade script: `node --version` check before applying any hook files. If < 18, warn and skip hook updates with explicit message: "Hooks require Node 18+. Your version: X. Skipping hook upgrade."

---

### Argument 7: Scope — How Often Will Users Actually Upgrade?
**Concern:** DLD is a framework for building products. Users install once, customize heavily, then stop tracking upstream. The realistic upgrade frequency is: (a) never, for most users; (b) monthly, for active DLD contributors/followers; (c) at a new project start, where they'd just clone fresh anyway. The upgrade path primarily serves case (b) — a small minority.
**Evidence:** The template sync mechanism already exists (`check-sync.sh`, `template-sync.md` rule) and is explicitly manual-review-only ("Review divergence manually. Not all differences need syncing."). This reflects the real-world reality: DLD upgrades are infrequent and judgment-intensive. Automating judgment is the risk.
**Impact:** Medium — ROI risk. High complexity for low-frequency use.
**Counter:** Validate demand before building. Ask: how many users are on DLD? How many have upgraded manually? If the answer is "2-3 people including us," the diff-viewer alternative (see below) is the correct scope.

---

### Argument 8: Testing a Multi-Version Upgrade Script Is Combinatorially Explosive
**Concern:** To test `/upgrade` correctly you need: (M versions of DLD) × (N user customization patterns) × (K operating systems) test scenarios. Even at M=3, N=5, K=2 that is 30 test scenarios, each requiring a real DLD installation in a specific state.
**Evidence:** The existing hook tests in `template/.claude/hooks/__tests__/` test pure functions against mocked input — no integration tests, no multi-version scenarios. The upgrade script would need a new test category that doesn't exist: "filesystem state machine tests" where the input is a directory tree in a specific version state.
**Impact:** Medium — Testing debt accumulates silently
**Counter:** Define the minimum test matrix before writing code: versions (current, current-1, pre-version-tracking), customization states (clean install, modified hooks, modified skills, added custom rules). If the matrix is > 12 scenarios, treat as P0 testing requirement, not P1.

---

## Simpler Alternatives

### Alternative 1: Enhanced Diff Viewer (80% value, 10% complexity)
**Instead of:** Full upgrade automation with 3-way merge, version tracking, rollback
**Do this:** Extend `check-sync.sh` to output a rich diff report. Add a `/upgrade-check` skill command that runs the script and presents changes in grouped form: "These files changed in template, you haven't modified them — safe to copy. These files changed in both — here's the diff, you decide." User copies what they want manually.
**Pros:** Zero merge risk. Zero rollback complexity. Uses existing `check-sync.sh` infrastructure. No network dependency. Works for all user states including pre-version-tracking.
**Cons:** Manual copy required. Doesn't scale to 50+ changed files in a major DLD release.
**Viability:** High — This is what most developers actually do with framework updates.

---

### Alternative 2: Selective Upgrade by Category
**Instead of:** Full file tree upgrade with 3-way merge
**Do this:** Categorize DLD files into: (A) pure template files — user never modifies (e.g., `agents/council/`, most scripts); (B) configurable files — user extends but doesn't rewrite (e.g., `hooks.config.mjs`); (C) user-owned files — user fully customizes (e.g., `rules/localization.md`, `CLAUDE.md`). Upgrade only category A automatically. Prompt for B. Skip C entirely.
**Pros:** Eliminates merge conflicts on the files that matter most. Category A upgrades are safe and unambiguous.
**Cons:** Requires maintaining the category list. Disagreement on which files are A vs B vs C.
**Viability:** Medium — Good design, but the category list becomes a maintenance burden.

---

### Alternative 3: New Project Bootstrap With Migration Guide
**Instead of:** In-place upgrade of existing projects
**Do this:** When a user wants the latest DLD, they clone fresh and run `/retrofit` on their existing project to bring it into the new structure. Migration guide = a markdown checklist of what changed between versions.
**Pros:** Clean slate. No merge conflicts. Retrofit skill already exists. Users get the full new DLD experience.
**Cons:** More work for the user. Their git history is separate. Not suitable for mid-project upgrades.
**Viability:** Low for mid-project, High for new-project starts.

---

**Verdict:** Alternative 1 (Enhanced Diff Viewer) solves 80% of the real need — knowing what changed and safely applying non-conflicting updates — with a fraction of the complexity. Build that first. If users consistently need automated merge for 20+ files at a time, escalate to the full implementation.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | No `.dld-version` present | Fresh DLD install, run upgrade | Script detects missing version, initializes baseline from current template hash, warns user | High | P0 | deterministic |
| DA-2 | Template file renamed between versions | User has `agents/spark/codebase.md` modified, template renamed it | Script detects rename via manifest, presents diff against new path, does NOT silently delete user file | High | P0 | deterministic |
| DA-3 | Both user and template modified same `.md` file | `hooks.config.mjs` modified by user AND changed in template | Script presents full diff, requires explicit human choice — does NOT auto-merge | High | P0 | deterministic |
| DA-4 | Working tree is dirty | Uncommitted changes exist, user runs `/upgrade` | Script exits with error: "Commit or stash changes before upgrading" | High | P0 | deterministic |
| DA-5 | Node.js version below 18 | `node --version` returns `v16.x.x` | Script skips hook file upgrades, warns user with explicit version requirement | Medium | P1 | deterministic |
| DA-6 | No network access, `--latest` flag | `curl` to GitHub API fails | Script exits with clear error: "Cannot fetch latest. Use --local for offline upgrade." | Medium | P1 | deterministic |
| DA-7 | User added a custom file in `.claude/` | `rules/my-custom-rule.md` exists, not in template | Script preserves it untouched, does not delete files that exist only in user's project | High | P0 | deterministic |
| DA-8 | Clean install, no customizations | All `.claude/` files match template exactly | Script upgrades all changed files automatically, no prompts, reports N files updated | Low | P1 | deterministic |
| DA-9 | Upgrade from 2 versions behind | User on v1.0, template at v1.2 — v1.1 had a rename | Rename manifest covers cumulative renames across skipped versions | Medium | P1 | deterministic |
| DA-10 | Skill file with YAML frontmatter | `agents/coder.md` has `---` frontmatter block | Merge/diff handles frontmatter correctly — not treated as conflict marker | Medium | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | Pre-edit hook sync zone warning | `template/.claude/hooks/pre-edit.mjs:94` | Sync zone check still fires correctly after upgrade modifies `.claude/` files | P0 |
| SA-2 | `check-sync.sh` output | `template/scripts/check-sync.sh:12` | Script still runs correctly if upgrade script changes file layout | P1 |
| SA-3 | `hooks.config.mjs` excludeFromSync list | `template/.claude/hooks/hooks.config.mjs:85` | User-declared custom exclusions survive upgrade | P0 |
| SA-4 | Autopilot state files | `.claude/scripts/autopilot-state.mjs` | In-progress autopilot runs are not disrupted by `.claude/` file upgrades | P1 |

### Assertion Summary
- Deterministic: 10 | Side-effect: 4 | Total: 14

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| Pre-edit hook sync zone check | `template/.claude/hooks/pre-edit.mjs:94-111` | Upgrade script modifies `.claude/` files, which are in the sync zone — hook will fire during upgrade itself | Upgrade script must temporarily disable or bypass sync zone hook, OR run outside Claude Code session |
| `check-sync.sh` | `template/scripts/check-sync.sh:12-40` | Assumes `template/.claude/` is the reference. After upgrade, reference has changed. Script output meaning shifts. | Document that `check-sync.sh` compares LOCAL template to root — not GitHub. |
| `CUSTOMIZATIONS.md` | `template/.claude/CUSTOMIZATIONS.md:1` | Currently a placeholder. Upgrade script needs it to be a machine-readable registry of user customizations to know what NOT to overwrite | Upgrade depends on this file having real content — bootstrapping problem |
| hooks.config.local.mjs pattern | `template/.claude/hooks/hooks.config.mjs:8` | Users may have `hooks.config.local.mjs` overrides. Upgrade script must detect and not overwrite this file | Add `hooks.config.local.mjs` to upgrade exclusion list |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| `.dld-version` file | data | High — does not exist, must be created | Define schema before implementation. JSON with: `{"version": "...", "installed_at": "...", "file_hashes": {...}, "renames": [...]}` |
| `template/` local directory | filesystem | Medium — upgrade via `--local` depends on this always being present | Document that `git pull` on DLD repo is how `template/` gets updated |
| GitHub API / `git fetch` | network | Medium — `--latest` mode | Rate limit 60/hr unauthenticated; require GitHub token for reliable use |
| Node.js 18+ | runtime | Medium — hooks won't work on older Node | Runtime check before applying hook upgrades |
| `CUSTOMIZATIONS.md` | data | High — must be machine-readable for upgrade to respect user changes | Define and enforce structured format before upgrade feature ships |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** What is the canonical source of truth for "latest DLD version" — GitHub tags, local `template/` directory, or something else?
   **Why it matters:** Determines whether network is required. Local-only = always works, never truly "latest." GitHub = requires auth for reliable rate limits.

2. **Question:** What is the schema for `.dld-version`? Specifically: does it store per-file hashes (to detect user modifications) or just a version string?
   **Why it matters:** Per-file hashes = upgrade can be smart about what was modified. Version string only = upgrade must ask about every changed file. These are fundamentally different UX models.

3. **Question:** Are agent `.md` prompt files treated as non-mergeable (human choice required) or as mergeable (3-way diff)?
   **Why it matters:** If prompt files are mergeable, a corrupted merge produces silent behavioral regression with no error signal. This is the highest-severity silent failure mode in the entire feature.

4. **Question:** Does the upgrade script run INSIDE a Claude Code session (as a skill) or OUTSIDE (as a standalone bash script)?
   **Why it matters:** Running inside a session means hooks will fire during the upgrade itself (pre-edit sync zone warnings on every `.claude/` file write). Running outside bypasses hooks entirely. Each has different safety implications.

5. **Question:** What is the minimum viable upgrade scenario? Is it "update hooks only" (safe, deterministic) or "update all template files" (complex, risky)?
   **Why it matters:** Hooks are the highest-value upgrade target (bug fixes, new safety rules). Skills and agents carry customization risk. Separating these two categories reduces scope by ~60%.

---

## Final Verdict

**Recommendation:** Proceed with caution — but validate the scope first.

**Reasoning:** The feature has a real problem to solve but the proposed scope (full 3-way merge with version tracking) is substantially more complex than it appears. Three P0 risks are unresolved: (1) the chicken-and-egg bootstrap problem for existing users, (2) silent behavioral regression from auto-merging prompt files, and (3) the rename-detection gap. The simpler alternative (enhanced diff viewer) likely delivers 80% of the value for 10% of the complexity and should be validated first.

The single highest-ROI narrow scope: **"upgrade hooks only."** Hooks are pure logic (not customized by users), carry real security value when updated, and the upgrade is deterministic — replace the file, check Node version, done. No merge conflicts, no prompt corruption risk, clear rollback (git stash).

**Conditions for success:**
1. Define `.dld-version` schema before writing any code — it is the foundation everything else depends on
2. Treat all `.md` files in `.claude/` as non-mergeable — human choice required when both sides changed
3. Mandatory dirty-tree check before upgrade starts — git must be clean
4. Rename manifest is P0, not optional — without it, any DLD refactor silently destroys user customizations
5. Ship the diff-viewer (Alternative 1) first as v0.1, validate real user behavior, then decide if full automation is warranted
