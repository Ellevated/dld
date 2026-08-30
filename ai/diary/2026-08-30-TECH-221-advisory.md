# TECH-221 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/gate_ancestry.py:134 | new public `branch_state()` absent from `.claude/rules/dependencies.md` | resolved by PHASE 3 documenter (bdbd7e26) |
| scripts/vps/orchestrator_queue.py:1 | file sits at exactly 400/400 LOC — next edit breaks the limit | /spark a split before it must grow again |
| scripts/vps/tests/test_orchestrator_in_progress.py:443 | EC-6 stubs `_pueue_add`, so the real `{**os.environ, **env}` merge is unverified | moot: the flag is telemetry only (claude-runner.py passes a CLOSED env whitelist); the prompt self-detects via `git ls-remote` |
| .claude/skills/autopilot/worktree-setup.md:158 | "WHY origin/develop explicit" comment sits after the if/else, reads as if it governs both arms; autopilot-git.md correctly scoped it to the else | cosmetic |
