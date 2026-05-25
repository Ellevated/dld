"""
Module: migrate_backlog_to_lifecycle
Role: One-shot migration from ai/backlog.md + ai/features/*.md to
      ai/lifecycle/{spec_id}.yaml per-spec state files.

Uses:
  - pathlib: Path
  - yaml: safe_load, safe_dump
  - re: regex parsing
  - argparse: CLI
  - lifecycle: now_iso(), build_initial_yaml(), LIFECYCLE_DIR

Used by:
  - operator: manual one-shot migration CLI

Glossary: ai/glossary/orchestrator.md
"""

import argparse
import re
import sys
from glob import glob
from pathlib import Path
from typing import Optional

import yaml
from lifecycle import build_initial_yaml

BACKLOG_ROW_RE = re.compile(
    r"^\|\s*(?P<id>(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*)\s*\|"
    r"[^|]+\|\s*(?P<status>queued|in_progress|blocked|done|resumed|draft)\s*\|"
    r"(?P<rest>[^|]*\|[^|]*\|.*)?$"
)
SPEC_STATUS_RE = re.compile(r"\*\*Status:\*\*\s*(\w+)")
SPEC_BLOCKED_RE = re.compile(r"\*\*Blocked Reason:\*\*\s*(.+)")
PRIORITY_COL_RE = re.compile(r"\bP([0-3])\b")
SECTION_RE = re.compile(r"^##\s+.*?(P([0-3])|LAUNCH BLOCKERS)", re.IGNORECASE)
STARS_RE = re.compile(r"(⭐+)")

VALID_STATUSES = {"queued", "in_progress", "blocked", "done", "resumed", "draft"}
KIND_MAP = {"TECH": "tech", "FTR": "ftr", "BUG": "bug", "ARCH": "arch", "GROWTH": "ftr"}


def parse_backlog(backlog_path: Path) -> dict[str, dict]:
    """Parse ai/backlog.md rows. Returns {spec_id: {status, priority, kind}}."""
    results: dict[str, dict] = {}
    current_priority = "p1"
    for line in backlog_path.read_text(encoding="utf-8").splitlines():
        sm = SECTION_RE.match(line)
        if sm:
            if "LAUNCH BLOCKERS" in line.upper():
                current_priority = "p0"
            elif sm.group(2):
                current_priority = f"p{sm.group(2)}"
        m = BACKLOG_ROW_RE.match(line)
        if not m:
            continue
        spec_id, status, rest = m.group("id"), m.group("status"), m.group("rest") or ""
        priority = current_priority
        pm = PRIORITY_COL_RE.search(rest)
        if pm:
            priority = f"p{pm.group(1)}"
        else:
            stars_m = STARS_RE.search(rest)
            if stars_m:
                count = len(stars_m.group(1))
                priority = "p0" if count >= 5 else ("p1" if count >= 3 else "p2")
        results[spec_id] = {
            "status": status,
            "priority": priority,
            "kind": KIND_MAP.get(spec_id.split("-")[0], "tech"),
        }
    return results


def parse_spec(spec_path: Path) -> tuple[Optional[str], Optional[str]]:
    """Parse ai/features/*.md. Returns (status, blocked_reason)."""
    status: Optional[str] = None
    blocked_reason: Optional[str] = None
    for line in spec_path.read_text(encoding="utf-8").splitlines():
        if status is None:
            sm = SPEC_STATUS_RE.search(line)
            if sm:
                val = sm.group(1).strip().rstrip("|").strip()
                if val in VALID_STATUSES:
                    status = val
        bm = SPEC_BLOCKED_RE.search(line)
        if bm:
            r = bm.group(1).strip()
            if r and not r.startswith("populated"):
                blocked_reason = r
    return status, blocked_reason


def find_spec_file(features_dir: Path, spec_id: str) -> Optional[Path]:
    """Locate spec markdown file, including subdirectory layout."""
    for pattern in (
        str(features_dir / f"{spec_id}*.md"),
        str(features_dir / spec_id / f"{spec_id}*.md"),
    ):
        matches = [Path(p) for p in glob(pattern)]
        if matches:
            return matches[0]
    return None


# Idempotency comparison ignores volatile fields (timestamps differ on re-run).
_VOLATILE_FIELDS = frozenset({"updated_at"})


