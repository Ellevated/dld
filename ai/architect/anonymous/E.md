# Developer Experience Architecture Research

**Persona:** Dan (DX Architect / Pragmatist)
**Focus:** Innovation tokens, boring tech, developer workflow — scripts/vps/ contour
**Mode:** Retrofit (brownfield)
**Date:** 2026-05-23

---

## Research Conducted

Note: Exa search credits exhausted at time of writing. Research is conducted from
direct code evidence (primary source), architectural documentation (ADR chain,
deep-audit-report.md), and practitioner knowledge of the referenced technologies
(pueue, SQLite, git plumbing, pre-commit framework, Airflow/Prefect/Temporal).
This is appropriate for a brownfield audit — the code IS the evidence.

**Direct code reads:**
- `lifecycle.py` (602 LOC) — full _atomic_write implementation, CAS loop, WT-sync
- `callback.py` (1374 LOC) — _subject_implements, _SPEC_ID_RE, module docstring
- `orchestrator.py` (667 LOC) — bootstrap_new_specs, startup_reconcile
- `db.py` (531 LOC) — _ensure_migrations, schema patterns
- `spec_operator.py` (60 LOC) — interface and purpose
- `requirements.txt` — dependency surface
- `architecture-agenda.md` (Dan section) — question set
- `deep-audit-report.md` — 85 findings from 6 personas

**Reference knowledge applied:**
- Dan McKinley, "Choose Boring Technology" (mcfunley.com/choose-boring-technology)
- pueue task scheduler: design, callback contract
- SQLite WAL mode: capabilities and limits for single-machine write-ahead logging
- git plumbing: hash-object, write-tree, commit-tree, update-ref
- Airflow/Prefect/Temporal/Dagster: what they actually give you
- pre-commit framework (pre-commit.com): what it solves vs hand-rolled hooks

---

## Kill Question Answer

**"Is this solving a business problem or engineering curiosity?"**

| Proposed Technology | Business Problem Solved | Engineering Curiosity | Verdict |
|---------------------|------------------------|-----------------------|---------|
| SQLite for orchestrator state | Persist slot counts, task log across restarts | No — industry standard for single-machine state | Keep |
| pueue for task queuing | Run AI tasks with concurrency limits, callbacks, retry | Somewhat exotic but well-justified | Keep with caveats |
| Git as lifecycle DB (ADR-023) | "Audit trail lives in git" / "multi-machine sync via push" | Yes — gave us today's bug #3 | Replace with SQLite |
| Custom CAS via git plumbing + private GIT_INDEX_FILE | Prevent concurrent writes racing | Yes — invented wheel that already exists | Replace |
| Circuit-breaker (TECH-169) | Prevent mass-autopilot-loop on bad gate | Legitimate operational concern | Keep but simplify |
| 8-rule gate (cefaa55) | Know if a spec's work is done | Rule accumulation = engineering treadmill | Simplify to 1 rule |
| Custom Python daemon (orchestrator) | Dispatch tasks across 10 projects | Legitimate (Airflow is 100x overkill) | Keep |
| spec_operator.py CLI | Operator can manually mutate spec status | YAGNI — no human uses it as intended | Remove |
| Three-layer status (yaml + backlog + spec body) | — | Accidental from migration debt | Collapse to SQLite |
| _atomic_write / _atomic_write_file duplication | — | Accidental complexity | Remove via DRY |

**Innovation tokens spent on business:** 2 (pueue for AI task queuing, custom orchestrator)
**Innovation tokens spent on infrastructure:** 6 (git-as-DB, CAS plumbing, 8-rule gate, circuit-breaker,
  three-layer status, spec_operator CLI)

---

## Innovation Token Accounting

**Token Budget:** 3 tokens for a project of this scale (internal tooling, 1 human operator)

**Actual Token Spending:**

