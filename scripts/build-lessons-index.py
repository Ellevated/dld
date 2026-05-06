#!/usr/bin/env python3
"""
Build lessons index from project archive.

Reads BUG tasks from ai/archive/ (or ai/features/ for closed BUGs),
classifies by root_cause_class, writes structured lessons to ai/lessons/.

Usage:
    python scripts/build-lessons-index.py [--dry-run] [--domain DOMAIN] [--min-severity LEVEL]

Output:
    ai/lessons/<domain>/L-NNN.md   — individual lesson files
    ai/lessons/index.jsonl          — machine-readable index (append-only)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path


ROOT_CAUSE_TAXONOMY = {
    "money-precision": {
        "keywords": [
            "kopecks",
            "rub",
            "ruble",
            "float",
            "decimal",
            "amount",
            "price",
            "balance",
            "kopeck",
            "money",
            "currency",
        ],
        "severity": "critical",
    },
    "race-condition": {
        "keywords": [
            "concurrent",
            "race",
            "lock",
            "advisory",
            "simultaneous",
            "deadlock",
            "locking",
            "atomic",
            "transaction",
            "isolation",
        ],
        "severity": "critical",
    },
    "ssot-violation": {
        "keywords": [
            "ssot",
            "duplicate",
            "sync",
            "diverge",
            "inconsistent",
            "mismatch",
            "two sources",
            "multiple sources",
        ],
        "severity": "high",
    },
    "migration-drift": {
        "keywords": [
            "migration",
            "migrate",
            "schema",
            "column",
            "table",
            "alembic",
            "alter",
            "add column",
            "drop column",
        ],
        "severity": "critical",
    },
    "atomicity": {
        "keywords": [
            "partial",
            "rollback",
            "mid-flight",
            "halfway",
            "incomplete",
            "transaction",
            "multi-step",
        ],
        "severity": "high",
    },
    "idempotency": {
        "keywords": [
            "idempotent",
            "duplicate",
            "double",
            "twice",
            "replay",
            "retry",
            "webhook",
            "re-run",
        ],
        "severity": "high",
    },
    "boolean-trap": {
        "keywords": [
            "is_active",
            "is_deleted",
            "bool",
            "boolean",
            "flag",
            "status",
            "state",
            "nullable bool",
        ],
        "severity": "medium",
    },
    "fsm-deadlock": {
        "keywords": [
            "state machine",
            "fsm",
            "stuck",
            "transition",
            "slot",
            "pickup",
            "lifecycle",
            "status flow",
        ],
        "severity": "high",
    },
    "cross-layer-import": {
        "keywords": ["import", "circular", "layer", "domain", "api import", "shared", "direction"],
        "severity": "medium",
    },
    "pydantic-coercion": {
        "keywords": [
            "pydantic",
            "coerce",
            "coercion",
            "validation",
            "type cast",
            "string to int",
            "none to",
        ],
        "severity": "medium",
    },
    "case-mismatch": {
        "keywords": ["snake_case", "camelcase", "camel", "field name", "naming", "case"],
        "severity": "medium",
    },
    "null-safety": {
        "keywords": [
            "none",
            "null",
            "nullable",
            "missing",
            "undefined",
            "optional",
            "not found",
            "keyerror",
            "attributeerror",
        ],
        "severity": "medium",
    },
}

DOMAIN_PATTERNS = {
    "billing": ["billing", "balance", "payment", "invoice", "charge", "refund", "money", "kopeck"],
    "campaigns": ["campaign", "slot", "proof", "screenshot", "pickup", "substep", "buyer_task"],
    "buyer": ["buyer", "ugc", "creator", "identity", "onboarding", "merge"],
    "seller": ["seller", "brand", "advertiser", "offer"],
    "llm": ["llm", "gpt", "claude", "openai", "vision", "prompt", "tool_call", "agent"],
    "db": ["migration", "schema", "database", "sql", "postgres", "sqlite", "index", "table"],
    "security": ["auth", "token", "permission", "secret", "key", "csrf", "injection"],
    "api": ["api", "webhook", "endpoint", "handler", "route", "http"],
    "storage": ["file", "upload", "s3", "bucket", "media", "image", "storage"],
}

SEVERITY_ORDER = {"critical": 3, "high": 2, "medium": 1}


def detect_domain(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for domain, keywords in DOMAIN_PATTERNS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[domain] = score
    if not scores:
        return "general"
    return max(scores, key=scores.get)


def classify_root_cause(text: str) -> tuple[str, str]:
    """Returns (root_cause_class, severity)."""
    text_lower = text.lower()
    scores = {}
    for cls, meta in ROOT_CAUSE_TAXONOMY.items():
        score = sum(1 for kw in meta["keywords"] if kw in text_lower)
        if score > 0:
            scores[cls] = (score, meta["severity"])

    if not scores:
        return "general", "medium"

    best = max(scores, key=lambda c: (scores[c][0], SEVERITY_ORDER[scores[c][1]]))
    return best, scores[best][1]


def extract_prevention_rule(text: str, root_cause: str) -> str:
    """Try to extract a one-line prevention rule from task body."""
    # Look for Resolution / Fix / How to prevent sections
    for pattern in [
        r"(?:resolution|fix|solution|prevent)[:\s]+(.+?)(?:\n|$)",
        r"(?:use|always|never|must|should)[^\n]+(?:\n|$)",
    ]:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            rule = m.group(0 if "use|always" in pattern else 1).strip()
            if len(rule) > 10:
                return rule[:200]

    defaults = {
        "money-precision": "Использовать int (kopecks), никогда float/Decimal для денег",
        "race-condition": "Использовать advisory lock или transaction isolation перед concurrent writes",
        "ssot-violation": "Один источник правды — не хранить одно и то же в двух местах",
        "migration-drift": "Миграция и код меняются в одном PR, CI применяет миграцию",
        "atomicity": "Все шаги — в одной транзакции или с компенсирующей операцией",
        "idempotency": "Проверять на duplicate перед записью, использовать upsert",
        "fsm-deadlock": "Описать все легальные переходы FSM явно, запретить остальные",
        "general": "Добавить тест на граничный случай",
    }
    return defaults.get(root_cause, defaults["general"])


def parse_task_file(path: Path) -> dict | None:
    """Parse a task spec file (BUG- prefix expected)."""
    text = path.read_text(encoding="utf-8")
    name = path.stem  # e.g. BUG-350-2026-02-15-kopecks-migration

    # Only process BUG tasks
    if not re.match(r"BUG-\d+", name, re.IGNORECASE):
        return None

    task_id = re.match(r"(BUG-\d+)", name, re.IGNORECASE).group(1).upper()

    # Extract title from first H1 or filename
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else name

    domain = detect_domain(text)
    root_cause, severity = classify_root_cause(text)
    prevention = extract_prevention_rule(text, root_cause)

    keywords = list(
        {
            kw
            for kw, meta in ROOT_CAUSE_TAXONOMY.items()
            if root_cause == kw
            for kw in meta["keywords"]
            if kw in text.lower()
        }
    )[:8]
    if not keywords:
        keywords = root_cause.split("-")

    return {
        "task_id": task_id,
        "title": title[:100],
        "domain": domain,
        "root_cause_class": root_cause,
        "severity": severity,
        "prevention_rule": prevention,
        "keywords": keywords,
    }


def next_lesson_id(lessons_dir: Path) -> str:
    existing = [f.stem for f in lessons_dir.glob("L-*.md") if re.match(r"L-\d+", f.stem)]
    nums = [int(re.search(r"\d+", s).group()) for s in existing if re.search(r"\d+", s)]
    n = max(nums, default=0) + 1
    return f"L-{n:03d}"


def write_lesson(lessons_dir: Path, lesson_id: str, data: dict, dry_run: bool) -> Path:
    domain_dir = lessons_dir / data["domain"]
    lesson_file = domain_dir / f"{lesson_id}.md"

    content = f"""---
