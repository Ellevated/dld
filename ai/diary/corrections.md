# Corrections Diary

## 2026-02-16: During Bug Hunt ADR-008 test

**Context:** Testing `run_in_background: true` pattern in Bug Hunt pipeline
**I did:** Edited `template/.claude/` files, then ran test
**User corrected:** "мне кажется у тебя просто какой то кривой скил загрузился?"
**Why:** Template-sync rule: DLD uses `.claude/` at runtime, not `template/.claude/`. Editing template without syncing = test on old code.
**Rule:** ALWAYS sync template → .claude/ BEFORE testing. Verify with `grep` that the change is in the ACTIVE file.
