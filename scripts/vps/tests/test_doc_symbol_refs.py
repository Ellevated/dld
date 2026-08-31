# scripts/vps/tests/test_doc_symbol_refs.py
"""Every `module.py::symbol` citation must resolve — in docs *and* in the gate scripts.

The docs used to cite `file.py:LINE`. All eleven such citations in status-model.md were
wrong by the time anyone looked (ARCH-209): the TECH-210..216 and TECH-213 splits moved
the code, three pointed past the end of a file that had shrunk by a thousand lines, and
the rest landed on a closing paren or a blank. Nothing complained, because a line number
is not checkable — which is the same defect class as a rule copied into prose.

`module.py::symbol` is checkable, and this is the check. It survives a move within a file
and fails loudly when a symbol is renamed or moved between modules.

**Why `.claude/scripts/` is in scope.** The first version of this test globbed
`docs/orchestrator/` only — and the very next rot was found by hand, in the header of
`validate-allowlist.mjs`: it cited `callback.py:451-459`, past the end of a 371-line file,
naming a module the parser had left. A guard against citation rot that cannot see the
guard scripts is the same blind spot one level up. Both trees are globbed, because a fix
landing in one only is this repository's most common defect (`rules/template-sync.md`).

**Not in scope: prompts.** `.claude/agents/**` and `.claude/skills/**` are full of
`src/domains/billing/services.py:89` — illustrations of an output format, pointing at a
downstream project's code that does not exist here. Thirty-five of them, all legitimate.
The rule "cite the symbol" applies to text that points at *this* repository's code, which
is docs and scripts.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]

SOURCES = (
    sorted((REPO_ROOT / "docs" / "orchestrator").glob("*.md"))
    + sorted((REPO_ROOT / ".claude" / "scripts").glob("*.mjs"))
    + sorted((REPO_ROOT / "template" / ".claude" / "scripts").glob("*.mjs"))
)

# `module.py::symbol` inside backticks
REF_RE = re.compile(r"`([\w./-]+\.py)::(\w+)`")
# The shape this test exists to keep out: `module.py:123` / `module.py:12-34`.
# Backticks are optional on purpose — the rotted citation this test was widened for
# was a bare one, in a `//` comment: `// Sources: scripts/vps/callback.py:451-459`.
LINE_REF_RE = re.compile(r"`?\b[\w./-]+\.(?:py|mjs|sh):\d+(?:-\d+)?`?")


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _citations():
    for src in SOURCES:
        text = src.read_text(encoding="utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in REF_RE.finditer(line):
                yield src, lineno, m.group(1), m.group(2)


@pytest.mark.parametrize(
    "src,lineno,module,symbol",
    [pytest.param(*c, id=f"{_rel(c[0])}:{c[1]}:{c[2]}::{c[3]}") for c in _citations()],
)
def test_symbol_citation_resolves(src, lineno, module, symbol):
    path = REPO_ROOT / "scripts" / "vps" / Path(module).name
    assert path.is_file(), f"{_rel(src)}:{lineno} cites {module}, which does not exist"

    source = path.read_text(encoding="utf-8", errors="replace")
    defined = re.search(
        rf"^(?:async def|def|class)\s+{re.escape(symbol)}\b|^{re.escape(symbol)}\s*[:=]",
        source,
        re.MULTILINE,
    )
    assert defined, f"{_rel(src)}:{lineno} cites {module}::{symbol}, not defined there"


def test_citations_are_actually_found():
    """A glob that silently matches nothing would make every assertion above vacuous."""
    per_kind = {".md": 0, ".mjs": 0}
    for src, _, _, _ in _citations():
        per_kind[src.suffix] = per_kind.get(src.suffix, 0) + 1
    assert per_kind[".md"] > 0, "no symbol citations found in docs/orchestrator/"
    assert per_kind[".mjs"] > 0, (
        "no symbol citations found in .claude/scripts/ — either the glob broke or a "
        "script's source citation was dropped instead of being kept current"
    )


@pytest.mark.parametrize("src", SOURCES, ids=_rel)
def test_no_line_number_citations_remain(src):
    """Line numbers are the form that rots. Cite the symbol instead."""
    offenders = [
        f"{_rel(src)}:{lineno}  {line.strip()[:90]}"
        for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), 1)
        if LINE_REF_RE.search(line)
    ]
    assert not offenders, "line-number citations found:\n" + "\n".join(offenders)
