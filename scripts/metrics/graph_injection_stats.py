#!/usr/bin/env python3
"""EXP-004 — did the injected blast radius reach the runs, and did it change them?

Reads Claude Code transcripts (``~/.claude/projects/*/*.jsonl``) and answers two
questions the experiment is built on:

1. **Delivery** — in what share of runs that edited code did ``graph-context.mjs``
   actually inject? A hook that silently fails to run looks exactly like a hook whose
   advice was ignored, and those two need different fixes.
2. **Effect** — of the runs that got a non-empty blast radius, in how many did the
   session go on to edit one of the files it was told about?

Counting is done over parsed ``tool_use`` blocks, never by grepping the raw line: the
tool *definitions* in a system prompt match any naive grep and turned "0 real calls"
into "52 sessions with graph calls" during the EXP-002 verdict.

Usage:
    python3 scripts/metrics/graph_injection_stats.py --since 2026-09-08
    python3 scripts/metrics/graph_injection_stats.py --since 2026-09-08 --json
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import time

CODE_EXT = {
    ".py",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".rs",
    ".rb",
    ".java",
    ".kt",
    ".php",
    ".cs",
    ".swift",
    ".sh",
    ".bash",
    ".sql",
    ".vue",
    ".svelte",
}
EDIT_TOOLS = {"Edit", "Write", "MultiEdit"}
GRAPH_TOOL_PREFIX = "mcp__codebase-memory__"

# The hook's own wording — see .claude/hooks/graph-context.mjs::buildMessage.
INJECTION_MARKER = "BLAST RADIUS — "
_PATH_RE = re.compile(r"[\w./-]+\.[A-Za-z]{1,6}")


def _blocks(record: dict) -> list:
    message = record.get("message") or {}
    content = message.get("content")
    return content if isinstance(content, list) else []


def _text_of(record: dict, _depth: int = 0) -> str:
    """Every string in the record, joined.

    A hook's additionalContext does not land in one predictable field: in a real
    transcript it arrives as ``{"hookName": "PreToolUse:Edit", ...}`` with the text
    inside a nested list, and it also shows up in the tool-result echo. Walking the
    record is what keeps this counter from silently reporting zero when the transcript
    shape shifts.
    """
    if _depth > 6:
        return ""
    parts = []
    if isinstance(record, str):
        return record
    values = (
        record.values() if isinstance(record, dict) else record if isinstance(record, list) else []
    )
    for value in values:
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, (dict, list)):
            parts.append(_text_of(value, _depth + 1))
    return "\n".join(p for p in parts if p)


def _files_from_injection(text: str) -> set[str]:
    """Paths named inside one injected blast radius block."""
    out: set[str] = set()
    for line in text.splitlines():
        if INJECTION_MARKER in line:
            continue  # the header names the edited file itself, not its blast radius
        if not any(k in line for k in ("Импортируют файл", "файлов:", "Тесты, дотягивающиеся")):
            continue
        for match in _PATH_RE.findall(line):
            if os.path.splitext(match)[1] in CODE_EXT:
                out.add(match)
    return out


def scan_session(path: str) -> dict | None:
    injected: set[str] = set()
    radius: set[str] = set()
    edited: set[str] = set()
    graph_calls = 0

    try:
        handle = open(path, encoding="utf-8", errors="ignore")
    except OSError:
        return None

    with handle:
        for line in handle:
            if INJECTION_MARKER not in line and "tool_use" not in line:
                continue
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue

            for block in _blocks(record):
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = str(block.get("name") or "")
                if name.startswith(GRAPH_TOOL_PREFIX):
                    graph_calls += 1
                elif name in EDIT_TOOLS:
                    file_path = str((block.get("input") or {}).get("file_path") or "")
                    if os.path.splitext(file_path)[1].lower() in CODE_EXT:
                        edited.add(file_path.replace("\\", "/"))

            text = _text_of(record)
            if INJECTION_MARKER in text:
                for chunk in text.split(INJECTION_MARKER)[1:]:
                    injected.add(chunk.splitlines()[0].split(" (")[0].strip())
                radius |= _files_from_injection(text)

    if not edited and not injected:
        return None

    acted = any(any(e.endswith(r) or r.endswith(e) for r in radius) for e in edited)
    return {
        "session": os.path.basename(path),
        "edited_code_files": len(edited),
        "injections": len(injected),
        "radius_files": len(radius),
        "acted_on_radius": bool(radius) and acted,
        "graph_tool_calls": graph_calls,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--since", required=True, help="YYYY-MM-DD — transcripts modified on or after"
    )
    parser.add_argument("--root", default=os.path.expanduser("~/.claude/projects"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cutoff = time.mktime(time.strptime(args.since, "%Y-%m-%d"))
    rows = []
    for path in glob.glob(os.path.join(args.root, "*", "*.jsonl")):
        try:
            if os.path.getmtime(path) < cutoff:
                continue
        except OSError:
            continue
        row = scan_session(path)
        if row:
            rows.append(row)

    edited_sessions = [r for r in rows if r["edited_code_files"]]
    injected_sessions = [r for r in edited_sessions if r["injections"]]
    with_radius = [r for r in rows if r["radius_files"]]
    acted = [r for r in with_radius if r["acted_on_radius"]]

    summary = {
        "since": args.since,
        "sessions_scanned": len(rows),
        "sessions_editing_code": len(edited_sessions),
        "sessions_with_injection": len(injected_sessions),
        "delivery_rate": round(len(injected_sessions) / len(edited_sessions), 3)
        if edited_sessions
        else None,
        "sessions_with_nonempty_radius": len(with_radius),
        "sessions_acting_on_radius": len(acted),
        "effect_rate": round(len(acted) / len(with_radius), 3) if with_radius else None,
        "graph_tool_calls": sum(r["graph_tool_calls"] for r in rows),
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    print(f"EXP-004 · транскрипты с {args.since}")
    print(f"  сессий с правками кода:        {summary['sessions_editing_code']}")
    print(
        f"  из них с инъекцией:            {summary['sessions_with_injection']}"
        f"  (delivery {summary['delivery_rate']}, порог 0.8)"
    )
    print(f"  сессий с непустым blast radius:{summary['sessions_with_nonempty_radius']}")
    print(
        f"  из них тронули файл из списка: {summary['sessions_acting_on_radius']}"
        f"  (effect {summary['effect_rate']}, порог 0.3)"
    )
    print(f"  добровольных вызовов графа:    {summary['graph_tool_calls']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
