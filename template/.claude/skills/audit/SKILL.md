---
name: audit
description: Systematic code analysis (READ-ONLY). Light mode for focused checks, Deep mode for full forensics with 6 parallel personas.
model: opus
---

# Audit — Systematic Code Analysis

READ-ONLY systematic analysis for finding patterns, inconsistencies, and issues.

**Activation:** `/audit`, `/audit {zone}`, `/audit deep`, "deep audit", "full audit"
**Output (Light):** `ai/audit/YYYY-MM-DD-{zone}.md`
**Output (Deep):** `ai/audit/deep-audit-report.md` (consolidated from 6 persona reports)

## When to Use

- Find patterns: "find all places where X"
- Consistency check: "is there anywhere left with Y?"
- Refactor-scan: "where else to update after Z"
- Security scan: "check for vulnerabilities"
- Coverage check: "what's not covered by tests"
- **Full forensics for retrofit:** "deep audit", from `/retrofit`

**Don't use:** Features → `/spark`, Bug fixes → `/spark`

## Principles

1. **READ-ONLY** — Never modify files (except reports in `ai/audit/`)
2. **Systematic** — ALL relevant files, not just obvious
3. **Zone-Aware** — Use zone prompt for focused analysis (Light mode)
4. **Inventory-First** — Deep mode starts with deterministic codebase scan (Phase 0)

---

## Mode Detection

Audit operates in two modes:

| Trigger | Mode | Description | Read Next |
|---------|------|-------------|-----------|
| `/audit`, `/audit {zone}`, "quick audit", "check code" | **Light** | Fast scan, single agent, zone-based | Continue below |
| From `/retrofit`, `/audit deep`, "deep audit", "full audit" | **Deep** | Full forensics, 6 parallel personas + synthesizer | `deep-mode.md` |

**Default:** Light (if unclear, ask user)

## Modules

| Module | When | Content |
|--------|------|---------|
| `deep-mode.md` | Mode = Deep | Phase 0 inventory + 6 personas + synthesis + gates |

**Flow:**
```
Light: SKILL.md (zones below)
Deep:  SKILL.md → deep-mode.md
```

---

## Light Mode — Zone Prompts

Quick-start templates for common audit scenarios. Copy, adapt, run.

### billing — Money Flow Audit

```
ZONE: billing
SCOPE: src/domains/billing/, tests/*billing*

CHECK:
□ Kopecks vs rubles — units consistent everywhere?
□ Transactions — all operations in try/except with rollback?
□ Balance — race conditions on parallel deductions?
□ Rounding — Decimal or float? (float = bug)
□ Negative balance — protection from going negative?
□ Audit trail — all money operations logged?

PATTERNS:
- `* 100`, `/ 100` — unit conversion
- `amount`, `balance`, `price` — money fields
- `transaction`, `charge`, `refund` — operations
```

### seller — LLM Agent Audit

```
ZONE: seller (SellerBot)
SCOPE: src/domains/seller/, src/config/prompts/

CHECK:
□ Prompt injection — user input doesn't go directly into prompt?
□ Token limits — truncation for long inputs?
□ Fallback — what if LLM doesn't respond / timeout?
□ Cost control — usage logged? Limits in place?
□ Prompt versioning — versions in separate files?
□ Temperature — determinism where needed (temp=0)?

PATTERNS:
- `openai.chat`, `completion` — LLM calls
- `system:`, `user:` — prompt construction
- `max_tokens`, `temperature` — LLM params
```

### buyer — FSM & UI Audit

```
ZONE: buyer (BuyerBot)
SCOPE: src/domains/buyer/, src/api/telegram/buyer/

CHECK:
□ FSM completeness — all states have handlers?
□ Dead-ends — any states without exit?
□ Callback orphans — all callback_data have handlers?
□ Back navigation — can return from any state?
□ Timeout handling — what if user silent for 24h?
□ Input validation — all user inputs validated?

PATTERNS:
- `state=`, `@router.message` — FSM handlers
- `callback_data=` — button callbacks
- `InlineKeyboardButton` — UI elements
```

### campaigns — Business Logic Audit

