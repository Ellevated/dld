# Security Architecture Cross-Critique

**Persona:** Bruce (Security Architect)
**Label:** G
**Phase:** 2 — Peer Review (Karpathy Protocol)
**Date:** 2026-02-27

---

## My Phase 1 Position — Summary

My research (research-security.md) concluded:

1. **The catastrophic failure mode is unauthorized Gmail inbox access at scale, not arbitrary code execution.** This is a Plaid-pattern product, not a code execution sandbox.
2. **Critical threat: OAuth token plaintext storage** — AES-256-GCM encryption at rest is non-negotiable, not optional.
3. **Critical threat: OAuth CSRF on the Google callback** — the `/auth/google/callback` endpoint without cryptographically random, server-side-validated state = account linking attack.
4. **Critical threat: Prompt injection via RSS** — user-controlled RSS content fed into LLM synthesis without structural isolation.
5. **Critical threat: IDOR on workspace/briefing IDs** — trusting client-supplied workspace_id without JOIN to user_id ownership.
6. **E2B not required** for Phase 2 read-only scope. Node.js worker_threads with explicit permission scoping is sufficient.
7. **Google App Verification** is a hidden blocker — initiate on day 31, not day 89. 4-6 week review timeline.
8. **Do not store Gmail content at rest** — fetch per-task, use in synthesis, discard. Minimizes breach blast radius.
9. **Data deletion must revoke Google OAuth BEFORE deleting DB record** — prevents zombie tokens.

---

## Peer Analysis Reviews

---

### Analysis A (DX Architect — Dan McKinley persona)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Analysis A is primarily a complexity-reduction argument, not a security analysis. However, several of its conclusions have direct security implications that I agree with, and one I must flag as incomplete.

**Where A is correct from a security standpoint:**

The argument against LangGraph.js is partially a security argument. LangGraph introduces a stateful checkpoint store — an additional persistence layer containing user context (preferences, OAuth token references, in-flight briefing state). Every additional persistence layer is an attack surface. A simple `async function generateBriefing()` has zero checkpoint storage attack surface. A LangGraph checkpointer adds a second place where sensitive user state lives. A's position that "this is a linear pipeline that doesn't need a graph" eliminates this attack surface entirely.

The argument against Turso at launch is also implicitly a security argument. Analysis A recommends SQLite WAL on Fly.io persistent volume. From a security perspective, a single SQLite file on a Fly.io volume has a much smaller blast radius than a cloud-hosted Turso DB with a separate API key, a separate auth surface, and a separate potential for misconfiguration (public DB access, leaked Turso token). Keeping the DB local reduces the number of credentials to manage and the number of network paths an attacker can exploit.

**Missed security gaps:**

- A is entirely silent on OAuth token storage encryption. It recommends "OAuth tokens stored encrypted in SQLite" in a one-line aside, but never identifies this as the most critical security decision in the system. A solo founder reading A's analysis would not understand the severity of storing Gmail OAuth refresh tokens in plaintext.
- A does not mention the Google OAuth CSRF state parameter vulnerability at all.
- A recommends "Clerk (free tier)" without noting that the Clerk-Stripe webhook sync is a potential account state inconsistency attack surface (Analysis F covers this well).
- A is silent on prompt injection via RSS — the most underappreciated attack vector in this system.

**Rank:** Moderate (security coverage is incidental, not primary)

---

### Analysis B (Domain Architect — Eric Evans persona)

**Agreement:** Agree (on architecture boundaries) — Partially Agree (on security implications)

**Reasoning from security perspective:**

Analysis B's domain boundary work has significant security implications that B largely gets right, even if not framing them as security decisions:

**Where B is correct from a security standpoint:**

B's insistence that `oauth_tokens` belongs to the `auth` domain and not the `sources` domain is exactly correct from a blast-radius perspective. If OAuth credentials were stored alongside source configurations (same table, same access pattern), then a SQL injection in the briefing compilation endpoint could potentially join across and read OAuth tokens. Separate domains with separate table ownership means separate access patterns. The sources domain never needs to touch the oauth_tokens table directly — it receives a decrypted access token injected at task start. This is the principle of least privilege applied at the domain level.

B's requirement that `SourceCredential` stores "only a reference to the credential vault, never the raw token" is sound. The Source aggregate correctly models this as a reference, not the credential itself.

