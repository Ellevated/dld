# Feature: [ARCH-176a] Multi-tenant Foundation — Pydantic schema + project registry + DB seed

**Status:** done | **Priority:** P1 | **Date:** 2026-04-26 | **Parent:** [ARCH-176](ARCH-176-2026-04-26-multi-tenant-refactor.md)

## Why

Часть 1/4 разбивки ARCH-176 (autopilot отказался выполнять единый 18-task spec). Это foundation — всё остальное зависит от этой спеки.

Создаёт три вещи без которых остальные части не смогут стартовать:
1. **Pydantic schema** для `projects/{id}/config.yaml` — основа валидации (используется в 176b response_pipeline и 176c onboard CLI + scheduler gate)
2. **`get_active_projects()`** — DB-first registry проектов (используется в 176b cli.py/handlers.py и 176c onboard CLI)
3. **Migration 044** — сидинг grisha/domabout/sabsabi в `projects` таблицу (devil блокер #2; разблокирует sabsabi в CLI)

**Не ломает ничего** — только новые файлы + сидинг существующих 3 проектов.

---

## Context

- Master spec: `ai/features/ARCH-176-2026-04-26-multi-tenant-refactor.md`
- Devil's advocate finding: scheduler сейчас работает через filesystem fallback (`infra/scheduler/main.py:102-110`), DB пустая
- ADR-015: `shared/*` lazy-importing `infra.db.connection.get_connection()` — accepted pattern

---

## Scope

**In scope:**
- `shared/project_config.py` — Pydantic `BaseModel` schema (Optional everywhere, `extra="allow"`)
- `shared/projects.py` — `get_active_projects()` DB primary + filesystem fallback + module cache + `invalidate_cache()`
- `infra/db/migrations/044_seed_existing_projects.sql` — INSERT OR IGNORE для grisha/domabout/sabsabi
- `infra/db/seed.py` — параметризованный `seed_project(conn, id, name, ...)`

**Out of scope (другие подспеки):**
- Token convention в client.py → ARCH-176b
- cli.py / response_pipeline.py / handlers.py / bot.py → ARCH-176b
- Scheduler validation gate, onboard CLI → ARCH-176c
- Документация → ARCH-176d

---

## Allowed Files

### New files (create)
- `shared/projects.py`
- `shared/project_config.py`
- `infra/db/migrations/044_seed_existing_projects.sql`
- `tests/test_project_config_schema.py`
- `tests/test_get_active_projects.py`

### Existing files (modify)
- `infra/db/seed.py` — параметризовать `seed_project()` (~20 LOC)

**Forbidden:** любые другие файлы (cli.py, response_pipeline.py, client.py — это 176b; onboard, scheduler — это 176c).

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Priority |
|----|----------|-------|----------|----------|
| EC-7 | Pydantic accepts existing yamls | Загрузка grisha/domabout/sabsabi config.yaml через `ProjectConfig.load()` | Валидация проходит, нет ValidationError | P0 |
| EC-8 | Pydantic rejects malformed | yaml без обязательного `name`/`project` | ValidationError с конкретным указанием поля | P0 |
| EC-12 | get_active_projects DB primary | DB содержит kirill (is_active=1) | Возвращает kirill в списке | P0 |
| EC-13 | get_active_projects fs fallback | DB пустая, filesystem содержит `projects/kirill/config.yaml` | Возвращает kirill через filesystem fallback | P0 |
| EC-14 | get_active_projects cache invalidation | После INSERT в projects + invalidate_cache() | Возвращает обновлённый список | P1 |
| EC-16 | Migration 044 seed idempotent | Миграция 044 запускается на DB с existing projects rows | Не дублирует, INSERT OR IGNORE | P0 |

### Side-Effect Assertions

| ID | Affected Component | Regression Check | Priority |
|----|-------------------|------------------|----------|
| SA-1 | grisha/domabout/sabsabi pipeline | Нет регрессий — это additive change | P0 |
| SA-3 | Scheduler `load_all_projects` | Сохраняет filesystem fallback на cold start (без DB) | P0 |

---

## Tasks (from planner DAG)

### Task 1.1 — Pydantic schema for `projects/*/config.yaml`
- **File:** Create `shared/project_config.py`
- **Symbols:** `class ProjectConfig(BaseModel)`:
  - Required: `project: str`, `name: str`
  - Optional: `wb_seller_id: Optional[int] = None` (kirill yaml currently lacks it — Optional + WARN on load), `brand`, `token_expires`, `seller_phone`, `seller_name`
  - Containers: `schedule`, `skus`, `thresholds`, `features` — `Field(default_factory=dict)`
  - `model_config = ConfigDict(extra="allow")`
  - `@classmethod ProjectConfig.load(path: Path) -> "ProjectConfig"` (uses `shared.yaml_loader.load_yaml` + `model_validate`)

### Task 1.2 — Tests for ProjectConfig schema
- **File:** Create `tests/test_project_config_schema.py`
- **Tests:**
  - `test_load_grisha_yaml_valid()` — assert no ValidationError
  - `test_load_domabout_yaml_valid()` — same
  - `test_load_kirill_yaml_valid()` — kirill (с missing wb_seller_id) — Optional, не должен падать
  - `test_invalid_yaml_raises_validation_error()` — yaml dict без `project`/`name` → ValidationError упоминает поле
  - `test_extra_field_allowed()` — yaml с unknown key `xyz: 123` грузится OK

### Task 1.3 — `shared/projects.py` with cache
- **File:** Create `shared/projects.py`
- **Symbols:**
  - `_cache: list[str] | None = None` (module-level)
  - `get_active_projects() -> list[str]` — DB primary (lazy `from infra.db.connection import get_connection`, `SELECT id FROM projects WHERE is_active=1`); on `sqlite3.OperationalError` (table missing) OR empty → fallback to `Path("projects").iterdir()` matching `child/config.yaml`; cache; ADR-015 (lazy infra import)
  - `invalidate_cache() -> None` — `_cache = None`

### Task 1.4 — Tests for `get_active_projects`
- **File:** Create `tests/test_get_active_projects.py`
- **Tests (use `tmp_path` + monkeypatch DB_PATH and CWD):**
  - `test_db_primary_returns_active_rows()` — seed kirill is_active=1, assert in result
  - `test_db_inactive_excluded()` — is_active=0 → not returned
  - `test_fs_fallback_when_table_missing()` — fresh tmp DB (без миграций), `projects/foo/config.yaml` → возвращает `["foo"]`
  - `test_fs_fallback_when_db_empty()` — DB exists но без rows → fs scan
  - `test_cache_invalidation()` — call → INSERT new row → still cached; `invalidate_cache()` → new value

### Task 3.1 — Migration 044 seeding existing projects
- **File:** Create `infra/db/migrations/044_seed_existing_projects.sql`
- **Content:**
  ```sql
  -- Migration 044: Seed grisha/domabout/sabsabi rows so get_active_projects() & scheduler don't depend on filesystem fallback.
  -- Idempotent: INSERT OR IGNORE.
  INSERT OR IGNORE INTO projects (id, name, wb_seller_id, brand, is_active) VALUES ('grisha', 'Grisha Official', 250023805, 'Зорина2990', 1);
  INSERT OR IGNORE INTO projects (id, name, wb_seller_id, brand, is_active) VALUES ('domabout', 'DomAbout', 1181523, 'DomAbout', 1);
  INSERT OR IGNORE INTO projects (id, name, is_active) VALUES ('sabsabi', 'Sabsabi', 1);
  INSERT OR IGNORE INTO project_config (project_id) VALUES ('grisha');
  INSERT OR IGNORE INTO project_config (project_id) VALUES ('domabout');
  INSERT OR IGNORE INTO project_config (project_id) VALUES ('sabsabi');
  ```

### Task 3.2 — Parameterize `seed_project()` function
- **File:** Modify `infra/db/seed.py`
- **Changes:**
  - Add `def seed_project(conn, id_, name, wb_seller_id=None, brand=None, is_active=1) -> None` — runs INSERT OR IGNORE for `projects` + `project_config`
  - Refactor existing `seed_projects()` to call `seed_project(conn, "grisha", ...)`, `seed_project(conn, "domabout", ...)`, `seed_project(conn, "sabsabi", "Sabsabi")`
  - Keep `if __name__ == "__main__"` entry point
- **Validate manually:** `python infra/db/migrate.py && sqlite3 state/wb.db "SELECT id,name,is_active FROM projects"` shows 3 rows

### Execution order
```
1.1 → 1.2          (schema first, then schema tests)
1.3 → 1.4          (registry then registry tests)
3.1 → 3.2          (migration sql then seed.py refactor)
```
1.x and 3.x — independent, can interleave.

---

## Related

- **Parent:** ARCH-176 (master spec, status=split)
- **Blocks:** ARCH-176b (token convention + pipeline cleanup needs `get_active_projects`), ARCH-176c (onboard CLI needs `ProjectConfig`)
- **Depends on:** —
