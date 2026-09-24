# TECH-226 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/fleet_pause.py:47 | active_pause returns the marker dict without checking until_iso/rate_limit_type; readers must use .get() (all three do) | validate keys in active_pause if a fourth reader appears |
| scripts/vps/tests/test_fleet_pause.py:138 | test_on_rejected_swallows_notify_exception does not assert the marker was written, although its comment says so | add `assert fleet_pause.active_pause(now=now)` |
| scripts/vps/orchestrator_queue.py:92 | pre-existing `except Exception: pass` (a68035b5, 2026-07-28) flagged by pre-review-check | out of scope; leave to a cleanup spec |
| scripts/vps/callback.py:113,362 | pre-existing `except Exception:` (6c18d020, 2026-03-18) flagged by pre-review-check | out of scope; leave to a cleanup spec |
| scripts/vps/.rate-limited-until | marker (and .lock/.tmp) not in .gitignore — shows as untracked in the VPS main checkout while a pause is active | one .gitignore line in a follow-up (.gitignore was not in Allowed Files) |
