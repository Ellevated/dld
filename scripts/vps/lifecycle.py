"""
Module: lifecycle
Role: Atomic git-plumbing writer for per-spec lifecycle YAML state files.
      Stores state in ai/lifecycle/{spec_id}.yaml via private GIT_INDEX_FILE,
      never touching the working tree. CAS update-ref prevents race conditions.
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

# ADR-025 (ARCH-193): identity enforcement — only known writer identities may
# call write_lifecycle / create_initial / build_initial_yaml.  Prevents
# accidental anonymous writes and makes audit trails meaningful.
# ADR-025 (ARCH-193): "autopilot" removed — signals via task_status JSON only;
# "spark" removed — zero direct callers (specs bootstrap via
# orchestrator.create_initial which writes by="orchestrator").
_ALLOWED_WRITERS = frozenset({"callback", "orchestrator", "operator", "qa", "audit", "migration"})

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


class LifecycleAlreadyDoneError(Exception):
    """Rule 7 — done is terminal (ADR-025, ARCH-193).

    Raised by write_lifecycle when any writer attempts a non-done
    transition on a spec whose HEAD yaml already shows status="done".
    """

    def __init__(self, *, spec_id: str, attempted: str, by: str) -> None:
        super().__init__(
            f"lifecycle({spec_id}): cannot transition done → {attempted} "
            f"(writer={by}); done is terminal (Rule 7 — ADR-025)"
        )
        self.spec_id = spec_id
        self.attempted = attempted
        self.by = by


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
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
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

        # Layer 3 (ARCH-187 / ADR-024): sync WT to new HEAD blob so subsequent
        # `git add .` from any agent cannot smuggle a stale yaml into a commit.
        # Single-file checkout-index has no merge logic → race-free.
        # Best-effort: log on failure but don't fail the write
        # (assert_clean_lifecycle_tree at orchestrator boot is the backstop).
        sync_result = _run(
            ["git", "checkout-index", "--force", "--", f"{LIFECYCLE_DIR}/{spec_id}.yaml"],
            cwd=repo_dir,
        )
        if sync_result.returncode != 0:
            log.warning(
                "WT sync after write_lifecycle failed (best-effort): rc=%d stderr=%s",
                sync_result.returncode,
                sync_result.stderr.strip(),
            )

        return True

    finally:
        try:
            os.unlink(idx_path)
        except OSError:
            pass


def _push_best_effort(repo_dir: str, branch: str) -> None:
    try:
        r = _run(["git", "push", "origin", branch], cwd=repo_dir)
    except subprocess.TimeoutExpired as exc:
        log.warning(
            "lifecycle push timeout (best-effort, not fatal): branch=%s cmd=%s",
            branch,
            exc.cmd,
        )
        _bump_push_failure_counter(repo_dir)
        return
    if r.returncode != 0:
        log.warning(
            "lifecycle push failed (best-effort, not fatal): branch=%s stderr=%s",
            branch,
            r.stderr.strip()[:200],
        )
        _bump_push_failure_counter(repo_dir)


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
    repo_dir, spec_id: str, priority: str, kind: str, status: str = "queued"
) -> None:
    """Bootstrap a new lifecycle.yaml (default status=queued, version=1).

    `status` override is used by orchestrator.bootstrap_new_specs when the
    spec is in the backlog DONE archive section — bootstrap as 'done' so it
    never dispatches.
    """
    _by = "orchestrator"
    if _by not in _ALLOWED_WRITERS:
        raise ValueError(f"create_initial: invalid by={_by!r}; allowed={sorted(_ALLOWED_WRITERS)}")
    repo_dir = str(repo_dir)
    branch = _current_branch(repo_dir)

    def make_yaml():
        return _build_yaml_content(
            spec_id,
            status,
            existing=None,
            reason=None,
            by=_by,
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
        if _run(["git", "read-tree", "HEAD"], cwd=repo_dir, env=env).returncode != 0:
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
        r = _run(["git", "rev-parse", "HEAD"], cwd=repo_dir)
        if r.returncode != 0:
            return False
        head_sha = r.stdout.strip()
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
        # Sync WT (best-effort; backlog.md is a render so stale WT is recoverable)
        sync = _run(["git", "checkout-index", "--force", "--", rel_path], cwd=repo_dir)
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
