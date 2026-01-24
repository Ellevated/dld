---
name: audit
description: Systematic code analysis (READ-ONLY) with zone-specific prompts
model: opus
---

# Audit — Systematic Code Analysis

READ-ONLY systematic analysis for finding patterns, inconsistencies, and issues.

**Activation:** `audit`, `audit {zone}`

## When to Use

- Find patterns: "найди все места где X"
- Consistency check: "нигде не осталось Y?"
- Refactor-scan: "где ещё обновить после Z"
- Security scan: "проверь на уязвимости"
- Coverage check: "что не покрыто тестами"

**Don't use:** Features → `/spark`, Bug fixes → `/spark`

## Principles

1. **READ-ONLY** — Never modify files (except report in `ai/audit/`)
2. **Systematic** — ALL relevant files, not just obvious
3. **Zone-Aware** — Use zone prompt for focused analysis

## Zone Prompts

Quick-start templates for common audit scenarios. Copy, adapt, run.

### billing — Money Flow Audit

```
ZONE: billing
SCOPE: src/domains/billing/, tests/*billing*

CHECK:
□ Копейки vs рубли — единицы везде консистентны?
□ Транзакции — все операции в try/except с rollback?
□ Баланс — race conditions при параллельных списаниях?
□ Округление — Decimal или float? (float = bug)
□ Negative balance — защита от минуса?
□ Audit trail — логируются ли все money operations?

PATTERNS:
- `* 100`, `/ 100` — конверсия единиц
- `amount`, `balance`, `price` — money fields
- `transaction`, `charge`, `refund` — operations
```

### seller — LLM Agent Audit

```
ZONE: seller (SellerBot)
SCOPE: src/domains/seller/, src/config/prompts/

CHECK:
□ Prompt injection — user input не попадает напрямую в prompt?
□ Token limits — есть ли truncation для длинных inputs?
□ Fallback — что если LLM не отвечает / timeout?
□ Cost control — логируется ли usage? Есть ли лимиты?
□ Prompt versioning — версии в отдельных файлах?
□ Temperature — детерминизм где нужен (temp=0)?

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
□ FSM completeness — все states имеют handlers?
□ Dead-ends — есть ли states без выхода?
□ Callback orphans — все callback_data имеют handlers?
□ Back navigation — можно ли вернуться из любого state?
□ Timeout handling — что если user молчит 24h?
□ Input validation — все user inputs валидируются?

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
□ Offer expiration — просроченные offers обрабатываются?
□ Double-booking — защита от duplicate assignments?
□ Status transitions — валидны ли все переходы?
□ Notifications — buyer/seller уведомляются о changes?
□ Metrics — считаются ли conversion rates?

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
□ Coverage gaps — какие modules < 80%?
□ Edge cases — негативные сценарии покрыты?
□ Mocks vs real — не слишком ли много mocks?
□ Flaky tests — есть ли random failures?
□ Test isolation — tests не зависят друг от друга?
□ Fixtures — переиспользуются или дублируются?

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
□ Rollback — каждая миграция reversible?
□ Data loss — DROP/DELETE без backup?
□ Indexes — большие таблицы имеют индексы?
□ Foreign keys — constraints на месте?
□ Default values — NOT NULL без DEFAULT?
□ One statement — один statement на файл? (TECH-073)

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
□ SQL injection — raw queries с f-strings?
□ XSS — user input в HTML без escape?
□ Auth bypass — endpoints без auth check?
□ Secrets — hardcoded keys/passwords?
□ SSRF — user-controlled URLs в requests?
□ Rate limiting — protection от abuse?

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
/audit "найди все hardcoded URLs"
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

| After Audit | Next Step |
|-------------|-----------|
| Found bugs | `/spark` per bug |
| Need refactoring | Create TECH spec |
| Security issue | Create SEC spec, escalate |
| Just reporting | Done |
