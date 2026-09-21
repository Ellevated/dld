#!/usr/bin/env python3
"""Finds code changed in one of DLD's two prompt trees and not the other.

`.claude/` is what DLD runs; `template/.claude/` is what downstream projects receive. The
contract in `.claude/rules/template-sync.md` names what must stay identical and what
deliberately differs. The defect this framework produces most often is a fix landing in one
tree only, and nothing caught it: `diff -r` is useless here, because these files are *supposed*
to differ in their prose — spec ids stripped, header comments rewritten, wording hedged for
downstream users.

So this compares **function bodies, not files**. `ast-grep` extracts every top-level function
declaration and arrow-function const from both trees; bodies with the same `(file, name)` key
are compared textually. A header comment rewritten above the code changes no function and stays
silent; a regex fixed in one tree only shows up immediately.

Why `ast-grep` and not the `codebase-memory` graph this used to read (until 2026-09-21): the
tool was removed from the contour — 0 calls in 52 fleet runs (EXP-002) and 0 hook injections in
10 sessions (EXP-004), while its daemon burned CPU and its binary had to be downloaded into CI.
`ast-grep` parses the same tree-sitter syntax locally, on demand, with no index to keep fresh —
so there is nothing to rebuild and no staleness window between the graph and the files.

Scope, stated plainly: extraction covers **top-level** declarations in `.mjs`/`.js`. Functions
nested inside another function are compared as part of their enclosing body; `.py`/`.sh` files,
should any appear under the trees, are reported as SKIPPED rather than compared silently.
Module-level constants, top-level statements and prose in either tree are outside every unit,
so a one-tree change to those is invisible here. It is a check on the executable twins, not a
replacement for reading `template-sync.md`.

Findings:

  DIVERGED             both trees define it, bodies differ
  MISSING_IN_TEMPLATE  root defines it, template's copy of the same file does not
  MISSING_IN_ROOT      template defines it, root's copy of the same file does not

Exit codes: 0 clean or unavailable, 1 findings, 2 the extractor could not be run.

`--require-tool` turns every "unavailable" path into exit 2. Locally a missing binary should
not fail anyone's commit; in CI a missing binary means the check silently measured nothing,
which is the exact failure mode this repo has been bitten by before — a green step that never
ran. CI passes the flag.

Requires `ast-grep` (`pip install ast-grep-cli==0.45.3`, or `npm i -g @ast-grep/cli`). Set
`AST_GREP_BIN` to override binary discovery.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT_PREFIX = ".claude/"
TMPL_PREFIX = "template/.claude/"

# Only executable code is expected to be functionally identical across the trees.
CODE_SUFFIXES = (".mjs", ".js")
# Extractor coverage, honestly: anything with these suffixes gets a loud SKIPPED line.
UNSUPPORTED_SUFFIXES = (".py", ".sh")

# `function $NAME` also matches `export function $NAME` — the capture sits inside the
# declaration node and the leading `export ` is reported separately (charCount.leading).
JS_PATTERNS = (
    "function $NAME($$$) { $$$ }",
    "async function $NAME($$$) { $$$ }",
    "const $NAME = ($$$) => { $$$ }",
    "const $NAME = async ($$$) => { $$$ }",
    "const $NAME = ($$$) => $E",
    "const $NAME = async ($$$) => $E",
)


def find_tool() -> str | None:
    """Locate the ast-grep binary, or None when it is not installed."""
    override = os.environ.get("AST_GREP_BIN")
    if override:
        candidate = Path(override)
        return str(candidate) if candidate.exists() else None
    return shutil.which("ast-grep")


def relative(path: str) -> str:
    """Strip whichever tree prefix a path carries, so twins share one key."""
    if path.startswith(TMPL_PREFIX):
        return path[len(TMPL_PREFIX) :]
    if path.startswith(ROOT_PREFIX):
        return path[len(ROOT_PREFIX) :]
    return path


def read_lines(path: Path, cache: dict) -> list[str] | None:
    """Read a file once per run, normalising line endings and trailing whitespace."""
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


def normalise(text: str) -> list[str]:
    """A body as comparable lines: LF endings, no trailing whitespace."""
    return [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]


def run_pattern(tool: str, pattern: str, tree_dir: Path) -> list[dict]:
    """One ast-grep pattern over one tree; returns raw match objects."""
    proc = subprocess.run(
        [tool, "run", "--pattern", pattern, "--lang", "js", "--json=stream", str(tree_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    # ast-grep follows grep's convention: 0 = matches found, 1 = none, >1 = error.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"ast-grep failed on {tree_dir} (exit {proc.returncode}): stderr={proc.stderr[-400:]!r}"
        )
    matches = []
    for line in proc.stdout.splitlines():
        if line.strip():
            matches.append(json.loads(line))
    return matches


def collect(repo_root: Path, prefix: str, tool: str, cache: dict) -> tuple[dict, list[str]]:
    """Map (file, name) -> normalised body for one tree, plus skipped files."""
    tree_dir = repo_root / prefix
    symbols: dict[tuple[str, str], list[str]] = {}
    skipped: list[str] = []

    for path in sorted(tree_dir.rglob("*")):
        if path.is_file() and path.suffix in UNSUPPORTED_SUFFIXES:
            skipped.append(path.relative_to(repo_root).as_posix())

    for pattern in JS_PATTERNS:
        for match in run_pattern(tool, pattern, tree_dir):
            name = match["metaVariables"]["single"]["NAME"]["text"]
            start_line = match["range"]["start"]["line"]
            abs_path = Path(match["file"])
            lines = read_lines(abs_path, cache)
            if lines is None or start_line >= len(lines):
                continue
            # Top-level only: a nested `const x = () => …` inside a function would key on
            # the same name from a different scope. Indentation is the cheap discriminator
            # that matches this corpus' uniform formatting.
            if lines[start_line][:1].isspace():
                continue
            rel_file = relative(abs_path.relative_to(repo_root).as_posix())
            body = normalise(match["text"])
            key = (rel_file, name)
            previous = symbols.get(key)
            # Overlapping patterns must not double-count: keep the outermost match.
            if previous is None or len(body) > len(previous):
                symbols[key] = body
    return symbols, skipped


def analyse(root: dict, tmpl: dict) -> tuple[list, int]:
    """Compare every twin body. Returns (findings, twins compared)."""
    root_files = {f for f, _ in root}
    tmpl_files = {f for f, _ in tmpl}
    both_trees = root_files & tmpl_files

    findings: list[tuple[str, str, str, str]] = []
    compared = 0

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

        compared += 1
        if root[key] != tmpl[key]:
            # difflib, not a zip: a one-line insertion shifts every later line and a
            # positional compare would report the whole tail as changed.
            delta = sum(
                1
                for line in difflib.unified_diff(root[key], tmpl[key], n=0)
                if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
            )
            findings.append(("DIVERGED", rel_file, name, f"{delta} line(s)"))

    severity = {"DIVERGED": 0, "MISSING_IN_TEMPLATE": 1, "MISSING_IN_ROOT": 2}
    findings.sort(key=lambda f: (severity[f[0]], f[1], f[2]))
    return findings, compared


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    require_tool = "--require-tool" in sys.argv[1:]

    def unavailable() -> int:
        """0 locally (a missing tool is not a broken commit), 2 under --require-tool."""
        if require_tool:
            print("  --require-tool was passed: treating this as a failure, not a skip.")
            return 2
        return 0

    tool = find_tool()
    if tool is None:
        print("TREE_SYNC_UNAVAILABLE: ast-grep not installed — nothing ran.")
        print("  Install it (`pip install ast-grep-cli==0.45.3` or `npm i -g @ast-grep/cli`),")
        print("  or set AST_GREP_BIN, to enable this check.")
        return unavailable()

    cache: dict = {}
    try:
        root, skipped_root = collect(repo_root, ROOT_PREFIX, tool, cache)
        tmpl, skipped_tmpl = collect(repo_root, TMPL_PREFIX, tool, cache)
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"TREE_SYNC_ERROR: {exc}", file=sys.stderr)
        return 2

    for skipped in sorted(set(skipped_root) | set(skipped_tmpl)):
        print(f"TREE_SYNC_SKIPPED: {skipped} — extractor covers {', '.join(CODE_SUFFIXES)} only")

    if not root and not tmpl:
        print("TREE_SYNC_UNAVAILABLE: no top-level functions found under either tree.")
        print("  Either the trees are empty or ast-grep matched nothing — investigate.")
        return unavailable()

    findings, compared = analyse(root, tmpl)

    print(
        f"tree sync — {len(root)} root symbols, {len(tmpl)} template symbols, {compared} twins compared"
    )

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