def _cmp_data(d: dict) -> dict:
    """Strip volatile fields for noop comparison."""
    return {k: v for k, v in d.items() if k not in _VOLATILE_FIELDS}


def _build_pair(
    spec_id: str,
    status: str,
    priority: str,
    kind: str,
    blocked_reason: Optional[str],
) -> tuple[str, dict]:
    """Return (yaml_string, parsed_dict) for one spec entry."""
    yaml_str = build_initial_yaml(
        spec_id,
        status=status,
        priority=priority,
        kind=kind,
        blocked_reason=blocked_reason,
    )
    return yaml_str, yaml.safe_load(yaml_str)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate ai/backlog.md + ai/features/*.md to ai/lifecycle/*.yaml"
    )
    parser.add_argument("--commit", action="store_true", help="Write YAML files (default: dry run)")
    parser.add_argument("--repo", default=".", help="Repo root path (default: .)")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    backlog_path = repo / "ai" / "backlog.md"
    features_dir = repo / "ai" / "features"
    lifecycle_dir = repo / "ai" / "lifecycle"

    for p in (backlog_path, features_dir):
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            return 1

    backlog_entries = parse_backlog(backlog_path)
    if not backlog_entries:
        print("ERROR: no spec rows found in backlog.md", file=sys.stderr)
        return 1

    mismatches: list[str] = []
    yaml_strings: dict[str, str] = {}
    yaml_dicts: dict[str, dict] = {}

    for spec_id, entry in sorted(backlog_entries.items()):
        spec_file = find_spec_file(features_dir, spec_id)
        blocked_reason: Optional[str] = None

        if spec_file is not None:
            spec_status, blocked_reason = parse_spec(spec_file)
            if spec_status is not None and spec_status != entry["status"]:
                # ARCH-186 migration tolerance: when backlog says done but spec.md
                # still shows queued/in_progress/draft, this is historical pollution
                # from BUG-185 (autostash race) — backlog is canonical. Skip the
                # mismatch error for done-state and trust backlog.
                if entry["status"] in ("done", "blocked"):
                    print(
                        f"NOTE: {spec_id} backlog={entry['status']} spec={spec_status} — "
                        f"trusting backlog (historical BUG-185 drift)",
                        file=sys.stderr,
                    )
                else:
                    mismatches.append(
                        f"MISMATCH: {spec_id} backlog={entry['status']} spec={spec_status}"
                    )
                    continue

        yaml_str, data = _build_pair(
            spec_id,
            entry["status"],
            entry["priority"],
            entry["kind"],
            blocked_reason,
        )
        yaml_strings[spec_id] = yaml_str
        yaml_dicts[spec_id] = data

    if mismatches:
        for msg in mismatches:
            print(msg, file=sys.stderr)
        return 2

    if not args.commit:
        for spec_id, yaml_str in yaml_strings.items():
            print(f"--- {spec_id}.yaml ---")
            print(yaml_str)
        print(f"Would write {len(yaml_strings)} files. Run with --commit to apply.")
        return 0

    lifecycle_dir.mkdir(parents=True, exist_ok=True)

    # Idempotency: all targets exist with matching content (ignoring volatile)?
    def _is_noop() -> bool:
        for sid, data in yaml_dicts.items():
            target = lifecycle_dir / f"{sid}.yaml"
            if not target.exists():
                return False
            existing = yaml.safe_load(target.read_text(encoding="utf-8"))
            if _cmp_data(existing or {}) != _cmp_data(data):
                return False
        return bool(yaml_dicts)

    if _is_noop():
        print("Already migrated, no-op.")
        return 0

    for spec_id, yaml_str in yaml_strings.items():
        (lifecycle_dir / f"{spec_id}.yaml").write_text(yaml_str, encoding="utf-8")

    print(f"Wrote {len(yaml_strings)} lifecycle files.")

    # Round-trip self-test (WT read, no git commit yet)
    failed: list[str] = []
    for spec_id, data in yaml_dicts.items():
        loaded = yaml.safe_load((lifecycle_dir / f"{spec_id}.yaml").read_text(encoding="utf-8"))
        if loaded is None or loaded.get("status") != data["status"]:
            failed.append(f"ROUND-TRIP FAILED: {spec_id} expected={data['status']} got={loaded}")

    if failed:
        for msg in failed:
            print(msg, file=sys.stderr)
        return 1

    print("Round-trip self-test: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
