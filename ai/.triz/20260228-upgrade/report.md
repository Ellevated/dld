# System Health Report: DLD /upgrade Mechanism

**Date:** 2026-02-28
**Target:** /Users/desperado/dev/dld
**Question:** Hidden negative consequences of /upgrade mechanism -- what systemic risks remain beyond pyproject.toml overwrite?
**Method:** TOC + TRIZ System Diagnostics

---

## System Metrics Summary

### File Churn (last 6 months)

| Module | Changes | Files | Tests | Churn Rate |
|--------|---------|-------|-------|------------|
| upgrade.mjs (engine) | 3 | 1 | 0 | LOW -- but 0 tests for 394 LOC destructive code |
| template/.claude/hooks | 84 | 9 | 11 | HIGH -- best-tested module, but BYPASSED during upgrade |
| template/.claude/agents/bug-hunt | 96 | 12 | 0 | HIGH -- co-changes as a unit (8x) |
| template/.claude/skills/spark | 62 | 4 | 0 | HIGH -- bug-mode.md alone: 29 changes |
| template/.claude/skills/autopilot | 58 | 7 | 0 | HIGH -- co-changes with spark (5x) |
| template/.claude/rules | 40 | 5 | 0 | HIGH -- in SAFE_GROUPS, auto-applied |
| template/CLAUDE.md | 28 | 1 | 0 | HIGH -- PROTECTED, never reaches users |

### Co-Change Clusters

| Cluster | Files | Co-changes | Risk |
|---------|-------|------------|------|
| Bug-hunt pipeline | orchestrator + validator + bug-mode + model-capabilities | 8 | Spans agents/ + skills/ + rules/ -- current grouping splits this unit |
| Hook system | pre-edit + utils + validate-spec + hooks.config | 6 | Auto-applied as group, but hooks.config has user customizations |
| Core skills | autopilot/SKILL + spark/completion + spark/bug-mode + council/SKILL | 5 | NOT in SAFE_GROUPS -- each requires manual review = fatigue |
| Release bundle | CLAUDE.md + localization + release/SKILL | 3 | CLAUDE.md is PROTECTED -- version bumps never propagate |

---

## TOC Analysis

### Core Constraint

**No upgrade contract -- no formal specification of what constitutes a correct, safe, reversible upgrade operation.**

**Type:** POLICY

The upgrade engine was conceived as a "smart `cp -r`" utility, not as a safety-critical state transition system. Without a contract, every discovered bug leads to a reactive patch (e.g., adding pyproject.toml to PROTECTED), and the PROTECTED set grows ad-hoc while the actual risk surface remains unknown.

### Current Reality Tree

```
ROOT: upgrade.mjs operates OUTSIDE the system it maintains
  |
  +-- No contract defining correct upgrade behavior
  |     |
  |     +-- UDE-1: Zero tests (nothing to test AGAINST)
  |     |     +-- UDE-5: No backup/rollback (no definition of "safe apply")
  |     |           +-- UDE-2: Silent self-overwrite (no special-casing for engine)
  |     |
  |     +-- UDE-7: skip[] is dead code (no version comparison logic)
  |           +-- UDE-9: Hardcoded version string (not designed as gating mechanism)
  |
  +-- Engine operates BELOW the hook layer but modifies it
  |     |
  |     +-- UDE-3: Hooks fully bypassed (cpSync is not a Claude tool call)
  |           +-- UDE-4: hooks.config.mjs silently overwritten (in SAFE_GROUPS)
  |
  +-- Files treated as isolated blobs, not versioned interdependent system
        |
        +-- UDE-8: 39-file manual review = upgrade fatigue
        +-- UDE-11: CLAUDE.md (28 changes) never reaches users
        +-- UDE-6: Zombie files accumulate (no file lifecycle model)
        +-- UDE-10: Groups by directory, not by functional dependency
```

**Convergence:** ALL chains converge on the missing contract. Without it: no tests (what would they assert?), no rollback (what state to restore?), no hooks (what invariants to check?), no versioning (what semantics to compare?).

### Evaporating Clouds

