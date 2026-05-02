# Bug Fix: [BUG-084] Keywords sheet пустой — регрессия с 13 апреля

**Status:** blocked | **Priority:** P1 | **Risk:** R2 | **Date:** 2026-04-25

## ACTION REQUIRED (2026-04-25)

Tasks 1 + 4 выполнены и закоммичены в ветке `fix/BUG-084`:
- `internal/collector/mpstats_keywords.go` — fetch с structured logging (slog) + warnings на 4 failure paths
- `internal/collector/mpstats_provider.go` — silent failure path заменён на `fetchKeywords`
- Defect B (LatestPos ordering) исправлен: `entry.Pos[0]` вместо `Pos[len-1]`
- Unit-тесты `TestMPStats_Keywords_LogsAndWarnings` (3 sub-tests) + `TestMPStats_Keywords_LatestPos_OrderingNewestFirst` — PASS

**Заблокировано на Task 2 (Diagnostic gate)** — требуется живой запрос к MPStats:

```bash
git checkout fix/BUG-084
go build -o /tmp/scan-cli ./cmd/scan-cli
for nm in 213779222 503663412 231851104; do
  /tmp/scan-cli -nm $nm -auto-competitors=false -type light 2>&1 | tee /tmp/diag-$nm.log
done
grep "collector.mpstats.by_keywords" /tmp/diag-*.log
```

По результату определить Task 3 fix по decision tree (Implementation Plan ниже), сделать Task 5/6, выставить status=resumed и перезапустить autopilot BUG-084.

## Symptom

`Keywords` лист в xlsx содержит только заголовок, строки 4+ пустые. Воспроизводится в обоих прогонах — `run-2026-04-13/212237368.xlsx` и `run-2026-04-24/{213779222,503663412,231851104}.xlsx`. Регрессия держится минимум 2 недели.

Следствие: критерий #29 «Позиции в поиске» получает `Conclusion = "Нет данных"` для всех ниш.

## Root Cause (5 Whys)

1. Почему Keywords пустой? — Reporter не получает keyword data либо получает пустой массив.
2. Почему не получает? — Либо collector не запрашивает MPStats keywords endpoint, либо запрашивает но парсинг возвращает empty, либо данные есть в Result но reporter не читает.
3. Почему регрессия с апреля? — Что-то изменилось в collector/MPStats integration в районе 13 апреля (нужен `git log -- internal/collector/`).

**ROOT CAUSE:** Точную точку определит autopilot диагностика. Гипотезы:
- MPStats endpoint изменил contract (response shape)
- Поле перестало пробрасываться через collector → analyzer → reporter
- Pipeline собирает keywords, но reporter ожидает другое поле

## Reproduction Steps

1. `go run ./cmd/scan-cli -nm 213779222 -auto-competitors -light=false`
2. Открыть xlsx → лист `Keywords`
3. Expected: список запросов + позиции
4. Got: только заголовок A4:G4 (пусто)

## Fix Approach (superseded by Implementation Plan below)

1. ~~`git log --since=2026-04-01 -- internal/collector/ internal/reporter/sheet_keywords*` — найти что изменилось~~
2. ~~Запустить scan с verbose log, проверить:~~
3. ~~Восстановить недостающее звено + integration test~~

См. `## Implementation Plan` ниже — конкретные таски с file:line и тестами.

## Diagnostic Findings (planner, 2026-04-25)

**Cold reading кода нашёл два независимых дефекта в `internal/collector/mpstats_provider.go`:**

### Defect A — silent failure path (нет логирования вообще)

`mpstats_provider.go:104-128` — fetch `by_keywords`:

```go
kwData, err := p.fetchEndpoint(ctx, nmID,
    fmt.Sprintf("get/item/%d/by_keywords", nmID), "by_keywords", "")
if err == nil && kwData != nil {
    var kwResp mpstatsKeywordsResponse
    if json.Unmarshal(kwData, &kwResp) == nil {
        for word, entry := range kwResp.Words {
            ...
        }
    }
}
```

