"""
Module: gate_logic
Role: Pure-function core for gate-daemon shadow (ARCH-190 Wave 1 MP-001).
      Extracted from callback.py — ZERO I/O on import, stdlib-only.

Uses:
  - re: _SPEC_ID_RE constant, match_subject patterns
  - subprocess: fetch_develop, find_implementation_commit (only inside function bodies)
  - pathlib: Path type for parse_allowed_files
  - logging: logging.getLogger(__name__)
  - dataclasses: reserved for future GateResult value-object

Used by:
  - gate-daemon.py: fetch_develop, parse_allowed_files, match_subject,
                    find_implementation_commit

Glossary: ai/glossary/ (orchestrator domain)

FF-09 invariant: ZERO imports from callback, lifecycle, db, orchestrator.
Pure-functional core: all subprocess calls are inside function bodies only.
"""

import logging
import re
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Spec-id regex (L-derived-2: must stay in sync with callback.py:43 and
# orchestrator.py:308 until MP-011 consolidation in Wave 5).
# `[a-z]*` captures sub-spec suffixes (ARCH-176a/b/c).
# GROWTH prefix added in TECH-189 Task 6.
# ---------------------------------------------------------------------------
_SPEC_ID_RE = re.compile(r"(TECH|FTR|BUG|ARCH|GROWTH)-\d+[a-z]*")

# ---------------------------------------------------------------------------
# Allowed Files section parsing — mirrors callback._parse_allowed_files_*
# ---------------------------------------------------------------------------

# Extension regex for legacy specs (any backtick-wrapped path with extension).
_ALLOWED_FILE_EXT_RE = re.compile(r"`([^\s`\n]+\.[a-zA-Z][\w-]*)`")

# TECH-167 v1 canonical format
_ALLOWED_FILES_V1_HEADING_RE = re.compile(r"^##[ \t]+Allowed Files[ \t]*$")
_ALLOWED_FILES_V1_MARKER_RE = re.compile(r"<!--\s*callback-allowlist\s+v1\b[^>]*-->")
_ALLOWED_FILES_V1_BULLET_RE = re.compile(r"^-[ \t]+`([^\s`\n]+\.[A-Za-z][\w-]*)`(?:[ \t]+.*)?$")

# TECH-166 legacy fallback heading variants (case-insensitive):
#   ## Allowed Files, ## Updated Allowed Files, ## Files Allowed to Modify
_ALLOWED_FILES_HEADING_RE = re.compile(
    r"^##\s+(?:(?:Updated\s+)?Allowed\s+Files\b|Files\s+Allowed\s+to\s+Modify\b)",
    re.IGNORECASE,
)
_NEXT_H2_RE = re.compile(r"^##\s+\S")


def _parse_allowed_files_v1(spec_text: str) -> list[str] | None:
    """Strict canonical v1 parser. Returns:

    list[str]: >=1 paths (success).
    []        : marker present but ZERO valid bullets — degrade-closed.
    None      : v1 marker not present (caller should try legacy fallback).

    Copied verbatim from callback._parse_allowed_files_v1.
    """
    lines = spec_text.splitlines()

    # Locate the canonical heading (must be EXACT — case-sensitive, no suffix).
    heading_idxs = [i for i, ln in enumerate(lines) if _ALLOWED_FILES_V1_HEADING_RE.match(ln)]
    if not heading_idxs:
        return None  # caller falls back to legacy
    # Use the first canonical heading; section ends at next H2.
    start = heading_idxs[0] + 1
    end = len(lines)
    for j in range(start, len(lines)):
        if _NEXT_H2_RE.match(lines[j]):
            end = j
            break
    section = lines[start:end]
    section_text = "\n".join(section)

    # Marker is the v1 opt-in. Without it, spec is legacy; defer.
    if not _ALLOWED_FILES_V1_MARKER_RE.search(section_text):
        return None

    # Strict mode: only canonical bullets count.
    paths: list[str] = []
    for ln in section:
        m = _ALLOWED_FILES_V1_BULLET_RE.match(ln)
        if m:
            paths.append(m.group(1))
    # Empty list with marker present = degrade-closed (explicit empty allowlist).
    return paths


def _parse_allowed_files_legacy(spec_text: str) -> list[str] | None:
    """Pre-TECH-167 parser: heading variants + any backticked-path-shape.

    Used only when v1 marker is absent (legacy specs). Same semantics as the
    pre-TECH-167 implementation: section heading match -> extract every
    backticked path inside the section.

    Copied verbatim from callback._parse_allowed_files_legacy.
    """
    lines = spec_text.splitlines()
    in_section = False
    section_buf: list[str] = []
    for line in lines:
        if not in_section:
            if _ALLOWED_FILES_HEADING_RE.match(line):
                in_section = True
            continue
        if _NEXT_H2_RE.match(line):
            break
        section_buf.append(line)
    if not in_section:
        return None
    return _ALLOWED_FILE_EXT_RE.findall("\n".join(section_buf))


def parse_allowed_files(spec_path: Path) -> list[str] | None:
    """Extract allowlist from a spec file.

    Public API (gate-daemon entry point). Mirrors callback._parse_allowed_files.

    Strategy (TECH-167):
        1. If spec has the v1 marker -> strict canonical parse (no fallback).
        2. Else -> legacy parser (heading variants, any backticked paths).
        3. Section absent entirely -> None (degrade-open sentinel).

    Args:
        spec_path: Absolute path to the spec markdown file.

    Returns:
        list[str]: explicit list (may be empty if v1 marker present but
                   bullets malformed -> degrade-closed).
        None:      no Allowed Files section at all (legacy spec without
                   any allowlist — caller decides degrade-open semantics).
    """
    try:
        text = spec_path.read_text(errors="replace")
    except OSError as exc:
        log.warning("ALLOWED_FILES: read failed for %s: %s", spec_path, exc)
        return None

    v1 = _parse_allowed_files_v1(text)
    if v1 is not None:
        log.info(
            "ALLOWED_FILES: v1 canonical parse for %s -> %d path(s)",
            spec_path.name,
            len(v1),
        )
        return v1

    legacy = _parse_allowed_files_legacy(text)
    if legacy is not None:
        log.info(
            "ALLOWED_FILES: legacy fallback parse for %s -> %d path(s)",
            spec_path.name,
            len(legacy),
        )
    return legacy


def match_subject(subject: str, spec_id: str) -> bool:
    """Return True iff the commit *subject* (first line) declares it implements spec_id.

    Renamed from callback._subject_implements.

    TECH-177 / L-derived-3: Body/footer/trailer mentions DO NOT count.
    Cross-references in body (e.g. `see also FTR-925`, `Refs: FTR-925`) caused
    false-positive auto-close in awardybot 2026-05-04 incident.

    Accepted forms (canonical):
      - Conventional Commits with spec_id in scope:
          `feat(FTR-925): ...`
          `fix(FTR-925)!: ...`
          `feat(FTR-925,FTR-926): ...`        # multi-spec scope
          `chore(area, FTR-925): ...`         # whitespace tolerated
      - Merge commit:
          `merge FTR-925`
          `merge FTR-925: ...`
      - Legacy bare prefix:
          `FTR-925: ...`

    Rejected:
      - body / footer / trailer mentions
      - `feat(other): ... see FTR-925`        # ID after ':' is not a scope
      - `feat: FTR-925 something`             # no scope, ID inside message

    Args:
        subject: First line of a git commit message.
        spec_id: Spec identifier to match (e.g. "TECH-189", "GROWTH-042").

    Returns:
        True if subject declares implementation of spec_id.
    """
    if not subject or not spec_id:
        return False
    # Conventional: <type>(<scope>)[!]: <description>
    m = re.match(r"^[a-z]+\(([^)]*)\)!?:", subject)
    if m:
        scopes = [s.strip() for s in m.group(1).split(",")]
        if spec_id in scopes:
            return True
    # Merge commit: `merge SPEC-ID` (start, optionally followed by ':' or space)
    if re.match(rf"^merge\s+{re.escape(spec_id)}\b", subject, re.IGNORECASE):
        return True
    # Legacy bare: `SPEC-ID: <description>`
    if re.match(rf"^{re.escape(spec_id)}:\s", subject):
        return True
    return False


def fetch_develop(project_path: str, timeout: int = 15) -> bool:
    """Refresh origin/develop ref before gate evaluation.

    Renamed from callback._fetch_develop. Default timeout changed to 15s
    (aggressive per-fetch — Devil Attack 3 mitigation, spec §Approach 2).

    Best-effort: on network failure we fall through and evaluate against
    the local snapshot of origin/develop. The gate is conservative
    (only marks done on positive match), so stale-origin failure means
    "may stay blocked one extra cycle", not "false-done".

    Args:
        project_path: Absolute path to the git project root.
        timeout: Subprocess timeout in seconds (default 15, not 30).

    Returns:
        True if fetch succeeded, False on any error.
    """
    try:
        subprocess.run(
            ["git", "-C", project_path, "fetch", "origin", "develop", "--quiet"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return True
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("FETCH: failed for %s: %s", project_path, exc)
        return False


def find_implementation_commit(
    project_path: str,
    spec_id: str,
    allowed_files: list[str],
) -> str | None:
    """Return the SHA of the first commit on origin/develop that implements spec_id.

    Renamed from callback._is_done_on_develop. Returns commit SHA (str) instead
    of bare bool, so gate-daemon can record matching_commit_sha in shadow JSONL.

    Two-step approach (L-derived-3 / Devil Attack 2+10 mitigation):
        Step 1: `git log origin/develop --pretty=%H%x00%s -- <allowed_files>`
                Path filter first — only commits touching allowed paths are examined.
        Step 2: Python loop with match_subject(subject, spec_id).
                Subject-only matching — body/footer mentions are IGNORED.

    NOT bare `--grep SPEC-ID` (would match body/trailer mentions = false positives).

    No activity window. No `--all`. No auto-close path. The state of
    origin/develop is the only thing that matters.

    Conservative fail-closed: on any error or empty inputs, returns None
    (ambiguity -> blocked, not done).

    Args:
        project_path: Absolute path to the git project root.
        spec_id: Spec identifier to match (e.g. "TECH-189", "GROWTH-042").
        allowed_files: Non-empty list of relative paths from the spec allowlist.

    Returns:
        Full commit SHA string (truthy) if implementation found, None otherwise.
    """
    if not spec_id or not allowed_files:
        return None
    cmd = [
        "git",
        "-C",
        project_path,
        "log",
        "origin/develop",
        "--pretty=%H%x00%s",
        "--",
        *allowed_files,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("GATE: git log failed for %s: %s", spec_id, exc)
        return None
    if r.returncode != 0:
        log.warning(
            "GATE: git log rc=%s stderr=%s",
            r.returncode,
            r.stderr.strip()[:200],
        )
        return None
    for line in r.stdout.splitlines():
        if not line:
            continue
        sha, _, subject = line.partition("\x00")
        if match_subject(subject, spec_id):
            return sha.strip()
    return None
