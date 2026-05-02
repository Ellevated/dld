---
id: TECH-178
title: "Fix get_feedbacks_count/get_questions_count + cleanup orphan pending state files"
status: done
priority: P1
created: 2026-04-26
mode: feature
parent: BUG-177  # discovered while diagnosing stuck negative cases
related:
  - BUG-049  # legacy launchd cleanup — collect_rnp.py is still active
  - BUG-080  # cmd_fetch merge into pending — origin of stale items
  - BUG-122  # earlier audit flagged pending grow + DB gate gaps
  - BUG-123  # collect_results cleanup + pending prune in cmd_send
  - FTR-017  # modern domains/intelligence briefing (does NOT use broken count)
domain: reviews + infra/wb_api
---

## Problem

Two unrelated technical hygiene issues found while diagnosing BUG-177. Bundled into one spec because both are small and touch reviews/RNP plumbing.

### Problem 1: `get_feedbacks_count()` / `get_questions_count()` return WRONG numbers

`infra/wb_api/_feedbacks.py:63-87` calls the wrong WB API endpoints. The methods are documented as "unanswered count" but actually return total archive counts.

| Method | Endpoint hit | Endpoint that should be hit |
|--------|--------------|------------------------------|
| `get_feedbacks_count()` | `GET /api/v1/feedbacks/count` → `{data: int}` total in archive | `GET /api/v1/feedbacks/count-unanswered` → `{data: {countUnanswered, countUnansweredToday}}` |
| `get_questions_count()` | `GET /api/v1/questions/count` → `{data: int}` total in archive | `GET /api/v1/questions/count-unanswered` → `{data: {countUnanswered, countUnansweredToday}}` |

**Evidence (domabout, 2026-04-26):**

| Source | Returned | Reality |
|--------|----------|---------|
| `get_feedbacks_count()` | 49 381 | 4 unanswered |
| `get_questions_count()` | 991 | small N |
| `/feedbacks?isAnswered=false&take=1` → `data.countUnanswered` | 4 | ground truth |

**WB API docs confirm** (`docs/wb-api.md:15670`):
- `/feedbacks/count` and `/questions/count` accept `dateFrom`/`dateTo`/`isAnswered` and return `{data: int}` — total in period, NOT unanswered.
- `/feedbacks/count-unanswered` and `/questions/count-unanswered` are dedicated endpoints that return `{data: {countUnanswered: N, countUnansweredToday: N}}`.

**Consumer impact:** only one active consumer — `agents/analyst/tools/collect_rnp.py:163-164`. This is the LEGACY РНП script (still invoked by `/rnp` skill `.claude/skills/rnp/SKILL.md:27` and shell wrappers `infra/scheduler/run_rnp.sh`, `run_rnp_domabout.sh`). Result: every morning report shows fake counts like "Неотвеченных отзывов: 49381" / "Неотвеченных вопросов: 991". Operator sees apocalypse, reality is fine.

**Confirmed NOT affected:** modern `domains/intelligence/collector.py:184` uses `len(feedbacks_result.data)` directly — bypasses the broken methods. So scheduler-driven RNP (FTR-017+) is correct, but the manual `/rnp` slash command lies.

**Test coverage gap:** only one live integration test `tests/integration/test_wb_api_live.py:28-38` asserts `count >= 0` — passes even with garbage. Zero unit tests with mocked responses.

### Problem 2: Stale items in `state/auto-responder/pending/{project}.json`

35 items dated 2026-03-25 → 2026-04-14 sitting in `state/auto-responder/pending/domabout.json`, file untouched since 2026-04-23.

The file is **NOT orphan** in the strict sense — `domains/reviews/cli.py:cmd_fetch` writes it (BUG-080 merge-append) and `cli.py:cmd_send` prunes consumed IDs from it (BUG-123 `_prune_pending`). But: the **scheduler-driven** pipeline (`response_pipeline.execute_pipeline()`) bypasses the file entirely (DB + action_gate + idempotency). So the only writer is the manual `/respond` slash command.

**Staleness mechanism:** operator runs `/respond domabout 200` (which triggers `cli.py:cmd_fetch`) but never runs `cmd_send`, OR `cmd_send` skips items via hard-check / API failure / idempotency without consuming them, OR the slash command is interrupted between fetch and send. Items rot in pending forever. Then `cli.py:cmd_stats` reports inflated "pending: N" and `cli_complaints.py:print_sla_status` shows scary "[!!] expired (>30d)" warnings that don't reflect actual unanswered reviews on WB.