| # | Technology | Boring Alternative | Why Innovate Here? | Token Cost | Verdict |
|---|------------|-------------------|-------------------|------------|---------|
| 1 | Git as lifecycle DB (ADR-023) | SQLite single table | "Audit trail + multi-machine sync" | 1 token | REVOKE — gave bug #3 today |
| 2 | Custom CAS via private GIT_INDEX_FILE | SQLite transaction | "Atomic writes without locking" | 0.5 token | REVOKE — SQLite transactions are simpler |
| 3 | pueue task queue | systemd timer + cron | AI tasks need concurrency limits + callbacks | 0.5 token | KEEP — justified |
| 4 | 8-rule gate in callback.py | "merge commit with SPEC-ID exists on develop" | Avoid false-done | 0.5 token | SWAP — 1 rule = same reliability |
| 5 | Circuit-breaker (TECH-169) | Simpler rate-limit check | Prevent runaway loop | 0.25 token | KEEP — but simplify |
| 6 | spec_operator.py CLI | Direct lifecycle.write_lifecycle() call | "Operator UI" | 0.25 token | REMOVE — YAGNI |
| 7 | Custom Python orchestrator daemon | Airflow / Temporal | Those tools are 100x overkill for 10 projects | 1 token | KEEP — this IS the boring choice |
| 8 | claude_agent_sdk + custom subprocess wrapping | — | Unavoidable — no boring alternative | 0.5 token | KEEP — unavoidable |

**Total tokens spent:** ~4.5 tokens on a 3-token budget.