Никакого логирования: ни ошибок, ни счётчика кейвордов, ни raw size response. Если MPStats возвращает `{"words": null}`, JSON-парсер успешно даёт `kwResp.Words == nil`, цикл крутится 0 раз, `pd.Keywords` остаётся пустым — **scan завершается «успешно» без warning'а**. Это объясняет, почему в `run-2026-04-24/213779222.log` нет ни одной строчки про keywords (см. логи — там только `collector.enrich_brands.ok`, никакой `collector.keywords.*`).

`Warnings` поле не заполняется при пустом результате. Sub-endpoint failures для `sizes`/`comments`/`brand` пишут `pd.Warnings = append(pd.Warnings, "mpstats sizes: " + err.Error())` (см. line 144, 152, 161, 170) — а `by_keywords` НЕ пишет ничего, потому что `if err == nil && kwData != nil` молча проглатывает `kwData == nil` (cache miss + HTTP 404/500 после CB open).

Кэш в БД (`mpstats_cache` table, TTL 24h) усугубляет: если хоть раз пришёл `{"words":{}}`, он залипает на сутки. Но регрессия держится 12+ дней — значит проблема воспроизводится **каждый раз**, а не закэширована.

### Defect B — `LatestPos` извлекается с конца массива (вероятно неправильный конец)

`mpstats_provider.go:111-113`:

```go
latestPos := 0
if len(entry.Pos) > 0 {
    latestPos = entry.Pos[len(entry.Pos)-1]   // <-- Go: last element
}
```

Python-эталон `src/scanner/auto_collect.py:259`:

```python
latest_pos = positions[0] if positions else 0   # <-- Python: first element
```

MPStats API doc (`docs/MPSTATS_API.md:120-134`) формат `pos: [45, 42, 38, ...]` — порядок не задокументирован. Sales endpoint в MPStats возвращает массив **от d2 (новее) к d1 (старее)** (см. `MPSTATS_API.md:55-58`), что согласуется с Python чтением `[0]` как «свежее». **Go берёт хвост** — это либо самое старое значение, либо мусор. Само по себе это не делает ячейку пустой (даёт неверное число), но в комбинации с тем, что `Words` map пустая, не относится к корневой причине.

### Гипотеза corner-case (может стать root cause после диагностики)

MPStats `by_keywords` для НЕ-одежды (зеркала, очки, отпариватели — это nmID `213779222`, `503663412`, `231851104` из калибровочного прогона) **возвращает `{}` без поля `words`** или `5xx` после нескольких неудачных запросов. Это классифицирует MPStats как «по этому nmID нет ключевых слов в индексе» — что правдоподобно для редких товаров. Тогда фикс — детектировать это явно и писать warning, а не молчать.

### Таким образом ROOT CAUSE = silent failure без логирования

Точная переменная (HTTP status, response shape, parse error) **не определяется по cold reading** — нужен живой запрос к MPStats. План ниже:
1. **Сначала** добавить логи и счётчики
2. **Потом** запустить диагностический прогон, зафиксировать ответ MPStats как fixture
3. **Потом** написать unit-тест на ту структуру, которую реально вернул MPStats
4. **Параллельно** починить `LatestPos` ordering и пробросить warning'и при пустом ответе

## Impact Tree Analysis

### Step 1: UP
- [ ] reporter sheet_keywords потребитель
- [ ] критерий #29 «Позиции в поиске» зависит от keywords

### Step 2: DOWN
- [ ] MPStats keywords API endpoint
- [ ] collector keyword fetch

### Step 3: BY TERM
- [ ] `grep -ri "keyword\|Keywords\|keywords" internal/collector/ internal/reporter/`

## Allowed Files

Определит autopilot. Ожидаемая зона:
- `internal/collector/*keyword*.go`
- `internal/reporter/sheet_keywords*.go`
- `internal/scanner/pipeline.go` (проброс)
- integration test

## Tests

