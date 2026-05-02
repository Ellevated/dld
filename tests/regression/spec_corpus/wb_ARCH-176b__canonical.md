# Feature: [ARCH-176b] Multi-tenant Critical Fixes — Token convention + Pipeline cleanup

**Status:** done | **Priority:** P1 | **Date:** 2026-04-26 | **Parent:** [ARCH-176](ARCH-176-2026-04-26-multi-tenant-refactor.md)

## Why

Часть 2/4 разбивки ARCH-176. Это **самая критичная** часть — фактически разблокирует подключение kirill.

Решает 3 hardcoded-блокера:
1. **`infra/wb_api/client.py:55-70`** — 4 dict'а `PROJECT_TOKENS`, `PROJECT_FEEDBACKS_TOKENS`, `PROJECT_BUYER_CHAT_TOKENS`, `PROJECT_RETURNS_TOKENS`. Любой `create_project_client("kirill")` упадёт с `UnknownProjectTokenError` до запуска пайплайна. Devil блокер #1.
2. **`domains/reviews/cli.py:22`** — `_VALID_PROJECTS = ("grisha", "domabout")` — sabsabi уже сломан в CLI
3. **`domains/reviews/response_pipeline.py:31-34`** — `_PROJECT_CONFIGS` с hardcoded "Grisha Official"/"DomAbout" — попадает в текст ответов покупателям

После этой спеки `create_project_client("kirill")` с `WB_API_TOKEN_KIRILL` в .env работает, CLI принимает любой seeded проект, response prompt читает имя из yaml.

---

## Context

- Master spec: `ai/features/ARCH-176-2026-04-26-multi-tenant-refactor.md`
- Memory: `feedback-no-silent-token-fallback.md` — multi-tenant резолверы fail-fast, никогда не подставлять токен другого магазина
- Memory: `project-sabsabi-wb-rate-limit.md` — sabsabi POST endpoint в permanent lockout, тестовые правки не должны затрагивать его pipeline
- Grisha legacy: `WB_API_TOKEN` без суффикса остаётся как explicit exception (token_manager.py:80-81)

---

## Scope

**In scope:**
- `infra/wb_api/client.py` — заменить 4 PROJECT_*_TOKENS dict'а на конвенцию `WB_API_TOKEN_{ID_UPPER}` (+ grisha legacy исключение)
- `domains/reviews/cli.py` — заменить `_VALID_PROJECTS` tuple на `get_active_projects()` (из 176a)
- `domains/reviews/response_pipeline.py` — заменить `_PROJECT_CONFIGS` dict на priority chain (`seller_name` > `name` > `project_id.title()`) через `ProjectConfig.load()` (из 176a)
- `infra/telegram/handlers.py:327` — заменить hardcoded `for project in ("grisha", "domabout")` на `get_active_projects()` (из 176a)
- `infra/telegram/bot.py:45-48` — удалить мёртвый `PROJECT_CHAT_IDS` dict

**Out of scope (другие подспеки):**
- Pydantic schema, get_active_projects, migration 044 → ARCH-176a (предусловие)
- Scheduler validation gate, onboard CLI → ARCH-176c
- Документация → ARCH-176d
- TOKEN_REGISTRY в `infra/wb_api/token_manager.py` — backlog cleanup

---

## Allowed Files

### Existing files (modify)
- `infra/wb_api/client.py` — заменить 4 PROJECT_*_TOKENS dict'а (~60 LOC diff)
- `domains/reviews/cli.py` — `_VALID_PROJECTS` → `get_active_projects()` (~5-10 LOC)
- `domains/reviews/response_pipeline.py` — `_PROJECT_CONFIGS` → priority chain (~25 LOC)
- `infra/telegram/handlers.py` — `_infer_project_from_chat()` dynamic loop (~5 LOC)
- `infra/telegram/bot.py` — удалить мёртвый `PROJECT_CHAT_IDS` (~5 LOC)

### New files (create)
- `tests/test_wb_client_token_resolution.py`

**Forbidden:**
- `infra/wb_api/token_manager.py` — TOKEN_REGISTRY, отдельный backlog
- `tools/sabsabi_*.py` — one-shot скрипты, не трогать
- Удаление grisha legacy `WB_API_TOKEN` без суффикса (BACKWARD COMPAT)

---

## Eval Criteria

### Deterministic Assertions

| ID | Scenario | Input | Expected | Priority |
|----|----------|-------|----------|----------|
| EC-1 | Token convention для нового проекта | `create_project_client("kirill")` с `WB_API_TOKEN_KIRILL` в env | Возвращает client, нет UnknownProjectTokenError | P0 |
| EC-2 | Grisha legacy backward-compat | `create_project_client("grisha")` с `WB_API_TOKEN` (без суффикса) в env | Возвращает client, использует legacy token | P0 |
| EC-3 | No silent fallback | `create_project_client("kirill")` БЕЗ `WB_API_TOKEN_KIRILL` в env | Поднимает explicit error, НЕ fallback на чужой токен | P0 |
| EC-4 | CLI dynamic projects | `python -m domains.reviews.cli send --project sabsabi` после миграции 044 | Не отвергается как invalid project | P0 |
| EC-5 | seller_name priority chain | yaml: `name: "Kirill Shop"`, нет seller_name → response prompt | Использует "Kirill Shop", не "kirill" slug | P0 |
| EC-6 | seller_name fallback | yaml без seller_name и без name → response prompt | Использует "Kirill" (project_id.title()) | P1 |
| EC-17 | Telegram handlers dynamic | Kirill пишет в свой чат → `_infer_project_from_chat` | Возвращает "kirill", не None | P1 |

