---
id: TECH-171
type: TECH
status: done
priority: P1
risk: R2
created: 2026-05-02
---

# TECH-171 — Guard structured audit log + daily digest

**Status:** done
**Priority:** P1
**Risk:** R2

---

## Problem

Сейчас решения guard'а видны только в `callback-debug.log` среди всего шума (USAGE/skill detection/etc.). False-positive demote ловится не быстрее чем через ручной аудит репо одного из проектов. Нет дашборда / алёрта на "что-то странное случилось вчера".

---

## Goal

1. **Structured audit log** — JSONL файл `scripts/vps/callback-audit.jsonl`, одна строка на каждое решение `verify_status_sync`:
   ```json
   {
     "ts": "2026-05-02T10:30:00Z",
     "project_id": "awardybot",
     "spec_id": "FTR-897",
     "pueue_id": 1409,
     "target_in": "done",
     "target_out": "blocked",
     "reason": "no_implementation_commits",
     "allowed_count": 16,
     "code_loc": 0,
     "test_loc": 0,
     "code_commits": 0,
     "started_at": "2026-05-01T19:31:45Z",
     "duration_ms": 234
   }
   ```

   - Append-only, line-delimited JSON.
   - Ротация: log-rotate by date, держим 30 дней.
   - Path в `.env`: `CALLBACK_AUDIT_LOG=/home/dld/projects/dld/scripts/vps/callback-audit.jsonl`.

2. **Daily digest** (cron @ 09:00 MSK):
   - Скрипт `scripts/vps/audit_digest.py` читает последние 24h JSONL.
   - Группирует по project + verdict.
   - Шлёт Telegram message через event_writer с summary:
     ```
     📊 Callback digest 02.05 (last 24h)
     awardybot: 12 done ✓, 1 demote (FTR-897 → blocked, no_impl)
     dowry:     3 done ✓, 0 demote
     gipotenuza: 5 done ✓, 0 demote
     wb:        0 done ✓, 4 demote (ARCH-176a/b/c/d, no_impl)
     ```
   - При наличии demote — линк на JSONL для детального просмотра.

3. **Per-callback metric** в audit_log: `code_loc` / `test_loc` / `code_commits` (через numstat, как в моём аудите 02.05) — это будущий semantic signal, не только бинарный has_commits.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/audit_digest.py`
- `scripts/vps/event_writer.py`
- `scripts/vps/.env.example`
- `scripts/vps/setup-vps.sh`
- `tests/unit/test_audit_log_format.py`
- `tests/integration/test_audit_digest.py`

---

## Tasks

1. **Audit logger** в callback.py: helper `_write_audit(record: dict)` — append JSON line, atomic write.
2. **Numstat aggregation** в `_has_implementation_commits` — расширить return до `(bool, code_loc, test_loc, code_commits)` или separate helper.
3. **Hook в `verify_status_sync`** — собрать record, вызвать `_write_audit` ровно один раз per callback (после всех guards и решений).
4. **`audit_digest.py`**: argparse, чтение JSONL, группировка, Telegram отправка через event_writer.
5. **Cron entry**: добавить в `setup-vps.sh --phase3` строку `0 9 * * *` для digest.
6. **Logrotate config** для audit JSONL.
7. **Tests**: формат строк, агрегация digest'а на synthetic input.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Каждый `verify_status_sync` пишет ровно 1 JSON line |
| EC-2 | deterministic | Запись содержит все required keys (см. Goal) |
| EC-3 | integration | digest скрипт корректно агрегирует mocked JSONL за 24h |
| EC-4 | integration | Cron entry добавлен в crontab (idempotent) |
| EC-5 | integration | logrotate чистит файлы старше 30 дней |

---

## Drift Log

**Checked:** 2026-05-02 14:00 UTC
**Result:** no_drift

All Allowed Files exist and match spec assumptions. `verify_status_sync` and `_has_implementation_commits` in `scripts/vps/callback.py` are present and have the expected signatures. `event_writer.notify` API is stable. `setup-vps.sh --phase3` block exists with cron-installation pattern that we will reuse.

### References Updated
- (none)

---

## Implementation Plan

Eight bite-sized tasks, ordered by dependency. Tasks 1–3 form the audit-write path inside `callback.py`. Task 4 builds the read/digest path. Tasks 5–6 do install/ops wiring. Tasks 7–8 are tests + env doc.

Execution order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 (7 can run in parallel with 4–6).

---

### Task 1: `_write_audit(record)` helper in callback.py

**Files:**
- Modify: `scripts/vps/callback.py` (add helper near `_get_started_at`, ~line 700)

**Context:**
Atomic append-line JSONL writer. Path resolved from `CALLBACK_AUDIT_LOG` env (default `<SCRIPT_DIR>/callback-audit.jsonl`). Must never raise — callback invariant is "always exit 0".

**Step 1: Add helper**

```python
# Place AFTER _get_started_at, BEFORE _has_implementation_commits.

