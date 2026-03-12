# Feature: [FTR-135] API Version Endpoint
**Status:** done | **Priority:** P2 | **Date:** 2026-02-22

## Why
Demonstrate a realistic FastAPI endpoint pattern for DLD users and verify the EDD pipeline end-to-end (spark produces Eval Criteria, devil produces DA-N assertions, facilitator maps DA→EC, autopilot implements, tester validates by EC).

## Context
DLD is a framework/template — no application code exists in `src/`. This feature creates a standalone example showing how to build a FastAPI version endpoint following 12-factor app principles with Pydantic BaseSettings.

---

## Scope
**In scope:**
- GET /api/version endpoint returning `{"name", "version", "env"}`
- Pydantic BaseSettings for env var config (APP_NAME, APP_VERSION, APP_ENV)
- Unit tests with structured eval criteria
- `.env.example` for documentation

**Out of scope:**
- Production security toggle (hide version in prod)
- Auto-detection from pyproject.toml (importlib.metadata)
- Database health checks
- Authentication

---

## Impact Tree Analysis (ARCH-392)

### Step 1: UP — who uses?
- N/A — greenfield, no existing code depends on this

### Step 2: DOWN — what depends on?
- FastAPI, pydantic-settings, uvicorn (runtime)
- pytest, httpx (testing)

