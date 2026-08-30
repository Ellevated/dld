# scripts/vps/tests/test_doc_symbol_refs.py
"""Every `module.py::symbol` citation in docs/orchestrator/ must resolve.

The docs used to cite `file.py:LINE`. All eleven such citations in status-model.md were
wrong by the time anyone looked (ARCH-209): the TECH-210..216 and TECH-213 splits moved
the code, three pointed past the end of a file that had shrunk by a thousand lines, and
the rest landed on a closing paren or a blank. Nothing complained, because a line number
is not checkable — which is the same defect class as a rule copied into prose.

`module.py::symbol` is checkable, and this is the check. It survives a move within a file
and fails loudly when a symbol is renamed or moved between modules.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS = sorted((REPO_ROOT / "docs" / "orchestrator").glob("*.md"))

# `module.py::symbol` inside backticks
REF_RE = re.compile(r"`([\w./-]+\.py)::(\w+)`")
# The shape this test exists to keep out: `module.py:123` / `module.py:12-34`
LINE_REF_RE = re.compile(r"`[\w./-]+\.py:\d+(?:-\d+)?`")


def _citations():
    for doc in DOCS:
        text = doc.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in REF_RE.finditer(line):
                yield doc, lineno, m.group(1), m.group(2)


@pytest.mark.parametrize(
    "doc,lineno,module,symbol",
    [pytest.param(*c, id=f"{c[0].name}:{c[1]}:{c[2]}::{c[3]}") for c in _citations()],
)
def test_symbol_citation_resolves(doc, lineno, module, symbol):
    path = REPO_ROOT / "scripts" / "vps" / Path(module).name
    assert path.is_file(), f"{doc.name}:{lineno} cites {module}, which does not exist"

    source = path.read_text(encoding="utf-8", errors="replace")
    defined = re.search(
        rf"^(?:async def|def|class)\s+{re.escape(symbol)}\b|^{re.escape(symbol)}\s*[:=]",
        source,
        re.MULTILINE,
    )
    assert defined, f"{doc.name}:{lineno} cites {module}::{symbol}, not defined there"


def test_no_line_number_citations_remain():
    """Line numbers are the form that rots. Cite the symbol instead."""
    offenders = []
    for doc in DOCS:
        for lineno, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if LINE_REF_RE.search(line):
                offenders.append(f"{doc.name}:{lineno}  {line.strip()[:90]}")
    assert not offenders, "line-number citations found:\n" + "\n".join(offenders)
