# Codebase Research — Upgrade skill-writer → skill-creator (TECH-145)

## Existing Code

### Reusable Modules

| Module | File:line | Description | Reuse how |
|--------|-----------|-------------|-----------|
| `eval-judge` agent | `.claude/agents/eval-judge.md:1` | 5-dimension rubric scorer (sonnet, effort:high) | Import directly — grader IS eval-judge |
| `eval-agents.mjs` | `.claude/scripts/eval-agents.mjs:1` | Scans test/agents/ for golden datasets, returns JSON task list | Pattern for run_eval script structure |
| `eval-judge.mjs` | `.claude/scripts/eval-judge.mjs:1` | Parses Eval Criteria from spec, extracts by type | Pattern for parsing prompt output |
| `/eval` skill | `.claude/skills/eval/SKILL.md:1` | Orchestrates golden-dataset eval loop (scan → run → judge → report) | Pattern only — new loop is prompt-level not file-level |
| Three-Expert Gate | `.claude/skills/skill-writer/SKILL.md:201` | Karpathy/Sutskever/Murati compression gate for UPDATE mode | Keep intact in UPDATE mode |
| Preservation Checklist | `.claude/skills/skill-writer/SKILL.md:184` | Critical guard against removing protective sections | Keep intact |

### Similar Patterns

| Pattern | File:line | Description | Similarity |
|---------|-----------|-------------|------------|
| Eval iteration loop | `.claude/skills/eval/SKILL.md:19-55` | scan → run agent → judge → aggregate | Exact pattern for skill-creator CREATE loop |
| Agent frontmatter | `template/.claude/skills/skill-writer/SKILL.md:64-87` | `name/description/model/tools` template | Hybrid frontmatter extends this |
| `project_agnostic` field | Not yet present | Missing from current frontmatter | New addition needed |
| `allowed_tools` field | Not yet present | Missing from current frontmatter | New addition needed |
| Python scripts | `scripts/pre-review-check.py:1` | Only Python script in repo — deterministic checks | Pattern for run_eval.py, improve_description.py, aggregate_benchmark.py |
| mjs scripts | `.claude/scripts/eval-agents.mjs:1` | Node.js scripts pattern (dominant in .claude/scripts/) | Alternative to Python — check feature intent |

**Recommendation:** The `eval-judge` agent is a direct reuse target for the `grader` role. The `/eval` skill flow is the exact pattern for the CREATE iteration loop. Python scripts exist in `scripts/` (root) but NOT in `.claude/scripts/` — all `.claude/scripts/` are `.mjs`. Decision needed: Python or mjs for `run_eval`, `improve_description`, `aggregate_benchmark`.

---

## Impact Tree Analysis

### Step 1: UP — Who uses changed code?

```bash
grep -rn "skill-writer" . --include="*.md" --include="*.sh" --include="*.json"
# Results: 14 occurrences across 9 files
```

| File | Line | Usage |
|------|------|-------|
| `CLAUDE.md` | 156 | Skills table entry |
| `template/CLAUDE.md` | 157 | Skills table entry |
| `.claude/skills/reflect/SKILL.md` | 20, 142, 148, 154, 171, 180-182, 186, 207 | 10 references — reflect handoff target |
| `template/.claude/skills/reflect/SKILL.md` | same as above | mirror |
| `.claude/skills/autopilot/SKILL.md` | 239 | "Creating skills: `/skill-writer create` skill" reference |
| `template/.claude/skills/autopilot/SKILL.md` | same | mirror |
| `scripts/smoke-test.sh` | 154 | REQUIRED_SKILLS array |
| `template/scripts/smoke-test.sh` | 154 | REQUIRED_SKILLS array |
| `docs/15-skills-setup.md` | 46, 101, 209 | Documentation — skills table, file structure, settings.json example |

### Step 2: DOWN — What does it depend on?

| Dependency | File | Usage |
|------------|------|-------|
| Exa MCP | frontmatter implicit | Research phase (max 3 calls) |
| `wc -l` bash | SKILL.md:245 | Line count validation |
| `CLAUDE.md` | target | Registration of new skills |
| `.claude/agents/*.md` | target | Agent files created by CREATE mode |
| `.claude/skills/*/SKILL.md` | target | Skill files created by CREATE mode |
| `.claude/rules/*.md` | target | Updated by UPDATE mode |