**No risk to actual review answering:** scheduler responds via DB pipeline, so stale pending files don't cause double-replies or missed replies. This is purely cosmetic + operator confusion + disk noise.

**Files affected (current state on disk):**
- `state/auto-responder/pending/domabout.json` — 35 stale items, 14d+ old
- `state/auto-responder/pending/grisha.json` — needs check
- `state/auto-responder/pending/sabsabi.json` — needs check
- `state/auto-responder/pending/kirill.json` — needs check

---

## Goal

1. **Fix 1:** `get_feedbacks_count()` / `get_questions_count()` return the actual unanswered count from WB. Lock contract with unit tests.
2. **Fix 2:** Provide a maintenance tool that prunes stale items (>N days) from `state/auto-responder/pending/*.json`, dry-run by default, age-aware (does NOT blanket-delete fresh work-in-progress).
3. RNP script (`collect_rnp.py`) is touched only if test confirms downstream display still works after the API contract change.

**Out of scope** (explicit): deprecation/removal of `domains/reviews/batch.py` and `collect_results()`. They're still consumed by `/respond` SKILL Step 4 (`.claude/skills/respond/SKILL.md:155`) and 9 tests. Separate decision needed (TECH-XXX follow-up if we kill the manual flow entirely).

---

## Approach

### Fix 1 — switch to `/count-unanswered` endpoint

Two valid options considered:

| Option | Pros | Cons |
|--------|------|------|
| **A. Use `/feedbacks/count-unanswered`** (chosen) | Semantically correct. Same rate-limit cost (1 req). Simpler response parsing. Matches WB intent. | Two new endpoints in our client. |
| B. Reuse `get_feedbacks(isAnswered=false, take=1)` and parse `data.countUnanswered` | No new endpoint. | Wastes payload (returns 1 feedback object too). Couples count to listing semantics. |

**Decision: Option A.** New response shape: `{"data": {"countUnanswered": N, "countUnansweredToday": N}, "error": false, ...}`. We extract `countUnanswered` and return as int. `countUnansweredToday` is exposed via a sibling method for future use (RNP "today" badge). Optional, minimal addition.

### Fix 2 — `tools/maintenance/cleanup_orphan_pending.py`

Single-file CLI script under existing `tools/` namespace. Pattern matches `tools/diagonal-scan/scripts/run_scan.py` style.

```bash
# Dry-run by default — show what would be removed, no writes
python tools/maintenance/cleanup_orphan_pending.py

# Actually delete items older than 30 days from all projects
python tools/maintenance/cleanup_orphan_pending.py --apply --max-age-days 30

# Only one project
python tools/maintenance/cleanup_orphan_pending.py --apply --project domabout

# More aggressive — used after confirming SKILL flow finished cleanly
python tools/maintenance/cleanup_orphan_pending.py --apply --max-age-days 7
```

**Algorithm:**
1. Iterate `state/auto-responder/pending/*.json` (or `--project` filter).
2. For each file, load list of items.
3. For each item, parse `created_date` (ISO 8601 from WB). Compute `age_days = now - created_date`.
4. Partition into `keep` (age <= max_age_days OR malformed date) and `remove` (age > max_age_days).
5. **Dry-run:** print summary `would remove N items from {file} (age range: X-Y days)`, exit.
6. **Apply:** if `keep` non-empty, rewrite file with `json.dumps(keep, ensure_ascii=False, indent=2)`. If `keep` empty, `unlink(missing_ok=True)`. Mirror the pattern from `cli.py:_prune_pending`.
7. Print final summary: per-project `removed:N kept:M`.

