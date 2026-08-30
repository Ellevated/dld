"""
Module: lifecycle
Role: Facade over the lifecycle module group (TECH-214 split). Holds the public
      API — read_lifecycle, write_lifecycle, create_initial, list_by_status,
      assert_clean_lifecycle_tree, write_file_atomic, reconcile_orphans, now_iso,
      build_initial_yaml — and delegates every git/CAS/push/recovery mechanic to
      the siblings below. State lives in ai/lifecycle/{spec_id}.yaml.
      Rule 7 (ADR-025, ARCH-193) stays HERE, structurally inside write_lifecycle
      and mirrored in create_initial: done is terminal, so any non-done transition
      over a HEAD yaml already showing status="done" raises
      LifecycleAlreadyDoneError. It does not move to a sibling — moving it would
      reopen the question of whether every write path still passes it.
      Identity enforcement: only _ALLOWED_WRITERS may call write functions.
      Also re-exports the names three consumers bind at import time (see И-2):
      run_git (salvage.py), LIFECYCLE_DIR (render_backlog.py) and
      build_initial_yaml, defined here (migrate_backlog_to_lifecycle.py).
      Private mechanics are NOT re-exported — an alias here would turn
      patch.object(lifecycle, "_run", ...) into a silent no-op.

Uses:
  - lifecycle_const: LIFECYCLE_DIR, MAX_CAS_RETRIES, _ALLOWED_WRITERS,
    _ALLOWED_WRITERS_FOR_CREATE, _VALID_PRIORITIES, _write_lock — leaf of the
    graph, so the write lock exists exactly once per process
  - lifecycle_errors: the four lifecycle exception types
  - lifecycle_git: git primitives + YAML assembly (_run/run_git, _now_iso,
    _current_branch, _read_yaml_from_head, _build_yaml_content)
  - lifecycle_cas: atomic plumbing writes and the CAS retry loop
  - lifecycle_push: push, rebase-onto-origin, push-failure counter
  - lifecycle_recovery: the two narrow Rule 7 escapes (bootstrap artifact,
    false reconciliation)
  - logging, random, time: retry backoff and diagnostics in write_file_atomic
  - glob: glob — working-tree fallback in list_by_status
  - pathlib: Path
  - typing: Optional
  - yaml: safe_load — parsing the working-tree fallback

Used by:
  - callback.py: write_lifecycle(), read_lifecycle()
  - orchestrator.py: create_initial(), list_by_status(),
                     assert_clean_lifecycle_tree(), reconcile_orphans()
  - render_backlog.py: read_lifecycle(), list_by_status()
  - migrate_backlog_to_lifecycle.py: create_initial(), write_lifecycle()
  - salvage.py: run_git

Glossary: ai/glossary/orchestrator.md
"""

import logging
import random
import time
from glob import glob
from pathlib import Path
from typing import Optional

import lifecycle_cas
import lifecycle_git
import lifecycle_push
import yaml
from lifecycle_const import (  # noqa: F401 — re-export: read via lifecycle.<NAME>
    _ALLOWED_WRITERS,
    _ALLOWED_WRITERS_FOR_CREATE,
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
from lifecycle_git import run_git  # noqa: F401 — public alias (salvage.py:35)
from lifecycle_recovery import (  # noqa: F401 — re-export
    recover_bootstrap_artifact,
    recover_false_reconciliation,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def read_lifecycle(repo_dir, spec_id: str) -> Optional[dict]:
    """Read lifecycle YAML from HEAD (git object store). Returns parsed dict or None.

    Reads via 'git show HEAD:<path>' so it always returns the committed state,
    even when working tree is not yet synced (e.g. in tests without a remote).
    Falls back to working tree file if HEAD doesn't have a git repo context.
    """
    return lifecycle_git._read_yaml_from_head(str(repo_dir), spec_id)


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
        _existing_head = lifecycle_git._read_yaml_from_head(str(repo_dir), spec_id)
        if _existing_head and _existing_head.get("status") == "done":
            raise LifecycleAlreadyDoneError(spec_id=spec_id, attempted=status, by=by)
    repo_dir = str(repo_dir)
    branch = lifecycle_git._current_branch(repo_dir)

    def make_yaml():
        existing = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
        return lifecycle_git._build_yaml_content(
            spec_id,
            status,
            existing=existing,
            reason=reason,
            by=by,
            pueue_id=pueue_id,
            allowed_files_hash=allowed_files_hash,
        )

    lifecycle_cas._cas_loop(repo_dir, spec_id, branch, make_yaml)


def create_initial(
    repo_dir,
    spec_id: str,
    priority: str,
    kind: str,
    status: str = "queued",
    *,
    by: str = "orchestrator",
    depends_on: Optional[list] = None,
) -> None:
    """Bootstrap a new lifecycle.yaml (default status=queued, version=1).

    `status` override is used by orchestrator.bootstrap_new_specs when the
    spec is in the backlog DONE archive section — bootstrap as 'done' so it
    never dispatches.

    `by` defaults to "orchestrator" for backward compatibility with existing
    callers. Spark may pass by="spark" to claim an ID via CAS (ARCH-196 CR-7).
    Gated by _ALLOWED_WRITERS_FOR_CREATE (superset of _ALLOWED_WRITERS).

    `depends_on` lists spec_ids this spec waits for (TECH-222); absent == [].
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
    branch = lifecycle_git._current_branch(repo_dir)

    # Rule 7: done is terminal — even create_initial cannot overwrite a done lifecycle.
    # write_lifecycle has the same guard; mirroring here closes the spark CAS path.
    _existing_head = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
    if _existing_head and _existing_head.get("status") == "done":
        raise LifecycleAlreadyDoneError(spec_id=spec_id, attempted=status, by=by)

    def make_yaml():
        return lifecycle_git._build_yaml_content(
            spec_id,
            status,
            existing=None,
            reason=None,
            by=by,
            pueue_id=None,
            allowed_files_hash=None,
            priority=priority,
            kind=kind,
            depends_on=depends_on,
        )

    lifecycle_cas._cas_loop(repo_dir, spec_id, branch, make_yaml)


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
    r = lifecycle_git._run(["git", "ls-tree", "--name-only", f"HEAD:{LIFECYCLE_DIR}"], cwd=repo_dir)
    if r.returncode == 0:
        names = sorted(n for n in r.stdout.splitlines() if n.endswith(".yaml"))
        results = []
        for name in names:
            spec_id = name[:-5]  # strip .yaml
            data = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
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
    r = lifecycle_git._run(["git", "status", "--porcelain", LIFECYCLE_DIR], cwd=repo_dir)
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
    branch = lifecycle_git._current_branch(repo_dir)

    with _write_lock:
        for attempt in range(1, MAX_CAS_RETRIES + 1):
            # Check if content already matches HEAD — skip the commit then.
            head_content = lifecycle_git._run(["git", "show", f"HEAD:{rel_path}"], cwd=repo_dir)
            if head_content.returncode == 0 and head_content.stdout == content:
                return True
            if lifecycle_cas._atomic_write_file(
                repo_dir, rel_path, content, commit_message, branch
            ):
                lifecycle_push._push_best_effort(repo_dir, branch)
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
    """Public alias for lifecycle_git._now_iso(). Returns current UTC time as ISO-8601 string."""
    return lifecycle_git._now_iso()


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
    return lifecycle_git._build_yaml_content(
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
