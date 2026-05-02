# DLD Backlog

## 🎯 Цели

| Milestone | Цель | Дедлайн | Метрика |
|-----------|------|---------|---------|
| **LAUNCH** | Первый публичный релиз | 1 неделя | 1K stars |
| **GROWTH** | Community traction | 1 месяц | 10K stars, собес Anthropic |
| **STANDARD** | Стандарт де-факто | 1 год | O-1 виза |

---

## 🚀 LAUNCH BLOCKERS (без этого не запускаемся)

| ID | Задача | Status | Impact | Feature.md |
|----|--------|--------|--------|------------|
| TECH-063 | Publish create-dld to NPM | done | ⭐⭐⭐⭐⭐ | [spec](features/TECH-063-2026-02-01-publish-npm-package.md) |
| TECH-060 | Create Demo GIF for README | done | ⭐⭐⭐⭐⭐ | [spec](features/TECH-060-2026-02-01-demo-gif-creation.md) |
| TECH-061 | Fix Discord Placeholder Links | done | ⭐⭐⭐⭐ | [spec](features/TECH-061-2026-02-01-discord-placeholder-fix.md) |
| TECH-062 | Sync template/.claude with root .claude | done | ⭐⭐⭐ | [spec](features/TECH-062-2026-02-01-sync-template-root.md) |
| TECH-076 | Structural Smoke Test for create-dld | done | ⭐⭐⭐⭐⭐ | [spec](features/TECH-076-2026-02-02-e2e-create-dld-test.md) |

---

## 📈 GROWTH (после launch)

| ID | Задача | Status | Impact | Feature.md |
|----|--------|--------|--------|------------|
| GROWTH-001 | HackerNews launch execution | blocked | ⭐⭐⭐⭐⭐ | [draft](features/TECH-016-2026-01-24-hackernews-post.md) |
| GROWTH-002 | Reddit r/programming + r/MachineLearning | blocked | ⭐⭐⭐⭐ | [draft](features/TECH-018-2026-01-24-reddit-posts.md) |
| GROWTH-003 | Twitter thread launch | blocked | ⭐⭐⭐ | [draft](features/TECH-017-2026-01-24-twitter-thread.md) |
| GROWTH-004 | Product Hunt launch | blocked | ⭐⭐⭐⭐ | [draft](features/TECH-033-2026-01-26-producthunt-assets.md) |
| GROWTH-005 | Dev.to article publish | blocked | ⭐⭐⭐ | [draft](features/TECH-029-2026-01-26-devto-article.md) |
| GROWTH-006 | YouTube tutorial publish | blocked | ⭐⭐⭐ | [draft](features/TECH-031-2026-01-26-youtube-script.md) |

---

## 🔧 INTERNAL (не влияет на stars, делать после GROWTH)

