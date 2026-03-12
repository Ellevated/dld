# Bug Hunt Report: PLPilot Feature Modules TypeScript Audit

**ID:** BUG-106 (report only, not in backlog)
**Date:** 2026-02-16
**Mode:** Bug Hunt (multi-agent)
**Target:** /Users/desperado/dev/plpilot/src/features/

## Original Problem
<user_input>
Bug hunt plpilot src/features/ — find all bugs in TypeScript feature modules (payments, billing, calendar, dashboard, cards, tags, auth, settings, profile, onboarding, errors, receipts, reports)
</user_input>

## Executive Summary
- Zones analyzed: 4 (A, B, C, D)
- Total findings: 465
- By severity: **Critical: 56**, **High: 115**, Medium: 159, Low: 135
- By persona: code-reviewer (66), junior-developer (93), qa-engineer (117), security-auditor (48), software-architect (69), ux-analyst (72)
- **Relevant (in scope): 50** (kept after validation)
- **Out of scope: 26** (moved to ideas.md)
- **Duplicates merged: 87** (removed via deduplication)
- **Groups formed: 8** (P0: 3, P1: 4, P2: 1)
- **Specs created: 8** (BUG-107 through BUG-114)

## Grouped Specs

| # | Spec ID | Group Name | Findings | Priority | Status |
|---|---------|-----------|----------|----------|--------|
| 1 | BUG-107 | Payment & Billing Financial Safety | F-001, F-002, F-003, F-004, F-005, F-006, F-007 | P0 | queued |
| 2 | BUG-108 | Subscription Upgrade Flow | F-008, F-009, F-010, F-011, F-012, F-013 | P0 | queued |
| 3 | BUG-112 | Authorization & Access Control | F-034, F-035, F-036, F-037, F-038 | P0 | queued |
| 4 | BUG-109 | React Hook & State Management Races | F-014, F-015, F-016, F-017, F-018, F-019, F-020 | P1 | queued |
| 5 | BUG-110 | Date/Time Calculation Bugs | F-021, F-022, F-023, F-024, F-025, F-026, F-027 | P1 | queued |
| 6 | BUG-111 | Financial Calculation & Currency Bugs | F-028, F-029, F-030, F-031, F-032, F-033 | P1 | queued |
| 7 | BUG-113 | Error Handling & UX Dead Ends | F-039, F-040, F-041, F-042, F-043, F-044, F-045, F-046 | P2 | queued |
| 8 | BUG-114 | AI Feature Safety & Rate Limiting | F-047, F-048, F-049, F-050 | P2 | queued |

## All Findings

### Zone A - Payment Creation, Receipt Scanning & Cooling-off

#### A-CR-001: Race condition: form reset during async operations
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/payments/hooks/use-payment-form.ts:59
- **Description:** The useEffect at line 59 resets form state based on `currentRow`, `scanData`, and `open`. When the dialog opens with scanData, it triggers an async card lookup (line 75). If the user closes/reopens the dialog quickly, or if `cards` data updates, the form resets mid-operation, potentially overwriting user edits or causing state inconsistency.
- **Evidence:**
  ```typescript
  useEffect(() => {
    if (currentRow && open) {
      form.reset({ ... })
    } else if (scanData && open) {
      const matchedCard = cards?.find(...)
      form.reset({ ... })
    } else if (!currentRow && !scanData && open) {
      form.reset({ ... })
    }
  }, [currentRow, scanData, open, form, cards])
  ```
- **Fix suggestion:** Use refs to track initialization state. Reset only on first open, not on every `cards` update. Alternative: move card matching outside effect, compute derived state with useMemo instead of side-effect reset.

#### A-CR-002: Receipt upload silently fails after payment creation
- **Severity:** critical
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/payments/hooks/use-payment-form.ts:131
- **Description:** `uploadReceiptImage` (line 131) is called AFTER payment creation succeeds (line 172). If upload fails, it shows a toast warning, but: 1) The dialog closes immediately (line 176) 2) User cannot retry upload without creating duplicate payment 3) Receipt row insertion error at line 148 shows toast but does NOT throw — mutation completes successfully despite data corruption.
- **Evidence:**
  ```typescript
  const { error: insertError } = await supabase.from('receipts').insert({...})
  if (insertError) {
    toast.warning('Чек загружен, но не привязан к платежу.')
    // BUG: Does NOT throw — mutation returns success
  }
  ```