1. **Integration:** scan-cli на nm 213779222 → лист Keywords содержит ≥1 строку запроса
2. **Unit:** collector keyword parser на сохранённом MPStats response (fixture)
3. **Regression:** golden fixture — структура keywords sheet не должна regressить

## Definition of Done

- [ ] Keywords sheet заполнен реальными данными для всех 3 тестовых nm_id
- [ ] Критерий #29 получает Conclusion с конкретными позициями (не «Нет данных»)
- [ ] Integration test
- [ ] Запись в Breaking Changes Log если был API contract change

## Reference

- Calibration report: `ai/calibration/run-2026-04-24/REPORT.md` § «Keywords sheet пустой»
- Evidence: `run-2026-04-24/213779222.xlsx Keywords!A4:G4` пусто

---

## Implementation Plan

Tasks ordered by dependency. Coder выполняет их строго подряд. **Task 2 — обязательный гейт**: без живого ответа MPStats Task 3-4 не выполняются.

### Allowed Files (canonical)

- `internal/collector/mpstats_provider.go` (modify; 343 LOC)
- `internal/collector/mpstats_types.go` (no-op read; reference for shape)
- `internal/collector/collector_test.go` (modify; ~600 LOC limit, currently ~280)
- `internal/collector/testdata/mpstats_by_keywords/` (create — fixtures)
- `tests/integration/collector_keywords_test.go` (create — real API smoke)
- `internal/reporter/sheet_keywords.go` (no modifications needed in MVP plan; revisit only if Task 5 reveals reporter-side bug)
- `.claude/rules/architecture.md` (modify «Breaking Changes Log» if API contract changed)

**FORBIDDEN to modify:** `internal/scanner/pipeline.go` (current data flow correct), `internal/reporter/types.go` (ReportData contract correct), `internal/collector/registry.go` (mergeProductData line 249-251 correctly propagates Keywords).

---

### Task 1: Add structured logging + warnings to keywords fetch path

**Files:**
- Modify: `internal/collector/mpstats_provider.go:104-128`

**Why:** Без логов никто 12 дней не замечал тихий silent failure. Логи нужны до фикса, чтобы на следующем калибровочном прогоне сразу увидеть точную причину.

**Steps:**

1. Открыть `internal/collector/mpstats_provider.go`, найти блок `// 3. Keywords` (line ~104).
2. Добавить `slog.Logger` поле в `MPStatsProvider` struct (line 21-29) и параметр в `NewMPStatsProvider` (line 32). **Если** `slog.Logger` уже есть — пропустить. Сейчас провайдер логгер не получает (см. сигнатуру). Минимальная инвазивность: использовать `slog.Default()` внутри fetch блока — без изменения публичного конструктора. Это допустимо потому что MPStatsProvider уже использует side-channel глобал (`net/http.DefaultTransport` через `*http.Client`).
3. Заменить блок lines 104-128 на:

