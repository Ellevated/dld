# Bug Fix: [BUG-182] In-Memory Rate Limits & Cron Safety

**Status:** done | **Priority:** P1 | **Date:** 2026-02-18
**Bug Hunt Report:** ai/.bughunt/20260217-full (20260217-full hunt, Group G4)

## Findings in This Group

| ID | Severity | Title |
|----|----------|-------|
| C-CR-008 | high | renew-subscription in-memory rate limit resets on cold start |
| C-CR-009 | high | verify-telegram-webapp in-memory rate limit resets on cold start |
| D-CR-002 | high | /link brute-force in-memory rate limit resets on cold start |
| D-QA-003 | medium | linkAttempts Map memory leak (never cleaned) |
| D-SEC-006 | high | DB-backed rate limiter (rate-limit.ts) fails open on error |
| C-CR-006 | medium | send-winback CRON_SECRET null check missing |
| D-CR-011 | medium | CRON_SECRET plain string equality (=== not timing-safe) across 10 cron functions |
| D-SEC-012 | high | content-factory and blog-expander accept service_role_key as auth token |

## Root Cause

Three distinct but related issues share a common theme: **Edge Function infrastructure patterns that are unsafe in serverless environments**.

### 1. In-memory state resets on cold start (C-CR-008, C-CR-009, D-CR-002, D-QA-003)

Deno Edge Functions are ephemeral. Module-level variables (`let lastInvocationTime`, `const rateLimitMap = new Map()`, `const linkAttempts = new Map()`) survive only within a single isolate instance. Supabase cold-starts functions frequently (no guaranteed warm pool), so:

- **renew-subscription** (line 16): `let lastInvocationTime = 0` resets to 0 on every cold start. The 1-hour rate limit check on line 34 always passes after a cold start, potentially allowing double-charge if pg_cron fires a retry while a fresh isolate starts.
- **verify-telegram-webapp** (line 17): `const rateLimitMap = new Map<number, number[]>()` resets on every cold start. The 5 req/hour per telegram_id limit is meaningless -- an attacker gets 5 free attempts per cold start.
- **commands.ts** (line 12): `const linkAttempts = new Map()` resets on cold start. The 5 attempts/10min brute-force protection for `/link` codes is ineffective. Additionally, entries are never evicted from the Map (no cleanup), so it leaks memory during warm periods.

### 2. DB-backed rate limiter fails open (D-SEC-006)

`_shared/infra/rate-limit.ts` line 39-41: When the DB query fails, the function returns without throwing, silently allowing the request through. The comment on line 22 explicitly states "Fails open: if DB is unavailable, request is allowed." This is a deliberate design choice but the wrong one for security-critical rate limiting. If Supabase has a transient error, ALL rate limits disappear.

### 3. CRON_SECRET auth inconsistencies (C-CR-006, D-CR-011, D-SEC-012)

Across 13 cron-triggered Edge Functions, there are **four distinct auth patterns**:

**Pattern A -- Good (null check + ===):** check-reminders, update-exchange-rates, send-monthly-summary, content-publish, content-research (5 functions)
```
if (!expectedSecret) return 500
if (token !== expectedSecret) return 403
```

**Pattern B -- Missing null check (=== only):** renew-subscription, expire-subscriptions, send-dunning-notification, send-winback (4 functions)
```
if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) return 401
```
The `!cronSecret` check catches null but combines it into a single 401 response, obscuring whether the secret is missing vs wrong. send-winback (line 37) has the weakest pattern: `if (req.headers.get("Authorization") !== \`Bearer ${cronSecret}\`)` -- when `cronSecret` is undefined, this becomes `!== "Bearer undefined"` which still rejects but for the wrong reason and leaks that the env var is not set.

**Pattern C -- Accepts service_role_key as alternative auth:** content-factory (line 82), blog-expander (line 59)
```
const isAuthorized = token === cronSecret || token === serviceKey
```
This is a security widening: if the service_role_key leaks, an attacker can trigger content generation. The service_role_key is meant for DB admin access, not for cron auth. It also bypasses any future CRON_SECRET rotation.

**Pattern D -- None use timingSafeEqual:** All 13 cron functions use `===` or `!==` for CRON_SECRET comparison. The `timingSafeEqual` function exists in `_shared/infra/crypto.ts` and is already used for Telegram webhook secret verification. The timing side-channel risk for CRON_SECRET is lower than for user-facing secrets (cron calls come from pg_cron, not attackers), but inconsistency creates confusion about which pattern is correct.

## Fix Approach

### Step 1: Create a shared `verifyCronSecret` utility

Create a new function in `_shared/infra/cron-auth.ts` that standardizes cron authentication:

- Accept the Request object
- Extract Bearer token from Authorization header
- Read `CRON_SECRET` from env
- Null-check the env var (return 500 if missing)
- Use `timingSafeEqual` for comparison (consistency with other secret comparisons)
- Return either `{ ok: true }` or `{ ok: false, response: Response }` so callers can early-return
- Do NOT accept service_role_key as an alternative

### Step 2: Replace all in-memory rate limits with DB-backed approach

For **renew-subscription**: Replace the module-level `lastInvocationTime` with a DB-based idempotency check. The function already queries `user_subscriptions` -- add a simple check using a `cron_invocations` table or repurpose the existing `ai_rate_limits` table with a "system" user_id and "renew-subscription" command. Alternatively, use the existing `billing_history` table to check if a renewal was already initiated for the same subscription period (which is the actual business concern, not the invocation timestamp).

For **verify-telegram-webapp**: Replace the module-level `rateLimitMap` with a DB-based approach. Insert attempt records into a new `auth_rate_limits` table (or reuse `ai_rate_limits` with a different command name like `telegram_verify:{telegram_id}`). Check count in the last hour before proceeding.

For **commands.ts /link**: Replace the module-level `linkAttempts` Map with a DB-based approach. Use the same table as verify-telegram-webapp, with command `link_attempt:{telegram_id}`. This also fixes the memory leak since DB records are cleaned up by the existing 24h cleanup in rate-limit.ts.

### Step 3: Fix rate-limit.ts fail-open behavior

Change the fail-open behavior in `_shared/infra/rate-limit.ts` to **fail closed** (deny on error). When the DB is unavailable, it is safer to temporarily block AI commands (which are non-critical) than to allow unlimited usage. The change is on line 41: instead of `return` (allow), throw `RateLimitExceededError` with a retry-after of 5 minutes.

### Step 4: Migrate all 13 cron functions to use the shared utility

Replace each function's inline CRON_SECRET verification with a call to `verifyCronSecret(req)`. For content-factory and blog-expander, remove the service_role_key acceptance -- they should only accept CRON_SECRET.

### Step 5: Add a new migration for cron_invocations table

Create a lightweight table for cron idempotency and auth rate limiting:

```
cron_invocations (
  id UUID PK,
  function_name TEXT NOT NULL,
  subject TEXT NOT NULL,  -- telegram_id, user_id, or "system"
  created_at TIMESTAMPTZ DEFAULT now()
)
INDEX on (function_name, subject, created_at DESC)
```

This table serves double duty:
- Cron idempotency: check if `renew-subscription` / `system` has a recent entry
- Auth rate limiting: check if `telegram_verify` / `{telegram_id}` has too many recent entries
- Link brute-force: check if `link_attempt` / `{telegram_id}` has too many recent entries

### Step 6: Update existing tests

- Update `renew-subscription-test.ts` rate limit tests to test the new DB-backed pattern
- Update `rate-limit-test.ts` to verify fail-closed behavior
- Add tests for the new `verifyCronSecret` utility

## Impact Tree

### UP -- who uses?

