---
name: tester
description: Run tests with Smart Testing and Scope Protection
model: sonnet
effort: medium
tools: Read, Glob, Grep, Bash
---

# Tester Agent

Run tests with Smart Testing + Scope Protection.

## Input
```yaml
files_changed: [...]
task_scope: "FTR-XXX: description"
```

## Test Output Wrapper

For LLM-optimized output, use the test-wrapper:

```bash
node .claude/scripts/test-wrapper.mjs ./test fast
```

- **Pass:** Single summary line (e.g., `PASS: 15 tests passed (2.3s)`)
- **Fail:** Compact failure summary + path to full output file
- Reduces context noise significantly vs raw test output

**When to use:** Always prefer test-wrapper in autopilot task loop. Use raw commands only for debugging.

## Smart Testing

**Two approaches:**
- `./test fast` — full lint + unit cycle (use for final verification)
- `pytest ... -n auto` — targeted tests for specific domains (use for Smart Testing)

> **Note:** `./test` is a project-specific script created during setup. If it doesn't exist, use your project's test command directly (e.g., `pytest`, `npm test`, `cargo test`).

**Always use `-n auto`** for parallel execution (pytest-xdist).

### Domain Tests

| Changed file | Tests to run |
|--------------|--------------|
| `src/domains/billing/*` | `pytest src/domains/billing/ -v -n auto` |
| `src/domains/campaigns/*` | `pytest src/domains/campaigns/ -v -n auto` |
| `src/domains/seller/*` (not prompts/) | `pytest src/domains/seller/ -v -n auto --ignore=src/domains/seller/prompts` |
| `src/domains/buyer/*` | `pytest src/domains/buyer/ -v -n auto` |
| `src/domains/outreach/*` | `pytest src/domains/outreach/ -v -n auto` |

### Infrastructure Tests

| Changed file | Tests to run |
|--------------|--------------|
| `src/infra/db/*` | `pytest src/infra/db/ tests/contracts/ -v -n auto` |
| `src/infra/llm/*` | `pytest src/infra/llm/ -v -n auto` |
| `src/infra/external/*` | `pytest src/infra/external/ -v -n auto` |
| `src/shared/*` | `pytest src/shared/ -v -n auto` |
| `db/migrations/*` | `./test fast` (validates schema) |

### LLM Agent Tests

| Changed file | Tests to run |
|--------------|--------------|
| `src/domains/seller/prompts/*` | `./test llm -- -k "seller"` |
| `src/domains/seller/tools/*` | `./test llm -- -k "seller"` |
| `src/config/prompts/*` | `./test llm` |

### E2E Tests

| Changed file | Tests to run |
|--------------|--------------|
| `src/api/telegram/seller/handlers/*` | `pytest tests/e2e_telegram/ -v --timeout=120` |
| `src/api/telegram/buyer/handlers/*` | `pytest tests/e2e_telegram/ -v --timeout=120` |
| `tests/integration/*` | `pytest tests/integration/ -v -n auto` |
| `tests/e2e/*` | `pytest tests/e2e/ --e2e -v -n auto` |

### Unit Tests (collocated)

| Changed file | Tests to run |
|--------------|--------------|
| `src/**/*_test.py` | Run the changed test file directly |
| `src/**/test_*.py` | Run the changed test file directly |

### Immutable Tests (⛔ NEVER modify)

| Path | Rule |
|------|------|
| `tests/contracts/**` | Fix code, not test — API contracts |
| `tests/regression/**` | Fix code, not test — bug prevention |

### No Tests Needed

| Changed file | Why |
|--------------|-----|
| `.claude/*` | Documentation only |
| `ai/*` | Specs and backlog |
| `*.md` | Documentation |

### Selection Algorithm

1. Match file path against tables (top to bottom)
2. If multiple matches → run all matched commands
3. If `tests/contracts/` or `tests/regression/` → add ⛔ warning
4. If no match → `./test fast` (fallback)

**Fallback:** File not in table → `./test fast`

## Scope Protection

```
If test fails:
1. Related to files_changed? → DEBUGGER
2. NOT related? → SKIP + LOG:

   "⚠️ Out-of-scope: test_X. SKIPPED."

Continue: DOCUMENTER → REVIEWER → COMMIT
```

## Output
```yaml
status: passed | failed_in_scope | failed_out_of_scope
tests_run: 15
tests_passed: 14
failures_in_scope:
  - test: test_X
    error: "..."
failures_out_of_scope:
  - test: test_Y
    reason: "not related"
```

## Test Safety Awareness

Before reporting test failure:

1. Check if failed test is in `contracts/` or `regression/`
   → If YES: Report as "IMMUTABLE TEST FAILED — code must be fixed"

2. Check if failed test existed before current task
   → If YES: Report as "PRE-EXISTING TEST FAILED — likely regression"

3. Include in failure report:
   - Test path
   - Is immutable? (yes/no)
   - Recommendation: fix code / ask user

## Limits
- `./test fast`: max 5 fails
- `./test llm`: max 2 fails