```go
// 3. Keywords (BUG-084: было silent failure без логов).
kwData, kwErr := p.fetchEndpoint(ctx, nmID,
    fmt.Sprintf("get/item/%d/by_keywords", nmID), "by_keywords", "")
if kwErr != nil {
    // Запросов до этой точки уже было 2 (item, sales) — если 3-й
    // упал (CB open / 5xx / parse), пишем warning и идём дальше.
    pd.Warnings = append(pd.Warnings, "mpstats by_keywords: "+kwErr.Error())
    slog.Warn("collector.mpstats.by_keywords.fetch_failed",
        slog.Int64("nm_id", nmID),
        slog.String("error", kwErr.Error()))
} else if kwData == nil {
    // Pre-FTR-021 path: fetchEndpoint may return (nil, nil) on CB open.
    pd.Warnings = append(pd.Warnings, "mpstats by_keywords: empty body (CB open or cache miss after http error)")
    slog.Warn("collector.mpstats.by_keywords.empty_body",
        slog.Int64("nm_id", nmID))
} else {
    var kwResp mpstatsKeywordsResponse
    if uerr := json.Unmarshal(kwData, &kwResp); uerr != nil {
        pd.Warnings = append(pd.Warnings, "mpstats by_keywords: parse: "+uerr.Error())
        slog.Warn("collector.mpstats.by_keywords.parse_failed",
            slog.Int64("nm_id", nmID),
            slog.String("error", uerr.Error()),
            slog.Int("body_size", len(kwData)),
            slog.String("body_head", string(kwData[:min(len(kwData), 256)])))
    } else if len(kwResp.Words) == 0 {
        // Это самый подозрительный кейс — JSON распарсился, но Words пуст.
        // Возможные причины: контракт изменился, MPStats не находит товар
        // в индексе, ниша редкая. Логируем raw для дальнейшей диагностики.
        pd.Warnings = append(pd.Warnings, "mpstats by_keywords: zero words in response")
        slog.Warn("collector.mpstats.by_keywords.zero_words",
            slog.Int64("nm_id", nmID),
            slog.Int("body_size", len(kwData)),
            slog.String("body_head", string(kwData[:min(len(kwData), 512)])))
    } else {
        for word, entry := range kwResp.Words {
            latestPos := 0
            if len(entry.Pos) > 0 {
                // BUG-084 Defect B (Task 4): берём первый элемент, т.к.
                // MPStats возвращает массив newest→oldest (см. Python ref
                // src/scanner/auto_collect.py:259 и docs/MPSTATS_API.md).
                latestPos = entry.Pos[0]
            }
            avgPos := 0.0
            if len(entry.Pos) > 0 {
                sum := 0
                for _, pos := range entry.Pos {
                    sum += pos
                }
                avgPos = float64(sum) / float64(len(entry.Pos))
            }
            pd.Keywords = append(pd.Keywords, KeywordData{
                Word: word, Freq: entry.Freq, LatestPos: latestPos, AvgPos: avgPos,
            })
        }
        slog.Info("collector.mpstats.by_keywords.ok",
            slog.Int64("nm_id", nmID),
            slog.Int("words_count", len(kwResp.Words)))
    }
}
```

4. Helper `min` в Go 1.21+ — уже builtin (см. `go.mod` для подтверждения версии). Если Go ниже 1.21 — добавить локальный `func min(a, b int) int`.

**Tests (Task 1 unit):**

Add to `internal/collector/collector_test.go` after `TestMPStats_KeywordsParsing` (line 213-229):

```go
func TestMPStats_Keywords_LogsAndWarnings(t *testing.T) {
    // Case A: server returns 500 — should warn, not crash.
    srv500 := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if strings.HasSuffix(r.URL.Path, "/by_keywords") {
            w.WriteHeader(500)
            return
        }
        w.Write([]byte(`{"id":111}`)) // for /item; sales returns []; etc.
    }))
    defer srv500.Close()

    // Case B: server returns {"words": null}.
    srvNullWords := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if strings.HasSuffix(r.URL.Path, "/by_keywords") {
            w.Write([]byte(`{"words":null}`))
            return
        }
        w.Write([]byte(`{"id":111}`))
    }))
    defer srvNullWords.Close()

    // Case C: server returns valid words map.
    srvOK := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        if strings.HasSuffix(r.URL.Path, "/by_keywords") {
            w.Write([]byte(`{"words":{"футболка":{"pos":[5,10,15],"freq":1000}}}`))
            return
        }
        w.Write([]byte(`{"id":111}`))
    }))
    defer srvOK.Close()

    for _, tc := range []struct {
        name           string
        srv            *httptest.Server
        wantWordsLen   int
        wantWarnSubstr string
    }{
        {"500_warns", srv500, 0, "mpstats by_keywords"},
        {"null_words_warns", srvNullWords, 0, "zero words"},
        {"happy_path", srvOK, 1, ""},
    } {
        t.Run(tc.name, func(t *testing.T) {
            p := newTestMPStatsProvider(tc.srv)
            pd, err := p.FetchProduct(context.Background(), 111)
            if err != nil {
                t.Fatalf("FetchProduct: %v", err)
            }
            if len(pd.Keywords) != tc.wantWordsLen {
                t.Errorf("Keywords len = %d, want %d", len(pd.Keywords), tc.wantWordsLen)
            }
            if tc.wantWarnSubstr != "" {
                found := false
                for _, w := range pd.Warnings {
                    if strings.Contains(w, tc.wantWarnSubstr) {
                        found = true
                        break
                    }
                }
                if !found {
                    t.Errorf("warnings = %v, want substring %q", pd.Warnings, tc.wantWarnSubstr)
                }
            }
        })
    }
}
```

