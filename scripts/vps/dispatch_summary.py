#!/usr/bin/env python3
"""
Module: dispatch_summary
Role: one machine-built briefing for the LLM dispatcher (Hermes) — every fact it
      needs to decide what to run next, and nothing else.

Why this exists. Until 2026-09-07 the decision "which spec runs now" lived in
code: a chain of gates in `orchestrator.scan_queued`, each of which answered
`False` for the WHOLE project when it refused. Two of them stopped the fleet that
day — a red-CI gate on a fleet whose develop is red by default, and a spec with
no `## Allowed Files` that held five ready specs behind it — and both refusals
were INFO lines nobody reads. The decision moves to a model; this script is its
input, and `dispatch_one.py` is its only way to act.

Deliberately NOT a gate: it never filters a spec out. A spec that looks
undispatchable is reported WITH the reason, because "fix the allowlist and run
it" is a decision the dispatcher can make and a gate cannot.

Uses: json, os, re, subprocess, sys, pathlib, db, lifecycle
Used by: skills/dispatcher (via ~/ops/dispatcher.sh), operators on the VPS
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import db  # noqa: E402
import lifecycle  # noqa: E402

ALLOWLIST_HEADING = re.compile(r"^## Allowed Files\s*$", re.MULTILINE)
PROVIDERS = ("claude", "codex", "gemini")
# A real spec run, not a smoke task: "<project>:<PREFIX-NNN>" with an optional
# skill prefix ("awardybot:qa-FTR-1506").
SPEC_LABEL = re.compile(r"^[\w.-]+:(?:[a-z]+-)?(?:BUG|FTR|TECH|ARCH|GROWTH)-\d+$")
MAX_SPECS_PER_PROJECT = 12


def _run(cmd: list[str], cwd: str | None = None, timeout: int = 30) -> str:
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _spec_body(project_dir: str, spec_id: str) -> Path | None:
    hits = sorted(Path(project_dir, "ai", "features").glob(f"{spec_id}-*.md"))
    return hits[0] if hits else None


def _spec_problem(project_dir: str, spec_id: str) -> str | None:
    """What would make this spec fail on arrival — stated, never used to filter."""
    body = _spec_body(project_dir, spec_id)
    if body is None:
        return "no spec body in ai/features/ (ID claimed, Spark never wrote it)"
    try:
        text = body.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"spec body unreadable: {exc}"
    if not ALLOWLIST_HEADING.search(text):
        return "no `## Allowed Files` section — the callback guard blocks it on arrival"
    return None


def _depends_on(project_dir: str, spec_id: str) -> list[str]:
    row = lifecycle.read_lifecycle(project_dir, spec_id) or {}
    deps = row.get("depends_on") or []
    unmet = []
    for dep in deps:
        drow = lifecycle.read_lifecycle(project_dir, dep) or {}
        if drow.get("status") != "done":
            unmet.append(f"{dep}={drow.get('status', 'missing')}")
    return unmet


def _running(project_dir: str) -> list[str]:
    """Worktrees that hold live work — the ground truth, not a status field."""
    out = _run(["git", "worktree", "list", "--porcelain"], cwd=project_dir)
    trees = [ln.split(" ", 1)[1] for ln in out.splitlines() if ln.startswith("worktree ")]
    return [Path(t).name for t in trees[1:]]


def _pueue_active() -> list[dict]:
    raw = _run(["pueue", "status", "--json"], timeout=20)
    if not raw:
        return []
    try:
        tasks = json.loads(raw).get("tasks", {})
    except json.JSONDecodeError:
        return []
    live = []
    for tid, t in tasks.items():
        status = t.get("status")
        name = list(status.keys())[0] if isinstance(status, dict) else status
        if name in {"Running", "Queued", "Paused"}:
            live.append({"pueue_id": int(tid), "state": name, "label": t.get("label") or ""})
    return sorted(live, key=lambda x: x["pueue_id"])


def _provider_health() -> dict:
    """Last verdict per provider — a free slot on a broken runner is not capacity.

    Measured on the dispatcher's first live pass (2026-09-07): it correctly saw
    claude=0, spent the free codex and gemini slots, and both runs died in
    seconds — codex on a CLI too old for its pinned model, gemini on a missing
    API key. Neither had run in weeks, so nothing had noticed. A slot count alone
    invites that mistake every pass; the last outcome per provider prevents it.
    """
    raw = _run(["pueue", "status", "--json"], timeout=20)
    health = {p: {"last": "unproven", "note": "no finished run on record"} for p in PROVIDERS}
    if not raw:
        return health
    try:
        tasks = json.loads(raw).get("tasks", {})
    except json.JSONDecodeError:
        return health
    for provider in PROVIDERS:
        group = f"{provider}-runner"
        # Only real spec runs count. A green `argv-check` in the codex group said
        # "last run ok" while every actual autopilot run on that provider was dying
        # on an outdated CLI — a smoke task is not evidence the runner can work.
        done = [
            t
            for t in tasks.values()
            if t.get("group") == group
            and SPEC_LABEL.match(t.get("label") or "")
            and not isinstance(t.get("status"), str)
        ]
        finished = []
        for t in done:
            status = t.get("status") or {}
            key = list(status.keys())[0] if isinstance(status, dict) else str(status)
            if key != "Done":
                continue
            result = (status.get("Done") or {}).get("result")
            ok = result == "Success" if isinstance(result, str) else "Success" in (result or {})
            finished.append((t.get("start") or "", ok, t.get("label") or ""))
        if not finished:
            continue
        start, ok, label = sorted(finished)[-1]
        health[provider] = {
            "last": "ok" if ok else "FAILED",
            "note": f"{label} at {start[:16]}",
        }
    return health


def _recent_verdicts(limit: int = 8) -> list[dict]:
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT project_id, task_label, skill, status, started_at, finished_at, exit_code "
            "FROM task_log ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def build(project_rows: list[dict]) -> dict:
    projects = []
    for row in project_rows:
        pid, pdir = row["project_id"], row["path"]
        if not os.path.isdir(pdir):
            projects.append({"project": pid, "error": f"path missing: {pdir}"})
            continue
        specs = []
        for cand in lifecycle.list_by_status(pdir, {"queued", "resumed"})[:MAX_SPECS_PER_PROJECT]:
            sid = cand["spec_id"]
            specs.append(
                {
                    "spec_id": sid,
                    "status": cand.get("status", "queued"),
                    "priority": cand.get("priority"),
                    "problem": _spec_problem(pdir, sid),
                    "unmet_deps": _depends_on(pdir, sid),
                }
            )
        projects.append(
            {
                "project": pid,
                "path": pdir,
                "enabled": bool(row.get("enabled", 1)),
                "waiting": specs,
                "live_worktrees": _running(pdir),
                "head": _run(["git", "log", "--oneline", "-1"], cwd=pdir),
            }
        )
    return {
        "slots_free": {p: db.get_available_slots(p) for p in PROVIDERS},
        "provider_health": _provider_health(),
        "pueue_active": _pueue_active(),
        "projects": projects,
        "recent": _recent_verdicts(),
    }


def render(summary: dict) -> str:
    """Markdown for a prompt: short, and every line is a fact the model can act on."""
    out: list[str] = ["# Dispatch briefing", ""]
    free = summary["slots_free"]
    health = summary.get("provider_health", {})
    for prov in PROVIDERS:
        h = health.get(prov, {})
        out.append(
            f"- **{prov}**: {free.get(prov, 0)} free slot(s) · "
            f"last run {h.get('last', '?')} ({h.get('note', '')})"
        )
    live = summary["pueue_active"]
    out.append(f"**Running now ({len(live)}):** " + (", ".join(t["label"] for t in live) or "—"))
    out.append("")
    for p in summary["projects"]:
        if p.get("error"):
            out.append(f"## {p['project']} — {p['error']}")
            continue
        waiting = p["waiting"]
        out.append(f"## {p['project']} ({len(waiting)} waiting)")
        if p["live_worktrees"]:
            out.append(f"- live worktrees: {', '.join(p['live_worktrees'])}")
        for s in waiting:
            bits = [f"`{s['spec_id']}`", s["status"]]
            if s.get("priority"):
                bits.append(str(s["priority"]))
            if s["unmet_deps"]:
                bits.append("waits on " + ", ".join(s["unmet_deps"]))
            if s["problem"]:
                bits.append("PROBLEM: " + s["problem"])
            out.append("- " + " · ".join(bits))
        if not waiting:
            out.append("- nothing waiting")
        out.append("")
    out.append("## Last runs")
    for r in summary["recent"]:
        out.append(
            f"- {r['task_label']} · {r['skill']} · {r['status']} · "
            f"{r['started_at']} → {r.get('finished_at') or 'running'}"
        )
    return "\n".join(out)


def main(argv: list[str]) -> int:
    as_json = "--json" in argv
    rows = [p for p in db.get_all_projects() if p.get("enabled", 1)]
    summary = build(rows)
    print(json.dumps(summary, ensure_ascii=False, indent=2) if as_json else render(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
