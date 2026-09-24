# TECH-225 — advisory findings

| File:line | Finding | Suggested action |
|-----------|---------|------------------|
| scripts/vps/tests/test_runner_ratelimit.py:107 | повторная проверка resets_at_iso через datetime дублирует литерал строкой выше | убрать дубль при следующей правке файла |
| scripts/vps/callback_ratelimit.py:56 | `except Exception` вокруг count_requeues_since (как у соседей в callback_circuit) | сузить до sqlite3.Error |