### Side-Effect Assertions

| ID | Affected Component | File:line | Regression Check | Priority |
|----|-------------------|-----------|------------------|----------|
| SA-1 | grisha pipeline run end-to-end | `infra/scheduler/jobs_reviews.py` | grisha/domabout/sabsabi не ломаются | P0 |
| SA-2 | Existing tests | `tests/test_review_*.py` | Все unit + integration tests passing | P0 |

---

## Implementation Plan

(Tasks from planner DAG — validated against codebase 2026-05-02, file:line refs verified)


### Task 2.1 — Token convention in `infra/wb_api/client.py`
- **File:** Modify `infra/wb_api/client.py:55-125`
- **Changes:**
  - DELETE all 4 PROJECT_*_TOKENS dicts (`:55-70`)
  - Add helper `_resolve_token(project: str, suffix: str = "") -> str`:
    - if `project == "grisha"` and not suffix → return `os.getenv("WB_API_TOKEN", "")` (legacy backward compat — see token_manager.py:80-81)
    - else `env_var = f"WB_API_TOKEN_{project.upper()}{suffix}"`, then `os.getenv(env_var, "")`
    - if empty → raise `EnvironmentError(f"Missing token: {env_var}. Add to .env: {env_var}=...")` (NO silent fallback — feedback-no-silent-token-fallback memory)
  - `create_project_client(project)` → `_resolve_token(project)` (no suffix)
  - `create_project_feedbacks_client(project)` → try `_resolve_token(project, "_FEEDBACKS")`; on EnvironmentError fallback to `_resolve_token(project)` with `warnings.warn` (mirror token_manager.py:91-100)
  - `create_project_buyer_chat_client(project)` → same as feedbacks (uses `_FEEDBACKS` suffix)
  - `create_project_returns_client(project)` → same as feedbacks (uses `_FEEDBACKS` suffix)

### Task 2.2 — Tests for token resolver
- **File:** Create `tests/test_wb_client_token_resolution.py`
- **Tests (monkeypatch env):**
  - `test_grisha_legacy_token()` — env `WB_API_TOKEN=abc`, no suffix → client.token == "abc"
  - `test_kirill_convention_token()` — env `WB_API_TOKEN_KIRILL=xyz` → returns client
  - `test_kirill_missing_token_raises()` — no env → EnvironmentError
  - `test_no_silent_fallback_to_grisha()` — env `WB_API_TOKEN=grisha_tok` set, `WB_API_TOKEN_KIRILL` unset → kirill client raises, NOT returns grisha token
  - `test_feedbacks_fallback_emits_warning()` — `WB_API_TOKEN_DOMABOUT_FEEDBACKS` unset, `WB_API_TOKEN_DOMABOUT` set → uses analytics token + warnings.warn

### Task 4.4 — Delete dead `PROJECT_CHAT_IDS` (do first — pure deletion, no risk)
- **File:** Modify `infra/telegram/bot.py:44-48`
- **Changes:**
  - Delete `PROJECT_CHAT_IDS: Dict[str, str] = {...}` (lines 44-48 + comment) — confirmed no readers via grep
  - Remove unused `Dict` import if it becomes unused

### Task 4.1 — Replace `_VALID_PROJECTS` in CLI
- **File:** Modify `domains/reviews/cli.py:22, :321`
- **Changes:**
  - Delete `_VALID_PROJECTS = ("grisha", "domabout")` (line 22)
  - Each `argparse` subparser at `:321` (and any other `choices=_VALID_PROJECTS`): replace with `choices=tuple(get_active_projects())` — call inside `_build_parser()` at runtime
  - Lazy `from shared.projects import get_active_projects`

### Task 4.2 — Replace `_PROJECT_CONFIGS` with priority chain
- **File:** Modify `domains/reviews/response_pipeline.py:31-34, :64, :101`
- **Changes:**
  - Delete `_PROJECT_CONFIGS` dict (lines 31-34)
  - At line 64, replace `config = _PROJECT_CONFIGS.get(...)` with helper `_resolve_seller_name(project_id) -> str`:
    - Lazy `from shared.project_config import ProjectConfig`, attempt `ProjectConfig.load(Path(f"projects/{project_id}/config.yaml"))`
    - Priority chain: `cfg.seller_name` (if not None) > `cfg.name` (if not None) > `project_id.title()`
    - On any exception (missing file, ValidationError) → `logger.warning(...)` and return `project_id.title()` (defensive)
  - Update line 101 (`seller_name=config["seller_name"]`) to `seller_name=_resolve_seller_name(project_id)`
  - Replace `config = ...` with single string variable

### Task 4.3 — Dynamic `_infer_project_from_chat`
- **File:** Modify `infra/telegram/handlers.py:318-331`
- **Changes:**
  - Replace hardcoded `for project in ("grisha", "domabout"):` (line 327) with `for project in get_active_projects():`
  - Lazy `from shared.projects import get_active_projects` inside function
  - Behavior unchanged: returns first project whose `TELEGRAM_CHAT_ID_{UPPER}` env matches; None if no match

### Execution order
```
2.1 → 2.2                (token convention + tests, independent)
4.4 → 4.1 → 4.2 → 4.3   (dead code first, then live consumers)
```

---

## Related

- **Parent:** ARCH-176 (master spec, status=split)
- **Depends on:** ARCH-176a (нужны `get_active_projects` и `ProjectConfig.load` + миграция 044 для EC-4 sabsabi)
- **Blocks:** ARCH-176c (onboard CLI должен работать с уже data-driven client/cli/handlers)