B's insistence on `workspace_id` as the aggregate root for all queries directly prevents the IDOR vulnerability I flagged in Phase 1. Every repository function taking `userId` as a non-optional parameter is the correct implementation.

The Anti-Corruption Layer at every external boundary (Gmail adapter, Calendar adapter) is also a security control. External API responses mapped to internal types before any DB write prevents API response injection — a scenario where a malicious or compromised external API returns a crafted response that, if stored directly, could cause downstream injection or schema pollution.

**Missed security gaps:**

- B does not address the LLM synthesis component at all from a security perspective. The Briefing context contains the LLM call — which is the prompt injection attack surface. B correctly places LLM execution inside the Briefing context but says nothing about what goes into the LLM prompt, whether RSS content is treated as untrusted input, or how the prompt is architecturally structured to prevent injection.
- B's `SourceCredential` stores "a reference to the credential vault" but never specifies what the credential vault IS in this architecture. In my analysis, the answer is Fly.io secrets + AES-256-GCM application-layer encryption. B leaves this undefined.
- The `Signal` entity (raw ingested content) is correctly identified as the entry point for untrusted external content — but B does not flag the security implication. Signals from RSS feeds are attacker-controlled inputs that will be passed to the LLM synthesis step.

**Rank:** Strong (security implications of domain boundaries are sound even if not explicitly framed as security decisions)

---

### Analysis C (Data Architect — Martin persona)

**Agreement:** Agree

**Reasoning from security perspective:**

Analysis C is the strongest security-adjacent peer analysis in this set, even though it is nominally a data architecture document. Several of C's decisions directly address threat vectors I identified in Phase 1.

**Where C is correct from a security standpoint:**

C's separation of `preferences` (user-authored, user-editable) from `memory_signals` (system-learned, never user-edited) is not just a data integrity decision — it is a security control. If a user could directly modify `memory_signals` (by controlling what the system "learns" about them), they could potentially poison the behavioral model used for synthesis. Keeping system-owned tables separate from user-owned tables with separate write paths prevents this.

C's `oauth_tokens` table design is correct: separate table, AES-256 encrypted columns for both access token and refresh token, `token_expiry` field, scopes in plaintext (scopes are not sensitive). The `UNIQUE INDEX idx_oauth_tokens_workspace_provider` prevents a workspace from accumulating multiple live tokens for the same provider — important for ensuring revocation affects the right token.

C's append-only `usage_ledger` with `idempotency_key UNIQUE` is a security control, not just a data pattern. It prevents a race-condition attack where an adversary triggers concurrent briefings to bypass the usage cap. The `BEGIN IMMEDIATE` transaction pattern with the cap check before the ledger insert is exactly the atomic TOCTOU (time-of-check-time-of-use) prevention I recommended.

C's `briefing_feedback` table design has a subtle security implication C correctly captures: `item_ref TEXT` nullable, `source_id TEXT` nullable. This means the feedback system only stores behavioral signals — it does NOT store the actual email content, source titles, or any PII that appeared in the briefing. This aligns with my "do not store Gmail content at rest" recommendation.

C's `PRAGMA foreign_keys = ON` per-connection note is important: without it, the workspace_id FK constraints that enforce tenant isolation are not enforced. A missed pragma allows orphaned rows and could permit cross-workspace data access in edge cases.

**Missed security gaps:**

- C specifies `access_token_enc TEXT NOT NULL` and `refresh_token_enc TEXT NOT NULL` but does not specify the encryption algorithm (AES-256-GCM) or the key management approach. "AES-256" appears in a comment but the GCM mode (which provides authentication as well as encryption) is not specified. AES-256-CBC without authentication can be attacked with padding oracle attacks. The distinction matters.
- C notes `token_expiry TIMESTAMPTZ NOT NULL` but does not address the SELECT FOR UPDATE semantics needed to prevent a race condition where two concurrent briefings both see an expired access token, both attempt to refresh, and Google issues two access tokens while only one is stored. C mentions this as a concern but the schema does not enforce atomicity at the DB level.
- C does not address the log sanitization requirement. The structured logging fields in the briefing row (`failure_reason TEXT`) could inadvertently capture OAuth error messages that contain partial token values if the Google API returns them in error responses. This needs sanitization at the application layer before writing to the DB.

**Rank:** Strong (the strongest security-adjacent analysis in the peer set)

---