**rate-limit.ts consumers (8 Edge Functions):**
- `supabase/functions/telegram-webhook/handlers/analytics.ts` -- imports checkRateLimit, RateLimitExceededError, formatRateLimitMessage
- `supabase/functions/telegram-webhook/handlers/gamification.ts` -- imports checkRateLimit, RateLimitExceededError, formatRateLimitMessage
- `supabase/functions/telegram-webhook/handlers/negotiate.ts` -- imports checkRateLimit, RateLimitExceededError, formatRateLimitMessage
- `supabase/functions/achievements/index.ts` -- imports checkRateLimit, RateLimitExceededError
- `supabase/functions/price-comparison/index.ts` -- imports checkRateLimit, RateLimitExceededError
- `supabase/functions/generate-link-code/index.ts` -- imports checkRateLimit, RateLimitExceededError
- `supabase/functions/receive-email/index.ts` -- imports checkRateLimit, RateLimitExceededError
- `supabase/functions/scan-receipt/index.ts` -- imports checkRateLimit, RateLimitExceededError
- `supabase/functions/cancellation-guide/index.ts` -- imports checkRateLimit, RateLimitExceededError

**crypto.ts (timingSafeEqual) consumers (3 functions):**
- `supabase/functions/telegram-webhook/index.ts` -- webhook secret verification
- `supabase/functions/content-bot-webhook/index.ts` -- webhook secret verification
- `supabase/functions/_shared/telegram/webapp-verification.ts` -- initData HMAC verification

### DOWN -- what depends on?

- `_shared/infra/rate-limit.ts` depends on: Supabase client (jsr:@supabase/supabase-js), `ai_rate_limits` table, `Deno.env` for `AI_RATE_LIMIT_PER_HOUR`
- `_shared/infra/crypto.ts` depends on: Web Crypto API (`crypto.subtle`)
- All cron functions depend on: `Deno.env.get("CRON_SECRET")`
- `renew-subscription` depends on: `_shared/billing/yookassa.ts`, `_shared/billing/plans.ts`, `_shared/auth/supabase.ts`
- `verify-telegram-webapp` depends on: `_shared/telegram/webapp-verification.ts`, `_shared/auth/supabase.ts`, Clerk API
- `commands.ts` depends on: `_shared/telegram/link-service.ts`, `_shared/auth/supabase.ts`

### BY TERM -- grep project

| File | Line | Status | Action |
|------|------|--------|--------|
| `supabase/functions/renew-subscription/index.ts` | 16 | `let lastInvocationTime = 0` | Replace with DB idempotency check |
| `supabase/functions/renew-subscription/index.ts` | 28 | `!cronSecret \|\| authHeader !== ...` | Replace with verifyCronSecret() |
| `supabase/functions/verify-telegram-webapp/index.ts` | 17 | `const rateLimitMap = new Map()` | Replace with DB rate limit |
| `supabase/functions/verify-telegram-webapp/index.ts` | 19-30 | `function isRateLimited()` | Replace with DB-backed check |
| `supabase/functions/telegram-webhook/handlers/commands.ts` | 12 | `const linkAttempts = new Map()` | Replace with DB rate limit |
| `supabase/functions/telegram-webhook/handlers/commands.ts` | 14-21 | `function checkLinkRateLimit()` | Replace with DB-backed check |
| `supabase/functions/_shared/infra/rate-limit.ts` | 41 | `return // fail open` | Change to throw (fail closed) |
| `supabase/functions/expire-subscriptions/index.ts` | 17-21 | `!cronSecret \|\| authHeader !==` | Replace with verifyCronSecret() |
| `supabase/functions/send-dunning-notification/index.ts` | 19-23 | `!cronSecret \|\| authHeader !==` | Replace with verifyCronSecret() |
| `supabase/functions/send-winback/index.ts` | 36-38 | `authHeader !== Bearer ${cronSecret}` | Replace with verifyCronSecret() |
| `supabase/functions/check-reminders/index.ts` | 56-74 | token !== expectedSecret | Replace with verifyCronSecret() |
| `supabase/functions/update-exchange-rates/index.ts` | 25-42 | token !== expectedSecret | Replace with verifyCronSecret() |
| `supabase/functions/send-monthly-summary/index.ts` | 16-31 | token !== expectedSecret | Replace with verifyCronSecret() |
| `supabase/functions/content-publish/index.ts` | 17-36 | token !== expectedSecret | Replace with verifyCronSecret() |
| `supabase/functions/content-research/index.ts` | 12-28 | token !== expectedSecret | Replace with verifyCronSecret() |
| `supabase/functions/content-factory/index.ts` | 76-89 | token === cronSecret \|\| token === serviceKey | Replace with verifyCronSecret() (remove service_role_key acceptance) |
| `supabase/functions/blog-expander/index.ts` | 53-66 | token === cronSecret \|\| token === serviceKey | Replace with verifyCronSecret() (remove service_role_key acceptance) |
| `supabase/functions/tests/renew-subscription-test.ts` | 94-110 | Rate limit tests assume in-memory pattern | Rewrite for DB-backed pattern |
| `supabase/functions/tests/_shared/rate-limit-test.ts` | 1-21 | Tests RateLimitExceededError format only | Add fail-closed behavior tests |
| `supabase/functions/tests/check-reminders-test.ts` | 80-139 | Tests inline cron auth pattern | Update to test verifyCronSecret() |

## Research Sources

No external research needed. The `timingSafeEqual` utility already exists at `_shared/infra/crypto.ts` and is battle-tested in the Telegram webhook auth flow. The DB-backed rate limiting pattern already exists in `_shared/infra/rate-limit.ts` using the `ai_rate_limits` table -- the in-memory patterns are legacy code that was never migrated.

## Allowed Files

### New files
1. `supabase/functions/_shared/infra/cron-auth.ts` -- shared verifyCronSecret utility
2. `supabase/functions/tests/_shared/cron-auth-test.ts` -- tests for the new utility
3. `supabase/migrations/00037_cron_invocations.sql` -- new table for cron idempotency and auth rate limits (verified: 00036 is latest existing migration)

### Modified files (in-memory rate limit removal)
4. `supabase/functions/renew-subscription/index.ts` -- remove in-memory lastInvocationTime, use DB idempotency + verifyCronSecret
5. `supabase/functions/verify-telegram-webapp/index.ts` -- remove in-memory rateLimitMap, use DB rate limit
6. `supabase/functions/telegram-webhook/handlers/commands.ts` -- remove in-memory linkAttempts Map, use DB rate limit

### Modified files (fail-open fix)
7. `supabase/functions/_shared/infra/rate-limit.ts` -- change fail-open to fail-closed

### Modified files (cron auth standardization)
8. `supabase/functions/expire-subscriptions/index.ts` -- use verifyCronSecret
9. `supabase/functions/send-dunning-notification/index.ts` -- use verifyCronSecret
10. `supabase/functions/send-winback/index.ts` -- use verifyCronSecret
11. `supabase/functions/check-reminders/index.ts` -- use verifyCronSecret
12. `supabase/functions/update-exchange-rates/index.ts` -- use verifyCronSecret
13. `supabase/functions/send-monthly-summary/index.ts` -- use verifyCronSecret
14. `supabase/functions/content-publish/index.ts` -- use verifyCronSecret
15. `supabase/functions/content-research/index.ts` -- use verifyCronSecret
16. `supabase/functions/content-factory/index.ts` -- use verifyCronSecret, remove service_role_key acceptance
17. `supabase/functions/blog-expander/index.ts` -- use verifyCronSecret, remove service_role_key acceptance

### Modified test files
18. `supabase/functions/tests/renew-subscription-test.ts` -- update rate limit tests for DB pattern
19. `supabase/functions/tests/_shared/rate-limit-test.ts` -- add fail-closed behavior tests
20. `supabase/functions/tests/check-reminders-test.ts` -- update cron auth tests to reference verifyCronSecret pattern

## Tests

