# Cross-Cutting Rules: Morning Briefing Agent

**Architecture:** Alternative B — Domain-Pure
**Date:** 2026-02-28
**Source:** All 8 personas + Architect Board synthesis
**Rule:** Cross-cutting rules are CODE, not prose.

---

## Error Handling Pattern

```typescript
// All domain functions return Result<T, E>
type Result<T, E> = { ok: true; value: T } | { ok: false; error: E };

function ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

function err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

// Domain error types (per context)
type BriefingError =
  | { code: 'TASK_CAP_EXCEEDED'; tasksUsed: number; taskCap: number }
  | { code: 'NO_SOURCES_AVAILABLE' }
  | { code: 'SYNTHESIS_FAILED'; reason: string }
  | { code: 'SCHEMA_VALIDATION_FAILED'; zodError: string }
  | { code: 'ALL_DELIVERIES_FAILED'; attempts: number };

type SourceError =
  | { code: 'SOURCE_AUTH_EXPIRED'; provider: string }
  | { code: 'SOURCE_FETCH_TIMEOUT'; sourceId: string }
  | { code: 'SOURCE_HEALTH_DEGRADED'; sourceId: string };

type WorkspaceError =
  | { code: 'WORKSPACE_NOT_FOUND' }
  | { code: 'WORKSPACE_TRIAL_EXPIRED' }
  | { code: 'WORKSPACE_LIMIT_REACHED'; currentCount: number };

// Usage in domain code
async function compileBriefing(
  workspaceId: string
): Promise<Result<Briefing, BriefingError>> {
  const capCheck = await billing.canConsumeTask(workspaceId);
  if (!capCheck.ok) return err({ code: 'TASK_CAP_EXCEEDED', ...capCheck.error });

  const sources = await fetchAllSources(workspaceId);
  if (sources.succeeded.length === 0) return err({ code: 'NO_SOURCES_AVAILABLE' });

  // ... compilation logic
  return ok(briefing);
}
```

---

## Money Handling

```typescript
// ALL money in cents (integer). Never float. Never Decimal.
// ADR-001: Avoid float precision errors

interface LLMCost {
  amount_cents: number;   // $0.045 = 4 (rounded to nearest cent)
}

// For sub-cent LLM costs: store as micro-dollars (1/1,000,000)
interface PreciseCost {
  amount_microdollars: number;  // $0.045 = 45000
}

// Aggregation: sum micro-dollars, convert to cents only for Stripe/display
function toCents(microdollars: number): number {
  return Math.ceil(microdollars / 10000);
}
```

---

## Auth Middleware

```typescript
// Clerk wrapper — imported ONLY in infra/auth/
import { requireAuth } from '@clerk/express';

// Workspace ownership check
async function requireWorkspaceAccess(
  req: Request,
  res: Response,
  next: NextFunction
) {
  const { workspaceId } = req.params;
  const clerkUserId = req.auth.userId;  // from Clerk middleware

  const workspace = await db.query(
    'SELECT id FROM workspace_workspaces WHERE id = ? AND clerk_user_id = ?',
    [workspaceId, clerkUserId]
  );

  if (!workspace) {
    return res.status(404).json({
      code: 'WORKSPACE_NOT_FOUND',
      message: 'Workspace not found or access denied',
      action: 'Verify workspace ID or check account ownership'
    });
  }

  req.workspace = workspace;
  next();
}

// Route composition
router.get(
  '/api/v1/workspaces/:workspaceId/briefings',
  requireAuth(),              // Clerk: who are you?
  requireWorkspaceAccess,     // Our code: do you own this workspace?
  briefingController.list     // Domain handler
);
```

---

## Logging Schema

```typescript
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => ({ level: label }),
  },
});

// Standard log context
interface LogContext {
  service: 'briefing-worker' | 'api' | 'scheduler' | 'webhook';
  trace_id: string;           // sha256(workspace_id + scheduled_window)
  workspace_id?: string;
  briefing_id?: string;
}

// Example: briefing synthesis complete
logger.info({
  service: 'briefing-worker',
  trace_id: 'abc123',
  workspace_id: 'ws_5eF6g7H',
  briefing_id: 'brief_9iJ0k1L',
  msg: 'briefing.synthesis.completed',
  sources_configured: 5,
  sources_succeeded: 4,
  model: 'claude-sonnet-4-6',
  tokens_in: 4100,
  tokens_out: 1500,
  cost_usd: 0.045,
  duration_ms: 4200,
});

// NEVER log:
// - OAuth tokens (access_token, refresh_token)
// - User email content
// - Raw API credentials
```

---

## Security Rules

```typescript
// OAuth token handling
// 1. Encrypted at rest: AES-256-GCM
// 2. DEK from Fly.io secrets (ENCRYPTION_KEY env var)
// 3. Decrypted in-memory per-request only
// 4. Never cached beyond single request scope
// 5. Never logged

import { createCipheriv, createDecipheriv, randomBytes } from 'crypto';

function encryptToken(plaintext: string, key: Buffer): string {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', key, iv);
  const encrypted = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  const tag = cipher.getAuthTag();
  return Buffer.concat([iv, tag, encrypted]).toString('base64');
}

function decryptToken(ciphertext: string, key: Buffer): string {
  const data = Buffer.from(ciphertext, 'base64');
  const iv = data.subarray(0, 12);
  const tag = data.subarray(12, 28);
  const encrypted = data.subarray(28);
  const decipher = createDecipheriv('aes-256-gcm', key, iv);
  decipher.setAuthTag(tag);
  return decipher.update(encrypted) + decipher.final('utf8');
}

// Gmail content: NEVER stored at rest. Ephemeral in-memory only.
// Google OAuth scopes: gmail.readonly + calendar.readonly ONLY
// Prompt injection defense: structural XML tag separation in prompts
```

