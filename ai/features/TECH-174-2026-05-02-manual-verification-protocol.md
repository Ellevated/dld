---
id: TECH-174
type: TECH
status: queued
priority: P2
risk: R2
created: 2026-05-02
---

# TECH-174 — Manual spec verification protocol (operator checklist)

**Status:** done
**Priority:** P2
**Risk:** R2

---

## Problem

Когда callback / autopilot ошибаются (FTR-897 false-done case), оператор вынужден руками открывать репо, читать спеку, грепать allowed_files, проверять миграции. Сегодня (02.05) пользователь выявил что 17 из 18 моих "HARD-FAIL" — на самом деле OK, и нашёл единственный реальный пробел (FTR-897 Task 11). Это была **тяжёлая ручная работа**, которую можно превратить в воспроизводимый чек-лист.

---

## Goal

Один документ `~/.claude/projects/-root/memory/spec-verification-protocol.md` — checklist для оператора (или агента в режиме `/qa`):

```markdown
# Manual Spec Verification Protocol

When to use:
- Spec marked `done` but you suspect false-positive.
- Audit before manually confirming a status.
- Periodic spot-checks on autopilot output quality.

## Step 1 — Read the spec
- Open `ai/features/<SPEC_ID>*.md`.
- Note: ## Allowed Files (canonical list).
- Note: ## Tasks (what was supposed to happen).
- Note: ## Eval Criteria (how to verify).

## Step 2 — File existence check
For each path in ## Allowed Files:
  ls <project>/<path>     # exists?
  if "NEW" in spec: file MUST exist
  if "modified" in spec: file should have recent changes

## Step 3 — Code search
For each Task description:
  grep -r '<keyword>' <project>/<allowed_dir> | wc -l
  Expected: matching the Task verbiage (function names, route names, etc.).

## Step 4 — Tests
- Are new tests in tests/{unit,integration}/?
- Run: `cd <project> && ./test fast` — must pass.
- Coverage uplift on touched files (if reported).

## Step 5 — Migrations (DB-touching specs)
- ls supabase/migrations/<DATE>_<SPEC_ID>*.sql
- Did migration apply to dev? (check deploy logs)
- Did migration apply to prod? (rare, but check)

## Step 6 — Acceptance criteria
For each EC-N in spec:
  Run the deterministic check OR
  Read the integration test asserts OR
  Manual UAT for LLM-judge criteria.

## Step 7 — Verdict
- All steps green → spec genuinely done.
- Some steps red → return spec to `queued` with reason in Blocked Reason field.
- Use operator-mode tool (TBD): `python3 scripts/vps/operator.py demote <project> <spec_id> "<reason>"`.
```

Plus: **automated heuristic helper** `scripts/vps/spec_verify.py <project> <spec_id>` — выполняет Steps 1-3 автоматически и печатает report. Step 4-6 — manual.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `~/.claude/projects/-root/memory/spec-verification-protocol.md`
- `scripts/vps/spec_verify.py`
- `scripts/vps/operator.py`
- `tests/integration/test_spec_verify.py`

---

## Tasks

1. **Document protocol** — markdown с 7 шагами + примеры.
2. **`spec_verify.py`**: argparse, использует `callback._parse_allowed_files`, делает file existence + grep counts + git log report.
3. **`operator.py`**: CLI для ручных операций (demote, force-done, reset-circuit). Wraps callback functions через plumbing-commit.
4. **Tests**: synthetic spec в tmpdir, прогоняем spec_verify, проверяем report.
5. **Включить protocol в `/qa` skill** — ссылка из `.claude/skills/qa/SKILL.md`.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | spec_verify.py FTR-897 awardybot reports Task 11 missing (file `src/api/v2/buyer/onboarding.py` not found) |
| EC-2 | deterministic | spec_verify.py BUG-913 awardybot reports OK (allowed files exist, recent commits) |
| EC-3 | integration | operator.py demote fluently через plumbing-commit, не трогая working tree |
| EC-4 | deterministic | Protocol .md имеет все 7 шагов + примеры команд |

---

## Drift Log

