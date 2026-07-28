"""
Module: lifecycle_const
Role: Leaf of the lifecycle module graph — every module-level constant plus the
      single process-wide write lock. Imported (never imports), so the Lock
      exists exactly once per process: Python caches the module in sys.modules.

Uses:
  - threading: Lock

Used by:
  - lifecycle.py, lifecycle_errors.py, lifecycle_cas.py, lifecycle_push.py,
    lifecycle_recovery.py
"""

import threading

LIFECYCLE_DIR = "ai/lifecycle"
MAX_CAS_RETRIES = 3
# How many fetch+rebase+retry rounds when a lifecycle push is rejected
# non-fast-forward (callback committed status on a stale local develop while the
# agent's code commits already landed on origin). Bounded — see _push_best_effort.
_PUSH_REBASE_RETRIES = 3

# ADR-025 (ARCH-193): identity enforcement — only known writer identities may
# call write_lifecycle / create_initial / build_initial_yaml.  Prevents
# accidental anonymous writes and makes audit trails meaningful.
# ADR-025 (ARCH-193): "autopilot" removed — signals via task_status JSON only;
# "spark" removed — zero direct callers (specs bootstrap via
# orchestrator.create_initial which writes by="orchestrator").
_ALLOWED_WRITERS = frozenset({"callback", "orchestrator", "operator", "qa", "audit", "migration"})

# ARCH-196 CR-7: surgical writer extension for spec-first ID claim.
# Spark may invoke create_initial() to claim an ID via CAS (Kafka pattern),
# but is NOT in _ALLOWED_WRITERS (which gates write_lifecycle status mutations).
# This preserves Rule 7 (ADR-025) — spark cannot promote/demote status,
# only create the initial queued row that callback then drives forward.
_ALLOWED_WRITERS_FOR_CREATE = frozenset({"spark"}) | _ALLOWED_WRITERS

# TECH-200: valid priority enum — matches render_backlog.PRIORITY_ORDER.
_VALID_PRIORITIES = frozenset({"p0", "p1", "p2"})

# In-process lock: serializes plumbing writes within one Python process.
# Eliminates intra-process CAS stampede (e.g. concurrent threads in callback).
# Multi-machine CAS is still guarded by git update-ref.
_write_lock = threading.Lock()
