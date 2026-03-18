# External Research — Fix 3 DLD Cycle Breaks + Smoke Test

## Best Practices (5 with sources)

### 1. Smoke Tests as Pipeline Gate — Fast, Shallow, Broad
**Source:** [Smoke Testing in CI/CD Pipelines — CircleCI](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/)
**Summary:** Smoke tests ("build verification tests") should run on every build and cover the critical path only — not edge cases. They answer one question: "is the build stable enough to proceed?" CircleCI recommends they complete in under 5 minutes and exercise the real system, not mocks.
**Why relevant:** The DLD cycle has a single critical path: inbox file → orchestrator → pueue → claude-runner → callback → notify. A smoke test that walks this exact path (with a dry-run sentinel task) catches all 3 current breaks in one shot before deeper testing.

### 2. BATS for Shell/Pipeline Integration Tests
**Source:** [Effective End-to-End Testing with BATS — Jack Henschel](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/)
**Summary:** BATS (Bash Automated Testing System) is the natural choice when your system under test lives in bash. It allows using `grep`, `jq`, `sqlite3`, `pueue` directly in assertions. Used for end-to-end validation of Kubernetes components at Buildkite. Reduces boilerplate vs rolling your own test harness in pure shell.
**Why relevant:** The DLD orchestrator is a bash+python hybrid. BATS lets you assert against real sqlite state, real pueue output, and real file system changes — exactly what the pipeline smoke test needs. Python `pytest` would require subprocess wrapping for each shell component; BATS treats them as first-class.