**Checked:** 2026-05-04 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `scripts/vps/spec_verify.py` | already implemented (commit a13ba50) | Plan: skip — verify only |
| `scripts/vps/spec_operator.py` | already implemented; renamed from `operator.py` (commit 5e472cd, stdlib shadow fix) | Plan: skip — verify only; spec text mentioning `operator.py` is stale but allowlist still matches v1 marker via wildcard intent |
| `tests/integration/test_spec_verify.py` | already implemented (commit a13ba50) | Plan: skip — verify only |
| `~/.claude/projects/-root/memory/spec-verification-protocol.md` | does NOT exist | Plan: CREATE in Task 1 |
| `.claude/skills/qa/SKILL.md` | exists, no reference to protocol yet | Plan: ADD reference in Task 5 |

### References Updated
- Task 2/3: `operator.py` → `spec_operator.py` (file already renamed for stdlib safety)

---

## Implementation Plan

Most files already exist (commits 8736e0b, a13ba50, 5e472cd). Remaining work is the
operator-facing protocol document and the `/qa` skill reference. We also re-validate
the existing scripts and tests against their evals.

### Task 1: Create the protocol document (operator-facing checklist)

**File:** `~/.claude/projects/-root/memory/spec-verification-protocol.md` (CREATE)

**Why:** Single source of truth for the 7-step manual verification routine.
Lives in `~/.claude/projects/-root/memory/` so it auto-loads in any Claude Code
session that the operator runs from `~/`. Test
`test_protocol_doc_has_seven_steps` in `tests/integration/test_spec_verify.py:237`
asserts headings `## Step 1` … `## Step 7` and at least one ` ```bash ` block.

**Content requirements (must match test asserts + EC-4):**

- Top-level heading `# Manual Spec Verification Protocol`.
- "When to use" section listing 3 triggers (suspect false-done, pre-confirm audit,
  spot-check).
- Headings `## Step 1` through `## Step 7` (exact spelling, used by test loop).
- Each step has a short description AND at least one fenced ` ```bash ` example
  command.
- Step contents (mirror spec Goal section verbatim where possible):
  - Step 1 — Read the spec (paths under `ai/features/<SPEC_ID>*.md`).
  - Step 2 — File existence check (loop over `## Allowed Files`, `ls`).
  - Step 3 — Code search (grep keywords from each Task description).
  - Step 4 — Tests (`./test fast`, coverage on touched files).
  - Step 5 — Migrations (`ls supabase/migrations/<DATE>_<SPEC_ID>*.sql`).
  - Step 6 — Acceptance criteria (deterministic / integration / LLM-judge).
  - Step 7 — Verdict + demote command:
    `python3 scripts/vps/spec_operator.py demote <project> <SPEC_ID> "<reason>"`.
- Cross-reference at the bottom: link to
  `scripts/vps/spec_verify.py` (automates Steps 1–3) and
  `scripts/vps/spec_operator.py` (Step 7 mutation).

**Verification:**
```bash
test -f ~/.claude/projects/-root/memory/spec-verification-protocol.md
grep -c '^## Step [1-7]' ~/.claude/projects/-root/memory/spec-verification-protocol.md   # expect 7
grep -c '```bash' ~/.claude/projects/-root/memory/spec-verification-protocol.md          # expect >=1
pytest tests/integration/test_spec_verify.py::test_protocol_doc_has_seven_steps -v
```

**Acceptance:**
- [ ] File exists at exact path above.
- [ ] All 7 `## Step N` headings present.
- [ ] Demote command in Step 7 references `spec_operator.py` (not stale `operator.py`).
- [ ] `test_protocol_doc_has_seven_steps` passes (no longer skips).

---

### Task 2: Re-verify `spec_verify.py` against EC-1/EC-2

**File:** `scripts/vps/spec_verify.py` (VERIFY, no edits expected)

**Why:** Code is already in place from commit a13ba50; this task just confirms
both deterministic eval criteria still hold against the current implementation.

**Steps:**
```bash
cd /home/dld/projects/dld
pytest tests/integration/test_spec_verify.py::test_spec_verify_reports_missing_file -v   # EC-1 surrogate
pytest tests/integration/test_spec_verify.py::test_spec_verify_ok_when_files_and_symbols_present -v   # EC-2 surrogate
pytest tests/integration/test_spec_verify.py::test_spec_verify_cli_exit_codes -v
```

**If any test fails:** investigate (do NOT patch the test). Likely culprits:
parser changes in `callback._parse_allowed_files`, or symbol-extraction regex in
`spec_verify.extract_symbols` (`scripts/vps/spec_verify.py:147-163`).

**Acceptance:**
- [ ] All three tests above pass.
- [ ] `python3 scripts/vps/spec_verify.py --help` runs and shows two positional args.

---

### Task 3: Re-verify `spec_operator.py` against EC-3