**Design decisions:**
- Default `--max-age-days = 30` matches `MAX_FEEDBACK_AGE_DAYS = 30` in `_wb_client.py` — items past this are unreplyable on WB (HTTP error from POST `/feedbacks/answer`). Safe upper bound.
- Age-based, not blanket — protects `/respond` users mid-flow (yesterday's fetch is fresh).
- Dry-run default — every operator sees what will happen first. No `--yes` flag.
- Preserves items with malformed `created_date` rather than deleting silently (operator can investigate).
- No git commit, no DB write — pure file maintenance.

---

## Code Changes

### 1. `infra/wb_api/_feedbacks.py:63-87` — fix both count methods

```python
def get_feedbacks_count(self) -> int:
    """GET /api/v1/feedbacks/count-unanswered — unanswered reviews count.

    Returns:
        Number of unanswered feedbacks (all-time). 0 on API error.
    """
    data = self._request(
        "GET", FEEDBACKS_API, "/api/v1/feedbacks/count-unanswered"
    )
    if isinstance(data, dict):
        inner = data.get("data", {})
        if isinstance(inner, dict):
            return int(inner.get("countUnanswered") or 0)
    return 0

def get_questions_count(self) -> int:
    """GET /api/v1/questions/count-unanswered — unanswered questions count.

    Returns:
        Number of unanswered questions (all-time). 0 on API error.
    """
    data = self._request(
        "GET", FEEDBACKS_API, "/api/v1/questions/count-unanswered"
    )
    if isinstance(data, dict):
        inner = data.get("data", {})
        if isinstance(inner, dict):
            return int(inner.get("countUnanswered") or 0)
    return 0
```

Removed the legacy fallback branches (top-level int, top-level dict-with-countUnanswered) — `/count-unanswered` always returns the documented shape; if not, return 0. Keep behaviour conservative.

### 2. `tests/unit/test_wb_api_client.py` — add 2 unit tests

Mock the new endpoint and assert correct parsing:

```python
@responses.activate
def test_get_feedbacks_count_returns_unanswered(self, client):
    responses.add(
        responses.GET,
        f"{FEEDBACKS_API}/api/v1/feedbacks/count-unanswered",
        json={
            "data": {"countUnanswered": 4, "countUnansweredToday": 1},
            "error": False, "errorText": "", "additionalErrors": None,
        },
        status=200,
    )
    assert client.get_feedbacks_count() == 4

@responses.activate
def test_get_feedbacks_count_returns_zero_on_error(self, client):
    responses.add(
        responses.GET,
        f"{FEEDBACKS_API}/api/v1/feedbacks/count-unanswered",
        status=500,
    )
    assert client.get_feedbacks_count() == 0

# Same pair for get_questions_count
```

### 3. `tests/integration/test_wb_api_live.py:28-38` — strengthen live assertion

Current test only checks `>= 0` (passes with garbage 49 381). Add upper-bound sanity check vs `get_feedbacks(take=1)` `countUnanswered`:

```python
def test_get_feedbacks_count_matches_listing(self, wb_client):
    """Count from /count-unanswered must equal countUnanswered in listing."""
    count = wb_client.get_feedbacks_count()
    listing = wb_client.get_feedbacks(is_answered=False, take=1)
    expected = (listing or {}).get("data", {}).get("countUnanswered", 0)
    assert count == expected, f"count={count} expected={expected}"
```

### 4. `tools/maintenance/cleanup_orphan_pending.py` — NEW (~80 LOC)

Standalone CLI. Imports stdlib only (no domain imports — pure file operations + ISO date parsing). Lives under `tools/maintenance/` (new directory).

### 5. `tools/maintenance/__init__.py` — NEW (empty)

### 6. `tests/unit/test_cleanup_orphan_pending.py` — NEW (~120 LOC)

Tests:
- Dry-run does not write file
- Apply removes only items older than `--max-age-days`
- Empty keep list → file unlinked
- Malformed `created_date` → kept (not removed silently)
- `--project` filter limits scope
- Items with no `created_date` field → kept

### 7. `agents/analyst/tools/collect_rnp.py` — NO CHANGE

The script reads the return value of `get_feedbacks_count()` as `int` and prints/forwards it. Once the underlying API method is fixed, the displayed numbers correct themselves automatically. No edit needed.

Verification step (manual, not in CI): after merge, run `/rnp` for domabout — confirm "Неотвеченных отзывов" shows ~5, not 49 000.

### 8. `docs/api/wb-api-reference.md:228-231` — update endpoint name

Replace the line that says `GET /api/v1/feedbacks/count Количество необработанных отзывов` (misleading) with the correct dedicated endpoint:

```diff
- | GET | `/api/v1/feedbacks/count` | Количество необработанных отзывов |
+ | GET | `/api/v1/feedbacks/count-unanswered` | Количество неотвеченных отзывов (unanswered + unansweredToday) |
+ | GET | `/api/v1/feedbacks/count` | Total в архиве за период (с фильтром isAnswered/dateFrom/dateTo) |
```

Same for `/questions/count`.

---

## Allowed Files

```
infra/wb_api/_feedbacks.py                      # modify — fix 2 methods
tests/unit/test_wb_api_client.py                # modify — add 4 tests
tests/integration/test_wb_api_live.py           # modify — strengthen 1 test
tools/maintenance/__init__.py                   # create
tools/maintenance/cleanup_orphan_pending.py     # create
tests/unit/test_cleanup_orphan_pending.py       # create
docs/api/wb-api-reference.md                    # modify — clarify endpoints
ai/backlog.md                                   # modify — add row
```

---

## Eval Criteria

| ID | Source | Test | Pass Condition | Priority |
|----|--------|------|----------------|----------|
| EC-1 | Fix 1 | Unit: mock `/feedbacks/count-unanswered` returning `{data: {countUnanswered: 4, countUnansweredToday: 1}}` | `get_feedbacks_count()` returns `4` | P0 |
| EC-2 | Fix 1 | Unit: mock `/questions/count-unanswered` returning `{data: {countUnanswered: 12}}` | `get_questions_count()` returns `12` | P0 |
| EC-3 | Fix 1 | Unit: mock 500 response | `get_feedbacks_count()` returns `0` (no exception) | P0 |
| EC-4 | Fix 1 | Unit: mock empty `{data: {}}` | `get_feedbacks_count()` returns `0` | P1 |
| EC-5 | Fix 1 | Unit: verify the request URL ends with `/count-unanswered`, NOT `/count` | Only `/count-unanswered` is hit | P0 |
| EC-6 | Fix 1 (devil DA-1) | Integration test (live, requires WB token) | `get_feedbacks_count()` value within 5% of `get_feedbacks(is_answered=False, take=1).data.countUnanswered` | P1 |
| EC-7 | Fix 2 | Unit: pending file with 5 items (3 old, 2 fresh), `--max-age-days 30`, dry-run | File unchanged on disk; stdout reports "would remove 3 items" | P0 |
| EC-8 | Fix 2 | Unit: same setup, `--apply` | File contains exactly 2 fresh items; old items removed | P0 |
| EC-9 | Fix 2 | Unit: `--apply` with all items old | File deleted (`unlink`), stdout reports "file removed" | P0 |
| EC-10 | Fix 2 (devil DA-3) | Unit: item with `created_date: ""` or missing | Item kept (not silently removed); stdout warns "skipping malformed date" | P1 |
| EC-11 | Fix 2 | Unit: `--project domabout` | Only domabout.json processed; grisha.json untouched | P1 |
| EC-12 | Fix 2 | Unit: empty pending dir | Exit 0 with "no files to process" | P1 |
| EC-13 | Regression | Re-run full `tests/test_review_cli.py` and `tests/test_review_batch.py` | All existing tests pass — no regression in `cli.cmd_fetch`, `cli.cmd_send`, `_prune_pending`, `batch.collect_results` | P0 |
| EC-14 | Manual | Trigger `/rnp` for domabout in test environment after deploy | Морning report shows realistic unanswered counts (single digits / small N), NOT 49 000 | P0 |

**TDD Order:** EC-1 → EC-3 → EC-5 → EC-2 → EC-7 → EC-8 → EC-9 → EC-10 → EC-4, EC-11, EC-12 → EC-13 (regression) → EC-6 (live) → EC-14 (manual smoke).

---

## Devil's Advocate (recorded)

**DA-1: "Maybe `/count` IS unanswered for some accounts and we'd break them."**
Verified against WB OpenAPI spec (`docs/wb-api.md:15670`): `/count` accepts `dateFrom`/`dateTo`/`isAnswered` and returns `{data: int}`. Without query params it returns ALL feedbacks for the account, all-time. The 49 381 figure for domabout matches the archive total observed via `get_feedbacks?isAnswered=false&take=1` → `data.countArchive: 49477`. Definitively not unanswered. Single source of truth: switch is safe.

**DA-2: "Are there other consumers of `/feedbacks/count` or `get_feedbacks_count` we missed?"**
Grep results: `get_feedbacks_count` referenced in:
- `infra/wb_api/_feedbacks.py:63` — definition
- `agents/analyst/tools/collect_rnp.py:163` — only active consumer
- `tests/integration/test_wb_api_live.py:28` — test
- Various `ai/audit/` and `ai/.bughunt/` files — historical references, no live code
No other production consumers. Modern `domains/intelligence` uses `len(feedbacks_result.data)`, not the broken method.

**DA-3: "What if pending cleanup nukes someone's mid-flow `/respond` session?"**
Mitigated by `--max-age-days 30` default + dry-run default. 30 days is the WB hard limit (`MAX_FEEDBACK_AGE_DAYS`) — items older are unreplyable anyway. A user with a 1-day-old fetch is safe. EC-10 also guards against silent loss of items with bad dates (kept, not removed).

**DA-4: "Should we also delete `state/auto-responder/ready/{project}.json` orphan items?"**
No. `cmd_send` already prunes ready (BUG-123). Stale ready means `cmd_send` is failing — that's a different bug to investigate, not silently delete. Out of scope.

**DA-5: "Should we deprecate `batch.collect_results` since the scheduler bypasses it?"**
Out of scope. The `/respond` slash command (`.claude/skills/respond/SKILL.md`) actively uses it for the subagent fan-out flow. 9 tests in `test_review_batch.py` exercise it. Killing this is a product decision (do we still support manual operator flow alongside the scheduler?), not a tech-debt fix. Open as separate TECH-XXX if we decide to consolidate.

**DA-6: "Should we add `agents/analyst/tools/collect_rnp.py` to the deprecation queue?"**
Out of scope. Modern `domains/intelligence/briefing.py` is the replacement (FTR-017 noted it as deprecated wrapper). Three call sites still exist (`/rnp` skill + 2 shell wrappers). Killing them needs a /rnp SKILL rewrite to call the modern collector. Open as separate FTR if we want a unified RNP.

---

## Definition of Done

- [ ] `get_feedbacks_count()` returns actual unanswered count from `/count-unanswered`
- [ ] `get_questions_count()` returns actual unanswered count from `/count-unanswered`
- [ ] 4 new unit tests in `test_wb_api_client.py` pass (EC-1, EC-2, EC-3, EC-5)
- [ ] Strengthened live test in `test_wb_api_live.py` passes (EC-6)
- [ ] `tools/maintenance/cleanup_orphan_pending.py` runs in dry-run by default and produces clear stdout
- [ ] `--apply` correctly removes items older than `--max-age-days` (EC-7, EC-8, EC-9)
- [ ] Items with malformed dates are kept (EC-10)
- [ ] `--project` filter scopes to one project (EC-11)
- [ ] All existing review CLI/batch tests pass (EC-13)
- [ ] `docs/api/wb-api-reference.md` accurately distinguishes `/count` vs `/count-unanswered`
- [ ] Manual smoke: `/rnp` for domabout shows realistic unanswered numbers (single digits)
- [ ] One-time cleanup run executed: `python tools/maintenance/cleanup_orphan_pending.py --apply --max-age-days 30` for all projects, stale `domabout.json` items pruned
- [ ] Backlog row added: `TECH-178 | feedbacks count fix + pending cleanup | done | P1 | [TECH-178](features/TECH-178-2026-04-26-feedbacks-count-and-pending-cleanup.md)`

---

## Blueprint Reference

No system-blueprint constraints (utility/maintenance scope). Aligns with:
- ADR-014: scheduler jobs exempt from infra→domains rule (cleanup tool is in `tools/`, no scheduler integration).
- `docs/architecture-layers.md`: `tools/` layer reserved for one-off and maintenance scripts. `cleanup_orphan_pending.py` fits.
- `.claude/rules/architecture.md`: `infra/wb_api/_feedbacks.py` change preserves existing public API (signatures unchanged), only fixes implementation. No import direction change.

---

## Notes for Autopilot

- **Run order:** Fix 1 first (smaller blast radius, immediate operator value). Fix 2 second.
- **No DB migration.** No schema change. No new tables.
- **Backward compatible.** All callers of `get_feedbacks_count()` / `get_questions_count()` continue to receive `int >= 0`. Only the value changes (from broken to correct).
- **Testing strategy:** unit tests with `responses` library mocking, no live API in CI for the unit suite. EC-6 live test is `--integration` marked.
- **Deploy verification:** EC-14 is manual — operator runs `/rnp domabout` and checks the morning report numbers look sane.