### Step 3: BY TERM — Grep key terms

```bash
grep -rn "skill-writer" . --include="*.md" --include="*.sh"
# Results: 14 occurrences (see Step 1 above)

grep -rn "skill.creator" .
# Results: 0 — does not exist yet

grep -rn "grader\|comparator\|analyzer" . --include="*.md" --include="*.mjs"
# Results: 0 — none of the new agents exist yet

grep -rn "run_eval\|improve_description\|aggregate_benchmark" .
# Results: 0 — scripts don't exist yet
```

| File | Line | Context |
|------|------|---------|
| `.claude/rules/localization.md` | — | "skill-writer" NOT present — no Russian trigger for it currently |
| `template/.claude/rules/localization.md` | — | Spanish template also has no skill-writer trigger |
| `docs/15-skills-setup.md` | 209 | `settings.json` example with `"name": "skill-writer"` |

### Step 4: CHECKLIST — Mandatory folders

- [x] `scripts/smoke-test.sh` — 1 occurrence at line 154 (REQUIRED_SKILLS array)
- [x] `template/scripts/smoke-test.sh` — 1 occurrence at line 154 (mirror)
- [ ] `db/migrations/**` — N/A (no database in DLD)
- [ ] `ai/glossary/**` — N/A (no domain glossary for this)
- [x] `docs/15-skills-setup.md` — 3 occurrences (lines 46, 101, 209)
- [x] `.claude/scripts/upgrade.mjs` — GROUP_PATTERNS skills group covers `.claude/skills/` — rename is automatically upgrade-safe

### Step 5: DUAL SYSTEM check

The rename `skill-writer → skill-creator` creates a dual-system problem: reflect skill references old name in 10 places. Both must be updated atomically.

Upgrade.mjs has a `deprecated` file cleanup mechanism — old `skill-writer/` directory must be listed as deprecated so `/upgrade` can clean it from user projects.

---

## Affected Files

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `template/.claude/skills/skill-writer/SKILL.md` | 244 | Current skill (universal) | rename dir + rewrite content |
| `.claude/skills/skill-writer/SKILL.md` | 245 | Current skill (DLD copy) | rename dir + rewrite content |
| `template/.claude/skills/reflect/SKILL.md` | ~207 | Calls skill-writer as handoff | modify (10 references) |
| `.claude/skills/reflect/SKILL.md` | 207 | Mirror | modify (10 references) |
| `template/.claude/skills/autopilot/SKILL.md` | ~240 | Mentions skill-writer create | modify (1 reference) |
| `.claude/skills/autopilot/SKILL.md` | 240 | Mirror | modify (1 reference) |
| `template/CLAUDE.md` | 304 | Skills table (skill-writer row) | modify row |
| `CLAUDE.md` | 303 | Skills table (skill-writer row) | modify row |
| `.claude/rules/localization.md` | 35 | Russian triggers — NO entry for skill-writer | add alias for skill-creator |
| `template/.claude/rules/localization.md` | ~35 | Spanish template | add alias (optional) |
| `scripts/smoke-test.sh` | 237 | REQUIRED_SKILLS["skill-writer"] | modify array entry |
| `template/scripts/smoke-test.sh` | 237 | Mirror | modify array entry |
| `docs/15-skills-setup.md` | 447 | 3 references to skill-writer | modify |
| `template/.claude/agents/grader.md` | 0 | New agent: prompt grader | create |
| `.claude/agents/grader.md` | 0 | Mirror | create |
| `template/.claude/agents/comparator.md` | 0 | New agent: prompt comparator | create |
| `.claude/agents/comparator.md` | 0 | Mirror | create |
| `template/.claude/agents/analyzer.md` | 0 | New agent: weakness analyzer | create |
| `.claude/agents/analyzer.md` | 0 | Mirror | create |
| `template/.claude/skills/skill-creator/SKILL.md` | 0 | New skill (renamed + extended) | create |
| `.claude/skills/skill-creator/SKILL.md` | 0 | Mirror | create |
| `.claude/scripts/upgrade.mjs` | ~350 | Deprecated files list for cleanup | modify (add skill-writer to deprecated) |