- **Fix suggestion:** 1) Use RPC that creates payment + receipt atomically (transaction) 2) OR: Keep dialog open on receipt error, show retry button 3) OR: Throw error and rollback payment creation (compensating transaction)

#### A-CR-003: waitForElement rejection not handled — widget init fails silently
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/billing/hooks/use-yookassa-widget.ts:102
- **Description:** `waitForElement` can reject after 20 frames if DOM element not found (line 40). The rejection is caught at line 109, but only logs generic "Failed to initialize". Root cause (element missing) is lost.
- **Evidence:**
  ```typescript
  await waitForElement(containerId)
  if (cancelled) { widget.destroy(); return }
  await widget.render(containerId)
  } catch (err) {
    if (!cancelled) {
      setError(err instanceof Error ? err.message : 'Failed to initialize payment widget')
    }
  }
  ```
- **Fix suggestion:** Add specific error message for waitForElement timeout: "Payment form container not found. Please refresh page." Log full error to console for debugging.

#### A-CR-004: Subscription polling race: auto-close before backend confirms payment
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/billing/components/upgrade-dialog.tsx:76
- **Description:** Payment success flow: 1) YooKassa widget fires 'success' event (line 86) 2) Component starts polling subscription every 2s (line 84) 3) Auto-closes when subscription.plan !== 'free' (line 106). Race condition: YooKassa 'success' fires when user completes 3DS, NOT when backend confirms. Backend webhook processes payment asynchronously (network delay, queue). Polling may check subscription BEFORE webhook updates it. If first poll sees plan='free', timeout continues for 30s. If webhook is delayed >30s, polling stops, user stuck at "Обновляем...".
- **Evidence:**
  ```typescript
  // Stop after 30s
  const timeout = setTimeout(() => {
    clearInterval(interval)
    pollingRef.current = null
  }, 30_000)
  ```
- **Fix suggestion:** 1) Increase timeout to 90s (webhook SLA) 2) Add exponential backoff (2s → 4s → 8s) 3) Show "Payment processing may take up to 2 minutes" message 4) OR: Use Supabase realtime subscription updates instead of polling

#### A-CR-005: Polling interval not cleared on unmount
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/billing/components/upgrade-dialog.tsx:92
- **Description:** Polling interval is stored in `pollingRef` but cleanup only happens in: 1) useEffect return (line 97) — only when paymentResult changes 2) Auto-close effect (line 109) — only when subscription becomes Pro. Missing cleanup: If user closes dialog manually while polling is active, dialog unmounts but interval keeps firing, queries invalidated every 2s in background. Memory leak: interval never cleared.
- **Evidence:**
  ```typescript
  return () => {
    clearInterval(interval)
    clearTimeout(timeout)
    pollingRef.current = null
  }
  }, [paymentResult, queryClient])
  ```
- **Fix suggestion:** Add cleanup in dialog onOpenChange: `if (!open && pollingRef.current) clearInterval(pollingRef.current)`. Or: use useEffect with `open` dependency to stop polling when dialog closes.

#### A-CR-006: Cooling-off nudge fetch races with dialog state — stale data shown
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/payments/components/cooling-off-dialog.tsx:58
- **Description:** Effect at line 58 fetches AI nudge when dialog opens. It uses `fetchedRef` to prevent duplicate fetches, but ref is NEVER reset. Race conditions: 1) User opens dialog for Payment A → fetch starts 2) User closes dialog before fetch completes 3) User opens dialog for Payment B → fetch skipped (fetchedRef=true) 4) Payment A's nudge displays for Payment B.
- **Evidence:**
  ```typescript
  const fetchedRef = useRef(false)
  useEffect(() => {
    if (!open || nudge || fetchedRef.current) return
    fetchedRef.current = true
    // BUG: Never reset when dialog closes
  }, [open, nudge, paymentData, supabase.functions])
  ```
- **Fix suggestion:** Reset `fetchedRef.current = false` when dialog closes. Add cleanup: `if (!open) { fetchedRef.current = false }` OR move fetch into onOpenChange callback.

