# Safety Rules

Critical rules that must never be violated.

## Parallel Safety

For multi-autopilot environments:

- ⛔ **NEVER take task with status `in_progress`** — another autopilot working!
- ⛔ **ONLY take tasks with `queued` or `resumed`**
- Before taking ANY task: READ backlog → VERIFY status

## Git Safety

- ⛔ **NEVER push to `main`** — only `develop`
- ⛔ **NEVER auto-resolve conflicts** → STATUS: blocked
- ⛔ **NEVER** `git clean -fd` — destroys parallel work
- ⛔ **NEVER** `git reset --hard` — loses changes

## File Safety

- ⛔ **Modify files NOT in `## Allowed Files`** — File Allowlist!
- ⛔ **Take tasks with status `draft`** — no plan yet!

**Rule:** File NOT in spec's `## Allowed Files` → REFUSE. No exceptions.

## Test Safety

- ⛔ **NEVER modify** `tests/contracts/**` or `tests/regression/**`
- ⛔ **NEVER change test assertions** without user approval
- Test fails → fix CODE, not test (unless created in current session)
- Unclear? → ASK USER

## Code Quality Gates

- ⛔ File > 400 LOC (600 for tests) → split
- ⛔ `__init__.py` > 5 exports → reduce API
- ⛔ New code in `src/services/`, `src/db/`, `src/utils/` → use domains/
- ⛔ Import upward in dependency graph → fix direction

## Workflow Rules

- ⛔ Commit without Reviewer approved
- ⛔ Group multiple tasks before review
- ⛔ Skip Documenter or Reviewer
- ⛔ Run ALL LLM tests without reason (Smart Testing!)
- ⛔ Fix out-of-scope test failures (Scope Protection!)
- ⛔ Check DoD at start — DoD is FINAL checklist!

## Scope Protection

**SSOT:** `.claude/agents/tester.md#scope-protection`

Test fails but NOT related to `files_changed`? → SKIP, don't fix. Log and continue.

## Smart Testing

**SSOT:** `.claude/agents/tester.md#smart-testing`

Run only tests related to changed files, not entire suite.

## Migration Safety

**SSOT:** `.claude/rules/database.md#migrations`

- ⛔ **NEVER apply migrations manually** — CI only!
- Validate locally: squawk lint, dry-run
- CI applies after push to develop

## Serverless Functions

- ⛔ **NEVER deploy serverless functions manually** — CI only!
- Validate locally: type check, lint
- CI deploys after push to develop
