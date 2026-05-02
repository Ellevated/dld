# Bug Fix: [BUG-181] Free Tier Enforcement Gaps

**Status:** done | **Priority:** P0 | **Date:** 2026-02-18
**Bug Hunt Report:** [BUG-178](features/BUG-178-bughunt.md)

## Findings in This Group

| ID | Severity | Title |
|----|----------|-------|
| C-QA-001 | critical | scan-receipt Edge Function has no server-side scan count check |
| B-CR-003 | high | ReceiptScanButton and PaymentsPrimaryButtons bypass scan limit |
| B-ARCH-009 | high | Free tier card limit (maxCards:1) computed but never wired to UI |
| B-ARCH-003 | high | Free tier payment count TOCTOU -- client check races with mutation |
| D-SEC-005 | high | Telegram bot linked user photo handler has zero scan rate limiting |
| B-ARCH-002 | medium | PaywallOverlay renders Pro-only children in DOM (blur+opacity CSS) |

## What BUG-177 Already Fixed

BUG-177 (done) added:
- `useMonthlyReceiptCount()` hook in `src/hooks/api/use-receipt-scan.ts` -- counts receipts from DB for current month
- `canScanReceipt` flag in `usePlanLimits()` -- `isPro || receiptsUsed < FREE_LIMITS.maxReceiptScans`
- Soft gate in `ReceiptScanCard` -- shows limit dialog when `!canScanReceipt`, with upgrade CTA and "add manually" fallback
- "Remaining X of 3" display text in `ReceiptScanDialog` header

**What BUG-177 did NOT fix (remaining gaps):**
1. **No server-side enforcement** -- the `scan-receipt` Edge Function does rate-limit checking (via `checkRateLimit`) but does NOT check the user's subscription plan or monthly scan count. A free user can call the API directly (curl/Postman) and scan unlimited receipts.
2. **Alternative web entry points bypass limit** -- `PaymentsPrimaryButtons` has a scan button (line 51) that opens `ReceiptScanDialog` without checking `canScanReceipt` first. `ReceiptScanButton` is dead code but exported, meaning it could be used without a gate.
3. **Telegram bot photo handler has no scan limit** -- linked users in the Telegram bot can send unlimited photos. There is no monthly scan count check for linked users at all.
4. **Card limit never enforced** -- `canCreateCard` is computed in `usePlanLimits()` but never checked in `CardsPrimaryButtons` or `CardsMutateDrawer`. Free users can create unlimited cards.
5. **PaywallOverlay renders children in DOM** -- when `isLocked=true`, children are rendered with `opacity-30 blur-sm pointer-events-none select-none`. The actual data (reports, calendar) is in the DOM and extractable via DevTools. This is a low-severity information leak but should be addressed.
6. **Payment count TOCTOU** -- `canCreatePayment` is checked client-side before mutation, but between the check and the Supabase INSERT a second tab/request could slip through.

## Root Cause

Free tier enforcement was implemented as a purely client-side concern. The `usePlanLimits()` hook computes limit flags, but:
- The server (Edge Functions) has no awareness of plan limits
- Not all client-side entry points consume `usePlanLimits()` consistently
- The Telegram bot operates entirely outside the web client and has no concept of plan limits for linked users
- `PaywallOverlay` uses CSS-only hiding, which is not a security boundary

The architectural gap is: **there is no server-side middleware or RPC that enforces plan limits before resource creation**. All enforcement relies on the web client UI making the correct checks in every entry point.

## Fix Approach

### 1. Server-side scan limit enforcement in `scan-receipt` Edge Function

Add a subscription-aware scan count check to the `scan-receipt` Edge Function. After authenticating the user (`verifyClerkToken`), query `user_subscriptions` to determine if user is Pro. If not Pro, count receipts created this month (from `receipts` table filtered by `user_id` and `created_at >= start of month`). If count >= 3, return 403 with a descriptive error. This makes the server the authoritative enforcement point.

The check should use `createAdminClient()` (not the user client) to query subscription status, since RLS on `user_subscriptions` already scopes to the user but we need a reliable read.

### 2. Telegram bot scan limit for linked users

