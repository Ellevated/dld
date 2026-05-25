# Target inventory: callback/lifecycle/orchestrator contour
Generated: 2026-05-23T17:42:33+03:00

## Core modules
- scripts/vps/callback.py — 1374 LOC
- scripts/vps/lifecycle.py — 602 LOC
- scripts/vps/orchestrator.py — 667 LOC
- scripts/vps/db.py — 531 LOC
- scripts/vps/event_writer.py — 167 LOC
- scripts/vps/run-agent.sh — 76 LOC
- scripts/vps/claude-runner.py — 362 LOC
- scripts/vps/render_backlog.py — 213 LOC
- scripts/vps/marker_utils.py — MISSING
- scripts/vps/migrate_backlog_to_lifecycle.py — 246 LOC

## Integration tests
- tests/integration/test_callback_already_merged.py — 252 LOC
- tests/integration/test_callback_circuit_breaker.py — 313 LOC
- tests/integration/test_callback_feature_branch.py — 228 LOC
- tests/integration/test_callback_no_impl_demote.py — 214 LOC
- tests/integration/test_callback_status_sync.py — 430 LOC

## Unit tests
- scripts/vps/tests/conftest.py
- scripts/vps/tests/__pycache__
- scripts/vps/tests/requirements-dev.txt
- scripts/vps/tests/run-tests.sh
- scripts/vps/tests/test_callback.py
- scripts/vps/tests/test_db.py
- scripts/vps/tests/test_lifecycle.py
- scripts/vps/tests/test_migrate_backlog.py
- scripts/vps/tests/test_orchestrator_git_pull.py
- scripts/vps/tests/test_orchestrator_lifecycle.py
- scripts/vps/tests/test_orchestrator.py
- scripts/vps/tests/test_render_backlog.py

## ADR references
- .claude/rules/architecture.md (ADR-018, 021, 022, 023, 024 + TECH-166..177)

## Specs in this refactoring wave (2026-05)
- ai/features/ARCH-186-2026-05-16-orchestrator-lifecycle-file-sot.md
- ai/features/ARCH-187-2026-05-20-lifecycle-write-identity-enforcement.md
- ai/features/BUG-185-2026-05-15-autostash-callback-marker-overwrite.md
- ai/features/BUG-188-2026-05-20-claude-runner-post-result-exception-false-fail.md
- ai/features/TECH-166-2026-05-01-callback-implementation-guard.md
- ai/features/TECH-176-2026-05-04-guard-already-merged-detection.md
- ai/features/TECH-177-2026-05-04-callback-cross-spec-id-mention.md

## Hooks
- .claude/hooks/pre-commit-lifecycle-guard.mjs — 64 LOC
- .git-hooks/pre-commit — 40 LOC
- scripts/hooks/pre-commit — 58 LOC
