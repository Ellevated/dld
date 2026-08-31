# TECH-220 Task 2+3/5 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/gate-daemon.py:398 | 398 LOC — 2 lines from the 400 ceiling | Next change here must split the file first; do not add to it |
| scripts/vps/callback_sync.py:280, callback_dispatch.py:84,112, orchestrator_queue.py:116 | 4 `except Exception:` without re-raise, flagged by pre-review-check | Pre-existing (identical against merge-base 35cec2ca); they implement callback's "always exit 0" contract. Left untouched under Scope Protection |