### Step 3: BY TERM — grep entire project
- `grep -rn "version" examples/ --include="*.py"` → 0 results (directory doesn't exist yet)

### Step 4: CHECKLIST — mandatory folders
- [x] No existing tests to break
- [x] No migrations needed
- [x] No glossary needed

### Verification
- [x] All new files in Allowed Files
- [x] No conflicts with existing code

---

## Allowed Files
**ONLY these files may be modified during implementation:**

**New files allowed:**
1. `examples/version-endpoint/main.py` — FastAPI app + version router
2. `examples/version-endpoint/config.py` — Pydantic BaseSettings
3. `examples/version-endpoint/test_version.py` — Unit tests (eval criteria)
4. `examples/version-endpoint/pyproject.toml` — Dependencies
5. `examples/version-endpoint/.env.example` — Sample env vars

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Environment

nodejs: false
docker: false
database: false

---

## Blueprint Reference

**Domain:** N/A (standalone example, not in template domains)
**Cross-cutting:** None
**Data model:** None

---

## Approaches

### Approach 1: Standalone Example with Pydantic BaseSettings (selected)
**Source:** [FastAPI Settings Docs](https://fastapi.tiangolo.com/advanced/settings/), [12-Factor App](https://12factor.net/config)
**Summary:** Create `examples/version-endpoint/` with BaseSettings class, @lru_cache singleton, Depends() injection. Clean, testable, industry-standard pattern.
**Pros:** Type safety, fail-fast validation, testable via DI override, FastAPI community standard
**Cons:** Requires pydantic-settings dependency, slightly more code than os.getenv

### Approach 2: Direct os.getenv (rejected)
**Source:** [FastAPI Env Vars Guide](https://medium.com/@joerosborne/how-to-set-environment-variables-in-fastapi-837c538190e3)
**Summary:** Read env vars directly with os.getenv() defaults.
**Pros:** Minimal code (10 lines), zero dependencies
**Cons:** No validation, no type safety, hard to test, fails silently

### Selected: 1
**Rationale:** Approach 1 (BaseSettings) is the FastAPI industry standard (11 sources confirm). Provides type safety, fail-fast behavior, and testability. Approach 2 is too simplistic for a realistic example. Devil's concern about premature infra addressed by placing in `examples/`.

---

## Design

### User Flow
1. User copies `examples/version-endpoint/` to their project
2. User sets env vars: `APP_NAME=myapp APP_VERSION=1.0.0 APP_ENV=dev`
3. User runs: `uvicorn main:app --reload`
4. GET http://localhost:8000/api/version → `{"name": "myapp", "version": "1.0.0", "env": "dev"}`
5. User checks docs: http://localhost:8000/docs

### Architecture
```
examples/version-endpoint/
├── main.py           # FastAPI app + router (entry point)
├── config.py         # Settings(BaseSettings) + get_settings()
├── test_version.py   # Pytest + httpx tests
├── pyproject.toml    # Dependencies
└── .env.example      # Sample env vars
```

### Database Changes
None.

---

## Flow Coverage Matrix (REQUIRED)

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | Copy example to project | - | documentation |
| 2 | Set environment variables | Task 1 (.env.example) | new |
| 3 | Run uvicorn | Task 2 (main.py) | new |
| 4 | GET /api/version | Task 2 (main.py) + Task 3 (config.py) | new |
| 5 | Check /docs | - | automatic (FastAPI) |

**GAPS:** None. All flow steps covered.

---

## Eval Criteria (MANDATORY)

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Version endpoint returns 200 | GET /api/version | HTTP 200 + JSON with keys "name", "version", "env" | deterministic | user requirement | P0 |
| EC-2 | Values match env vars | APP_NAME=test APP_VERSION=2.0.0 APP_ENV=staging | {"name": "test", "version": "2.0.0", "env": "staging"} | deterministic | user requirement | P0 |
| EC-3 | Defaults for missing env vars | No env vars set | {"name": "myapp", "version": "1.0.0", "env": "dev"} | deterministic | devil DA-1,DA-2,DA-3 | P0 |
| EC-4 | No auth required | GET without Authorization header | HTTP 200 (not 401/403) | deterministic | user requirement | P0 |
| EC-5 | POST returns 405 | POST /api/version | HTTP 405 Method Not Allowed | deterministic | devil DA-5 | P1 |

### Integration Assertions (if applicable)

| ID | Setup | Action | Expected | Type | Source | Priority |
|----|-------|--------|----------|------|--------|----------|
| EC-6 | App running | GET /docs | Swagger UI shows /api/version endpoint | integration | devil DA-9 | P1 |

### Coverage Summary
- Deterministic: 5 | Integration: 1 | LLM-Judge: 0 | Total: 6 (min 3)

### TDD Order
1. Write test from EC-1 (GET returns 200 + correct keys) -> FAIL -> Implement -> PASS
2. EC-2 (values match env vars) -> FAIL -> Implement config -> PASS
3. EC-3 (defaults) -> FAIL -> Add defaults to Settings -> PASS
4. EC-4 (no auth) -> should PASS already
5. EC-5 (POST 405) -> should PASS already (FastAPI default)
6. EC-6 (swagger) -> should PASS already

---

## Implementation Plan

### Research Sources
- [FastAPI Advanced Settings](https://fastapi.tiangolo.com/advanced/settings/) — BaseSettings + Depends pattern
- [Pydantic Settings Docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — SettingsConfigDict, env_prefix
- [12-Factor App Config](https://12factor.net/config) — Env vars as config

### Task 1: Create project structure and config
**Type:** code
**Files:**
  - create: `examples/version-endpoint/pyproject.toml`
  - create: `examples/version-endpoint/.env.example`
  - create: `examples/version-endpoint/config.py`
**Pattern:** [FastAPI Advanced Settings](https://fastapi.tiangolo.com/advanced/settings/)
**Acceptance:**
  - pyproject.toml has fastapi, pydantic-settings, uvicorn, pytest, httpx
  - .env.example lists APP_NAME, APP_VERSION, APP_ENV with sample values
  - config.py has Settings(BaseSettings) with 3 fields + defaults + get_settings()

### Task 2: Create FastAPI app with version endpoint
**Type:** code
**Files:**
  - create: `examples/version-endpoint/main.py`
**Pattern:** [FastAPI Settings](https://fastapi.tiangolo.com/advanced/settings/)
**Acceptance:**
  - FastAPI app with GET /api/version
  - Uses Depends(get_settings) for config injection
  - Returns {"name", "version", "env"} from settings
  - EC-1, EC-2, EC-4 pass

### Task 3: Write tests (TDD verification)
**Type:** test
**Files:**
  - create: `examples/version-endpoint/test_version.py`
**Pattern:** [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
**Acceptance:**
  - Tests for EC-1 through EC-6
  - Uses httpx TestClient
  - Settings override via dependency_overrides
  - All tests pass with `pytest test_version.py -v`

### Execution Order
1 → 2 → 3

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks from Implementation Plan completed

### Tests
- [ ] All eval criteria from ## Eval Criteria section pass
- [ ] `pytest examples/version-endpoint/test_version.py -v` — all green

### Technical
- [ ] No regressions
- [ ] All files < 400 LOC

---

## Autopilot Log
[Auto-populated by autopilot during execution]
