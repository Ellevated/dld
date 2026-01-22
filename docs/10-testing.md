# Testing Strategy

## Test Pyramid

```
        /\
       /  \     E2E (manual + critical flows)
      /────\
     /      \   Integration (cross-domain, DB)
    /────────\
   /          \  Unit (domain logic, collocated)
  /────────────\
```

---

## Test Categories

| Category | Location | Pattern | Purpose | Mutable? |
|----------|----------|---------|---------|----------|
| **Unit** | `src/domains/**/` | `*_test.py` | Business logic | Yes |
| **Integration** | `tests/integration/` | `test_*.py` | Cross-domain, DB | Yes |
| **E2E** | `tests/e2e/` | `test_*.py` | Full user flows | Yes |
| **Contracts** | `tests/contracts/` | `test_*.py` | API contracts | **NO** |
| **Regression** | `tests/regression/` | `test_*.py` | Bug prevention | **NO** |
| **LLM** | `tests/llm_agent/` | `test_*.py` | Agent behavior | Yes |

---

## Colocation Rule

Unit tests live next to code:

```
src/domains/orders/
├── service.py
├── service_test.py     # ← unit test here
├── repository.py
└── repository_test.py  # ← unit test here
```

**Why:** When LLM modifies `service.py`, it sees `service_test.py` in same folder.

---

## Immutable Tests (NEVER modify)

### Contracts (`tests/contracts/`)

API contracts between domains. If test fails → **fix code, not test**.

```python
@pytest.mark.contract
def test_order_service_returns_result_type():
    """Contract: OrderService.create() returns Result[Order, Error]"""
    result = order_service.create(valid_input)
    assert isinstance(result, Result)
```

### Regression (`tests/regression/`)

Prevent bugs from returning. Created after bug fix.

```python
@pytest.mark.regression
def test_bug_156_orphan_callback():
    """BUG-156: Callback must have handler. This test prevents regression."""
    # ... test that reproduces the bug
```

**Rule:** Only humans can modify contract/regression tests.

---

## Test Decision Tree

```
TEST FAILED
    │
    ├─ Is test in contracts/ or regression/?
    │   └─ YES → FIX CODE, not test
    │
    ├─ Was test created in current session?
    │   └─ YES → May update if requirements changed
    │
    ├─ Is this a refactoring task?
    │   └─ YES → Behavior should NOT change. Fix code.
    │
    └─ UNCLEAR? → ASK USER
```

---

## TDD Workflow (for Autopilot)

Every task follows:

```
1. Write failing test
2. Run test → verify FAIL
3. Write minimal implementation
4. Run test → verify PASS
5. Commit
```

---

## Running Tests

```bash
# Unit tests (fast)
pytest src/domains/ -v

# Integration
pytest tests/integration/ -v

# E2E (requires running services)
pytest tests/e2e/ --e2e -v

# LLM tests (expensive, use sparingly)
./test llm

# Full suite
./test

# Fast (lint + unit)
./test fast

# Coverage
pytest --cov=src tests/
```

---

## Smart Testing (Autopilot)

Run only relevant tests based on changed files:

| Changed file | Tests to run |
|--------------|--------------|
| `src/domains/orders/service.py` | `pytest src/domains/orders/` |
| `src/domains/orders/prompts/*` | `./test llm -- -k "orders"` |
| `src/infra/db/*` | `./test fast` |
| `.claude/*` | No tests |

**Fallback:** If file not in table → `./test fast`

---

## Fixtures

Shared fixtures in root `conftest.py`:

```python
# conftest.py
import pytest

@pytest.fixture
def db_session():
    """Isolated database session for tests."""
    # setup
    yield session
    # teardown

@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    ...
```

Domain-specific fixtures in domain's `conftest.py`:

```python
# src/domains/orders/conftest.py
@pytest.fixture
def sample_order():
    return Order(id=uuid4(), ...)
```

---

## CI Integration

```yaml
# .github/workflows/ci.yml
- name: Run tests with coverage
  run: pytest tests/ -v --cov=src --cov-report=xml

- name: Check coverage threshold
  run: |
    coverage report --fail-under=40
```

---

## LLM Test Safety

LLM agents must NOT:
- Modify tests in `tests/contracts/`
- Modify tests in `tests/regression/`
- Delete or skip existing tests without user approval
- Change assertion values without user approval

If LLM breaks these rules → CI fails → PR blocked.
