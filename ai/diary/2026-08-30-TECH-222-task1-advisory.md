# TECH-222 Task 1/9 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/tests/test_lifecycle.py:788 | Test file over the 600-LOC guideline (was already 730 before this spec) | Split into test_lifecycle_depends_on.py in a follow-up TECH — outside this spec's Allowed Files |
| .claude/rules/dependencies.md | Stale LOC counts (338/397) and still names the dead `_render_and_commit_backlog` | Refresh after TECH-222 merges — not in Allowed Files |
