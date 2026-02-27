# Spec: FTR-078 User notification preferences

## Scope
Allow users to configure which notifications they receive and through which channels (email, push, in-app).

## Allowed Files
1. `src/domains/notifications/preferences.py` — NEW: preference model and service
2. `src/api/notifications.py` — NEW: REST endpoints for preferences
3. `src/api/main.py` — MODIFY: register notifications router
4. `db/migrations/005_notification_preferences.sql` — NEW: preferences table
5. `tests/test_notification_preferences.py` — NEW: preference tests

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Type | Source | Priority |
|----|----------|-------|----------|------|--------|----------|
| EC-1 | Get default preferences | GET /notifications/preferences (new user) | All channels enabled | deterministic | design | P0 |
| EC-2 | Update preference | PATCH /notifications/preferences {"email": false} | email disabled, others unchanged | deterministic | user | P0 |
| EC-3 | Invalid channel | PATCH with {"sms": true} | 400 error (sms not supported) | deterministic | devil | P1 |

### Coverage Summary
- Deterministic: 3 | Total: 3

### TDD Order
1. EC-1 -> default preferences
2. EC-2 -> update single preference
3. EC-3 -> validation
