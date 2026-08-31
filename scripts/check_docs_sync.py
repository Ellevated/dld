#!/usr/bin/env python3
"""
Deterministic documentation-sync check: env vars the code reads must be documented.

`agents/review.md` has told the reviewer to run this file for a long time, and the
file did not exist — so the reviewer hit a missing-file error and moved on. Its
stated red flag was "changed settings.py but .env.example not updated"; this is
that check, in the stronger form that catches the actual production failure: an
environment variable the code reads and nobody wrote down. The deploy comes up,
the variable is unset, and the failure surfaces somewhere unrelated.

Detects `os.environ["X"]`, `os.environ.get("X")`, `os.getenv("X")` and the
`from os import environ` spellings, via ast — a regex trips over line breaks and
reports the variable named in a comment.

The other red flag in review.md — "documenter agent skipped without reason" — is
not a property of the source tree and stays a judgment call for the reviewer.

Exit 0 = PASS (or nothing to check), Exit 1 = undocumented vars, Exit 2 = usage.

Usage:
    python scripts/check_docs_sync.py                    # whole tree
    python scripts/check_docs_sync.py src/config.py ...  # only these files
    python scripts/check_docs_sync.py --env .env.sample  # different template
    python scripts/check_docs_sync.py --json
"""

import ast
import json
import sys
from pathlib import Path
from typing import NamedTuple

# Env-file templates, in the order they are looked for.
ENV_TEMPLATES = (".env.example", ".env.sample", ".env.template", ".env.dist")

# Variables the runtime or CI provides. Documenting these in .env.example would
# be noise, and demanding it is how a check gets switched off.
AMBIENT = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "USERNAME",
        "SHELL",
        "LANG",
        "LC_ALL",
        "TZ",
        "TMPDIR",
        "TEMP",
        "TMP",
        "PWD",
        "OLDPWD",
        "HOSTNAME",
        "TERM",
        "PYTHONPATH",
        "PYTHONHASHSEED",
        "PYTHONUNBUFFERED",
        "PYTHONDONTWRITEBYTECODE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CI",
        "GITHUB_ACTIONS",
        "GITHUB_TOKEN",
        "GITHUB_SHA",
        "GITHUB_REF",
        "GITHUB_WORKSPACE",
        "GITHUB_REPOSITORY",
        "RUNNER_OS",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "SYSTEMROOT",
        "USERPROFILE",
    }
)

SKIP_DIRS = frozenset({"__pycache__", ".git", "node_modules", "venv", ".venv", "build", "dist"})


class Finding(NamedTuple):
    """One env var read by the code and absent from the template."""

    file: str
    line: int
    var: str


def _is_environ(node: ast.AST) -> bool:
    """True for `os.environ` and a bare `environ`."""
    if isinstance(node, ast.Attribute):
        return node.attr == "environ"
    return isinstance(node, ast.Name) and node.id == "environ"


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def env_vars_in(file_path: Path) -> list[tuple[int, str]]:
    """Every env var name this file reads, with line numbers.

    A dynamic key (`os.getenv(name)`) is deliberately skipped rather than
    guessed at — a check that invents findings gets ignored.
    """
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []

    found: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        # os.environ["X"]
        if isinstance(node, ast.Subscript) and _is_environ(node.value):
            name = _const_str(node.slice)
            if name:
                found.append((node.lineno, name))
            continue

        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func

        # os.getenv("X") / getenv("X")
        is_getenv = (isinstance(func, ast.Attribute) and func.attr == "getenv") or (
            isinstance(func, ast.Name) and func.id == "getenv"
        )
        # os.environ.get("X") / environ.get("X")
        is_environ_get = (
            isinstance(func, ast.Attribute) and func.attr == "get" and _is_environ(func.value)
        )

        if is_getenv or is_environ_get:
            name = _const_str(node.args[0])
            if name:
                found.append((node.lineno, name))

    return found


def documented_vars(env_file: Path) -> set[str]:
    """Names declared in an env template. `# commented out` still counts as documented."""
    names: set[str] = set()
    try:
        text = env_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return names

    for raw in text.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if key.isidentifier() or (key and all(c.isalnum() or c == "_" for c in key)):
            names.add(key)
    return names


def find_env_template(explicit: str | None, root: Path) -> Path | None:
    if explicit:
        p = Path(explicit)
        return p if p.is_file() else None
    for name in ENV_TEMPLATES:
        candidate = root / name
        if candidate.is_file():
            return candidate
    return None


def collect_files(args: list[str], root: Path) -> list[Path]:
    if args:
        return [Path(a) for a in args if a.endswith(".py")]
    return sorted(
        p
        for p in root.rglob("*.py")
        if not SKIP_DIRS & set(p.parts) and "test" not in p.name.lower()
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if "--help" in argv or "-h" in argv:
        print(__doc__)
        return 0

    as_json = "--json" in argv
    if as_json:
        argv.remove("--json")
    # `--all` is accepted because review.md's checklist spells it that way; the
    # whole-tree scan is already the default, so it is a no-op rather than a lie.
    if "--all" in argv:
        argv.remove("--all")

    explicit_env = None
    if "--env" in argv:
        i = argv.index("--env")
        if i + 1 >= len(argv):
            print("Error: --env needs a file", file=sys.stderr)
            return 2
        explicit_env = argv[i + 1]
        del argv[i : i + 2]

    root = Path.cwd()
    env_file = find_env_template(explicit_env, root)

    if env_file is None:
        msg = f"DOCS SYNC SKIPPED (no {' / '.join(ENV_TEMPLATES)} in {root})"
        print(json.dumps({"status": "skipped", "reason": msg}) if as_json else msg)
        return 0

    documented = documented_vars(env_file)
    files = collect_files(argv, root)

    findings: list[Finding] = []
    for f in files:
        if not f.exists():
            continue
        for line, var in env_vars_in(f):
            if var in documented or var in AMBIENT:
                continue
            findings.append(Finding(file=str(f), line=line, var=var))

    # One line per (file, var); the same var read twice in a file is one problem.
    seen: set[tuple[str, str]] = set()
    unique: list[Finding] = []
    for f in findings:
        key = (f.file, f.var)
        if key not in seen:
            seen.add(key)
            unique.append(f)

    if as_json:
        print(
            json.dumps(
                {
                    "status": "failed" if unique else "passed",
                    "env_file": str(env_file),
                    "checked": len(files),
                    "undocumented": [f._asdict() for f in unique],
                },
                indent=2,
            )
        )
        return 1 if unique else 0

    if not unique:
        print(f"DOCS SYNC PASSED ({len(files)} file(s) against {env_file.name})")
        return 0

    print(f"DOCS SYNC FAILED — env vars read by the code but absent from {env_file.name}:")
    for f in unique:
        print(f"  - {f.file}:{f.line}: {f.var}")
    print(f"\nAdd them to {env_file.name} (a commented-out line counts as documented).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
