# Bug Fix: [BUG-326] Error Handling & Observability — content pipeline

**Status:** done | **Priority:** P0 | **Date:** 2026-04-19

## Symptom

Admin `/stats` in Telegram bot shows `error='unknown'` for every failed `content_items` row, with `draft='{}'`, `rubric='unknown'`. Zero diagnostic info for failures that have persisted for 2+ days after FTR-321 deploy. Operator cannot distinguish 429 rate-limit, 404 deprecated model, network timeout, or LLM empty response.

Source: bughunt `ai/bughunt/2026-04-19-report.md` Zone A (18 findings, 5 critical). Inbox: `ai/inbox/20260419-102408-bughunt-1.md`.

## Root Cause

Three-layer error-handling bug + dead fallback code + wrong column writes, interacting with FTR-321 free-tier models:

1. **DOMException serialization.** `AbortSignal.timeout()` throws `DOMException` with no enumerable own properties. `JSON.stringify(DOMException) = '{}'`. Catch block uses this as the error message → `draft='{}'` persisted.
2. **Wrong column.** `content-factory` catch block writes the message to `draft` column; the `error` column exists (used correctly by `content-factory-finalize`) but remains `NULL`.
3. **Hardcoded rubric.** `rubric: 'unknown'` is a string literal — even when `pickRubric()` returned a valid slug before the failure, real rubric is discarded.
4. **Dead fallback.** `callLLMWithFallback` only catches `DOMException{name:'TimeoutError'}` + 5xx. 429 (free-tier rate limit, common after FTR-321), 404 (deprecated model), and `Error{name:'AbortError'}` (alternative Deno abort shape) all bypass fallback. `AI_DETECT_FALLBACK` constant defined in `models.ts` but call-site uses plain `callLLM` → dead code.
5. **`callLLM` swallows empty response.** 200 OK with empty `choices[]` (filtered / over quota) returns `""`. Phase 1 revision replaces valid article with empty string.
6. **Finalize retry loses error.** After 3 retries, `error='finalize_retries_exceeded'` overwrites the per-attempt failure reason (e.g., the actual 429).
7. **`/force` admin command always returns success** even when pipeline fails — admin gets false confirmation.

## Reproduction Steps

1. `POST /content-factory` manually; simulate AI_DETECT returning HTTP 429 (`OpenRouter 429: Rate limit exceeded`).
2. Pipeline fails; catch block writes record to `content_items`.
3. Query: `select error, draft, rubric from content.content_items where status='failed' order by created_at desc limit 1`.
4. **Expected:** `error='OpenRouter 429: Rate limit exceeded'`, `draft=NULL`, `rubric='sub_week'` (or whatever was picked).
5. **Got:** `error=NULL`, `draft='{}'`, `rubric='unknown'`.

## Fix Approach

Seven findings, one spec — all touch error handling / fallback surface. Group them:

### Findings mapped to fixes

| ID | Severity | File | Fix |
|----|----------|------|-----|
| F-001 (A-ROOT-001) | CRITICAL | `content-factory/index.ts` catch block | Serialize error via `Object.getOwnPropertyNames` / `name+message`; write to `error` column; preserve rubric slug |
| F-002 (A-ROOT-002) | CRITICAL | `_shared/ai/llm-client.ts` + finalize call-site | Extend fallback match to 4xx/AbortError; switch AI_DETECT to `callLLMWithFallback` |
| F-003 (A-CR-002) | HIGH | `_shared/ai/llm-client.ts:42` | Throw on empty choices instead of returning `""` |
| F-004 (A-CR-003) | HIGH | `content-factory-finalize/index.ts` catch | Write `error` column on every failed retry, not just final |
| F-005 (A-UX-001) | HIGH | `content-bot-webhook/handlers/commands.ts` `/force` | Parse response JSON; reply with real error if `status='failed'` |
| F-006 (A-UX-002) | MEDIUM | `content-factory/index.ts` | Log structured error to `console.error` before DB insert (last-resort audit trail) |
| F-007 (A-QA-001) | MEDIUM | `content-factory/index.ts` rubric override path | Validate+trim; return 400 on invalid override |

### Implementation sketch