Add `"strings"` to `import (...)` block at top of `collector_test.go` if not already there.

**Acceptance:**
- `go test ./internal/collector/... -run TestMPStats_Keywords -v` → PASS, 4 sub-tests (existing + 3 new)
- `go vet ./...` → 0 warnings
- File ≤ 400 LOC (current 343 + ~70 = ~413 — slightly over; if so, перенести `Keywords` логику в новый `mpstats_keywords.go` 50 LOC)

---

### Task 2: Diagnostic live run + capture fixture (BLOCKING gate)

**Files:**
- Create: `internal/collector/testdata/mpstats_by_keywords/213779222.json`
- Create: `internal/collector/testdata/mpstats_by_keywords/503663412.json`
- Create: `internal/collector/testdata/mpstats_by_keywords/231851104.json`

**Why:** До диагностического прогона НЕЛЬЗЯ написать корректный фикс — мы не знаем, что именно ломается (5xx? `{"words":{}}`? переименованное поле?). Нужны живые ответы MPStats для 3 nmID из калибровочного прогона.

**Steps:**

1. **Build** updated bot binary локально: `go build -o /tmp/scan-cli ./cmd/scan-cli`
2. **Set env** (or read `/etc/gipotenuza/.env`):
   ```bash
   export MPSTATS_TOKEN=...
   export DATABASE_URL=postgres://...
   export OPENROUTER_API_KEY=...
   ```
3. **Run** diagnostic для всех 3 nmID:
   ```bash
   for nm in 213779222 503663412 231851104; do
     /tmp/scan-cli -nm $nm -auto-competitors=false -type light 2>&1 | tee /tmp/diag-$nm.log
   done
   ```
4. **Look for** `collector.mpstats.by_keywords.*` в логах. Должно быть одно из:
   - `.fetch_failed` → причина в HTTP/CB layer
   - `.empty_body` → cache miss + retry exhaustion
   - `.parse_failed` → формат ответа изменился (записать body_head)
   - `.zero_words` → товар не индексируется MPStats или контракт изменён
   - `.ok` (с words_count > 0) → значит пайплайн работает, проверить reporter side
5. **Capture raw response.** Если diag показал `.zero_words` или `.parse_failed`, нужен сам body. Самый простой путь — добавить **временный** debug-лог body в Task 1 (под флагом env, чтобы не насорить в проде):
   ```go
   if os.Getenv("MPSTATS_DEBUG_BY_KEYWORDS") == "1" && len(kwData) > 0 {
       _ = os.WriteFile(fmt.Sprintf("/tmp/mpstats_kw_%d.json", nmID), kwData, 0644)
   }
   ```
   Прогнать diag с `MPSTATS_DEBUG_BY_KEYWORDS=1`, скопировать `/tmp/mpstats_kw_*.json` → `internal/collector/testdata/mpstats_by_keywords/{nmID}.json`.
6. Удалить debug-блок (не коммитить env-флажок в финальный PR).
7. Записать **выводы** диагностики в spec — append section `## Diagnostic Run Results (YYYY-MM-DD)`:
   ```markdown
   ## Diagnostic Run Results (2026-04-25)

   nmID 213779222: <одна из 5 категорий из шага 4> + body_head <первые 256 байт>
   nmID 503663412: ...
   nmID 231851104: ...

   Итог: <одно предложение — какой именно дефект>
   ```

