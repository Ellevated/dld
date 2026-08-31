"""
Module: lifecycle_errors
Role: The four exception classes raised by the lifecycle write/recovery primitives.

Uses:
  - lifecycle_const: MAX_CAS_RETRIES

Used by:
  - lifecycle.py, lifecycle_cas.py, lifecycle_recovery.py
"""

from lifecycle_const import MAX_CAS_RETRIES


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


class NotBootstrapArtifactError(Exception):
    """Raised by recover_bootstrap_artifact when the 4-criteria signature
    does not match — i.e. the spec is a legitimate `done` (it ran and
    completed) and must NOT be demoted.
    """

    def __init__(self, *, spec_id: str, criterion: str, value) -> None:
        super().__init__(
            f"lifecycle({spec_id}): not a bootstrap-as-done artifact — "
            f"{criterion}={value!r}; refusing to recover (Rule 7 still applies)"
        )
        self.spec_id = spec_id
        self.criterion = criterion
        self.value = value


class NotFalseReconciliationError(Exception):
    """Raised by recover_false_reconciliation when the signature does not match
    — the spec really was implemented, and Rule 7 must keep protecting it.
    """

    def __init__(self, *, spec_id: str, criterion: str, value) -> None:
        super().__init__(
            f"lifecycle({spec_id}): not a false reconciliation — "
            f"{criterion}={value!r}; refusing to recover (Rule 7 still applies)"
        )
        self.spec_id = spec_id
        self.criterion = criterion
        self.value = value