| Conflict | Hidden Assumption | Resolution |
|----------|-------------------|------------|
| Overwrite to deliver vs. overwrite destroys config | Overwrite is the only delivery mechanism | Three-phase apply: backup, apply, validate. Rollback on failure. |
| Auto-apply for speed vs. manual review for safety | Safety = human review | Safety through CONTRACT: automated tests validate post-apply, backup exists for rollback. Human reviews the contract once; machine enforces it every time. |
| Engine must be upgradable vs. engine must be trustworthy | upgrade.mjs is just another framework file | Treat engine as INFRASTRUCTURE -- separate trust tier, always show diff, never auto-apply. |
| Hooks must validate all writes vs. upgrade needs direct filesystem | Hooks can only fire on Claude tool calls | Post-upgrade validation pass: engine calls validator as final step (separation in time). |

---

## TRIZ Analysis

### Ideal Final Result

"The upgrade engine ITSELF delivers every framework improvement to every user WITHOUT destroying customizations, WITHOUT bypassing safety hooks, WITHOUT requiring manual review of 39 files, and WITHOUT being able to silently corrupt its own logic."

### Contradictions Found

| # | Type | Contradiction | Separation Principle | Solution |
|---|------|---------------|---------------------|----------|
| TC-1 | Technical | Fast auto-delivery vs. configuration safety | -- | Extract volatile from stable: hooks.config.mjs = pure default, all customizations in .local.mjs |
| TC-2 | Technical | Framework coverage vs. engine trustworthiness | -- | Segmentation: INFRASTRUCTURE category, never auto-applied |
| TC-3 | Technical | Deterministic filesystem ops vs. hook enforcement | -- | Pre/post validation sandwich: hooks before + after, cpSync during |
| TC-4 | Technical | PROTECTED CLAUDE.md vs. stale framework content (28 changes) | -- | Section markers: `<!-- DLD:BEGIN -->` / `<!-- DLD:END -->` for framework zones |
| TC-5 | Technical | Simple file-copier vs. zombie accumulation | -- | Deprecation manifest (.claude/deprecated.json) + --cleanup flag |
| TC-6 | Technical | Per-file review thoroughness vs. upgrade adoption | -- | Functional unit batching: 39 files -> 8-10 named units from co-change data |
| PC-1 | Physical | upgrade.mjs must/must not be upgradable | Separation in condition | Upgradable WHEN user explicitly approves; non-upgradable during batch auto-apply |
| PC-2 | Physical | Hook enforcement must/must not be universal | Separation in time | Enforce BEFORE and AFTER upgrade, not DURING |
| PC-3 | Physical | CLAUDE.md must/must not be mutable | Separation in space | Framework sections inside markers update; user sections outside never touched |
| PC-4 | Physical | File overwrite must/must not be immediate | Separation in time | git stash before, validate after, stash pop on failure |
| PC-5 | Physical | Group granularity must/must not be coarse | Separation in scale | Macro (directory) for simple; micro (functional unit) for cross-cutting |
| PC-6 | Physical | Version tracking must/must not be present | Separation in condition | Passive receipt on write, active gate on read |

### Unused Resources

1. **Co-change data** -- already collected in git log, not used by upgrade.mjs for functional unit grouping
2. **Git diff output** -- generated by showDiff() but only shown to human, never parsed for automated risk detection
3. **hooks.config.local.mjs** -- override mechanism exists but upgrade never offers migration when detecting divergence
4. **.dld-version skip[]** -- written every time, never read -- storage exists, read path missing
5. **Post-upgrade Step 5** -- already re-runs --analyze but does not validate state (hooks loading, settings parsing)
6. **Git tags** -- contain semantic version info, upgrade.mjs uses hardcoded '3.9.0' instead
7. **CI pipeline** -- smoke-test.yml tests hooks but has zero coverage of upgrade.mjs

---

## Recommendations (prioritized by leverage)

