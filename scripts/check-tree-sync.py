#!/usr/bin/env python3
"""Finds code changed in one of DLD's two prompt trees and not the other.

`.claude/` is what DLD runs; `template/.claude/` is what downstream projects receive. The
contract in `.claude/rules/template-sync.md` names what must stay identical and what
deliberately differs. The defect this framework produces most often is a fix landing in one
tree only, and nothing caught it: `diff -r` is useless here, because these files are *supposed*
to differ in their prose — spec ids stripped, header comments rewritten, wording hedged for
downstream users. template-sync.md says so explicitly for `check-prompt-integrity.mjs`:
"logic identical, header comments differ".

So this compares **function bodies, not files**. The `codebase-memory` graph supplies each
function's start and end line in each tree; the bodies at those lines are then compared
directly. A header comment rewritten above the code changes no function and stays silent; a
regex fixed in one tree only shows up immediately.

Why not the graph's own `SIMILAR_TO` edges, or its complexity metrics? Both were tried and
both lie. Edges are absent for many pairs whose files are byte-identical (measured: 33
"findings" of which 30 were files with zero diff), and metrics miss any edit that keeps the
line count — `lines`, `complexity` and `cognitive` were all equal across a real one-tree fix.
The graph is trusted for structure, which it knows exactly, and for nothing fuzzier.

Scope, stated plainly: this compares **function bodies only**. Module-level constants,
top-level statements and prose in either tree are outside every span the graph reports, so a
one-tree change to those is invisible here. It is a check on the executable twins, not a
replacement for reading `template-sync.md`.

Findings:

  DIVERGED             both trees define it, bodies differ
  MISSING_IN_TEMPLATE  root defines it, template's copy of the same file does not
  MISSING_IN_ROOT      template defines it, root's copy of the same file does not

Exit codes: 0 clean or unavailable, 1 findings, 2 the graph could not be queried.

`--require-graph` turns every "unavailable" path into exit 2. Locally a missing binary should
not fail anyone's commit; in CI a missing binary means the check silently measured nothing,
which is the exact failure mode this repo has been bitten by before — a green step that never
ran. CI passes the flag.

Requires the `codebase-memory-mcp` binary (external OSS, DeusData/codebase-memory-mcp) and a
`.cbmignore` un-skipping the hidden trees — without it the indexer never sees `.claude/` and
this check has nothing to compare. Set CBM_BIN to override binary discovery.
"""

from __future__ import annotations

import difflib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT_PREFIX = ".claude/"
TMPL_PREFIX = "template/.claude/"

# Only executable code is expected to be functionally identical across the trees.
CODE_SUFFIXES = (".mjs", ".js", ".py", ".sh")

BINARY_CANDIDATES = (
    Path.home() / "AppData/Local/Programs/codebase-memory-mcp/codebase-memory-mcp.exe",
    Path.home() / ".local/bin/codebase-memory-mcp",
    Path("/usr/local/bin/codebase-memory-mcp"),
)


def find_binary() -> Path | None:
    """Locate the codebase-memory binary, or None when it is not installed."""
    override = os.environ.get("CBM_BIN")
    if override:
        candidate = Path(override)
        return candidate if candidate.exists() else None

    on_path = shutil.which("codebase-memory-mcp")
    if on_path:
        return Path(on_path)

    for candidate in BINARY_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def parse_table(text: str) -> dict | None:
    """Parse the human table `query_graph` prints instead of JSON on 0.10.8.

        rows: 2  (cols: f, name)
          template/.claude/scripts/x.mjs readStdin "483" "487"
        total: 2

    `--json` wraps the envelope but not this payload, and there is no structuredContent
    to fall back on, so the table is the only machine-readable form the CLI offers for
    this tool. Values are shell-quoted, which is why shlex and not split() — a quoted
    number and a bare identifier sit in the same row.
    """
    lines = text.splitlines()
    header = next((ln for ln in lines if ln.startswith("rows:")), None)
    if header is None:
        return None

    match = re.search(r"\(cols:\s*(.+?)\)", header)
    columns = [c.strip() for c in match.group(1).split(",")] if match else []

    rows: list[list[str]] = []
    for line in lines:
        if not line.startswith(("  ", "\t")):
            continue
        try:
            values = shlex.split(line.strip())
        except ValueError:
            continue
        if values:
            rows.append(values)
    return {"columns": columns, "rows": rows}


