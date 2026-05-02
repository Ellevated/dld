---
id: TECH-174
type: TECH
status: queued
priority: P2
risk: R2
created: 2026-05-02
---

# TECH-174 — Manual spec verification protocol (operator checklist)

**Status:** queued
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