id: {lesson_id}
domain: {data["domain"]}
root_cause_class: {data["root_cause_class"]}
severity: {data["severity"]}
created: {__import__("datetime").date.today()}
occurrence_count: 1
related: [{data["task_id"]}]
---

# {data["root_cause_class"]}: {data["title"][:60]}

## Prevention Rule
{data["prevention_rule"]}

## Context
Extracted from {data["task_id"]}.

## Keywords
{", ".join(data["keywords"])}
"""
    if not dry_run:
        domain_dir.mkdir(parents=True, exist_ok=True)
        lesson_file.write_text(content, encoding="utf-8")

    return lesson_file


def update_index(index_file: Path, entry: dict, dry_run: bool):
    line = json.dumps(entry, ensure_ascii=False)
    if not dry_run:
        with index_file.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def main():
    parser = argparse.ArgumentParser(description="Build ai/lessons/ from archive")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no writes")
    parser.add_argument("--domain", help="Process only this domain")
    parser.add_argument("--min-severity", choices=["critical", "high", "medium"], default="medium")
    parser.add_argument("--archive-dir", default="ai/archive", help="Source directory")
    parser.add_argument("--lessons-dir", default="ai/lessons", help="Output directory")
    args = parser.parse_args()

    archive_dir = Path(args.archive_dir)
    lessons_dir = Path(args.lessons_dir)
    index_file = lessons_dir / "index.jsonl"

    if not archive_dir.exists():
        print(f"Archive directory not found: {archive_dir}", file=sys.stderr)
        print("Create ai/archive/ with BUG task spec files first.")
        sys.exit(0)  # Not an error — project may not have archive yet

    min_sev = SEVERITY_ORDER[args.min_severity]
    processed = skipped = written = 0

    for path in sorted(archive_dir.glob("*.md")):
        data = parse_task_file(path)
        if data is None:
            skipped += 1
            continue

        processed += 1
        if SEVERITY_ORDER[data["severity"]] < min_sev:
            skipped += 1
            continue

        if args.domain and data["domain"] != args.domain:
            skipped += 1
            continue

        domain_dir = lessons_dir / data["domain"]
        lesson_id = next_lesson_id(domain_dir)

        lesson_path = write_lesson(lessons_dir, lesson_id, data, args.dry_run)
        index_entry = {
            "id": lesson_id,
            "domain": data["domain"],
            "root_cause_class": data["root_cause_class"],
            "prevention_rule": data["prevention_rule"],
            "keywords": data["keywords"],
            "severity": data["severity"],
            "related": [data["task_id"]],
            "created": str(__import__("datetime").date.today()),
            "occurrence_count": 1,
        }
        update_index(index_file, index_entry, args.dry_run)

        status = "DRY-RUN" if args.dry_run else "WRITTEN"
        print(
            f"[{status}] {lesson_id} ({data['domain']}/{data['root_cause_class']}) ← {data['task_id']}"
        )
        written += 1

    print(
        f"\nDone: {written} lessons {'would be ' if args.dry_run else ''}written, {skipped} skipped, {processed} processed"
    )


if __name__ == "__main__":
    main()
