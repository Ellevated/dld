# Feature Spec Template

Template for creating feature specifications via Spark.

---

## File Naming

```
ai/features/{TYPE}-{ID}-{YYYY-MM-DD}-{slug}.md
```

Examples:
- `FTR-182-2026-01-05-user-authentication.md`
- `BUG-045-2026-01-05-login-crash-fix.md`
- `REFACTOR-220-2026-01-05-split-user-service.md`

---

## Full Template

```markdown
# {Type}: [{ID}] {Title}

**Status:** draft | **Priority:** P0/P1/P2/P3 | **Date:** YYYY-MM-DD

## Зачем (RU)

{1-2 предложения: зачем это нужно пользователю/бизнесу}

## Контекст (RU)

{Текущее состояние, что не работает или чего не хватает}

---

## Scope

**In scope:**
- {what will be done}
- {what will be done}

**Out of scope:**
- {what will NOT be done}
- {explicitly excluded}

---

## Allowed Files

**ONLY these files may be modified during implementation:**

| # | File | Action | Reason |
|---|------|--------|--------|
| 1 | `src/domains/X/service.py` | modify | Add new method |
| 2 | `src/domains/X/models.py` | modify | Add new model |
| 3 | `src/domains/X/service_test.py` | modify | Add tests |

**New files allowed:**
| # | File | Reason |
|---|------|--------|
| 1 | `src/domains/X/new_feature.py` | New module for feature |

**FORBIDDEN:** All other files. Autopilot must refuse changes outside this list.

---

## Approaches

### Approach 1: {Name}

**Source:** {URL or "internal analysis"}

**Summary:** {2-3 sentences}

**Pros:**
- {advantage 1}
- {advantage 2}

**Cons:**
- {disadvantage 1}

### Approach 2: {Name}

{same structure}

### Selected: Approach {N}

**Rationale:** {why this approach was chosen}

---

## Design

### User Flow

1. User does X
2. System responds with Y
3. User sees Z

### Architecture

{ASCII diagram or description of component interaction}

### DB Changes

| Table | Change | Fields |
|-------|--------|--------|
| `users` | add column | `verified_at: timestamp` |
| `sessions` | new table | `id, user_id, token, expires_at` |

### API Changes

```python
# New endpoint
POST /api/v1/auth/login
Request: { "email": str, "password": str }
Response: { "token": str, "expires_at": datetime }
```

---

## Implementation Plan

### Task 1: {Name}

**Time:** ~X minutes
**Files:**
- Modify: `src/domains/X/models.py`
- Test: `src/domains/X/models_test.py`

**Steps:**
1. Add `UserSession` model
2. Add `test_user_session_creation`
3. Run tests

**Acceptance:**
- [ ] Model has all required fields
- [ ] Test passes

### Task 2: {Name}

{same structure}

### Execution Order

Task 1 → Task 2 → Task 3

### Dependencies

- Task 2 depends on Task 1 (needs model to exist)
- Task 3 can run in parallel with Task 2

---

## UI Event Completeness

*(Required for UI features)*

| Producer | callback_data | Consumer | In Allowed Files? |
|----------|---------------|----------|-------------------|
| `auth_keyboard()` | `auth:login` | `cb_auth_login()` | `handlers.py` ✓ |

**Rule:** Every callback_data MUST have a handler in Allowed Files.

---

## Flow Coverage Matrix

| # | User Flow Step | Covered by Task | Status |
|---|----------------|-----------------|--------|
| 1 | User clicks Login | Task 1 | ✓ |
| 2 | Form appears | Task 2 | ✓ |
| 3 | User submits | Task 3 | ✓ |
| 4 | Token stored | Task 4 | ✓ |

**Gaps:** None (all steps covered)

---

## Definition of Done

### Functional
- [ ] Feature works as specified
- [ ] All tasks completed
- [ ] User flow is complete (no dead-ends)

### Technical
- [ ] Tests pass (`./test fast`)
- [ ] No regressions
- [ ] Files stay within LOC limits
- [ ] No import violations

### Documentation
- [ ] Code is self-documenting
- [ ] Complex logic has comments

---

## Autopilot Log

*(Filled by Autopilot during execution)*

### Task 1/3: {Name} — {date}
- Coder: completed (2 files)
- Tester: passed (15 tests)
- Documenter: n/a
- Reviewer: approved
- Commit: abc1234

### Task 2/3: {Name} — {date}
{same structure}
```

---

## Minimal Template

For quick specs (bugs, small features):

```markdown
# {Type}: [{ID}] {Title}

**Status:** draft | **Priority:** P1 | **Date:** YYYY-MM-DD

## Problem
{What's broken or missing}

## Solution
{How to fix it}

## Allowed Files
1. `src/domains/X/service.py` — fix bug
2. `src/domains/X/service_test.py` — add regression test

## Tasks
1. Add failing test that reproduces bug
2. Fix the bug
3. Verify test passes

## DoD
- [ ] Bug fixed
- [ ] Regression test added
- [ ] `./test fast` passes
```

---

## Checklist Before Saving Spec

Spark must verify:

- [ ] ID determined by protocol (not guessed)
- [ ] File created in `ai/features/`
- [ ] `## Allowed Files` section exists
- [ ] All UI callbacks have handlers (if UI feature)
- [ ] Flow coverage complete (no gaps)
- [ ] Status is `draft` (not `queued`)
- [ ] Backlog row added

---

## Common Mistakes

### Missing Allowed Files

```markdown
# ❌ BAD: No Allowed Files
## Tasks
1. Add auth service
2. Add tests

# ✅ GOOD: Explicit Allowed Files
## Allowed Files
1. `src/domains/auth/service.py` — new
2. `src/domains/auth/service_test.py` — new
```

### Orphan Callbacks

```markdown
# ❌ BAD: Callback without handler
## Tasks
1. Add button with callback_data="login"
# Where is the handler?

# ✅ GOOD: Complete UI mapping
## UI Event Completeness
| Producer | callback | Consumer | File |
|----------|----------|----------|------|
| `login_btn()` | `auth:login` | `cb_login()` | `handlers.py` ✓ |
```

### Vague Tasks

```markdown
# ❌ BAD: Vague
### Task 1: Add authentication

# ✅ GOOD: Specific
### Task 1: Add UserSession model
**Files:** src/domains/auth/models.py
**Steps:**
1. Create UserSession dataclass
2. Add fields: id, user_id, token, expires_at
```
