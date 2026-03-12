# Ideas

Out-of-scope findings, future improvements, and architectural notes.

## Out of Scope from BUG-106 (2026-02-16)

- **Object URL not revoked when file changes during preview** (A-CR-011) — Minor memory leak (50MB over 10 selections); low impact, theoretical concern
- **waitForElement rejection not handled** (A-CR-003) — Merged into F-039 (widget init error UX). Error IS caught, just message is generic.
- **Converted total calculated even when only one currency** (B-CR-009) — Performance micro-optimization; no user-facing bug
- **Redundant currency check when allCurrencies.size === 1** (B-CR-010) — Code clarity issue, not a bug; naming improvement only
- **Unique key uses compound id+date but entries are from expandPayments** (B-CR-014) — Code is actually correct; finding is a documentation suggestion
- **Locale hardcoded to ru-RU breaks international users** (B-QA-004) — PLPilot is a Russian-language app; i18n is a feature request not a bug
- **Relative date labels hardcoded in Russian** (B-QA-029) — Same as above — i18n feature request, not bug for Russian-only app
- **File validation rejects non-JPEG/PNG/WebP even if ACCEPTED_TYPES expands** (A-QA-012) — Hypothetical — ACCEPTED_TYPES is NOT being expanded; code is correct as-is
- **Billing history shows YooKassa payment IDs without redaction** (A-SEC-012) — Low-risk information disclosure; payment IDs alone are not sensitive without API keys
- **Competitor pricing sent to AI without validation could leak business intelligence** (A-SEC-013) — Theoretical concern; user voluntarily inputs this data; AI training opt-out is separate concern
- **YooKassa widget errors logged to console may expose sensitive data** (A-SEC-014) — Console.error logging is standard practice; sensitive data exposure requires malicious browser extension
- **Variable named 'date' but contains Date object, not date string** (C-JR-003) — Naming convention preference, zero user impact
- **Loading state shows only text, no spinner or skeleton (cards)** (C-UX-008) — UI polish, not a bug; text loading indicator is functional
- **Loading state shows only text, no spinner or skeleton (tags)** (C-UX-009) — Same as above; UI polish
- **Tags section hidden when no tags exist** (A-UX-023) — Feature discoverability, not a bug; design decision
- **Form reset on dialog close loses unsaved changes without confirmation** (A-UX-027) — Nice-to-have UX improvement; not a bug — standard dialog behavior
- **Custom period_days allows up to 3650 days (10 years)** (A-JR-006) — Intentional generous limit; not a bug
- **parseCents allows empty whole part like '.50'** (A-JR-017) — Mathematically correct behavior (.50 = $0.50); not a bug
- **parseCents: normalized === '' check is dead code** (A-JR-018) — Dead code, not a bug; defensive programming
- **IIFE in JSX for converted total is hard to debug and test** (B-QA-016) — Code style preference, not a bug
- **daysSince calculation can be negative due to clock changes** (B-QA-019) — Edge case with manual clock manipulation; minor UX impact
- **Monthly summary day selector limited to 28 days** (D-QA-005) — Intentional design to handle February reliably; not a bug
- **Fallback to localStorage breaks multi-device sync** (D-ARCH-004) — Architectural concern about dual-state; not a bug in single-device use
- **No indication of which payment is being refunded** (A-UX-013) — UX improvement; refund targets latest payment which is correct behavior
- **No validation feedback for last_four input** (C-UX-003) — Minor UX polish; Zod validation catches on submit
- **cheapest_regions array rendered without key uniqueness validation** (A-QA-022) — Defensive coding; backend data is unlikely to have duplicate country codes
- **Russian pluralization breaks for numbers 11-14** (B-QA-010) — Finding itself concludes the code IS correct for Russian pluralization

## Out of Scope from BUG-115 (2026-02-17)

- Add hooks-config.json for project-specific allowed/blocked pattern overrides (A-SA-001) — architectural enhancement, not a bug; config system is a new feature
- Support worktree-local .claude/hooks/ directory with fallback to main repo (A-SA-003) — feature request for advanced git worktree workflows; not a defect
- Create hooks-manifest.json for programmatic hook discovery (A-SA-004) — developer tooling improvement; no current user-facing breakage
- Add optional verbose logging mode for hook dispatch debugging (A-SA-007) — observability enhancement; current silent exit is by design (ADR-004 fail-safe)
- Add early guard for empty file_path as defense-in-depth (A-JD-004) — defensive coding improvement; current behavior catches error downstream without data loss

