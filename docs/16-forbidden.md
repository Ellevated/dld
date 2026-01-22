# Forbidden — Stop Words & Guardrails

Rules that prevent codebase degradation. Enforced by CI and LLM instructions.

---

## File Size Limits

| Type | Max LOC | Action if exceeded |
|------|---------|-------------------|
| Code files | 400 | Split into modules |
| Test files | 600 | Split by test category |
| `__init__.py` | 5 exports | Reduce public API |

```bash
# CI check
python scripts/check_file_sizes.py --max-lines 400 --max-test-lines 600 --fail
```

---

## Legacy Folders (DON'T CREATE)

These folders are anti-patterns. Never create them in new projects:

```
src/services/     ← use src/domains/{domain}/services/
src/db/           ← use src/infra/db/
src/utils/        ← use src/shared/
src/helpers/      ← use src/shared/
src/agents/       ← use src/domains/{domain}/
src/core/         ← use src/domains/{domain}/
src/common/       ← use src/shared/
```

**Why:** LLM doesn't know where to put code when there are multiple options.

---

## Import Rules (DAG)

```
Direction: ONLY downward

shared  ←  infra  ←  domains  ←  api
              ↓
   billing ← campaigns ← seller/buyer
```

### Forbidden imports:

```python
# ❌ infra importing from domains
from src.domains.orders import OrderService  # in infra/db/client.py

# ❌ shared importing from anything
from src.infra.db import db  # in shared/result.py

# ❌ billing importing from campaigns (wrong direction)
from src.domains.campaigns import Campaign  # in domains/billing/service.py

# ❌ circular import
# domains/orders/service.py imports domains/payments/service.py
# domains/payments/service.py imports domains/orders/service.py
```

```bash
# CI check
python scripts/check_domain_imports.py --strict
```

---

## Test Safety

### Immutable test locations:

```
tests/contracts/    ← API contracts — NEVER modify
tests/regression/   ← Bug prevention — NEVER modify
```

### Forbidden actions:

- Delete tests without user approval
- Skip tests (`@pytest.mark.skip`) without user approval
- Change assertion values without user approval
- Modify contract/regression tests at all

### Decision tree:

```
Test failed?
  ├─ In contracts/ or regression/ → FIX CODE
  ├─ Created in current session → May update
  └─ Unclear → ASK USER
```

---

## Spec Compliance

Every code change must respect `## Allowed Files` in feature spec.

### Before modifying ANY file:

```
1. Check feature spec
2. Find "## Allowed Files" section
3. File in list? → proceed
4. File NOT in list? → REFUSE
```

### If file not in list:

```
"⛔ BLOCKED: {file} not in Allowed Files. Refusing to modify."
```

Options:
- Update spec first (user approval)
- Ask user for permission

---

## Git Safety

```
⛔ NEVER force push          (git push --force)
⛔ NEVER auto-resolve conflicts
⛔ NEVER push to main without PR
⛔ NEVER skip hooks          (--no-verify)
⛔ NEVER amend pushed commits
```

---

## Naming Forbidden

```
❌ sm.py, mgr.py, util.py    → Use full names
❌ helpers.py, common.py     → Be specific
❌ process(), handle()       → Use verb_noun()
❌ data, info, item          → Use domain terms
```

---

## Over-engineering Forbidden

```
❌ Add features not requested
❌ Premature abstraction (3 similar lines > helper)
❌ Feature flags for internal code
❌ Backwards compatibility shims for new code
❌ Error handling for impossible cases
```

---

## CI Enforcement

Add these checks to `.github/workflows/ci.yml`:

```yaml
- name: Check file sizes
  run: python scripts/check_file_sizes.py --max-lines 400 --max-test-lines 600 --fail

- name: Check import violations
  run: python scripts/check_domain_imports.py --strict

- name: Validate spec compliance
  run: python scripts/validate_spec.py "$SPEC_FILE" $CHANGED_FILES

- name: Check docs sync
  run: python scripts/check_docs_sync.py
```

---

## LLM Instructions

Add to CLAUDE.md:

```markdown
## Forbidden (CI enforced)

### File Limits
- ⛔ Max 400 LOC per file (600 for tests)
- ⛔ Max 5 exports in `__init__.py`

### Legacy Folders (DELETED)
src/services/, src/db/, src/utils/, src/agents/

### Import Direction
shared → infra → domains → api

### Test Safety
- ⛔ Never modify tests/contracts/
- ⛔ Never modify tests/regression/
- ⛔ Never delete/skip tests without approval

### Spec Compliance
- ⛔ Only modify Allowed Files from spec
```

---

## Scripts Reference

| Script | Purpose |
|--------|---------|
| `scripts/check_file_sizes.py` | Enforce LOC limits |
| `scripts/check_domain_imports.py` | Enforce import DAG |
| `scripts/validate_spec.py` | Enforce Allowed Files |
| `scripts/check_docs_sync.py` | Prevent doc drift |