In `telegram-webhook/handlers/receipts.ts`, the linked-user photo handler (line 87+) should check the user's subscription and monthly scan count before invoking `scanReceipt`. Reuse the same logic as the Edge Function: query `user_subscriptions` for plan, count `receipts` for current month, and if limit exceeded, reply with a message directing the user to upgrade. Since the Telegram handler already has `telegramUser.user_id`, this is straightforward.

### 3. Wire `canCreateCard` to `CardsPrimaryButtons`

In `CardsPrimaryButtons`, import `usePlanLimits` and check `canCreateCard`. When the limit is reached, replace the "Add card" button with an `UpgradeDialog` trigger (same pattern as `PaymentsPrimaryButtons` does for payments). This is a 1:1 copy of the existing payments pattern.

### 4. Wire `canScanReceipt` to `PaymentsPrimaryButtons` scan button

The scan button in `PaymentsPrimaryButtons` (line 51) should check `canScanReceipt` before opening the dialog. When limit is reached, show the same soft limit dialog that `ReceiptScanCard` already shows, or redirect to `UpgradeDialog`. Import `canScanReceipt` from the existing `usePlanLimits` call already in the component.

### 5. Fix PaywallOverlay to not render children when locked

Change `PaywallOverlay` from rendering children with CSS blur to conditionally not rendering children at all when `isLocked=true`. Instead of `{children}` with blur classes, render a static placeholder (the lock icon, description, and upgrade button only). This prevents Pro-only data from appearing in the DOM.

**Important UX consideration:** The current blur effect provides a "preview teaser" of what Pro offers. If removing the preview entirely is undesirable from a product perspective, an alternative is to render a static mock/screenshot instead of live data. However, the simplest and most secure approach is to simply not render children.

### 6. Add `canScanReceipt` gate to `ReceiptScanButton` (dead code hardening)

Even though `ReceiptScanButton` is currently unused (no imports found), it is an exported public component. Add the same `canScanReceipt` gate that `ReceiptScanCard` has. If the component is truly dead code, consider removing it entirely.

### 7. Extract shared plan-limit checking utility for Edge Functions

Create a shared utility in `supabase/functions/_shared/billing/plan-limits.ts` that provides a `checkFreeTierLimit(supabase, userId, resource)` function. This function queries `user_subscriptions` and counts the relevant resource for the current month. Both `scan-receipt` and the Telegram bot handler can import it. This prevents logic duplication and ensures consistency.

## Impact Tree

### UP -- who uses the affected code?

- `scan-receipt/index.ts` -- called by `useReceiptScan` mutation in `src/hooks/api/use-receipt-scan.ts`
- `useReceiptScan` -- called by `ReceiptScanDialog` component
- `ReceiptScanDialog` -- used by `ReceiptScanCard`, `ReceiptScanButton`, `PaymentsPrimaryButtons`
- `PaywallOverlay` -- used by `Reports` page (`src/features/reports/index.tsx`) and `Calendar` page (`src/features/calendar/index.tsx`)
- `CardsPrimaryButtons` -- used by Cards page route
- `telegram-webhook/handlers/receipts.ts` -- invoked by Grammy router in `telegram-webhook/index.ts`

### DOWN -- what does the affected code depend on?

- `scan-receipt/index.ts` depends on: `clerk-auth.ts`, `receipt-scanner.ts`, `rate-limit.ts`, `response.ts`, `supabase.ts`
- `usePlanLimits` depends on: `usePayments`, `useCards`, `useIsPro`, `useMonthlyReceiptCount`
- `PaywallOverlay` depends on: `UpgradeDialog`, `lucide-react`
- `receipts.ts` (Telegram) depends on: `scan-helpers.ts`, `receipt-service.ts`, `access-levels.ts`, `telegram-auth.ts`

### BY TERM -- grep project