**File:** `scripts/vps/spec_operator.py` (VERIFY, no edits expected)

**Why:** Confirms plumbing-commit path still works after callback.py refactors
(commits 5e472cd, 8736e0b). EC-3 is "operator.py demote fluently через
plumbing-commit, не трогая working tree".

**Steps:**
```bash
cd /home/dld/projects/dld
pytest tests/integration/test_spec_verify.py::test_operator_demote_via_plumbing_does_not_touch_working_tree -v   # EC-3
pytest tests/integration/test_spec_verify.py::test_operator_force_done -v
pytest tests/integration/test_spec_verify.py::test_operator_demote_unknown_spec_returns_3 -v
python3 scripts/vps/spec_operator.py --help
python3 scripts/vps/spec_operator.py demote --help
```

**Acceptance:**
- [ ] All three operator tests pass.
- [ ] `--help` lists three subcommands: `demote`, `force-done`, `reset-circuit`.
- [ ] Operator's working-tree dirty file survives a demote (asserted by test).

---

### Task 4: Run the full test_spec_verify.py module

**File:** `tests/integration/test_spec_verify.py` (RUN, no edits expected)

**Steps:**
```bash
cd /home/dld/projects/dld
pytest tests/integration/test_spec_verify.py -v
```

**Acceptance:**
- [ ] All tests pass (after Task 1, `test_protocol_doc_has_seven_steps` no longer skipped).
- [ ] Zero failures, zero errors.

---

### Task 5: Reference protocol from `/qa` skill

**File:** `.claude/skills/qa/SKILL.md` (MODIFY — append a short pointer)

**Why:** Spec Task 5 — "Включить protocol в `/qa` skill". The QA skill is the
operator-facing hatch when "test the product like a user" overlaps with
"verify a spec went through cleanly".

**What to add:** A new short section near the bottom of the file (before any
trailing changelog/footer if present, otherwise at end) titled
`## Spec Verification Protocol (when QA-ing a closed spec)`.

**Section content (suggested verbatim):**

```markdown
## Spec Verification Protocol (when QA-ing a closed spec)

When the user asks to QA a spec that is already marked `done` (e.g.
"check FTR-897 was actually delivered"), follow the operator checklist:

`~/.claude/projects/-root/memory/spec-verification-protocol.md`

Quick path:

```bash
# Steps 1–3 automated
python3 scripts/vps/spec_verify.py <project_dir> <SPEC_ID>

# Step 7 — if you need to demote a false-done
python3 scripts/vps/spec_operator.py demote <project> <SPEC_ID> "<reason>"
```

Steps 4–6 (tests, migrations, acceptance) stay manual — exercise the product
yourself, do NOT just trust the heuristic report.
```

**Constraints:**
- Do NOT alter the YAML frontmatter or HARD BOUNDARIES section — they are
  semantically load-bearing for skill activation.
- Insert ABOVE any "Change History" / footer block; otherwise append at EOF.
- Keep the inserted block ≤25 lines.

**Verification:**
```bash
grep -n 'spec-verification-protocol.md' .claude/skills/qa/SKILL.md
grep -n 'spec_verify.py' .claude/skills/qa/SKILL.md
grep -n 'spec_operator.py' .claude/skills/qa/SKILL.md
```
All three greps must return at least one hit.

**Acceptance:**
- [ ] New section present in `.claude/skills/qa/SKILL.md`.
- [ ] All three grep checks return ≥1 hit.
- [ ] YAML frontmatter and HARD BOUNDARIES section unchanged (`git diff` shows
      only an additive section).

---

### Execution Order

```
Task 1 (create protocol doc)
   ↓
Task 5 (qa skill — references the doc created in Task 1)
   ↓
Tasks 2, 3, 4 (parallel verification — pure pytest runs)
```

Tasks 2/3/4 are independent verification gates and may be run concurrently.
Task 5 depends on Task 1 only because the section it adds points at the
file Task 1 creates.

### Dependencies

- Task 5 references the protocol path created by Task 1.
- Tasks 2, 3, 4 share `tests/integration/test_spec_verify.py` but assert
  disjoint test functions — safe to interleave.
- No code changes to `callback.py`, `db.py`, `event_writer.py` are required
  by this spec (TECH-174 is operator-tooling, not orchestrator-state).

### Research Sources

None — implementation is project-internal tooling that wraps existing
`callback.py` plumbing primitives. No external library or API surface
changed since the spec was written.