**Acceptance:**
- 3 fixture-файла созданы (могут быть `{"words":{}}` или с реальными словами — главное, чтобы это были РЕАЛЬНЫЕ ответы MPStats)
- spec обновлён секцией `## Diagnostic Run Results`
- Известна точная причина (HTTP error / parse error / empty body / contract change)

**If gate failed** (MPStats недоступен или сами 3 nmID удалены): использовать любой публичный nmID-одежды (например 212237368 из 04-13 прогона) + 1 nmID из своей текущей выдачи — главное собрать 3 разных кейса.

---

### Task 3: Conditionally fix the actual root cause (depends on Task 2 output)

**Files:**
- Modify: `internal/collector/mpstats_provider.go` (или `mpstats_types.go` если контракт изменился)

**Why:** Точечный фикс делается ПОСЛЕ Task 2. До Task 2 — nothing to fix.

**Decision tree (based on Task 2 results):**

| Diagnostic outcome | Fix |
|---|---|
| `.zero_words` для всех 3 nmID + body содержит ключи кроме `words` (например `keywords` или `data`) | Поменять JSON tag в `mpstats_types.go:39-41`: `Words map[string]mpstatsKeywordEntry \`json:"words"\`` → `\`json:"<new_field>"\``. Добавить ADR в Breaking Changes Log. |
| `.zero_words` + body это `{"words":{}}` (пустой объект) | MPStats не индексирует эти товары. Это **не bug**, это feature — добавить fallback: если `len(Words) == 0` и `nmID` валиден, помечаем criterion #29 как «нет данных от MPStats» (warning уже есть с Task 1). Закрыть BUG-084 как «not reproducible — данных у MPStats реально нет». |
| `.parse_failed` | Field type changed (например `pos: []int` → `pos: [[int, date]]`). Обновить `mpstatsKeywordEntry` struct. |
| `.fetch_failed` 401 | MPStats токен истёк / просрочен. Operational fix, not code. |
| `.fetch_failed` 5xx чаще 50% запросов | MPStats outage / rate-limit. Increase limiter window or add retry. |
| `.empty_body` | CircuitBreaker stuck. Reset CB или поднять `ReadyToTrip` threshold с 5 до 10. |
| `.ok` для всех 3 (words_count > 0) | Пайплайн на стороне collector работает, баг где-то в reporter. Идти в Task 5 + дебаг `kwBuildTop30` / `kwAllEmpty` / `selectCompetitors`. |

**Acceptance:**
- Конкретное изменение зависит от Task 2 outcome
- Все unit-тесты Task 1 должны продолжать проходить
- Если контракт изменился — добавить запись в `.claude/rules/architecture.md` § «Breaking Changes Log»: `2026-04-25 | BUG-084 | MPStats /by_keywords: contract change «words» → «<X>», stale Keywords data since 2026-04-XX`

---

### Task 4: Fix `LatestPos` ordering (newest = first element, не последний)

**Files:**
- Modify: `internal/collector/mpstats_provider.go:111-113`

**Why:** Уже встроен в Task 1 patch (см. `latestPos = entry.Pos[0]`). Этот таск отдельный, потому что нужен independent unit-test, а также потому что фикс может pre-empt'ить Task 3, если Task 3 фикс не нужен.

**Steps:**

1. **Verify** Task 1 уже применил `entry.Pos[0]` вместо `entry.Pos[len(entry.Pos)-1]`. Если applied — skip к шагу 2.
2. **Add unit test** в `collector_test.go` около `TestMPStats_KeywordsParsing` (line 213):

