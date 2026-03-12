# Devil's Advocate — skill-creator (rename + eval loop upgrade)

## Why NOT Do This?

### Argument 1: Python Scripts in a Node.js Infrastructure
**Concern:** The proposal includes 3 Python scripts (`run_eval`, `improve_description`, `aggregate_benchmark`). DLD's entire scripting layer is Node.js ESM (`.mjs`). All 8 hooks, all 8 scripts in `.claude/scripts/`, all CI runners — Node.js. Python is not declared in any DLD prerequisite. A DLD user who installs DLD on a TS/Node-only project (which is common — see system-blueprint stack) may not have Python at all.
**Evidence:**
- `/Users/desperado/dev/dld/.claude/scripts/` — 8 files, all `.mjs`
- `/Users/desperado/dev/dld/CLAUDE.md` prerequisites: "Node.js 18+" only
- `/Users/desperado/dev/dld/.claude/hooks/post-edit.mjs:9` — ruff is the only non-node dep and it's optional (Python linter for py projects only)
- `/Users/desperado/dev/dld/template/CLAUDE.md` — no Python prerequisite listed
**Impact:** High
**Counter:** Rewrite scripts as `.mjs` (Node 18+ has `fetch` built-in, no extra deps). The existing `eval-agents.mjs` and `eval-judge.mjs` already prove the pattern works. Python adds a runtime dependency that breaks on vanilla Node.js DLD setups.

---

### Argument 2: The Rename Breaks 8 Known Touch Points — With Partial Discovery Risk
**Concern:** The rename `skill-writer → skill-creator` is not cosmetic. At least 8 files reference `skill-writer` by exact name: CLAUDE.md, template/CLAUDE.md, smoke-test.sh, template/smoke-test.sh, docs/15-skills-setup.md, template/skills/reflect/SKILL.md (×5 references), template/skills/autopilot/SKILL.md (×1 reference). The `reflect` skill has the deepest coupling — it generates output with the string "Run /skill-writer" baked into the spec format, and its DoD checklist reads `- [ ] skill-writer applied changes`. Downstream DLD users who have existing reflect specs in-flight will have broken links.
**Evidence:**
- `grep skill-writer` → 8 files, 17+ occurrences
- `/Users/desperado/dev/dld/template/.claude/skills/reflect/SKILL.md:154` — DoD hardcodes `skill-writer`
- `/Users/desperado/dev/dld/template/.claude/skills/reflect/SKILL.md:160,166,183,192,193,194,198,219` — 8 more references
- `/Users/desperado/dev/dld/scripts/smoke-test.sh:154` — smoke test hardcodes skill name in REQUIRED_SKILLS array
- `/Users/desperado/dev/dld/docs/15-skills-setup.md:46,101,209` — docs reference `skill-writer`
**Impact:** High
**Counter:** If proceeding, the rename must update ALL 8 files atomically. The smoke test is the hardest dependency — it checks for `skill-writer` in REQUIRED_SKILLS. Upgrading DLD users (via `/upgrade`) will also need a migration path since their reflect specs, diary entries, and backlog may reference the old name.

---

### Argument 3: Eval Loop Assumes `claude -p` / `claude --print` Subprocess — Fragile in Multiple Environments
**Concern:** The eval-driven iteration loop (draft → test → grade → repeat) is described as using Anthropic's upstream pattern which relies on `claude -p` subprocess calls. The existing `autopilot-loop.sh` already uses `claude --print`. This subprocess pattern breaks in: (a) CI environments without `claude` CLI installed, (b) headless/remote servers, (c) DLD projects that use Claude Code via IDE plugin rather than CLI. The eval loop for skill quality is not a user-facing feature — it's a meta-tool — so it would primarily run on the developer's machine. But users of DLD will encounter it documented and try to use it in unexpected contexts.
**Evidence:**
- `/Users/desperado/dev/dld/scripts/autopilot-loop.sh:117` — `claude --print` with `set +e` wrapper shows this already fails silently
- The eval loop for skill optimization is a tighter loop than autopilot — it needs multiple `claude -p` calls in sequence, multiplying the failure surface
**Impact:** Medium
**Counter:** Document hard prerequisite: "Requires `claude` CLI in PATH". Gate the scripts with `command -v claude || { echo 'ERROR: claude CLI not found'; exit 1; }`. This at least fails fast rather than mysteriously.

