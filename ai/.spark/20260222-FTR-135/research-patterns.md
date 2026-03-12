# Pattern Research — API Version Endpoint

## Approach 1: Direct os.environ Reads

**Source:** [FastAPI Environment Variables](https://medium.com/@joerosborne/how-to-set-environment-variables-in-fastapi-837c538190e3)

### Description
Read environment variables directly in the endpoint handler using `os.getenv()`. No configuration class, no validation layer. Simple function that fetches from environment and returns JSON response.

### Pros
- Minimal code (10-15 lines total)
- Zero dependencies beyond stdlib
- No configuration boilerplate
- Fastest to implement (15 minutes)
- Easy to understand for beginners

### Cons
- No type safety (everything is string or None)
- No validation (typos in env var names fail silently)
- Environment variables scattered across codebase
- Hard to test (requires mocking os.environ)
- No default values or coercion (bool, int)
- Duplicated `os.getenv()` calls if used in multiple places

### Complexity
**Estimate:** Easy — 15-30 minutes
**Why:** Single endpoint file, direct implementation. Research shows this is the "quick and dirty" approach used in tutorials but discouraged for production.

### Example Source
```python
# main.py
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/version")
async def version():
    return {
        "name": os.getenv("APP_NAME", "unknown"),
        "version": os.getenv("APP_VERSION", "0.0.0"),
        "env": os.getenv("APP_ENV", "dev")
    }
```

---

## Approach 2: Pydantic BaseSettings Class

**Source:** [FastAPI Settings Management](https://fastapi.tiangolo.com/advanced/settings/), [Pydantic Settings Guide](https://runebook.dev/en/articles/fastapi/advanced/settings/index)

### Description
Create a Pydantic `BaseSettings` class that automatically loads and validates environment variables. Use dependency injection with `@lru_cache()` to ensure settings are loaded once and reused across requests. Type hints provide automatic conversion (str → bool, str → int).

### Pros
- Type safety with automatic conversion (`debug: bool` reads "true" as `True`)
- Built-in validation (missing required fields raise errors on startup)
- Single source of truth for all config
- Easy to test (instantiate Settings with overrides)
- `.env` file support out of the box
- Dependency injection pattern (testable, mockable)
- Field descriptions and constraints via Pydantic
- Industry standard (recommended by FastAPI docs)

### Cons
- Requires `pydantic-settings` dependency (1 extra package)
- More boilerplate code (~30-40 lines for config class)
- Learning curve for Pydantic BaseSettings pattern
- Overkill for projects with <5 environment variables

### Complexity
**Estimate:** Medium — 1-2 hours
**Why:** Need to create config module, understand BaseSettings, implement dependency injection. Research shows this is FastAPI best practice and widely adopted.

### Example Source
```python
# config.py
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str
    app_version: str
    app_env: str = "dev"  # default value

    class Config:
        env_file = ".env"
        case_sensitive = False  # APP_NAME or app_name both work

@lru_cache()
def get_settings():
    return Settings()

# main.py
from fastapi import FastAPI, Depends
from config import Settings, get_settings

app = FastAPI()

@app.get("/api/version")
async def version(settings: Settings = Depends(get_settings)):
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "env": settings.app_env
    }
```

**Source:** [FastAPI Advanced Settings](https://fastapi.tiangolo.com/advanced/settings/)

---

## Approach 3: Auto-Detect from pyproject.toml + Env Override

**Source:** [importlib.metadata.version()](https://adamj.eu/tech/2025/07/30/python-check-package-version-importlib-metadata-version/), [Single-Source Versioning](https://packaging.python.org/en/latest/discussions/single-source-version/)

### Description
Use `importlib.metadata.version()` to read the installed package version from package metadata (set in `pyproject.toml`). Combine with Pydantic BaseSettings for other env vars. This eliminates manual version duplication — version lives only in `pyproject.toml`, not in environment variables.

### Pros
- Single source of truth for version (pyproject.toml)
- No manual version updates in .env files
- Standard Python approach (PEP 566, importlib.metadata)
- Works for all installed packages
- Automatic sync between package metadata and runtime
- Still type-safe for other settings (name, env)
- Recommended by Python packaging guide

### Cons
- Only works when package is installed (`pip install -e .`)
- Fails in development if not installed (need fallback)
- Requires pyproject.toml with `[project] version = "x.y.z"`
- More complex error handling (version might not exist)
- Harder to override version for testing
- Learning curve for importlib.metadata API

### Complexity
**Estimate:** Medium — 2-3 hours
**Why:** Need to understand importlib.metadata, handle installation edge cases, implement fallback for dev environment. Research shows this is industry best practice but requires careful error handling.

### Example Source
```python
# config.py
from functools import lru_cache
from importlib.metadata import version, PackageNotFoundError
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str
    app_env: str = "dev"

    class Config:
        env_file = ".env"

    @property
    def app_version(self) -> str:
        """Auto-detect version from installed package metadata."""
        try:
            return version(self.app_name)
        except PackageNotFoundError:
            # Fallback for development (not installed)
            return "0.0.0-dev"

@lru_cache()
def get_settings():
    return Settings()

# main.py
from fastapi import FastAPI, Depends
from config import Settings, get_settings

app = FastAPI()

@app.get("/api/version")
async def version(settings: Settings = Depends(get_settings)):
    return {
        "name": settings.app_name,
        "version": settings.app_version,  # auto-detected
        "env": settings.app_env
    }
```

**Source:** [importlib.metadata documentation](https://adamj.eu/tech/2025/07/30/python-check-package-version-importlib-metadata-version/)

---

## Comparison Matrix

| Criteria | Approach 1 | Approach 2 | Approach 3 |
|----------|------------|------------|------------|
| Complexity | Low | Medium | Medium |
| Maintainability | Low | High | High |
| Performance | High | High | High |
| Scalability | Low | High | High |
| Dependencies | None | pydantic-settings | pydantic-settings |
| Testability | Low | High | Medium |
| Type Safety | None | Full | Full |
| Version Sync | Manual | Manual | Automatic |
| Error Handling | None | Startup validation | Runtime fallback |
| Production Ready | No | Yes | Yes |

**Rating scale:** Low / Medium / High

---

## Recommendation

**Selected:** Approach 2 (Pydantic BaseSettings)

### Rationale

For an E2E pipeline test feature, Approach 2 strikes the best balance between simplicity and production quality. Research across 10+ sources shows this is the FastAPI community standard for good reason.

Key factors:

1. **Type Safety Without Complexity** — Pydantic BaseSettings gives us automatic type conversion and validation with minimal code. The version endpoint is simple (3 fields), so we don't need the auto-detection complexity of Approach 3. We get 80% of the benefit for 20% of the effort.

2. **Proven at Scale** — FastAPI official docs, multiple Medium articles, and Stack Overflow consensus all recommend this pattern. It's battle-tested across thousands of production FastAPI apps. The `@lru_cache()` + `Depends()` pattern is the standard way to handle config injection.

3. **Testing-Friendly** — E2E pipeline needs testability. With BaseSettings, we can easily inject mock settings in tests by overriding the dependency. Approach 1 requires mocking `os.environ` (brittle), Approach 3 adds metadata complexity.

4. **Realistic Feature** — The goal is to test the E2E pipeline with a realistic feature. Real production FastAPI apps use BaseSettings, not raw `os.getenv()`. This feature should represent actual engineering practices.

5. **Low Dependency Cost** — `pydantic-settings` is maintained by the Pydantic team (same org as FastAPI's core dependency). It's a 200KB package, not a heavyweight framework. The dependency is justified by the value.

### Trade-off Accepted

We're giving up:
- **Approach 1's simplicity** — 15 minutes vs 1-2 hours implementation time. But the 2-hour investment pays back immediately in type safety and testability.
- **Approach 3's version auto-detection** — We'll manually set `APP_VERSION` in env vars instead of reading from `pyproject.toml`. This is acceptable because:
  - Simpler error handling (no `PackageNotFoundError` edge cases)
  - Works immediately in development without `pip install -e .`
  - Version endpoint is typically set by CI/CD anyway (git tag → env var)

For a single version endpoint, auto-detection is premature optimization. If we later need version sync across 10+ services, we can migrate to Approach 3.

---

## Research Sources

- [FastAPI Advanced Settings (Official)](https://fastapi.tiangolo.com/advanced/settings/) — Pydantic BaseSettings pattern
- [Pydantic Settings Best Practices](https://runebook.dev/en/articles/fastapi/advanced/settings/index) — Type safety and validation benefits
- [FastAPI Environment Variables Guide](https://medium.com/@joerosborne/how-to-set-environment-variables-in-fastapi-837c538190e3) — Comparison of os.getenv vs BaseSettings
- [FastAPI Twelve-Factor Config](https://medium.com/@hadiyolworld007/fastapi-pydantic-settings-twelve-factor-secrets-and-config-without-footguns-7990e2f20919) — Configuration best practices
- [Python Package Versioning](https://adamj.eu/tech/2025/07/30/python-check-package-version-importlib-metadata-version/) — importlib.metadata pattern
- [Single-Source Versioning Guide](https://packaging.python.org/en/latest/discussions/single-source-version/) — Official Python packaging recommendations
- [FastAPI Settings Dependency Injection](https://runebook.dev/en/articles/fastapi/advanced/settings/index/settings-in-a-dependency) — @lru_cache pattern
- [FastAPI Production Configuration](https://medium.com/@ramanbazhanau/preparing-fastapi-for-production-a-comprehensive-guide-d167e693aa2b) — Production deployment patterns
- [Pydantic Settings Multi-Environment](https://blog.greeden.me/en/2025/11/11/no-drama-configuration-secret-management-a-practical-fastapi-x-pydantic-settings-guide-environment-variables-env-multi-env-switching-type-safety-validation-secret-operation/) — Comprehensive pydantic-settings guide
- [Configuration Strategy Best Practices](https://www.shshell.com/blog/fastapi-module-3-lesson-3-config) — .env file security and type conversion
