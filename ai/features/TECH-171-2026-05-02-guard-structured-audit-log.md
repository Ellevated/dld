---
id: TECH-171
type: TECH
status: queued
priority: P1
risk: R2
created: 2026-05-02
---

# TECH-171 — Guard structured audit log + daily digest

**Status:** queued
**Priority:** P1
**Risk:** R2

---

## Problem

Сейчас решения guard'а видны только в `callback-debug.log` среди всего шума (USAGE/skill detection/etc.). False-positive demote ловится не быстрее чем через ручной аудит репо одного из проектов. Нет дашборда / алёрта на "что-то странное случилось вчера".

---

## Goal

1. **Structured audit log** — JSONL файл `scripts/vps/callback-audit.jsonl`, одна строка на каждое решение `verify_status_sync`:
   ```json
   {
     "ts": "2026-05-02T10:30:00Z",
     "project_id": "awardybot",
     "spec_id": "FTR-897",
     "pueue_id": 1409,
     "target_in": "done",
     "target_out": "blocked",
     "reason": "no_implementation_commits",
     "allowed_count": 16,
     "code_loc": 0,
     "test_loc": 0,
     "code_commits": 0,
     "started_at": "2026-05-01T19:31:45Z",
     "duration_ms": 234
   }
   ```

   - Append-only, line-delimited JSON.
   - Ротация: log-rotate by date, держим 30 дней.
   - Path в `.env`: `CALLBACK_AUDIT_LOG=/home/dld/projects/dld/scripts/vps/callback-audit.jsonl`.

2. **Daily digest** (cron @ 09:00 MSK):
   - Скрипт `scripts/vps/audit_digest.py` читает последние 24h JSONL.
   - Группирует по project + verdict.
   - Шлёт Telegram message через event_writer с summary:
     ```
     📊 Callback digest 02.05 (last 24h)
     awardybot: 12 done ✓, 1 demote (FTR-897 → blocked, no_impl)
     dowry:     3 done ✓, 0 demote
     gipotenuza: 5 done ✓, 0 demote
     wb:        0 done ✓, 4 demote (ARCH-176a/b/c/d, no_impl)
     ```
   - При наличии demote — линк на JSONL для детального просмотра.

3. **Per-callback metric** в audit_log: `code_loc` / `test_loc` / `code_commits` (через numstat, как в моём аудите 02.05) — это будущий semantic signal, не только бинарный has_commits.

---

## Allowed Files

<!-- callback-allowlist v1 -->

- `scripts/vps/callback.py`
- `scripts/vps/audit_digest.py`
- `scripts/vps/event_writer.py`
- `scripts/vps/.env.example`
- `scripts/vps/setup-vps.sh`
- `tests/unit/test_audit_log_format.py`
- `tests/integration/test_audit_digest.py`

---

## Tasks

1. **Audit logger** в callback.py: helper `_write_audit(record: dict)` — append JSON line, atomic write.
2. **Numstat aggregation** в `_has_implementation_commits` — расширить return до `(bool, code_loc, test_loc, code_commits)` или separate helper.
3. **Hook в `verify_status_sync`** — собрать record, вызвать `_write_audit` ровно один раз per callback (после всех guards и решений).
4. **`audit_digest.py`**: argparse, чтение JSONL, группировка, Telegram отправка через event_writer.
5. **Cron entry**: добавить в `setup-vps.sh --phase3` строку `0 9 * * *` для digest.
6. **Logrotate config** для audit JSONL.
7. **Tests**: формат строк, агрегация digest'а на synthetic input.

---

## Eval Criteria

| ID | Type | Description |
|----|------|-------------|
| EC-1 | deterministic | Каждый `verify_status_sync` пишет ровно 1 JSON line |
| EC-2 | deterministic | Запись содержит все required keys (см. Goal) |
| EC-3 | integration | digest скрипт корректно агрегирует mocked JSONL за 24h |
| EC-4 | integration | Cron entry добавлен в crontab (idempotent) |
| EC-5 | integration | logrotate чистит файлы старше 30 дней |