### Analysis D (Evolutionary Architect — Neal persona)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Analysis D takes an evolutionary/fitness function approach. From a security standpoint, the fitness function framing is valuable — security controls that are not tested continuously drift toward failure.

**Where D is correct from a security standpoint:**

D identifies "OAuth token storage encrypted at rest" as a fitness function with a CI implementation: `grep for raw token storage in non-vault paths`. This is exactly right. Static analysis for security anti-patterns is more reliable than code review because it runs on every commit. A developer who accidentally stores a token in plaintext (perhaps during debugging) will be caught before the code reaches production.

D's data isolation integration test — "verify workspace_id-scoped queries cannot return data from another workspace, even with a crafted query parameter" — is the automated IDOR test I described as "Write integration tests that explicitly verify cross-user isolation" in my Phase 1 output. D operationalizes this as a fitness function, which is the correct approach.

D's schema migration reversibility fitness function has security implications: a bad migration that corrupts the oauth_tokens table or the memory_signals table is a data breach in effect, even if not caused by an attacker. D correctly treats migration safety as a load-bearing architectural property.

**Missed security gaps:**

- D's fitness function for "OAuth token storage" only checks for plaintext storage patterns, not for encryption algorithm correctness, IV reuse, or GCM authentication tag verification. A system that uses AES-256-ECB (deterministic encryption, exposes patterns) would pass D's grep-based fitness function but would be cryptographically broken.
- D proposes the fitness function for dependency direction (`shared ← infra ← domains ← api`) but does not add a fitness function for "LLM synthesis prompt receives untrusted content without structural isolation." This is the prompt injection attack surface — it is not caught by any of D's proposed fitness functions.
- D's security fitness function is built for Day 60+ ("Build at Scale Point 1: month 4-6"). But the OAuth token grep should be a Day 1 pre-commit hook, not a month-4 addition. The prompt injection structural check should also be Day 1. D's prioritization is too conservative on security items.

**Rank:** Moderate (security fitness functions are present but incomplete and too deferred)

---

### Analysis E (LLM Systems Architect — Erik persona)

**Agreement:** Agree

**Reasoning from security perspective:**

Analysis E is the only peer analysis that directly addresses the LLM-specific attack surface. E's work on structured outputs, context budgeting, and the behavioral memory two-layer architecture all have direct security implications.

**Where E is correct from a security standpoint:**

E's insistence on structured output (typed JSON) rather than freeform Markdown for briefing output is a security control. If the briefing output is freeform Markdown and is later rendered in a web dashboard or email client, it becomes an XSS vector. A structured `BriefingOutput` JSON object with defined string fields (all of which are encoded before rendering) is safer than Markdown where `<script>` tags could appear in synthesis output from malicious sources.

E's two-stage pipeline pattern (Haiku extraction → Sonnet synthesis) has a security benefit E does not explicitly state: the Haiku extraction stage acts as a pre-processing sanitization layer. Raw article content goes into the Haiku extraction prompt; the Haiku output is a structured `SourceItem` object. If the RSS content contains a prompt injection payload ("SYSTEM: ignore previous instructions"), the Haiku extraction call may produce a structured output with the payload embedded in `title` or `summary` fields — but those fields are typed strings, not instruction contexts. The Sonnet synthesis call then receives structured objects, not raw untrusted text. This is architectural defense-in-depth for prompt injection, even if E does not frame it that way.

E's `LLMJudgeRubric` includes `no_hallucination: boolean` — checking whether URLs and sources in the briefing are real. This is relevant to a specific attack scenario where a malicious RSS feed injects fake URLs or fake source citations into the synthesis output. The LLM judge acts as a secondary verification layer.

E's hard cap enforcement via LiteLLM `budget_manager` at the infrastructure layer is a DoS mitigation — it prevents an attacker who gains access to the briefing trigger endpoint from generating indefinite LLM calls.

**Missed security gaps:**

- E's structured output pattern is excellent, but E does not address the specific concern of what happens when the structured output contains a prompt injection attempt in a string field that will later be rendered to the user. A `summary: "Click here: javascript:alert(1)"` would pass JSON schema validation but cause XSS if the web dashboard renders it without sanitization. E needs an output sanitization layer for all user-visible string fields.
- E's `preference_signals` table design does not address the injection risk in `sender_id TEXT` and `tag TEXT` fields. If these are derived from email headers or RSS metadata, they are attacker-controlled strings that could contain injection payloads if they're later used in dynamic queries or rendered in UIs.
- E does not address the `tool_choice: { type: "any" }` pattern for structured outputs (which E recommends). This forces a tool call but if the synthesis prompt is successfully injection-attacked and the tool call schema is not strictly validated server-side, the attacker could potentially cause unexpected tool call behavior. Validate tool call inputs against the schema on the server, not just on the model's output.