### Minimum required test cases

1. **verifyCronSecret returns ok:true with valid Bearer token** -- verify the happy path works with timingSafeEqual
2. **verifyCronSecret returns 401 when Authorization header is missing** -- no auth header present
3. **verifyCronSecret returns 401 when Authorization header is not Bearer scheme** -- e.g., "Basic abc"
4. **verifyCronSecret returns 500 when CRON_SECRET env var is not set** -- server misconfiguration detected
5. **verifyCronSecret returns 403 when token does not match CRON_SECRET** -- wrong token
6. **verifyCronSecret rejects service_role_key** -- must not accept alternative tokens
7. **rate-limit.ts checkRateLimit throws on DB error (fail-closed)** -- verify the behavior change from returning void to throwing
8. **DB rate limit for verify-telegram-webapp blocks after 5 attempts in 1 hour** -- functional test of the new DB-backed pattern
9. **DB rate limit for /link blocks after 5 attempts in 10 minutes** -- functional test for brute-force protection
10. **renew-subscription DB idempotency prevents double invocation within 1 hour** -- verify the cron cannot double-charge

## Drift Log

**Checked:** 2026-03-01 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `supabase/migrations/` | New migrations 00035, 00036 added since spec | AUTO-FIX: migration number updated to 00037 |
| All 13 cron functions | Code unchanged since spec | No action needed |
| `_shared/infra/rate-limit.ts` | Code unchanged | No action needed |
| `_shared/infra/crypto.ts` | Code unchanged | No action needed |

### References Updated
- Migration file: `00035_cron_invocations.sql` -> `00037_cron_invocations.sql`

---

## Detailed Implementation Plan

### Task 1: Create migration for cron_invocations table

**Files:**
- Create: `supabase/migrations/00037_cron_invocations.sql`

**Context:**
This table serves as the DB-backed replacement for all in-memory rate limiting and cron idempotency checks. It stores function invocation records with a function_name + subject + timestamp pattern that supports both per-user rate limiting (verify-telegram-webapp, /link brute-force) and cron deduplication (renew-subscription). An admin-only RLS policy ensures only service_role can write/read (cron functions use createAdminClient).

**Steps:**

```sql
-- supabase/migrations/00037_cron_invocations.sql
-- DB-backed rate limiting and cron idempotency (BUG-182)
-- Replaces in-memory rate limits that reset on cold start

CREATE TABLE IF NOT EXISTS cron_invocations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  function_name TEXT NOT NULL,
  subject TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Primary lookup: "how many times has function X been called for subject Y recently?"
CREATE INDEX idx_cron_invocations_lookup
  ON cron_invocations(function_name, subject, created_at DESC);

-- Cleanup index: delete old records efficiently
CREATE INDEX idx_cron_invocations_cleanup
  ON cron_invocations(created_at);

-- RLS: only service_role can access (cron functions use admin client)
ALTER TABLE cron_invocations ENABLE ROW LEVEL SECURITY;

-- No user-facing policies needed — only admin client accesses this table
```

**Acceptance Criteria:**
- [ ] Migration file exists at `supabase/migrations/00037_cron_invocations.sql`
- [ ] No duplicate migration number (`ls supabase/migrations/ | grep 00037` returns exactly 1 file)
- [ ] SQL is valid (no syntax errors)

---

### Task 2: Create shared verifyCronSecret utility + tests

**Files:**
- Create: `supabase/functions/_shared/infra/cron-auth.ts`
- Create: `supabase/functions/tests/_shared/cron-auth-test.ts`

**Context:**
This utility standardizes cron authentication across all 13 Edge Functions. It extracts the Bearer token, null-checks the CRON_SECRET env var, and uses timingSafeEqual for comparison. Returns a discriminated union so callers can early-return on failure. Does NOT accept service_role_key as alternative auth.

**Step 1: Create cron-auth.ts**

```typescript
// supabase/functions/_shared/infra/cron-auth.ts

/**
 * Module: cron-auth
 * Role: Standardized cron secret verification for all pg_cron-triggered Edge Functions
 * Uses: _shared/infra/crypto.ts (timingSafeEqual)
 * Used by: All 13 cron Edge Functions
 */
import { timingSafeEqual } from "./crypto.ts"

type CronAuthResult =
  | { ok: true }
  | { ok: false; response: Response }

/**
 * Verify that the request carries a valid CRON_SECRET Bearer token.
 *
 * Returns { ok: true } on success, or { ok: false, response } with
 * an appropriate HTTP error response on failure.
 *
 * Security:
 * - Uses timingSafeEqual to prevent timing side-channel attacks
 * - Returns 500 if CRON_SECRET env var is not set (server misconfiguration)
 * - Returns 401 if Authorization header is missing or not Bearer scheme
 * - Returns 403 if token does not match CRON_SECRET
 * - Does NOT accept service_role_key or any alternative tokens
 */
export async function verifyCronSecret(req: Request): Promise<CronAuthResult> {
  const authHeader = req.headers.get("Authorization")

  if (!authHeader?.startsWith("Bearer ")) {
    return {
      ok: false,
      response: new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      }),
    }
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {
    console.error("CRON_SECRET environment variable is required but not set")
    return {
      ok: false,
      response: new Response(JSON.stringify({ error: "Server configuration error" }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      }),
    }
  }

  const isValid = await timingSafeEqual(token, expectedSecret)

  if (!isValid) {
    console.warn("Invalid cron token")
    return {
      ok: false,
      response: new Response(JSON.stringify({ error: "Forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      }),
    }
  }

  return { ok: true }
}
```

**Step 2: Create cron-auth-test.ts**

