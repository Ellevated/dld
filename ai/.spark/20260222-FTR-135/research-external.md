# External Research — API Version Endpoint

## Best Practices (5 with sources)

### 1. Simple JSON Response with Standard Fields
**Source:** [FastAPI Health Check Best Practices](https://www.index.dev/blog/how-to-implement-health-check-in-python)
**Summary:** Version endpoints should return simple JSON with standard fields: `name`, `version`, and `environment`. Common patterns include `/version`, `/api/version`, or `/health` endpoints.
**Why relevant:** Our endpoint follows this industry standard with `{"name": "myapp", "version": "1.0.0", "env": "dev"}`.

### 2. Public Endpoints — No Authentication Required
**Source:** [FastAPI Production Best Practices](https://render.com/articles/fastapi-production-deployment-best-practices)
**Summary:** Version/health endpoints should be publicly accessible for monitoring, load balancers, and debugging. Authentication creates chicken-and-egg problems during startup verification.
**Why relevant:** Our spec correctly marks this as public (no auth) — version info is not sensitive and needs to be accessible for ops tooling.

### 3. 12-Factor Config via Environment Variables
**Source:** [The Twelve-Factor App — Config](https://12factor.net/config)
**Summary:** Store config in environment variables, not code constants. Config varies between deploys (dev/staging/prod), code doesn't. Litmus test: "Could you make the codebase open source without compromising credentials?"
**Why relevant:** Our spec uses `APP_NAME`, `APP_VERSION`, `APP_ENV` env vars — strict separation of config from code.

### 4. Type-Safe Settings with pydantic-settings
**Source:** [Pydantic Settings Official Docs](https://context7.com/pydantic/pydantic-settings/llms.txt)
**Summary:** Use `BaseSettings` from `pydantic-settings` for type validation, automatic env var loading, and fail-fast behavior. Missing or invalid config crashes at startup, not in production.
**Why relevant:** FastAPI + pydantic-settings is the industry standard for 12-factor apps. Validates config before app starts.

### 5. Structured Settings Classes with Dependency Injection
**Source:** [FastAPI Settings and Environment Variables](https://fastapi.tiangolo.com/uk/advanced/settings/)
**Summary:** Define a `Settings` class inheriting from `BaseSettings`, use `@lru_cache` decorator to create singleton, inject via `Depends()`. Central configuration, type safety, easy testing.
**Why relevant:** This pattern enables clean dependency injection, making settings testable and maintainable across the application.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| pydantic-settings | 2.x | Type safety, auto env loading, validation, .env support | Extra dependency (not in pydantic core) | All FastAPI apps with env config | [PyPI](https://context7.com/pydantic/pydantic-settings/llms.txt) |
| python-dotenv | 1.x | Simple .env loading | No validation, manual parsing | Development only (use env vars in prod) | [12-factor Guide](https://12factor.net/config) |
| pydantic | 2.x | Core validation, type hints | Settings require separate package | All FastAPI apps | [FastAPI Docs](https://fastapi.tiangolo.com) |

**Recommendation:** `pydantic-settings 2.x` — industry standard for FastAPI, provides type safety + validation + 12-factor compliance out of the box. Already in most FastAPI projects.

---

## Production Patterns

### Pattern 1: BaseSettings with Dependency Injection
**Source:** [FastAPI + Pydantic Settings](https://medium.com/@hadiyolworld007/fastapi-pydantic-settings-twelve-factor-secrets-and-config-without-footguns-7990e2f20919)
**Description:**
1. Define `Settings(BaseSettings)` class with typed fields
2. Use `@lru_cache` to create singleton instance
3. Inject via `Depends(get_settings)` in routes
4. Environment variables auto-load with prefix support

**Real-world use:** Standard pattern across FastAPI ecosystem — used by production apps at scale
**Fits us:** Yes — clean, testable, type-safe. Follows FastAPI best practices.

### Pattern 2: Nested Settings with Prefixes
**Source:** [Pydantic Settings — SettingsConfigDict](https://context7.com/pydantic/pydantic-settings/llms.txt)
**Description:**
1. Use `env_prefix` for namespacing (`APP_`, `DB_`, etc.)
2. Nested models with `env_nested_delimiter='__'`
3. Example: `APP_DB__HOST` → `settings.db.host`

**Real-world use:** Complex apps with multiple service configs (database, cache, external APIs)
**Fits us:** No — overkill for simple 3-field version endpoint. Use flat structure.

### Pattern 3: Public Version + Protected Health
**Source:** [FastAPI Health Check Patterns](https://www.index.dev/blog/how-to-implement-health-check-in-python)
**Description:**
1. `/version` — public, returns app metadata
2. `/health` — may include DB checks, dependency status
3. `/readiness` — k8s readiness probe (can accept traffic?)
4. `/liveness` — k8s liveness probe (should restart?)

**Real-world use:** Kubernetes deployments, microservices architectures
**Fits us:** Partially — we only need `/api/version` now, but pattern allows future expansion to health checks.

---

## Key Decisions Supported by Research

1. **Decision:** Use pydantic-settings BaseSettings vs manual os.getenv()
   **Evidence:** [Pydantic Settings Tutorial](https://medium.com/@muruganantham52524/pydantic-v2-10-python-tutorial-typed-settings-for-fastapi-env-variables-docker-secrets-4bae378cb379) — "One missing environment variable. One invalid type. And your app refuses to start — exactly as it should."
   **Confidence:** High — fail-fast > fail-in-production

2. **Decision:** No authentication for /api/version endpoint
   **Evidence:** [FastAPI Production Deployment](https://render.com/articles/fastapi-production-deployment-best-practices) — version endpoints must be accessible for monitoring, load balancers, health checks
   **Confidence:** High — industry standard, version info is not sensitive

3. **Decision:** Environment variables (not config files) for APP_NAME, APP_VERSION, APP_ENV
   **Evidence:** [12-Factor App Config](https://12factor.net/config) — "strict separation of config from code. Config varies substantially across deploys, code does not."
   **Confidence:** High — 12-factor compliance, standard for cloud-native apps

4. **Decision:** Simple flat structure (not nested settings)
   **Evidence:** [YAGNI principle](https://fastapi.tiangolo.com/uk/advanced/settings/) — 3 simple fields don't justify complex nested config
   **Confidence:** High — keep it simple, add complexity when needed

---

## Code Pattern (from research)

```python
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict
from fastapi import Depends, FastAPI

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(
        env_prefix='APP_',  # APP_NAME, APP_VERSION, APP_ENV
        case_sensitive=False,
    )

    name: str = "myapp"
    version: str = "1.0.0"
    env: str = "dev"

@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()

app = FastAPI()

@app.get("/api/version")
async def version(settings: Settings = Depends(get_settings)):
    """Public version endpoint — no auth required."""
    return {
        "name": settings.name,
        "version": settings.version,
        "env": settings.env,
    }
```

**Source:** Pattern from [FastAPI Settings Docs](https://fastapi.tiangolo.com/uk/advanced/settings/) + [Pydantic Settings Examples](https://context7.com/pydantic/pydantic-settings/llms.txt)

---

## Research Sources

- [The Twelve-Factor App — Config](https://12factor.net/config) — foundational principles for env-based config
- [FastAPI Settings and Environment Variables](https://fastapi.tiangolo.com/uk/advanced/settings/) — official FastAPI pattern for pydantic-settings
- [Pydantic Settings Official Docs](https://context7.com/pydantic/pydantic-settings/llms.txt) — BaseSettings API, validation, configuration
- [FastAPI Health Check Best Practices](https://www.index.dev/blog/how-to-implement-health-check-in-python) — version/health endpoint patterns
- [FastAPI Production Deployment Best Practices](https://render.com/articles/fastapi-production-deployment-best-practices) — public endpoints, monitoring, security
- [FastAPI + Pydantic Settings: Twelve-Factor](https://medium.com/@hadiyolworld007/fastapi-pydantic-settings-twelve-factor-secrets-and-config-without-footguns-7990e2f20919) — practical guide to config management
- [Pydantic v2.10 Tutorial](https://medium.com/@muruganantham52524/pydantic-v2-10-python-tutorial-typed-settings-for-fastapi-env-variables-docker-secrets-4bae378cb379) — fail-fast validation benefits
- [Centralizing FastAPI Configuration](https://davidmuraya.com/blog/centralizing-fastapi-configuration-with-pydantic-settings-and-env-files/) — single source of truth pattern
- [FastAPI Best Practices GitHub](https://github.com/zhanymkanov/fastapi-best-practices) — startup conventions and patterns
- [Twelve-Factor App Guide](https://oneuptime.com/blog/post/2026-02-20-twelve-factor-app-guide/view) — modern cloud-native principles

---

## Additional Insights

### Why pydantic-settings Over Manual Parsing

**Problem with os.getenv():**
```python
# ❌ Manual parsing — fails silently
DEBUG = os.getenv("DEBUG", "false").lower() == "true"
MAX_CONNECTIONS = int(os.getenv("MAX_CONNECTIONS", "10"))  # ValueError in prod!
```

**Solution with BaseSettings:**
```python
# ✅ Type-safe, validated, fails at startup
class Settings(BaseSettings):
    debug: bool = False
    max_connections: int = 10
```

**Source:** [FastAPI Config Best Practices](https://www.shshell.com/blog/fastapi-module-3-lesson-3-config)

### Environment Variable Naming Conventions

From [12-factor research](https://stackoverflow.com/questions/41202907/twelve-factor-apps-ways-to-stay-align-with-the-config-guideline):

- Use UPPERCASE for env vars (standard convention)
- Prefix with app name to avoid collisions (`APP_`, `MYAPP_`)
- Separate words with underscores (`DATABASE_URL`, not `databaseUrl`)
- Nested config: use double underscore (`APP_DB__HOST`)

### Testing Settings

**Pattern:** Override settings in tests via dependency injection

```python
# tests/conftest.py
def get_test_settings():
    return Settings(
        name="test-app",
        version="0.0.0",
        env="test"
    )

app.dependency_overrides[get_settings] = get_test_settings
```

**Source:** [FastAPI Testing Documentation](https://fastapi.tiangolo.com/advanced/)

---

## Notes for Implementation

1. **Install dependency:** `pip install pydantic-settings`
2. **Create .env.example:** Document required env vars for developers
3. **Default values:** Provide sensible defaults for dev environment
4. **Validation:** Let app crash at startup if config invalid (fail-fast)
5. **No secrets in version endpoint:** Only non-sensitive metadata