```typescript
// _shared/ai/llm-client.ts — fix F-003 (empty choices)
if (data.error) throw new Error(`OpenRouter error: ${JSON.stringify(data.error)}`)
const content = data.choices?.[0]?.message?.content
if (!content) throw new Error(`OpenRouter empty content (model: ${options.model})`)
return content

// _shared/ai/llm-client.ts — fix F-002 (fallback conditions)
const isTimeout = err instanceof DOMException && err.name === "TimeoutError"
const isAbort = err instanceof Error && err.name === "AbortError"
const is5xx = err instanceof Error && /^OpenRouter 5\d\d:/.test(err.message)
const is4xx = err instanceof Error && /^OpenRouter (429|404):/.test(err.message)
if (!isTimeout && !isAbort && !is5xx && !is4xx) throw err
// ... fallback call

// content-factory/index.ts — fix F-001 (catch block)
} catch (err: unknown) {
  const message = err instanceof Error || err instanceof DOMException
    ? `${(err as Error).name}: ${(err as Error).message}`
    : (typeof err === "object" && err !== null
        ? JSON.stringify(err, Object.getOwnPropertyNames(err))
        : String(err))

  console.error("[factory] Error:", message, { rubric: rubric?.slug })  // F-006

  const capturedRubricSlug = rubric?.slug ?? "__error__"
  await supabase.schema("content").from("content_items").insert({
    rubric: capturedRubricSlug,
    status: "failed",
    error: message,      // F-001: error column, not draft
    draft: null,
  })
  return jsonResponse({ status: "failed", error: message }, 200)  // F-005 unblocker
}

// content-factory-finalize/index.ts — fix F-004 (preserve per-attempt error)
// In the retry-increment UPDATE, add:
catchUpdate.error = message  // overwrite "finalize_retries_exceeded" on final too

// content-factory/index.ts — fix F-007 (rubric override validation)
let rubricOverride: string | null = null
if (req.method === "POST") {
  try {
    const body = await req.json() as { rubric_override?: string }
    rubricOverride = body.rubric_override?.trim() || null
    if (body.rubric_override !== undefined && !rubricOverride) {
      return jsonResponse({ error: "rubric_override must be non-empty" }, 400)
    }
  } catch (err) {
    console.warn("[factory] Invalid JSON body:", err)
    return jsonResponse({ error: "Invalid JSON body" }, 400)
  }
}

// content-bot-webhook/handlers/commands.ts — fix F-005 (/force)
const result = await response.json() as { status?: string; error?: string }
if (result.status === "failed") {
  await ctx.reply(`Pipeline failed: ${result.error ?? "no error info"}`)
  return
}
await ctx.reply(`Pipeline запущен. Status: ${result.status}`)
```

## Impact Tree Analysis

### Step 1: UP — who uses?
- [x] `content-bot-webhook/handlers/commands.ts` — calls `/force` (F-005 touches this)
- [x] `content-bot-webhook/handlers/commands.ts /stats` — reads `error` column (benefits from fix, no code change needed)
- [x] All cron-triggered pipelines: `content-research`, `content-factory`, `content-factory-finalize`, `content-publish` use `callLLM*` — changed error shape may propagate

### Step 2: DOWN — what depends on?
- [x] `_shared/ai/llm-client.ts` → `callLLM`, `callLLMWithFallback` (both modified)
- [x] `_shared/ai/models.ts` → `MODELS.AI_DETECT`, `MODELS.AI_DETECT_FALLBACK` (used, no change)
- [x] PostgreSQL `content.content_items` schema — `error` column exists (migration 00051); no schema change needed

### Step 3: BY TERM — grep entire project

| File | Reason | Action |
|------|--------|--------|
| `supabase/functions/content-factory/index.ts:88,128,207,271-281,284` | Primary — catch block, rubric, rubric_override | Modify |
| `supabase/functions/content-factory-finalize/index.ts:124,329` | AI_DETECT call-site + catch block | Modify |
| `supabase/functions/_shared/ai/llm-client.ts:37,42,56` | Empty choices + fallback conditions | Modify |
| `supabase/functions/content-bot-webhook/handlers/commands.ts` (`/force` handler) | Propagate real error to admin | Modify |
| `supabase/functions/tests/` | Regression tests | New test file |

