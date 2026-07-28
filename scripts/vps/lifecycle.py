"""
Module: lifecycle
Role: Atomic git-plumbing writer for per-spec lifecycle YAML state files.
      Stores state in ai/lifecycle/{spec_id}.yaml via private GIT_INDEX_FILE.
      CAS update-ref prevents race conditions. After each write, syncs the
      working tree via `git checkout HEAD -- <path>` (TECH-194 Layer D fix).
      Identity enforcement: only _ALLOWED_WRITERS may call write functions (ADR-025).
      Rule 7 structural: done is terminal — LifecycleAlreadyDoneError raised on
      any non-done transition when HEAD yaml already shows status="done" (ARCH-193).

Uses:
  - pathlib: Path
  - subprocess: run (git plumbing commands)
  - yaml: safe_load, safe_dump
  - tempfile: NamedTemporaryFile
  - os: environ, unlink
  - datetime: now, timezone

Used by:
  - callback.py: write_lifecycle(), read_lifecycle()
  - orchestrator.py: create_initial(), list_by_status(),
                     assert_clean_lifecycle_tree(), reconcile_orphans()
  - render_backlog.py: read_lifecycle(), list_by_status()
  - migrate_backlog_to_lifecycle.py: create_initial(), write_lifecycle()

Glossary: ai/glossary/orchestrator.md
"""

import logging
import os
import random
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Optional

