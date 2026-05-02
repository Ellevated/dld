# Feature: [ARCH-176d] Multi-tenant Documentation — dependencies + building-blocks + audit checklist

**Status:** queued | **Priority:** P2 | **Date:** 2026-04-26 | **Parent:** [ARCH-176](ARCH-176-2026-04-26-multi-tenant-refactor.md)

## Why

Часть 4/4 разбивки ARCH-176. Документация финального состояния кода после 176a/b/c.

3 файла:
1. `.claude/rules/dependencies.md` — добавить новые модули `shared.projects`, `shared.project_config`, `tools.onboard_project`; обновить заметку про `infra.wb_api.client` (token convention)
2. `docs/building-blocks.md` — добавить новые кирпичики (`get_active_projects`, `ProjectConfig.load`, onboard CLI 3-step recipe)
3. `docs/multi-tenancy-audit.md` — заменить 10-step чеклист на 3-step онбординг, отметить resolved blockers

---

## Context

- Master spec: `ai/features/ARCH-176-2026-04-26-multi-tenant-refactor.md`
- `dependencies.md` — модульный CLAUDE.md, читается каждой сессией
- `building-blocks.md` — реестр reusable кирпичиков (см. project rule "Не изобретай заново")

---

## Scope

**In scope:**
- `.claude/rules/dependencies.md` — 3 новых раздела + заметка про client.py
- `docs/building-blocks.md` — 3 новых section'а
- `docs/multi-tenancy-audit.md` — обновить чеклист, отметить resolved blockers

**Out of scope:** код (всё уже сделано в 176a/b/c).

---

## Allowed Files

### Existing files (modify)
- `.claude/rules/dependencies.md`
- `docs/building-blocks.md`
- `docs/multi-tenancy-audit.md`

**Forbidden:** любой код.

---

## Eval Criteria

| ID | Scenario | Input | Expected | Priority |
|----|----------|-------|----------|----------|
| EC-D1 | dependencies.md mentions new modules | grep `shared.projects` | Found с указанием → / ←  цепочек | P0 |
| EC-D2 | building-blocks.md has onboard recipe | grep `onboard_project` | Found с 3-step bash example | P0 |
| EC-D3 | audit checklist is 3-step | docs/multi-tenancy-audit.md | Содержит обновлённый 3-шаговый онбординг | P0 |
| EC-D4 | Resolved blockers marked | docs/multi-tenancy-audit.md | PROJECT_*_TOKENS, _VALID_PROJECTS, _PROJECT_CONFIGS, PROJECT_CHAT_IDS отмечены как resolved + ссылка на ARCH-176a/b | P1 |

---

## Tasks (from planner DAG)

### Task 7.1 — Update `.claude/rules/dependencies.md`
- **File:** Modify `.claude/rules/dependencies.md`
- **Add 3 entries:**
  - **Under `## shared layer`:**
    - `### shared.projects` — `→ infra.db.connection (lazy, ADR-015), pathlib`; `← infra.scheduler.main, infra.telegram.handlers, domains.reviews.cli, tools.onboard_project`; Public API `get_active_projects()`, `invalidate_cache()`
    - `### shared.project_config` — `→ pydantic, shared.yaml_loader`; `← infra.scheduler.main, domains.reviews.response_pipeline, tools.onboard_project`; Public API `ProjectConfig`, `ProjectConfig.load(path)`
  - **Under `## tools layer`:**
    - `### tools.onboard_project` — `→ infra.db.connection, shared.project_config, shared.projects, argparse, pathlib`
- **Update existing entry:**
  - `### infra.wb_api.client` — добавить заметку: "Tokens resolved via convention `WB_API_TOKEN_{ID_UPPER}` (grisha legacy `WB_API_TOKEN` accepted as exception) — no PROJECT_*_TOKENS dicts (ARCH-176b)"

### Task 7.2 — Update `docs/building-blocks.md`
- **File:** Modify `docs/building-blocks.md`
- **Add 3 sections:**
  - "Active projects (multi-tenant)":
    ```python
    from shared.projects import get_active_projects, invalidate_cache
    projects = get_active_projects()  # → ['grisha', 'domabout', 'sabsabi', ...]
    # DB primary, filesystem fallback. Cached. Call invalidate_cache() after onboard.
    ```
  - "Project config schema":
    ```python
    from shared.project_config import ProjectConfig
    cfg = ProjectConfig.load(Path("projects/kirill/config.yaml"))
    # → ProjectConfig(project='kirill', name='Kirill Shop', wb_seller_id=..., ...)
    # Optional everywhere; extra="allow"; raises pydantic.ValidationError on missing required.
    ```
  - "Onboard new project (3-step)":
    ```bash
    echo "WB_API_TOKEN_KIRILL=..." >> .env
    echo "TELEGRAM_CHAT_ID_KIRILL=..." >> .env
    python -m tools.onboard_project --id kirill --name "Kirill Shop" --wb-seller-id 123456
    # DB INSERT/UPDATE + atomic yaml + skeleton state files. Idempotent.
    ```

### Task 7.3 — Update `docs/multi-tenancy-audit.md`
- **File:** Modify `docs/multi-tenancy-audit.md`
- **Changes:**
  - Replace 10-step checklist с new 3-step онбординг recipe (echo .env x2 + onboard CLI)
  - Mark **resolved blockers** (с ссылкой на спеки):
    - `PROJECT_TOKENS` / `PROJECT_FEEDBACKS_TOKENS` / `PROJECT_BUYER_CHAT_TOKENS` / `PROJECT_RETURNS_TOKENS` removed → ARCH-176b
    - `_VALID_PROJECTS` removed → ARCH-176b
    - `_PROJECT_CONFIGS` removed → ARCH-176b
    - `_infer_project_from_chat` теперь dynamic → ARCH-176b
    - `PROJECT_CHAT_IDS` dead code removed → ARCH-176b
    - DB seed для существующих проектов → migration 044 (ARCH-176a)
    - Pydantic schema → `shared.project_config.ProjectConfig` (ARCH-176a)
    - Scheduler validation gate → ARCH-176c
  - Add link to migration 044 и ARCH-176a/b/c специации
  - Note **remaining backlog**:
    - TOKEN_REGISTRY data-driven cleanup (`infra/wb_api/token_manager.py`)
    - `tools/sabsabi_*.py` one-shot scripts (hardcoded "sabsabi" — known pattern)
    - Knowledge base bootstrap (cards + seller_notes interview) — отдельный FTR

### Execution order
```
7.1 → 7.2 → 7.3   (any order — independent files)
```

---

## Related

- **Parent:** ARCH-176 (master spec, status=split)
- **Depends on:** ARCH-176a + ARCH-176b + ARCH-176c (документация отражает финальное состояние кода)
- **Blocks:** —
