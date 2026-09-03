#!/usr/bin/env python3
"""Find .claude/rules files that load into every session.

A rules file is loaded conditionally only if its frontmatter declares `paths:`.
Without that key it loads into EVERY session, forever — and having *other*
frontmatter keys does not help, because only `paths:` is a loading condition.
That is what made this invisible: the files looked configured.

Measured 2026-07-26 across nine projects: 56 unmarked files, ~87k tokens burned
per session before the first user word. AwardyBot alone carried 37k for 25 days.
Nobody noticed, because the cost shows up as "context filled up fast", never as
an error.

A file that genuinely must always load declares `always_on: true` instead — the
intent then lives in the file rather than in this script's exception list.

**Mass matters as much as the header.** Measured 2026-09-03 in AwardyBot: one `Read` of
a file under `src/domains/seller/` pulled +67K tokens into the context with
`.claude/rules/` present and +7K without it — the scoped rules whose globs matched.
An autopilot spec dispatches 12-14 cold agents and each touches many paths, so nearly
every scoped rule loads into nearly every agent; 57K words of rules became 2.0M
cache-write tokens in a single run. `paths:` decides *when* a rule loads, not *whether*
its cost is paid. So this script also reports the total scoped mass and fails above
`--max-words=N` (default 25 000): a project over the ceiling moves reference sections
(change histories, ADR tables, runbooks) out of `.claude/rules/` into `docs/`, leaving
a pointer — see dld `docs/2026-09-02-autopilot-medlenno-i-dorogo.md`.

Exit codes: 0 clean, 1 undeclared always-on files found or scoped mass over the ceiling.
"""

from __future__ import annotations

import sys
from pathlib import Path

CHARS_PER_TOKEN = 4  # rough, but the ranking is what matters


def frontmatter_keys(text: str) -> set[str]:
    """Top-level keys of a leading `---` block. Empty set if there is none."""
    if not text.startswith("---"):
        return set()
    end = text.find("\n---", 3)
    if end == -1:
        return set()
    return {
        line.split(":", 1)[0].strip()
        for line in text[3:end].splitlines()
        if ":" in line and not line.startswith((" ", "\t", "-", "#"))
    }


DEFAULT_MAX_WORDS = 25_000


def main() -> int:
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    max_words = DEFAULT_MAX_WORDS
    for a in sys.argv[1:]:
        if a.startswith("--max-words="):
            max_words = int(a.split("=", 1)[1])
    root = Path(positional[0] if positional else ".").resolve()
    rules = root / ".claude" / "rules"
    if not rules.is_dir():
        print(f"no {rules} — nothing to check")
        return 0

    scoped: list[tuple[str, int]] = []
    declared: list[tuple[str, int]] = []
    leaking: list[tuple[str, int]] = []
    scoped_words: list[tuple[str, int]] = []

    for f in sorted(rules.rglob("*.md")):
        text = f.read_text(encoding="utf-8", errors="replace")
        rel = str(f.relative_to(rules)).replace("\\", "/")
        cost = len(text) // CHARS_PER_TOKEN
        keys = frontmatter_keys(text)
        if "paths" in keys:
            scoped.append((rel, cost))
            scoped_words.append((rel, len(text.split())))
        elif "always_on" in keys:
            declared.append((rel, cost))
        else:
            leaking.append((rel, cost))

    print(f"rules under {rules}\n")
    if scoped:
        print(f"  scoped by paths:      {len(scoped)}")
    for rel, cost in sorted(declared, key=lambda x: -x[1]):
        print(f"  always-on (declared)  {rel}  ~{cost:,} tok")

    mass = sum(w for _, w in scoped_words)
    over = mass > max_words
    if scoped_words:
        print(f"  scoped mass:          {mass:,} words (ceiling {max_words:,})")
        for rel, w in sorted(scoped_words, key=lambda x: -x[1])[:5]:
            print(f"    {rel:<40} {w:>7,} words")
    if over:
        print(
            f"\n  scoped rules weigh {mass:,} words — over the {max_words:,} ceiling. A cold\n"
            "  agent pays for every matching rule on its first touch of a path (~4 tokens per\n"
            "  word in Russian) and autopilot dispatches 12-14 of them per spec. Move reference\n"
            "  sections (change history, ADR tables, runbooks) to docs/ and leave a pointer."
        )

    if not leaking:
        print("\nno undeclared always-on rules")
        return 1 if over else 0

    total = sum(c for _, c in leaking)
    print(f"\n  {len(leaking)} file(s) load into EVERY session, ~{total:,} tokens each time:\n")
    for rel, cost in sorted(leaking, key=lambda x: -x[1]):
        print(f"    {rel:<40} ~{cost:>7,} tok")
    print(
        "\nGive each one a `paths:` header scoped to the code it describes, or\n"
        "`always_on: true` if it genuinely belongs in every session.\n"
        "Derive globs from the real layout — a rule that never loads is a silent\n"
        "loss of guidance, which is worse than the tokens."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
