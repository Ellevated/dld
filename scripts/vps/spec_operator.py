#!/usr/bin/env python3
"""
Module: operator
Role: Operator-facing CLI for manual spec status mutations. Writes lifecycle
      state via lifecycle.write_lifecycle() (atomic git plumbing, ADR-023).
      Identity enforcement: caller must supply --by from allowed set (ADR-024).

Uses:
  - lifecycle.py: read_lifecycle(), write_lifecycle(), LifecycleWriteRaceError, LifecycleAlreadyDoneError
  - callback.py: _reset_circuit_cli (reset-circuit subcommand only)

Used by: operators (CLI), `/qa` skill, post-circuit triage.

Subcommands:
    demote      <project> <SPEC_ID> <reason> --by=<identity>  spec→queued (or --blocked)
    force-done  <project> <SPEC_ID> <reason> --by=<identity>  spec→done (bypasses guard)
    reset-circuit                                              clear callback_decisions, resume

Exit codes:
    0 — applied.
    2 — usage / IO error / invalid identity (--by not in allowed set).
    3 — spec .md not found, OR lifecycle yaml not found (never bootstrapped).
    4 — CAS race exhausted after retries; caller should retry.
    5 — done is terminal; cannot demote/overwrite (Rule 7, ADR-025).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

import lifecycle  # noqa: E402  (sys.path mutation above)

try:
    import callback  # type: ignore
except Exception as exc:  # noqa: BLE001
    print(f"operator: cannot import callback module: {exc}", file=sys.stderr)
    sys.exit(2)


def _resolve_project(arg: str) -> Path:
    p = Path(arg).expanduser()
    if not p.is_absolute():
        # Try common roots so operators can pass project name only.
        for root in (Path("~/projects").expanduser(), Path.cwd()):
            cand = (root / arg).expanduser()
            if cand.is_dir():
                p = cand
                break
    return p.resolve()


def _find_spec(project: Path, spec_id: str) -> Path | None:
    features = project / "ai" / "features"
    if not features.is_dir():
        return None
    matches = sorted(features.glob(f"{spec_id}*.md"))
    return matches[0] if matches else None


def _set_status(project: Path, spec_id: str, target: str, reason: str | None, by: str) -> int:
    """Apply target status to spec lifecycle yaml via lifecycle.write_lifecycle."""
    spec_path = _find_spec(project, spec_id)
    if spec_path is None:
        print(
            f"operator: spec not found: {project}/ai/features/{spec_id}*.md",
            file=sys.stderr,
        )
        return 3

    existing = lifecycle.read_lifecycle(project, spec_id)
    if existing is None:
        print(
            f"operator: lifecycle yaml not found — spec was never bootstrapped: {spec_id}",
            file=sys.stderr,
        )
        return 3

    try:
        lifecycle.write_lifecycle(project, spec_id, target, reason=reason, by=by)
    except lifecycle.LifecycleAlreadyDoneError as exc:
        print(f"operator: {exc}", file=sys.stderr)
        return 5
    except ValueError as exc:
        print(f"operator: {exc}", file=sys.stderr)
        return 2
    except lifecycle.LifecycleWriteRaceError:
        print("operator: race exhausted, retry later", file=sys.stderr)
        return 4

    print(f"operator: {spec_id} → {target} (by={by}, reason={reason})")
    return 0


def cmd_demote(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    if not project.is_dir():
        print(f"operator: project dir not found: {project}", file=sys.stderr)
        return 2
    target = "blocked" if args.blocked else "queued"
    return _set_status(project, args.spec_id, target, args.reason, args.by)


def cmd_force_done(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    if not project.is_dir():
        print(f"operator: project dir not found: {project}", file=sys.stderr)
        return 2
    return _set_status(project, args.spec_id, "done", args.reason, args.by)


def cmd_reset_circuit(_args: argparse.Namespace) -> int:
    callback._reset_circuit_cli()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="operator", description="Manual operator CLI for spec status + circuit reset."
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    p_d = sub.add_parser("demote", help="Move spec back to queued (or --blocked).")
    p_d.add_argument("project")
    p_d.add_argument("spec_id")
    p_d.add_argument("reason")
    p_d.add_argument(
        "--blocked", action="store_true", help="Demote to 'blocked' instead of 'queued'."
    )
    p_d.add_argument(
        "--by",
        required=True,
        choices=["operator", "qa", "audit"],
        help="Identity of caller. Mandatory — recorded in transitions yaml (ADR-024).",
    )
    p_d.set_defaults(func=cmd_demote)

    p_f = sub.add_parser("force-done", help="Force spec to done (bypasses TECH-166 guard).")
    p_f.add_argument("project")
    p_f.add_argument("spec_id")
    p_f.add_argument("reason")
    p_f.add_argument(
        "--by",
        required=True,
        choices=["operator", "qa", "audit"],
        help="Identity of caller. Mandatory — recorded in transitions yaml (ADR-024).",
    )
    p_f.set_defaults(func=cmd_force_done)

    p_r = sub.add_parser("reset-circuit", help="Clear callback_decisions, resume claude-runner.")
    p_r.set_defaults(func=cmd_reset_circuit)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