| File | Line | Status | Action |
|------|------|--------|--------|
| `supabase/functions/scan-receipt/index.ts` | 17-58 | needs fix | Add subscription check + monthly scan count before scanning |
| `supabase/functions/telegram-webhook/handlers/receipts.ts` | 87-113 | needs fix | Add monthly scan count check for linked users |
| `src/features/payments/components/payments-primary-buttons.tsx` | 51 | needs fix | Gate scan button with `canScanReceipt` |
| `src/features/cards/components/cards-primary-buttons.tsx` | 10 | needs fix | Gate create button with `canCreateCard` |
| `src/features/billing/components/paywall-overlay.tsx` | 23-25 | needs fix | Do not render children when `isLocked=true` |
| `src/features/receipts/components/receipt-scan-button.tsx` | 30 | needs fix | Add `canScanReceipt` gate or remove dead code |
| `src/hooks/use-plan-limits.ts` | all | ok (BUG-177) | Already has `canCreateCard`, `canScanReceipt` flags |
| `src/hooks/api/use-receipt-scan.ts` | all | ok (BUG-177) | Already has `useMonthlyReceiptCount` |
| `src/features/receipts/components/receipt-scan-card.tsx` | all | ok (BUG-177) | Already gates with `canScanReceipt` |
| `src/features/receipts/components/receipt-scan-dialog.tsx` | all | ok (BUG-177) | Already shows remaining count |

## Research Sources

None needed -- all fixes use existing patterns already present in the codebase (`usePlanLimits`, `UpgradeDialog` trigger, Supabase queries for count).

## Allowed Files

### New files:
1. `supabase/functions/_shared/billing/plan-limits.ts` -- shared free tier limit checking utility for Edge Functions
2. `supabase/functions/tests/plan-limits-test.ts` -- unit tests for the shared plan limits utility

### Modified files:
3. `supabase/functions/scan-receipt/index.ts` -- add server-side scan limit enforcement
4. `supabase/functions/telegram-webhook/handlers/receipts.ts` -- add scan limit for linked users
5. `src/features/payments/components/payments-primary-buttons.tsx` -- gate scan button with `canScanReceipt`
6. `src/features/cards/components/cards-primary-buttons.tsx` -- gate create button with `canCreateCard`
7. `src/features/billing/components/paywall-overlay.tsx` -- stop rendering children when locked
8. `src/features/receipts/components/receipt-scan-button.tsx` -- add limit gate or remove dead code

### Test files:
9. `src/hooks/__tests__/use-plan-limits.test.ts` -- regression tests for plan limit flags
10. `src/features/billing/components/__tests__/paywall-overlay.test.tsx` -- verify children not rendered when locked
11. `src/features/cards/components/__tests__/cards-primary-buttons.test.tsx` -- verify card limit gate

## Implementation Plan

### Task 1: Create shared plan-limits utility for Edge Functions
**Type:** code
**Files:**
  - create: `supabase/functions/_shared/billing/plan-limits.ts`
  - create: `supabase/functions/tests/plan-limits-test.ts`
**Details:**
  - Export `checkScanLimit(supabase: SupabaseClient, userId: string): Promise<{ allowed: boolean; used: number; limit: number }>`
  - Query `user_subscriptions` for plan (if plan !== 'free' and status === 'active', return allowed:true)
  - Count `receipts` where `user_id = userId` and `created_at >= start of current month`
  - Return `{ allowed: used < 3, used, limit: 3 }`
  - Export `FREE_SCAN_LIMIT = 3` constant
  - Tests: free user under limit -> allowed, free user at limit -> blocked, pro user -> always allowed, no subscription row -> treat as free
**Acceptance:** Utility correctly determines scan eligibility for free and pro users

### Task 2: Add server-side scan enforcement to scan-receipt
**Type:** code
**Files:**
  - modify: `supabase/functions/scan-receipt/index.ts`
**Details:**
  - After `verifyClerkToken` and before processing the image, call `checkScanLimit(adminClient, userId)`
  - If `!allowed`, return `errorResponse("Free tier scan limit reached (3/month). Upgrade to Pro for unlimited scans.", 403, req)`
  - Use `createAdminClient()` for the limit check (not user client) to bypass RLS for the subscription query
**Acceptance:** Direct API call from a free user who has 3+ scans this month returns 403

### Task 3: Add scan limit to Telegram bot linked-user handler
**Type:** code
**Files:**
  - modify: `supabase/functions/telegram-webhook/handlers/receipts.ts`
**Details:**
  - In the linked-user photo handler (after line 87), before scanning, call `checkScanLimit`
  - If not allowed, reply with Russian message: "Вы использовали 3 из 3 бесплатных сканирований в этом месяце. Перейдите на Pro для безлимитных сканирований: https://plpilot.ru/billing" with inline keyboard URL button
  - Import `createAdminClient` (already imported) and `checkScanLimit` from shared utility
