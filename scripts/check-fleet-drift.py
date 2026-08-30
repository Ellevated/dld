#!/usr/bin/env python3
"""Measure how far each downstream project has drifted from `template/`.

**Why this exists.** DLD ships a prompt tree; projects receive a copy by hand, because
the auto-apply script (`upgrade.mjs`) was deleted 2026-05-25 for overwriting protected
files. Three months of hand-copying later, nobody could answer "is project X current?"
without diffing 150 files by eye — so on 2026-08-31 an audit did exactly that and found
~100 diverged files per project, plus two gate scripts (`validate-allowlist.mjs`,
`check-prompt-integrity.mjs`) that no project had at all while template prompts invoked
them as hard gates. A prompt calling a script that is not there exits 127 on every spec.

That audit was manual, and it missed one of the two scripts. This is the same audit,
run by a machine.

**The marker cannot lie.** Each synced project carries `.claude/DLD_VERSION`, written by
`--apply`, never by hand. It records the DLD commit and a digest of the file set as it
was delivered. This script recomputes that digest from the files actually on disk: when
they disagree the marker is reported as STALE, which is the interesting state — it means
the project was synced once and has drifted since, or was synced only in part. A marker
that is trusted rather than verified is the failure this repository has now hit three
times (`index_status.head_sha`, `file.py:LINE` citations, an exit code nobody wrote).

Exit: 0 = every project at or under its baseline, 1 = drift/absence/stale marker, 2 = usage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = REPO_ROOT / "template"
BASELINE = REPO_ROOT / "scripts" / "fleet-drift-baseline.txt"
MARKER_REL = ".claude/DLD_VERSION"

# Files the downstream copy must match byte for byte (after newline normalisation).
# Directly from `skills/upgrade/SKILL.md` section 3 "cherry-pick SAFE groups" plus the
# gate scripts, which are executable contracts named by prompts — not a matter of taste.
SYNCED_GLOBS = (
    ".claude/agents/**/*.md",
    ".claude/hooks/*.mjs",
    ".claude/scripts/**/*.mjs",
    ".claude/skills/**/*.md",
    ".git-hooks/pre-commit",
    "scripts/check_domain_imports.py",
    "scripts/check_docs_sync.py",
    "scripts/pre-review-check.py",
)

# Never compared: the project owns these outright (`skills/upgrade/SKILL.md` section 5).
# Overwriting any of them is what got the auto-apply script deleted.
LOCAL_NAMES = frozenset(
    {
        ".claude/rules/architecture.md",
        ".claude/rules/dependencies.md",
        ".claude/rules/localization.md",
        ".claude/rules/template-sync.md",
        ".claude/CUSTOMIZATIONS.md",
        ".claude/hooks/hooks.config.mjs",
        ".claude/hooks/hooks.config.local.mjs",
        ".claude/settings.json",
        ".claude/settings.local.json",
        # Root-only tooling: needs two trees to compare, so a project cannot hold it.
        ".claude/scripts/eval-agents.mjs",
    }
)


def _norm(path: Path) -> bytes:
    """Content with newlines normalised — a CRLF checkout is not drift."""
    return path.read_bytes().replace(b"\r\n", b"\n")


def _digest(path: Path) -> str:
    return hashlib.sha256(_norm(path)).hexdigest()


def template_manifest(template: Path = TEMPLATE) -> dict[str, str]:
    """Relative path -> digest, for every file a project is expected to carry."""
    manifest: dict[str, str] = {}
    for pattern in SYNCED_GLOBS:
        for src in sorted(template.glob(pattern)):
            if not src.is_file():
                continue
            rel = src.relative_to(template).as_posix()
            if rel in LOCAL_NAMES:
                continue
            manifest[rel] = _digest(src)
    return manifest


def manifest_digest(manifest: dict[str, str]) -> str:
    """One digest over the whole set — what the marker records."""
    joined = "\n".join(f"{rel}:{sha}" for rel, sha in sorted(manifest.items()))
    return hashlib.sha256(joined.encode()).hexdigest()


@dataclass
class Report:
    project: str
    identical: int = 0
    differs: list[str] = field(default_factory=list)
    absent: list[str] = field(default_factory=list)
    marker: str = "none"

    @property
    def drift(self) -> int:
        return len(self.differs) + len(self.absent)


def _marker_state(project: Path, delivered: dict[str, str]) -> str:
    """`none` | `<sha7>` | `STALE:<sha7>` — verified, never trusted."""
    marker = project / MARKER_REL
    if not marker.is_file():
        return "none"
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "STALE:unreadable"

    recorded = str(data.get("synced_from", "?"))[:7]
    if data.get("manifest_sha256") != manifest_digest(delivered):
        return f"STALE:{recorded}"
    return recorded


def inspect(project: Path, manifest: dict[str, str]) -> Report:
    rep = Report(project=project.name)
    delivered: dict[str, str] = {}

    for rel, want in manifest.items():
        dst = project / rel
        if not dst.is_file():
            rep.absent.append(rel)
            continue
        got = _digest(dst)
        delivered[rel] = got
        if got == want:
            rep.identical += 1
        else:
            rep.differs.append(rel)

    rep.marker = _marker_state(project, delivered)
    return rep


def write_marker(project: Path, manifest: dict[str, str], commit: str) -> None:
    marker = project / MARKER_REL
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "synced_from": commit,
                "manifest_sha256": manifest_digest(manifest),
                "files": len(manifest),
                "_comment": (
                    "Written by scripts/check-fleet-drift.py --apply. Never edit by hand: "
                    "the digest is recomputed from the files on disk, so a hand-edited "
                    "marker reports STALE rather than the version it claims."
                ),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def apply_sync(
    project: Path,
    manifest: dict[str, str],
    commit: str,
    template: Path = TEMPLATE,
    absent_only: bool = False,
) -> tuple[int, int]:
    """Copy synced files into the project. Returns (updated, created).

    `absent_only` delivers files the project does not have and touches nothing it does.
    That distinction is the whole safety argument. A missing file is unambiguous — a
    prompt names a gate script, the script is not there, the run exits 127 — and creating
    it cannot destroy anything. An *existing* file that differs is ambiguous: AwardyBot
    alone carries 364 local commits under `.claude/`, so some of those differences are
    the project's own work and overwriting them is exactly what got `upgrade.mjs` deleted
    on 2026-05-25. Full `--apply` is therefore a per-project decision made with the diff
    in hand, never a fleet-wide sweep.

    No marker is written in `absent_only` mode: the project is not at this template
    version, and a marker claiming otherwise would be the lie this design exists to
    prevent.
    """
    updated = created = 0
    for rel in manifest:
        src, dst = template / rel, project / rel
        if dst.is_file():
            if absent_only or _digest(dst) == manifest[rel]:
                continue
            updated += 1
        else:
            created += 1
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(_norm(src))
        if src.stat().st_mode & 0o111:
            dst.chmod(dst.stat().st_mode | 0o111)
    if not absent_only:
        write_marker(project, manifest, commit)
    return updated, created


def read_baseline(path: Path = BASELINE) -> dict[str, int]:
    if not path.is_file():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        name, _, count = line.partition("=")
        out[name.strip()] = int(count.strip())
    return out


def discover(root: Path) -> list[Path]:
    return sorted(
        p
        for p in root.iterdir()
        if p.is_dir() and (p / ".claude").is_dir() and p.resolve() != REPO_ROOT
    )


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("projects", nargs="*", type=Path, help="project paths")
    ap.add_argument("--root", type=Path, help="scan this dir for repos with .claude/")
    ap.add_argument("--apply", action="store_true", help="copy synced files + write marker")
    ap.add_argument(
        "--apply-absent",
        action="store_true",
        help="deliver only files the project lacks; never overwrite, never stamp a marker",
    )
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--template", type=Path, default=TEMPLATE, help="template tree to compare against"
    )
    ap.add_argument("--baseline", type=Path, default=BASELINE, help="drift debt register")
    args = ap.parse_args(argv)

    projects = list(args.projects)
    if args.root:
        projects += discover(args.root)
    if not projects:
        ap.error("no projects given: pass paths or --root")

    manifest = template_manifest(args.template)
    if not manifest:
        print("FAIL: template manifest is empty — did SYNCED_GLOBS stop matching?")
        return 2

    commit = (
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        or "unknown"
    )

    baseline, reports, failed = read_baseline(args.baseline), [], False
    for project in projects:
        if not (project / ".claude").is_dir():
            print(f"SKIP  {project} — no .claude/", file=sys.stderr if args.json else sys.stdout)
            continue
        if args.apply or args.apply_absent:
            updated, created = apply_sync(
                project, manifest, commit, args.template, absent_only=args.apply_absent
            )
            # stderr under --json: stdout must stay parseable by whoever called us.
            print(
                f"APPLY {project.name}: {updated} updated, {created} created",
                file=sys.stderr if args.json else sys.stdout,
            )
        rep = inspect(project, manifest)
        reports.append(rep)
        if rep.drift > baseline.get(rep.project, 0) or rep.marker.startswith("STALE"):
            failed = True

    if args.json:
        print(json.dumps([r.__dict__ | {"drift": r.drift} for r in reports], indent=2))
        return 1 if failed else 0

    print(f"\ntemplate: {len(manifest)} synced files @ {commit[:7]}\n")
    for r in sorted(reports, key=lambda r: -r.drift):
        allowed = baseline.get(r.project, 0)
        ok = r.drift <= allowed and not r.marker.startswith("STALE")
        budget = f" (baseline {allowed})" if allowed else ""
        print(
            f"  {'ok' if ok else 'DRIFT':5} {r.project:<14} identical={r.identical:<4} "
            f"differs={len(r.differs):<4} absent={len(r.absent):<4}{budget}  marker={r.marker}"
        )
        for rel in r.absent[:5]:
            print(f"           absent: {rel}")
        if len(r.absent) > 5:
            print(f"           absent: ... and {len(r.absent) - 5} more")

    print(
        "\nFAIL: a project drifted past its baseline, or its marker no longer matches "
        "the files on disk.\n  Sync it:  python scripts/check-fleet-drift.py <path> --apply"
        if failed
        else "\nOK: every project at or under its baseline."
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