**Python scripts (if chosen over mjs):**

| File | LOC | Role | Change type |
|------|-----|------|-------------|
| `scripts/run_eval.py` OR `.claude/scripts/run-eval.mjs` | 0 | Run skill against golden prompts, collect output | create |
| `scripts/improve_description.py` OR `.claude/scripts/improve-description.mjs` | 0 | Apply suggested improvement to frontmatter description | create |
| `scripts/aggregate_benchmark.py` OR `.claude/scripts/aggregate-benchmark.mjs` | 0 | Aggregate multi-run scores, compute stats | create |

**Total:** 17 existing files modified, 6-9 files created

---

## Reuse Opportunities

### Import (use as-is)

- `eval-judge` agent — the grader role is identical: takes input + actual output + rubric → returns 5-dimension score. No need to create a new `grader.md`; `eval-judge.md` already does this. Unless the grader needs skill-specific rubric dimensions (e.g., "clarity of activation trigger"), reuse directly.
- `eval-agents.mjs` scan pattern — the directory-walking, config.json loading, golden-pair enumeration logic is the exact structure `run_eval` needs for prompts.

### Extend (subclass or wrap)

- `eval-judge.md` → extend into `grader.md` if skill-specific dimensions are needed beyond the generic 5. Keep `effort: high`, keep `model: sonnet`, but add "Activation Clarity" and "Protective Section Completeness" as 6th/7th dimensions.
- `/eval` SKILL.md → the CREATE mode iteration loop (generate → grade → compare → analyze → improve → repeat) is an extension of the scan→run→judge→report pattern already in `/eval`.

### Pattern (copy structure, not code)

- `test/agents/{agent}/config.json` pattern → create `test/skills/{skill}/config.json` for golden prompt datasets for the skill-creator itself
- `scripts/pre-review-check.py` → confirms Python scripts belong in `scripts/` (root), not `.claude/scripts/` (mjs only). Follow this convention for `run_eval.py` etc.
- `upgrade.mjs` PROTECTED/ALWAYS_ASK/INFRASTRUCTURE sets → the skill rename needs `skill-writer` added to a `DEPRECATED` list so upgrade cleanup handles it automatically for existing DLD users

---

## Git Context

### Recent Changes to Affected Areas