import yaml
from lifecycle_const import (  # noqa: F401 — re-export: read via lifecycle.<NAME>
    _ALLOWED_WRITERS,
    _ALLOWED_WRITERS_FOR_CREATE,
    _PUSH_REBASE_RETRIES,
    _VALID_PRIORITIES,
    LIFECYCLE_DIR,
    MAX_CAS_RETRIES,
    _write_lock,
)
from lifecycle_errors import (  # noqa: F401 — re-export
    LifecycleAlreadyDoneError,
    LifecycleWriteRaceError,
    NotBootstrapArtifactError,
    NotFalseReconciliationError,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(
    cmd: list,
    *,
    cwd: str,
    env: Optional[dict] = None,
    input_text: Optional[str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run git with byte-level I/O and explicit UTF-8. Never `text=True`.

    `text=True` breaks this module on Windows in two separate ways:

    1. stdin is wrapped in a TextIOWrapper with universal newlines, so every "\\n"
       becomes "\\r\\n". The lifecycle yaml is fed to `git hash-object --stdin`, so
       the blob lands in git with CRLF despite `.gitattributes` (*.yaml eol=lf).
       `ai/lifecycle/` is then permanently dirty, and `assert_clean_lifecycle_tree`
       aborts orchestrator startup — for every project, not just the affected one.
    2. stdout is decoded with the locale encoding (cp1251 on a Russian Windows),
       so any Cyrillic spec title raises UnicodeDecodeError and `render_backlog`
       silently skips the yaml as malformed.

    Output keeps the newline normalization `text=True` used to provide, so the
    ~40 existing call sites are unaffected.
    """
    raw_input = input_text.encode("utf-8") if input_text is not None else None
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=raw_input,
        capture_output=True,
        check=False,
        timeout=timeout,
    )

    def _decode(b: bytes) -> str:
        return b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    return subprocess.CompletedProcess(p.args, p.returncode, _decode(p.stdout), _decode(p.stderr))


# Public alias. Other VPS modules that shell out to git must not re-derive the
# byte-level I/O rules above — re-deriving them is how the CRLF/cp1251 bug got
# written twice. Import this, not `_run`.
run_git = _run


def _current_branch(repo_dir: str) -> str:
    r = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=repo_dir)
    if r.returncode == 0:
        return r.stdout.strip()
    return _run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()


def _read_yaml_from_head(repo_dir: str, spec_id: str) -> Optional[dict]:
    r = _run(["git", "show", f"HEAD:{LIFECYCLE_DIR}/{spec_id}.yaml"], cwd=repo_dir)
    if r.returncode != 0:
        return None
    try:
        return yaml.safe_load(r.stdout)
    except yaml.YAMLError:
        return None


def _build_yaml_content(
    spec_id: str,
    status: str,
    *,
    existing: Optional[dict],
    reason: Optional[str],
    by: str,
    pueue_id: Optional[int],
    allowed_files_hash: Optional[str],
    priority: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    now = _now_iso()
    if existing is None:
        data: dict = {
            "spec_id": spec_id,
            "status": status,
            "priority": priority or "p1",
            "kind": kind or "tech",
            "blocked_reason": None,
            "started_at": None,
            "finished_at": None,
            "allowed_files_hash": allowed_files_hash,
            "updated_at": now,
            "updated_by": by,
            "version": 1,
            "pueue_id": pueue_id,
            "transitions": [],
        }
        return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)

    data = dict(existing)
    old_status = data.get("status", "unknown")
    data.update(
        {
            "status": status,
            "updated_at": now,
            "updated_by": by,
            "version": int(data.get("version", 0)) + 1,
        }
    )
    if reason is not None:
        data["blocked_reason"] = reason
    if allowed_files_hash is not None:
        data["allowed_files_hash"] = allowed_files_hash
    if pueue_id is not None:
        data["pueue_id"] = pueue_id
    if (
        old_status in ("queued", "resumed")
        and status == "in_progress"
        and not data.get("started_at")
    ):
        data["started_at"] = now
    if status == "done" and not data.get("finished_at"):
        data["finished_at"] = now
    transitions = list(data.get("transitions") or [])
    transitions.append(
        {"from": old_status, "to": status, "at": now, "by": by, "pueue_id": pueue_id}
    )
    data["transitions"] = transitions
    return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)


def _atomic_write(repo_dir: str, spec_id: str, yaml_content: str, branch: str) -> bool:
    """One CAS attempt. Returns True on success, False on race (HEAD moved)."""
    git_dir = os.path.join(repo_dir, ".git")

    with tempfile.NamedTemporaryFile(dir=git_dir, delete=False) as f:
        idx_path = f.name

    try:
        env = {**os.environ, "GIT_INDEX_FILE": idx_path}

        # TOCTOU fix (FTR-1270 wipe, 2026-06-22): pin HEAD once so the tree
        # snapshot, the commit parent, and the CAS all reference the SAME commit.
        # Reading HEAD twice (read-tree HEAD ... later rev-parse HEAD) let a
        # concurrent push land between them — the tree snapshotted the OLD HEAD
        # while the parent was the NEW HEAD; the CAS only guards parent==branch,
        # so it committed a stale tree that silently reverted everything in between.
        hr = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if hr.returncode != 0:
            return False
        head_sha = hr.stdout.strip()

        if _run(["git", "read-tree", head_sha], cwd=repo_dir, env=env).returncode != 0:
            return False

        r = _run(
            ["git", "hash-object", "-w", "--stdin"], cwd=repo_dir, env=env, input_text=yaml_content
        )
        if r.returncode != 0:
            return False
        blob_sha = r.stdout.strip()

        path_in_repo = f"{LIFECYCLE_DIR}/{spec_id}.yaml"
        if (
            _run(
                [
                    "git",
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"100644,{blob_sha},{path_in_repo}",
                ],
                cwd=repo_dir,
                env=env,
            ).returncode
            != 0
        ):
            return False

        # backlog.md status sync (re-enabled, status-only). lifecycle.yaml stays
        # the SoT; backlog.md is a human-authored view. The OLD plain-table render
        # was disabled 2026-05-16 because it destroyed founder descriptions /
        # section structure. render_backlog.sync_status rewrites ONLY the Status
        # cell of existing rows (override carries THIS spec's new status, which is
        # not in HEAD yet) and is folded into the SAME atomic commit as the YAML —
        # no second commit, no WT race. Best-effort: never break the status write.
        try:
            import render_backlog

            bl = _run(["git", "show", f"{head_sha}:ai/backlog.md"], cwd=repo_dir)
            if bl.returncode == 0:
                m_status = re.search(r"status:\s*(\S+)", yaml_content)
                override = {spec_id: m_status.group(1)} if m_status else None
                synced = render_backlog.sync_status(repo_dir, bl.stdout, overrides=override)
                if synced != bl.stdout:
                    blob = _run(
                        ["git", "hash-object", "-w", "--stdin"],
                        cwd=repo_dir,
                        env=env,
                        input_text=synced,
                    )
                    if blob.returncode == 0:
                        _run(
                            [
                                "git",
                                "update-index",
                                "--add",
                                "--cacheinfo",
                                f"100644,{blob.stdout.strip()},ai/backlog.md",
                            ],
                            cwd=repo_dir,
                            env=env,
                        )
        except Exception as exc:  # noqa: BLE001 — render must never break the write
            log.warning("backlog sync skipped for %s: %s", spec_id, exc)

        r = _run(["git", "write-tree"], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        tree_sha = r.stdout.strip()

        m = re.search(r"status:\s*(\S+)", yaml_content)
        status_str = m.group(1) if m else "update"
        msg = f"lifecycle({spec_id}): {status_str}"

        r = _run(["git", "commit-tree", tree_sha, "-p", head_sha, "-m", msg], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        new_commit = r.stdout.strip()

        r = _run(["git", "update-ref", f"refs/heads/{branch}", new_commit, head_sha], cwd=repo_dir)
        if r.returncode != 0:
            log.debug("CAS lost for %s (branch %s)", spec_id, branch)
            return False

        # Layer 3 (ARCH-187 / ADR-024 / TECH-194): sync WT to new HEAD blob so
        # subsequent `git add .` from any agent cannot smuggle a stale yaml into
        # a commit. Uses `git checkout HEAD -- <path>` (not checkout-index) so
        # both the default .git/index and WT are updated atomically. checkout-index
        # with a private GIT_INDEX_FILE only writes the WT file but leaves the
        # default index with a staged deletion (`D  `) — fixed in TECH-194.
        # Best-effort: log on failure but don't fail the write
        # (assert_clean_lifecycle_tree at orchestrator boot is the backstop).
        sync_result = _run(
            ["git", "checkout", "HEAD", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
            cwd=repo_dir,
        )
        if sync_result.returncode != 0:
            log.warning(
                "WT sync after write_lifecycle failed (best-effort): rc=%d stderr=%s",
                sync_result.returncode,
                sync_result.stderr.strip(),
            )

        # Sync WT for backlog.md too (it was folded into the commit above). Best-
        # effort + separate: backlog.md may not exist in some projects, and a miss
        # here must not fail the lifecycle write.
        _run(["git", "checkout", "HEAD", "--", "ai/backlog.md"], cwd=repo_dir)

        return True

    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def _push_best_effort(repo_dir: str, branch: str) -> None:
    """Push the lifecycle commit to origin; self-heal a non-fast-forward reject.

    Failure mode (push-race divergence): while an agent runs, orchestrator skips
    git pull, so callback commits status on a STALE local develop. Meanwhile the
    agent's code commits land on origin. The plain push is then rejected
    non-fast-forward and the branches diverge — orchestrator's `merge --ff-only`
    can never heal it, so the done-commit is trapped locally and the status looks
    stuck at queued (9 manual rebases/day on awardybot, 2026-06-21).

    Recovery: fetch origin, verify the local-ahead commits touch ONLY lifecycle/
    backlog paths (callback is their sole writer → conflict-free by construction),
    rebase them onto origin/<branch> and retry the push. Bounded; on any surprise
    (dirty WT, a non-lifecycle local commit, rebase conflict) abort cleanly and
    fall back to the legacy best-effort counter — never worse than before.
    """
    if _try_push(repo_dir, branch):
        return
    for attempt in range(1, _PUSH_REBASE_RETRIES + 1):
        if not _rebase_onto_origin(repo_dir, branch):
            break
        if _try_push(repo_dir, branch):
            log.info(
                "lifecycle push recovered via rebase onto origin/%s (attempt %d)",
                branch,
                attempt,
            )
            return
        # push raced again (origin moved between fetch and push) — retry
    log.warning(
        "lifecycle push failed after rebase recovery (best-effort, not fatal): branch=%s",
        branch,
    )
    _bump_push_failure_counter(repo_dir)


def _try_push(repo_dir: str, branch: str) -> bool:
    """Single `git push origin <branch>`. True on success, False on any failure."""
    try:
        r = _run(["git", "push", "origin", branch], cwd=repo_dir, timeout=60)
    except subprocess.TimeoutExpired as exc:
        log.warning("lifecycle push timeout: branch=%s cmd=%s", branch, exc.cmd)
        return False
    if r.returncode != 0:
        log.info(
            "lifecycle push rejected (will attempt rebase recovery): branch=%s stderr=%s",
            branch,
            r.stderr.strip()[:200],
        )
        return False
    return True


def _local_ahead_is_lifecycle_only(repo_dir: str, branch: str) -> bool:
    """True iff every commit in origin/<branch>..HEAD touches only lifecycle/backlog.

    This is the safety gate that makes auto-rebase sound: callback is the sole
    writer of ai/lifecycle/*.yaml (+ the folded ai/backlog.md render), and code
    commits never touch those paths, so replaying lifecycle-only commits onto
    origin is conflict-free by construction. Any other ahead-commit → bail.
    """
    rev = _run(["git", "rev-list", f"origin/{branch}..HEAD"], cwd=repo_dir)
    if rev.returncode != 0:
        return False
    commits = rev.stdout.split()
    if not commits:
        # Nothing ahead — the rejection wasn't a divergence we created. Bail
        # (a plain behind-only state is not our recovery case).
        return False
    for sha in commits:
        files = _run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
            cwd=repo_dir,
        )
        if files.returncode != 0:
            return False
        for path in files.stdout.splitlines():
            path = path.strip()
            if not path:
                continue
            if not (path.startswith(f"{LIFECYCLE_DIR}/") or path == "ai/backlog.md"):
                return False
    return True


def _rebase_onto_origin(repo_dir: str, branch: str) -> bool:
    """Fetch origin/<branch> and rebase local lifecycle-only commits onto it.

    Returns True only if the rebase succeeded and left a clean WT. Returns False
    (state restored) on any guard failure: fetch error, dirty WT, a non-lifecycle
    local-ahead commit, or a rebase conflict (which is aborted). On False the
    caller falls back to the legacy counter — never worse than the old behavior.
    """
    try:
        fetch = _run(["git", "fetch", "--quiet", "origin", branch], cwd=repo_dir, timeout=60)
    except subprocess.TimeoutExpired:
        log.warning("lifecycle rebase: fetch timeout branch=%s", branch)
        return False
    if fetch.returncode != 0:
        log.warning(
            "lifecycle rebase: fetch failed branch=%s stderr=%s",
            branch,
            fetch.stderr.strip()[:200],
        )
        return False

    # Guard 1: WT must be clean. rebase refuses on a dirty tree, and we must
    # never disturb uncommitted work. In the stuck case the WT is clean (just
    # behind origin) because _atomic_write synced only the yaml+backlog paths.
    status = _run(["git", "status", "--porcelain"], cwd=repo_dir)
    if status.returncode != 0 or status.stdout.strip():
        log.warning("lifecycle rebase: WT not clean, skipping auto-rebase branch=%s", branch)
        return False

    # Guard 2: only auto-rebase when every ahead-commit is lifecycle/backlog-only.
    if not _local_ahead_is_lifecycle_only(repo_dir, branch):
        log.warning(
            "lifecycle rebase: local-ahead commits touch non-lifecycle files — "
            "refusing auto-rebase (manual heal) branch=%s",
            branch,
        )
        return False

    try:
        rebase = _run(["git", "rebase", f"origin/{branch}"], cwd=repo_dir, timeout=60)
    except subprocess.TimeoutExpired:
        log.warning("lifecycle rebase: timeout branch=%s — aborting", branch)
        _run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    if rebase.returncode != 0:
        log.warning(
            "lifecycle rebase: conflict/failure, aborting branch=%s stderr=%s",
            branch,
            rebase.stderr.strip()[:200],
        )
        _run(["git", "rebase", "--abort"], cwd=repo_dir)
        return False
    return True


def _bump_push_failure_counter(repo_dir: str) -> None:
    """Increment ai/.lifecycle-push-failures counter (best-effort)."""
    counter = Path(repo_dir) / "ai" / ".lifecycle-push-failures"
    try:
        prev = int(counter.read_text().strip()) if counter.is_file() else 0
        counter.write_text(str(prev + 1))
    except Exception:  # noqa: BLE001
        pass


def _cas_loop(repo_dir: str, spec_id: str, branch: str, yaml_fn) -> None:
    """Run CAS retry loop with in-process lock + jitter.

    In-process lock (_write_lock) serializes writes within one Python process,
    eliminating intra-process CAS stampede while preserving multi-machine CAS
    safety via git update-ref.
    """
    with _write_lock:
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            yaml_content = yaml_fn()
            try:
                wrote = _atomic_write(repo_dir, spec_id, yaml_content, branch)
            except subprocess.TimeoutExpired as exc:
                log.warning(
                    "lifecycle git plumbing timeout (spec=%s cmd=%s); treating as CAS failure",
                    spec_id,
                    exc.cmd,
                )
                wrote = False
            if wrote:
                _push_best_effort(repo_dir, branch)
                return
            log.warning("CAS attempt %d/%d failed for %s", attempt, MAX_CAS_RETRIES, spec_id)
            if attempt < MAX_CAS_RETRIES:
                # Jitter: spread retries to reduce multi-machine CAS stampede (0–50ms)
                time.sleep(random.uniform(0, 0.05))
        raise LifecycleWriteRaceError(spec_id, MAX_CAS_RETRIES)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_lifecycle(repo_dir, spec_id: str) -> Optional[dict]:
    """Read lifecycle YAML from HEAD (git object store). Returns parsed dict or None.

    Reads via 'git show HEAD:<path>' so it always returns the committed state,
    even when working tree is not yet synced (e.g. in tests without a remote).
    Falls back to working tree file if HEAD doesn't have a git repo context.
    """
    return _read_yaml_from_head(str(repo_dir), spec_id)


def write_lifecycle(
    repo_dir,
    spec_id: str,
    status: str,
    *,
    reason: Optional[str] = None,
    by: str = "callback",
    pueue_id: Optional[int] = None,
    allowed_files_hash: Optional[str] = None,
) -> None:
    """
    Atomically write a lifecycle status update via git plumbing.

    Uses private GIT_INDEX_FILE + CAS update-ref. Never touches working tree.
    Retries up to MAX_CAS_RETRIES on CAS race; raises LifecycleWriteRaceError
    if all retries are exhausted.
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(f"write_lifecycle: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}")
    # Rule 7 — done is terminal (ADR-025, ARCH-193). Structural guard at the
    # write primitive — protects ALL callers (callback, operator, qa, audit,
    # migration, orchestrator).
    if status != "done":
        _existing_head = _read_yaml_from_head(str(repo_dir), spec_id)
        if _existing_head and _existing_head.get("status") == "done":
            raise LifecycleAlreadyDoneError(spec_id=spec_id, attempted=status, by=by)
    repo_dir = str(repo_dir)
    branch = _current_branch(repo_dir)

    def make_yaml():
        existing = _read_yaml_from_head(repo_dir, spec_id)
        return _build_yaml_content(
            spec_id,
            status,
            existing=existing,
            reason=reason,
            by=by,
            pueue_id=pueue_id,
            allowed_files_hash=allowed_files_hash,
        )

    _cas_loop(repo_dir, spec_id, branch, make_yaml)


def create_initial(
    repo_dir,
    spec_id: str,
    priority: str,
    kind: str,
    status: str = "queued",
    *,
    by: str = "orchestrator",
) -> None:
    """Bootstrap a new lifecycle.yaml (default status=queued, version=1).

    `status` override is used by orchestrator.bootstrap_new_specs when the
    spec is in the backlog DONE archive section — bootstrap as 'done' so it
    never dispatches.

    `by` defaults to "orchestrator" for backward compatibility with existing
    callers. Spark may pass by="spark" to claim an ID via CAS (ARCH-196 CR-7).
    Gated by _ALLOWED_WRITERS_FOR_CREATE (superset of _ALLOWED_WRITERS).
    """
    if by not in _ALLOWED_WRITERS_FOR_CREATE:
        raise ValueError(
            f"create_initial: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS_FOR_CREATE)}"
        )
    # Spark creates specs ONLY in queued: council/architect decisions happen in
    # Spark Phase 4 before the spec exists, so a spark-born blocked/done spec is
    # a process violation (e.g. "council_required" pre-implementation gates).
    if by == "spark" and status != "queued":
        raise ValueError(
            f"create_initial: by='spark' may only create status='queued' (got {status!r})"
        )
    # Normalize priority: lowercase, strip whitespace, validate enum (TECH-200)
    priority = (priority or "p1").strip().lower()
    if priority not in _VALID_PRIORITIES:
        log.warning(
            "create_initial %s: unknown priority %r, defaulting to p1",
            spec_id,
            priority,
        )
        priority = "p1"
    repo_dir = str(repo_dir)
    branch = _current_branch(repo_dir)

    # Rule 7: done is terminal — even create_initial cannot overwrite a done lifecycle.
    # write_lifecycle has the same guard; mirroring here closes the spark CAS path.
    _existing_head = _read_yaml_from_head(repo_dir, spec_id)
    if _existing_head and _existing_head.get("status") == "done":
        raise LifecycleAlreadyDoneError(spec_id=spec_id, attempted=status, by=by)

    def make_yaml():
        return _build_yaml_content(
            spec_id,
            status,
            existing=None,
            reason=None,
            by=by,
            pueue_id=None,
            allowed_files_hash=None,
            priority=priority,
            kind=kind,
        )

    _cas_loop(repo_dir, spec_id, branch, make_yaml)


def list_by_status(repo_dir, status) -> list:
    """
    List lifecycle files matching status (str or set[str]).

    Reads spec_ids from HEAD via 'git ls-tree', then loads each YAML via
    'git show'. Falls back to WT glob if HEAD has no lifecycle files yet.
    Returns sorted list of dicts.
    """
    if isinstance(status, str):
        status = {status}
    repo_dir = str(repo_dir)

    # Get file list from HEAD object store
    r = _run(["git", "ls-tree", "--name-only", f"HEAD:{LIFECYCLE_DIR}"], cwd=repo_dir)
    if r.returncode == 0:
        names = sorted(n for n in r.stdout.splitlines() if n.endswith(".yaml"))
        results = []
        for name in names:
            spec_id = name[:-5]  # strip .yaml
            data = _read_yaml_from_head(repo_dir, spec_id)
            if data and data.get("status") in status:
                results.append(data)
        return results

    # Fallback: WT glob (pre-init or no HEAD)
    pattern = str(Path(repo_dir) / LIFECYCLE_DIR / "*.yaml")
    results = []
    for yaml_path in sorted(glob(pattern)):
        try:
            data = yaml.safe_load(Path(yaml_path).read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError):
            continue
        if data and data.get("status") in status:
            results.append(data)
    return results


def assert_clean_lifecycle_tree(repo_dir) -> None:
    """
    Assert ai/lifecycle/ has no uncommitted changes in the working tree.

    Raises RuntimeError if dirty. Called at orchestrator boot.
    """
    repo_dir = str(repo_dir)
    r = _run(["git", "status", "--porcelain", LIFECYCLE_DIR], cwd=repo_dir)
    output = r.stdout.strip()
    if output:
        raise RuntimeError(f"Dirty lifecycle tree in {repo_dir}: {output}")


def write_file_atomic(
    repo_dir,
    rel_path: str,
    content: str,
    commit_message: str,
    *,
    by: str = "callback",
) -> bool:
    """Atomically commit a single file's content via git plumbing.

    Generic version of `_atomic_write` for arbitrary file paths. Used by
    callback to commit rendered ai/backlog.md alongside lifecycle yaml writes.
    Never touches working tree.

    Returns:
        True on success (or no-op when content already matches HEAD).
        False on plumbing failure (logged, never raises — render is
        best-effort, lifecycle yaml is the SoT).
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(
            f"write_file_atomic: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}"
        )
    repo_dir = str(repo_dir)
    branch = _current_branch(repo_dir)

    with _write_lock:
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            # Check if content already matches HEAD — skip the commit then.
            head_content = _run(["git", "show", f"HEAD:{rel_path}"], cwd=repo_dir)
            if head_content.returncode == 0 and head_content.stdout == content:
                return True
            if _atomic_write_file(repo_dir, rel_path, content, commit_message, branch):
                _push_best_effort(repo_dir, branch)
                return True
            log.warning(
                "write_file_atomic CAS attempt %d/%d failed for %s",
                attempt,
                MAX_CAS_RETRIES,
                rel_path,
            )
            if attempt < MAX_CAS_RETRIES:
                time.sleep(random.uniform(0, 0.05))
    log.warning("write_file_atomic: gave up after %d attempts for %s", MAX_CAS_RETRIES, rel_path)
    return False


def _atomic_write_file(
    repo_dir: str,
    rel_path: str,
    content: str,
    commit_message: str,
    branch: str,
) -> bool:
    """One CAS attempt for arbitrary file path. Mirrors _atomic_write but generic."""
    git_dir = os.path.join(repo_dir, ".git")
    with tempfile.NamedTemporaryFile(dir=git_dir, delete=False) as f:
        idx_path = f.name
    try:
        env = {**os.environ, "GIT_INDEX_FILE": idx_path}
        # TOCTOU fix (FTR-1270 wipe): pin HEAD once — tree, parent, CAS all on the
        # same commit (see _atomic_write). Reading HEAD twice raced a concurrent
        # push and silently reverted in-between commits.
        hr = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if hr.returncode != 0:
            return False
        head_sha = hr.stdout.strip()
        if _run(["git", "read-tree", head_sha], cwd=repo_dir, env=env).returncode != 0:
            return False
        r = _run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=repo_dir,
            env=env,
            input_text=content,
        )
        if r.returncode != 0:
            return False
        blob_sha = r.stdout.strip()
        if (
            _run(
                ["git", "update-index", "--add", "--cacheinfo", f"100644,{blob_sha},{rel_path}"],
                cwd=repo_dir,
                env=env,
            ).returncode
            != 0
        ):
            return False
        r = _run(["git", "write-tree"], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        tree_sha = r.stdout.strip()
        r = _run(
            ["git", "commit-tree", tree_sha, "-p", head_sha, "-m", commit_message],
            cwd=repo_dir,
            env=env,
        )
        if r.returncode != 0:
            return False
        new_commit = r.stdout.strip()
        r = _run(
            ["git", "update-ref", f"refs/heads/{branch}", new_commit, head_sha],
            cwd=repo_dir,
        )
        if r.returncode != 0:
            return False
        # Sync WT (best-effort; backlog.md is a render so stale WT is recoverable).
        # Uses `git checkout HEAD -- <path>` (not checkout-index) to update both
        # default .git/index and WT. checkout-index with private GIT_INDEX_FILE
        # only writes WT, leaving default index with staged deletion — TECH-194.
        sync = _run(["git", "checkout", "HEAD", "--", rel_path], cwd=repo_dir)
        if sync.returncode != 0:
            log.warning("write_file_atomic WT sync failed: %s", sync.stderr.strip()[:200])
        return True
    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def reconcile_orphans(repo_dir, pueue_alive_ids: set) -> list:
    """
    Demote in_progress specs whose pueue task is no longer alive.

    Reads current state from HEAD (same as list_by_status).
    Returns list of reconciled spec_ids.
    """
    in_progress = list_by_status(repo_dir, "in_progress")
    reconciled = []
    for data in in_progress:
        pueue_id = data.get("pueue_id")
        if pueue_id is not None and int(pueue_id) in pueue_alive_ids:
            continue
        spec_id = data["spec_id"]
        log.info("reconcile_orphans: demoting %s (pueue_id=%s)", spec_id, pueue_id)
        write_lifecycle(
            repo_dir, spec_id, "queued", reason="orphaned from crash", by="orchestrator"
        )
        reconciled.append(spec_id)
    return reconciled


def recover_bootstrap_artifact(
    repo_dir,
    spec_id: str,
    *,
    reason: str,
    by: str = "operator",
) -> None:
    """Demote a *bootstrap-as-done* lifecycle artifact (TECH-195).

    Narrow Rule 7 escape — bypasses LifecycleAlreadyDoneError ONLY when the
    HEAD yaml matches all four criteria of a silent-bootstrap signature:

      * status == "done"
      * transitions == [] (or absent)
      * pueue_id is None (never dispatched)
      * finished_at is None (callback never closed it)

    Otherwise raises NotBootstrapArtifactError — legitimate `done` entries
    remain protected by Rule 7. The recovery records a transition with
    `by="operator"` (default) so the demote shows up in audit history.

    Args:
        repo_dir: Path to the project repo (with `ai/lifecycle/` directory).
        spec_id: Spec identifier, e.g. "TECH-195".
        reason: Reason recorded in lifecycle (e.g. "TECH-195 bootstrap recovery").
        by: Writer identity. Must be in _ALLOWED_WRITERS; default "operator".

    Raises:
        ValueError: if `by` is not in _ALLOWED_WRITERS.
        FileNotFoundError: if no HEAD yaml exists for spec_id.
        NotBootstrapArtifactError: if any of the 4 criteria fails (legitimate
            done — Rule 7 still applies, recovery refused).
        LifecycleWriteRaceError: if CAS races exhaust retries.
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(
            f"recover_bootstrap_artifact: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}"
        )

    repo_dir = str(repo_dir)
    existing = _read_yaml_from_head(repo_dir, spec_id)
    if existing is None:
        raise FileNotFoundError(
            f"recover_bootstrap_artifact({spec_id}): no HEAD yaml in {repo_dir}"
        )

    # Validate ALL 4 criteria — refuse otherwise.
    if existing.get("status") != "done":
        raise NotBootstrapArtifactError(
            spec_id=spec_id, criterion="status", value=existing.get("status")
        )
    if existing.get("transitions"):
        raise NotBootstrapArtifactError(
            spec_id=spec_id, criterion="transitions", value=existing.get("transitions")
        )
    if existing.get("pueue_id") is not None:
        raise NotBootstrapArtifactError(
            spec_id=spec_id, criterion="pueue_id", value=existing.get("pueue_id")
        )
    if existing.get("finished_at") is not None:
        raise NotBootstrapArtifactError(
            spec_id=spec_id, criterion="finished_at", value=existing.get("finished_at")
        )

    branch = _current_branch(repo_dir)

    def make_yaml():
        # Re-read HEAD inside CAS loop in case of concurrent writes.
        head_now = _read_yaml_from_head(repo_dir, spec_id)
        # If the artifact was already recovered between our pre-check and the
        # CAS attempt, the 4-criteria check will fail again here — but we want
        # the build to proceed once with the originally-validated `existing`.
        # Use head_now if present (for version+transitions) else fall back.
        base = head_now if head_now is not None else existing
        return _build_yaml_content(
            spec_id,
            "queued",
            existing=base,
            reason=reason,
            by=by,
            pueue_id=None,
            allowed_files_hash=None,
        )

    # NOTE: deliberately bypassing the Rule 7 guard in write_lifecycle — we
    # have *just* validated the bootstrap-as-done signature above, which is
    # the narrow operator-escape ADR-025 always envisioned (see
    # recover_bootstrap_as_done.py docstring).
    _cas_loop(repo_dir, spec_id, branch, make_yaml)


def recover_false_reconciliation(
    repo_dir,
    spec_id: str,
    *,
    reason: str,
    by: str = "operator",
    check_only: bool = False,
) -> None:
    """Demote a spec the reconciliation gate closed against its own birth commit.

    Second narrow Rule 7 escape, same shape as recover_bootstrap_artifact and
    the same reason for existing: `done` is terminal by construction, so a spec
    closed by a bug cannot be reopened by any normal path.

    The bug (fixed 2026-07-27 in gate_logic.strip_bookkeeping_paths): a spec
    listing `ai/lifecycle/<ID>.yaml` in its Allowed Files matched the commit
    Spark writes to claim its own ID — `lifecycle(BUG-460): queued` — because
    that subject parses as a conventional commit with the spec id in scope.

    Signature required, ALL of it — otherwise refuse:

      * status == "done"
      * blocked_reason starts with "already_implemented_on_develop:"
      * pueue_id is None   (never dispatched)
      * started_at is None (never ran)
      * the cited commit is bookkeeping-only — its subject begins `lifecycle(`
        or it touches nothing outside ai/lifecycle, ai/features, ai/diary,
        ai/backlog.md

    That last check is what keeps this honest. A spec genuinely reconciled
    against real work on develop cites a real implementation commit, fails the
    check, and stays done.

    Args:
        repo_dir: Path to the project repo.
        spec_id: Spec identifier, e.g. "BUG-460".
        reason: Recorded in the lifecycle transition.
        by: Writer identity; must be in _ALLOWED_WRITERS.

    Raises:
        ValueError: `by` not in _ALLOWED_WRITERS.
        FileNotFoundError: no HEAD yaml for spec_id.
        NotFalseReconciliationError: signature did not match — Rule 7 stands.
        LifecycleWriteRaceError: CAS retries exhausted.
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(
            f"recover_false_reconciliation: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}"
        )

    repo_dir = str(repo_dir)
    existing = _read_yaml_from_head(repo_dir, spec_id)
    if existing is None:
        raise FileNotFoundError(
            f"recover_false_reconciliation({spec_id}): no HEAD yaml in {repo_dir}"
        )

    if existing.get("status") != "done":
        raise NotFalseReconciliationError(
            spec_id=spec_id, criterion="status", value=existing.get("status")
        )
    blocked_reason = existing.get("blocked_reason") or ""
    prefix = "already_implemented_on_develop:"
    if not blocked_reason.startswith(prefix):
        raise NotFalseReconciliationError(
            spec_id=spec_id, criterion="blocked_reason", value=blocked_reason
        )
    if existing.get("pueue_id") is not None:
        raise NotFalseReconciliationError(
            spec_id=spec_id, criterion="pueue_id", value=existing.get("pueue_id")
        )
    if existing.get("started_at") is not None:
        raise NotFalseReconciliationError(
            spec_id=spec_id, criterion="started_at", value=existing.get("started_at")
        )

    sha = blocked_reason[len(prefix) :].strip()
    if not sha:
        raise NotFalseReconciliationError(spec_id=spec_id, criterion="cited_sha", value=sha)

    subject = _run(["git", "log", "-1", "--format=%s", sha], cwd=repo_dir).stdout.strip()
    files = [
        ln.strip()
        for ln in _run(
            ["git", "show", "--name-only", "--format=", sha], cwd=repo_dir
        ).stdout.splitlines()
        if ln.strip()
    ]
    bookkeeping_only = subject.startswith("lifecycle(") or all(
        f.startswith(("ai/lifecycle/", "ai/features/", "ai/diary/")) or f == "ai/backlog.md"
        for f in files
    )
    if not bookkeeping_only:
        raise NotFalseReconciliationError(
            spec_id=spec_id,
            criterion="cited_commit_is_real_work",
            value=f"{sha} {subject!r} touches {files[:5]}",
        )

    if check_only:
        # Every criterion above has passed. Callers use this to preview a
        # recovery honestly — a dry-run that skips validation would report the
        # legitimately-reconciled specs as recoverable too.
        return

    branch = _current_branch(repo_dir)

    def make_yaml():
        head_now = _read_yaml_from_head(repo_dir, spec_id)
        base = head_now if head_now is not None else existing
        return _build_yaml_content(
            spec_id,
            "queued",
            existing=base,
            reason=reason,
            by=by,
            pueue_id=None,
            allowed_files_hash=None,
        )

    # Deliberately bypassing Rule 7, exactly as recover_bootstrap_artifact does:
    # the signature above has just proven this `done` was never earned.
    _cas_loop(repo_dir, spec_id, branch, make_yaml)


def now_iso() -> str:
    """Public alias for _now_iso(). Returns current UTC time as ISO-8601 string."""
    return _now_iso()


def build_initial_yaml(
    spec_id: str,
    *,
    status: str,
    priority: str,
    kind: str,
    blocked_reason: Optional[str] = None,
    by: str = "migration",
) -> str:
    """Build YAML string for a new lifecycle entry (version=1, no transitions).

    Encapsulates the schema construction so external tools (migrate, tests)
    don't duplicate field lists.

    Args:
        spec_id: Spec identifier, e.g. "TECH-001".
        status: Initial status string, e.g. "queued".
        priority: Priority level, e.g. "p1".
        kind: Spec kind, e.g. "tech".
        blocked_reason: Optional block reason (None for non-blocked entries).
        by: Origin tag for `updated_by` field. Default "migration"
            (one-shot backlog→YAML migration). Other callers: "callback",
            "spark", "manual".

    Returns:
        YAML string ready to write to ai/lifecycle/{spec_id}.yaml.
    """
    if by not in _ALLOWED_WRITERS:
        raise ValueError(
            f"build_initial_yaml: invalid by={by!r}; allowed={sorted(_ALLOWED_WRITERS)}"
        )
    return _build_yaml_content(
        spec_id,
        status,
        existing=None,
        reason=blocked_reason,
        by=by,
        pueue_id=None,
        allowed_files_hash=None,
        priority=priority,
        kind=kind,
    )