**Rank:** Strong (LLM-specific security thinking is best in the peer set, even if not framed as security analysis)

---

### Analysis F (Devil's Advocate — Fred persona)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

Analysis F is the most contrarian peer analysis. From a security perspective, F raises several valid points and several that are dangerously incomplete.

**Where F is correct from a security standpoint:**

F's SPOF #2 (Clerk-Stripe sync) is a real operational security risk I did not fully address in Phase 1. The Clerk-Stripe webhook synchronization failure scenario — user pays, Stripe fires webhook, Clerk does not update, user cannot access their workspace — is not just a billing bug. It is an authorization state inconsistency. A user who has paid but is denied access to their data is a trust incident. F correctly identifies this as a distributed systems problem. F's proposed fix (Stripe as single source of truth for subscription state, `users.stripe_customer_id` in your DB, no Clerk involvement in billing state) is architecturally cleaner and eliminates the sync surface.

F's argument that behavioral memory on day 1 is empty (and therefore the "moat" claim is not testable at day 90) has a security corollary: an empty behavioral memory system is still a data collection system. You are collecting behavioral signals from day 1 even if you cannot use them for personalization yet. From a privacy and compliance perspective, this means your privacy policy must disclose behavioral data collection before you collect it, regardless of whether you use it. F implicitly raises this concern by questioning whether the moat justifies the complexity — but from security, the concern is different: you may be collecting data you cannot describe to users.

F's minimum viable stack (JWT + bcrypt instead of Clerk) has security merits F does not fully articulate: self-hosted auth means you control the credential storage, the session management, and the audit logs. Clerk is a third-party with access to your user credentials. For some threat models, centralizing auth at a third party is a risk, not a feature.

**Where F is wrong from a security standpoint:**

F's dismissal of Clerk in favor of "JWT + bcrypt in 200-300 lines of TypeScript" is security-naive. Rolling your own auth is one of the most common sources of critical vulnerabilities. The 200-300 lines of TypeScript will be missing:
- Timing-safe comparison for bcrypt (easy to get wrong)
- Proper JWT secret rotation
- Session invalidation on password change
- Brute force protection
- Account enumeration prevention in the forgot-password flow
- Secure HTTP-only cookie handling

Clerk has a dedicated security team that has solved these problems. A 2-person startup has not. F's "build auth yourself" recommendation is a false economy from a security standpoint.

F also recommends against E2B for valid reasons (read-only scope) but does not provide any alternative hardening for the worker execution environment. "No sandbox" is not a security architecture — it is an absence of one. The correct answer (which my Phase 1 analysis provided) is Node.js worker_threads with explicit permission scoping, not no isolation at all.

**Missed security gaps:**

- F never discusses OAuth token storage security despite identifying the Gmail OAuth integration as a core feature. F's minimum viable stack has `users.preferences JSON` — where do the Gmail OAuth tokens go in F's proposed 3-table schema? They are completely absent, which means they would likely end up in an ad-hoc column or in the preferences JSON blob — both catastrophic mistakes.
- F's stress test #2 (Gmail OAuth token expiry) identifies a reliability concern but misses the security dimension: if the token refresh logic is not atomic (SELECT FOR UPDATE), concurrent briefings can cause a token double-refresh race condition that leaves a stale token in the DB. F frames this as a reliability issue only.

