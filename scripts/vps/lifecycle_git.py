"""
Module: lifecycle_git
Role: Git primitives — byte-level subprocess I/O, current branch lookup,
      HEAD yaml read, and lifecycle yaml content builder.

Uses:
  - subprocess: run (git plumbing commands)
  - yaml: safe_load, safe_dump
  - datetime: now, timezone
  - lifecycle_const: LIFECYCLE_DIR

Used by:
  - lifecycle.py: facade re-exports run_git, delegates all internal calls
  - lifecycle_cas.py, lifecycle_push.py, lifecycle_recovery.py (Task 3/4)
  - salvage.py: run_git() — public alias of _run
"""

import subprocess
from datetime import datetime, timezone
from typing import Optional

import yaml
from lifecycle_const import LIFECYCLE_DIR


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(
    cmd: list,
    *,
    cwd: str,
    env: Optional[dict] = None,
    input_text: Optional[str] = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    """Run git with byte-level I/O and explicit UTF-8. Never `text=True`.

    `text=True` breaks this module on Windows in two separate ways:

    1. stdin is wrapped in a TextIOWrapper with universal newlines, so every "\\n"
       becomes "\\r\\n". The lifecycle yaml is fed to `git hash-object --stdin`, so
       the blob lands in git with CRLF despite `.gitattributes` (*.yaml eol=lf).
       `ai/lifecycle/` is then permanently dirty, and `assert_clean_lifecycle_tree`
       aborts orchestrator startup — for every project, not just the affected one.
    2. stdout is decoded with the locale encoding (cp1251 on a Russian Windows),
       so any Cyrillic spec title raises UnicodeDecodeError and `render_backlog`
       silently skips the yaml as malformed.

    Output keeps the newline normalization `text=True` used to provide, so the
    ~40 existing call sites are unaffected.
    """
    raw_input = input_text.encode("utf-8") if input_text is not None else None
    p = subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        input=raw_input,
        capture_output=True,
        check=False,
        timeout=timeout,
    )

    def _decode(b: bytes) -> str:
        return b.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")

    return subprocess.CompletedProcess(p.args, p.returncode, _decode(p.stdout), _decode(p.stderr))


# Public alias. Other VPS modules that shell out to git must not re-derive the
# byte-level I/O rules above — re-deriving them is how the CRLF/cp1251 bug got
# written twice. Import this, not `_run`.
run_git = _run


def _current_branch(repo_dir: str) -> str:
    r = _run(["git", "symbolic-ref", "--short", "HEAD"], cwd=repo_dir)
    if r.returncode == 0:
        return r.stdout.strip()
    return _run(["git", "rev-parse", "HEAD"], cwd=repo_dir).stdout.strip()


def _read_yaml_from_head(repo_dir: str, spec_id: str) -> Optional[dict]:
    r = _run(["git", "show", f"HEAD:{LIFECYCLE_DIR}/{spec_id}.yaml"], cwd=repo_dir)
    if r.returncode != 0:
        return None
    try:
        return yaml.safe_load(r.stdout)
    except yaml.YAMLError:
        return None


def _build_yaml_content(
    spec_id: str,
    status: str,
    *,
    existing: Optional[dict],
    reason: Optional[str] = None,
    by: str,
    pueue_id: Optional[int] = None,
    allowed_files_hash: Optional[str] = None,
    priority: Optional[str] = None,
    kind: Optional[str] = None,
    depends_on: Optional[list] = None,
) -> str:
    now = _now_iso()
    if existing is None:
        data: dict = {
            "spec_id": spec_id,
            "status": status,
            "priority": priority or "p1",
            "kind": kind or "tech",
            "blocked_reason": None,
            # Обе отметки пустые НАМЕРЕННО и здесь остаются. Единственный
            # вызов с status="done" — bootstrap архивной секции backlog'а:
            # такая спека закончилась когда-то давно, а не «сейчас», и её
            # сигнатура (done ∧ transitions=[] ∧ pueue_id=None ∧
            # finished_at=None) — то, по чему lifecycle_recovery отличает
            # bootstrap-артефакт от настоящей работы. Проставить finished_at
            # здесь значит и соврать про время, и закрыть путь восстановления.
            "started_at": None,
            "finished_at": None,
            "allowed_files_hash": allowed_files_hash,
            "updated_at": now,
            "updated_by": by,
            "version": 1,
            "pueue_id": pueue_id,
            "transitions": [],
            "depends_on": [str(d) for d in (depends_on or [])],
        }
        return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)

    data = dict(existing)
    old_status = data.get("status", "unknown")
    data.update(
        {
            "status": status,
            "updated_at": now,
            "updated_by": by,
            "version": int(data.get("version", 0)) + 1,
        }
    )
    if reason is not None:
        data["blocked_reason"] = reason
    if allowed_files_hash is not None:
        data["allowed_files_hash"] = allowed_files_hash
    if pueue_id is not None:
        data["pueue_id"] = pueue_id
    if depends_on is not None:
        data["depends_on"] = [str(d) for d in depends_on]
    else:
        data.setdefault("depends_on", [])
    # ЛЮБОЙ вход в in_progress — начало работы. Прежний список
    # `("queued", "resumed")` терял реальные случаи: спека, поднятая из
    # `blocked` прямо в `in_progress`, уходила в done со `started_at: null`
    # (замер по флоту 31.08.2026: 75 done-спек из 183 за две недели без
    # started_at). Длительность прогона нельзя измерить по состоянию, из
    # которого в него вошли.
    if status == "in_progress" and not data.get("started_at"):
        data["started_at"] = now
    transitions = list(data.get("transitions") or [])
    if status == "done":
        if not data.get("started_at"):
            # Досыпать из истории, а не из воздуха: время первого перехода в
            # in_progress — настоящее наблюдение. Нет такого перехода — поле
            # остаётся пустым, это честнее выдуманной отметки.
            first_run = next(
                (t.get("at") for t in transitions if t.get("to") == "in_progress"), None
            )
            if first_run:
                data["started_at"] = first_run
        if not data.get("finished_at"):
            data["finished_at"] = now
    transitions.append(
        {"from": old_status, "to": status, "at": now, "by": by, "pueue_id": pueue_id}
    )
    data["transitions"] = transitions
    return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True)