```typescript
// supabase/functions/tests/_shared/cron-auth-test.ts

import { assertEquals, assert } from "jsr:@std/assert@1"
import { verifyCronSecret } from "../../_shared/infra/cron-auth.ts"

// Helper to create Request with Authorization header
function makeRequest(authHeader?: string): Request {
  const headers = new Headers()
  if (authHeader) headers.set("Authorization", authHeader)
  return new Request("https://example.com/test", { headers })
}

// --- Happy path ---

Deno.test("verifyCronSecret — returns ok:true with valid Bearer token", async () => {
  const secret = "test-cron-secret-value"
  const origGet = Deno.env.get
  Deno.env.get = (key: string) => key === "CRON_SECRET" ? secret : origGet.call(Deno.env, key)
  try {
    const result = await verifyCronSecret(makeRequest(`Bearer ${secret}`))
    assertEquals(result.ok, true)
  } finally {
    Deno.env.get = origGet
  }
})

// --- Missing/invalid Authorization header ---

Deno.test("verifyCronSecret — returns 401 when Authorization header is missing", async () => {
  const result = await verifyCronSecret(makeRequest())
  assertEquals(result.ok, false)
  if (!result.ok) {
    assertEquals(result.response.status, 401)
  }
})

Deno.test("verifyCronSecret — returns 401 when Authorization is not Bearer scheme", async () => {
  const result = await verifyCronSecret(makeRequest("Basic abc123"))
  assertEquals(result.ok, false)
  if (!result.ok) {
    assertEquals(result.response.status, 401)
  }
})

Deno.test("verifyCronSecret — returns 401 when Authorization is empty string", async () => {
  const result = await verifyCronSecret(makeRequest(""))
  assertEquals(result.ok, false)
  if (!result.ok) {
    assertEquals(result.response.status, 401)
  }
})

// --- Missing CRON_SECRET env var ---

Deno.test("verifyCronSecret — returns 500 when CRON_SECRET env var is not set", async () => {
  const origGet = Deno.env.get
  Deno.env.get = (key: string) => key === "CRON_SECRET" ? undefined as unknown as string : origGet.call(Deno.env, key)
  try {
    const result = await verifyCronSecret(makeRequest("Bearer some-token"))
    assertEquals(result.ok, false)
    if (!result.ok) {
      assertEquals(result.response.status, 500)
    }
  } finally {
    Deno.env.get = origGet
  }
})

// --- Wrong token ---

Deno.test("verifyCronSecret — returns 403 when token does not match CRON_SECRET", async () => {
  const origGet = Deno.env.get
  Deno.env.get = (key: string) => key === "CRON_SECRET" ? "correct-secret" : origGet.call(Deno.env, key)
  try {
    const result = await verifyCronSecret(makeRequest("Bearer wrong-secret"))
    assertEquals(result.ok, false)
    if (!result.ok) {
      assertEquals(result.response.status, 403)
    }
  } finally {
    Deno.env.get = origGet
  }
})

// --- Rejects service_role_key ---

Deno.test("verifyCronSecret — rejects service_role_key (only CRON_SECRET accepted)", async () => {
  const cronSecret = "cron-secret-value"
  const serviceRoleKey = "service-role-key-different"
  const origGet = Deno.env.get
  Deno.env.get = (key: string) => {
    if (key === "CRON_SECRET") return cronSecret
    if (key === "SUPABASE_SERVICE_ROLE_KEY") return serviceRoleKey
    return origGet.call(Deno.env, key)
  }
  try {
    const result = await verifyCronSecret(makeRequest(`Bearer ${serviceRoleKey}`))
    assertEquals(result.ok, false)
    if (!result.ok) {
      assertEquals(result.response.status, 403)
    }
  } finally {
    Deno.env.get = origGet
  }
})

// --- Contract test: source code uses timingSafeEqual ---

Deno.test("cron-auth — uses timingSafeEqual for comparison", async () => {
  const source = await Deno.readTextFile(
    new URL("../../_shared/infra/cron-auth.ts", import.meta.url),
  )
  assertEquals(
    source.includes("timingSafeEqual"),
    true,
    "cron-auth.ts must use timingSafeEqual from crypto.ts",
  )
})

Deno.test("cron-auth — does NOT reference service_role_key", async () => {
  const source = await Deno.readTextFile(
    new URL("../../_shared/infra/cron-auth.ts", import.meta.url),
  )
  assertEquals(
    source.includes("service_role"),
    false,
    "cron-auth.ts must NOT accept service_role_key as alternative auth",
  )
})
```

**Acceptance Criteria:**
- [ ] `cron-auth.ts` exports `verifyCronSecret` function
- [ ] All 8 test cases pass: `deno test --allow-all supabase/functions/tests/_shared/cron-auth-test.ts`
- [ ] Uses `timingSafeEqual` from crypto.ts (not `===`)
- [ ] Does not reference `service_role_key`

---

### Task 3: Fix rate-limit.ts fail-open to fail-closed + update tests

**Files:**
- Modify: `supabase/functions/_shared/infra/rate-limit.ts` (lines 22, 39-41)
- Modify: `supabase/functions/tests/_shared/rate-limit-test.ts`

**Context:**
The current `checkRateLimit` function silently returns (allows the request) when the DB query fails. This is dangerous for security-critical rate limiting. Changing to fail-closed means throwing RateLimitExceededError with a 5-minute retry-after when DB is unreachable.

**Step 1: Modify rate-limit.ts**

Replace lines 19-42 in `supabase/functions/_shared/infra/rate-limit.ts`:

Current code (lines 19-42):
```typescript
/**
 * Check rate limit for user+command. Records usage if within limit.
 * Throws RateLimitExceededError if exceeded.
 * Fails open: if DB is unavailable, request is allowed.
 */
export async function checkRateLimit(
  supabase: SupabaseClient,
  userId: string,
  command: string,
): Promise<void> {
  const maxPerHour = parseInt(Deno.env.get("AI_RATE_LIMIT_PER_HOUR") ?? "10")
  const windowMs = 3_600_000 // 1 hour
  const windowStart = new Date(Date.now() - windowMs)

  const { count, error: countError } = await supabase
    .from("ai_rate_limits")
    .select("*", { count: "exact", head: true })
    .eq("user_id", userId)
    .gte("created_at", windowStart.toISOString())

  if (countError) {
    console.error("Rate limit check failed:", countError)
    return // fail open
  }
```

New code:
```typescript
/**
 * Check rate limit for user+command. Records usage if within limit.
 * Throws RateLimitExceededError if exceeded.
 * Fails closed: if DB is unavailable, request is denied (D-SEC-006).
 */
export async function checkRateLimit(
  supabase: SupabaseClient,
  userId: string,
  command: string,
): Promise<void> {
  const maxPerHour = parseInt(Deno.env.get("AI_RATE_LIMIT_PER_HOUR") ?? "10")
  const windowMs = 3_600_000 // 1 hour
  const windowStart = new Date(Date.now() - windowMs)

  const { count, error: countError } = await supabase
    .from("ai_rate_limits")
    .select("*", { count: "exact", head: true })
    .eq("user_id", userId)
    .gte("created_at", windowStart.toISOString())

  if (countError) {
    console.error("Rate limit check failed (fail-closed):", countError)
    throw new RateLimitExceededError(
      command,
      new Date(Date.now() + 5 * 60_000), // retry after 5 minutes
    )
  }
```

**Step 2: Add fail-closed test to rate-limit-test.ts**

Append to `supabase/functions/tests/_shared/rate-limit-test.ts`:

```typescript
// --- D-SEC-006: Fail-closed behavior (contract test) ---

Deno.test("rate-limit.ts — fail-closed: does NOT return on DB error", async () => {
  const source = await Deno.readTextFile(
    new URL("../../_shared/infra/rate-limit.ts", import.meta.url),
  )
  // Old fail-open pattern: "return // fail open"
  assertEquals(
    source.includes("return // fail open"),
    false,
    "rate-limit.ts must NOT contain 'return // fail open' (D-SEC-006)",
  )
})

Deno.test("rate-limit.ts — fail-closed: throws RateLimitExceededError on DB error", async () => {
  const source = await Deno.readTextFile(
    new URL("../../_shared/infra/rate-limit.ts", import.meta.url),
  )
  assertEquals(
    source.includes("fail-closed"),
    true,
    "rate-limit.ts must reference fail-closed behavior in comment",
  )
  // Verify the pattern: if countError → throw (not return)
  const countErrorBlock = source.slice(
    source.indexOf("if (countError)"),
    source.indexOf("if ((count"),
  )
  assertEquals(
    countErrorBlock.includes("throw new RateLimitExceededError"),
    true,
    "Must throw RateLimitExceededError when DB query fails",
  )
})

Deno.test("rate-limit.ts — fail-closed: docstring updated", async () => {
  const source = await Deno.readTextFile(
    new URL("../../_shared/infra/rate-limit.ts", import.meta.url),
  )
  assertEquals(
    source.includes("Fails closed"),
    true,
    "Docstring must say 'Fails closed' not 'Fails open'",
  )
})
```

**Acceptance Criteria:**
- [ ] `rate-limit.ts` throws on DB error instead of returning
- [ ] Docstring says "Fails closed" not "Fails open"
- [ ] All 5 rate-limit tests pass: `deno test --allow-all supabase/functions/tests/_shared/rate-limit-test.ts`

---

### Task 4: Replace in-memory rate limits with DB-backed pattern in renew-subscription

**Files:**
- Modify: `supabase/functions/renew-subscription/index.ts` (lines 15-39)
- Modify: `supabase/functions/tests/renew-subscription-test.ts` (lines 94-110)

**Context:**
Remove the in-memory `lastInvocationTime` variable and replace it with a DB-backed idempotency check using the `cron_invocations` table. Also replace the inline cron auth with `verifyCronSecret()`.

**Step 1: Modify renew-subscription/index.ts**

Replace lines 1-39 (imports through rate limit) with:

Current code (lines 1-39):
```typescript
/**
 * Module: renew-subscription
 * Role: Cron job to auto-renew expiring subscriptions with retry logic
 * Uses: yookassa (createRecurringPayment), supabase (admin client), plans (PLAN_CONFIG)
 * Used by: pg_cron daily trigger
 */

import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { createRecurringPayment } from "../_shared/billing/yookassa.ts"
import { PLAN_CONFIG, MAX_RENEWAL_RETRIES } from "../_shared/billing/plans.ts"
import { createBot } from "../_shared/telegram/bot.ts"
import { formatDunningMessage } from "../_shared/telegram/telegram-format.ts"

/** In-memory rate limit: track last invocation time */
let lastInvocationTime = 0
const RATE_LIMIT_MS = 3_600_000 // 1 hour

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret
  const cronSecret = Deno.env.get("CRON_SECRET")
  const authHeader = req.headers.get("Authorization")

  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return errorResponse("Unauthorized", 401)
  }

  // Rate limit: max 1 invocation per hour
  const now = Date.now()
  if (now - lastInvocationTime < RATE_LIMIT_MS) {
    const retryAfterSec = Math.ceil((RATE_LIMIT_MS - (now - lastInvocationTime)) / 1000)
    console.warn(`Rate limited: last invocation ${Math.floor((now - lastInvocationTime) / 1000)}s ago`)
    return errorResponse(`Rate limited. Retry after ${retryAfterSec}s`, 429)
  }
  lastInvocationTime = now
```

New code:
```typescript
/**
 * Module: renew-subscription
 * Role: Cron job to auto-renew expiring subscriptions with retry logic
 * Uses: yookassa (createRecurringPayment), supabase (admin client), plans (PLAN_CONFIG), cron-auth
 * Used by: pg_cron daily trigger
 */

import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { createRecurringPayment } from "../_shared/billing/yookassa.ts"
import { PLAN_CONFIG, MAX_RENEWAL_RETRIES } from "../_shared/billing/plans.ts"
import { createBot } from "../_shared/telegram/bot.ts"
import { formatDunningMessage } from "../_shared/telegram/telegram-format.ts"
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"

const RATE_LIMIT_MS = 3_600_000 // 1 hour

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response

  const supabase = createAdminClient()

  // DB-backed idempotency: max 1 invocation per hour (C-CR-008)
  const windowStart = new Date(Date.now() - RATE_LIMIT_MS)
  const { count, error: countError } = await supabase
    .from("cron_invocations")
    .select("*", { count: "exact", head: true })
    .eq("function_name", "renew-subscription")
    .eq("subject", "system")
    .gte("created_at", windowStart.toISOString())

  if (countError) {
    console.error("Idempotency check failed:", countError)
    return errorResponse("Database error", 500)
  }

  if ((count ?? 0) > 0) {
    console.warn("Rate limited: renew-subscription already invoked within 1 hour")
    return errorResponse("Rate limited. Already invoked within 1 hour.", 429)
  }

  // Record this invocation
  await supabase
    .from("cron_invocations")
    .insert({ function_name: "renew-subscription", subject: "system" })
```

NOTE: The line `const supabase = createAdminClient()` on the old line 41 must be REMOVED since it's now included above. The coder should ensure no duplicate `createAdminClient()` call.

**Step 2: Update renew-subscription-test.ts**

Replace lines 94-110 (rate limit tests) with DB-backed pattern tests:

Current code (lines 94-110):
```typescript
// --- Rate limit logic tests ---

Deno.test("rate limit — invocations within 1 hour are rejected", () => {
  const RATE_LIMIT_MS = 3_600_000
  const lastInvocation = Date.now() - 1_800_000 // 30 min ago
  const now = Date.now()
  const isRateLimited = (now - lastInvocation) < RATE_LIMIT_MS
  assertEquals(isRateLimited, true)
})

Deno.test("rate limit — invocations after 1 hour are allowed", () => {
  const RATE_LIMIT_MS = 3_600_000
  const lastInvocation = Date.now() - 3_700_000 // 61+ min ago
  const now = Date.now()
  const isRateLimited = (now - lastInvocation) < RATE_LIMIT_MS
  assertEquals(isRateLimited, false)
})
```

New code:
```typescript
// --- Rate limit logic tests (DB-backed, BUG-182) ---

Deno.test("renew-subscription — uses cron_invocations table for rate limit", async () => {
  const source = await Deno.readTextFile(
    new URL("../renew-subscription/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes("cron_invocations"),
    true,
    "Must use cron_invocations table for DB-backed rate limiting",
  )
})

Deno.test("renew-subscription — no in-memory lastInvocationTime", async () => {
  const source = await Deno.readTextFile(
    new URL("../renew-subscription/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes("lastInvocationTime"),
    false,
    "Must NOT use in-memory lastInvocationTime (C-CR-008)",
  )
})

Deno.test("renew-subscription — uses verifyCronSecret", async () => {
  const source = await Deno.readTextFile(
    new URL("../renew-subscription/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes("verifyCronSecret"),
    true,
    "Must use verifyCronSecret() for cron auth (D-CR-011)",
  )
})
```

**Acceptance Criteria:**
- [ ] `renew-subscription/index.ts` has no `lastInvocationTime`
- [ ] Uses `verifyCronSecret()` for auth
- [ ] Uses `cron_invocations` table for idempotency
- [ ] All tests pass: `deno test --allow-all supabase/functions/tests/renew-subscription-test.ts`

---

### Task 5: Replace in-memory rate limits in verify-telegram-webapp and commands.ts

**Files:**
- Modify: `supabase/functions/verify-telegram-webapp/index.ts` (lines 16-30, 88-95)
- Modify: `supabase/functions/telegram-webhook/handlers/commands.ts` (lines 11-21, 117, 238)

**Context:**
Both files use in-memory Maps for rate limiting that reset on cold start. Replace with DB-backed checks using the `cron_invocations` table. The verify-telegram-webapp function checks 5 req/hour per telegram_id. The commands.ts checks 5 attempts/10min per telegram_id for /link brute-force protection.

**Step 1: Modify verify-telegram-webapp/index.ts**

Replace lines 16-30 (the in-memory rate limit block):

Current code (lines 16-30):
```typescript
// Simple in-memory rate limiting (5 req/hour per telegram_id)
const rateLimitMap = new Map<number, number[]>()

function isRateLimited(telegramId: number): boolean {
  const now = Date.now()
  const hourAgo = now - 3600000 // 1 hour
  const attempts = rateLimitMap.get(telegramId) || []
  const recentAttempts = attempts.filter(ts => ts > hourAgo)

  if (recentAttempts.length >= 5) return true

  recentAttempts.push(now)
  rateLimitMap.set(telegramId, recentAttempts)
  return false
}
```

New code:
```typescript
// DB-backed rate limiting: 5 req/hour per telegram_id (C-CR-009, D-QA-003)
async function checkTelegramVerifyRateLimit(
  supabase: import("jsr:@supabase/supabase-js@2").SupabaseClient,
  telegramId: number,
): Promise<boolean> {
  const windowStart = new Date(Date.now() - 3_600_000) // 1 hour

  const { count, error } = await supabase
    .from("cron_invocations")
    .select("*", { count: "exact", head: true })
    .eq("function_name", "telegram_verify")
    .eq("subject", String(telegramId))
    .gte("created_at", windowStart.toISOString())

  if (error) {
    console.error("Rate limit check failed (fail-closed):", error)
    return true // fail closed: deny on DB error
  }

  if ((count ?? 0) >= 5) return true

  // Record this attempt
  await supabase
    .from("cron_invocations")
    .insert({ function_name: "telegram_verify", subject: String(telegramId) })

  return false
}
```

Then replace lines 88-95 (the rate limit usage):