def unwrap(parsed: dict) -> dict:
    """Return the tool result from whichever envelope this CLI version used.

    `--json` yields the MCP envelope: `structuredContent` holds the result, and `content`
    repeats it as a JSON string. Older builds printed the bare result. Accept all three
    rather than pinning a version — the shape is cheap to detect and a version pin here
    would break on the next upgrade instead of on a rewrite.
    """
    text = None
    content = parsed.get("content")
    if isinstance(content, list) and content and isinstance(content[0], dict):
        raw = content[0].get("text")
        if isinstance(raw, str):
            text = raw

    # A failed tool call still exits 0 and still returns a well-formed envelope — the only
    # marker is isError. Unwrapping it silently yields an empty result that reads exactly
    # like "nothing matched", which is how a rejected query first reached CI as
    # "the graph holds no functions".
    if parsed.get("isError"):
        raise RuntimeError(f"tool reported an error: {text or parsed}")

    # Prefer whichever copy actually carries data. `structuredContent` is the documented
    # place, but a build that puts a summary there and the real payload in `content` would
    # silently answer "no rows" — indistinguishable from a clean tree, and therefore the
    # worst possible failure for a check whose whole job is to notice things.
    candidates = []
    if isinstance(parsed.get("structuredContent"), dict):
        candidates.append(parsed["structuredContent"])
    if text is not None:
        try:
            decoded = json.loads(text)
            if isinstance(decoded, dict):
                candidates.append(decoded)
        except json.JSONDecodeError:
            table = parse_table(text)
            if table is not None:
                candidates.append(table)
    candidates.append(parsed)

    for candidate in candidates:
        if any(candidate.get(key) for key in ("rows", "projects", "nodes")):
            return candidate
    return candidates[0]