_AUDIT_LOG_DEFAULT = SCRIPT_DIR / "callback-audit.jsonl"


def _audit_log_path() -> Path:
    """Resolve audit log path from env, fallback to SCRIPT_DIR/callback-audit.jsonl."""
    raw = os.environ.get("CALLBACK_AUDIT_LOG", "").strip()
    return Path(raw) if raw else _AUDIT_LOG_DEFAULT


def _write_audit(record: dict) -> None:
    """Append one JSON line to the audit log. Never raises.

    Atomic per-line write: open in 'a' mode + single write() of one line.
    POSIX append on a single write() under PIPE_BUF (4096 bytes) is atomic;
    our records are well under that. We do NOT fsync — daily digest is fine
    with a few seconds of OS buffer lag.
    """
    try:
        path = _audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception as exc:  # noqa: BLE001 — callback must never crash
        log.warning("AUDIT: write failed: %s", exc)
```

**Step 2: Smoke verify**

```bash
cd /home/dld/projects/dld-TECH-171
CALLBACK_AUDIT_LOG=/tmp/audit-smoke.jsonl python3 -c "
import sys; sys.path.insert(0, 'scripts/vps')
import callback
callback._write_audit({'ts': '2026-05-02T00:00:00Z', 'project_id': 'x', 'spec_id': 'TECH-1'})
print(open('/tmp/audit-smoke.jsonl').read())
"
```

Expected: one JSON line, valid JSON.

**Acceptance:**
- [ ] `_audit_log_path` honors `CALLBACK_AUDIT_LOG`, falls back to `SCRIPT_DIR/callback-audit.jsonl`.
- [ ] `_write_audit` appends a single `\n`-terminated line.
- [ ] Read-only-fs / missing-dir / non-serializable input → caught, logged, no exception.

---

### Task 2: Numstat aggregation in `_has_implementation_commits`

**Files:**
- Modify: `scripts/vps/callback.py:720-772` (extend `_has_implementation_commits` + add `_commit_stats`)

**Context:**
The guard currently returns `bool` from `git log -- <allowed>`. We need code/test LOC and commit-count for the audit record. Keep the existing `bool` API back-compat — add a new sibling helper that returns the stats. `verify_status_sync` will call BOTH (cheap; same git invocation pattern, runs once each).

**Step 1: Add `_commit_stats` helper directly below `_has_implementation_commits`**

```python
def _commit_stats(
    project_path: str,
    allowed: list[str] | None,
    started_at: str | None,
    branches: str = "all",
) -> tuple[int, int, int]:
    """Return (code_loc, test_loc, code_commits) for commits since started_at.

    Uses `git log --numstat` over the same scope as `_has_implementation_commits`.
    Heuristic split: a path is "test" if its first segment is `tests` or its
    basename starts with `test_` or ends with `_test.py` / `.test.ts` /
    `.spec.ts`. Everything else is "code".

    Degrade-open: any infra error returns (0, 0, 0). Caller still has the
    bool from `_has_implementation_commits` for the demotion decision.
    """
    if not allowed or started_at is None:
        return (0, 0, 0)

    cmd = ["git", "-C", project_path, "log"]
    if branches == "all":
        cmd.append("--all")
    elif branches == "develop":
        cmd.append("develop")
    cmd += [
        f"--since={started_at}",
        "--pretty=format:__COMMIT__%H",
        "--numstat",
        "--",
        *allowed,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("AUDIT_STATS: git log failed: %s", exc)
        return (0, 0, 0)
    if r.returncode != 0:
        return (0, 0, 0)

    code_loc = 0
    test_loc = 0
    commits: set[str] = set()
    for line in r.stdout.splitlines():
        if line.startswith("__COMMIT__"):
            commits.add(line[len("__COMMIT__"):].strip())
            continue
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added_s, removed_s, path = parts
        if added_s == "-" or removed_s == "-":
            continue  # binary file
        try:
            delta = int(added_s) + int(removed_s)
        except ValueError:
            continue
        if _is_test_path(path):
            test_loc += delta
        else:
            code_loc += delta
    return (code_loc, test_loc, len(commits))


def _is_test_path(path: str) -> bool:
    """Heuristic: tests/ dir, test_*.py, *_test.py, *.test.ts, *.spec.ts, *.spec.js."""
    base = path.rsplit("/", 1)[-1]
    if path.startswith("tests/") or "/tests/" in path:
        return True
    if base.startswith("test_") and base.endswith(".py"):
        return True
    if base.endswith("_test.py"):
        return True
    if base.endswith((".test.ts", ".test.tsx", ".test.js", ".spec.ts", ".spec.tsx", ".spec.js")):
        return True
    return False
```

**Step 2: Verify back-compat of `_has_implementation_commits`**

We do NOT modify its signature — existing callers (verify_status_sync) keep working. `_commit_stats` is additive.

```bash
grep -n "_has_implementation_commits\|_commit_stats\|_is_test_path" scripts/vps/callback.py
```

Expected: original definition intact, two new helpers below it.

**Acceptance:**
- [ ] `_has_implementation_commits` signature & behavior unchanged.
- [ ] `_commit_stats(...)` returns `(int, int, int)`.
- [ ] Empty allowlist or `started_at=None` → `(0, 0, 0)`.
- [ ] Binary files (numstat `-`) skipped without crashing.

---

### Task 3: Hook into `verify_status_sync` — write exactly one record

**Files:**
- Modify: `scripts/vps/callback.py:807-919` (function `verify_status_sync`)

**Context:**
The audit record must be written exactly ONCE per callback invocation, AFTER all guards have decided `target_out`. We capture `target_in` at function entry, run the existing logic, then build + write the record at the end (covering all return paths).

**Step 1: Refactor `verify_status_sync` to capture inputs and route through one exit point**

Replace the function body (keep signature). Key changes:
1. Capture `target_in = target` at top.
2. Capture `start_wall = time.monotonic()` at top.
3. Compute `allowed`, `started_at`, `code_loc`, `test_loc`, `code_commits` in the impl-guard branch (only when `target=='done'` originally).
4. Replace each early `return` with `return _emit_audit(...)`.
5. At end, call `_emit_audit(...)` with final `target_out`.

```python
import time  # add to imports at top of file if not present


def _emit_audit(
    *,
    project_path: str,
    spec_id: str,
    target_in: str,
    target_out: str,
    reason: str,
    pueue_id: int | None,
    allowed_count: int,
    code_loc: int,
    test_loc: int,
    code_commits: int,
    started_at: str | None,
    start_wall: float,
) -> None:
    """Build and write the audit record. Always returns None."""
    from datetime import datetime, timezone
    record = {
        "ts": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "project_id": Path(project_path).name,
        "spec_id": spec_id,
        "pueue_id": pueue_id,
        "target_in": target_in,
        "target_out": target_out,
        "reason": reason,
        "allowed_count": allowed_count,
        "code_loc": code_loc,
        "test_loc": test_loc,
        "code_commits": code_commits,
        "started_at": started_at,
        "duration_ms": int((time.monotonic() - start_wall) * 1000),
    }
    _write_audit(record)
```

**Step 2: Patch `verify_status_sync` to call `_emit_audit` on every exit**

```python
def verify_status_sync(
    project_path: str,
    spec_id: str,
    target: str = "done",
    pueue_id: int | None = None,
) -> None:
    target_in = target
    start_wall = time.monotonic()
    reason = "ok"
    allowed_count = 0
    code_loc = 0
    test_loc = 0
    code_commits = 0
    started_at: str | None = None

    p = Path(project_path)
    spec_files = list(p.glob(f"ai/features/{spec_id}*.md"))
    spec_file = spec_files[0] if spec_files else None
    spec_rel = str(spec_file.relative_to(p)) if spec_file else None
    spec_head = _read_head_blob(project_path, spec_rel) if spec_rel else None
    if not spec_files:
        log.warning("STATUS_SYNC: spec file not found for %s", spec_id)

    backlog_path = p / "ai" / "backlog.md"
    backlog_rel = "ai/backlog.md"
    backlog_head = _read_head_blob(project_path, backlog_rel) if backlog_path.is_file() else None
    if backlog_head is None and not backlog_path.is_file():
        log.warning("STATUS_SYNC: backlog.md not found in %s", project_path)

    spec_text = spec_head
    backlog_text = backlog_head

    # Implementation guard
    if target == "done" and spec_text is not None and pueue_id is not None and spec_file:
        allowed = _parse_allowed_files(spec_file)
        allowed_count = 0 if allowed is None else len(allowed)
        started_at = _get_started_at(int(pueue_id))
        code_loc, test_loc, code_commits = _commit_stats(project_path, allowed, started_at)
        if not _has_implementation_commits(project_path, allowed, started_at):
            reason = (
                "missing_allowed_files_section" if allowed is None else "no_implementation_commits"
            )
            log.warning("IMPL_GUARD: %s — demoting done → blocked (%s)", spec_id, reason)
            _, spec_text = _apply_blocked_reason(spec_text, reason)
            target = "blocked"
        else:
            if is_merged_to_develop(project_path, spec_id):
                log.info("IMPL_GUARD: %s — commits found and merged to develop ✓", spec_id)
            else:
                log.warning(
                    "IMPL_GUARD: %s has commits on feature branch but NOT merged to develop yet",
                    spec_id,
                )

    # Spec-authority guards
    if target == "done" and spec_text is not None:
        if re.search(r"\*\*Status:\*\*\s*blocked", spec_text, re.IGNORECASE):
            log.info("STATUS_SYNC: %s — spec is blocked at HEAD, skipping done", spec_id)
            _resync_backlog_to_spec(project_path, spec_id, "blocked", backlog_path)
            return _emit_audit(
                project_path=project_path, spec_id=spec_id, target_in=target_in,
                target_out="blocked", reason="spec_authority_blocked",
                pueue_id=pueue_id, allowed_count=allowed_count,
                code_loc=code_loc, test_loc=test_loc, code_commits=code_commits,
                started_at=started_at, start_wall=start_wall,
            )
    if target == "blocked" and spec_text is not None:
        if re.search(r"\*\*Status:\*\*\s*done", spec_text, re.IGNORECASE):
            log.info("STATUS_SYNC: %s — spec already done at HEAD, skipping blocked", spec_id)
            _resync_backlog_to_spec(project_path, spec_id, "done", backlog_path)
            return _emit_audit(
                project_path=project_path, spec_id=spec_id, target_in=target_in,
                target_out="done", reason="spec_authority_done",
                pueue_id=pueue_id, allowed_count=allowed_count,
                code_loc=code_loc, test_loc=test_loc, code_commits=code_commits,
                started_at=started_at, start_wall=start_wall,
            )

    # Apply + commit
    if spec_text is not None:
        ok_spec, spec_text = _apply_spec_status(spec_text, target)
        if not ok_spec:
            log.warning("STATUS_FIX: could not patch spec status for %s", spec_id)
    if backlog_text is not None:
        ok_bl, backlog_text = _apply_backlog_status(backlog_text, spec_id, target)
        if not ok_bl:
            log.warning("STATUS_FIX: could not patch backlog row for %s", spec_id)

    fixes: list[tuple[str, str]] = []
    if spec_rel and spec_head is not None and spec_text is not None and spec_text != spec_head:
        fixes.append((spec_rel, spec_text))
    if backlog_head is not None and backlog_text is not None and backlog_text != backlog_head:
        fixes.append((backlog_rel, backlog_text))

    if not fixes:
        log.info("STATUS_SYNC: %s — both spec and backlog are %s ✓", spec_id, target)
    else:
        log.warning("STATUS_SYNC: %s — auto-fixed %d file(s) → %s", spec_id, len(fixes), target)
        _git_commit_push(project_path, spec_id, target, fixes)

    _emit_audit(
        project_path=project_path, spec_id=spec_id, target_in=target_in,
        target_out=target, reason=reason if target == target_in or reason != "ok" else "ok",
        pueue_id=pueue_id, allowed_count=allowed_count,
        code_loc=code_loc, test_loc=test_loc, code_commits=code_commits,
        started_at=started_at, start_wall=start_wall,
    )
```

**Step 3: Smoke test by running existing callback unit tests**

```bash
cd /home/dld/projects/dld-TECH-171
python3 -m pytest tests/unit/test_callback*.py -x -q
```

Expected: PASS (we did not change external behavior).

**Acceptance:**
- [ ] Every code path in `verify_status_sync` calls `_emit_audit` exactly once.
- [ ] `target_in` always recorded as the original incoming target.
- [ ] When demote fires, `reason` is `no_implementation_commits` or `missing_allowed_files_section`.
- [ ] When spec-authority guard fires, `reason` is `spec_authority_blocked` or `spec_authority_done`.
- [ ] Happy path: `reason="ok"`, `target_out == target_in`.
- [ ] Existing callback tests still pass.

---

### Task 4: New `scripts/vps/audit_digest.py`

**Files:**
- Create: `scripts/vps/audit_digest.py`

**Context:**
Read last 24h of JSONL, group by `project_id` × `verdict` (verdict = "demote" if `target_in != target_out`, else "done"), produce a human summary, deliver via `event_writer.notify(...)` with skill="audit-digest", status="done".

**Step 1: Implement script**

```python
#!/usr/bin/env python3
"""
Module: audit_digest
Role: Daily digest of callback audit log — Telegram via OpenClaw event.
Uses: event_writer (notify), stdlib (json, argparse, datetime)
Used by: cron (0 9 * * *), operator CLI

CLI: python3 audit_digest.py [--log <path>] [--hours 24] [--project-path <path>]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import event_writer  # noqa: E402

DEFAULT_LOG = SCRIPT_DIR / "callback-audit.jsonl"


def _resolve_log_path(cli_path: str | None) -> Path:
    if cli_path:
        return Path(cli_path)
    raw = os.environ.get("CALLBACK_AUDIT_LOG", "").strip()
    return Path(raw) if raw else DEFAULT_LOG


def _parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def read_records(log_path: Path, hours: int) -> list[dict]:
    """Read JSONL, return records with ts within the last `hours`."""
    if not log_path.is_file():
        return []
    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=hours)
    out: list[dict] = []
    with open(log_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_ts(rec.get("ts", ""))
            if ts is None or ts < cutoff:
                continue
            out.append(rec)
    return out


def aggregate(records: list[dict]) -> dict[str, dict]:
    """Group by project_id → {done: int, demotes: list[(spec_id, reason)]}."""
    agg: dict[str, dict] = defaultdict(lambda: {"done": 0, "demotes": []})
    for r in records:
        project = r.get("project_id", "?")
        target_in = r.get("target_in")
        target_out = r.get("target_out")
        if target_in == "done" and target_out == "done":
            agg[project]["done"] += 1
        elif target_in == "done" and target_out == "blocked":
            agg[project]["demotes"].append(
                (r.get("spec_id", "?"), r.get("reason", "?"))
            )
    return dict(agg)


def render(agg: dict[str, dict], log_path: Path, hours: int) -> str:
    """Render the human summary string."""
    today = datetime.now(tz=timezone.utc).strftime("%d.%m")
    lines = [f"📊 Callback digest {today} (last {hours}h)"]
    if not agg:
        lines.append("(no autopilot callbacks in window)")
        return "\n".join(lines)
    width = max(len(p) for p in agg) + 1
    has_demote = False
    for project in sorted(agg):
        data = agg[project]
        done = data["done"]
        demotes = data["demotes"]
        if demotes:
            has_demote = True
            details = ", ".join(f"{sid}→blocked ({reason})" for sid, reason in demotes)
            lines.append(
                f"{project:<{width}} {done} done ✓, {len(demotes)} demote ({details})"
            )
        else:
            lines.append(f"{project:<{width}} {done} done ✓, 0 demote")
    if has_demote:
        lines.append("")
        lines.append(f"Detail: {log_path}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily callback audit digest")
    parser.add_argument("--log", default=None, help="Path to JSONL (else env CALLBACK_AUDIT_LOG)")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours")
    parser.add_argument(
        "--project-path",
        default=str(SCRIPT_DIR.parent.parent),
        help="Project root for OpenClaw event (default: repo root above scripts/vps)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print summary, do not notify")
    args = parser.parse_args()

    log_path = _resolve_log_path(args.log)
    records = read_records(log_path, args.hours)
    agg = aggregate(records)
    summary = render(agg, log_path, args.hours)
    print(summary)
    if args.dry_run:
        return 0
    try:
        event_writer.notify(args.project_path, "audit-digest", "done", summary, "")
    except Exception as exc:  # noqa: BLE001
        print(f"notify failed (non-fatal): {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 2: Verify**

```bash
cd /home/dld/projects/dld-TECH-171
chmod +x scripts/vps/audit_digest.py
python3 scripts/vps/audit_digest.py --log /tmp/audit-smoke.jsonl --hours 24 --dry-run
```

Expected: prints `📊 Callback digest …` (or "no autopilot callbacks in window").

**Acceptance:**
- [ ] `--dry-run` prints summary, doesn't call event_writer.
- [ ] Records older than `--hours` excluded.
- [ ] Demote line includes spec_id and reason.
- [ ] Nonexistent log file → empty summary, exit 0 (no crash).

---

### Task 5: Cron entry in `setup-vps.sh --phase3`

**Files:**
- Modify: `scripts/vps/setup-vps.sh:68-76` (insert after the nexus-cache cron block)

**Context:**
Append idempotent cron line `0 9 * * *` calling `audit_digest.py` via project venv. Idempotency: filter out any prior `audit_digest` line before writing the new crontab.

**Step 1: Insert block right after step "5. Install cron for nexus-cache-refresh.sh"**

Locate (around line 76):

```bash
    else
        warn "nexus-cache-refresh.sh not found — cron not installed"
    fi

    # 6. GEMINI_API_KEY in .env
```

Insert before "# 6. GEMINI_API_KEY in .env":

```bash
    # 5b. Install cron for audit_digest.py (TECH-171)
    DIGEST_SCRIPT="${SCRIPT_DIR}/audit_digest.py"
    DIGEST_LOG="/var/log/dld-orchestrator/audit-digest.log"
    if [[ -f "$DIGEST_SCRIPT" ]]; then
        sudo mkdir -p "$(dirname "$DIGEST_LOG")" 2>/dev/null \
            || mkdir -p "$(dirname "$DIGEST_LOG")" 2>/dev/null || true
        DIGEST_CRON="0 9 * * * ${SCRIPT_DIR}/venv/bin/python3 ${DIGEST_SCRIPT} >> ${DIGEST_LOG} 2>&1"
        (crontab -l 2>/dev/null | grep -v "audit_digest"; echo "$DIGEST_CRON") | crontab -
        ok "Cron installed: audit_digest.py at 09:00 daily"
    else
        warn "audit_digest.py not found — digest cron not installed"
    fi
```

Renumber subsequent comments accordingly (6 → 7, 7 → 8) for clarity.

**Step 2: Verify idempotency**

```bash
crontab -l | grep -c audit_digest   # before
bash scripts/vps/setup-vps.sh --phase3
crontab -l | grep -c audit_digest   # should be exactly 1
bash scripts/vps/setup-vps.sh --phase3
crontab -l | grep -c audit_digest   # still exactly 1
```

**Acceptance:**
- [ ] Running `--phase3` twice produces exactly one `audit_digest` line.
- [ ] Cron uses `venv/bin/python3`.
- [ ] Log dir created.

---

### Task 6: Logrotate config (30-day retention)

**Files:**
- Create: `scripts/vps/logrotate.callback-audit` (template, deployed by setup-vps.sh)
- Modify: `scripts/vps/setup-vps.sh` (--phase3 block: install logrotate config)

**Context:**
Use system logrotate (`/etc/logrotate.d/dld-callback-audit`). Daily rotation, 30 days kept, missingok, no compress (tiny file), copytruncate (so the open append handle in callback.py keeps working without HUP).

**Step 1: Create template**

```
# scripts/vps/logrotate.callback-audit
# Installed to /etc/logrotate.d/dld-callback-audit by setup-vps.sh --phase3.
# {{LOG_PATH}} is replaced at install time.

{{LOG_PATH}} {
    daily
    rotate 30
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y-%m-%d
}
```

**Step 2: Add install block in `setup-vps.sh --phase3` (right after the digest-cron block)**

```bash
    # 5c. Install logrotate config for callback-audit.jsonl (TECH-171)
    AUDIT_LOG_PATH="${CALLBACK_AUDIT_LOG:-${SCRIPT_DIR}/callback-audit.jsonl}"
    LOGROTATE_TEMPLATE="${SCRIPT_DIR}/logrotate.callback-audit"
    LOGROTATE_TARGET="/etc/logrotate.d/dld-callback-audit"
    if [[ -f "$LOGROTATE_TEMPLATE" ]]; then
        if command -v sudo &>/dev/null && [[ -w /etc/logrotate.d || $EUID -eq 0 ]] \
            || sudo -n true 2>/dev/null; then
            sed "s|{{LOG_PATH}}|${AUDIT_LOG_PATH}|g" "$LOGROTATE_TEMPLATE" \
                | sudo tee "$LOGROTATE_TARGET" >/dev/null
            ok "Logrotate config installed: $LOGROTATE_TARGET (30-day retention)"
        else
            warn "Cannot write $LOGROTATE_TARGET (no sudo) — skip; install manually:"
            echo "  sudo cp $LOGROTATE_TEMPLATE $LOGROTATE_TARGET"
        fi
    fi
```

**Step 3: Dry-run**

```bash
sudo logrotate -d /etc/logrotate.d/dld-callback-audit
```

Expected: prints planned actions, no errors.

**Acceptance:**
- [ ] `/etc/logrotate.d/dld-callback-audit` installed with substituted log path.
- [ ] `logrotate -d` validates without warnings.
- [ ] `copytruncate` present (so callback's open file handle stays valid).
- [ ] Re-running --phase3 overwrites idempotently.

---

### Task 7: Tests

**Files:**
- Create: `tests/unit/test_audit_log_format.py`
- Create: `tests/integration/test_audit_digest.py`

**Step 1: Unit — record schema**

```python
# tests/unit/test_audit_log_format.py
"""TECH-171 — verify audit JSONL record schema and one-line-per-callback contract."""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "vps"))

import callback  # noqa: E402

REQUIRED_KEYS = {
    "ts", "project_id", "spec_id", "pueue_id",
    "target_in", "target_out", "reason",
    "allowed_count", "code_loc", "test_loc", "code_commits",
    "started_at", "duration_ms",
}


def test_write_audit_appends_one_line(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(log_file))

    callback._write_audit({"ts": "2026-05-02T00:00:00Z", "project_id": "x", "spec_id": "TECH-1"})
    callback._write_audit({"ts": "2026-05-02T00:00:01Z", "project_id": "x", "spec_id": "TECH-2"})

    lines = log_file.read_text().splitlines()
    assert len(lines) == 2
    for line in lines:
        rec = json.loads(line)
        assert "spec_id" in rec


def test_write_audit_never_raises(tmp_path, monkeypatch):
    bad_path = tmp_path / "no" / "such" / "dir" / "log.jsonl"
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(bad_path))
    # Should auto-mkdir and succeed
    callback._write_audit({"ts": "x", "project_id": "y", "spec_id": "z"})
    assert bad_path.is_file()


def test_emit_audit_record_has_all_required_keys(tmp_path, monkeypatch):
    log_file = tmp_path / "audit.jsonl"
    monkeypatch.setenv("CALLBACK_AUDIT_LOG", str(log_file))

    callback._emit_audit(
        project_path="/tmp/proj-x",
        spec_id="TECH-99",
        target_in="done",
        target_out="blocked",
        reason="no_implementation_commits",
        pueue_id=42,
        allowed_count=3,
        code_loc=10,
        test_loc=5,
        code_commits=1,
        started_at="2026-05-02T00:00:00Z",
        start_wall=0.0,
    )
    rec = json.loads(log_file.read_text().splitlines()[0])
    assert REQUIRED_KEYS.issubset(rec.keys())
    assert rec["target_in"] == "done"
    assert rec["target_out"] == "blocked"
    assert rec["reason"] == "no_implementation_commits"
    assert rec["pueue_id"] == 42
    assert isinstance(rec["duration_ms"], int)


def test_is_test_path_heuristic():
    assert callback._is_test_path("tests/unit/test_x.py")
    assert callback._is_test_path("src/foo/test_bar.py")
    assert callback._is_test_path("src/foo/bar_test.py")
    assert callback._is_test_path("web/x.spec.ts")
    assert not callback._is_test_path("src/foo/bar.py")
    assert not callback._is_test_path("scripts/vps/callback.py")
```

**Step 2: Integration — digest aggregation**

```python
# tests/integration/test_audit_digest.py
"""TECH-171 — synthetic JSONL → digest summary."""

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DIGEST = REPO_ROOT / "scripts" / "vps" / "audit_digest.py"


def _ts(delta_h: float) -> str:
    return (datetime.now(tz=timezone.utc) - timedelta(hours=delta_h)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )


def test_digest_aggregates_done_and_demote(tmp_path):
    log = tmp_path / "audit.jsonl"
    records = [
        {"ts": _ts(1), "project_id": "awardybot", "spec_id": "FTR-1",
         "target_in": "done", "target_out": "done", "reason": "ok"},
        {"ts": _ts(2), "project_id": "awardybot", "spec_id": "FTR-2",
         "target_in": "done", "target_out": "done", "reason": "ok"},
        {"ts": _ts(3), "project_id": "awardybot", "spec_id": "FTR-897",
         "target_in": "done", "target_out": "blocked",
         "reason": "no_implementation_commits"},
        {"ts": _ts(48), "project_id": "awardybot", "spec_id": "FTR-OLD",
         "target_in": "done", "target_out": "done", "reason": "ok"},  # outside window
        {"ts": _ts(5), "project_id": "wb", "spec_id": "ARCH-176a",
         "target_in": "done", "target_out": "blocked",
         "reason": "no_implementation_commits"},
    ]
    log.write_text("\n".join(json.dumps(r) for r in records) + "\n")

    r = subprocess.run(
        [sys.executable, str(DIGEST), "--log", str(log), "--hours", "24", "--dry-run"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    out = r.stdout
    assert "Callback digest" in out
    assert "awardybot" in out
    assert "2 done" in out
    assert "1 demote" in out
    assert "FTR-897" in out
    assert "wb" in out
    assert "ARCH-176a" in out
    assert "FTR-OLD" not in out  # outside window


def test_digest_empty_log(tmp_path):
    log = tmp_path / "empty.jsonl"
    log.write_text("")
    r = subprocess.run(
        [sys.executable, str(DIGEST), "--log", str(log), "--hours", "24", "--dry-run"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    assert "no autopilot callbacks" in r.stdout


def test_digest_missing_log(tmp_path):
    log = tmp_path / "missing.jsonl"  # never created
    r = subprocess.run(
        [sys.executable, str(DIGEST), "--log", str(log), "--hours", "24", "--dry-run"],
        capture_output=True, text=True, timeout=30, check=True,
    )
    assert r.returncode == 0
```

**Step 3: Run**

```bash
cd /home/dld/projects/dld-TECH-171
python3 -m pytest tests/unit/test_audit_log_format.py tests/integration/test_audit_digest.py -v
```

Expected: all pass.

**Acceptance:**
- [ ] Unit tests cover schema, append-only, no-raise contract, test-path heuristic.
- [ ] Integration test synthesizes JSONL and asserts digest output content.
- [ ] No mocks in integration test (ADR-013 — uses real subprocess).

---

### Task 8: `.env.example` — document `CALLBACK_AUDIT_LOG`

**Files:**
- Modify: `scripts/vps/.env.example` (append after line 28)

**Step 1: Append**

```bash
# Callback audit log (TECH-171)
# JSONL stream of every verify_status_sync decision (one line per callback).
# Read by audit_digest.py at 09:00 daily. Logrotate keeps 30 days.
# Default: <SCRIPT_DIR>/callback-audit.jsonl
CALLBACK_AUDIT_LOG=/home/ubuntu/scripts/vps/callback-audit.jsonl
```

**Acceptance:**
- [ ] `.env.example` documents `CALLBACK_AUDIT_LOG` with default path comment.
- [ ] No real secrets present.

---

### Execution Order

```
Task 1 (write helper)
  └─> Task 2 (commit stats)
        └─> Task 3 (hook into verify_status_sync)
              ├─> Task 4 (audit_digest.py)        ┐
              │     └─> Task 5 (cron)             │
              │           └─> Task 6 (logrotate)  │
              ├─> Task 7 (tests)  ────────────────┤  parallel
              └─> Task 8 (.env doc) ──────────────┘
```

### Dependencies

- Task 2, 3 depend on Task 1 (`_write_audit`).
- Task 3 depends on Task 2 (`_commit_stats`, `_is_test_path`).
- Task 4 depends on Task 3 (record format must be stable).
- Task 5 depends on Task 4 (script must exist for cron to call it).
- Task 6 may run after Task 5 or in parallel (independent file).
- Task 7 depends on Tasks 1–4 (tests reference both helpers and digest CLI).
- Task 8 is independent (doc only).

### Research Sources

- ADR-013 (Mock ban in integration tests) — informs Task 7 design.
- ADR-018 (Callback status enforcement) — describes guard semantics being audited.
- Existing pattern: `setup-vps.sh --phase3` cron install for `nexus-cache-refresh.sh` (lines 68–76) — reused verbatim shape for digest cron.
- POSIX append-mode write atomicity for sub-PIPE_BUF lines — well-established (man 2 write). Audit lines stay under 1 KB.
