#!/usr/bin/env python3
"""
Module: callback
Role: Pueue completion callback — release slot, update phase, dispatch QA/Reflect, write audit log.

Uses:
  - callback_logs: extract_agent_output  (TECH-216)
  - callback_dispatch: resolve_spec_id, _step6_dispatch_qa_reflect  (TECH-216)
  - callback_scope: _commit_stats, _detect_out_of_scope_files, _emit_audit  (TECH-216)
  - callback_circuit: is_circuit_open, _trip_circuit, _record, _reset_circuit_cli  (TECH-216)
  - callback_sync: verify_status_sync  (TECH-216)
  - db: release_slot, finish_task, update_project_phase, record_decision, count_demotes_since
  - event_writer: notify, notify_circuit_event
  - lifecycle: read_lifecycle, write_lifecycle  (ADR-023 — sole status writer)
  - subprocess: pueue CLI fallback

Used by:
  - Pueue daemon (pueue.yml callback config)

CLI: python3 callback.py <pueue_id> '<group>' '<result>'
INVARIANT: Always exit 0. Every step in try/except.

TECH-171: _write_audit / _emit_audit append one JSONL line per verify_status_sync call.
Audit log path: $CALLBACK_AUDIT_LOG or scripts/vps/callback-audit.jsonl.
ARCH-186: verify_status_sync writes only to lifecycle.yaml (no markdown edits).
TECH-207: _step6_dispatch_qa_reflect — merge-confirmed QA dispatch fallback.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
import callback_circuit  # noqa: E402  — circuit-breaker (TECH-216)
import callback_dispatch  # noqa: E402  — QA/reflect dispatch (TECH-216)
import callback_logs  # noqa: E402  — agent output extraction (TECH-216)
import callback_scope  # noqa: E402  — allowlist telemetry + audit log (TECH-216)
import callback_sync  # noqa: E402  — the status gate + Step 6 (TECH-216)
import db  # noqa: E402
import event_writer  # noqa: E402
import gate_logic  # noqa: E402 — single source of gate logic (TECH-210)
import lifecycle  # noqa: E402  — atomic YAML writer (ADR-023)

log = logging.getLogger("callback")


def _load_env() -> None:
    """Load .env from SCRIPT_DIR. Manual parser."""
    env_file = SCRIPT_DIR / ".env"
    if not env_file.is_file():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip("'\""))


def _setup_logging() -> None:
    """Append-mode file + stderr logging."""
    log_file = SCRIPT_DIR / "callback-debug.log"
    handler = logging.FileHandler(str(log_file), mode="a")
    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    stderr_handler = logging.StreamHandler()
    stderr_handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.addHandler(stderr_handler)


def resolve_label(pueue_id: str) -> str:
    """Get task label. DB-first, pueue CLI fallback."""
    # Layer 1: DB (reliable — no socket dependency)
    try:
        row = db.get_task_by_pueue_id(int(pueue_id))
        if row:
            project_id = row["project_id"]
            task_label = row["task_label"]
            if task_label.startswith(f"{project_id}:"):
                label = task_label
            else:
                label = f"{project_id}:{task_label}"
            log.info("resolve_label from DB: %s", label)
            return label
    except Exception as exc:
        log.warning("resolve_label DB failed: %s", exc)

    # Layer 2: pueue CLI (fallback — may fail due to socket mismatch)
    try:
        result = subprocess.run(
            ["pueue", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        data = json.loads(result.stdout)
        task = data.get("tasks", {}).get(pueue_id, {})
        label = task.get("label", "unknown") or "unknown"
        if label != "unknown":
            log.info("resolve_label from pueue: %s", label)
        return label
    except Exception:
        return "unknown"


def parse_label(label: str) -> tuple:
    """Split label into (project_id, task_label)."""
    if ":" in label:
        project_id, _, task_label = label.partition(":")
        return project_id, task_label
    log.warning("label '%s' has no colon", label)
    return label, label


def map_result(result: str, raw_exit_code: str | None = None) -> tuple:
    """Map pueue result string to (status, exit_code).

    `result` is only ever "Success" / "Failed" / "Killed", so on its own it
    flattens every failure to 1. That is how 40% of runs over the week of
    2026-08-16 — all of them 90-minute TIMEOUT_SECONDS kills reporting 124 —
    were recorded in task_log as ordinary exit_code=1 failures, indistinguishable
    from a lint error. `{{ exit_code }}` in the pueue callback template carries
    the real code; it is optional so an un-migrated pueue.yml still works.
    """
    if "Success" in result:
        return "done", 0
    if raw_exit_code:
        try:
            return "failed", int(raw_exit_code)
        except ValueError:
            log.warning("un-parseable exit_code %r from pueue, recording 1", raw_exit_code)
    return "failed", 1


# --- TECH-216 re-exports: root tests/ and spec_operator.py reach these as
# `callback.<name>`; main() calls them by bare name so a monkeypatch still hits.
_find_log_file = callback_logs._find_log_file
_skill_from_pueue_command = callback_logs._skill_from_pueue_command
_parse_log_file = callback_logs._parse_log_file
extract_agent_output = callback_logs.extract_agent_output
resolve_spec_id = callback_dispatch.resolve_spec_id
is_already_queued = callback_dispatch.is_already_queued
_pueue_add = callback_dispatch._pueue_add
dispatch_qa = callback_dispatch.dispatch_qa
dispatch_reflect = callback_dispatch.dispatch_reflect


# --- TECH-166 / TECH-167: Implementation guard helpers ----------------------

# Дедупликация — это одна реализация, а не ноль имён. Алиас держит публичный шов
# для иммутабельного tests/regression/test_callback_spec_corpus.py:45 и прямых
# вызовов в tests/unit/; тело живёт в gate_logic (TECH-210, решение 2026-07-28).
_parse_allowed_files = gate_logic.parse_allowed_files


_get_started_at = callback_scope._get_started_at
_audit_log_path = callback_scope._audit_log_path
_write_audit = callback_scope._write_audit
_emit_audit = callback_scope._emit_audit
_is_test_path = callback_scope._is_test_path
_commit_stats = callback_scope._commit_stats
_detect_out_of_scope_files = callback_scope._detect_out_of_scope_files

CIRCUIT_THRESHOLD = callback_circuit.CIRCUIT_THRESHOLD
CIRCUIT_WINDOW_MIN = callback_circuit.CIRCUIT_WINDOW_MIN
CIRCUIT_HEAL_MIN = callback_circuit.CIRCUIT_HEAL_MIN
CIRCUIT_RESET_CLEAR_MIN = callback_circuit.CIRCUIT_RESET_CLEAR_MIN
CIRCUIT_PUEUE_GROUP = callback_circuit.CIRCUIT_PUEUE_GROUP
is_circuit_open = callback_circuit.is_circuit_open
_pueue_pause = callback_circuit._pueue_pause
_pueue_resume = callback_circuit._pueue_resume
_trip_circuit = callback_circuit._trip_circuit
_reset_circuit_cli = callback_circuit._reset_circuit_cli
_record = callback_circuit._record


def _render_and_commit_backlog(project_path: str, project_id: str) -> None:
    """Rule 5: inline render of ai/backlog.md after every lifecycle write.

    Best-effort. Lifecycle yaml is the SoT; backlog.md is a render. If render
    fails, lifecycle write still succeeds and the next callback retries the
    render. Logged but never raises.
    """
    try:
        import render_backlog

        content = render_backlog.render_backlog(project_path)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: render_backlog failed for %s: %s", project_id, exc)
        return
    try:
        ok = lifecycle.write_file_atomic(
            project_path,
            "ai/backlog.md",
            content,
            "render(backlog): auto-sync from lifecycle",
            by="callback",
        )
        if not ok:
            log.warning("RENDER: write_file_atomic returned False for %s", project_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("RENDER: write_file_atomic raised for %s: %s", project_id, exc)


verify_status_sync = callback_sync.verify_status_sync
_step6_dispatch_qa_reflect = callback_dispatch._step6_dispatch_qa_reflect


def write_event_for_skill(project_path: str, skill: str, status: str, task_label: str) -> None:
    """Write OpenClaw event for applicable skills."""
    if skill not in ("autopilot", "qa", "reflect", "spark"):
        return
    if status != "done" and not (status == "failed" and skill == "qa"):
        return

    artifact_rel = ""
    p = Path(project_path)
    if skill == "qa":
        qa_files = sorted(p.glob("ai/qa/[0-9]*-*.md"))
        if qa_files:
            artifact_rel = str(qa_files[-1].relative_to(p))
    elif skill == "reflect":
        reflect_files = sorted(p.glob("ai/reflect/findings-*.md"))
        if reflect_files:
            artifact_rel = str(reflect_files[-1].relative_to(p))

    event_writer.notify(
        project_path,
        skill,
        status,
        f"{skill} {status} for {task_label}",
        artifact_rel,
    )


def main() -> None:  # pragma: no cover
    """Main callback entry point. ALWAYS exits 0.

    Two modes:
      • Pueue callback: argv = [pueue_id, group, result]  — fired by daemon.
      • Operator CLI:   argv = ['--reset-circuit']        — manual reset.
    """
    try:
        _load_env()
        _setup_logging()

        # TECH-169: operator CLI mode
        if len(sys.argv) > 1 and sys.argv[1] == "--reset-circuit":
            _reset_circuit_cli()
            return

        pueue_id = sys.argv[1] if len(sys.argv) > 1 else "0"
        group = sys.argv[2] if len(sys.argv) > 2 else "unknown"
        result = sys.argv[3] if len(sys.argv) > 3 else "unknown"
        # Optional: pueue's {{ exit_code }}. Absent on hosts whose pueue.yml
        # predates the template change in setup-vps.sh.
        raw_exit_code = sys.argv[4] if len(sys.argv) > 4 else None

        log.info(
            "callback: id=%s group=%s result=%s exit_code=%s",
            pueue_id,
            group,
            result,
            raw_exit_code if raw_exit_code else "-",
        )

        # Skip night-reviewer group
        if group == "night-reviewer":
            log.info("skip night-reviewer callback")
            sys.exit(0)

        label = resolve_label(pueue_id)
        project_id, task_label = parse_label(label)
        if raw_exit_code is None and "Success" not in result:
            # pueue passed no {{ exit_code }} — the runner's log has the real one
            runner_code = callback_logs.runner_exit_code(pueue_id, project_id)
            if runner_code is not None:
                raw_exit_code = str(runner_code)
        status, exit_code = map_result(result, raw_exit_code)

        log.info("parsed: project=%s task=%s status=%s", project_id, task_label, status)

        # Step 1: Release slot (ALWAYS)
        try:
            db.release_slot(pueue_id)
        except Exception as exc:
            log.warning("release_slot failed: %s", exc)

        # Step 2: Finish task
        try:
            db.finish_task(pueue_id, status, exit_code)
        except Exception as exc:
            log.warning("finish_task failed: %s", exc)

        # Step 3: Update phase
        try:
            if task_label.startswith(("qa-", "reflect-")):
                new_phase = "idle"  # non-blocking tail tasks
            elif status == "done":
                if task_label.startswith("inbox-"):
                    new_phase = "idle"
                else:
                    new_phase = "qa_pending"
            else:
                new_phase = "failed"

            current_task = task_label if new_phase == "qa_pending" else None
            db.update_project_phase(project_id, new_phase, current_task)
            log.info("phase updated: %s -> %s", project_id, new_phase)
        except Exception as exc:
            log.warning("update_phase failed: %s", exc)

        # Step 4: Extract agent output
        skill, preview, task_status = "", "", ""
        try:
            skill, preview, task_status = extract_agent_output(pueue_id, project_id)
            log.info(
                "agent output: skill=%s preview_len=%d task_status=%s",
                skill,
                len(preview),
                task_status,
            )
        except Exception as exc:
            log.warning("extract_agent_output failed: %s", exc)

        # Step 5: Write OpenClaw event
        try:
            project_path = ""
            state = db.get_project_state(project_id)
            if state:
                project_path = state.get("path", "")
            if project_path:
                write_event_for_skill(project_path, skill, status, task_label)
        except Exception as exc:
            log.warning("write_event failed: %s", exc)

        # Step 6: Post-autopilot tail — dispatch QA + Reflect
        # Extracted to _step6_dispatch_qa_reflect (TECH-207)
        try:
            _step6_dispatch_qa_reflect(
                skill=skill,
                status=status,
                task_status=task_status,
                project_id=project_id,
                task_label=task_label,
                preview=preview,
            )
        except Exception as exc:
            log.warning("step6 dispatch failed: %s", exc)

        # Step 7: Verify spec + backlog status sync
        if skill == "autopilot" and status in ("done", "failed"):
            try:
                if not project_path:
                    state = db.get_project_state(project_id)
                    project_path = state.get("path", "") if state else ""
                if project_path:
                    sid = resolve_spec_id(task_label, preview, project_path)
                    if sid:
                        if status == "done":
                            # task_status=blocked or needs_review → demote to blocked
                            if task_status in ("blocked", "needs_review"):
                                target = "blocked"
                                log.info(
                                    "STATUS: task_status=%s → target=blocked (overrides pueue Success)",
                                    task_status,
                                )
                            else:
                                # task_status="" (missing) or "complete" → honour pueue Success
                                target = "done"
                        else:
                            target = "blocked"
                        verify_status_sync(
                            project_path,
                            sid,
                            target,
                            pueue_id=int(pueue_id) if pueue_id else None,
                            autopilot_signaled=task_status in ("blocked", "needs_review"),
                        )
            except Exception as exc:
                log.warning("status_sync check failed: %s", exc)

    except Exception:
        log.exception("callback fatal error")
    finally:
        sys.exit(0)


if __name__ == "__main__":
    main()
