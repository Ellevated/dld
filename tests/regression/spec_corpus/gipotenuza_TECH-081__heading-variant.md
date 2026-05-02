---
id: TECH-081
title: Haiku fallback for full-scan LLM (MP-027)
type: TECH
status: done
priority: P0
wave: 1
risk: R1
created: 2026-04-19
source: ai/architect/migration-path.md:402-416 (MP-027)
depends_on: []
spark_version: v2
---

# TECH-081 — Haiku 4.5 fallback for full-scan LLM path

## Context

MP-027 (Wave 1, P0, R1) — резервная модель для `ScanTypeFull`.

Сейчас `internal/analyzer/claude.go:180-183` жёстко валится после 3 неудачных попыток Sonnet 4.6 для full-scan: Light отрабатывает Haiku fallback, Full — хард-ошибка → revenue-критичный путь (платный скан пропадает, пользователь видит `shared.ErrClaudeBadOutput` / timeout).

Предложение архитекта (Scout #4 из `ai/architect/migration-path.md:410-416`): после 3 падений Sonnet полный скан тоже идёт в Haiku 4.5, помечая результат как `degraded=true` и пропуская метку downstream (в Excel и логи). Бюджет учитывает удешевление Haiku.

## Out of Scope

- Миграция существующего retry в `internal/analyzer/extract/client.go` — там свой контур (пары clusters / pain), решается отдельной задачей.
- Интеграция с `httpretry` из TECH-079 — `callLLM` здесь работает напрямую через `a.client.Do`, и менять его транспорт — отдельный риск (сломаются stub-серверы OpenRouter-mock в `analyzer_test.go`). Разнесено намеренно.
- Изменение промпта для Haiku — используется тот же `systemPrompt / userPrompt`, только `maxTokens=haikuMaxTokens`.
- Переключение на Haiku как primary.

## Blueprint Reference

- ADR-015 — domain-owned storage adapters (не трогаем).
- ADR-007 — Result/err propagation (сохраняется: возвращаем analysis + Degradation, не ошибку).
- Глоссарий: `Degradation` (см. `internal/analyzer/types.go:12-28`), `DiagnosticAlert` (см. `internal/analyzer/diagnostic_alerts.go`).
- Rules: `.claude/rules/architecture.md` ADR-014 (no mocks for DB shapes — здесь не DB, моки внешнего HTTP допустимы).

## User Story / Impact

- **Платёжный UX:** Full-scan (1500 ₽ за тариф Full) больше не падает при кратковременном 5xx в Sonnet.
- **Прозрачность:** Отчёт честно помечается «выполнен резервной моделью», чтобы selller понимал снижение качества и не считал это багом.
- **COGS:** Haiku ~в 5 раз дешевле Sonnet, поэтому `budgetUsed` начисляет `estimatedCostKop / 5` как и для Light (текущая ветка).

## Current State (AS-IS)

Файл `internal/analyzer/claude.go`:

```go
// lines 153-183
var lastErr error
for attempt := 0; attempt < maxRetries; attempt++ {
    if attempt > 0 {
        backoff := time.Duration(1<<uint(attempt-1)) * time.Second
        select {
        case <-ctx.Done():
            return nil, shared.ErrClaudeTimeout
        case <-time.After(backoff):
        }
    }

    result, err := a.callLLM(ctx, a.primaryModel, sonnetMaxTokens, systemPrompt, userPrompt)
    if err == nil {
        a.budgetUsed.Add(estimatedCostKop)
        a.recordModelUsed(a.primaryModel)
        result.PainClusters = painResult
        recordPainDegradation(result, painResult)
        a.applyDiagnosticAlerts(result, data, mediaFacts)
        return result, nil
    }
    lastErr = err
    if !isRetryable(err) {
        return nil, err
    }
    a.logger.Warn("analyzer.llm.retry", slog.Int("attempt", attempt+1), slog.String("error", err.Error()))
}

// Haiku fallback — only for Light scans
if scanType == criteria.ScanTypeFull {
    return nil, fmt.Errorf("analyzer: primary model failed after %d retries: %w", maxRetries, lastErr)
}

a.logger.Info("analyzer.llm.fallback", slog.String("model", a.fallbackModel))
result, err := a.callLLM(ctx, a.fallbackModel, haikuMaxTokens, systemPrompt, userPrompt)
if err != nil {
    return nil, fmt.Errorf("analyzer: fallback failed: %w", err)
}
a.budgetUsed.Add(estimatedCostKop / 5)
a.recordModelUsed(a.fallbackModel)
result.PainClusters = painResult
recordPainDegradation(result, painResult)
a.applyDiagnosticAlerts(result, data, mediaFacts)
return result, nil
```

Проблема: строки 181–183 отсекают Full, хотя Haiku доступен и прогон возможен.

## Target State (TO-BE)

### Поведение

1. Обе ветки (Light и Full) после 3 падений Sonnet идут в Haiku 4.5 с тем же промптом.
2. Успешный Haiku-fallback пишет `Degradation{Subsystem: "analyzer_llm", Reason: "primary_model_failed", Error: <truncated lastErr>}` в `ScanAnalysis.Degradations`.
3. Новый alert rule R20 `analyzer_haiku_fallback` в `detectDegradationAlerts` превращает запись в видимое предупреждение в Top5UrgentTasks.
4. `LastModelUsed()` возвращает slug Haiku — downstream (`scanner.pipeline.go:291`) уже сохраняет это в `scan_results.model_used` автоматически, Excel-отчёт читает оттуда.
5. `budgetUsed` начисляет `estimatedCostKop / 5` (как уже работает для Light). Гард бюджета перед стартом остаётся по Sonnet-estimate (фейл-сейф: резерв на полный Sonnet сохраняется, даже если в итоге пошли Haiku).
6. Если Haiku тоже упал — возвращаем `fmt.Errorf("analyzer: fallback failed: %w", err)` как сейчас (не добавляем retry в retry).

### Изменения в коде

**`internal/analyzer/claude.go`** (main edit):

- Удалить early-return для `ScanTypeFull` (строки 181–183).
- После успешного Haiku-fallback перед `applyDiagnosticAlerts` добавить:
  ```go
  result.Degradations = append(result.Degradations, Degradation{
      Subsystem: "analyzer_llm",
      Reason:    "primary_model_failed",
      Error:     truncErr(lastErr, 200),
  })
  ```
- Helper `truncErr(err error, max int) string` — в том же файле: `if err == nil { return "" }; s := err.Error(); if len(s) > max { s = s[:max] }; return s`. (Дублирование `truncErrString` из `scanner/pipeline.go` намеренно — кросс-пакетный импорт shim-функции нарушит ADR-015.)

**`internal/analyzer/diagnostic_alerts.go`**:

- Добавить case в `detectDegradationAlerts`:
  ```go
  case "analyzer_llm":
      alerts = append(alerts, DiagnosticAlert{
          Severity: "warning",
          Rule:     "analyzer_haiku_fallback",
          Message:  "Анализ выполнен резервной моделью (Haiku 4.5): основная модель (Sonnet 4.6) временно недоступна. Оценки могут быть менее точными — повторный скан через час обычно отрабатывает на основной модели.",
      })
  ```
- Расширить `degradationReasonRU` кейсом `primary_model_failed` → «сбой основной модели» (на случай если Error-поле пустое).

### Не изменяется

- `internal/analyzer/types.go` — структура `Degradation` уже вмещает новый Subsystem (строковое поле, без enum).
- `internal/scanner/pipeline.go` — пайплайн уже читает `LastModelUsed()` и сохраняет `scan_results.model_used`, уже запускает `DetectDiagnosticAlerts` после media-degradation.
- `internal/reporter/*` — Svodka уже получает Top5UrgentTasks из `ScanAnalysis.Summary`; alert R20 попадёт туда через стандартный mergeIntoTop5 путь.

## Allowed Files (STRICT)

Autopilot MAY modify ТОЛЬКО эти файлы:

- `internal/analyzer/claude.go` — удалить early-return, добавить запись Degradation, helper `truncErr`.
- `internal/analyzer/diagnostic_alerts.go` — добавить case `analyzer_llm` в `detectDegradationAlerts` + обновить `degradationReasonRU`.
- `internal/analyzer/analyzer_test.go` — новый тест `TestAnalyze_FullScan_HaikuFallbackOnSonnetFailure`.
- `internal/analyzer/diagnostic_alerts_test.go` — новый тест `TestDetectDiagnosticAlerts_AnalyzerLLM_EmitsR20`.

Любое касание других файлов — **STOP, спросить пользователя**.

## Eval Criteria

### Deterministic (unit/go test)

- **EC-1** `go build ./...` проходит.
- **EC-2** `go vet ./...` чист.
- **EC-3** Существующие тесты в `internal/analyzer/...` проходят без регресса — особенно `TestAnalyze_*` покрывающие light-fallback.
- **EC-4** `TestAnalyze_FullScan_HaikuFallbackOnSonnetFailure`: stub OpenRouter сервер отвечает 502 на первые 3 запроса (primary model), 200 с валидным tool_call на 4-й (fallback model). Проверки:
  - Результат: `err == nil`, `analysis != nil`, `len(analysis.Criteria) > 0`.
  - `a.LastModelUsed() == a.fallbackModel`.
  - `len(analysis.Degradations) >= 1`, одна из записей: `Subsystem=="analyzer_llm"`, `Reason=="primary_model_failed"`, `Error != ""`.
  - `a.BudgetUsedKop() == estimatedCostKop / 5` (начислено как Haiku, не Sonnet).
- **EC-5** `TestAnalyze_FullScan_FallbackAlsoFails`: stub отвечает 502 на все запросы. Проверка: `err != nil`, сообщение оборачивает `"analyzer: fallback failed"`.
- **EC-6** `TestAnalyze_FullScan_SonnetSucceedsFirstTry`: stub отвечает 200 сразу. Проверка: `LastModelUsed()==primaryModel`, `len(analysis.Degradations)==0`, бюджет начислен как Sonnet (`estimatedCostKop`).
- **EC-7** `TestDetectDiagnosticAlerts_AnalyzerLLM_EmitsR20`: передать `[]Degradation{{Subsystem:"analyzer_llm", Reason:"primary_model_failed"}}`, получить один alert с `Rule=="analyzer_haiku_fallback"`, `Severity=="warning"`.
- **EC-8** `TestDetectDiagnosticAlerts_AnalyzerLLM_Deduplicates`: две записи с `Subsystem=="analyzer_llm"` дают один алерт (существующий механизм seen-map в `detectDegradationAlerts`).

### Integration (real dependencies)

- **EC-9** Нет новых integration тестов — контур полностью покрыт через OpenRouter httptest stub (аналогично существующим `TestAnalyze_*` в `analyzer_test.go`). Причина: реальный Anthropic API через OpenRouter стоит денег и не детерминирован, а stub уже покрывает wire-protocol.

### LLM-judge

- Не требуется: семантика ответа не меняется, fallback идёт с тем же промптом.

### Manual smoke

- **EC-10** После merge один dev-прогон full-scan с временно сломанным `LLM_MODEL_PRIMARY` (через env override на несуществующий слаг): убедиться, что
  - Telegram присылает Excel,
  - Svodka содержит alert «Анализ выполнен резервной моделью…» в Top-5,
  - `scan_results.model_used='anthropic/claude-haiku-4.5'` в БД.

## Impact Tree (5-step Impact Analysis)

1. **UP — callers of `OpenRouterAnalyzer.Analyze`:**
   - `internal/scanner/pipeline.go` — уже обрабатывает любые Degradations через `DetectDiagnosticAlerts` (line 218). Новый subsystem попадёт в тот же контур автоматически.
   - `cmd/scan-cli`, `cmd/bot-loadtest` — вызывают через интерфейс `analyzer.Analyzer`, не зависят от fallback-логики.
2. **DOWN — uses:**
   - `callLLM` — не меняется.
   - `criteria.ScanTypeFull` — только читается, сама константа не затронута.
   - `a.fallbackModel` — уже инициализирован в конструкторе (DefaultFallbackModel = `anthropic/claude-haiku-4.5`).
3. **BY TERM grep:**
   - `rg -n "ScanTypeFull" internal/analyzer` → только `claude.go:181` (удаляемая строка) + тесты, отдельно проверим, что не сломали `TestAnalyze_ScanTypeFull_LoggedCorrectly` (analyzer_test.go:485).
   - `rg -n "primary_model_failed" .` после правки должен совпасть с новым кейсом в `diagnostic_alerts.go` и тестом.
4. **CHECKLIST:**
   - tests/ — новые test cases в `analyzer_test.go` и `diagnostic_alerts_test.go`.
   - db/migrations/ — не затрагивается.
   - deploy/ — не затрагивается.
   - scripts/gen-samples/ — не затрагивается (fallback не меняет sheetNames).
5. **DUAL SYSTEM:** Нет. Результат Haiku складывается в тот же `ScanAnalysis` shape, который потребляет reporter.

## Non-functional

- **Latency:** При fallback общее время = `3 × Sonnet timeout + backoff(500ms/1s/2s) + Haiku call`. Это уже хуже, чем сейчас (потому что сейчас — просто фейл), но быстрее, чем пытаться 6 раз Sonnet. Hard timeout `a.hardTimeout` накрывает всё (`ctx WithTimeout` на line 127).
- **Observability:** Логи `analyzer.llm.retry` (уже есть) + `analyzer.llm.fallback` (уже есть, line 185) — ничего нового. Можно добавить одну метрику `analyzer_fallback_total` через slog warn — отложено в Out of Scope (наблюдаемость метрик — отдельная Wave).
- **COGS:** `estimatedCostKop / 5` = ~280 коп = 2.8 ₽ за fallback (vs 14 ₽ Sonnet). Реальная стоимость записывается через `LastCostKop()` из OpenRouter usage поля — точнее estimate.

## Risks

| Risk | Mitigation |
|---|---|
| Haiku выдаёт невалидный tool_call (BUG-046 паттерн) | Тот же `callLLM` + guard `len(analysis.Criteria) == 0` уже есть (line 417). Haiku упадёт retryable → вернётся `"analyzer: fallback failed"`. |
| R20 alert перекроет более важные алерты в Top-5 | `MergeIntoTop5` уже делает приоритизацию по severity. R20 = `warning`, critical-правила (R1-R16) важнее. |
| `lastErr` nil на момент записи Degradation | Невозможно: в фоллбек-ветку попадаем только после цикла с 3 retryable-фейлами, каждый из которых выставляет `lastErr = err`. Defensive: helper `truncErr(nil, n)` возвращает пустую строку. |
| Параллельные скан-пайплайны (ARCH-044 concurrency) разделяют `lastModel atomic.Pointer` | Уже atomic, fallback пишет `a.recordModelUsed(fallbackModel)` — та же гарантия, что для primary. |

## Rollback

- Один revert коммита. Нет миграций, нет изменения схемы, нет изменения wire-protocol.
- Если Haiku-fallback делает хуже (например, массовые пустые criteria) — revert возвращает старое хард-фейл-поведение, пользователь увидит ошибку скана, но деньги не списались (billing ранее по флоу).

## Backlog Entry

```
- TECH-081 (Haiku fallback for full-scan LLM, MP-027) — queued, P0/R1, Wave 1
```

## Handoff

- Spark → autopilot: **ready**, human gate НЕ требуется (R1, R2-близкий — один файл ядра, изменение локализовано, покрытие тестами полное).
- Один коммит: `fix(analyzer): fallback to Haiku 4.5 on full-scan Sonnet failure (TECH-081)`.
- After merge: проверить в dev-логах наличие `analyzer.llm.fallback` при synthetic-фейле; подтвердить EC-10.