#### A-CR-007: Optimistic update missing — stale data flashes after create/update
- **Severity:** critical
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/hooks/api/use-payments.ts:106
- **Description:** Payment mutations invalidate queries on success (line 106-113), but do NOT use optimistic updates. Between mutation success and query refetch, UI shows stale data. Race condition with rapid actions: 1) User creates payment → invalidation fires 2) Query refetch starts (network latency 200-500ms) 3) User immediately edits the new payment 4) Edit mutation completes before create refetch 5) Edit invalidation fires, refetch starts 6) Create refetch completes, showing pre-edit state 7) Edit refetch completes, correcting state 8) User sees payment revert then correct itself (flicker).
- **Evidence:**
  ```typescript
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: queryKeys.payments.all })
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
    // No optimistic update — UI stale until refetch completes
  }
  ```
- **Fix suggestion:** Use `queryClient.setQueryData` for optimistic update, or enable `refetchOnWindowFocus: false` + aggressive `staleTime` to reduce flicker.

#### A-CR-008: Type safety bypassed — tables not in generated types
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/hooks/api/use-subscription.ts:22
- **Description:** Lines 20-22 cast `supabase` to `any` to access `user_subscriptions` and `billing_history` tables, which are "pending gen:types" (migration 00022). This disables all type checking for: column names, column types, query structure.
- **Evidence:**
  ```typescript
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type UntypedClient = { from: (table: string) => any }
  const supabase = useSupabaseClient() as unknown as UntypedClient
  ```
- **Fix suggestion:** Run `supabase gen types typescript` to generate Database types. If tables are new, manually define types: `type UserSubscription = { id: string; plan: PlanType; ... }`.

#### A-CR-009: Refund eligibility calculation has off-by-one error on day 7
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/hooks/api/use-subscription.ts:236
- **Description:** Line 236 checks `daysSince <= 7`, but calculation uses exact milliseconds. Edge case: Payment created 2026-02-16 10:00:00, check time 2026-02-23 10:00:01 (7 days + 1 second), `daysSince = 7.000011574` → INELIGIBLE. User sees "Refund 7 days" guarantee but gets rejected on exact day 7 boundary. Legal issue: false advertising if ToS says "7 days" but code enforces <7 days.
- **Evidence:**
  ```typescript
  const daysSince = (Date.now() - new Date(succeeded[0].created_at).getTime()) / (1000 * 60 * 60 * 24)
  return daysSince <= 7
  ```
- **Fix suggestion:** Use `daysSince < 7` for strict "<7 days", OR `Math.floor(daysSince) <= 7` for "up to 7 days inclusive". Better: check on backend using server time, not client-side calculation.

#### A-CR-010: Rate limit error handling too generic — user sees wrong guidance
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/receipts/components/receipt-scan-dialog.tsx:120
- **Description:** Line 120 checks for "Rate limit" or "429" in error message, but backend may return different formats. If rate limit error has different wording, fallback message is shown: "Не удалось распознать чек. Попробуйте другое фото" → User uploads better photo, but problem is rate limit, not photo quality.
- **Evidence:**
  ```typescript
  if (message.includes('Rate limit') || message.includes('429')) {
    toast.error('Слишком много запросов. Подождите немного')
  } else {
    toast.error('Не удалось распознать чек. Попробуйте другое фото')
  }
  ```
- **Fix suggestion:** Check response status code, not message text. Backend should return structured error: `{ code: 'RATE_LIMIT', retryAfter: 60 }`. Parse and show: "Try again in 60s".

#### A-CR-011: Object URL not revoked when file changes during preview
- **Severity:** low
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/receipts/components/receipt-scan-dialog.tsx:49
- **Description:** `setPreviewUrl` callback at line 49 revokes old URL only when setting new URL. If user selects file A, then closes dialog, `previewUrl` stays in state. Dialog reopens → `reset()` at line 45 revokes URL. BUT: if `reset` is called without `previewUrl` being set (e.g., user closes dialog before file selection completes), old URL leaks. Minor memory leak: 5MB image × 10 selections = 50MB until page refresh.
- **Evidence:**
  ```typescript
  const reset = useCallback(() => {
    setPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev)
      return null
    })
  }, [])
  ```
- **Fix suggestion:** Use ref to track URL and revoke in cleanup. OR: revoke in useEffect cleanup when component unmounts.