---

### Argument 4: Description Optimization — 20 Queries × Train/Test Split = When Does Anyone Actually Run This?
**Concern:** The description optimization with 20 trigger queries and a train/test split is a feature borrowed from Anthropic's internal tooling where they optimize agent routing across thousands of invocations. DLD skill-writer/creator is invoked 1-2x per month per user, for creating new agents or updating rules. The skill auto-selection in CLAUDE.md works because Claude already knows about all skills from the Skills table — it doesn't need an optimized description to route correctly. The 20-query benchmark would cost ~$2-5 per run (20 Claude invocations for testing alone) and produce marginal improvement over manually writing a good description.
**Evidence:**
- DLD skills are loaded via `settings.json` — the `description` field triggers semantic matching, but CLAUDE.md also has an explicit trigger table (`| User says | Skill activated |`) which is the primary routing mechanism
- The `reflect/SKILL.md` already lists "reflection, let's analyze the diary" as triggers — this is manually curated, not benchmarked
- `/Users/desperado/dev/dld/CLAUDE.md:163-189` — Skills table + trigger examples are the actual routing layer
**Impact:** Medium
**Counter:** Remove description optimization from MVP. Ship the eval loop (quality gate on prompt output) but skip the description benchmark. Manual description review via Three-Expert Gate is sufficient for a 1-2x/month tool.

---

### Argument 5: 3 New Agents (grader, comparator, analyzer) vs. Existing eval-judge — Duplication Risk
**Concern:** DLD already has `eval-judge.md` agent and `eval-agents.mjs` + `eval-judge.mjs` scripts. The proposal adds a `grader` agent (sounds like eval-judge), a `comparator` agent, and an `analyzer` agent. This creates two parallel eval systems: one for agent prompt quality (`/eval` skill + `test/agents/`) and one for skill quality (`skill-creator` eval loop). If the grader does what eval-judge does, we have semantic duplication that will diverge over time. DLD's principle is single source of truth.
**Evidence:**
- `/Users/desperado/dev/dld/.claude/agents/eval-judge.md` — exists, rubric-based LLM output scoring
- `/Users/desperado/dev/dld/.claude/skills/eval/SKILL.md` — full orchestration for golden dataset evaluation
- `/Users/desperado/dev/dld/.claude/scripts/eval-agents.mjs` — scan + dispatch already implemented in Node.js
- The `/eval` skill already covers the "evaluate agent prompt quality" use case
**Impact:** Medium
**Counter:** Before adding grader/comparator/analyzer, audit whether `eval-judge` can be reused with a different rubric. The comparator (diff before/after) and analyzer (pattern extraction) may be genuinely novel. But `grader` ≈ `eval-judge`. Reuse first, create new only if rubric can't cover the delta.

---

### Argument 6: Progressive Disclosure — Mismatch with DLD's Loading Model
**Concern:** Progressive disclosure (3-level loading) was designed for Claude Code contexts where skills are discovered at runtime with partial loading. In DLD, skill files are loaded FULLY when the skill is activated — there is no lazy loading mechanism. The `settings.json` maps skill names to full `SKILL.md` file paths; Claude Code reads the whole file. "Progressive disclosure" in DLD context means structuring the file so Claude reads the important parts first (which is already done via section ordering), not actual deferred loading.
**Evidence:**
- `/Users/desperado/dev/dld/.claude/settings.json` — skills array maps directly to full file paths, no partial loading
- `/Users/desperado/dev/dld/template/.claude/settings.json` — same pattern
- DLD's conditional loading mechanism uses `paths:` frontmatter in rules files, not in skills
**Impact:** Low
**Counter:** Rebrand "progressive disclosure" as "structured information hierarchy" — organize the SKILL.md so critical activation triggers come first, edge cases last. This is valid and achievable without inventing a loading mechanism that doesn't exist.

