#!/usr/bin/env python3
"""
Build lessons index from project archive — keyword-only, no LLM.

For intelligent classification use: /seed-lessons skill in Claude Code.
This script is for CI/automation where no LLM is available.

Usage:
    python3 scripts/build-lessons-index.py [--dry-run] [--domain DOMAIN]
    python3 scripts/build-lessons-index.py --dry-run --archive-dir ai/archive

Output:
    ai/lessons/<domain>/L-NNN.md   — individual lesson files
    ai/lessons/index.jsonl          — machine-readable index (append-only)
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_CAUSE_TAXONOMY = {
    "money-precision": [
        "kopecks",
        "kopeck",
        "rub",
        "ruble",
        "float",
        "decimal",
        "amount",
        "price",
        "balance",
        "money",
    ],
    "race-condition": [
        "concurrent",
        "race",
        "lock",
        "advisory",
        "simultaneous",
        "locking",
        "isolation",
    ],
    "ssot-violation": ["ssot", "diverge", "inconsistent", "two sources", "multiple sources"],
    "migration-drift": ["migration", "migrate", "alembic", "alter", "add column", "drop column"],
    "atomicity": ["partial", "rollback", "mid-flight", "halfway", "incomplete", "multi-step"],
    "idempotency": ["idempotent", "double", "twice", "replay", "webhook", "re-run"],
    "boolean-trap": ["is_active", "is_deleted", "nullable bool", "boolean trap"],
    "fsm-deadlock": ["state machine", "fsm", "stuck", "status flow", "lifecycle"],
    "cross-layer-import": ["circular import", "import direction", "cross-layer"],
    "pydantic-coercion": ["pydantic", "coerce", "coercion", "type cast"],
    "case-mismatch": ["snake_case", "camelcase", "field name mismatch"],
    "null-safety": ["keyerror", "attributeerror", "nonetype", "none check"],
}

DOMAIN_PATTERNS = {
    "billing": ["billing", "balance", "payment", "invoice", "charge", "refund", "kopeck"],
    "campaigns": ["campaign", "slot", "proof", "screenshot", "pickup", "substep"],
    "buyer": ["buyer", "ugc", "creator", "identity", "onboarding"],
    "seller": ["seller", "brand", "advertiser", "offer"],
    "llm": ["llm", "gpt", "claude", "openai", "vision", "prompt", "tool_call"],
    "db": ["migration", "schema", "database", "sql", "postgres", "sqlite"],
    "security": ["auth", "token", "permission", "secret", "csrf", "injection"],
    "api": ["webhook", "endpoint", "handler", "route"],
    "storage": ["upload", "s3", "bucket", "media", "storage"],
}

SEVERITY = {
    "money-precision": "critical",
    "race-condition": "critical",
    "migration-drift": "critical",
    "atomicity": "high",
    "idempotency": "high",
    "ssot-violation": "high",
    "fsm-deadlock": "high",
}

DEFAULTS = {
    "money-precision": "Использовать int (kopecks), никогда float/Decimal для денег",
    "race-condition": "Использовать advisory lock перед concurrent writes",
    "ssot-violation": "Один источник правды — не хранить одно и то же в двух местах",
    "migration-drift": "Миграция и код меняются в одном PR",
    "atomicity": "Все шаги — в одной транзакции",
    "idempotency": "Проверять на duplicate перед записью, использовать upsert",
    "fsm-deadlock": "Описать все легальные переходы FSM явно",
}


def best_match(text: str, patterns: dict) -> tuple[str, int]:
    t = text.lower()
    scores = {k: sum(1 for kw in v if kw in t) for k, v in patterns.items()}
    best = max(scores, key=scores.get, default="general")
    return (best if scores.get(best, 0) > 0 else "general"), scores.get(best, 0)


def next_id(domain_dir: Path) -> str:
    nums = [
        int(m.group(1)) for f in domain_dir.glob("L-*.md") if (m := re.search(r"L-(\d+)", f.stem))
    ]
    return f"L-{max(nums, default=0) + 1:03d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--domain")
    ap.add_argument("--archive-dir", default="ai/archive")
    ap.add_argument("--lessons-dir", default="ai/lessons")
    args = ap.parse_args()

    archive = Path(args.archive_dir)
    lessons = Path(args.lessons_dir)

    if not archive.exists():
        print("Archive not found. Run /seed-lessons in Claude Code for intelligent seeding.")
        sys.exit(0)

    written = skipped = 0
    for path in sorted(archive.glob("*.md")):
        if not re.match(r"BUG-\d+", path.stem, re.IGNORECASE):
            skipped += 1
            continue

        task_id = re.match(r"(BUG-\d+)", path.stem, re.IGNORECASE).group(1).upper()
        text = path.read_text(encoding="utf-8")
        title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        title = (title_m.group(1).strip() if title_m else path.stem)[:80]

        domain, _ = best_match(text, DOMAIN_PATTERNS)
        root_cause, _ = best_match(text, ROOT_CAUSE_TAXONOMY)
        severity = SEVERITY.get(root_cause, "medium")

        if args.domain and domain != args.domain:
            skipped += 1
            continue

        rule_m = re.search(
            r"(?:resolution|fix|solution|правило)[:\s]+(.+?)(?:\n|$)", text, re.IGNORECASE
        )
        prevention = (
            rule_m.group(1).strip()[:200]
            if rule_m and len(rule_m.group(1)) > 10
            else DEFAULTS.get(root_cause, "Добавить тест на граничный случай")
        )

        keywords = [kw for kw in ROOT_CAUSE_TAXONOMY.get(root_cause, []) if kw in text.lower()][:6]

        domain_dir = lessons / domain
        lesson_id = next_id(domain_dir)

        content = f"""---
id: {lesson_id}
domain: {domain}
root_cause_class: {root_cause}
severity: {severity}
created: {__import__("datetime").date.today()}
occurrence_count: 1
related: [{task_id}]
---

# {root_cause}: {title}

## Prevention Rule
{prevention}

## Context
Extracted from {task_id}.

## Keywords
{", ".join(keywords) or root_cause}
"""
        entry = {
            "id": lesson_id,
            "domain": domain,
            "root_cause_class": root_cause,
            "prevention_rule": prevention,
            "keywords": keywords,
            "severity": severity,
            "related": [task_id],
            "created": str(__import__("datetime").date.today()),
            "occurrence_count": 1,
        }

        if not args.dry_run:
            domain_dir.mkdir(parents=True, exist_ok=True)
            (domain_dir / f"{lesson_id}.md").write_text(content, encoding="utf-8")
            with (lessons / "index.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        tag = "DRY" if args.dry_run else "  OK"
        print(f"[{tag}] {lesson_id} {domain}/{root_cause} ← {task_id}")
        written += 1

    print(f"\n{written} lessons {'(dry-run) ' if args.dry_run else ''}| {skipped} skipped")
    if written == 0:
        print("Tip: use /seed-lessons in Claude Code for intelligent classification.")


if __name__ == "__main__":
    main()
