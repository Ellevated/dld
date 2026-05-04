# Manual Spec Verification Protocol

> Canonical install location: `~/.claude/projects/-root/memory/spec-verification-protocol.md`.
> This in-repo copy is the source of truth; copy it on operator setup:
> `cp scripts/vps/spec-verification-protocol.md ~/.claude/projects/-root/memory/`.
> Claude Code's sandbox treats `~/.claude/...` as a sensitive path and refuses
> automated writes there, so we ship the doc in-repo and install it manually.

Operator-facing checklist for verifying that a spec marked `done` actually
was implemented. Born from the 02.05 audit (TECH-174) where 17 of 18
suspected HARD-FAILs turned out OK and only one (FTR-897 Task 11) was a
real gap.

When to use:
- Spec marked `done` but you suspect a false-positive.
- Audit before manually confirming a status (operator UAT).
- Periodic spot-checks on autopilot output quality.
- Post circuit-breaker triage.

Automation: Steps 1–3 are reproduced by `scripts/vps/spec_verify.py`.
Steps 4–6 stay manual. Step 7 is the verdict.

## Step 1 — Read the spec

- Open `ai/features/<SPEC_ID>*.md`.
- Note: `## Allowed Files`, `## Tasks` / `## Implementation Plan`,
  `## Eval Criteria`.
- Frontmatter `status:` and `**Status:**` line MUST agree.

```bash
cd ~/projects/awardybot
less ai/features/FTR-897-2026-04-30-buyer-onboarding.md
```

## Step 2 — File existence check

```bash
cd <project>
python3 ~/projects/dld/scripts/vps/spec_verify.py "$PWD" FTR-897
```

Rules:
- "create NEW file" → file MUST exist.
- "modify" → recent commit on path (`git log --oneline -- <path>`).
- Missing NEW files = **HARD-FAIL**.

## Step 3 — Code search

```bash
git grep -c -F 'register_buyer' -- src/ tests/
```

Expected: ≥1 match per Task naming a function/route/class.
`spec_verify.py` automates this (extracts CamelCase, snake_case,
/route/paths, `backticked` ids from each Task line).

## Step 4 — Tests

- New tests in `tests/unit/` or `tests/integration/`?
- `cd <project> && ./test fast` — must pass.
- Coverage uplift on touched files.
- Integration tests use real deps (ADR-013).

## Step 5 — Migrations (DB-touching specs)

- `ls supabase/migrations/<DATE>_<SPEC_ID>*.sql` — present?
- Applied to dev? Applied to prod?
- Rollback path documented?

## Step 6 — Acceptance criteria

Per `EC-N`:
- **deterministic** → run the named check.
- **integration** → read asserts in the named test.
- **llm-judge / manual** → manual UAT.

## Step 7 — Verdict

- All green → annotate `ai/qa/<DATE>-<SPEC_ID>.md`.
- Some red → demote:

  ```bash
  python3 ~/projects/dld/scripts/vps/operator.py demote \
      <project> <SPEC_ID> "<reason>"
  ```

- Bypass guard (spec really done, guard mis-fired):

  ```bash
  python3 ~/projects/dld/scripts/vps/operator.py force-done \
      <project> <SPEC_ID> "<reason>"
  ```

- Circuit tripped (>3 demotes in 10 min):

  ```bash
  python3 ~/projects/dld/scripts/vps/operator.py reset-circuit
  ```

## Cross-references

- Guard: ADR-018, TECH-166 (`callback.py`).
- Allowlist: TECH-167 (`_parse_allowed_files`).
- Circuit: TECH-169.
- Audit log: TECH-171.
- `/qa` skill: invoke this protocol on done-spec validation.

## Change history

| Date | What | Spec |
|------|------|------|
| 2026-05-04 | Created — 7-step protocol + spec_verify.py + operator.py | TECH-174 |