---

### Argument 7: HTML Eval Viewer — Zero Value for a 1-2x/Month Meta-Tool
**Concern:** An HTML eval viewer (presumably opening a browser to show before/after comparisons) adds complexity: file generation, browser detection, platform-specific `open`/`xdg-open`/`start` commands, headless environments where this silently fails. The primary consumer of skill quality results is Claude itself (in the iteration loop) and the developer (who reads the markdown output). A markdown report is sufficient, as proven by `test/agents/eval-report.md` in the existing `/eval` skill.
**Evidence:**
- `/Users/desperado/dev/dld/.claude/skills/eval/SKILL.md:54` — current eval writes `test/agents/eval-report.md` — markdown only, no HTML viewer
- The `/eval report` command reads and displays the markdown — this is the UX pattern DLD users already know
**Impact:** Low
**Counter:** Skip the HTML viewer entirely. Output to markdown only. If a diff view is needed, `git diff` on the before/after SKILL.md files is more useful and zero-complexity.

---

## Simpler Alternatives

### Alternative 1: Eval Loop Without Rename
**Instead of:** Rename to skill-creator + 3 new agents + Python scripts + HTML viewer + description optimizer
**Do this:** Add eval quality gate to existing `skill-writer` as a new phase between "THREE-EXPERT GATE" and "WRITE". Dispatch `eval-judge` (already exists) with a skill-specific rubric. If score < 0.7 → iterate.
**Pros:** Zero rename migration cost. No new agents. No Python. Uses existing eval infrastructure. 20 LOC change to SKILL.md.
**Cons:** No benchmark across multiple queries. No comparator for before/after. Iteration loop is implicit (one pass).
**Viability:** High — delivers 60% of value at 5% of complexity.

---

### Alternative 2: Rename Only (No Eval Loop)
**Instead of:** Full upgrade
**Do this:** Rename the skill and update all 8 touch points. Add `project-agnostic` + `allowed-tools` to frontmatter (legitimate improvement). Keep Two-Mode structure (CREATE/UPDATE). No new agents, no scripts.
**Pros:** Clean foundation for future eval loop. Removes confusion between "writer" (sounds like text editing) and "creator" (sounds like generation). Low risk if all 8 files updated atomically.
**Cons:** Doesn't add the eval quality guarantee. Doesn't address the actual problem (inconsistent skill quality).
**Viability:** Medium — solves naming without the complexity tax.

---

### Alternative 3: Reuse /eval Skill for Skill Quality (No New Infrastructure)
**Instead of:** Building a parallel eval system inside skill-creator
**Do this:** Add a golden dataset for `skill-writer` itself to `test/agents/skill-writer/`. Document rubric criteria for "what makes a good skill prompt". Run `/eval agents skill-writer` to verify quality. The existing eval infrastructure handles everything.
**Pros:** Zero new files. Uses battle-tested infrastructure. Consistent with DLD's eval pattern.
**Cons:** `/eval` tests against golden input/output pairs, not the creative generation process. Harder to iterate on skill quality in a tight loop.
**Viability:** Medium — works for regression testing, not for iterative improvement.

---

**Verdict:** Alternative 1 is the right 80/20. The rename is legitimate (do it) and is a necessary prerequisite. The eval loop as a NEW PHASE inside the existing skill is the right scope. Python scripts, HTML viewer, description optimizer, and 3 new agents are YAGNI until there's evidence they're needed. The comparator agent (before/after diff) is the only genuinely novel addition worth considering.

