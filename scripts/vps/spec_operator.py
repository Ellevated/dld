#!/usr/bin/env python3
"""
Module: operator
Role: Operator-facing CLI for manual spec status mutations. Wraps the same
      git-plumbing commit primitives the callback uses (`_git_commit_push`)
      so every operator action lands as a clean atomic commit on develop
      WITHOUT touching the operator's working tree.

Uses: scripts.vps.callback (_git_commit_push, _apply_spec_status,
      _apply_backlog_status, _apply_blocked_reason, _read_head_blob,
      _reset_circuit_cli).

Used by: operators (CLI), `/qa` skill, post-circuit triage.

Subcommands:
    demote      <project> <SPEC_ID> <reason>   spec→queued (or blocked)
    force-done  <project> <SPEC_ID> <reason>   spec→done (bypasses guard)
    reset-circuit                              clear callback_decisions, resume

Exit codes:
    0 — applied (or already in target state).
    2 — usage / IO error.
    3 — spec or backlog not found.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

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


def _set_status(project: Path, spec_id: str, target: str,
                reason: str | None) -> int:
    """Apply target status to spec + backlog via callback._git_commit_push."""
    spec_path = _find_spec(project, spec_id)
    if spec_path is None:
        print(f"operator: spec not found: {project}/ai/features/{spec_id}*.md",
              file=sys.stderr)
        return 3

    rel_spec = str(spec_path.relative_to(project))
    spec_head = callback._read_head_blob(str(project), rel_spec)
    if spec_head is None:
        print(f"operator: cannot read HEAD:{rel_spec}", file=sys.stderr)
        return 3

    ok, new_spec = callback._apply_spec_status(spec_head, target)
    if not ok:
        print(f"operator: failed to apply spec status (target={target})",
              file=sys.stderr)
        return 3

    if reason and target in {"blocked", "queued"}:
        ok2, new_spec = callback._apply_blocked_reason(new_spec, reason)
        if not ok2:
            # not fatal — blocked-reason line just couldn't be appended.
            pass

    fixes: list[tuple[str, str]] = [(rel_spec, new_spec)]

    # Backlog row (best-effort — not fatal if absent).
    backlog_rel = "ai/backlog.md"
    backlog_head = callback._read_head_blob(str(project), backlog_rel)
    if backlog_head is not None:
        ok_b, new_backlog = callback._apply_backlog_status(
            backlog_head, spec_id, target)
        if ok_b and new_backlog != backlog_head:
            fixes.append((backlog_rel, new_backlog))

    callback._git_commit_push(str(project), spec_id, target, fixes)
    print(f"operator: {spec_id} → {target}"
          + (f"  (reason: {reason})" if reason else "")
          + f"  [{len(fixes)} file(s)]")
    return 0


def cmd_demote(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    if not project.is_dir():
        print(f"operator: project dir not found: {project}", file=sys.stderr)
        return 2
    target = "blocked" if args.blocked else "queued"
    return _set_status(project, args.spec_id, target, args.reason)


def cmd_force_done(args: argparse.Namespace) -> int:
    project = _resolve_project(args.project)
    if not project.is_dir():
        print(f"operator: project dir not found: {project}", file=sys.stderr)
        return 2
    return _set_status(project, args.spec_id, "done", args.reason)


def cmd_reset_circuit(_args: argparse.Namespace) -> int:
    callback._reset_circuit_cli()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="operator",
        description="Manual operator CLI for spec status + circuit reset.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_d = sub.add_parser("demote",
                         help="Move spec back to queued (or --blocked).")
    p_d.add_argument("project")
    p_d.add_argument("spec_id")
    p_d.add_argument("reason")
    p_d.add_argument("--blocked", action="store_true",
                     help="Demote to 'blocked' instead of 'queued'.")
    p_d.set_defaults(func=cmd_demote)

    p_f = sub.add_parser("force-done",
                         help="Force spec to done (bypasses TECH-166 guard).")
    p_f.add_argument("project")
    p_f.add_argument("spec_id")
    p_f.add_argument("reason")
    p_f.set_defaults(func=cmd_force_done)

    p_r = sub.add_parser("reset-circuit",
                         help="Clear callback_decisions, resume claude-runner.")
    p_r.set_defaults(func=cmd_reset_circuit)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
