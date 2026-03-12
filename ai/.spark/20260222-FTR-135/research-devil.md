# Devil's Advocate — API Version Endpoint

## Why NOT Do This?

### Argument 1: Information Disclosure Security Risk
**Concern:** Exposing version and environment publicly violates security principle of least information disclosure. Attackers use version fingerprinting to identify known vulnerabilities.

**Evidence:**
- OWASP recommends against exposing version information in production environments
- Template includes security.md (line 22-27) requiring careful secret management and security practices
- Architecture rules (ADR) emphasize explicit errors and security boundaries (architecture.md)
- No authentication on this endpoint means anyone can query version info

**Impact:** Medium

**Counter:** If we proceed anyway:
1. Only expose version in dev/staging environments (check `APP_ENV != "production"`)
2. Return minimal info — exclude internal build numbers, dependency versions
3. Add rate limiting to prevent enumeration attacks
4. Document in security policy as acceptable risk

### Argument 2: Configuration Complexity Without Clear Value
**Concern:** Adding 3 new environment variables (APP_NAME, APP_VERSION, APP_ENV) increases configuration surface area. What problem does this actually solve?

**Evidence:**
- DLD is a template/framework project — not a deployable app itself
- No existing codebase structure (src/ directory empty per Glob results)
- No evidence of deployment infrastructure that needs version checking
- Template already has version in pyproject.toml (line 1-11) — duplication

**Impact:** Low

**Counter:** If we proceed anyway:
1. Document WHY this is needed (which monitoring tool requires it?)
2. Auto-extract version from pyproject.toml instead of env var (single source of truth)
3. Make endpoint optional — only enable if APP_NAME is set

### Argument 3: Premature Infrastructure for Empty Project
**Concern:** This is a "hello world" endpoint being added to a framework template that has no actual application code yet.

**Evidence:**
- Glob for src/**/*.py = 0 results
- No domains defined (CLAUDE.md line 280: "domains/ {fill after bootstrap}")
- Template is meant for users to fill in AFTER /bootstrap
- Adding infrastructure before business logic violates DLD's own flow: bootstrap → board → architect → spark

**Impact:** High

**Counter:** If we proceed anyway:
1. This is an EXAMPLE feature to test /spark pipeline (as noted in Socratic insights)
2. Move to examples/ directory instead of core template
3. Document as "sample feature for testing framework"

---

## Simpler Alternatives

### Alternative 1: Static File Instead of API Endpoint
**Instead of:** FastAPI endpoint that reads env vars
**Do this:** Serve static `version.json` generated at build time
**Pros:**
- No code, no runtime logic, no env vars needed
- Can be generated from pyproject.toml during Docker build
- Web servers serve static files faster than Python endpoints
- Works even if app is broken (nginx serves file)
**Cons:**
- Can't show current environment dynamically (always shows build env)
- Requires build step integration
**Viability:** High — better for monitoring/ops use case

### Alternative 2: Extract from pyproject.toml Programmatically
**Instead of:** APP_VERSION env var
**Do this:** Read version from pyproject.toml at runtime using `importlib.metadata`
**Pros:**
- Single source of truth (version defined in one place)
- No config duplication
- Standard Python pattern: `importlib.metadata.version("package_name")`
**Cons:**
- Requires package to be installed (not just source code)
- Slightly slower (file read) vs env var
**Viability:** High — reduces config complexity

### Alternative 3: Skip Entirely Until Real Need
**Instead of:** Implement now
**Do this:** Wait until user runs /bootstrap and defines their actual app
**Pros:**
- Don't pollute template with example code
- User defines version strategy based on their actual deployment needs
- Follows DLD's own "no premature optimization" philosophy
**Cons:**
- No E2E test of /spark pipeline (but that's not user's problem)
**Viability:** High — most honest approach

**Verdict:** Alternative 1 (static file) or Alternative 3 (skip entirely) are better. If this is ONLY for testing /spark, document it as such and move to examples/.

---

## Edge Cases

| # | Scenario | Current Behavior | Proposed Behavior | Risk | Test Priority |
|---|----------|------------------|-------------------|------|---------------|
| 1 | APP_NAME not set | N/A | 500 error? Empty string? | High | P0 |
| 2 | APP_VERSION not set | N/A | 500 error? "unknown"? | High | P0 |
| 3 | APP_ENV not set | N/A | 500 error? Default to "dev"? | High | P0 |
| 4 | APP_ENV = invalid value (e.g., "staging123") | N/A | Accept any string? Validate enum? | Medium | P1 |
| 5 | APP_VERSION = malformed (e.g., "v1.0.0-beta-@#$") | N/A | Return as-is? Validate semver? | Low | P2 |
| 6 | Concurrent requests to /api/version | N/A | Should be idempotent (GET) | Low | P2 |
| 7 | APP_ENV = "production" | N/A | Should we HIDE version in prod for security? | High | P0 |

**Critical cases:** #1, #2, #3 (missing env vars) MUST be handled or endpoint will crash. #7 (production security) must be addressed or we're creating an attack vector.

---

## What Breaks?

### Side Effects