**Acceptance:** Linked free user sending a 4th photo in a month gets a friendly limit message

### Task 4: Wire `canScanReceipt` to PaymentsPrimaryButtons and fix ReceiptScanButton
**Type:** code
**Files:**
  - modify: `src/features/payments/components/payments-primary-buttons.tsx`
  - modify: `src/features/receipts/components/receipt-scan-button.tsx`
**Details:**
  - In `PaymentsPrimaryButtons`: the component already imports `usePlanLimits`. Destructure `canScanReceipt` alongside existing destructured values. When `!canScanReceipt`, the scan button should either open a limit dialog (same pattern as `ReceiptScanCard`) or disable with a tooltip. Simplest approach: check `canScanReceipt` in the scan button onClick, show toast with limit message and link to upgrade.
  - In `ReceiptScanButton`: either (a) add `usePlanLimits` import and gate like `ReceiptScanCard` does, or (b) remove the file entirely since it has zero imports. Recommend option (b) -- delete dead code.
**Acceptance:** Clicking scan in payments page when at limit shows friendly limit message

### Task 5: Wire `canCreateCard` to CardsPrimaryButtons
**Type:** code
**Files:**
  - modify: `src/features/cards/components/cards-primary-buttons.tsx`
**Details:**
  - Import `usePlanLimits` and `UpgradeDialog` from billing
  - Destructure `canCreateCard` from `usePlanLimits()`
  - When `!canCreateCard`, replace the "Add card" button with an `UpgradeDialog` trigger (exact same pattern as `PaymentsPrimaryButtons` line 42-48)
  - Optionally show "1 of 1 cards used" indicator like payments does
**Acceptance:** Free user with 1 card sees "Upgrade to Pro" instead of "Add card" button

### Task 6: Fix PaywallOverlay to not render children when locked
**Type:** code
**Files:**
  - modify: `src/features/billing/components/paywall-overlay.tsx`
**Details:**
  - When `isLocked=true`, do NOT render `{children}` at all
  - Instead render only the lock overlay with icon, description, and upgrade button
  - Maintain the same visual height using min-height or a placeholder skeleton
  - This prevents Pro-only data (reports charts, calendar entries) from being in the DOM
**Acceptance:** Inspecting DOM with DevTools when logged in as free user shows no report/calendar data

### Task 7: Add regression tests
**Type:** test
**Files:**
  - create: `src/hooks/__tests__/use-plan-limits.test.ts`
  - create: `src/features/billing/components/__tests__/paywall-overlay.test.tsx`
  - create: `src/features/cards/components/__tests__/cards-primary-buttons.test.tsx`
**Details:**
  - `use-plan-limits.test.ts`: Test `canScanReceipt`, `canCreateCard`, `canCreatePayment` flags return correct values for free vs pro users and various count states. Mock `usePayments`, `useCards`, `useIsPro`, `useMonthlyReceiptCount`.
  - `paywall-overlay.test.tsx`: Render with `isLocked=true` and verify children text NOT in document. Render with `isLocked=false` and verify children ARE rendered.
  - `cards-primary-buttons.test.tsx`: Mock `usePlanLimits` to return `canCreateCard: false`, verify upgrade trigger is shown instead of "Add card" button.
**Acceptance:** All 3 test files pass; tests cover the exact bug scenarios described in the findings

## Definition of Done

- [ ] Server-side scan limit enforced in `scan-receipt` Edge Function (403 for free users at limit)
- [ ] Telegram bot linked-user photo handler checks monthly scan limit
- [ ] `PaymentsPrimaryButtons` scan button checks `canScanReceipt`
- [ ] `CardsPrimaryButtons` create button checks `canCreateCard`
- [ ] `PaywallOverlay` does not render children in DOM when `isLocked=true`
- [ ] `ReceiptScanButton` dead code removed or gated
- [ ] Shared `plan-limits.ts` utility created for server-side reuse
- [ ] Regression tests added for all findings (min 3 test files)
- [ ] `pnpm test:run` passes with no new failures
- [ ] `pnpm lint` passes
- [ ] Impact tree verified: all 6 findings addressed
