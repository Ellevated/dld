# Manual Spec Verification Protocol

Чеклист оператора (или `/qa`-агента) для проверки, что спека, помеченная `done`, реально доставила
обещанное. Используется при подозрении на false-positive guard'а или перед ручным `force-done`.

**Шаги 1–3 автоматизированы** (`scripts/vps/spec_verify.py <project_dir> <SPEC_ID>` — allowed-file
existence + symbol grep + recent git log). **Шаги 4–6 — руками** (прогони продукт сам, не доверяй
эвристике). **Шаг 7** — вердикт + демоут через `spec_operator.py`.

> Контракт записи статуса и правила guard — [status-model.md](status-model.md). Статус живёт в
> `ai/lifecycle/*.yaml` (HEAD); демоут/force-done — только через `spec_operator.py` (plumbing, WT не
> трогается). **Не правь markdown руками для смены статуса.**

---

## Step 1 — Прочитать спеку

```bash
PROJECT=/home/dld/projects/awardybot
SPEC_ID=FTR-897
sed -n '/^## Allowed Files/,/^## /p' "$PROJECT"/ai/features/"$SPEC_ID"*.md
```
Заметь три секции: `## Allowed Files` (канон-список), `## Tasks`/`## Implementation Plan` (что должно
было произойти), `## Eval Criteria` (как проверять).

## Step 2 — Существование файлов

```bash
cd "$PROJECT"
for f in $(grep -E '^- `' ai/features/"$SPEC_ID"*.md | sed -E 's/^- `([^`]+)`.*/\1/'); do
  test -e "$f" && echo "OK   $f" || echo "MISS $f"
done
```
`NEW`-файл обязан существовать; `modified` — показывать недавние коммиты.

## Step 3 — Поиск символов

Для каждой Task grep ключевых символов (функции, роуты, классы) внутри allowed-директорий. Ноль
попаданий на обещанный символ = red flag.

```bash
grep -rn "create_buyer_account" "$PROJECT/src" | wc -l
```

## Step 4 — Тесты

```bash
cd "$PROJECT" && ./test ci      # CI-parity (TECH-206): зеркалит GitHub CI; должно быть зелёным
```
Новые тесты под `tests/unit/` или `tests/integration/`? Покрытие тронутых файлов выросло?

## Step 5 — Миграции (только DB-спеки)

```bash
ls "$PROJECT"/supabase/migrations/*"$SPEC_ID"*.sql 2>/dev/null
```
Спека упоминает schema-изменения, а файла миграции нет → **HARD-FAIL**. (Миграции — git-first, CI —
единственный источник apply; руками не накатывать.)

## Step 6 — Acceptance criteria

Для каждого `EC-N` в `## Eval Criteria`: `deterministic` → прогнать команду, сверить вывод;
`integration` → прочитать assert'ы, прогнать тест; `llm-judge` → ручной UAT end-to-end.

## Step 7 — Вердикт

- **Всё зелёное** → спека реально done, действий нет.
- **Любой red** → вернуть в `queued` с понятным reason:
  ```bash
  python3 scripts/vps/spec_operator.py demote "$PROJECT" "$SPEC_ID" \
    "Task 11 onboarding router missing" --by=operator
  ```
- **Застряла, но верифицирована вручную** → `force-done` (используй редко, аудит ПЕРЕД):
  ```bash
  python3 scripts/vps/spec_operator.py force-done "$PROJECT" "$SPEC_ID" \
    "manual verification passed" --by=operator
  ```
  (на уже-`done` спеке вернёт rc=5 — Rule 7, это норма.)
- **Circuit-breaker залип** после каскада демоутов:
  ```bash
  python3 scripts/vps/spec_operator.py reset-circuit
  ```

---

## Tooling

- `scripts/vps/spec_verify.py <project_dir> <SPEC_ID>` — автоматизирует шаги 1–3.
- `scripts/vps/spec_operator.py {demote,force-done,reset-circuit}` — шаг 7, всё через plumbing-commit.
- `scripts/vps/lifecycle_audit.py` — массовый READ-ONLY детектор дрейфа (14 категорий).
- Контракт статуса / правила guard — [status-model.md](status-model.md).