| ID | Задача | Status | Priority | Feature.md |
|----|--------|--------|----------|------------|
| TECH-129 | Multi-Agent ADR Migration — Zero-Read Pattern для pipeline-скиллов | done | P1 | [spec](features/TECH-129-2026-02-18-multi-agent-adr-migration.md) |
| TECH-055 | Review Pipeline Hardening (bug fix + enhancements) | done | P1 | [spec](features/TECH-055-2026-02-01-auto-review-agent.md) |
| TECH-057 | Semantic Skill Auto-Selection | done | P3 | [spec](features/TECH-057-2026-02-01-semantic-skill-triggers.md) |
| TECH-058 | Split spark/SKILL.md into modules | done | P3 | [spec](features/TECH-058-2026-02-01-split-spark-skill.md) |
| TECH-065 | Enhanced MCP Integration | done | P1 | [spec](features/TECH-065-2026-02-02-enhanced-mcp-integration.md) |
| TECH-066 | Tiered User Experience (LLM-First Install) | done | P1 | [spec](features/TECH-066-2026-02-02-tiered-user-experience.md) |
| TECH-067 | Planner Mandatory Drift Check | done | P1 | [spec](features/TECH-067-2026-02-02-planner-mandatory-drift-check.md) |
| TECH-068 | Native Language Skill Triggers | done | P2 | [spec](features/TECH-068-2026-02-02-native-language-skill-triggers.md) |
| TECH-069 | Ralph Loop Autopilot (Fresh Context per Spec) | done | P1 | [spec](features/TECH-069-2026-02-02-ralph-loop-autopilot.md) |
| TECH-070 | Sync LOC Limits Across Documentation | done | P2 | [spec](features/TECH-070-2026-02-02-loc-limits-sync.md) |
| TECH-071 | Spark Modules Cleanup (dedupe + dead refs) | done | P2 | [spec](features/TECH-071-2026-02-02-spark-modules-cleanup.md) |
| TECH-072 | LLM-First Onboarding with Diff Preview | done | P1 | [spec](features/TECH-072-2026-02-02-llm-first-onboarding.md) |
| TECH-073 | Sync Autopilot Plan Policy (template ← root) | done | P2 | [spec](features/TECH-073-2026-02-02-sync-autopilot-plan-always.md) |
| TECH-074 | Sync Root .claude from Template | done | P1 | [spec](features/TECH-074-2026-02-02-sync-root-claude-from-template.md) |
| TECH-075 | Template-Root Sync Enforcement System | done | P0 | [spec](features/TECH-075-2026-02-02-template-sync-enforcement.md) |
| TECH-077 | mypy type checking in CI | done | P3 | [spec](features/TECH-077-2026-02-02-mypy-type-checking-ci.md) |
| TECH-078 | Security scanning (dependabot) | done | P3 | [spec](features/TECH-078-2026-02-02-dependabot-security-scanning.md) |
| TECH-081 | Template Placeholder Fixes (localization, CLAUDE.md, documenter) | done | P2 | [spec](features/TECH-081-2026-02-02-localization-example.md) |
| BUG-082 | Autopilot loop mode ambiguous git push docs | done | P1 | [spec](features/BUG-082-2026-02-08-autopilot-loop-push-ambiguity.md) |
| BUG-083 | Bug Hunt: DLD Framework Full Audit (6 sub-specs) | done | P0 | [spec](features/BUG-083/BUG-083.md) |
| BUG-084 | Bug Hunt: Template Framework Deep Audit (29 sub-specs) | done | P1 | [spec](features/BUG-084/BUG-084.md) |
| FTR-085 | Release Skill — automated CHANGELOG + README + docs update | done | P1 | [spec](features/FTR-085-2026-02-14-release-skill.md) |
| BUG-086 | Bug Hunt Pipeline Consistency Fixes (paths, IDs, YAML resilience) | done | P1 | [spec](features/BUG-086-2026-02-15-bughunt-pipeline-consistency.md) |
| TECH-087 | Simplify Bug Hunt — remove embedded TOC/TRIZ framework agents | done | P2 | [spec](features/TECH-087-2026-02-15-simplify-bughunt-remove-frameworks.md) |
| FTR-088 | /triz skill — system-level diagnostics with TOC + TRIZ | done | P2 | [spec](features/FTR-088-2026-02-15-triz-skill-system-diagnostics.md) |
| FTR-089 | /diagram skill — professional Excalidraw diagram generation | done | P1 | [spec](features/FTR-089-2026-02-15-diagram-skill.md) |
| BUG-090 | Bug Hunt Pipeline Self-Check — 10 consistency fixes | done | P1 | [spec](features/BUG-090-2026-02-15-bughunt-selfcheck-fixes.md) |
| BUG-091 | /triz Pipeline Self-Check — 9 consistency fixes | done | P1 | [spec](features/BUG-091-2026-02-15-triz-selfcheck-fixes.md) |
| BUG-092 | Spark + Autopilot + Council Self-Check — 13 consistency fixes | done | P1 | [spec](features/BUG-092-2026-02-15-spark-autopilot-council-selfcheck.md) |
| BUG-093 | Bug Hunt Pipeline Self-Check Round 2 — 9 fixes | done | P1 | closed: superseded by BUG-094 + TECH-105 + TECH-116 |
| BUG-094 | Bug Hunt IPC Rewrite — file-based to response-based | done | P0 | [spec](features/BUG-094-2026-02-16-bughunt-ipc-rewrite.md) |
| BUG-096 | Security Hardening — Command Blocklist & Path Validation | done | P0 | closed: covered by BUG-103 + BUG-118 (both done) |
| BUG-097 | Test Infrastructure for Hooks | done | P0 | [spec](features/BUG-097-2026-02-17-test-infrastructure-hooks.md) |
| BUG-098 | Reliability & Fail-Safety Improvements | done | P1 | closed: covered by BUG-120 (done) |
| BUG-099 | Observability & Diagnostic Visibility | done | P1 | [spec](features/BUG-099-2026-02-17-observability-hooks.md) |
| BUG-100 | Architecture & Extensibility | done | P2 | [spec](features/BUG-100-2026-02-17-architecture-extensibility-hooks.md) |
| BUG-102 | Protocol Bugs — Wrong Hook Output Format | done | P0 | [spec](features/BUG-102.md) |
| BUG-103 | Security Bypasses — Regex Gaps in pre-bash | done | P1 | [spec](features/BUG-103.md) |
| BUG-104 | Logic & Consistency — Paths, LOC, Patterns | done | P2 | [spec](features/BUG-104.md) |
| TECH-105 | Flatten Bug Hunt Pipeline — Remove Orchestrator | done | P1 | [spec](features/TECH-105-2026-02-16-flatten-bughunt-pipeline.md) |
| TECH-116 | Background ALL Bug Hunt Steps — Fix Context Crash (ADR-009) | done | P0 | [spec](features/TECH-116-2026-02-17-background-all-bughunt-steps.md) |
| BUG-107 | PLPilot: Payment & Billing Financial Safety (7 findings) | done | P0 | [spec](features/BUG-107.md) |
| BUG-108 | PLPilot: Subscription Upgrade Flow (6 findings) | done | P0 | [spec](features/BUG-108.md) |
| BUG-109 | PLPilot: React Hook & State Management Races (7 findings) | done | P1 | closed: PLPilot project, not DLD |
| BUG-110 | PLPilot: Date/Time Calculation Bugs (7 findings) | done | P1 | closed: PLPilot project, not DLD |
| BUG-111 | PLPilot: Financial Calculation & Currency Bugs (6 findings) | done | P1 | closed: PLPilot project, not DLD |
| BUG-112 | PLPilot: Authorization & Access Control (5 findings) | done | P0 | [spec](features/BUG-112.md) |
| BUG-113 | PLPilot: Error Handling & UX Dead Ends (8 findings) | done | P2 | closed: PLPilot project, not DLD |
| BUG-114 | PLPilot: AI Feature Safety & Rate Limiting (4 findings) | done | P2 | closed: PLPilot project, not DLD |
| BUG-118 | Hooks: Command Detection Gaps (glob permissiveness + git commit substring) | done | P1 | [spec](features/BUG-118-command-detection-gaps.md) |
| BUG-119 | Hooks: File Classification Bugs (countLines off-by-one + isTestFile patterns) | done | P2 | [spec](features/BUG-119-file-classification-bugs.md) |
| BUG-120 | Hooks: Robustness & Code Quality (6 hardening fixes) | done | P2 | [spec](features/BUG-120-robustness-code-quality.md) |
| TECH-130 | Structured Eval Criteria in Spec Template | done | P1 | [spec](features/TECH-130-2026-02-22-structured-eval-criteria.md) |
| TECH-131 | Devil Scout Structured Eval Assertions | done | P1 | [spec](features/TECH-131-2026-02-22-devil-structured-assertions.md) |
| TECH-132 | Regression Flywheel — Auto-Generate Regression Tests | done | P1 | [spec](features/TECH-132-2026-02-22-regression-flywheel.md) |
| FTR-133 | LLM-as-Judge Eval Type for Tester Agent | done | P2 | [spec](features/FTR-133-2026-02-22-llm-as-judge-eval.md) |
| FTR-134 | Agent Prompt Eval Suite | done | P2 | [spec](features/FTR-134-2026-02-22-agent-prompt-eval-suite.md) |
| FTR-135 | API Version Endpoint (E2E Pipeline Test) | done | P2 | [spec](features/FTR-135-2026-02-22-api-version-endpoint.md) |
| TECH-136 | Bug Hunt Eval Criteria (ADR-012 Compliance) | done | P1 | [spec](features/TECH-136-2026-02-22-bughunt-eval-criteria.md) |
| FTR-137 | Deterministic DLD Upgrade Skill (/upgrade) | done | P1 | [spec](features/FTR-137-2026-02-26-upgrade-skill.md) |
| TECH-138 | Upgrade: INFRASTRUCTURE category (stop self-overwrite) | done | P0 | [spec](features/TECH-138-2026-02-28-upgrade-infrastructure-category.md) |
| TECH-139 | Upgrade: Protect hooks.config.mjs | done | P0 | [spec](features/TECH-139-2026-02-28-upgrade-protect-hooks-config.md) |
| TECH-140 | Upgrade: Git stash backup + post-apply validation | done | P0 | [spec](features/TECH-140-2026-02-28-upgrade-backup-rollback.md) |
| TECH-141 | Upgrade: Contract specification (document) | done | P1 | [spec](features/TECH-141-2026-02-28-upgrade-contract.md) |
| TECH-142 | Upgrade: Deprecation manifest + zombie detection | done | P2 | [spec](features/TECH-142-2026-02-28-upgrade-deprecation-manifest.md) |
| TECH-143 | Upgrade: CI smoke tests | done | P1 | [spec](features/TECH-143-2026-02-28-upgrade-ci-tests.md) |
| TECH-144 | Clean DLD-specific gitignore rules from template | done | P1 | [spec](features/TECH-144-2026-03-02-clean-gitignore-rules-template.md) |
| TECH-145 | Upgrade skill-writer → skill-creator (Anthropic upstream parity) | done | P1 | [spec](features/TECH-145-2026-03-08-upgrade-skill-creator.md) |
| FTR-146 | Multi-Project Orchestrator Phase 1 (Pueue + Telegram Bot + SQLite) | done | P0 | [spec](features/FTR-146-2026-03-10-multi-project-orchestrator-phase1.md) |
| FTR-147 | Multi-Project Orchestrator Phase 2: Architecture & Reliability | done | P0 | [spec](features/FTR-147-2026-03-10-multi-project-orchestrator-phase2.md) |
| FTR-148 | Multi-Project Orchestrator Phase 3: Functionality & Multi-Provider | done | P1 | [spec](features/FTR-148-2026-03-10-multi-project-orchestrator-phase3.md) |
| FTR-149 | Orchestrator Cycle v2: Inbox-Centric Architecture | done | P0 | [spec](features/FTR-149-2026-03-12-orchestrator-cycle-v2.md) |
| TECH-150 | Reflect Synthesis: Shell Script Safety Rules + Process ADRs | done | P2 | [spec](features/TECH-150-2026-03-12-reflect-synthesis.md) |
| BUG-121 | Orchestrator Post-Autopilot Tail Duplication + Broken Phase Ownership | draft | P0 | [spec](features/BUG-121-2026-03-16-orchestrator-post-autopilot-phase-ownership.md) |
| BUG-152 | Agent SDK venv сломан — fake bash wrapper вместо реального venv | done | P0 | [spec](features/BUG-152-2026-03-17-venv-sdk-broken.md) |
| TECH-151 | Orchestrator North-Star Alignment (draft→queued, remove dead code, inbox invariant) | done | P0 | [spec](features/TECH-151-2026-03-17-orchestrator-north-star-alignment.md) |
| TECH-153 | AI-First Economic Model — replace human-centric effort with Impact+Risk | done | P1 | [spec](features/TECH-153-2026-03-17-ai-first-economic-model.md) |
| TECH-154 | DLD Cycle E2E Reliability — First Full Pass (QA spec path, reflect, artifact-scan) | done | P0 | [spec](features/TECH-154-2026-03-18-cycle-e2e-reliability.md) |
| BUG-155 | DLD Cycle E2E Reliability v2 — Three Gap Closure + Smoke Test | done | P0 | [spec](features/BUG-155-2026-03-18-cycle-e2e-reliability-v2.md) |
| TECH-156 | Silence intermediate Telegram notifications during cycle (OpenClaw handles) | done | P1 | [spec](features/TECH-156-2026-03-18-silence-intermediate-notifications.md) |
| TECH-157 | Immediate OpenClaw wake after pending-event write (eliminate 5-min cron lag) | done | P1 | [spec](features/TECH-157-2026-03-18-openclaw-immediate-wake.md) |
| BUG-158 | QA dispatch fails for inbox tasks (no spec file) — add TASK_LABEL guard | done | P1 | closed: band-aid, superseded by BUG-159 |
| BUG-159 | QA resolves real spec_id for inbox tasks (multi-layer resolution) | done | P1 | closed: superseded by ARCH-161 (callback.py has multi-layer resolution) |
| BUG-160 | Fix broken OpenClaw wake in pueue-callback.sh (timeout + missing --text) | done | P1 | closed: superseded by ARCH-161 (event_writer.py has 30s timeout + --text) |
| ARCH-161 | Orchestrator Radical Rewrite — Python + North Star (delete Telegram, rewrite bash→Python) | done | P1 | [spec](features/ARCH-161-2026-03-18-orchestrator-radical-rewrite.md) |
| BUG-162 | Orphan Slot Watchdog — release stale compute_slots after crash/restart | done | P1 | [spec](features/BUG-162-2026-03-19-orphan-slot-watchdog.md) |
| BUG-163 | Fix event_writer wake_openclaw() blocking callback 23s (timeout 30→5, log DEBUG) | done | P1 | [spec](features/BUG-163-2026-03-19-event-writer-wake-timeout.md) |
| BUG-164 | Fix callback.py pueue socket mismatch — read agent output from log files + DB | done | P0 | [spec](features/BUG-164-2026-03-20-callback-pueue-socket-mismatch.md) |
| TECH-149 | Deterministic Worktree Cleanup After Merge | done | P1 | [spec](features/TECH-149-2026-03-25-worktree-cleanup.md) |
| TECH-165 | Anthropic Pipeline Optimization (SDK 0.1.48→0.1.63 + model routing + observability) | done | P1 | [spec](features/TECH-165-2026-04-18-anthropic-pipeline-optimization.md) |
| TECH-166 | Callback implementation guard — git-diff проверка allowed files перед mark-done (закрывает дыру с FTR-896 false-done) | done | P1 | [spec](features/TECH-166-2026-05-01-callback-implementation-guard.md) |
| TECH-167 | Spark canonical `## Allowed Files` section + emit-time linter (R1, корень format-drift'а) | done | P0 | [spec](features/TECH-167-2026-05-02-spark-canonical-allowed-files.md) |
| TECH-168 | Callback test suite — unit + integration + regression corpus (R0, защита от silent regression) | done | P0 | [spec](features/TECH-168-2026-05-02-callback-test-suite.md) |
| TECH-169 | Orchestrator circuit-breaker on mass-demote (>3 demotes/10min → pause + alert) | blocked | P0 | [spec](features/TECH-169-2026-05-02-orchestrator-circuit-breaker.md) |
| TECH-170 | Implementation guard видит feature-branch коммиты (`git log --all`) | done | P1 | [spec](features/TECH-170-2026-05-02-guard-feature-branch-awareness.md) |
| TECH-171 | Guard structured audit log + daily Telegram digest | done | P1 | [spec](features/TECH-171-2026-05-02-guard-structured-audit-log.md) |
| TECH-172 | Single Status write path — callback единственный writer, autopilot не трогает | done | P1 | [spec](features/TECH-172-2026-05-02-single-status-write-path.md) |
| TECH-173 | Rewrite `dld-orchestrator.md` — single source of truth + runbook + diagram | done | P1 | [spec](features/TECH-173-2026-05-02-orchestrator-docs-rewrite.md) |
| TECH-174 | Manual spec verification protocol + spec_verify.py + operator.py CLI | queued | P2 | [spec](features/TECH-174-2026-05-02-manual-verification-protocol.md) |
| TECH-175 | Spark spec template hardening — DO-NOT-REMOVE markers + schema versioning | queued | P2 | [spec](features/TECH-175-2026-05-02-spark-spec-template-hardening.md) |

---

## ✅ DONE (58 tasks)

<details>
<summary>Completed tasks (click to expand)</summary>

| ID | Задача | Feature.md |
|----|--------|------------|
| TECH-001 | Split autopilot.md into modules | [TECH-001](features/TECH-001-split-autopilot.md) |
| TECH-002 | Remove hardcode from template | ai/idea/tasks-breakdown.md |
| TECH-003 | Clean CLAUDE.md template | [TECH-003](features/TECH-003-2026-01-24-clean-claude-md-template.md) |
| TECH-004 | Add MCP setup instructions | [TECH-004](features/TECH-004-2026-01-24-mcp-setup-instructions.md) |
| TECH-005 | Add hooks README | [TECH-005](features/TECH-005-2026-01-24-hooks-readme.md) |
| TECH-006 | GitHub community files | [TECH-006](features/TECH-006-2026-01-24-github-community-files.md) |
| TECH-007 | Translate foundation docs | [TECH-007](features/TECH-007-2026-01-24-translate-foundation-docs.md) |
| TECH-008 | Translate architecture docs (01-08) | [TECH-008](features/TECH-008-2026-01-24-translate-architecture-docs.md) |
| TECH-009 | Translate process docs (09-14) | [TECH-009](features/TECH-009-2026-01-24-translate-process-docs.md) |
| TECH-010 | Translate LLM workflow docs (15-19) | [TECH-010](features/TECH-010-2026-01-24-translate-llm-workflow-docs.md) |
| TECH-011 | Translate all skills | [TECH-011](features/TECH-011-2026-01-24-translate-skills.md) |
| TECH-012 | Translate all agent prompts | [TECH-012](features/TECH-012-2026-01-24-translate-agents.md) |
| TECH-013 | Hero README | [TECH-013](features/TECH-013-2026-01-24-hero-readme.md) |
| TECH-014 | Create COMPARISON.md | [TECH-014](features/TECH-014-2026-01-24-comparison-md.md) |
| TECH-015 | Create FAQ.md | [TECH-015](features/TECH-015-2026-01-24-faq-md.md) |
| TECH-016 | Draft HackerNews post | [TECH-016](features/TECH-016-2026-01-24-hackernews-post.md) |
| TECH-017 | Draft Twitter thread | [TECH-017](features/TECH-017-2026-01-24-twitter-thread.md) |
| TECH-018 | Draft Reddit posts | [TECH-018](features/TECH-018-2026-01-24-reddit-posts.md) |
| TECH-019 | Example: Marketplace Launch | [TECH-019](features/TECH-019-2026-01-24-example-marketplace.md) |
| TECH-020 | Example: AI Autonomous Company | [TECH-020](features/TECH-020-2026-01-24-example-autonomous-company.md) |
| TECH-021 | Example: Content Factory | [TECH-021](features/TECH-021-2026-01-24-example-content-factory.md) |
| TECH-022 | Workflow diagram | [TECH-022](features/TECH-022-2026-01-24-workflow-diagram.md) |
| TECH-023 | Comparison table image | [TECH-023](features/TECH-023-2026-01-24-comparison-table-image.md) |
| TECH-025 | README tagline optimization | [TECH-025](features/TECH-025-2026-01-26-readme-tagline.md) |
| TECH-026 | i18n hooks to English | [TECH-026](features/TECH-026-2026-01-26-i18n-hooks.md) |
| TECH-027 | CI/CD GitHub workflows | [TECH-027](features/TECH-027-2026-01-26-cicd-workflows.md) |
| TECH-028 | CLI scaffolder (npx create-dld) | [TECH-028](features/TECH-028-2026-01-26-cli-scaffolder.md) |
| TECH-029 | Dev.to article draft | [TECH-029](features/TECH-029-2026-01-26-devto-article.md) |
| TECH-030 | GIF demo for README | [TECH-030](features/TECH-030-2026-01-26-gif-demo.md) |
| TECH-031 | YouTube tutorial script | [TECH-031](features/TECH-031-2026-01-26-youtube-script.md) |
| TECH-032 | Discord community setup | [TECH-032](features/TECH-032-2026-01-26-discord-setup.md) |
| TECH-033 | Product Hunt launch assets | [TECH-033](features/TECH-033-2026-01-26-producthunt-assets.md) |
| TECH-034 | "Used By" section in README | [TECH-034](features/TECH-034-2026-01-26-used-by-section.md) |
| TECH-035 | Post-execution Exa verifier | [TECH-035](features/TECH-035-2026-01-29-post-execution-verifier.md) |
| TECH-036 | Research-enhanced /reflect | [TECH-036](features/TECH-036-2026-01-29-research-enhanced-reflect.md) |
| TECH-037 | Cross-task memory feed | [TECH-037](features/TECH-037-2026-01-29-cross-task-memory-feed.md) |
| TECH-038 | Diary records successes | [TECH-038](features/TECH-038-2026-01-29-diary-records-successes.md) |
| TECH-039 | Expand reflect scope | [TECH-039](features/TECH-039-2026-01-29-reflect-scope-expansion.md) |
| TECH-040 | Bootstrap Exa research | [TECH-040](features/TECH-040-2026-01-29-bootstrap-exa-research.md) |
| TECH-041 | Bootstrap compression | [TECH-041](features/TECH-041-2026-01-29-bootstrap-three-expert-compression.md) |
| TECH-042 | Unified skill-writer | [TECH-042](features/TECH-042-2026-01-29-unified-skill-writer.md) |
| TECH-043 | Fix hooks in worktrees | [TECH-043](features/TECH-043-2026-01-30-fix-hooks-worktree.md) |
| TECH-044 | Fix links to wrong repository | [TECH-044](features/TECH-044-2026-01-30-fix-wrong-repo-links.md) |
| TECH-045 | Remove placeholder files | [TECH-045](features/TECH-045-2026-01-30-remove-placeholder-files.md) |
| TECH-046 | Secure template settings | [TECH-046](features/TECH-046-2026-01-30-secure-template-settings.md) |
| TECH-047 | Unify hook paths | [TECH-047](features/TECH-047-2026-01-30-unify-hook-paths.md) |
| TECH-048 | Fix CHANGELOG versions | [TECH-048](features/TECH-048-2026-01-30-fix-changelog-versions.md) |
| TECH-049 | Remove awardybot references | [TECH-049](features/TECH-049-2026-01-30-remove-awardybot-references.md) |
| TECH-050 | Improve NPM package | [TECH-050](features/TECH-050-2026-01-30-improve-npm-package.md) |
| TECH-051 | Add Python linting to CI | [TECH-051](features/TECH-051-2026-01-30-add-python-ci.md) |
| TECH-052 | Expand cspell dictionary | [TECH-052](features/TECH-052-2026-01-30-expand-cspell-dictionary.md) |
| TECH-053 | Fix ADR placeholder dates | [TECH-053](features/TECH-053-2026-01-30-fix-adr-dates.md) |
| TECH-054 | Safe git add in template | [TECH-054](features/TECH-054-2026-01-30-safe-git-add-template.md) |
| TECH-059 | Unit Tests for Python Hooks | [TECH-059](features/TECH-059-2026-02-01-python-hooks-tests.md) |
| TECH-064 | Remove Fake Testimonial | [TECH-064](features/TECH-064-2026-02-01-fake-testimonial-fix.md) |

</details>

---

## Статусы

| Status | Owner | Description |
|--------|-------|-------------|
| `draft` | Manual | Legacy — manual override only, Spark never outputs this |
| `queued` | Spark | Ready for execution |
| `in_progress` | Autopilot | Currently executing |
| `blocked` | Autopilot | Needs human |
| `done` | Autopilot | Completed |

---

## Принципы приоритизации

```
LAUNCH BLOCKERS → GROWTH → INTERNAL

Вопрос для каждой задачи:
"Это поможет получить stars или это внутренняя кухня?"

Stars = impact
Internal = можно позже
```

---

## Launch Checklist

- [ ] `npx create-dld my-project` работает без ошибок
- [ ] GIF в README показывает wow-эффект за 10 секунд
- [ ] Discord ссылка ведёт на реальный сервер
- [ ] 3+ реальных testimonials (не fake)
- [ ] Video walkthrough на YouTube
- [ ] HN post готов к публикации
- [ ] Время launch выбрано (вторник 10am PST)

---

## Архив

See `ai/archive/` for completed tasks.

## Ideas

See `ai/ideas.md` for raw ideas not yet specced.