| # | Recommendation | Source | Leverage | Effort |
|---|---------------|--------|----------|--------|
| 1 | Define upgrade contract specification | TOC core constraint + ADR-011 | HIGH (Meadows 5: system rules) | MEDIUM |
| 2 | Move upgrade.mjs to INFRASTRUCTURE category (never auto-apply) | TRIZ PC-1, TC-2 | HIGH (Meadows 5: system rules) | LOW |
| 3 | Add git-stash backup + post-apply validation | TRIZ PC-4, TC-3, TOC EC-4 | HIGH (Meadows 6: information flows) | LOW |
| 4 | Move hooks.config.mjs to PROTECTED, enforce .local.mjs pattern | TRIZ TC-1, TOC UDE-4 | MEDIUM (Meadows 9: delays) | LOW |
| 5 | Add CLAUDE.md section-sync with DLD markers | TRIZ PC-3, TC-4 | MEDIUM (Meadows 6: information flows) | MEDIUM |
| 6 | Add CI smoke tests for upgrade.mjs | TOC UDE-1, ADR-011 | MEDIUM (Meadows 5: system rules) | MEDIUM |
| 7 | Add deprecation manifest + zombie file detection | TRIZ TC-5 | LOW (Meadows 9: delays) | LOW |

### Recommendation Details

#### 1. Define upgrade contract specification

**Source:** TOC core constraint (POLICY: no upgrade contract) + ADR-011 (Enforcement as Code)
**Leverage:** Meadows 5 (system rules) -- changes the rules by which the upgrade engine operates, from ad-hoc reactive patches to a formal specification that all other improvements derive from
**Effort:** MEDIUM (document, not code -- but requires careful thought)

**What to do:**
1. Create `.claude/contracts/upgrade-contract.md` defining:
   - **INVARIANTS:** No file outside UPGRADE_SCOPE modified. No PROTECTED file modified. Every modified file has a backup path. Engine integrity verified before execution. Hooks load successfully after upgrade. .dld-version accurately reflects applied state.
   - **FILE LIFECYCLE:** States = added, modified, deprecated, removed. Propagation rules for each.
   - **ATOMICITY:** Either all files in a functional unit are applied, or none.
   - **REVERSIBILITY:** Any upgrade can be undone within the same session (git stash).
2. Use this contract as the test specification for recommendation #6.
3. Review the contract with `/council` -- it defines the trust boundary for all DLD users.

**Expected impact:** Converts reactive patching (add X to PROTECTED after it breaks) into proactive design. Every future upgrade.mjs change is validated against the contract. This is the constraint that, once resolved, makes all other UDEs addressable.

---

#### 2. Move upgrade.mjs to INFRASTRUCTURE category

