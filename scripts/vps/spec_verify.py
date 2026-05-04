#!/usr/bin/env python3
"""
Module: spec_verify
Role: Operator-facing automated heuristic helper for the manual spec
      verification protocol. Performs Steps 1–3 of the protocol
      (read spec, file existence check, code search) and prints a report.

Steps 4–6 (tests, migrations, acceptance) remain manual — see
`~/.claude/projects/-root/memory/spec-verification-protocol.md`.

Uses: scripts.vps.callback._parse_allowed_files (TECH-167 canonical parser).
Used by: operators (CLI), `/qa` skill, post-circuit triage.

Usage:
    python3 scripts/vps/spec_verify.py <project_dir> <SPEC_ID>

Exit codes:
    0  — all checks green (no missing files, every Task got >=1 grep hit).
    1  — missing files OR Task with zero plausible code matches (HARD-FAIL).
    2  — usage / IO error.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Reuse the canonical allowlist parser from callback.py — single source of truth.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from callback import _parse_allowed_files  # type: ignore
except Exception as exc:  # noqa: BLE001
    print(f"spec_verify: cannot import callback._parse_allowed_files: {exc}",
          file=sys.stderr)
    sys.exit(2)


_TASKS_HEADING_RE = re.compile(r"^##\s+(Tasks|Implementation Plan)\b", re.IGNORECASE)
_NEXT_H2_RE = re.compile(r"^##\s+\S")
_TASK_BULLET_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.*?)\s*$")

# Plausible code symbols inside Task descriptions:
#   snake_case, camelCase, CamelCase, dotted.paths, route/paths, file.ext.
_SYMBOL_RE = re.compile(
    r"`([^`]+)`"                                 # backticked identifiers
    r"|\b([A-Z][A-Za-z0-9]+(?:[A-Z][A-Za-z0-9]+)+)\b"   # CamelCase
    r"|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"      # snake_case
    r"|/(/?[A-Za-z0-9_\-]+(?:/[A-Za-z0-9_\-]+)+)"  # /route/like
)

# Stoplist: too generic to be a useful grep keyword.
_STOPWORDS = frozenset({
    "todo", "fixme", "task", "tasks", "test", "tests", "spec", "specs",
    "the", "and", "for", "with", "into", "from",
    "true", "false", "none",
})


@dataclass
class TaskCheck:
    line: str
    symbols: list[str] = field(default_factory=list)
    matches: dict[str, int] = field(default_factory=dict)

    @property
    def total_matches(self) -> int:
        return sum(self.matches.values())

    @property
    def ok(self) -> bool:
        # No symbols extracted = nothing to verify, treat as OK
        # (e.g. "Update CHANGELOG"). Symbols present but zero hits = FAIL.
        return not self.symbols or self.total_matches > 0


@dataclass
class Report:
    spec_id: str
    spec_path: Path
    project: Path
    allowed: list[str] | None
    missing: list[str] = field(default_factory=list)
    present: list[str] = field(default_factory=list)
    recent_commits: dict[str, int] = field(default_factory=dict)
    tasks: list[TaskCheck] = field(default_factory=list)

    @property
    def has_missing(self) -> bool:
        return bool(self.missing)

    @property
    def has_failed_tasks(self) -> bool:
        return any(not t.ok for t in self.tasks)

    @property
    def hard_fail(self) -> bool:
        return self.has_missing or self.has_failed_tasks


def find_spec_file(project: Path, spec_id: str) -> Path | None:
    features = project / "ai" / "features"
    if not features.is_dir():
        return None
    matches = sorted(features.glob(f"{spec_id}*.md"))
    return matches[0] if matches else None


def extract_tasks(spec_text: str) -> list[str]:
    lines = spec_text.splitlines()
    in_section = False
    out: list[str] = []
    for line in lines:
        if not in_section:
            if _TASKS_HEADING_RE.match(line):
                in_section = True
            continue
        if _NEXT_H2_RE.match(line):
            break
        m = _TASK_BULLET_RE.match(line)
        if m and m.group(1).strip():
            out.append(m.group(1).strip())
    return out


def extract_symbols(task_line: str) -> list[str]:
    syms: list[str] = []
    seen: set[str] = set()
    for m in _SYMBOL_RE.finditer(task_line):
        for g in m.groups():
            if not g:
                continue
            s = g.strip("`/ ")
            if not s or s.lower() in _STOPWORDS:
                continue
            if len(s) < 4:  # too short — too noisy
                continue
            if s in seen:
                continue
            seen.add(s)
            syms.append(s)
    return syms


def grep_count(project: Path, symbol: str, search_paths: list[str]) -> int:
    """Return number of matching lines for `symbol` under search_paths.

    Uses git grep (fast, respects .gitignore) when project is a git repo;
    falls back to ripgrep / grep -r otherwise.
    """
    cmd: list[str]
    if (project / ".git").exists():
        cmd = ["git", "-C", str(project), "grep", "-I", "-c", "-F", "--",
               symbol] + search_paths
    else:
        cmd = ["grep", "-rIcF", "--", symbol] + [
            str(project / p) for p in search_paths
        ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return 0
    if r.returncode not in (0, 1):  # 1 = no matches, still success
        return 0
    total = 0
    for line in r.stdout.splitlines():
        # `git grep -c` lines look like "path:N"; "grep -rc" the same.
        if ":" not in line:
            continue
        try:
            total += int(line.rsplit(":", 1)[1])
        except ValueError:
            continue
    return total


def recent_commit_count(project: Path, rel_path: str, since_days: int = 60) -> int:
    if not (project / ".git").exists():
        return 0
    try:
        r = subprocess.run(
            ["git", "-C", str(project), "log",
             f"--since={since_days}.days", "--oneline", "--all", "--", rel_path],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if r.returncode != 0:
        return 0
    return sum(1 for line in r.stdout.splitlines() if line.strip())


def build_report(project: Path, spec_id: str) -> Report:
    spec_path = find_spec_file(project, spec_id)
    if spec_path is None:
        raise FileNotFoundError(
            f"spec not found: {project}/ai/features/{spec_id}*.md")

    spec_text = spec_path.read_text(errors="replace")
    allowed = _parse_allowed_files(spec_path)

    rep = Report(spec_id=spec_id, spec_path=spec_path, project=project,
                 allowed=allowed)

    # File existence + recency
    if allowed:
        for rel in allowed:
            full = project / rel
            if full.exists():
                rep.present.append(rel)
                rep.recent_commits[rel] = recent_commit_count(project, rel)
            else:
                rep.missing.append(rel)

    # Code search per task — restrict to allowed dirs (or whole project if
    # allowlist absent).
    search_paths = _search_paths_from_allowed(allowed) if allowed else ["."]
    for line in extract_tasks(spec_text):
        tc = TaskCheck(line=line)
        tc.symbols = extract_symbols(line)
        for sym in tc.symbols:
            tc.matches[sym] = grep_count(project, sym, search_paths)
        rep.tasks.append(tc)
    return rep


def _search_paths_from_allowed(allowed: list[str]) -> list[str]:
    """Extract directory roots from the allowlist for a focused grep scope."""
    out: list[str] = []
    seen: set[str] = set()
    for p in allowed:
        # Strip ~/ prefix (out-of-tree paths) — not greppable inside project.
        if p.startswith("~"):
            continue
        head = p.split("/", 1)[0] if "/" in p else "."
        if head and head not in seen:
            seen.add(head)
            out.append(head)
    return out or ["."]


def render(rep: Report) -> str:
    lines: list[str] = []
    lines.append(f"=== spec_verify: {rep.spec_id} ===")
    lines.append(f"spec:    {rep.spec_path}")
    lines.append(f"project: {rep.project}")
    if rep.allowed is None:
        lines.append("allowed: <none — no Allowed Files section>")
    else:
        lines.append(f"allowed: {len(rep.allowed)} path(s)")

    lines.append("")
    lines.append("Step 2 — File existence:")
    if not rep.allowed:
        lines.append("  (skipped — no allowlist)")
    else:
        for rel in rep.present:
            n = rep.recent_commits.get(rel, 0)
            lines.append(f"  OK   {rel}  (recent commits: {n})")
        for rel in rep.missing:
            lines.append(f"  MISS {rel}")

    lines.append("")
    lines.append("Step 3 — Code search per task:")
    if not rep.tasks:
        lines.append("  (no Tasks/Implementation Plan section found)")
    for i, tc in enumerate(rep.tasks, 1):
        flag = "OK" if tc.ok else "FAIL"
        lines.append(f"  [{flag}] Task {i}: {tc.line[:80]}")
        if not tc.symbols:
            lines.append("        (no greppable symbols extracted)")
            continue
        for sym in tc.symbols:
            n = tc.matches.get(sym, 0)
            lines.append(f"        {sym!r}: {n} hit(s)")

    lines.append("")
    if rep.hard_fail:
        bits = []
        if rep.has_missing:
            bits.append(f"{len(rep.missing)} missing file(s)")
        bad_tasks = [i for i, t in enumerate(rep.tasks, 1) if not t.ok]
        if bad_tasks:
            bits.append(f"task(s) with zero matches: {bad_tasks}")
        lines.append("VERDICT: HARD-FAIL — " + "; ".join(bits))
        lines.append("Next: python3 scripts/vps/operator.py demote "
                     f"{rep.project.name} {rep.spec_id} '<reason>'")
    else:
        lines.append("VERDICT: heuristic-OK (Steps 1–3 green; Steps 4–6 still manual)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Automated Steps 1–3 of the manual spec verification protocol.")
    parser.add_argument("project", help="Path to project repo (e.g. ~/projects/awardybot)")
    parser.add_argument("spec_id", help="Spec ID, e.g. FTR-897")
    args = parser.parse_args(argv)

    project = Path(args.project).expanduser().resolve()
    if not project.is_dir():
        print(f"spec_verify: project dir not found: {project}", file=sys.stderr)
        return 2

    try:
        rep = build_report(project, args.spec_id)
    except FileNotFoundError as exc:
        print(f"spec_verify: {exc}", file=sys.stderr)
        return 2

    print(render(rep))
    return 1 if rep.hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