### 3. Expand-Contract Pattern for NULL Backfill in Operational Databases
**Source:** [How we make database schema migrations safe and robust at Defacto](https://www.getdefacto.com/article/database-schema-migrations)
**Summary:** The expand-contract pattern separates adding schema (expand) from populating data (backfill) from enforcing constraints (contract). For NULL backfills in operational tables: (1) add column nullable, (2) backfill in batches with `WHERE col IS NULL LIMIT N`, (3) add NOT NULL constraint only after 100% coverage. This prevents table locks in operational DBs.
**Why relevant:** The DLD `project_state` table has `topic_id` NULLs in existing rows. The fix should be a single-pass `UPDATE WHERE topic_id IS NULL` (small table, SQLite, no concurrency risk) — but the expand-contract mental model still applies: fix the data first, then tighten routing logic.

### 4. Telegram `message_thread_id` — Always Pass Explicitly, Fallback to None
**Source:** [FEATURE: Reply functions should reply to the same thread by default — python-telegram-bot #4139](https://github.com/python-telegram-bot/python-telegram-bot/issues/4139)
**Summary:** `Message.reply_text()` does NOT preserve `message_thread_id` by default — it sends to the General topic unless `do_quote=True` or `message_thread_id` is passed explicitly. Closed in PTB v21.3+ by introducing `do_quote` defaulting to preserve thread. For `Bot.send_message()` calls (outbound notifications), the caller must pass `message_thread_id` or omit it (which routes to General/DM without error).
**Why relevant:** `notify.py` calls `Bot.send_message(chat_id=..., text=...)`. When `topic_id` is NULL in `project_state`, passing `message_thread_id=None` is safe — the message routes to the main chat instead of crashing. The pattern: `message_thread_id=topic_id or None`.

### 5. File Naming — ISO 8601 (YYYY-MM-DD) is the Universal Standard
**Source:** [Master File Naming Conventions with YYYY-MM-DD — NameQuick](https://www.namequick.app/blog/file-naming-conventions)
**Source 2:** [normfn — Normalize filenames to ISO-8601 — GitHub](https://github.com/andrewferrier/normfn)
**Summary:** ISO 8601 (`YYYY-MM-DD`) is the universal standard for date-prefixed filenames. It sorts lexicographically correctly, is unambiguous across locales, and is what every downstream tool (git log, ls, grep) expects. The compact `YYYYMMDD` format (no separators) is a common variant used when hyphens are problematic (e.g., in identifiers). Both are valid but must not be mixed within the same system — one causes glob patterns and regex to fail on the other.
**Why relevant:** DLD inbox files were created with one date format (e.g. `20260318`) but the orchestrator glob may expect `2026-03-18` or vice versa. A normalization pass using Python `re.sub` or `os.rename` to unify to one format is the correct fix — not changing the glob.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| bats-core | v1.11.1 (2025) | Native bash, TAP output, works with real processes, no extra runtime | Bash-only assertions (use python for complex checks) | Shell+Python pipeline smoke tests | [bats-core GitHub](https://github.com/bats-core/bats-core) |
| bats-mock (buildkite) | v2.2.0 (2025-11) | Stub any CLI command (pueue, claude, notify) for unit-level shell tests | Fork of dormant project, limited maintainers | Stubbing external commands in shell tests | [buildkite-plugins/bats-mock](https://github.com/buildkite-plugins/bats-mock) |
| pytest + subprocess | pytest 8.x | Python ecosystem, parametrize, fixtures, assert sqlite state | Requires wrapping bash scripts in subprocess calls | Python-dominant pipelines needing shell testing | [pytest docs](https://docs.pytest.org) |
| python-telegram-bot | v21.9+ | Mature, `message_thread_id` handled via `do_quote`, `BadRequest` exceptions catchable | Async-first since v20, some breaking changes | Telegram notification with graceful thread fallback | [PTB GitHub](https://github.com/python-telegram-bot/python-telegram-bot) |

**Recommendation:** BATS for the smoke test script itself (the pipeline is bash, tests should be bash), Python `sqlite3` for state assertions within BATS `run` blocks. No new dependencies — bats-core is installed via `apt install bats` or `npm install -g bats`.

---

## Production Patterns

### Pattern 1: Sentinel Task Dry-Run (Pipeline Health Check)
**Source:** [How to Implement Smoke Testing Strategies — OneUptime](https://oneuptime.com/blog/post/2026-01-25-smoke-testing-strategies/view)
**Description:** Inject a known-good "canary" or "sentinel" task into the pipeline with `--dry-run` semantics. The task exercises every component (file creation, DB write, pueue dispatch, callback, notification) but exits with code 0 without doing real work. Smoke passes if the sentinel completes successfully within a timeout.
**Real-world use:** Used by CircleCI, Semaphore CI, and Sealos ML pipeline monitoring to verify pipeline health after deployment.
**Fits us:** Yes — create a `tests/smoke/run_cycle_smoke.sh` that places a synthetic `inbox/test-*.md` file, watches for it to be processed by orchestrator (via DB state change), and verifies the callback wrote to `task_log`. Covers all 3 break points.

### Pattern 2: Batched WHERE IS NULL Backfill
**Source:** [Batch Processing in SQLite: How to update efficiently a table with millions of records — Medium](https://medium.com/@yvsharabi/batch-processing-in-sqlite-a-deep-dive-into-database-field-updates-90dbf924b357)
**Description:** `UPDATE table SET col = val WHERE col IS NULL AND id IN (SELECT id FROM table WHERE col IS NULL LIMIT N)`. Use batch size 100-1000 rows. Track last processed ID to avoid full table scans on each iteration. For small operational tables (< 10K rows), a single-statement UPDATE with no LIMIT is safe.
**Real-world use:** Standard pattern for all SQL databases when backfilling a new column. SQLite has no MVCC so batching reduces lock duration; for <10K rows a single transaction is fine.
**Fits us:** Yes — DLD's `project_state` table has at most ~10 rows (one per project). A single `UPDATE project_state SET topic_id = <value> WHERE topic_id IS NULL` is the correct fix, with a CLI subcommand added to `db.py`.

### Pattern 3: Graceful Thread Routing Fallback (Telegram)
**Source:** [Bug: Telegram DM with forum/topics enabled loses thread routing — openclaw/openclaw #17980](https://github.com/openclaw/openclaw/issues/17980)
**Description:** When `topic_id` is NULL (project not yet associated to a thread), send to `chat_id` without `message_thread_id`. When `topic_id` IS set, pass it. Catch `BadRequest: Message thread not found` and retry without `message_thread_id`. This prevents notification silently dropping or crashing when topic binding is stale.
**Real-world use:** OpenClaw (318K stars), python-telegram-bot issue tracker — this is a documented production failure mode that has bitten multiple large projects.
**Fits us:** Yes — `notify.py` should use `message_thread_id=project["topic_id"] or None`. The `or None` handles the NULL case transparently. If the topic was deleted, wrap in try/except `BadRequest` and retry without thread ID.

### Pattern 4: BATS `setup` / `teardown` for Isolated Pipeline Tests
**Source:** [DevelopMeh — BATS: Testing Bash Like You Mean It](https://developmeh.com/tech-dives/bats-testing-bash-like-you-mean-it/)
**Description:** Use `setup()` to create a temp directory, seed a test SQLite DB, and place fixture inbox files. Use `teardown()` to clean up. Each test is a complete pipeline scenario: "given a valid inbox file, orchestrator dispatches and DB transitions to `in_progress`". Assert with `sqlite3 "$TEST_DB" "SELECT phase FROM project_state WHERE project_id='test'"`.
**Real-world use:** Jack Henschel used this for restic-k8s Kubernetes backup pipeline E2E tests. Buildkite uses BATS for their agent pipeline integration tests.
**Fits us:** Yes — this is exactly the shape of our smoke test. Setup: create temp DB + inbox dir. Test: trigger orchestrator cycle. Assert: DB state + pueue task created. Teardown: kill orchestrator, clean temp files.

---

## Key Decisions Supported by Research

1. **Decision:** Use BATS (not pytest) for the smoke test
   **Evidence:** [DevelopMeh BATS article](https://developmeh.com/tech-dives/bats-testing-bash-like-you-mean-it/) — "if your tool lives in bash, your integration tests should too." DLD orchestrator is bash-first; BATS avoids subprocess wrapping overhead and tests the real execution environment.
   **Confidence:** High

2. **Decision:** Fix `notify.py` routing with `topic_id or None` pattern (not a larger refactor)
   **Evidence:** [PTB issue #4139](https://github.com/python-telegram-bot/python-telegram-bot/issues/4139) + [openclaw #17980](https://github.com/openclaw/openclaw/issues/17980) — the NULL `message_thread_id` path is well-understood and handled by omitting the parameter. One-line fix.
   **Confidence:** High

3. **Decision:** Backfill `topic_id` NULLs via a `db.py backfill-topic` CLI subcommand (not a raw SQL migration file)
   **Evidence:** DLD ADR-017 (SQL only via Python parameterized queries) + [Defacto migration article](https://www.getdefacto.com/article/database-schema-migrations) — expand-contract says: patch data separately from schema. The existing `db.py` CLI pattern is already the SSOT for SQLite operations.
   **Confidence:** High

4. **Decision:** Normalize all inbox filenames to a single date format (compact `YYYYMMDD` or hyphenated `YYYY-MM-DD`) — pick one and enforce via a pre-check in `inbox-processor.sh`
   **Evidence:** [normfn project](https://github.com/andrewferrier/normfn) + [NameQuick conventions](https://www.namequick.app/blog/file-naming-conventions) — mixing formats breaks glob patterns silently. Correct fix: validate/normalize at the entry point (inbox-processor), not in every consumer.
   **Confidence:** High

5. **Decision:** Smoke test should run in < 60 seconds against a real (but isolated) DB instance — no mocks
   **Evidence:** [CircleCI smoke tests](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/) + DLD ADR-013 (mock ban in integration tests) — smoke tests use real dependencies. Create a `TEST_DB_PATH` environment variable pointing to a temp SQLite file for isolation.
   **Confidence:** High

---

## Research Sources

- [Smoke Testing in CI/CD Pipelines — CircleCI](https://circleci.com/blog/smoke-tests-in-cicd-pipelines/) — canonical definition, practices, and when to use smoke vs integration tests
- [Effective End-to-End Testing with BATS — Jack Henschel](https://blog.cubieserver.de/2025/effective-end-to-end-testing-with-bats/) — BATS for real pipeline E2E testing with setup/teardown patterns
- [DevelopMeh — BATS: Testing Bash Like You Mean It](https://developmeh.com/tech-dives/bats-testing-bash-like-you-mean-it/) — rationale for choosing BATS over language-specific frameworks for bash pipelines
- [buildkite-plugins/bats-mock v2.2.0](https://github.com/buildkite-plugins/bats-mock) — stubbing external CLI commands (pueue, claude) in BATS tests
- [How we make database schema migrations safe at Defacto](https://www.getdefacto.com/article/database-schema-migrations) — expand-contract pattern for NULL backfills
- [Batch Processing in SQLite — Medium](https://medium.com/@yvsharabi/batch-processing-in-sqlite-a-deep-dive-into-database-field-updates-90dbf924b357) — batched WHERE IS NULL UPDATE, last-ID tracking to avoid full scans
- [python-telegram-bot issue #4139 — thread routing](https://github.com/python-telegram-bot/python-telegram-bot/issues/4139) — `message_thread_id` must be passed explicitly; None routes safely to General
- [openclaw/openclaw #17980 — DM forum thread regression](https://github.com/openclaw/openclaw/issues/17980) — production case of topic_id NULL breaking Telegram notification routing
- [normfn — normalize filenames to ISO-8601](https://github.com/andrewferrier/normfn) — file naming normalization tool and rationale for single canonical date format
- [How to Implement Smoke Testing Strategies — OneUptime](https://oneuptime.com/blog/post/2026-01-25-smoke-testing-strategies/view) — what smoke tests should and should not cover, sentinel task pattern
- [Best Practices for End-to-End Testing in 2026 — Bunnyshell](https://www.bunnyshell.com/blog/best-practices-for-end-to-end-testing-in-2025/) — E2E test scope, speed, and CI integration requirements
