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

## Integration Tests — NO MOCKS (MANDATORY)

**Why:** LLM agents prefer mocks because they're faster to write.
Mocks test "does my mock return what I mocked?" — not "does my code work with real DB."

**Rule:** Code that touches DB or external services MUST have integration tests
in `tests/integration/` using real dependencies (Testcontainers).

**The pre-edit hook hard-blocks mock patterns in `tests/integration/`.**

### Python (Testcontainers)

```python
# tests/integration/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.fixture
def db(postgres):
    conn = psycopg.connect(postgres.get_connection_url())
    yield conn
    conn.rollback()
    conn.close()
```

### Node.js/TypeScript (Testcontainers)

```typescript
// tests/integration/setup.ts
import { PostgreSqlContainer } from '@testcontainers/postgresql';
let container, db;

beforeAll(async () => {
  container = await new PostgreSqlContainer().start();
  db = await connect(container.getConnectionUri());
});
afterAll(async () => { await container.stop(); });
```

### What's allowed vs forbidden in integration tests

| Allowed | Forbidden |
|---------|-----------|
| Real DB (Testcontainers) | `jest.mock()`, `vi.mock()` |
| Test fixtures/factories | `unittest.mock`, `MagicMock` |
| `jest.spyOn()` (read-only) | `@patch`, `mock.patch` |
| In-memory SQLite (real SQL) | `sinon.stub()`, `sinon.mock()` |

---

## Mutation Testing

Measures REAL test quality — are tests detecting bugs, or just running code?

### Stryker (JS/TS)

```bash
npx stryker run    # config: stryker.config.mjs
```

### mutmut (Python)

```bash
mutmut run --paths-to-mutate=src/
```

**Thresholds:** >80% = good, <60% = warning, <40% = fail

**Schedule:** Weekly in CI (too slow for every commit)

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