**Key insight:** We blew the token budget on infrastructure (git-as-DB, CAS loop,
8-rule gate) rather than on the actual business problem (reliably running AI tasks
and knowing when they're done). The irony is that these "innovative" infrastructure
choices are the source of the recurring incidents.

---

## Proposed DX Decisions

### Decision 1: "Git as Lifecycle DB" — REVOKE THIS TOKEN

**Quote from code (lifecycle.py:171-260):** The _atomic_write function performs 8 git
plumbing subprocesses (read-tree, hash-object, update-index, write-tree, rev-parse,
commit-tree, update-ref, checkout-index) with no timeout on any of them, holding a
threading.Lock() while doing so. When checkout-index runs after the private
GIT_INDEX_FILE has been deleted in the finally block, it reads from the stale main
index — this is bug #3 from today's incident.

**What ADR-023 was trying to solve:**
- Multi-machine convergence (git push syncs state)
- Audit trail (git log shows history)
- Avoid another writer race (backlog.md editing race in ADR-018)

**What it actually gave us:**
- Bug today: `checkout-index --force --` reads stale main index (lifecycle.py:244)
- 8 git subprocess calls vs 1 SQL statement
- LifecycleWriteRaceError on CAS failure after 3 retries
- push_best_effort logged at DEBUG level (lifecycle.py:266) — failures invisible
- `_atomic_write` and `_atomic_write_file` are two 80-LOC copies of the same bug
- No timeout — any git call can block the entire callback under _write_lock

**Boring alternative: SQLite, which we already have.**

```sql
-- This replaces 280 LOC of lifecycle.py
CREATE TABLE spec_lifecycle (
    spec_id     TEXT PRIMARY KEY,
    status      TEXT NOT NULL DEFAULT 'queued',
    priority    TEXT NOT NULL DEFAULT 'p1',
    kind        TEXT NOT NULL DEFAULT 'tech',
    blocked_reason TEXT,
    started_at  TEXT,
    finished_at TEXT,
    updated_at  TEXT NOT NULL,
    updated_by  TEXT NOT NULL,
    version     INTEGER NOT NULL DEFAULT 1,
    pueue_id    INTEGER,
    project_id  TEXT NOT NULL
);

CREATE TABLE spec_transitions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    spec_id     TEXT NOT NULL,
    from_status TEXT NOT NULL,
    to_status   TEXT NOT NULL,
    at          TEXT NOT NULL,
    by          TEXT NOT NULL,
    pueue_id    INTEGER,
    FOREIGN KEY (spec_id) REFERENCES spec_lifecycle(spec_id)
);
```

One `UPDATE spec_lifecycle SET status=?, updated_at=?, ... WHERE spec_id=?` inside
a SQLite WAL transaction replaces 8 subprocess calls + CAS retry loop + threading lock
+ checkout-index race. SQLite WAL handles concurrency between orchestrator and callback
(two processes on the same machine). That's all we have — there is no genuine
multi-machine scenario for this orchestrator.

**What we lose by dropping git-as-DB:**
- Git history of status changes. Answered by: transitions table + JSONL audit log
  (which already exists as callback-audit.jsonl).
- "Multi-machine sync via git push." Answered by: this orchestrator runs on a single
  VPS. The multi-machine convergence requirement is theoretical. If it ever becomes
  real, SQLite WAL + a periodic backup to git is simpler than the current CAS loop.

**LLM-native cost of migration:** ~$10, 2-3 hours. Remove lifecycle.py (602 LOC),
replace with 5 SQL functions in db.py. Migrate existing lifecycle/*.yaml to SQLite
with a one-shot script. This is a 3-4 file change — medium refactor.

---

### Decision 2: The 8-Rule Gate — SWAP FOR 1 RULE

**Quote from audit report:**
> `_subject_implements` отвергает доминирующую awardybot/dowry конвенцию
> (460 vs 176 коммитов) → систематические false-blocked

**Quote from deep-audit, Root 3:**
> feat(seller-batch): cancel-while-scheduled endpoint (FTR-1053 Task 4)
> _subject_implements returns False for all such → specs stay blocked

The 8-rule gate in verify_status_sync (callback.py, 202 LOC function) attempts to
infer "is work done?" from:
- commit subject format (Rule 1)
- LOC diff thresholds (Rule 3)
- file path matching allowed_files (Rules 4-5)
- origin/develop merge state (Rules 6-7)
- circuit-breaker state (Rule 2)
- cross-project guard (Rule 8, cefaa55)

Each rule is an inference. Each inference has edge cases. Each edge case spawns a
new rule. cefaa55 redesigned to 8 rules. Today we have bugs that 8 rules didn't catch.

**The boring alternative is the simplest possible gate:**

```python
def _is_done(project_path: str, spec_id: str) -> bool:
    """A spec is done when its work is merged to origin/develop."""
    r = subprocess.run(
        ["git", "-C", project_path, "log", "origin/develop",
         "--oneline", "--grep", spec_id],
        capture_output=True, text=True, timeout=30
    )
    return bool(r.stdout.strip())
```

Does `git log origin/develop --grep SPEC-ID` return any commits? If yes, done.
This is 5 lines, handles both commit conventions (scope and trailer), requires zero
regex maintenance, and cannot generate false-blocked because it doesn't care about
subject format — it searches the entire commit message.

**What we lose:** The LOC diff threshold checks (Rule 3 — "did enough code change?").
The question is whether Rule 3 prevented real false-dones in practice vs added
complexity that requires its own maintenance. Given that we still had 15 fake-done
flips today with 8 rules in place, the gates clearly aren't working reliably anyway.

**LLM-native cost of migration:** ~$5, 1 hour. Replace verify_status_sync (202 LOC)
with a ~30-line function. Add tests for both commit conventions. This immediately
fixes Root 3 (false-blocked on awardybot/dowry convention).

---

### Decision 3: Three-Layer Status — COLLAPSE TO ONE

**Quote from audit report (Root 1):**
> | ai/lifecycle/{spec_id}.yaml HEAD | git object store | callback (ADR-023) |
> | ai/backlog.md WT | working tree | render_backlog (best-effort) |
> | spec body ## Status: | working tree markdown | Spark (creates), никто не апдейтит |
>
> bootstrap_new_specs читает backlog.md из dirty WT без gate-check → 15 fake-done flips

Three representations of the same fact is not a design choice — it is accumulated
migration debt. ADR-018 used markdown. ADR-023 migrated to YAML. The migration
never finished: backlog.md and spec body still exist, still get read, and are
the source of today's 15 fake-done flips.

**Boring choice: SQLite + generated markdown.**

Keep ONE source of truth (SQLite spec_lifecycle table). Generate backlog.md as a
read-only view via `render_backlog.py` — but make it explicitly read-only by removing
all code that reads backlog.md as authoritative. bootstrap_new_specs becomes
`SELECT spec_id FROM spec_lifecycle WHERE status='queued'` — no markdown parsing,
no regex on the working tree.

The spec body `## Status:` line is purely cosmetic. It can stay as a human-readable
snapshot, but no code should read it for decisions.

**Three-layer → zero-layer:** status lives in ONE place. Everything else is a render
or a human annotation.

---

### Decision 4: spec_operator.py — REMOVE

**Quote from spec_operator.py:**
```
Used by: operators (CLI), `/qa` skill, post-circuit triage.
```

**Question from architecture-agenda.md:**
> spec_operator.py — нужен ли он вообще, если операторов в системе нет
> (Claude SDK не нуждается в operator UI; человек делает через git напрямую)

The actual users of this system are:
1. The founder (1 human) — who edits specs directly in git, not via a CLI tool
2. Claude SDK agents — who do not call spec_operator.py

Looking at the code, spec_operator.py imports callback._reset_circuit_cli — a private
function. This is a cross-module call into a god module's internals. The three
subcommands (demote, force-done, reset-circuit) are all operations that currently
require this tool because the "correct" path is so complicated. If we move status to
SQLite and simplify the gate, `demote` becomes `UPDATE spec_lifecycle SET status='queued'`
and `force-done` becomes `UPDATE spec_lifecycle SET status='done'`.

The operator CLI is a symptom of the complexity, not a feature. When the underlying
system is simple, you don't need a dedicated CLI to perform basic mutations.

**Remove spec_operator.py. Replace with direct SQLite mutations for the rare cases
where manual intervention is needed.** The founder is perfectly capable of running
`sqlite3 orchestrator.db "UPDATE spec_lifecycle SET status='queued' WHERE spec_id='ARCH-186'"`.

**LLM-native cost of removal:** ~$1, 15 minutes. Delete file, remove from documentation.

---

### Decision 5: pre-commit Framework vs Hand-Rolled Hooks — BORING WINS

**Quote from audit report (Root 2, Finding #4):**
> `pre-commit-lifecycle-guard.mjs` мёртв — `core.hooksPath=.git/hooks` во всех 3+
> репо, guard в `.git-hooks/`. Не работает нигде, даже в DLD.

The current approach: custom Node.js hook in `.git-hooks/`, requiring manual
`git config core.hooksPath .git-hooks` per repo. Not documented in onboarding.
Not verified in CI. Not deployed to any of the 10 managed projects.

The boring alternative: the pre-commit framework (pre-commit.com). It is:
- A Python package (pip install pre-commit) — no Node.js required
- Configured in `.pre-commit-config.yaml` — version-controlled, not per-developer-configured
- Self-installing via `pre-commit install` — one command, works everywhere
- Cross-repo via shared hook repos — publish the lifecycle guard as a hook, all projects reference it

If we go to SQLite and the "1-rule gate" (git log --grep), the pre-commit guard
becomes even simpler: validate that YAML files in ai/lifecycle/ are not modified
directly by commits (only by callback/orchestrator). With SQLite, there are no YAML
files to guard at all.

**Cost:** pre-commit is already in most Python projects' dev dependencies. This is
literally the boring choice.

---

### Decision 6: Custom Python Daemon vs Airflow/Temporal/Prefect — KEEP BORING

**The question from agenda:** "Multi-project orchestration via custom Python daemon
vs Airflow, Temporal, Dagster, Prefect"

Counter-intuitively, the custom Python daemon is the boring choice here.

Airflow: designed for data pipeline DAGs with hundreds of tasks, web UI, celery workers,
metadata database. Operational overhead: substantial. Learning curve: weeks. This would
be spending an innovation token on infrastructure that solves a much harder problem
than we have.

Temporal: event-driven workflow orchestration for distributed systems. Requires its own
server cluster. Design for microservices across multiple machines. Overkill by 3 orders
of magnitude for a 10-project VPS orchestrator.

Prefect: cloud-hosted or self-hosted workflow server, similar story.

The custom daemon is ~400 LOC of Python + pueue. It does exactly what we need:
- poll projects for queued specs
- acquire concurrency slots
- dispatch pueue tasks
- nothing else

The BORING choice is to keep this simple daemon and resist the urge to add features.
The pain is not from the daemon architecture — it's from the lifecycle state management
that lives in callback.py alongside the daemon. Once we move status to SQLite, the
daemon becomes straightforward.

---

### Decision 7: SQLite Schema Management — BORING WINS

**Quote from db.py (audit report finding #28):**
> Нет DB schema versioning; `_MIGRATIONS_APPLIED` — process-global флаг, ресет на рестарт

Current approach: runtime-applied ALTER TABLE statements in `_ensure_migrations()`,
guarded by a process-global boolean that resets on restart. New columns added inline.
No migration history. No `PRAGMA user_version`.

**Boring alternative:**

```python
# In db.py, replace _ensure_migrations() with:
SCHEMA_VERSION = 7  # increment with every structural change

def _apply_migrations(conn: sqlite3.Connection) -> None:
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current >= SCHEMA_VERSION:
        return
    migrations = [
        ("001_initial", "CREATE TABLE IF NOT EXISTS ..."),
        ("002_add_branch", "ALTER TABLE task_log ADD COLUMN branch TEXT"),
        ...
    ]
    for idx, (name, sql) in enumerate(migrations[current:], current + 1):
        conn.execute(sql)
        conn.execute(f"PRAGMA user_version = {idx}")
        conn.commit()
        log.info("Applied migration %s (version %d)", name, idx)
```

PRAGMA user_version is SQLite's built-in schema version field. It is stored in the
database file itself. It persists across restarts. This is the standard boring approach.
Alembic would be overkill for a 5-table SQLite schema owned by one codebase — PRAGMA
user_version with manual migration list is the right level of complexity.

**LLM-native cost:** ~$5, 1 hour. Replace _ensure_migrations() in db.py, add tests.

---

## Dev Pain Points Analysis: Stack Choice vs Design

The deep audit found 85 issues. Let me triage which are caused by stack choice
(and would go away with boring alternatives) vs design problems that would follow
us to any stack.

### Caused by exotic stack choices (go away with boring alternatives)

| Finding | Root Cause | Goes Away With |
|---------|------------|----------------|
| Bug #3: stale-index race in _atomic_write (lifecycle.py:244) | GIT_INDEX_FILE + checkout-index | SQLite transactions |
| `_push_best_effort` on DEBUG, failures invisible | git push as convergence mechanism | SQLite WAL (single machine, no push needed) |
| 8 git subprocess calls with no timeout | git-as-DB architecture | SQLite: one query, timeout via connection_timeout |
| LifecycleWriteRaceError after 3 CAS retries | CAS-on-git-ref architecture | SQLite: serializable transactions |
| `_atomic_write` and `_atomic_write_file` duplication (Coroner #11) | git-as-DB complexity generating two identical implementations | Removed by removing git-as-DB |
| pre-commit guard not deployed anywhere (Cartographer #4) | Node.js hook with manual core.hooksPath | pre-commit framework: `pre-commit install` |
| `allowed_files_hash` always null (Geologist finding) | Dead field from ADR-023 git-DB design | Remove with lifecycle.py |
| `migrate_backlog_to_lifecycle.py` not idempotent (Geologist) | One-shot migration script against git objects | Obviated if we don't migrate to git |

### Caused by design problems (survive any stack migration)

| Finding | Root Cause | Requires |
|---------|------------|----------|
| False-blocked on awardybot/dowry convention (Root 3) | Two incompatible commit conventions | Standardize convention OR change gate logic |
| bootstrap_new_specs reads WT backlog.md without gate (Root 1) | Two writers of "authoritative" state | Single SoR enforced by design |
| TELEGRAM_BOT_TOKEN in git history (Scout #7) | Missing secret hygiene practice | Remove from git, rotate token |
| scripts/vps/tests/ not in CI (Accountant #1) | pyproject.toml testpaths misconfiguration | One-line fix regardless of stack |
| 19 bare except Exception in callback.py (Archaeologist #17) | Grew organically from "always exit 0" INVARIANT | Requires refactor discipline |
| GROWTH prefix not in _SPEC_ID_RE (Cartographer #10) | Regex divergence between modules | common.py constant |
| `reconcile_orphans` writes `by="callback"` (Coroner #23) | Identity misattribution | Fix the constant |

**Key insight:** About half the bugs are directly caused by the git-as-DB choice.
The other half are design hygiene issues that would require fixing regardless.
But the git-as-DB bugs are the CURRENT production incidents (today's 15 fake-done
flips trace through the git-as-DB write path). Fix the stack, and you eliminate the
recurring incident pattern.

---

## Recommended Stack: Keep / Swap / Remove

### Keep

| Component | Why Keep | Boring Level |
|-----------|---------|--------------|
| SQLite (db.py) | Industry standard for single-machine state. WAL mode handles concurrency. Already in use. | Maximum boring |
| pueue task queue | Appropriate tool — concurrency limits, callbacks, persistent task state. Boring for this problem. | Boring for AI task orchestration |
| Custom Python orchestrator daemon (~300 LOC when cleaned up) | NOT the source of pain. Airflow/Temporal are 100x overkill. This IS the boring choice. | Boring |
| claude_agent_sdk | No alternative — unavoidable innovation spend | N/A |
| Python 3.12 | Excellent. Boring. Well documented. | Maximum boring |
| pytest | Boring. Standard. | Maximum boring |
| systemd for daemon management | Boring. Reliable. Standard. | Maximum boring |

### Swap

| Component | Current (Exotic) | Boring Alternative | Why Swap | Migration Cost |
|-----------|-----------------|-------------------|---------|----------------|
| lifecycle.py (602 LOC git-plumbing) | Custom CAS via git plumbing + private GIT_INDEX_FILE | SQLite spec_lifecycle + spec_transitions tables | Eliminates bug class, reduces code by ~500 LOC | $10, 3-4 hours |
| 8-rule gate in verify_status_sync (202 LOC) | 8 inference rules on commit subjects, diff sizes, file paths | `git log origin/develop --grep SPEC-ID` (5 lines) | Handles both commit conventions, no regex maintenance | $5, 1 hour |
| _ensure_migrations() with process-global flag | Inline ALTER TABLE + boolean flag | PRAGMA user_version + ordered migration list | Standard SQLite practice, survives restarts | $5, 1 hour |
| Hand-rolled .git-hooks/ + Node.js scripts | Manual core.hooksPath + .git-hooks/pre-commit | pre-commit framework + .pre-commit-config.yaml | Works everywhere, self-installing, cross-repo | $5, 1 hour |
| callback.py (1374 LOC god module) | 7 responsibilities in one file | Split into gate.py + writer.py + dispatcher.py + auditor.py | LLM context, single responsibility, testability | $15, 4 hours |

### Remove

| Component | Why Remove | What Replaces It |
|-----------|-----------|-----------------|
| spec_operator.py | YAGNI — no real user, complex coupling to callback internals | Direct SQLite mutations for the rare manual case |
| lifecycle.py | Replaced by SQLite | spec_lifecycle table in db.py |
| migrate_backlog_to_lifecycle.py | One-shot migration that's already run (or should have) | Once lifecycle.py is gone, this is irrelevant |
| spec_lint.py | Zombie validator for DLD-CALLBACK-MARKER which ARCH-186 deleted | Remove |
| render_backlog.py | Justified, but only if backlog.md becomes a generated view. Keep if simplified. | Optional: keep as `render_backlog.py` reading SQLite |
| DLD-CALLBACK-MARKER blocks in 23 spec files | ARCH-186 deleted the format, markers are fossils | Batch remove via sed |
| `.worktrees/ARCH-186`, `.worktrees/ARCH-187` | Stale worktrees from completed specs | git worktree remove |

---

## What the Boring Stack Looks Like

**Status SoR after boring migration:**

```
SQLite (orchestrator.db)
  spec_lifecycle table          <- single source of truth for all status
  spec_transitions table        <- audit trail (replaces git log for lifecycle)
  task_log table                <- pueue task history
  callback_decisions table      <- circuit breaker decisions
  sdk_post_result_errors table  <- telemetry

backlog.md                      <- generated view (render_backlog.py reads SQLite)
ai/lifecycle/*.yaml             <- DELETED (status in SQLite)
spec body ## Status:            <- cosmetic/documentation only, never read by code
```

**Gate after boring migration:**

```python
def _is_work_done(project_path: str, spec_id: str) -> bool:
    """Single rule. Handles all commit conventions."""
    r = subprocess.run(
        ["git", "-C", project_path, "log", "origin/develop",
         "--oneline", "--grep", spec_id],
        capture_output=True, text=True, timeout=30, check=False
    )
    return bool(r.stdout.strip())
```

**bootstrap_new_specs after boring migration:**

```python
def bootstrap_new_specs(project_id: str, project_dir: str):
    """Create lifecycle rows for new Spark specs."""
    known = {row["spec_id"] for row in db.get_all_specs(project_id)}
    for spec_md in (Path(project_dir) / "ai" / "features").glob("*.md"):
        m = _SPEC_ID_RE.search(spec_md.name)
        if not m or m.group(0) in known:
            continue
        status = _parse_status_from_spec(spec_md)  # reads spec body, not backlog.md
        db.create_spec(project_id, m.group(0), status)
```

No reading backlog.md. No regex on the working tree. No CAS loop. No git plumbing.

---

## Developer Workflow Assessment

**Current onboarding to this codebase:**

| Milestone | Reality | Target | Root Cause of Gap |
|-----------|---------|--------|-------------------|
| Understand lifecycle flow | 2+ hours (1374 LOC callback, 602 LOC lifecycle, 667 LOC orchestrator) | 30 min | God module, 7 responsibilities |
| Run tests locally | Unclear — scripts/vps/tests/ not in CI, separate run-tests.sh | 5 min | pyproject.toml misconfiguration |
| Understand why a spec is blocked | Hard — _subject_implements logic + 8 rules | Immediate — git log --grep SPEC-ID | 8-rule gate complexity |
| Debug a callback failure | Very hard — 19 bare except, best-effort swallowing, push failures at DEBUG | 15 min with structured errors | Missing typed exceptions |
| Understand status of a spec | Must check 3 places (yaml + backlog + spec body) | One place | Three-layer status |

**LLM agent ergonomics (this is an AI-maintained codebase):**

The audit report explicitly notes this in the Erik (LLM Architect) section:
"callback.py 1374 LOC — это влезает в context window, но может ли coder-агент
понять 7 ответственностей не прочитав весь файл?"

The answer is no. A coder agent working on the gate logic in verify_status_sync
must also load the dispatcher logic, the circuit breaker, the backlog renderer,
and the audit JSONL writer into context. These are unrelated responsibilities.
A 202-LOC function (_verify_status_sync) with 5 embedded rules is not a tool
an LLM can reason about cleanly.

After boring migration:
- gate.py: ~100 LOC, one responsibility (is this spec done?)
- writer.py: ~80 LOC, one responsibility (write new status to SQLite)
- dispatcher.py: ~150 LOC, one responsibility (dispatch QA/Reflect after completion)
- Each file fits in 400-LOC limit. Each has one job. An agent can be pointed at one file.

---

## The Innovation Token Verdict

*counts tokens*

OK, let me count what we actually built in scripts/vps/:

1. Custom Python orchestrator daemon — this is the boring choice relative to Airflow.
   Keep. Half a token.

2. pueue for task queuing — defensible, appropriate tool. Half a token.

3. SQLite for orchestrator state — completely boring. Free.

4. Git as lifecycle DB — one full innovation token, bought us today's incident.
   Spending a token to introduce a bug class that costs us one incident per month
   is negative ROI. Revoke.

5. CAS via git plumbing — this is a consequence of #4. Would not exist without git-as-DB.

6. 8-rule gate — half a token of complexity, bought us systematic false-blocked
   across 460 commits in awardybot. Revoke.

7. Circuit-breaker — legitimate operational concern. Quarter token. Keep.

8. spec_operator.py — quarter token, zero users. Revoke.

We are at ~3.75 tokens on a 3-token budget, and the overrun is entirely in items
that are either causing production incidents or serving no user.

After boring migration:
- Token 1: custom Python orchestrator (justified — Airflow is overkill)
- Token 0.5: pueue (justified — AI task concurrency management)
- Token 0.5: circuit-breaker (justified — operational safety)
- Remaining 1 token: available for a future business-value innovation

The budget goes from 3.75 (overrun) to 2.0 (room to breathe).

---

## Recommended Migration Order (Boring First)

All estimates are LLM-native (agent executes, not human developer team):

### Wave 1 — Zero-Innovation Fixes (this week, ~$10 total)

These fixes don't require architectural decisions. They are unambiguous improvements
regardless of which direction the architectural debate goes.

1. `pyproject.toml: testpaths = ["tests", "scripts/vps/tests"]` — 1 line, ~$1, unlocks 100 tests in CI
2. `tests/conftest.py: autouse DB isolation fixture` — 10 LOC, ~$1
3. Fix `_SPEC_ID_RE` to include GROWTH prefix (or create `common.py` constant) — ~$1
4. `reconcile_orphans` by identity fix: `by="orchestrator"` not `by="callback"` — ~$1
5. Remove spec_lint.py zombie validator + DLD-CALLBACK-MARKER from template/completion.md — ~$2
6. Move TELEGRAM_BOT_TOKEN to Nexus, remove from .env, rotate token — ~$1 + manual token rotation

### Wave 2 — Boring Stack Migration (~$25 total)

7. Replace lifecycle.py with SQLite spec_lifecycle + spec_transitions tables — ~$10
8. Replace 8-rule gate with `git log origin/develop --grep SPEC-ID` — ~$5
9. Replace _ensure_migrations() with PRAGMA user_version + migration list — ~$5
10. Remove spec_operator.py — ~$1
11. bootstrap_new_specs reads SQLite not backlog.md — ~$3 (dependency on Wave 2 #7)
12. Remove migrate_backlog_to_lifecycle.py after data migration — ~$1

### Wave 3 — DX Hardening (~$20 total)

13. Split callback.py into gate.py + writer.py + dispatcher.py + auditor.py — ~$15
14. Add pre-commit framework configuration — ~$5
15. Add timeouts to all subprocess calls in the contour — ~$5
16. Add DB retention for task_log, callback_decisions, sdk_post_result_errors — ~$3

**Total: ~$55 for the full boring migration.**

Compare that to the ongoing cost: one incident per month (audit report: "5-я итерация
фиксов за месяц"), each requiring a 2-hour human investigation, plus the $258/week
false-retry burn documented in BUG-188 (which traced through the same infrastructure).
The boring migration pays back in under 4 weeks at current incident rate.

---

## Cross-Cutting Implications

### For Domain Architecture (Eric)

The god module problem (callback.py, 7 responsibilities) maps directly to the
missing bounded context boundaries. Once we kill lifecycle.py and move status to
SQLite, the natural decomposition becomes visible: gate, writer, dispatcher, auditor
are four separate concerns that happen to share a trigger (pueue callback event).

### For Data Architecture (Martin)

The "single SoR" answer is SQLite. Not because SQLite is philosophically superior
to git-as-DB, but because SQLite is already in the codebase, handles concurrent
writes correctly with WAL mode, has transactions, has foreign keys, and does not
require 8 subprocess calls for a status update. The three-layer status collapses to
zero-layer: one table, one write path.

### For Ops (Charity)

The boring stack is more observable. SQLite queries are instant and don't have
timeout/hang risks. A dead-simple dashboard is `sqlite3 orchestrator.db "SELECT
spec_id, status, updated_at FROM spec_lifecycle ORDER BY updated_at DESC LIMIT 20"`.
No git log parsing. No YAML file system scans.

### For Security (Bruce)

Boring is more secure. The git-as-DB approach required identity enforcement
(ADR-023, ADR-024, ARCH-187) because the write path was complex enough that
unauthorized writes were a plausible threat. SQLite with a single writer process
(the callback) is simpler to reason about: if a process can write to
orchestrator.db, it has filesystem access anyway. The complexity of the identity
enforcement machinery (which doesn't work anywhere — pre-commit guard is dead)
is itself a security smell.

---

## Concerns and Recommendations

### Critical

- **Git-as-DB is causing production incidents.** Today's 15 fake-done flips trace
  directly through the git CAS write path. This is not a configuration problem —
  it is an architectural choice that generates an entire class of race conditions.
  Recommendation: migrate to SQLite in Wave 2.

- **TELEGRAM_BOT_TOKEN in git history.** Already compromised. This has nothing to do
  with the stack debate — it is an immediate P0 security action regardless.

- **scripts/vps/tests/ not in CI.** One-line fix. Unblocks 100 tests that are
  currently not running. This is the cheapest possible improvement with the largest
  regression protection gain.

### Important

- **Do not add more rules to verify_status_sync.** The audit report is explicit:
  "Каждое следующее правило в этом контуре будет иметь негативный ROI." The 9th rule
  will have a new edge case. The boring alternative (git log --grep) removes the
  rule-maintenance treadmill entirely.

- **spec_operator.py is YAGNI.** Zero evidence of use in real workflow. Its existence
  adds maintenance burden and its coupling to callback._reset_circuit_cli is an
  architectural smell that would disappear if callback were decomposed.

### Questions for Clarification

- Is the multi-machine convergence use case real? The git-as-DB approach was justified
  by "multiple machines can sync via git push." If this is theoretical rather than
  operational, it removes the last justification for lifecycle.py.

- What is the actual human interaction model for the rare "force-done" operation?
  If the answer is "I edit the YAML directly," then spec_operator.py is confirmed YAGNI.
  If someone actually uses spec_operator.py demote, that changes the removal calculus.

---

## References

- Dan McKinley — Choose Boring Technology (mcfunley.com/choose-boring-technology)
- Deep Audit Report: `/home/dld/projects/dld/ai/audit/deep-audit-report.md`
- Architecture Agenda: `/home/dld/projects/dld/ai/architect/architecture-agenda.md`
- lifecycle.py source: `/home/dld/projects/dld/scripts/vps/lifecycle.py`
- callback.py source: `/home/dld/projects/dld/scripts/vps/callback.py`
- orchestrator.py source: `/home/dld/projects/dld/scripts/vps/orchestrator.py`
- SQLite WAL documentation: sqlite.org/wal.html
- pre-commit framework: pre-commit.com
- ADR-023 (lifecycle SoT via git-YAML): `/home/dld/projects/dld/.claude/rules/architecture.md`
