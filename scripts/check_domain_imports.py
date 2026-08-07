#!/usr/bin/env python3
"""
Deterministic import-direction check.

Enforces the layering rule `shared -> infra -> domains -> api`: a module may
import from its own layer and from layers to its LEFT, never to its right. Also
forbids one domain importing another directly — domains talk through `shared`
or `infra`, never sideways.

Run BEFORE AI review. The rule has existed in CLAUDE.md since the first commit;
until now nothing checked it, and `agents/review.md` told the reviewer to run
this exact filename while the file did not exist.

Exit 0 = PASS (or nothing to check), Exit 1 = violations, Exit 2 = usage.

Usage:
    python scripts/check_domain_imports.py                    # whole src/ tree
    python scripts/check_domain_imports.py file1.py file2.py  # only these
    python scripts/check_domain_imports.py --src app          # different root
    python scripts/check_domain_imports.py --json             # machine-readable

A project with no source root is not an error — this framework repo has none,
and a check that fails where it does not apply gets switched off everywhere.
"""

import ast
import json
import sys
from pathlib import Path
from typing import NamedTuple

# Left to right. A module may import its own layer and anything to its left.
LAYERS = ("shared", "infra", "domains", "api")
RANK = {name: i for i, name in enumerate(LAYERS)}

DEFAULT_SRC = "src"


class Violation(NamedTuple):
    """One import that points the wrong way."""

    file: str
    line: int
    check: str
    message: str


def _module_parts(file_path: Path, src_root: Path) -> list[str] | None:
    """Package path of a file relative to the source root, as components.

    `src/domains/billing/service.py` -> ['domains', 'billing', 'service'].
    Returns None when the file lives outside the source root.
    """
    try:
        rel = file_path.resolve().relative_to(src_root.resolve())
    except ValueError:
        return None
    parts = list(rel.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return parts


def _target_parts(node: ast.AST, own_parts: list[str], src_root_name: str) -> list[str] | None:
    """Resolve an import node to package components inside the source tree.

    Absolute (`from domains.billing import x`) and relative (`from ..shared
    import x`) forms both land in the same shape. A leading `src.` is dropped so
    both `src.domains.x` and `domains.x` resolve — projects write it both ways.
    Returns None for anything that is not a project import (stdlib, packages).
    """
    if isinstance(node, ast.Import):
        # `import domains.billing` — take the first alias; the layer is in it.
        raw = node.names[0].name.split(".") if node.names else []
    elif isinstance(node, ast.ImportFrom):
        if node.level:
            # Relative: strip `level` components off this module's own package.
            # level=1 is the current package, so drop the module name itself.
            base = own_parts[:-1]
            extra = node.level - 1
            base = base[: len(base) - extra] if extra else base
            if extra and len(own_parts) - 1 - extra < 0:
                return None  # climbs above the source root
            raw = base + (node.module.split(".") if node.module else [])
        else:
            raw = node.module.split(".") if node.module else []
    else:
        return None

    if raw and raw[0] == src_root_name:
        raw = raw[1:]
    if not raw or raw[0] not in RANK:
        return None  # not a layered project import
    return raw


def _layer_of(parts: list[str]) -> str | None:
    return parts[0] if parts and parts[0] in RANK else None


def _domain_of(parts: list[str]) -> str | None:
    """Domain name for a `domains/<name>/...` path, else None."""
    if len(parts) >= 2 and parts[0] == "domains":
        return parts[1]
    return None


def check_file(file_path: Path, src_root: Path) -> list[Violation]:
    """Every import in one file, checked against the layering rule."""
    own_parts = _module_parts(file_path, src_root)
    if own_parts is None:
        return []
    own_layer = _layer_of(own_parts)
    if own_layer is None:
        return []  # file sits outside the layered tree; nothing to enforce

    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        # A file that does not parse is the linter's problem, not this check's.
        return []

    own_domain = _domain_of(own_parts)
    src_root_name = src_root.name
    violations: list[Violation] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        target = _target_parts(node, own_parts, src_root_name)
        if target is None:
            continue
        target_layer = _layer_of(target)
        if target_layer is None:
            continue

        if RANK[target_layer] > RANK[own_layer]:
            violations.append(
                Violation(
                    file=str(file_path),
                    line=node.lineno,
                    check="IMPORT_DIRECTION",
                    message=(
                        f"{own_layer} imports {target_layer} "
                        f"({'.'.join(target)}) — allowed direction is "
                        f"{' -> '.join(LAYERS)}"
                    ),
                )
            )
            continue

        target_domain = _domain_of(target)
        if own_domain and target_domain and own_domain != target_domain:
            violations.append(
                Violation(
                    file=str(file_path),
                    line=node.lineno,
                    check="CROSS_DOMAIN",
                    message=(
                        f"domain '{own_domain}' imports domain '{target_domain}' "
                        f"({'.'.join(target)}) — route it through shared or infra"
                    ),
                )
            )

    return violations


def collect_files(args: list[str], src_root: Path) -> list[Path]:
    """Explicit file list, or every .py under the source root."""
    if args:
        return [Path(a) for a in args if a.endswith(".py")]
    if not src_root.is_dir():
        return []
    return sorted(p for p in src_root.rglob("*.py") if "__pycache__" not in p.parts)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    as_json = "--json" in argv
    if as_json:
        argv.remove("--json")

    src_name = DEFAULT_SRC
    if "--src" in argv:
        i = argv.index("--src")
        if i + 1 >= len(argv):
            print("Error: --src needs a directory", file=sys.stderr)
            return 2
        src_name = argv[i + 1]
        del argv[i : i + 2]

    src_root = Path(src_name)

    if not src_root.is_dir() and not argv:
        msg = f"IMPORT CHECK SKIPPED (no {src_name}/ directory)"
        print(json.dumps({"status": "skipped", "reason": msg}) if as_json else msg)
        return 0

    files = collect_files(argv, src_root)
    if not files:
        msg = "IMPORT CHECK PASSED (no Python files to check)"
        print(json.dumps({"status": "passed", "violations": []}) if as_json else msg)
        return 0

    violations: list[Violation] = []
    for f in files:
        if f.exists():
            violations.extend(check_file(f, src_root))

    if as_json:
        print(
            json.dumps(
                {
                    "status": "failed" if violations else "passed",
                    "checked": len(files),
                    "violations": [v._asdict() for v in violations],
                },
                indent=2,
            )
        )
        return 1 if violations else 0

    if not violations:
        print(f"IMPORT CHECK PASSED ({len(files)} file(s))")
        return 0

    print("IMPORT CHECK FAILED:")
    for v in violations:
        print(f"  - {v.file}:{v.line}: [{v.check}] {v.message}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
