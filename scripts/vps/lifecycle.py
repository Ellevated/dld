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
    existing = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
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

    branch = lifecycle_git._current_branch(repo_dir)

    def make_yaml():
        # Re-read HEAD inside CAS loop in case of concurrent writes.
        head_now = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
        # If the artifact was already recovered between our pre-check and the
        # CAS attempt, the 4-criteria check will fail again here — but we want
        # the build to proceed once with the originally-validated `existing`.
        # Use head_now if present (for version+transitions) else fall back.
        base = head_now if head_now is not None else existing
        return lifecycle_git._build_yaml_content(
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
    lifecycle_cas._cas_loop(repo_dir, spec_id, branch, make_yaml)


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
    existing = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
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

    subject = lifecycle_git._run(
        ["git", "log", "-1", "--format=%s", sha], cwd=repo_dir
    ).stdout.strip()
    files = [
        ln.strip()
        for ln in lifecycle_git._run(
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

    branch = lifecycle_git._current_branch(repo_dir)

    def make_yaml():
        head_now = lifecycle_git._read_yaml_from_head(repo_dir, spec_id)
        base = head_now if head_now is not None else existing
        return lifecycle_git._build_yaml_content(
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
    lifecycle_cas._cas_loop(repo_dir, spec_id, branch, make_yaml)


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