Current code (lines 88-95):
```typescript
    // Rate limiting
    if (isRateLimited(verification.telegramId)) {
      return jsonResponse(
        { status: 'error', message: 'Слишком много попыток. Подождите час.' },
        429,
        req
      )
    }
```

New code:
```typescript
    // DB-backed rate limiting (C-CR-009)
    const supabaseForRateLimit = createAdminClient()
    if (await checkTelegramVerifyRateLimit(supabaseForRateLimit, verification.telegramId)) {
      return jsonResponse(
        { status: 'error', message: 'Слишком много попыток. Подождите час.' },
        429,
        req
      )
    }
```

NOTE: The `const supabase = createAdminClient()` on line 97 of the original code still exists below for the rest of the function. The coder must keep it but can rename `supabaseForRateLimit` to just reuse `supabase` by moving the `createAdminClient()` call to before the rate limit check instead. The simplest approach: move `const supabase = createAdminClient()` from line 97 to just before the rate limit check (after the HMAC verification on line 86), then use `supabase` everywhere. Remove the separate `supabaseForRateLimit` variable.

Concretely, the final shape of lines 86-100 should be:

```typescript
    // Create admin client for DB operations (moved up for rate limit check)
    const supabase = createAdminClient()

    // DB-backed rate limiting (C-CR-009)
    if (await checkTelegramVerifyRateLimit(supabase, verification.telegramId)) {
      return jsonResponse(
        { status: 'error', message: 'Слишком много попыток. Подождите час.' },
        429,
        req
      )
    }

    // Check if telegram_id already linked
    const { data: existingLink } = await supabase
```

And the old `const supabase = createAdminClient()` on line 97 must be removed.

**Step 2: Modify commands.ts**

Replace lines 11-21 (the in-memory linkAttempts block):

Current code (lines 11-21):
```typescript
// Rate limit for /link and deep-link: max 5 attempts per telegram_id per 10 minutes
const linkAttempts = new Map<number, { count: number; resetAt: number }>()

function checkLinkRateLimit(telegramId: number): boolean {
  const now = Date.now()
  const entry = linkAttempts.get(telegramId) ?? { count: 0, resetAt: now + 10 * 60 * 1000 }
  if (now > entry.resetAt) { entry.count = 0; entry.resetAt = now + 10 * 60 * 1000 }
  entry.count++
  linkAttempts.set(telegramId, entry)
  return entry.count > 5
}
```

New code:
```typescript
// DB-backed rate limit for /link and deep-link: max 5 attempts per telegram_id per 10 minutes (D-CR-002, D-QA-003)
async function checkLinkRateLimit(telegramId: number): Promise<boolean> {
  const { createAdminClient: createAdmin } = await import("../../_shared/auth/supabase.ts")
  const supabase = createAdmin()
  const windowStart = new Date(Date.now() - 10 * 60 * 1000) // 10 minutes

  const { count, error } = await supabase
    .from("cron_invocations")
    .select("*", { count: "exact", head: true })
    .eq("function_name", "link_attempt")
    .eq("subject", String(telegramId))
    .gte("created_at", windowStart.toISOString())

  if (error) {
    console.error("Link rate limit check failed (fail-closed):", error)
    return true // fail closed
  }

  if ((count ?? 0) >= 5) return true

  // Record this attempt
  await supabase
    .from("cron_invocations")
    .insert({ function_name: "link_attempt", subject: String(telegramId) })

  return false
}
```

IMPORTANT: Since `checkLinkRateLimit` is now async, the two call sites must be updated to `await` it:

Line 117 (inside `/start` deep-link handler):
Current: `if (checkLinkRateLimit(telegramId)) return ctx.reply("...")`
New: `if (await checkLinkRateLimit(telegramId)) return ctx.reply("...")`

Line 238 (inside `/link` command handler):
Current: `if (checkLinkRateLimit(telegramId)) return ctx.reply("...")`
New: `if (await checkLinkRateLimit(telegramId)) return ctx.reply("...")`

**Acceptance Criteria:**
- [ ] `verify-telegram-webapp/index.ts` has no `rateLimitMap` or `isRateLimited`
- [ ] `commands.ts` has no `linkAttempts` Map
- [ ] Both use `cron_invocations` table for rate limiting
- [ ] Both fail closed on DB error
- [ ] `grep "const rateLimitMap\|const linkAttempts" supabase/functions/` = 0 results

---

### Task 6: Migrate Pattern B cron functions to verifyCronSecret

**Files:**
- Modify: `supabase/functions/expire-subscriptions/index.ts` (lines 17-21)
- Modify: `supabase/functions/send-dunning-notification/index.ts` (lines 19-23)
- Modify: `supabase/functions/send-winback/index.ts` (lines 36-38)

**Context:**
These three functions use Pattern B auth (combined `!cronSecret || authHeader !== ...` check). Replace with standardized `verifyCronSecret()`.

**Step 1: Modify expire-subscriptions/index.ts**

Replace lines 8-22:

Current code (lines 8-22):
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret
  const cronSecret = Deno.env.get("CRON_SECRET")
  const authHeader = req.headers.get("Authorization")

  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return errorResponse("Unauthorized", 401)
  }
```

New code:
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 2: Modify send-dunning-notification/index.ts**

Replace lines 8-24:

Current code (lines 8-24):
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { createBot } from "../_shared/telegram/bot.ts"
import { InlineKeyboard } from "npm:grammy@1.39.3"

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret
  const cronSecret = Deno.env.get("CRON_SECRET")
  const authHeader = req.headers.get("Authorization")

  if (!cronSecret || authHeader !== `Bearer ${cronSecret}`) {
    return errorResponse("Unauthorized", 401)
  }
```

New code:
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { createBot } from "../_shared/telegram/bot.ts"
import { InlineKeyboard } from "npm:grammy@1.39.3"
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") {
    return new Response(null, { status: 200 })
  }

  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 3: Modify send-winback/index.ts**

Replace lines 1-39:

Current code (lines 1-39):
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"

const BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? ""
const APP_URL = Deno.env.get("APP_URL") ?? "https://plpilot.ru"

interface WinbackCampaign {
  name: string
  daysAfterChurn: number
  offerCode: string
  message: string
}

const CAMPAIGNS: WinbackCampaign[] = [
  {
    name: 'day30',
    daysAfterChurn: 30,
    offerCode: 'COMEBACK50',
    message: 'Привет! У нас много нового в PLPilot. Вернитесь на Pro — скидка 50% на первый месяц.',
  },
  {
    name: 'day60',
    daysAfterChurn: 60,
    offerCode: 'FREE30',
    message: 'Мы скучаем! Попробуйте Pro бесплатно на 1 месяц — ваши данные на месте.',
  },
  {
    name: 'day90',
    daysAfterChurn: 90,
    offerCode: 'TRIPLE90',
    message: 'Последнее предложение: 3 месяца Pro по цене 1. Предложение действует 7 дней.',
  },
]

