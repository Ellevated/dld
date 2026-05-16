"""
Module: lifecycle
Role: Atomic git-plumbing writer for per-spec lifecycle YAML state files.
      Stores state in ai/lifecycle/{spec_id}.yaml via private GIT_INDEX_FILE,
      never touching the working tree. CAS update-ref prevents race conditions.

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
import threading
import time
from datetime import datetime, timezone
from glob import glob
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger(__name__)

LIFECYCLE_DIR = "ai/lifecycle"
MAX_CAS_RETRIES = 3

# In-process lock: serializes plumbing writes within one Python process.
# Eliminates intra-process CAS stampede (e.g. concurrent threads in callback).
# Multi-machine CAS is still guarded by git update-ref.
_write_lock = threading.Lock()


class LifecycleWriteRaceError(Exception):
    """Raised when CAS update-ref fails MAX_CAS_RETRIES times consecutively."""

    def __init__(self, spec_id: str, attempts: int = MAX_CAS_RETRIES) -> None:
        self.spec_id = spec_id
        self.attempts = attempts
        super().__init__(f"CAS race: write_lifecycle({spec_id!r}) failed after {attempts} attempts")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(
    cmd: list, *, cwd: str, env: Optional[dict] = None, input_text: Optional[str] = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
    )


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

        if _run(["git", "read-tree", "HEAD"], cwd=repo_dir, env=env).returncode != 0:
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

        # NOTE: backlog.md auto-render disabled (2026-05-16 post-merge fix).
        # The plain-table render strips founder's rich descriptions/sections
        # (LAUNCH BLOCKERS / GROWTH / INTERNAL). backlog.md remains a
        # manually-maintained file. lifecycle.yaml is SoT for status; render
        # can be re-enabled in a follow-up spec that preserves structure.

        r = _run(["git", "write-tree"], cwd=repo_dir, env=env)
        if r.returncode != 0:
            return False
        tree_sha = r.stdout.strip()

        r = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if r.returncode != 0:
            return False
        head_sha = r.stdout.strip()

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

        return True

    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def _push_best_effort(repo_dir: str, branch: str) -> None:
    r = _run(["git", "push", "origin", branch], cwd=repo_dir)
    if r.returncode != 0:
        log.debug("push best-effort failed (ignored): %s", r.stderr.strip()[:200])


def _cas_loop(repo_dir: str, spec_id: str, branch: str, yaml_fn) -> None:
    """Run CAS retry loop with in-process lock + jitter.

    In-process lock (_write_lock) serializes writes within one Python process,
    eliminating intra-process CAS stampede while preserving multi-machine CAS
    safety via git update-ref.
    """
    with _write_lock:
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            yaml_content = yaml_fn()
            if _atomic_write(repo_dir, spec_id, yaml_content, branch):
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


def create_initial(repo_dir, spec_id: str, priority: str, kind: str) -> None:
    """Bootstrap a new lifecycle.yaml (status=queued, version=1)."""
    repo_dir = str(repo_dir)
    branch = _current_branch(repo_dir)

    def make_yaml():
        return _build_yaml_content(
            spec_id,
            "queued",
            existing=None,
            reason=None,
            by="orchestrator",
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
        write_lifecycle(repo_dir, spec_id, "queued", reason="orphaned from crash", by="callback")
        reconciled.append(spec_id)
    return reconciled


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
