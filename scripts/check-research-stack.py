#!/usr/bin/env python3
"""Verify the research stack agents actually depend on, instead of trusting setup.

Agents degrade silently when a provider is missing or renamed — they do not error,
they just search worse. Two real failures this guards against, both found on
2026-07-26 only because someone probed by hand:

  * Context7 was installed with `scope: project` bound to one directory, so it
    was invisible from every other repo. `claude plugin list` still showed it.
  * Exa consolidated its API down to `web_search_exa` + `web_fetch_exa`. The repo
    still named eight retired tools in 55 files and referenced the live fetch tool
    exactly zero times. Every one of those calls failed as an unknown tool.

So this checks reachability AND drift: whether the tool names the prompts ask for
are the tool names the server serves.

Exit codes: 0 all good, 1 something is broken, 2 could not check (network etc).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

EXA_MCP_URL = "https://mcp.exa.ai/mcp"
REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPT_DIRS = (".claude", "template/.claude")

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = YELLOW = DIM = RESET = ""

problems: list[str] = []
warnings: list[str] = []


def ok(msg: str) -> None:
    print(f"  {GREEN}ok{RESET}    {msg}")


def bad(msg: str) -> None:
    print(f"  {RED}FAIL{RESET}  {msg}")
    problems.append(msg)


def warn(msg: str) -> None:
    print(f"  {YELLOW}warn{RESET}  {msg}")
    warnings.append(msg)


def run(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    """Run a command, returning (rc, stdout+stderr). Never raises.

    Decoding is pinned to UTF-8: the CLI emits ✔/✗ in its status output, and on a
    non-UTF-8 console (cp1251 on a Russian Windows) the default locale codec dies
    inside subprocess's reader thread, leaving output empty. That reads as
    "context7 not installed" when context7 is in fact connected.
    """
    try:
        p = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except subprocess.SubprocessError as e:
        return 1, str(e)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------------------
# 1. CLI
# ---------------------------------------------------------------------------
def check_cli() -> str | None:
    print("\nClaude Code CLI")
    cli = shutil.which("claude")
    if not cli:
        bad("`claude` is not on PATH — nothing else here can be checked")
        return None
    rc, out = run([cli, "--version"])
    version = re.search(r"\d+\.\d+\.\d+", out)
    ok(f"{cli} ({version.group(0) if version else out.strip()})")
    return cli


# ---------------------------------------------------------------------------
# 2. Context7 — installed, and visible from HERE
# ---------------------------------------------------------------------------
def check_context7(cli: str) -> None:
    print("\nContext7 (library documentation)")
    rc, out = run([cli, "plugin", "list"])
    if rc != 0:
        warn(f"`claude plugin list` failed: {out.strip()[:120]}")
        return
    if "context7" not in out.lower():
        bad(
            "context7 not installed — run: claude plugin install context7@claude-plugins-official --scope user"
        )
        return
    # A project-scoped plugin is bound to the directory it was installed from and
    # is silently absent everywhere else. That is exactly how it broke before.
    line = next((ln for ln in out.splitlines() if "context7" in ln.lower()), "")
    if re.search(r"\bproject\b", line, re.IGNORECASE):
        bad(
            "context7 is installed at PROJECT scope — invisible outside its install "
            "directory. Reinstall with --scope user"
        )
        return
    status = "connected" if re.search(r"connect", line, re.IGNORECASE) else "installed"
    ok(f"context7 {status}{DIM} — {line.strip()[:80]}{RESET}")


# ---------------------------------------------------------------------------
# 3. Exa — reachable, and serving the tools the prompts name
# ---------------------------------------------------------------------------
def _post(url: str, payload: dict, session: str | None) -> tuple[str, str | None]:
    """One JSON-RPC POST to a streamable-HTTP MCP endpoint."""
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **({"Mcp-Session-Id": session} if session else {}),
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace"), resp.headers.get("Mcp-Session-Id")


def _payload(body: str) -> dict | None:
    """Unwrap a response that may be plain JSON or an SSE frame."""
    body = body.strip()
    if body.startswith("{"):
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return None
    for line in body.splitlines():
        if line.startswith("data:"):
            try:
                return json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
    return None


def probe_exa() -> set[str] | None:
    """Ask the live Exa server which tools it actually serves."""
    print("\nExa (web search / fetch)")
    try:
        body, session = _post(
            EXA_MCP_URL,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "dld-stack-check", "version": "1"},
                },
            },
            None,
        )
        if _payload(body) is None:
            warn("Exa initialize returned an unparseable response")
            return None
        body, _ = _post(EXA_MCP_URL, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, session)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        warn(f"could not reach {EXA_MCP_URL}: {e}")
        return None

    data = _payload(body)
    tools = (data or {}).get("result", {}).get("tools") or []
    names = {t.get("name", "") for t in tools if t.get("name")}
    if not names:
        bad(f"{EXA_MCP_URL} served no tools")
        return None
    ok(f"serves {len(names)}: {', '.join(sorted(names))}")
    return names


# ---------------------------------------------------------------------------
# 4. Drift — do the prompts ask for tools that exist?
# ---------------------------------------------------------------------------
def check_drift(live: set[str]) -> None:
    """Every mcp__exa__* name in the prompt tree must be one the server serves."""
    print("\nPrompt/server agreement")
    referenced: dict[str, list[str]] = {}
    for rel in PROMPT_DIRS:
        root = REPO_ROOT / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in {".md", ".json"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for name in re.findall(r"mcp__exa__(\w+)", text):
                referenced.setdefault(name, []).append(
                    str(path.relative_to(REPO_ROOT)).replace("\\", "/")
                )

    if not referenced:
        warn("no mcp__exa__* references found in the prompt tree — is that intended?")
        return

    dead = {n: f for n, f in referenced.items() if n not in live}
    for name, files in sorted(dead.items()):
        shown = ", ".join(sorted(set(files))[:3])
        more = f" (+{len(set(files)) - 3} more)" if len(set(files)) > 3 else ""
        bad(f"prompts call `{name}`, which Exa no longer serves — {shown}{more}")

    for name in sorted(referenced):
        if name in live:
            ok(f"`{name}` referenced in {len(set(referenced[name]))} file(s), served")

    unused = live - set(referenced)
    if unused:
        warn(f"served but never referenced: {', '.join(sorted(unused))}")


# ---------------------------------------------------------------------------
# 5. MCP connection status
# ---------------------------------------------------------------------------
def check_mcp_health(cli: str) -> None:
    print("\nMCP servers as this directory sees them")
    rc, out = run([cli, "mcp", "list"], timeout=120)
    if rc != 0 and not out.strip():
        warn("`claude mcp list` produced nothing")
        return
    for line in out.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("checking"):
            continue
        if re.search(r"fail|error|✗", line, re.IGNORECASE):
            bad(line[:140])
        elif re.search(r"connect|✔|✓", line, re.IGNORECASE):
            ok(line[:140])


def main() -> int:
    print(f"{DIM}research stack check — {REPO_ROOT}{RESET}")
    cli = check_cli()
    if not cli:
        return 1

    check_context7(cli)
    live = probe_exa()
    if live:
        check_drift(live)
    check_mcp_health(cli)

    print()
    if problems:
        print(
            f"{RED}{len(problems)} problem(s){RESET} — agents are searching worse than you think:"
        )
        for p in problems:
            print(f"  - {p}")
        return 1
    if warnings:
        print(f"{YELLOW}{len(warnings)} warning(s){RESET}, nothing broken:")
        for w in warnings:
            print(f"  - {w}")
        return 0
    print(f"{GREEN}research stack is healthy{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