**Rank:** Moderate (useful devil's advocate challenges, but the "build your own auth" recommendation is a security anti-pattern)

---

### Analysis H (Operations Engineer — Charity persona)

**Agreement:** Agree

**Reasoning from security perspective:**

Analysis H takes an operations/SRE perspective, but several of its recommendations are directly relevant to security posture — particularly around secrets management, log sanitization, and incident response.

**Where H is correct from a security standpoint:**

H's structured logging schema correctly uses `user_id` (a non-PII identifier) rather than email addresses or OAuth tokens in log lines. This is the exact log sanitization requirement I flagged in Phase 1 as "Logs must NEVER contain: email addresses, email subjects, OAuth tokens, Clerk JWTs."

H's Pino `redact` configuration (`redact: ['*.api_key', '*.token', '*.secret']`) is the correct implementation pattern. This is defense-in-depth for secret leakage via logs — even if a developer accidentally logs an object that contains a token, Pino's redact option prevents it from appearing in the log output.

H's BullMQ recommendation over node-cron has a security dimension H does not explicitly note: in-memory cron job state (node-cron) means that if the process crashes and restarts, a briefing job for a specific user could be lost or duplicated. A duplicated job that retries an OAuth refresh twice creates a race condition that could leave stale tokens. BullMQ's persistent queue with idempotency keys prevents this.

H's admin endpoints (POST /admin/briefings/retry) protected by Fly.io private networking (not exposed to internet) is the correct zero-trust approach for administrative operations. Exposing admin endpoints behind a password or API key is weaker than simply not exposing them to the public internet at all.

H's alert for "Anthropic/OpenAI API key rotation should trigger an alert" addresses a real operational security risk: API key rotation is often forgotten, and a leaked key that was rotated out of the application but not rotated at the provider level is still exploitable.

**Missed security gaps:**

- H recommends BullMQ with Upstash Redis, but does not address the security of the Redis connection. Redis is frequently misconfigured without authentication. The connection string should use TLS (`rediss://`) and a password. An unauthenticated Redis instance visible to the internet would expose the entire job queue including user IDs and workspace IDs.
- H's circuit breaker implementation (opossum library) does not address the scenario where the fallback function itself is exploitable. H's fallback for HN RSS returns `{ stories: [], error: "..." }` — this is safe. But if a similar fallback for Gmail were to silently proceed with empty credentials, the synthesis call would run with incomplete context and potentially expose the absence of Gmail data in a way that leaks information about the user's configuration.
- H discusses the Fly.io volume for SQLite but does not address volume encryption. Fly.io persistent volumes are encrypted at rest by the infrastructure layer, but this is a compliance question the team should verify rather than assume. If Fly.io does NOT encrypt volumes at rest (or if that encryption is provider-controlled and you need customer-managed keys for compliance reasons), application-layer encryption of the SQLite file becomes necessary.
- H's health check endpoint `/health` checks "DB connection, Redis connection, last cron heartbeat timestamp" — but should NOT expose version information or infrastructure details in the response body. A health check that returns `{"status": "ok", "db": "turso", "version": "1.2.3"}` gives attackers a technology fingerprint. Return `{"status": "ok"}` only.

**Rank:** Strong (operational security practices are sound; the missed gaps are implementation details, not architectural blind spots)

---

## Ranking

**Best Analysis:** C (Data Architect)

**Reason:** Analysis C has the highest density of security-correct decisions, even though it is nominally a data architecture document. The `oauth_tokens` table design, the append-only usage ledger with idempotency keys preventing race-condition abuse, the separation of user-authored preferences from system-learned signals, and the explicit `PRAGMA foreign_keys = ON` per-connection note all address real attack vectors without naming them as such. C demonstrates that good data architecture and good security architecture are often the same thing: both enforce invariants, both define clear ownership, both prevent state inconsistency.

**Worst Analysis:** F (Devil's Advocate)

**Reason:** Analysis F commits the cardinal security sin of recommending "build your own auth" to save complexity, without acknowledging that rolling custom authentication is one of the top sources of critical vulnerabilities in SaaS applications. F's minimum viable stack has a complete absence of OAuth token storage strategy (the most critical security decision in this system). F's stress test #2 identifies OAuth token expiry as a reliability concern without recognizing it as a security concern (stale token race conditions, token refresh atomicity). Despite having the correct instinct that complexity is the enemy of security (simpler systems have smaller attack surfaces), F applies this correctly to LangGraph and Turso but incorrectly to authentication — which is one domain where off-the-shelf solutions (Clerk, Auth0) are dramatically safer than custom implementations.

---

## Revised Position

**Revised Verdict:** Substantially confirmed, with two refinements from peer review

**What the peer analyses confirmed:**

- My assessment of OAuth token encryption at rest as the critical issue is validated by C, which independently arrived at the same design for the `oauth_tokens` table.
- My assessment of workspace IDOR as a critical threat is validated by B, which independently made `userId` a mandatory parameter on all repository functions.
- My assessment of E2B as over-engineering for Phase 2 read-only scope is validated by A, D, and F all independently reaching the same conclusion.
- My assessment of prompt injection via RSS as an underappreciated threat is validated by E's two-stage pipeline architecture, which provides structural defense without explicitly naming the prompt injection threat.

**Refinements from peer review:**

**Refinement 1: The Clerk-Stripe sync race condition is a higher-severity issue than I assessed in Phase 1.**

Analysis F's SPOF #2 correctly identifies the Clerk-Stripe webhook sync as a potential authorization inconsistency attack surface. In my Phase 1 analysis, I treated Clerk as the authoritative source for auth and trusted its webhook delivery. F's analysis highlights that Stripe webhook failures during Clerk sync could leave a user in a state where they have paid but cannot access their workspace. This is not just a billing bug — it is an authorization state corruption that could affect legitimate users and potentially be exploited to deny service to specific users.

**Revised recommendation:** Use a local `billing_cache` table (as C designed) as the fast-path for authorization decisions, but add a synchronous Stripe API check (C's recommendation for 429 responses) as a fallback when the billing cache indicates a user is over-limit. This prevents the Stripe-Clerk sync race from affecting user access, while keeping Stripe as the authoritative billing source.

**Refinement 2: The structured output pattern from E provides stronger prompt injection defense than my RSS sanitization approach alone.**

My Phase 1 analysis relied on input sanitization (stripping SYSTEM: prefixes, truncating content) combined with structural prompt separation (XML tags). Analysis E's two-stage pipeline — Haiku extraction to typed `SourceItem` objects, then Sonnet synthesis from structured objects only — provides a more robust architectural defense. The typed extraction output cannot carry instruction-format payloads into the synthesis context; it can only carry typed string values in defined fields.

**Revised recommendation:** Implement both layers. E's two-stage pipeline is the architectural defense; my input sanitization layer is the defense-in-depth fallback for when the extraction stage itself is targeted.

---

## Final Security Recommendation

*Synthesized position after reading all peer analyses.*

The system's security posture is determined by four non-negotiable decisions that must be locked in before the first user onboards:

**Decision 1: OAuth Token Encryption**
AES-256-GCM encryption at rest for all OAuth tokens, with key stored in Fly.io secrets. This is not optional. Implement before any user grants Gmail access. Write the key rotation runbook before onboarding user #1, not after a breach. (My Phase 1 analysis, confirmed by C.)

**Decision 2: OAuth CSRF State Parameter**
Cryptographically random (32-byte) state parameter, server-side session storage, 10-minute expiry, one-time use validation on the Google OAuth callback. This endpoint is the highest-risk surface in the system — an unprotected state parameter is a direct Gmail account linking attack. (My Phase 1 analysis, not adequately addressed by any peer.)

**Decision 3: Prompt Architecture for Untrusted Sources**
RSS feed content and Gmail snippets must never reach the Sonnet synthesis context as raw text. Implement E's two-stage pipeline: Haiku extraction to typed `SourceItem` objects first, synthesis from structured objects second. Add my input sanitization layer to the Haiku extraction prompt as defense-in-depth. (Combination of my Phase 1 analysis and E's peer analysis.)

**Decision 4: Workspace Isolation Enforcement**
Every single DB query in every domain must include `WHERE workspace_id = $workspaceId AND workspaces.user_id = $userId`. Use UUID v7 (not sequential integers) for all workspace IDs. Write integration tests that explicitly verify cross-workspace isolation before launch. (My Phase 1 analysis, confirmed by B and C.)

**The one thing I got wrong in Phase 1:**
I underweighted the Clerk-Stripe webhook sync as an authorization risk. I should have flagged this as a design concern requiring either: (a) local billing cache as authoritative fast-path (C's approach), or (b) synchronous Stripe API call on authorization decisions. The distributed sync between two third-party auth and billing systems creates an authorization consistency window that can be exploited or simply fail at the worst time (during the free trial conversion window).

**The one thing peers missed that I got right:**
No peer analysis addressed the Google App Verification requirement. This is a hidden launch blocker: Google requires a security review for apps requesting Gmail scopes before allowing more than 100 users. The review takes 4-6 weeks. If this is not initiated by day 31 of Phase 2 (when development begins), the launch at day 90 will be blocked — users will see a "This app hasn't been verified" warning screen that kills trial conversion. This is a deadline-sensitive security/compliance issue, not just an ops concern.