---

## Eval Assertions (Structured from Risk Analysis)

### Deterministic Assertions

| ID | Scenario | Input | Expected Behavior | Risk | Priority | Type |
|----|----------|-------|-------------------|------|----------|------|
| DA-1 | Rename with partial update | skill-writer renamed in SKILL.md but not in reflect/SKILL.md | CI/smoke-test catches reference mismatch | High | P0 | deterministic |
| DA-2 | Python script on Node-only environment | `run_eval.py` called on machine without Python | Clear error: "Python not found", not silent hang | High | P0 | deterministic |
| DA-3 | `claude --print` unavailable in CI | eval iteration loop triggered in headless CI | Graceful exit with actionable error message | High | P0 | deterministic |
| DA-4 | Eval loop score always < threshold | Grader never passes — infinite loop risk | Max N iterations hard cap, exits with FAIL status | High | P0 | deterministic |
| DA-5 | skill-creator CREATE with no agent file | Wrapper type selected but agents/ file omitted | Skill validates type and blocks incomplete create | Med | P1 | deterministic |
| DA-6 | Description optimizer with 0 passing queries | All 20 queries route elsewhere | Loop exits, reports "description needs manual fix" | Med | P1 | deterministic |
| DA-7 | HTML viewer on headless server | `open`/`xdg-open` not found | Falls back to markdown path, does not crash | Low | P2 | deterministic |
| DA-8 | grader rubric conflicts with eval-judge rubric | Both agents score same output differently | Documented which takes precedence | Low | P2 | deterministic |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | smoke-test.sh REQUIRED_SKILLS array | scripts/smoke-test.sh:154 | Smoke test must pass after rename | P0 |
| SA-2 | reflect/SKILL.md DoD checklist | template/.claude/skills/reflect/SKILL.md:154 | "skill-creator applied changes" replaces old name | P0 |
| SA-3 | reflect/SKILL.md next_action string | template/.claude/skills/reflect/SKILL.md:183 | String updated to "Run /skill-creator" | P0 |
| SA-4 | CLAUDE.md Skills table | CLAUDE.md:156 | Entry updated, trigger row added | P1 |
| SA-5 | docs/15-skills-setup.md | docs/15-skills-setup.md:46,101,209 | Docs updated, settings.json example updated | P1 |
| SA-6 | autopilot/SKILL.md reference | template/.claude/skills/autopilot/SKILL.md:247 | Updated to skill-creator | P1 |
| SA-7 | eval-judge agent overlap | .claude/agents/eval-judge.md | No duplicate eval scoring logic introduced | P1 |

### Assertion Summary
- Deterministic: 8 | Side-effect: 7 | Total: 15

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| smoke-test.sh | scripts/smoke-test.sh:154 | Hardcodes "skill-writer" in REQUIRED_SKILLS | Update to "skill-creator" |
| template/smoke-test.sh | template/scripts/smoke-test.sh:154 | Same hardcode in template copy | Update both copies |
| reflect/SKILL.md DoD | template/.claude/skills/reflect/SKILL.md:154 | "skill-writer applied" in checklist | Update to "skill-creator" |
| reflect/SKILL.md next_action | template/.claude/skills/reflect/SKILL.md:183 | "Run /skill-writer" baked into spec format | Update to "skill-creator" |
| reflect/SKILL.md anti-pattern table | template/.claude/skills/reflect/SKILL.md:192-194 | 3 rows reference "skill-writer" | Update all 3 |
| reflect/SKILL.md after section | template/.claude/skills/reflect/SKILL.md:198,219 | 2 more references | Update both |
| CLAUDE.md Skills table | CLAUDE.md:156 | Old name in Skills table | Update row + localization.md |
| template/CLAUDE.md Skills table | template/CLAUDE.md:157 | Template copy | Update both |
| docs/15-skills-setup.md | docs/15-skills-setup.md:46,101,209 | Docs, file structure diagram, settings example | Update all 3 |
| autopilot/SKILL.md | template/.claude/skills/autopilot/SKILL.md:247 | Cross-reference to old name | Update |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| Python runtime | Hard dependency for scripts | High | Rewrite scripts as .mjs OR gate with clear error |
| `claude` CLI in PATH | Required for eval loop | High | Pre-flight check + hard fail with install instructions |
| eval-judge.md | Semantic duplication with grader | Medium | Reuse eval-judge; only add comparator if genuinely novel |
| settings.json skills array | Name-keyed registration | Medium | Update name field; existing user settings break on upgrade |
| `/upgrade` skill | Must migrate old name for existing users | Medium | Add migration step to upgrade.mjs |