Deno.serve(async (req: Request) => {
  const cronSecret = Deno.env.get("CRON_SECRET")
  if (req.headers.get("Authorization") !== `Bearer ${cronSecret}`) {
    return errorResponse("Unauthorized", 401)
  }
```

New code:
```typescript
import { jsonResponse, errorResponse } from "../_shared/infra/response.ts"
import { createAdminClient } from "../_shared/auth/supabase.ts"
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"

const BOT_TOKEN = Deno.env.get("TELEGRAM_BOT_TOKEN") ?? ""
const APP_URL = Deno.env.get("APP_URL") ?? "https://plpilot.ru"

interface WinbackCampaign {
  name: string
  daysAfterChurn: number
  offerCode: string
  message: string
}

const CAMPAIGNS: WinbackCampaign[] = [
  {
    name: 'day30',
    daysAfterChurn: 30,
    offerCode: 'COMEBACK50',
    message: 'Привет! У нас много нового в PLPilot. Вернитесь на Pro — скидка 50% на первый месяц.',
  },
  {
    name: 'day60',
    daysAfterChurn: 60,
    offerCode: 'FREE30',
    message: 'Мы скучаем! Попробуйте Pro бесплатно на 1 месяц — ваши данные на месте.',
  },
  {
    name: 'day90',
    daysAfterChurn: 90,
    offerCode: 'TRIPLE90',
    message: 'Последнее предложение: 3 месяца Pro по цене 1. Предложение действует 7 дней.',
  },
]

Deno.serve(async (req: Request) => {
  // Verify cron secret (C-CR-006, D-CR-011: null check + timing-safe)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Acceptance Criteria:**
- [ ] All 3 files use `verifyCronSecret()` instead of inline auth
- [ ] `expire-subscriptions` no longer has `cronSecret` or `authHeader` variables
- [ ] `send-dunning-notification` no longer has `cronSecret` or `authHeader` variables
- [ ] `send-winback` no longer checks `req.headers.get("Authorization") !== ...` directly

---

### Task 7: Migrate Pattern A cron functions to verifyCronSecret

**Files:**
- Modify: `supabase/functions/check-reminders/index.ts` (lines 54-74)
- Modify: `supabase/functions/update-exchange-rates/index.ts` (lines 17-42)
- Modify: `supabase/functions/send-monthly-summary/index.ts` (lines 13-31)
- Modify: `supabase/functions/content-publish/index.ts` (lines 18-38)
- Modify: `supabase/functions/content-research/index.ts` (lines 10-28)

**Context:**
These five functions already have the "good" auth pattern (null check + separate status codes), but they use `===` instead of `timingSafeEqual`. Replace with standardized `verifyCronSecret()`.

**Step 1: Modify check-reminders/index.ts**

Add import at line 10 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 54-74:

Current code (lines 54-74):
```typescript
Deno.serve(async (req) => {
  // Validate Authorization header
  const authHeader = req.headers.get("Authorization")
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 })
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {

    console.error("CRON_SECRET environment variable is required but not set")
    return new Response("Server configuration error", { status: 500 })
  }

  if (token !== expectedSecret) {

    console.warn("Invalid cron token")
    return new Response("Forbidden", { status: 403 })
  }
```

New code (lines 54-58):
```typescript
Deno.serve(async (req) => {
  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 2: Modify update-exchange-rates/index.ts**

Add import at line 9 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 17-42:

Current code (lines 17-42):
```typescript
Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return corsResponse(req)
  }

  // Validate Authorization header (CRON_SECRET)
  const authHeader = req.headers.get("Authorization")
  if (!authHeader?.startsWith("Bearer ")) {
    return errorResponse("Unauthorized", 401, req)
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {

    console.error("CRON_SECRET environment variable is required but not set")
    return errorResponse("Server configuration error", 500, req)
  }

  if (token !== expectedSecret) {

    console.warn("Invalid cron token")
    return errorResponse("Forbidden", 403, req)
  }
```

New code:
```typescript
Deno.serve(async (req) => {
  // Handle CORS preflight
  if (req.method === "OPTIONS") {
    return corsResponse(req)
  }

  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 3: Modify send-monthly-summary/index.ts**

Add import at line 11 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 13-31:

Current code (lines 13-31):
```typescript
Deno.serve(async (req) => {
  // Validate Authorization header
  const authHeader = req.headers.get("Authorization")
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 })
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {
    console.error("CRON_SECRET environment variable is required but not set")
    return new Response("Server configuration error", { status: 500 })
  }

  if (token !== expectedSecret) {
    console.warn("Invalid cron token")
    return new Response("Forbidden", { status: 403 })
  }
```

New code:
```typescript
Deno.serve(async (req) => {
  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 4: Modify content-publish/index.ts**

Add import at line 10 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 18-38:

Current code (lines 18-38):
```typescript
Deno.serve(async (req) => {
  // Validate Authorization header (CRON_SECRET)
  const authHeader = req.headers.get("Authorization")
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 })
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {

    console.error("CRON_SECRET environment variable is required but not set")
    return new Response("Server configuration error", { status: 500 })
  }

  if (token !== expectedSecret) {

    console.warn("Invalid cron token")
    return new Response("Forbidden", { status: 403 })
  }
```

New code:
```typescript
Deno.serve(async (req) => {
  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Step 5: Modify content-research/index.ts**

Add import at line 8 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 10-28:

Current code (lines 10-28):
```typescript
Deno.serve(async (req) => {
  // Validate Authorization header
  const authHeader = req.headers.get("Authorization")
  if (!authHeader?.startsWith("Bearer ")) {
    return new Response("Unauthorized", { status: 401 })
  }

  const token = authHeader.slice(7)
  const expectedSecret = Deno.env.get("CRON_SECRET")

  if (!expectedSecret) {
    console.error("CRON_SECRET environment variable is required but not set")
    return new Response("Server configuration error", { status: 500 })
  }

  if (token !== expectedSecret) {
    console.warn("Invalid cron token")
    return new Response("Forbidden", { status: 403 })
  }
```

New code:
```typescript
Deno.serve(async (req) => {
  // Verify cron secret (D-CR-011: timing-safe comparison)
  const auth = await verifyCronSecret(req)
  if (!auth.ok) return auth.response
```

**Acceptance Criteria:**
- [ ] All 5 files use `verifyCronSecret()` instead of inline auth
- [ ] No `token !== expectedSecret` pattern remains in any of these files
- [ ] All files import `verifyCronSecret` from `"../_shared/infra/cron-auth.ts"`

---

### Task 8: Migrate Pattern C functions (remove service_role_key acceptance)

**Files:**
- Modify: `supabase/functions/content-factory/index.ts` (lines 75-91)
- Modify: `supabase/functions/blog-expander/index.ts` (lines 52-67)

**Context:**
These two functions accept both CRON_SECRET and service_role_key for auth (D-SEC-012). The service_role_key acceptance is a security widening: if it leaks, an attacker can trigger AI content generation. Replace with verifyCronSecret() which only accepts CRON_SECRET.

**Step 1: Modify content-factory/index.ts**

Add import at line 20 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 75-91:

Current code (lines 75-91):
```typescript
Deno.serve(async (req) => {
  try {
    // 1. Auth: accept both CRON_SECRET and service_role JWT
    const authHeader = req.headers.get("Authorization") ?? ""
    const cronSecret = Deno.env.get("CRON_SECRET")
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")

    const token = authHeader.replace("Bearer ", "")
    const isAuthorized = token === cronSecret || token === serviceKey

    if (!isAuthorized) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      })
    }
```

New code:
```typescript
Deno.serve(async (req) => {
  try {
    // 1. Auth: CRON_SECRET only (D-SEC-012: removed service_role_key acceptance)
    const auth = await verifyCronSecret(req)
    if (!auth.ok) return auth.response
```

**Step 2: Modify blog-expander/index.ts**

Add import at line 17 (after existing imports):
```typescript
import { verifyCronSecret } from "../_shared/infra/cron-auth.ts"
```

Replace lines 52-67:

Current code (lines 52-67):
```typescript
Deno.serve(async (req) => {
  try {
    // 1. Auth: CRON_SECRET or service_role
    const authHeader = req.headers.get("Authorization") ?? ""
    const cronSecret = Deno.env.get("CRON_SECRET")
    const serviceKey = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")

    const token = authHeader.replace("Bearer ", "")
    const isAuthorized = token === cronSecret || token === serviceKey

    if (!isAuthorized) {
      return new Response(JSON.stringify({ error: "Unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      })
    }
```

New code:
```typescript
Deno.serve(async (req) => {
  try {
    // 1. Auth: CRON_SECRET only (D-SEC-012: removed service_role_key acceptance)
    const auth = await verifyCronSecret(req)
    if (!auth.ok) return auth.response
```

**Acceptance Criteria:**
- [ ] `content-factory/index.ts` does not reference `serviceKey` or `service_role`
- [ ] `blog-expander/index.ts` does not reference `serviceKey` or `service_role`
- [ ] `grep "token === serviceKey" supabase/functions/` = 0 results
- [ ] Both use `verifyCronSecret()` for auth

---

### Task 9: Update check-reminders-test.ts

**Files:**
- Modify: `supabase/functions/tests/check-reminders-test.ts` (lines 78-138)

**Context:**
The existing test file has a `validateCronAuth` helper function that mirrors the old inline auth pattern. Update to verify that check-reminders now uses `verifyCronSecret` from the shared utility.

**Step 1: Replace the auth test section**

Replace lines 78-138:

Current code (lines 78-138):
```typescript
// --- Auth token validation logic (mirrors check-reminders/index.ts:56-74) ---

function validateCronAuth(
  authHeader: string | null,
  expectedSecret: string | null,
): number {
  if (!authHeader?.startsWith("Bearer ")) {
    return 401
  }
  const token = authHeader.slice(7)
  if (!expectedSecret) {
    return 500
  }
  if (token !== expectedSecret) {
    return 403
  }
  return 200
}

Deno.test("cron auth — correct CRON_SECRET token returns 200", () => {
  const secret = "my-cron-secret-value"
  const result = validateCronAuth(`Bearer ${secret}`, secret)
  assertEquals(result, 200)
})

Deno.test("cron auth — wrong token (service_role_key mismatch) returns 403", () => {
  const cronSecret = "cron-secret-value"
  const serviceRoleKey = "service-role-key-different-value"
  const result = validateCronAuth(`Bearer ${serviceRoleKey}`, cronSecret)
  assertEquals(result, 403)
})

Deno.test("cron auth — missing Authorization header returns 401", () => {
  const result = validateCronAuth(null, "some-secret")
  assertEquals(result, 401)
})

Deno.test("cron auth — empty Authorization header returns 401", () => {
  const result = validateCronAuth("", "some-secret")
  assertEquals(result, 401)
})

Deno.test("cron auth — non-Bearer scheme returns 401", () => {
  const result = validateCronAuth("Basic abc123", "some-secret")
  assertEquals(result, 401)
})

Deno.test("cron auth — missing CRON_SECRET env var returns 500", () => {
  const result = validateCronAuth("Bearer some-token", null)
  assertEquals(result, 500)
})

Deno.test("cron auth — empty CRON_SECRET env var returns 500", () => {
  const result = validateCronAuth("Bearer some-token", "")
  assertEquals(result, 500)
})

Deno.test("cron auth — token with extra spaces is rejected (exact match)", () => {
  const secret = "my-secret"
  const result = validateCronAuth(`Bearer ${secret} `, secret)
  assertEquals(result, 403)
})
```

New code:
```typescript
// --- Auth: check-reminders uses shared verifyCronSecret (BUG-182) ---

Deno.test("check-reminders — uses verifyCronSecret from shared utility", async () => {
  const source = await Deno.readTextFile(
    new URL("../check-reminders/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes("verifyCronSecret"),
    true,
    "check-reminders must use verifyCronSecret() from cron-auth.ts",
  )
})

Deno.test("check-reminders — imports cron-auth.ts", async () => {
  const source = await Deno.readTextFile(
    new URL("../check-reminders/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes('from "../_shared/infra/cron-auth.ts"'),
    true,
    "Must import from _shared/infra/cron-auth.ts",
  )
})

Deno.test("check-reminders — no inline CRON_SECRET comparison", async () => {
  const source = await Deno.readTextFile(
    new URL("../check-reminders/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes("token !== expectedSecret"),
    false,
    "Must NOT have inline token comparison (use verifyCronSecret)",
  )
})

Deno.test("check-reminders — no direct Deno.env.get CRON_SECRET", async () => {
  const source = await Deno.readTextFile(
    new URL("../check-reminders/index.ts", import.meta.url),
  )
  assertEquals(
    source.includes('Deno.env.get("CRON_SECRET")'),
    false,
    "Must NOT directly read CRON_SECRET (verifyCronSecret handles it)",
  )
})
```

**Acceptance Criteria:**
- [ ] All check-reminders tests pass: `deno test --allow-all supabase/functions/tests/check-reminders-test.ts`
- [ ] Old `validateCronAuth` helper function is removed
- [ ] New tests verify check-reminders uses verifyCronSecret

---

### Execution Order

```
Task 1 (migration) ─────────────────────────────────┐
Task 2 (cron-auth.ts + tests) ──────────────────────┤
Task 3 (rate-limit.ts fail-closed + tests) ─────────┤ All independent
                                                     ↓
Task 4 (renew-subscription) ─── depends on Tasks 1, 2
Task 5 (verify-telegram-webapp + commands.ts) ─── depends on Task 1
Task 6 (Pattern B: expire/dunning/winback) ─── depends on Task 2
Task 7 (Pattern A: reminders/rates/summary/publish/research) ─── depends on Task 2
Task 8 (Pattern C: factory/expander) ─── depends on Task 2
Task 9 (check-reminders tests) ─── depends on Task 7
```

Tasks 1, 2, 3 can run in parallel.
Tasks 4-8 can run in parallel after Tasks 1 and 2 are done.
Task 9 depends on Task 7.

### Dependencies

- Tasks 4, 5 depend on Task 1 (need `cron_invocations` table to exist)
- Tasks 4, 6, 7, 8 depend on Task 2 (need `verifyCronSecret` function to exist)
- Task 3 is independent (only changes existing rate-limit.ts)
- Task 9 depends on Task 7 (tests verify check-reminders was updated)

### Verification Commands

After all tasks complete:

```bash
# Verify no in-memory rate limits remain
grep -rn "let lastInvocationTime\|const rateLimitMap\|const linkAttempts" supabase/functions/

# Verify no service_role_key acceptance
grep -rn "token === serviceKey" supabase/functions/

# Verify all 13 cron functions use verifyCronSecret
for f in check-reminders update-exchange-rates send-monthly-summary content-publish content-research renew-subscription expire-subscriptions send-dunning-notification send-winback content-factory blog-expander; do
  echo "--- $f ---"
  grep -c "verifyCronSecret" "supabase/functions/$f/index.ts"
done

# Note: content-research has no subfolder named for grep — adjust path
# Also verify commands.ts does NOT use verifyCronSecret (it's not a cron function)

# Run all tests
deno test --allow-all supabase/functions/tests/
```

## Definition of Done

- [ ] All 8 findings in group fixed (C-CR-008, C-CR-009, D-CR-002, D-QA-003, D-SEC-006, C-CR-006, D-CR-011, D-SEC-012)
- [ ] New `verifyCronSecret` utility created and all 13 cron functions migrated to use it
- [ ] All in-memory rate limiting removed from renew-subscription, verify-telegram-webapp, and commands.ts
- [ ] DB-backed rate limiting implemented for verify-telegram-webapp and /link command
- [ ] rate-limit.ts changed from fail-open to fail-closed
- [ ] content-factory and blog-expander no longer accept service_role_key as auth
- [ ] Migration added for cron_invocations table (migration number verified unique)
- [ ] Minimum 10 test cases passing (see Tests section)
- [ ] Existing tests updated (renew-subscription-test.ts, rate-limit-test.ts, check-reminders-test.ts)
- [ ] `grep "let lastInvocationTime\|const rateLimitMap\|const linkAttempts" supabase/functions/` = 0 results
- [ ] `grep "token === serviceKey" supabase/functions/` = 0 results
- [ ] No new test failures in `deno test --allow-all supabase/functions/tests/`