def call(binary: Path, tool: str, payload: dict, attempts: int = 3) -> dict:
    """Run one MCP tool through the CLI, returning its parsed JSON result.

    `--json` is mandatory, not cosmetic: 0.9.0 printed JSON by default, 0.10.8 prints a
    human table instead, and without the flag this script read 248 rows of formatted text
    as "no result". CI found that; a version-agnostic flag is the fix.

    Retries an empty result — each invocation starts a temporary daemon unless one is warm,
    and a cold start can finish with exit 0 and no output at all.
    """
    last = None
    for attempt in range(attempts):
        proc = subprocess.run(
            [str(binary), "cli", "--json", tool],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        # Structured logs go to stderr and the result to stdout, but a few log lines leak
        # into stdout on some builds. Take the last line that parses as JSON.
        for line in reversed([ln for ln in proc.stdout.splitlines() if ln.strip()]):
            try:
                return unwrap(json.loads(line))
            except json.JSONDecodeError:
                continue
        last = proc
        if attempt < attempts - 1:
            time.sleep(2)

    raise RuntimeError(
        f"{tool} returned no JSON after {attempts} attempts (last exit {last.returncode}). "
        f"stdout={last.stdout[-600:]!r} stderr={last.stderr[-400:]!r}"
    )


def project_for(binary: Path, repo_root: Path) -> str | None:
    """Return the indexed project name whose root_path is this repo."""
    result = call(binary, "list_projects", {})
    wanted = str(repo_root).replace("\\", "/").rstrip("/").lower()
    for project in result.get("projects", []):
        root = str(project.get("root_path", "")).replace("\\", "/").rstrip("/").lower()
        if root == wanted:
            return project["name"]
    return None


def is_code(path: str) -> bool:
    return path.endswith(CODE_SUFFIXES)


def relative(path: str) -> str:
    """Strip whichever tree prefix a path carries, so twins share one key."""
    if path.startswith(TMPL_PREFIX):
        return path[len(TMPL_PREFIX) :]
    if path.startswith(ROOT_PREFIX):
        return path[len(ROOT_PREFIX) :]
    return path


def collect_symbols(binary: Path, project: str) -> tuple[dict, dict, list[str]]:
    """Return (root, template) maps of (file, name) -> span, plus sample paths seen.

    The samples exist so that "no functions found" can say *why*. The query matched or it
    did not; the paths it returned are the only way to tell a stale index from a prefix
    that does not look the way this script assumes.
    """
    # One label per query. `(n:Function OR n:Method)` works on the Cypher subset this tool
    # shipped in 0.9.0, but the subset is not a documented contract and a rejected query
    # comes back as a well-formed empty result, not as an error the caller notices. Two
    # plain MATCHes ask for less and cost one extra call.
    rows: list[list] = []
    for label in ("Function", "Method"):
        result = call(
            binary,
            "query_graph",
            {
                "project": project,
                "query": (
                    f"MATCH (n:{label}) WHERE n.file_path CONTAINS 'claude/' "
                    "RETURN n.file_path AS f, n.name AS name, n.start_line AS s, "
                    "n.end_line AS e"
                ),
            },
        )
        rows.extend(result.get("rows", []))
    root: dict[tuple[str, str], tuple[int, int]] = {}
    tmpl: dict[tuple[str, str], tuple[int, int]] = {}
    samples: list[str] = []
    for path, name, start, end in rows:
        if len(samples) < 5 and path not in samples:
            samples.append(path)
        if not is_code(path):
            continue
        key = (relative(path), name)
        span = (int(start), int(end))
        if path.startswith(TMPL_PREFIX):
            tmpl[key] = span
        elif path.startswith(ROOT_PREFIX):
            root[key] = span
    return root, tmpl, samples


def read_lines(repo_root: Path, tree_prefix: str, rel_file: str, cache: dict) -> list[str] | None:
    """Read a file once per run, normalising line endings and trailing whitespace."""
    path = repo_root / tree_prefix / rel_file
    if path in cache:
        return cache[path]
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        cache[path] = None
        return None
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    cache[path] = lines
    return lines


def body(lines: list[str] | None, span: tuple[int, int]) -> list[str] | None:
    """Slice a function body out of a file by its 1-indexed inclusive line span."""
    if lines is None:
        return None
    start, end = span
    if start < 1 or end < start or end > len(lines):
        return None
    return lines[start - 1 : end]


def analyse(repo_root: Path, root: dict, tmpl: dict) -> tuple[list, int, int]:
    """Compare every twin body. Returns (findings, twins compared, unreadable spans)."""
    root_files = {f for f, _ in root}
    tmpl_files = {f for f, _ in tmpl}
    both_trees = root_files & tmpl_files

    findings: list[tuple[str, str, str, str]] = []
    cache: dict[Path, list[str] | None] = {}
    compared = 0
    unreadable = 0

    for key in sorted(root.keys() | tmpl.keys()):
        rel_file, name = key
        if rel_file not in both_trees:
            # The file itself lives in one tree only — template-sync.md governs that,
            # and it lists the deliberate cases. Not a drifted twin.
            continue

        in_root, in_tmpl = key in root, key in tmpl
        if in_root and not in_tmpl:
            findings.append(("MISSING_IN_TEMPLATE", rel_file, name, ""))
            continue
        if in_tmpl and not in_root:
            findings.append(("MISSING_IN_ROOT", rel_file, name, ""))
            continue

        root_body = body(read_lines(repo_root, ROOT_PREFIX, rel_file, cache), root[key])
        tmpl_body = body(read_lines(repo_root, TMPL_PREFIX, rel_file, cache), tmpl[key])

        if root_body is None or tmpl_body is None:
            # Stale line spans mean the index predates an edit — say so rather than
            # reporting a difference we did not actually read.
            unreadable += 1
            continue

        compared += 1
        if root_body != tmpl_body:
            # difflib, not a zip: a one-line insertion shifts every later line and a
            # positional compare would report the whole tail as changed.
            delta = sum(
                1
                for line in difflib.unified_diff(root_body, tmpl_body, n=0)
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            findings.append(("DIVERGED", rel_file, name, f"{delta} line(s)"))

    severity = {"DIVERGED": 0, "MISSING_IN_TEMPLATE": 1, "MISSING_IN_ROOT": 2}
    findings.sort(key=lambda f: (severity[f[0]], f[1], f[2]))
    return findings, compared, unreadable


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    require_graph = "--require-graph" in sys.argv[1:]

    def unavailable() -> int:
        """0 locally (a missing tool is not a broken commit), 2 under --require-graph."""
        if require_graph:
            print("  --require-graph was passed: treating this as a failure, not a skip.")
            return 2
        return 0

    binary = find_binary()
    if binary is None:
        print("TREE_SYNC_UNAVAILABLE: codebase-memory-mcp not installed — nothing ran.")
        print("  Install it, or set CBM_BIN, to enable this check.")
        return unavailable()

    if not (repo_root / ".cbmignore").exists():
        print("TREE_SYNC_UNAVAILABLE: no .cbmignore — the indexer skips hidden directories,")
        print("  so .claude/ and template/.claude/ are absent from the graph and there is")
        print("  nothing to compare. Add '!.claude/' and '!template/.claude/' to .cbmignore.")
        return unavailable()

    try:
        project = project_for(binary, repo_root)
        if project is None:
            print(f"TREE_SYNC_UNAVAILABLE: {repo_root} is not indexed — nothing ran.")
            print('  Index it first: index_repository(repo_path=".", mode="full")')
            return unavailable()
        root, tmpl, samples = collect_symbols(binary, project)
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"TREE_SYNC_ERROR: {exc}", file=sys.stderr)
        return 2

    if not root and not tmpl:
        print("TREE_SYNC_UNAVAILABLE: the graph holds no functions under either tree.")
        print('  The index predates .cbmignore — rebuild with mode="full" and re-run.')
        if samples:
            print("  The query DID return rows; none matched the expected prefixes")
            print(f"  ('{ROOT_PREFIX}' / '{TMPL_PREFIX}') with a code suffix. Sample paths:")
            for sample in samples:
                print(f"    {sample}")
        else:
            print("  The query returned no rows at all.")
        return unavailable()

    findings, compared, unreadable = analyse(repo_root, root, tmpl)

    print(
        f"tree sync — {len(root)} root symbols, {len(tmpl)} template symbols, {compared} twins compared"
    )
    if unreadable:
        print(f"  ({unreadable} span(s) unreadable — the index is behind the files; rebuild it)")

    if not findings:
        print("\nclean: every twin body in the executable trees is identical.")
        return 0

    print(f"\n{len(findings)} finding(s):\n")
    label = {
        "DIVERGED": "bodies differ — fixed in one tree only?",
        "MISSING_IN_TEMPLATE": "defined in .claude/, absent from template/.claude/",
        "MISSING_IN_ROOT": "defined in template/.claude/, absent from .claude/",
    }
    current = None
    for kind, rel_file, name, detail in findings:
        if kind != current:
            print(f"  {kind} — {label[kind]}")
            current = kind
        suffix = f"  ({detail})" if detail else ""
        print(f"    {rel_file}::{name}{suffix}")

    print("\nCheck `.claude/rules/template-sync.md` before syncing — some divergence there is")
    print("deliberate and documented. Anything it does not list is a defect.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