---

## Test Derivation

All test cases are captured in `## Eval Assertions` above as DA-IDs and SA-IDs.
Facilitator maps these to EC-IDs in the spec's `## Eval Criteria` section.

---

## Questions to Answer Before Implementation

1. **Question:** Will Python be a first-class DLD prerequisite, or is it optional?
   **Why it matters:** If Python is required, it must be documented in CLAUDE.md prerequisites and template README. If optional, scripts must be in Node.js or gated with a clear error.

2. **Question:** Does the eval loop need to call `claude -p` as a subprocess, or can it run the grader agent as a Task tool dispatch (in-process)?
   **Why it matters:** In-process Task dispatch (existing DLD pattern) avoids the `claude` CLI dependency entirely and is consistent with ADR-008/009. Subprocess adds a new dependency class.

3. **Question:** What is the concrete user story for description optimization? When would a DLD user run 20-query benchmark on a skill they just created?
   **Why it matters:** If the answer is "never / only at skill authorship time" then this belongs in a one-time dev workflow, not in the production skill. If "always" — it adds $2-5 cost per skill creation that needs to be justified.

4. **Question:** How does `/upgrade` handle existing users who have `skill-writer` references in their own specs, diary entries, and reflect outputs?
   **Why it matters:** `/upgrade` updates `.claude/` files but does not touch `ai/features/` or `ai/diary/`. Users will have broken cross-references unless the migration plan explicitly covers this.

5. **Question:** Is the grader agent's rubric distinct enough from eval-judge to warrant a new file, or is this the same agent with a different prompt?
   **Why it matters:** If it's just a different rubric, add a `skill-quality.rubric.md` and dispatch `eval-judge` — no new agent needed. This keeps agent count down.

---

## Final Verdict

**Recommendation:** Proceed with caution

**Reasoning:** The rename from skill-writer → skill-creator is legitimate and should happen — "writer" implies text editing, "creator" implies generation, and the new name better reflects the skill's role. The eval loop concept is sound and adds real value. BUT the proposed implementation has three genuine blockers: (1) Python scripts in a Node.js-only infrastructure, (2) 10 uncounted rename touch points that will break smoke tests and reflect specs, (3) YAGNI features (HTML viewer, description optimizer, 3 new agents) that triple the scope with marginal benefit for a meta-tool used 1-2x per month.

**Conditions for success:**
1. Scripts must be `.mjs` — no Python dependency introduced (reuse existing `eval-agents.mjs` pattern)
2. Rename must update ALL 10 touch points atomically — smoke tests must pass before merge
3. Eval loop = one new phase in SKILL.md dispatching eval-judge (existing agent) with a skill rubric — no grader/comparator/analyzer agents until eval-judge proves insufficient
4. Progressive disclosure = section ordering in SKILL.md — not an actual loading mechanism (DLD doesn't support lazy skill loading)
5. HTML viewer = skip. Markdown report only, consistent with `/eval` pattern
6. Description optimizer = skip for MVP. Three-Expert Gate + one manual test invocation is sufficient for a 1-2x/month tool
7. Upgrade migration plan must handle existing `skill-writer` references in user `ai/` directories, not just `.claude/`