---

## Context Boundary Enforcement

```bash
#!/bin/bash
# scripts/check-context-boundaries.sh — pre-commit + CI

set -e

# No cross-context imports
CONTEXTS=("briefing" "source" "priority" "workspace" "notification" "identity" "billing")

for from_ctx in "${CONTEXTS[@]}"; do
  for to_ctx in "${CONTEXTS[@]}"; do
    if [ "$from_ctx" != "$to_ctx" ]; then
      if grep -rn "from.*domains/$to_ctx" "src/domains/$from_ctx/" 2>/dev/null; then
        echo "FAIL: $from_ctx imports from $to_ctx"
        exit 1
      fi
    fi
  done
done

echo "Context boundaries OK"
```

---

## Fitness Functions (Pre-commit + CI)

```bash
#!/bin/bash
# scripts/check-architecture.sh

set -e

# 1. Context boundary enforcement
./scripts/check-context-boundaries.sh

# 2. Dependency direction
npx dependency-cruiser --validate .dependency-cruiser.cjs src/ || exit 1

# 3. File size limit (400 LOC, 600 for tests)
find src/ -name "*.ts" ! -name "*.test.ts" -exec wc -l {} + \
  | awk '$1 > 400 { print "OVER LIMIT: " $2 " (" $1 " lines)"; fail=1 } END { exit fail }' || exit 1

# 4. No float in money paths
grep -rn "price.*float\|amount.*float\|cost.*0\." src/ \
  && echo "FAIL: float in money context" && exit 1 || true

# 5. No Clerk imports outside infra/auth/
grep -rn "from.*@clerk" src/domains/ src/api/ \
  && echo "FAIL: Clerk imported outside infra/auth/" && exit 1 || true

# 6. No raw token in logs
grep -rn "refresh_token\|access_token" src/ --include="*.ts" \
  | grep -v "oauth_tokens\|_enc\|encrypt\|decrypt\|\.test\." \
  && echo "FAIL: potential raw token exposure" && exit 1 || true

# 7. No cross-context SQL JOINs
grep -rn "JOIN.*briefing_.*ON.*source_\|JOIN.*source_.*ON.*briefing_" src/ \
  && echo "FAIL: cross-context SQL JOIN detected" && exit 1 || true

# 8. Google OAuth verification gate (pre-launch)
# This is a manual check — reminder output only
echo "REMINDER: Google OAuth App Verification must be submitted by day 31 of Phase 2"

echo "All architecture checks passed"
```

---

## Domain Event Bus

```typescript
// EventEmitter3 typed bus — in-process pub/sub
// Zero infrastructure. Makes context boundaries observable.
import EventEmitter from 'eventemitter3';

// Event type definitions
interface DomainEvents {
  'identity:user-registered': { userId: string; email: string };
  'billing:subscription-changed': { workspaceId: string; newTier: string };
  'workspace:created': { workspaceId: string };
  'workspace:task-cap-reached': { workspaceId: string; tasksUsed: number };
  'source:signal-ingested': { sourceId: string; workspaceId: string; signalCount: number };
  'source:health-degraded': { sourceId: string; workspaceId: string };
  'briefing:compilation-requested': { workspaceId: string; briefingId: string };
  'briefing:ready': { workspaceId: string; briefingId: string };
  'briefing:failed': { workspaceId: string; briefingId: string; reason: string };
  'briefing:engaged': { workspaceId: string; briefingId: string; feedbackType: string };
  'notification:delivery-confirmed': { briefingId: string; channelId: string };
  'notification:delivery-failed': { briefingId: string; channelId: string; error: string };
  'priority:updated': { workspaceId: string };
}

// Singleton bus
export const domainBus = new EventEmitter<DomainEvents>();

// Usage in Source context:
// domainBus.emit('source:signal-ingested', { sourceId, workspaceId, signalCount });

// Usage in Briefing context (listener):
// domainBus.on('source:signal-ingested', async (data) => { ... });

// COMMENT CONVENTION:
// Every emit/on call includes: "// Domain Event: {EventName} — see domain-map.md"
```

---

## Irreversible vs Reversible Decisions

| Decision | Type | Rationale |
|----------|------|-----------|
| Behavioral memory schema (3-layer) | **Irreversible** | 90 days of accumulated user data is load-bearing |
| Multi-tenant isolation (workspace_id everywhere) | **Irreversible** | Retrofitting tenant isolation is a rewrite |
| OAuth token encryption (AES-256-GCM) | **Irreversible** | Cannot downgrade encryption |
| Billing tier structure (Trial/Solo/Pro) | **Irreversible** | Users on existing tiers expect stability |
| LLM model choice (Haiku/Sonnet) | Reversible | Config change via LiteLLM |
| Hosting region (Fly.io iad) | Reversible | Deploy to new region |
| Delivery channels (Telegram/email) | Reversible | Add channels without schema change |
| Monitoring tooling | Reversible | Swap providers freely |
| Clerk vs alternative auth | Reversible | ACL wrapper protects from vendor lock-in |