#### A-CR-012: Date validation race — edit fails when end_date equals next_payment_date
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/payments/data/schema.ts:44
- **Description:** Schema validation at line 44 requires `end_date > next_payment_date`. Edge case: user sets both to same day (e.g., last payment date). Business logic gap: if subscription ends on next payment date, it's valid (final charge then cancel). Schema blocks this with strict `>` comparison.
- **Evidence:**
  ```typescript
  .refine(
    (data) => {
      if (data.end_date && data.next_payment_date) {
        return data.end_date > data.next_payment_date
      }
      return true
    },
    {
      message: 'Дата окончания должна быть позже даты следующего платежа',
      path: ['end_date'],
    }
  )
  ```
- **Fix suggestion:** Change to `>=` if "end on payment date" is valid business case. OR: clarify message: "End date must be after next payment, or leave blank to cancel after this charge."

#### A-CR-013: Payment token reused on retry — double charge risk
- **Severity:** critical
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/billing/components/upgrade-dialog.tsx:64
- **Description:** `confirmationToken` is set once on successful checkout (line 66) and never cleared except when user clicks "Try again" after widget error (line 232) or closes dialog (line 71). Race condition: 1) User clicks "Оплатить" → token created 2) Widget loads, user enters card 3) Network error during payment submission 4) Widget shows error, user clicks browser back/forward 5) Dialog remounts with stale `confirmationToken` 6) Widget re-renders with same token 7) User completes payment → SUCCEEDS 8) User clicks "Try again" thinking first failed 9) New token created → user charged TWICE. YooKassa tokens are single-use, but if first payment succeeds after user thinks it failed, second attempt with new token creates duplicate charge.
- **Evidence:**
  ```typescript
  const handleProceed = async () => {
    const result = await createCheckout(selectedPlan)
    if (result) {
      setConfirmationToken(result.confirmationToken)
    }
  }
  ```
- **Fix suggestion:** Clear `confirmationToken` on any widget error. Track payment status on backend, prevent duplicate charges with idempotency key. Show pending state if first payment is processing.

#### A-CR-014: Discount acceptance has no backend call — silent no-op
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/settings/billing/cancel-dialog.tsx:76
- **Description:** `handleAcceptDiscount` at line 76 shows toast "Скидка 25% будет применена" but makes NO API call. Discount is never actually applied. User flow: 1) User clicks "Отменить подписку" 2) Reason: "Дорого" 3) Offer: "Скидка 25%" 4) User clicks "Принять скидку" 5) Toast shows success → dialog closes 6) Next billing cycle: FULL PRICE charged 7) User complains: "I accepted the discount!". This is either unfinished feature or intentional dark pattern.
- **Evidence:**
  ```typescript
  const handleAcceptDiscount = async () => {
    toast.info('Скидка 25% будет применена в следующем периоде')
    setOpen(false)
    resetDialog()
  }
  ```
- **Fix suggestion:** Call backend to apply discount. If not implemented, remove fake offer or show "Coming soon" message instead of confirming action that won't happen.

#### A-CR-015: Refund amount not validated — wrong currency displayed
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/settings/billing/refund-dialog.tsx:28
- **Description:** Line 29 shows refund confirmation: `Возврат ${result.amount} ₽ оформлен`. Hardcodes ₽ symbol, but subscription may be in USD/EUR (line 211 of use-subscription). Edge case: User subscribed in USD region, backend returns `{ amount: "4.99", currency: "USD" }`, UI shows "Возврат 4.99 ₽ оформлен" → displays wrong currency.
- **Evidence:**
  ```typescript
  toast.success(`Возврат ${result.amount} ₽ оформлен`, {
    description: 'Деньги вернутся на карту в течение 5-7 дней',
  })
  ```
- **Fix suggestion:** Use `result.currency` to show correct symbol: `${CURRENCY_SYMBOLS[result.currency]} ${result.amount}`.