```go
func TestMPStats_Keywords_LatestPos_OrderingNewestFirst(t *testing.T) {
    // MPStats returns pos array newest-first (see Python ref auto_collect.py:259
    // и docs/MPSTATS_API.md /sales endpoint pattern «d2 → d1»).
    // Fixture: 3 days, position improved 45→42→38, newest = 38.
    body := `{"words":{"футболка":{"pos":[38,42,45],"freq":1000}}}`
    var kwResp mpstatsKeywordsResponse
    if err := json.Unmarshal([]byte(body), &kwResp); err != nil {
        t.Fatal(err)
    }
    entry := kwResp.Words["футболка"]
    // Replicate the production extraction logic.
    if got := entry.Pos[0]; got != 38 {
        t.Errorf("Pos[0] = %d, want 38 (newest)", got)
    }
}
```

3. Acceptance: тест проходит, `entry.Pos[0]` извлекает 38 (свежее значение).

**Acceptance:**
- `go test ./internal/collector/... -run TestMPStats_Keywords_LatestPos_OrderingNewestFirst -v` PASS
- `git diff internal/collector/mpstats_provider.go` показывает `entry.Pos[0]` instead of `entry.Pos[len(entry.Pos)-1]`

---

### Task 5: Integration test on real MPStats (no-mocks, ADR-013)

**Files:**
- Create: `tests/integration/collector_keywords_test.go`

**Why:** ADR-013 запрещает моки в integration tests. Тест должен ходить в реальный MPStats. Запускаем в локальном dev / на CI с секретом, в обычном CI-pipeline помечаем `//go:build integration && mpstats`.

**Steps:**

1. Создать файл:

```go
//go:build integration && mpstats

// Package integration — BUG-084 regression: Keywords sheet must contain
// at least one keyword for a known popular nmID.
package integration

import (
	"context"
	"net/http"
	"os"
	"testing"
	"time"

	"github.com/ellevated/gipotenuza/internal/collector"
)

// TestMPStats_ByKeywords_HasData_LiveAPI hits the real MPStats /by_keywords
// endpoint for an nmID that is guaranteed to be indexed (popular product).
// Skips if MPSTATS_TOKEN is unset.
func TestMPStats_ByKeywords_HasData_LiveAPI(t *testing.T) {
	token := os.Getenv("MPSTATS_TOKEN")
	if token == "" {
		t.Skip("MPSTATS_TOKEN not set")
	}

	// Popular nmID indexed in MPStats — выбираем из калибровочного прогона.
	// 212237368 = боди (одежда, очень частотное), используется в run-2026-04-13.
	const popularNmID int64 = 212237368

	httpClient := &http.Client{Timeout: 30 * time.Second}
	p := collector.NewMPStatsProvider(httpClient, token, nil)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()

	pd, err := p.FetchProduct(ctx, popularNmID)
	if err != nil {
		t.Fatalf("FetchProduct(%d): %v", popularNmID, err)
	}

	if len(pd.Keywords) == 0 {
		t.Fatalf("BUG-084 regression: pd.Keywords is empty for popular nmID %d. Warnings: %v",
			popularNmID, pd.Warnings)
	}

	// Sanity checks on first keyword
	first := pd.Keywords[0]
	if first.Word == "" {
		t.Errorf("first keyword has empty Word")
	}
	if first.LatestPos < 0 {
		t.Errorf("first keyword LatestPos = %d, want >= 0", first.LatestPos)
	}
	t.Logf("OK: %d keywords, first = {Word:%q Freq:%d LatestPos:%d}",
		len(pd.Keywords), first.Word, first.Freq, first.LatestPos)
}
```

2. Verify build constraint синтаксис не конфликтует с другими integration-тестами:
   `grep -rn "//go:build integration" tests/integration/` — должны быть аналогичные файлы.

3. Run locally:
   ```bash
   MPSTATS_TOKEN=... go test -tags 'integration mpstats' ./tests/integration/ -run TestMPStats_ByKeywords -v
   ```

**Acceptance:**
- Файл компилируется без ошибок при `-tags 'integration mpstats'`
- Pass с реальным токеном MPStats и popular nmID
- В обычном CI (без тэгов) тест НЕ запускается (skipped by build tag)
- Время выполнения < 60 секунд