### Step 4: Checklist

- [x] Regression tests for DOMException serialization, 429/404 fallback, empty-choices throw, `/force` error response
- [x] Migration: NONE needed (error column already exists per migration 00051)
- [x] Edge Function touchpoints listed above

### Step 5: Dual system

- Error state is written to one column (`error`) and read by bot `/stats` — single path, no dual system.

## Research Sources

No external research needed — root causes identified in bughunt report section 2-3.

Deno / Supabase runtime specifics for `AbortSignal.timeout()`:
- https://docs.deno.com/api/web/~/AbortSignal.timeout (`TimeoutError` DOMException)
- https://supabase.com/docs/guides/functions/debugging (Edge Function logs)

## Allowed Files

1. `supabase/functions/content-factory/index.ts` — catch block, rubric_override validation
2. `supabase/functions/content-factory-finalize/index.ts` — AI_DETECT fallback call, catch-block `error` column write
3. `supabase/functions/_shared/ai/llm-client.ts` — empty-choices throw, fallback match conditions
4. `supabase/functions/content-bot-webhook/handlers/commands.ts` — `/force` real error propagation
5. `supabase/functions/tests/content-factory-error-handling-test.ts` — NEW: regression tests (DOMException serialization, 4xx fallback, empty choices, column writes)
6. `supabase/functions/tests/content-finalize-fallback-test.ts` — NEW: regression tests for AI_DETECT fallback path
7. `.claude/rules/domains/content.md` — update Change History with BUG-326

## Tests

Minimum test cases (regression protection):

### Unit tests — `tests/content-factory-error-handling-test.ts`

- **T1** — DOMException serialization: `new DOMException("aborted", "TimeoutError")` → message `TimeoutError: aborted` (not `{}`)
- **T2** — Generic Error serialization: preserves `name: message` shape
- **T3** — Plain object with stack: uses `Object.getOwnPropertyNames` to include stack
- **T4** — `rubric_override` validation: empty string + whitespace-only → HTTP 400
- **T5** — `rubric_override` validation: malformed JSON body → HTTP 400 (not 500)
- **T6** — Catch block writes `error` column (not `draft`); `draft` is `NULL`; rubric preserved

### Unit tests — `tests/content-finalize-fallback-test.ts`

- **T7** — `callLLMWithFallback` catches `OpenRouter 429:` error and retries with fallback model
- **T8** — `callLLMWithFallback` catches `OpenRouter 404:` error and retries with fallback
- **T9** — `callLLMWithFallback` catches `Error{name:'AbortError'}` and retries with fallback
- **T10** — `callLLMWithFallback` does NOT catch generic `Error("network down")` (bubbles up)
- **T11** — `callLLM` throws `OpenRouter empty content (model: X)` on empty `choices` array (not `""`)
- **T12** — `callLLM` throws on explicit `data.error` response

### Integration test — `/force` flow

- **T13** — Mock `content-factory` returning `{ status: "failed", error: "..." }`; `/force` handler replies with failure message (not false success)

## Definition of Done

- [x] DOMException / AbortError serializable via `name + message` path
- [x] `content-factory` catch writes to `error` column with real message; `draft` is `NULL`; rubric slug preserved
- [x] `callLLMWithFallback` catches 429, 404, AbortError, 5xx, TimeoutError
- [x] Phase 2 AI_DETECT uses `callLLMWithFallback` with `AI_DETECT_FALLBACK`
- [x] `callLLM` throws on empty choices (no silent `""` return)
- [x] Finalize catch writes `error` column on every failure (not only final)
- [x] `/force` admin command propagates real error message
- [x] `console.error` fallback logs before DB insert (last-resort audit trail)
- [x] `rubric_override` validated + 400 on invalid
- [x] All regression tests pass (T1-T13)
- [ ] After deploy: admin `/stats` shows real error messages within 24h (post-deploy verification)
- [x] `.claude/rules/domains/content.md` Change History updated

## Related

- FTR-321 (2026-04-05) — introduced free-tier models + AI_DETECT surface that exposed this bug
- BUG-322 — wall-clock graceful degradation (prior fix in same file, does not address catch-block error column)
- BUG-327 (this wave) — pipeline stability, depends on this spec deploying first to see real errors