```
ZONE: campaigns
SCOPE: src/domains/campaigns/, src/domains/outreach/

CHECK:
□ Slot lifecycle — create → assign → complete → close?
□ Offer expiration — expired offers handled?
□ Double-booking — protection from duplicate assignments?
□ Status transitions — all transitions valid?
□ Notifications — buyer/seller notified of changes?
□ Metrics — conversion rates calculated?

PATTERNS:
- `slot`, `offer`, `campaign` — entities
- `status`, `state` — lifecycle
- `assign`, `complete`, `expire` — transitions
```

### tests — Test Coverage Audit

```
ZONE: tests
SCOPE: tests/, src/**/test_*.py

CHECK:
□ Coverage gaps — which modules < 80%?
□ Edge cases — negative scenarios covered?
□ Mocks vs real — too many mocks?
□ Flaky tests — random failures?
□ Test isolation — tests don't depend on each other?
□ Fixtures — reused or duplicated?

PATTERNS:
- `@pytest.mark.skip` — skipped tests (why?)
- `@pytest.fixture` — fixtures usage
- `mock.patch` — mocking patterns
- `assert` — assertion patterns
```

### migrations — Database Audit

```
ZONE: migrations
SCOPE: db/migrations/

CHECK:
□ Rollback — every migration reversible?
□ Data loss — DROP/DELETE without backup?
□ Indexes — large tables have indexes?
□ Foreign keys — constraints in place?
□ Default values — NOT NULL without DEFAULT?
□ One statement — one statement per file? (TECH-073)

PATTERNS:
- `DROP`, `DELETE`, `TRUNCATE` — destructive
- `ALTER TABLE` — schema changes
- `CREATE INDEX` — performance
- `FOREIGN KEY`, `REFERENCES` — integrity
```

### security — OWASP Audit

```
ZONE: security
SCOPE: entire codebase

CHECK:
□ SQL injection — raw queries with f-strings?
□ XSS — user input in HTML without escape?
□ Auth bypass — endpoints without auth check?
□ Secrets — hardcoded keys/passwords?
□ SSRF — user-controlled URLs in requests?
□ Rate limiting — protection from abuse?

PATTERNS:
- `f"SELECT`, `f"INSERT` — SQL injection risk
- `os.environ`, `getenv` — secrets handling
- `requests.get(url)` — SSRF risk
- `password`, `secret`, `key`, `token` — sensitive
```

### architecture — Structure Audit

```
ZONE: architecture
SCOPE: src/

CHECK:
□ Layer violations — api → domains → infra → shared?
□ Circular imports — A imports B imports A?
□ File size — files > 400 LOC?
□ Export bloat — __init__.py > 5 exports?
□ Legacy paths — imports from src/services/?
□ DRY violations — copy-paste code?

PATTERNS:
- `from src.services.` — legacy import
- `from src.db.` — legacy import
- `# TODO`, `# FIXME` — tech debt markers
```

## Usage

### Single Zone
```
/audit billing
```
→ Uses billing zone prompt, systematic search

### Custom Query
```
/audit "find all hardcoded URLs"
```
→ Custom search, full codebase

### Multi-Zone
```
/audit billing security
```
→ Runs both zone prompts, merged report

## Output

```yaml
status: complete
zone: billing | seller | custom
findings: N issues in M files
severity: X critical, Y warning, Z info
report: ai/audit/YYYY-MM-DD-{zone}.md (if saved)
recommendations: [actionable items]
```

## Report Template

```markdown
# Audit: {Zone/Topic}
**Date:** YYYY-MM-DD | **Scope:** {paths}

## Summary
- Issues: N (X critical, Y warning, Z info)
- Files: M affected

## Findings

| # | File | Line | Issue | Severity |
|---|------|------|-------|----------|
| 1 | path | 42 | desc | critical |

## Recommendations

### P0 (Immediate)
1. **[Action]** — [Why]

### P1 (Soon)
2. **[Action]** — [Why]

## Create Tasks?
- [ ] TECH-XXX: Fix pattern A
- [ ] BUG-XXX: Fix pattern B
```

## Integration

### Light Mode
| After Audit | Next Step |
|-------------|-----------|
| Found bugs | `/spark` per bug |
| Need refactoring | Create TECH spec |
| Security issue | Create SEC spec, escalate |
| Just reporting | Done |

### Deep Mode
| After Deep Audit | Next Step |
|-----------------|-----------|
| From `/retrofit` | `/architect` (retrofit mode — uses audit report as primary input) |
| Standalone | Create TECH/BUG specs for critical findings |