**Source:** TRIZ PC-1 (separation in condition) + TC-2 (#1 Segmentation)
**Leverage:** Meadows 5 (system rules) -- changes the classification rules that determine what auto-applies
**Effort:** LOW (15-30 min code change)

**What to do:**
1. Add `INFRASTRUCTURE` set in upgrade.mjs:
   ```javascript
   const INFRASTRUCTURE = new Set([
     '.claude/scripts/upgrade.mjs',
     '.claude/hooks/run-hook.mjs',
   ]);
   ```
2. In `resolveTargets()`, exclude INFRASTRUCTURE files from group-based apply. Only process them when `--files` explicitly names them.
3. When analyze() detects INFRASTRUCTURE changes, output a distinct warning: `"ENGINE UPDATE: upgrade.mjs has a new version. Review with --diff --file .claude/scripts/upgrade.mjs"`
4. The SKILL.md prompt should present engine updates as a separate, named step with explicit approval.

**Expected impact:** Eliminates silent self-modification. The engine that governs all upgrades cannot modify its own logic without explicit user consent. Breaks the trust-chain vulnerability (TC-2).

---

#### 3. Add git-stash backup + post-apply validation

**Source:** TRIZ PC-4 (separation in time) + TC-3 (#10 preliminary action) + TOC EC-4 (post-upgrade validation)
**Leverage:** Meadows 6 (information flows) -- adds a feedback loop where the system detects and reports its own post-upgrade state
**Effort:** LOW (30-45 min -- ~25 lines of code)

**What to do:**
1. Before `apply()`, create a git stash reference:
   ```javascript
   const stashRef = execSync('git stash create', { encoding: 'utf-8' }).trim();
   ```
2. After `apply()`, run `validate()`:
   - Verify no PROTECTED file was modified (compare SHA before/after)
   - Dynamic `import()` of hooks.config.mjs to verify it loads
   - Verify .claude/settings.json parses as valid JSON
   - Log every cpSync to `.dld-upgrade-log` (audit trail)
3. If `validate()` fails and stashRef is non-empty:
   ```javascript
   execSync('git checkout -- .'); // restore all tracked files
   ```
4. Report validation results in JSON output.

**Expected impact:** Eliminates unrecoverable mixed state (UDE-5). Creates audit trail for manual rollback. Compensates for hook bypass (UDE-3) with equivalent post-apply checks. Uses existing git infrastructure -- zero new dependencies.

---

#### 4. Move hooks.config.mjs to PROTECTED, enforce .local.mjs pattern

**Source:** TRIZ TC-1 (#2 Taking out) + TOC UDE-4
**Leverage:** Meadows 9 (delays) -- prevents delayed discovery of lost customizations
**Effort:** LOW (10 min)

**What to do:**
1. Add `'.claude/hooks/hooks.config.mjs'` to the PROTECTED set in upgrade.mjs.
2. Add a header comment to template's hooks.config.mjs: `// DO NOT EDIT directly. Use hooks.config.local.mjs for customizations (protected from upgrades).`
3. When analyze() detects hooks.config.mjs divergence between user and template, emit a migration suggestion: "Your hooks.config.mjs has custom rules. Consider migrating them to hooks.config.local.mjs (protected from future upgrades)."
4. Update SKILL.md to mention hooks.config.local.mjs during the conflict resolution step.

**Expected impact:** Eliminates the most immediate data-loss risk. User's current hooks.config.mjs customization (git-local-folders.md in excludeFromSync) is preserved. The existing .local.mjs override mechanism (unused resource #3) becomes the standard path.

---

#### 5. Add CLAUDE.md section-sync with DLD markers

**Source:** TRIZ PC-3 (separation in space) + TC-4 (#1 Segmentation)
**Leverage:** Meadows 6 (information flows) -- opens an information flow that is currently blocked (28 changes never reaching users)
**Effort:** MEDIUM (2-3 hours)

**What to do:**
1. Add markers to template/CLAUDE.md around framework sections:
   ```
   <!-- DLD:BEGIN:skills-table -->
   | Skill | When |
   |-------|------|
   ...
   <!-- DLD:END:skills-table -->
   ```
   Sections to mark: skills-table, flows, key-rules, project-structure, task-statuses.
2. Add `patchCLAUDE()` function to upgrade.mjs:
   - Read user's CLAUDE.md
   - For each `DLD:BEGIN:X` / `DLD:END:X` block, replace content from template
   - Leave everything outside markers untouched
   - Write back
3. Move CLAUDE.md from PROTECTED to a new `SECTION_SYNC` category.
4. During analyze(), report which sections have updates.

**Expected impact:** Resolves the highest-churn file problem (28 changes). Users receive framework updates (skill tables, flow descriptions, version strings) while their project-specific content (name, stack, domains) is never touched. Skills that reference CLAUDE.md sections will match the user's actual content.

---

#### 6. Add CI smoke tests for upgrade.mjs

**Source:** TOC UDE-1 + ADR-011 (Enforcement as Code)
**Leverage:** Meadows 5 (system rules) -- adds a hard gate preventing broken upgrades from shipping
**Effort:** MEDIUM (2-3 hours)

**What to do:**
1. Create `template/.claude/scripts/__tests__/upgrade.test.mjs` with tests derived from the contract (#1):
   - Test: PROTECTED files are never modified (create temp project, modify PROTECTED files, run upgrade, verify unchanged)
   - Test: UPGRADE_SCOPE filter excludes non-framework files (ai/, CLAUDE.md, pyproject.toml)
   - Test: Partial failure does not update .dld-version
   - Test: INFRASTRUCTURE files excluded from group-based apply
   - Test: backup is created before first cpSync (after #3)
   - Test: .dld-version reflects actual applied files, not hardcoded string
   - Test: skip[] is honored during analyze (after implementation)
2. Add to CI workflow (smoke-test.yml or new upgrade-test.yml).
3. Make CI gate: upgrade.mjs changes require all tests passing.

**Expected impact:** The most destructive mechanism in the framework (overwrites 146 files) gains deterministic validation. Prevents regressions like the pyproject.toml incident. Aligns with ADR-011.

---

#### 7. Add deprecation manifest + zombie file detection

**Source:** TRIZ TC-5 (#10 preliminary action)
**Leverage:** Meadows 9 (delays) -- reduces delayed accumulation of dead files
**Effort:** LOW (1 hour)

**What to do:**
1. Create `.claude/deprecated.json`:
   ```json
   {
     "3.10": {
       "removed": [],
       "renamed": {}
     }
   }
   ```
2. In analyze(), read deprecated.json. Flag user_only files matching removed/renamed entries:
   ```
   DEPRECATED: agents/old-agent.md was removed in v3.10. Safe to delete.
   RENAMED: agents/foo.md -> agents/bar.md in v3.10.
   ```
3. Add `--cleanup` flag: shows deprecated files, asks for confirmation, moves to `.claude/.upgrade-trash/` (recoverable).
4. Maintain deprecated.json as part of release process.

**Expected impact:** Stops silent zombie accumulation. Users get actionable intelligence about dead weight. No automatic deletion -- preserves the engine's simplicity while adding lifecycle awareness.

---

## Cross-Reference: TOC Constraint -> TRIZ Solutions

| TOC Finding | TRIZ Solutions That Address It |
|-------------|-------------------------------|
| Core constraint: no upgrade contract | TC-3/validate(), PC-4/git-stash, PC-6/version-as-gate -- all require a contract to define "what is correct" |
| Exploitation: move upgrade.mjs to ALWAYS_ASK | PC-1 + TC-2: INFRASTRUCTURE category (stronger than ALWAYS_ASK) |
| Exploitation: move hooks.config.mjs to PROTECTED | TC-1: #2 Taking out -- extract volatile from stable |
| Exploitation: git stash before apply | PC-4: #10 Preliminary action -- exact same solution |
| Elevation: dependency-aware functional units | PC-5 + TC-6: #5 Merging -- co-change data informs unit boundaries |
| Elevation: CLAUDE.md section sync | PC-3 + TC-4: #1 Segmentation -- spatial separation of user/framework zones |
| Subordination: CI not testing upgrade.mjs | Unused resource #7: CI pipeline exists but has zero upgrade coverage |

**Alignment:** TOC and TRIZ converge strongly. No contradictions between the two analyses. TOC exploitation strategies are subsets of TRIZ solutions. TRIZ adds the "how" (specific mechanisms) to TOC's "what" (constraint identification).

---

## Risk Matrix: What Happens If We Do Nothing

| Risk | Probability | Impact | Trigger |
|------|------------|--------|---------|
| hooks.config.mjs overwritten | HIGH (next upgrade) | User loses hook customizations silently | `--apply --groups safe` |
| upgrade.mjs silently self-modifies | HIGH (next upgrade) | New engine logic runs without review | `--apply --groups safe` |
| Stale CLAUDE.md causes skill confusion | MEDIUM (ongoing) | Skills reference sections user doesn't have | Any skill invocation |
| Partial apply leaves mixed state | LOW (disk/permission error) | Unrecoverable, no audit trail | Hardware failure during apply |
| Supply chain injection | VERY LOW | Malicious hooks execute arbitrary JS | MITM on GitHub clone |

---

## Next Steps

- [ ] `/spark` spec for recommendation #1 (upgrade contract) -- this is the foundational document
- [ ] Implement #2 (INFRASTRUCTURE category) and #4 (hooks.config.mjs PROTECTED) -- both LOW effort, immediate risk reduction
- [ ] Implement #3 (git-stash + validation) -- LOW effort, high safety improvement
- [ ] `/council` debate on recommendation #5 (CLAUDE.md section-sync) -- involves UX tradeoffs around marker preservation
- [ ] `/spark` spec for recommendation #6 (CI tests) -- requires contract (#1) as input
- [ ] Track #7 (deprecation manifest) for next release cycle

**Recommended execution order:** #2 + #4 (10 min, immediate risk reduction) -> #3 (30 min, safety net) -> #1 (contract document) -> #6 (CI tests based on contract) -> #5 (CLAUDE.md sync) -> #7 (deprecation manifest)