| Affected Component | File:line | Why It Breaks | Fix Required |
|--------------------|-----------|---------------|--------------|
| FastAPI router | N/A (doesn't exist yet) | Need to create API entry point | Create src/api/ structure per architecture.md |
| Environment config | N/A | Need .env.example with new vars | Document APP_NAME, APP_VERSION, APP_ENV |
| Deployment | N/A | CI/CD must set env vars | Update deployment docs/scripts |

### Dependencies at Risk

| Dependency | Type | Risk | Mitigation |
|------------|------|------|------------|
| pyproject.toml version | data | Low | Version defined in TWO places (duplication) | Use Alternative 2 (importlib.metadata) |
| Environment variables | config | Medium | If env vars missing = crash | Provide defaults or validate at startup |

---

## Eval Assertions (Derived from Risk Analysis)

### Deterministic Criteria

| ID | Criterion | Type | Pass Condition |
|----|-----------|------|----------------|
| DA-1 | Missing APP_NAME graceful | deterministic | Returns {"name": "unknown", ...} or {"name": "", ...}, not 500 error |
| DA-2 | Missing APP_VERSION graceful | deterministic | Returns {"version": "unknown", ...} not 500 error |
| DA-3 | Missing APP_ENV graceful | deterministic | Returns {"env": "dev", ...} (default) not 500 error |
| DA-4 | Response structure exact | deterministic | JSON keys match spec exactly: "name", "version", "env" |
| DA-5 | HTTP method correct | deterministic | GET /api/version returns 200, POST returns 405 Method Not Allowed |
| DA-6 | Content-Type header | deterministic | Response has Content-Type: application/json |

### Integration Criteria

| ID | Criterion | Type | Pass Condition |
|----|-----------|------|----------------|
| DA-7 | No auth required | integration | GET /api/version succeeds without Authorization header |
| DA-8 | Idempotent | integration | 10 concurrent requests return identical responses |
| DA-9 | FastAPI integration | integration | Endpoint registered in router, shows in /docs |

### LLM-as-Judge Criteria

| ID | Criterion | Type | Pass Condition |
|----|-----------|------|----------------|
| DA-10 | Security consideration | llm-judge | If APP_ENV="production", version info should be minimal (no internal build numbers/git hashes) |
| DA-11 | Error handling quality | llm-judge | Missing env vars handled gracefully with reasonable defaults, not crashes |

### Simpler Alternative Criteria

| ID | Criterion | Type | Pass Condition |
|----|-----------|------|----------------|
| SA-1 | Single source of truth | deterministic | Version NOT duplicated in env var AND pyproject.toml (should read from pyproject.toml) |
| SA-2 | Static file option | deterministic | If version.json exists, serve it instead of dynamic endpoint |
| SA-3 | Production safety | deterministic | If APP_ENV="production", endpoint returns minimal info or 404 |

---

## Assertion Summary

**Total:** 14 eval criteria (6 deterministic, 3 integration, 2 llm-judge, 3 simpler alternatives)

**P0 (Must Have):**
- DA-1, DA-2, DA-3: Graceful degradation for missing env vars
- DA-4, DA-5, DA-6: Correct HTTP endpoint behavior
- DA-7: Public access (no auth)
- SA-3: Production environment safety

**P1 (Should Have):**
- DA-8: Idempotency
- DA-9: FastAPI integration
- DA-10: Security best practices
- SA-1: Avoid config duplication

**P2 (Nice to Have):**
- DA-11: Error handling quality review
- SA-2: Static file alternative support

---

## Questions to Answer Before Implementation

1. **Question:** Is this a real feature for the template, or just an example to test /spark pipeline?
   **Why it matters:** If it's just a test, it should be in examples/ not core template. Don't pollute template with test code.

2. **Question:** What is the actual use case? Which monitoring tool/healthcheck requires this exact format?
   **Why it matters:** If no concrete use case, we're building speculative infrastructure. YAGNI principle applies.

3. **Question:** Should version info be exposed in production environments?
   **Why it matters:** Security fingerprinting risk. OWASP recommends against it. Need explicit decision with rationale.

4. **Question:** Why use environment variables instead of reading from pyproject.toml (single source of truth)?
   **Why it matters:** Config duplication creates drift. Version in pyproject.toml != version in APP_VERSION env var = confusion.

5. **Question:** Does this endpoint need to exist before any actual application code exists?
   **Why it matters:** DLD template has no src/ code yet. This violates "bootstrap → architect → feature" flow.

---

## Final Verdict

**Recommendation:** Reconsider

**Reasoning:**
This feature has three fundamental problems:

1. **Security:** Exposing version/env publicly violates information disclosure principles. No mitigation for production environments proposed.
2. **Premature:** Adding infrastructure to an empty template (no src/ code exists). Violates DLD's own bootstrap → architect → feature flow.
3. **No Clear Need:** Described as "E2E test of pipeline" not as solving actual user problem. Test code shouldn't be in template core.

The simpler alternatives (static version.json, read from pyproject.toml, or skip entirely) deliver same value with less risk and complexity.

**IF this is purely to test /spark pipeline:**
- Move to `examples/version-endpoint/`
- Document as "sample feature for testing"
- Don't commit to template core

**IF this is a real feature users need:**
- Answer the 5 questions above first
- Implement Alternative 2 (read from pyproject.toml, no env var duplication)
- Add production environment check (SA-3)
- Add all P0 eval criteria

**Conditions for success:**
1. Must handle missing env vars gracefully (DA-1, DA-2, DA-3) — no 500 errors
2. Must address production security concern (SA-3) — hide/minimize version info in production
3. Must avoid config duplication (SA-1) — single source of truth for version
4. Must document actual use case — who needs this endpoint and why?