#### A-CR-016: Script tag not removed on load failure — duplicate scripts injected
- **Severity:** medium
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/billing/lib/load-yookassa-sdk.ts:36
- **Description:** On script load error (line 40), `loadPromise` is reset to null (line 41), but the failed `<script>` tag remains in DOM. If user retries: 1) `loadYooKassaSdk()` called again 2) Checks `loadPromise === null` (true after error) → creates new script 3) New script appended to `<head>` 4) Both scripts in DOM (one failed, one loading) 5) If second succeeds, SDK loads, but DOM has 2 script tags. Not severe leak, but clutters DOM and can cause issues if SDK has init guards.
- **Evidence:**
  ```typescript
  script.onerror = () => {
    loadPromise = null
    reject(new Error('Failed to load YooKassa SDK'))
  }
  // Script tag NOT removed from DOM
  ```
- **Fix suggestion:** Remove script tag on error: `script.onerror = () => { document.head.removeChild(script); ... }`.

#### A-CR-017: Scan data period mapping loses one-time payments
- **Severity:** critical
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/features/payments/hooks/use-payment-form.ts:80
- **Description:** Line 80 maps scan result period: `scanData.period === 'one-time' ? 'monthly' : ...`. Business logic error: Receipt scan detects one-time payment (e.g., annual subscription paid upfront). Form defaults to 'monthly' instead of 'yearly'. User saves without checking → creates monthly recurring charge. User expects annual $99 charge → gets monthly $9.99 × 12 = $119.88.
- **Evidence:**
  ```typescript
  period: scanData.period === 'one-time' ? 'monthly' : (scanData.period ?? 'monthly'),
  ```
- **Fix suggestion:** Map 'one-time' to 'yearly' for annual charges, or add validation to warn user: "Receipt shows one-time payment. Is this annual? Set period to yearly."

#### A-CR-018: Selective invalidation creates inconsistent cache state
- **Severity:** high
- **Zone:** Zone A
- **Persona:** code-reviewer
- **File:** src/hooks/api/use-payments.ts:162
- **Description:** Update mutation conditionally invalidates queries based on which fields changed: Financial change (amount/card) → invalidates dashboard, reports, sankey. Schedule change (date/period) → invalidates calendar, upcoming. Race condition: 1) User updates amount from 100 to 200 → dashboard invalidated 2) Dashboard refetch starts 3) User immediately updates period from monthly to yearly 4) Calendar invalidated, dashboard NOT invalidated (amount unchanged) 5) Dashboard refetch completes with OLD period 6) Calendar refetch completes with NEW period 7) Dashboard shows monthly 200, calendar shows yearly 200 → inconsistent.
- **Evidence:**
  ```typescript
  if (affectsFinancials(variables.payment)) {
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all })
  }
  if (affectsSchedule(variables.payment)) {
    queryClient.invalidateQueries({ queryKey: queryKeys.calendar.all })
  }
  ```
- **Fix suggestion:** Always invalidate all dependent queries on update, OR use fine-grained cache keys per payment field and invalidate selectively with proper dependency tracking.

#### A-JR-001: Missing validation for scan period fallback
- **Severity:** high
- **Zone:** Zone A
- **Persona:** junior-developer
- **File:** payments/hooks/use-payment-form.ts:80
- **Description:** I expected: Validation when scanData.period === 'one-time', to ensure it's converted to a valid period. But found: Direct ternary fallback to 'monthly' without checking if scanData.period is valid first. This means: If scanData.period is 'one-time', it defaults to 'monthly', but what if scanData.period is null, undefined, or some invalid value? The code assumes it's always either 'one-time' or a valid period.
- **Evidence:**
  ```typescript
  period: scanData.period === 'one-time' ? 'monthly' : (scanData.period ?? 'monthly'),
  ```
- **Fix suggestion:** Add explicit validation: `period: scanData.period && scanData.period !== 'one-time' ? scanData.period : 'monthly'`

---

## Notes

**Total findings:** 465 across 4 zones, 6 personas

**Next steps:**
1. Run validation (Step 4) to filter in-scope findings
2. Group similar findings
3. Create individual specs for each group
4. Update this report with final counts

**Critical findings requiring immediate attention:**
- A-CR-002: Receipt upload silently fails (data corruption)
- A-CR-007: Optimistic update missing (race conditions)
- A-CR-013: Payment token reused on retry (double charge risk)
- A-CR-017: Scan data period mapping loses one-time payments (billing errors)

---

**Report generated:** 2026-02-16
**Pipeline:** Bug Hunt v2 (6 personas × 4 zones)