---

### Task 6: Manual end-to-end verification

**Files:** none (verification only)

**Steps:**

1. Build: `go build -o /tmp/scan-cli ./cmd/scan-cli`
2. Run scan-cli с auto-competitors на 3 калибровочных nmID:
   ```bash
   for nm in 213779222 503663412 231851104; do
     /tmp/scan-cli -nm $nm -type full -auto-competitors -auto-competitors-limit 4 \
       2>&1 | tee /tmp/verify-$nm.log
   done
   ```
3. Открыть каждый xlsx (путь в `excel=...`), проверить лист `Keywords`:
   - Row 1 (merged): «Ключевые слова»
   - Row 3 headers: Запрос / Частота / МЫ / ТОП-1 / ТОП-2 / ТОП-3 / Слабый
   - Rows 4-33: **минимум 1 заполненная строка** с ненулевой частотой и хотя бы одной позицией в одной из колонок C-G
4. Открыть лист `Сводка`, найти строку «#29 Позиции в поиске» — Conclusion должен содержать конкретные ключевые слова или позиции, **не** строго «Нет данных».
5. Если хотя бы 1 из 3 nmID показывает пустой Keywords sheet — RETURN to Task 2 (что-то упустили).
6. **Если все 3 показывают данные** — спишем результаты в spec section `## Verification Run (2026-04-25)`:
   ```markdown
   ## Verification Run (2026-04-25)

   - 213779222: Keywords рендерит N запросов, top-1 «...», МЫ позиция X
   - 503663412: ...
   - 231851104: ...

   Критерий #29 Conclusion для 213779222: «...»
   ```

**Acceptance:**
- Все 3 калибровочных nmID показывают `Keywords!A4:G4` НЕ пустым
- Минимум 1 nmID имеет ≥10 строк ключевых слов
- Критерий #29 имеет осмысленный Conclusion

---

### Execution Order

```
Task 1 (logging) → Task 2 (diagnostic gate) → Task 3 (root-cause fix)
                                            ↘ Task 4 (LatestPos fix, parallel after Task 1)
                                                    ↘ Task 5 (integration test)
                                                            ↘ Task 6 (manual verification)
```

Task 1 must merge first (logs needed for Task 2). Task 2 is BLOCKING — без живого ответа MPStats Task 3 не выполняется. Task 4 (LatestPos) можно делать параллельно с Task 2/3, потому что фикс ясный из cold reading. Task 5 пишется после Task 3 (тест должен подтвердить именно тот fix). Task 6 — финальная human-side проверка.

### Dependencies

- **Task 2 → Task 3**: cannot fix without diagnostic data
- **Task 1 → Task 2**: diagnostic uses logs added in Task 1
- **Task 3 → Task 5**: integration test verifies the fix
- **Task 5 → Task 6**: end-to-end check after integration test passes
- Task 4 depends only on Task 1 (independent of Task 2/3 outcome)

### Risk

- **R2** — все изменения локализованы в `internal/collector/mpstats_provider.go` + tests. Reporter не меняется. Backward-compatible (slog warnings в новых местах).
- Mitigation: Task 6 запускает scan на 3 разных nmID — катастрофическую регрессию заметим до merge.

### Research Sources

- `docs/MPSTATS_API.md:120-134` — by_keywords contract reference (2026-02-17 verified)
- `src/scanner/auto_collect.py:248-267` — Python reference impl (Task 4 LatestPos ordering)
- `ai/calibration/run-2026-04-24/REPORT.md:90-91` — evidence that empty rows persist 12+ days
- `ai/features/FTR-026-2026-04-12-keywords-heatmap-sheet.md` — original Keywords sheet contract
- `ai/features/FTR-021-2026-04-12-mpstats-extended-data.md:231` — confirms `Capabilities() = [Sales, Keywords, Similar]` is intended (no scope drift)
- `.claude/rules/architecture.md` ADR-013 (no mocks in tests/integration/) — Task 5 build-tagged real API call