```bash
git log --oneline -5 -- .claude/skills/skill-writer/ template/.claude/skills/skill-writer/
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-02-02 | 3dfcd09 | Ellevated | chore: remove internal folders from tracking |
| 2026-02-02 | 602aa29 | Ellevated | feat(TECH-062): sync template/.claude with root .claude |
| 2026-01-30 | 4f3b5e9 | Ellevated | feat: batch implementation of TECH-025..TECH-029, TECH-034, TECH-043 |
| 2026-01-29 | d3013d2 | Ellevated | fix: restore critical content in skill-writer (102→222 lines) |
| 2026-01-29 | 86baff2 | Ellevado | refactor: Three-Expert compression of skill-writer (299→102 lines, -66%) |

**Observation:** The skill-writer was created in TECH-042 (commit 6110bad), then over-compressed (86baff2), then restored (d3013d2). The current 245-line version is the stabilized form. The restoration commit is important — it means the Three-Expert compression was too aggressive before, and the Preservation Checklist was added as a guard. Do NOT re-compress during the rename.

```bash
git log --oneline -5 -- template/CLAUDE.md
```

| Date | Commit | Author | Summary |
|------|--------|--------|---------|
| 2026-03-01 | 31fbd51 | Ellevated | feat(hooks): deterministic mock ban in integration tests (ADR-013) |
| 2026-02-28 | 94da2d2 | Ellevated | feat(upgrade): register /upgrade skill in CLAUDE.md + localization |
| 2026-02-27 | 6fe2933 | Ellevated | docs: release v3.9 |
| 2026-02-22 | a3295ad | Ellevated | feat(eval): Agent Prompt Eval Suite |
| 2026-02-17 | 43f495d | Ellevated | feat(brandbook): v2 |

**Observation:** CLAUDE.md was updated 2026-03-01 (ADR-013). Current version is stable. The `/eval` skill was added 2026-02-22 — very recent. This means the eval infrastructure (eval-judge.md, eval-agents.mjs, eval-judge.mjs, test/agents/) is mature and tested.

---

## Overlap Analysis: /eval vs skill-creator CREATE loop

The existing `/eval` skill evaluates **existing agents against golden datasets** (test/agents/).

The proposed skill-creator CREATE eval loop evaluates **newly generated skill/agent prompts against golden prompts** during creation. This is a different scope:

| Dimension | /eval skill | skill-creator CREATE loop |
|-----------|-------------|--------------------------|
| What is evaluated | Existing agents | Newly generated prompts |
| Input | Golden task input files | Example activation phrases / edge cases |
| Rubric | Task-specific (test/agents/.../rubric.md) | Prompt quality rubric (structure, clarity, protection) |
| Iteration | One-shot (no loop) | Loop until score >= threshold |
| Output | eval-report.md | Better SKILL.md / agent.md |
| Agents used | eval-judge | grader + comparator + analyzer |

**Conclusion:** No conflict. They serve different purposes. The CREATE loop in skill-creator is analogous to Anthropic's "prompt improvement loop" (generate → evaluate → improve → repeat). The existing `/eval` is for regression testing of deployed agents.

---

## Risks

1. **Risk:** 10 references to `skill-writer` in reflect/SKILL.md — each must be updated precisely
   **Impact:** If any remain, reflect will reference a non-existent skill name
   **Mitigation:** After rename, run `grep -rn "skill-writer" . --include="*.md"` → must return 0. Enforce as acceptance criterion.

2. **Risk:** smoke-test.sh REQUIRED_SKILLS hardcodes "skill-writer"
   **Impact:** Template validation fails after rename — breaking CI smoke test for all new DLD installs
   **Mitigation:** Update both `scripts/smoke-test.sh` and `template/scripts/smoke-test.sh` atomically with the rename.

3. **Risk:** Existing DLD users who already have `.claude/skills/skill-writer/` will have stale directory after upgrading
   **Impact:** `/upgrade` won't remove old skill-writer/ directory automatically unless it's in the deprecated list
   **Mitigation:** Add `".claude/skills/skill-writer/"` to `upgrade.mjs` deprecated files cleanup.

4. **Risk:** template/.claude/skills/skill-writer/ and .claude/skills/skill-writer/ are in DIFFERENT sync states (template has Three-Expert gate out-of-order at line 215 vs root has it correct at line 201)
   **Impact:** Minor divergence — template version has `**STOP:** Did you check Preservation Checklist first?` in the wrong position within the Three-Expert Gate section
   **Mitigation:** Fix this divergence during the rewrite.

5. **Risk:** Python vs mjs decision for new scripts — repo has mixed convention
   **Impact:** `scripts/pre-review-check.py` is the only Python script; all `.claude/scripts/*.mjs` are Node.js
   **Mitigation:** Put Python scripts in `scripts/` (root) per existing convention, OR use mjs in `.claude/scripts/` per dominant pattern. Feature spec should decide. Recommend mjs for consistency with eval-agents.mjs which is structurally similar.

6. **Risk:** New agents (grader, comparator, analyzer) vs reusing eval-judge
   **Impact:** Creating 3 new agents when eval-judge already grades is duplication
   **Mitigation:** Clarify whether grader is eval-judge with different rubric (extend) or a different scoring model (new). If the only difference is rubric content, reuse eval-judge directly and parameterize the rubric. Create new agent files only if the scoring dimensions are fundamentally different.

7. **Risk:** `allowed-tools` and `project-agnostic` frontmatter fields don't exist in current agent/skill schema
   **Impact:** Unknown whether Claude Code's skill loader honors these fields or ignores them
   **Mitigation:** Treat as documentation fields (informational, not enforcement) until Claude Code supports them. Flag in spec.
