"""
Module: lifecycle_recovery
Role: The two narrow Rule 7 (ADR-025) escapes. `done` is terminal by
      construction, so a lifecycle closed by a bug cannot be reopened by any
      normal path. Each function validates a full signature of the specific
      defect it undoes, then bypasses the write_lifecycle guard deliberately;
      anything that fails the signature stays done.

Uses:
  - lifecycle_git: _read_yaml_from_head, _current_branch, _build_yaml_content, _run
  - lifecycle_cas: _cas_loop
  - lifecycle_const: _ALLOWED_WRITERS
  - lifecycle_errors: NotBootstrapArtifactError, NotFalseReconciliationError

Used by:
  - lifecycle.py: re-exports both names
  - recover_bootstrap_as_done.py: recover_bootstrap_artifact (via lifecycle)
  - recover_false_reconciliation.py: recover_false_reconciliation (via lifecycle)
"""

import lifecycle_cas
import lifecycle_git
from lifecycle_const import _ALLOWED_WRITERS
from lifecycle_errors import NotBootstrapArtifactError, NotFalseReconciliationError


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
