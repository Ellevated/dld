# Architecture: [ARCH-055] Analyzer DAG — 4-фазный рефакторинг после вертикальных срезов
**Status:** blocked | **Priority:** P1 | **Risk:** R1 | **Date:** 2026-04-14
**Depends on:** FTR-050, FTR-051, FTR-052, FTR-053 в проде ≥1 неделю

## ACTION REQUIRED (2026-04-14)

Gate not satisfiable in this autopilot pass:
1. FTR-050 / FTR-052 shipped today (2026-04-14) — нужен реальный prod traffic ≥7 дней для calibration feedback по 4-фазной модели
2. FTR-051 в blocked (нужна live Gemini calibration)
3. FTR-053 в blocked (зависит от FTR-051)

Резюме: 4-фазная модель формализуется ТОЛЬКО после того, как все 4 вертикальных среза реально наберут feedback. Если рефакторить сейчас — это проектирование framework под гипотетические требования, что прямо запрещено в Context спеки.

Resume conditions: FTR-051 unblocked → FTR-053 unblocked → все 4 в проде ≥7 дней → собрать calibration feedback → пересмотреть 4-фазную модель (возможно нужно 3 или 5 фаз).

## Context

ARCH-047 основная архитектурная мысль: монолит `claude.go` → `Analyze()` делает три вещи сразу (парсит сырьё, считает факты, выдаёт вердикт) и упирается в output tokens (`finish_reason=length` на Sonnet 12288 при 32 критериях). После BUG-046 система работает, но хрупко — любое расширение критериев повторно взрывает potlimit.

**Важное архитектурное решение:** рефакторим **не до, а после** вертикальных срезов. Причина — мы не знаем какие реально нужны фазы и slots, пока не написали 4 живых extract/compute/derive/verdict вертикали (FTR-050/051/052/053). Рефакторинг сейчас = проектирование framework под гипотетические требования. Рефакторинг после = консолидация повторяющихся паттернов в явный контракт.

**Prerequisite gate:** спек стартует только когда все 4 вертикали (FTR-050/051/052/053) в проде ≥1 неделю и собрали calibration feedback. Если при выводе 4 вертикалей выяснилось, что 4-фазная модель не подходит (например, нужно 3 фазы или 5), этот спек переписывается с нуля.

## Goal

Вытащить общие паттерны из FTR-050/051/052/053 в явный 4-фазный pipeline:

1. **Phase 0 COLLECT** — уже существующий `collector/registry.go`, без изменений
2. **Phase 1 EXTRACT** — единая точка входа для LLM-экстракции на дешёвой модели (Gemini 3 Flash / Lite). В v1 поглощает `extract/pain_clusters.go` (FTR-051); в v2 — competitor claims, keyword density, positioning phrases
3. **Phase 2 COMPUTE** — единая точка для детерминированных computations (`collector/review_metrics.go`, `price_metrics.go`, `size_metrics.go`). Сейчас они разбросаны — консолидируется в `internal/analyzer/compute/`
4. **Phase 2.5 DERIVE** — детерминированные recommendations на базе compute (`analyzer/derive/size_recommendations.go`, `price_recommendations.go`, `pain_classification.go`). Формализуется как «pure function от facts, без LLM»
5. **Phase 3 VERDICT** — LLM per-block (Card/Product/Traffic) получает compressed facts + derive recommendations, формулирует narrative. Заменяет монолитный `claude.go Analyze()`
6. **Phase 4 SYNTH** — top-5 urgent, growth tasks, ИТОГО на базе scored verdicts

Миграция на Gemini 3 Flash как primary модель (с Sonnet fallback) — встроена в Phase 3 вызов.

## Non-Goals

- **Не** меняем публичный контракт `analyzer.ScanAnalysis` (reporter/sheet_svodka потребляет `Criteria[]` + `Summary` — внутри меняем, снаружи та же форма)
- **Не** трогаем `scan_results` schema inversion — добавляем 3 новые колонки (`extracted_facts jsonb`, `machine_facts jsonb`, `phase_timings jsonb`), старые не модифицируем
- **Не** выпиливаем старый `claude.go` одномоментно — сосуществуют в `ANALYZER_PIPELINE=legacy|dag` env flag для safe migration
- **Не** переписываем BUG-046 guard-rails — они мигрируют на Phase 3 с тем же принципом (empty criteria retry, diagnostic dump)
- **Не** расширяем число критериев в этом спеке — только пере-организация имеющихся
- **Не** добавляем media pipeline (ARCH-048) — ARCH-055 читает `MediaFacts` как input, не генерирует

## Architecture

### Directory layout

```
internal/analyzer/
├── extract/           # Phase 1 — LLM extract subagents
│   ├── pain_clusters.go       (from FTR-051)
│   ├── client.go              (from FTR-051 — OpenRouter wrap for Gemini)
│   ├── types.go
│   └── cache.go               (FS-based, reused)
│
├── compute/           # Phase 2 — pure Go deterministic facts
│   ├── review_metrics.go      (moved from collector — FTR-051)
│   ├── price_metrics.go       (moved from collector — FTR-050)
│   ├── size_metrics.go        (moved from collector — FTR-052)
│   ├── size_match.go          (moved from collector — FTR-053)
│   ├── brand_demand.go        (new, from ARCH-047 §8.5)
│   └── types.go               — unified FactsPerCard struct
│
├── derive/            # Phase 2.5 — deterministic recommendations
│   ├── price_recommendations.go
│   ├── size_recommendations.go
│   ├── pain_classification.go
│   └── types.go
│
├── verdict/           # Phase 3 — LLM per-block narrative
│   ├── block_card.go
│   ├── block_product.go
│   ├── block_traffic.go
│   ├── client.go              (Gemini 3 Flash primary, Sonnet fallback)
│   └── prompt.go              (per-block prompt builder)
│
├── synth/             # Phase 4 — top-5 / ИТОГО / niche insight
│   ├── top5.go
│   ├── summary.go
│   └── prompt.go
│
├── pipeline.go        # entry point: Analyze(ctx, ScanData) → ScanAnalysis
├── claude.go          # LEGACY path, guarded by ANALYZER_PIPELINE=legacy
└── pipeline_test.go
```

**Import direction:** strict one-way. `extract → compute → derive → verdict → synth`. No backward imports.

### Single entry point

```go
// internal/analyzer/pipeline.go
type Pipeline struct {
    extract   extract.Client
    verdict   verdict.Client
    synth     synth.Client
    registry  *criteria.Registry
    cache     extract.Cache
    pipelineVer string // "dag_v1" — хранится в scan_results
}

func (p *Pipeline) Analyze(ctx context.Context, data ScanData) (*ScanAnalysis, error) {
    // 1. EXTRACT (parallel safe)
    painResult, err := p.extract.PainClusters(ctx, data)
    // ... (guarded, fallback empty)

    // 2. COMPUTE (pure, no I/O)
    facts := compute.DeriveAll(data, painResult) // struct with all metrics

    // 3. DERIVE
    recs := derive.All(facts)

    // 4. VERDICT per block (3 parallel calls)
    verdicts, err := p.verdict.RunAll(ctx, facts, recs, p.registry)

    // 5. SYNTH
    summary, err := p.synth.Build(ctx, verdicts, facts)

    return assembleScanAnalysis(verdicts, summary, facts), nil
}
```

### DataKind unified enum

`internal/analyzer/compute/types.go`:
```go
type FactsPerCard struct {
    NmID           int64
    Pricing        *compute.PriceMetrics
    Review         *compute.ReviewMetrics
    Size           *compute.SizeMetrics
    SizeMatch      *compute.SizeMatch
    BrandDemand    *compute.BrandDemandFacts
    Media          *media.MediaFacts  // from ARCH-048, read-only here
    Pain           []extract.PainCluster
    // ...
}

type Facts struct {
    Ours   FactsPerCard
    Comps  []FactsPerCard  // 4 entries
    Category CategoryContext
    Classification criteria.ProductClass
}
```

Каждый критерий объявляет `RequiredFacts []DataKind` — pipeline проверяет полноту перед вызовом verdict, критерии с missing facts помечаются `data_missing` (fail-loud по ARCH-045).

### Per-block verdict calls

3 параллельных вызова в Phase 3:
- `verdict/block_card.go` — критерии Block=Card (фото, название, описание, цена, отзывы, …)
- `verdict/block_product.go` — Block=Product (размеры, SKU, состав, бренд, …)
- `verdict/block_traffic.go` — Block=Traffic (SEO, ключи, позиции, категорийный график, …)

Каждый блок получает только свой subset facts и только свой subset критериев. Output tokens блока ≤ 4K → уходим от `finish_reason=length`.

Параллелизм через `errgroup.Group`. Если один блок упал (timeout/error), остальные завершают; блок с ошибкой помечается `partial` в Summary и fail-loud пишет в diagnostic dump.

### Gemini 3 Flash migration

Primary model для Phase 3 verdict — `google/gemini-3-flash-preview` через OpenRouter:
- context 1M, max_out 65536 (×5 к Sonnet)
- цена $0.50 in / $3.00 out за M — ×9 дешевле Sonnet 4.6 на скан
- Fallback: `google/gemini-3.1-flash-lite-preview` (×2 дешевле, качество под вопросом — A/B)

**Схема ретраев:**
1. Gemini 3 Flash primary
2. На ошибке (timeout, 5xx, parse failure) → Gemini 3.1 Flash Lite
3. На втором провале → Sonnet 4.6 legacy path (как сегодня в claude.go)

Env flag:
```
ANALYZER_PIPELINE=dag  # новый pipeline (default после прогрева)
ANALYZER_PIPELINE=legacy  # старый claude.go
ANALYZER_PRIMARY_MODEL=gemini-3-flash-preview
ANALYZER_FALLBACK_MODEL=gemini-3.1-flash-lite-preview
```

### Persistence расширение

`db/migrations/NNNN_analyzer_dag_phase_data.sql`:
```sql
ALTER TABLE scan_results
    ADD COLUMN extracted_facts jsonb NULL,
    ADD COLUMN machine_facts jsonb NULL,
    ADD COLUMN phase_timings jsonb NULL,
    ADD COLUMN pipeline_version text NOT NULL DEFAULT 'legacy';
```

`pipeline_version`:
- `"legacy"` — старый claude.go
- `"dag_v1"` — новый pipeline

Позволяет ретро-сравнение между сканами на одном артикуле до/после миграции.

### Legacy migration gate

1. **Week 0** (этот спек ship): feature flag `ANALYZER_PIPELINE=dag` для dev-бота, prod остаётся `legacy`
2. **Week 1**: shadow mode — prod пишет оба (`legacy` результат в ScanAnalysis + DAG результат в `machine_facts`), сравниваем разности
3. **Week 2**: Canary 10% — случайные 10% prod сканов используют DAG
4. **Week 3**: Canary 50%
5. **Week 4**: `dag_v1` becomes default, legacy остаётся за env flag для emergency rollback
6. **Week 6**: удаляем `claude.go` legacy path

Shadow mode не в этом спеке, а в micro-итерации после него.

## Scope

**In scope:**
- Создание директорий `extract/` `compute/` `derive/` `verdict/` `synth/`
- Перенос `internal/collector/review_metrics.go` → `internal/analyzer/compute/review_metrics.go`
- Перенос `internal/collector/price_metrics.go` → `internal/analyzer/compute/price_metrics.go`
- Перенос `internal/collector/size_metrics.go` → `internal/analyzer/compute/size_metrics.go`
- Перенос `internal/collector/size_match.go` → `internal/analyzer/compute/size_match.go`
- Перенос `internal/analyzer/extract/*.go` (из FTR-051) — остаются в том же месте
- Перенос `internal/analyzer/derive/*.go` (из FTR-050/052) — остаются в том же месте
- Новые файлы `verdict/block_*.go`, `verdict/client.go`, `verdict/prompt.go`
- Новые файлы `synth/top5.go`, `synth/summary.go`
- `internal/analyzer/pipeline.go` — unified entry
- Feature flag `ANALYZER_PIPELINE` в config
- Миграция `db/migrations/NNNN_analyzer_dag_phase_data.sql`
- `internal/storage/store_scans.go` — write extracted_facts / machine_facts / pipeline_version
- Обновление `cmd/bot/adapters.go` — dependency injection pipeline vs legacy
- Unit tests на каждую phase + integration test end-to-end

**Out of scope:**
- Shadow mode и traffic split (micro-итерации после ship)
- Новые критерии
- Vision pipeline (ARCH-048)
- Brand demand compute (`brand_demand.go`) — отдельный микро-спек если потребуется
- Prompt tuning на конкретные блоки — v1 переносит текущий монолитный prompt, разделённый по блокам
- Удаление `claude.go` — оставляем до week 6

---

## Allowed Files

**Create:**
- `internal/analyzer/compute/` (directory + files moved from collector)
- `internal/analyzer/verdict/block_card.go`
- `internal/analyzer/verdict/block_product.go`
- `internal/analyzer/verdict/block_traffic.go`
- `internal/analyzer/verdict/client.go`
- `internal/analyzer/verdict/prompt.go`
- `internal/analyzer/verdict/*_test.go`
- `internal/analyzer/synth/top5.go`
- `internal/analyzer/synth/summary.go`
- `internal/analyzer/synth/prompt.go`
- `internal/analyzer/synth/*_test.go`
- `internal/analyzer/pipeline.go`
- `internal/analyzer/pipeline_test.go`
- `db/migrations/NNNN_analyzer_dag_phase_data.sql`
- `ai/diary/2026-04-XX-arch055-migration-notes.md`

**Modify:**
- `internal/collector/types.go` (remove moved types, keep pointers)
- `internal/collector/registry.go` (no longer derive metrics — pipeline does)
- `internal/analyzer/claude.go` (guard with feature flag, no behavior change)
- `internal/analyzer/prompt.go` (split into per-block builders or reuse in verdict/prompt.go)
- `internal/config/config.go` (+ `ANALYZER_PIPELINE` / `ANALYZER_PRIMARY_MODEL` / `ANALYZER_FALLBACK_MODEL`)
- `cmd/bot/adapters.go` (DI pipeline)
- `internal/storage/store_scans.go` (new columns)
- `.claude/rules/dependencies.md`
- `.claude/rules/architecture.md` (+ADR entry)
- `ai/backlog.md`

**Forbidden:**
- Удаление `claude.go` — оставляем как legacy path
- Изменения `analyzer.ScanAnalysis` public struct
- Новые MPStats / WB API вызовы
- Media pipeline mods

---

## ADR (новая запись)

`architecture.md`:

> **ADR-016** | Analyzer 4-phase DAG pipeline | 2026-04-XX | Monolithic `claude.go Analyze()` упирался в output tokens (finish_reason=length на 32 критериях), LLM одновременно парсил сырьё / считал факты / выдавал вердикт. Split на extract/compute/derive/verdict/synth фазы позволяет: (1) детерминизм Phase 2 вместо галлюцинаций, (2) per-block параллелизм в Phase 3 со сниженным output, (3) model routing (Gemini 3 Flash для verdict вместо Sonnet — ×9 дешевле), (4) кэш Phase 1 extract между сканами, (5) отладку extracted_facts/machine_facts в БД отдельно от verdicts.

---

## Tests

### Phase unit tests

#### test-1: compute.DeriveAll pure function
#### test-2: derive.All возвращает детерминированный slice
#### test-3: verdict.block_card возвращает ScanAnalysis.Criteria только для Block=Card
#### test-4: verdict.RunAll параллельно вызывает 3 блока
#### test-5: verdict retry chain на Gemini fail → Flash Lite → Sonnet
#### test-6: synth.Build собирает top-5 из готовых verdicts

### Pipeline integration

#### test-7: end-to-end на фикстуре ScanData (моки LLM)
**Given:** фикстура 5 карточек + mock extract + mock verdict clients
**Then:** ScanAnalysis.Criteria непустой, Summary.Top5 содержит ≥3 элемента, все критерии категории имеют Score

#### test-8: partial failure of one block
**Given:** block_product mock returns error
**Then:** final ScanAnalysis содержит Card + Traffic критерии, Block Product помечен `partial`, warn залогирован

#### test-9: data_missing fail-loud
**Given:** critical fact (PriceMetrics) отсутствует
**Then:** критерии, зависящие от него, помечены NotApplicable + reason="data_missing", остальные работают

### Feature flag gating

#### test-10: `ANALYZER_PIPELINE=legacy` routes to claude.go Analyze
#### test-11: `ANALYZER_PIPELINE=dag` routes to pipeline.Analyze

### Migration regression

#### test-12: На тех же калибровочных артикулах, где работали FTR-050..053, DAG даёт тот же набор критериев и чисел (±5% tolerance на LLM narrative)

### Cost regression

#### test-13: Полный pipeline cost per scan ≤ $0.05 (baseline Sonnet legacy — ~$0.08)
(замер через OpenRouter dashboard)

### BUG-046 regression

#### test-14: empty criteria retry работает в verdict layer
**Given:** verdict client returns 0 criteria on first try
**Then:** retry triggered, diagnostic dump saved

---

## Acceptance Criteria

- [ ] `go test ./internal/analyzer/...` зелёный, все 4 фазы покрыты
- [ ] `ANALYZER_PIPELINE=dag go run ./cmd/bot` — полный скан проходит на 3 калибровочных артикулах
- [ ] `ANALYZER_PIPELINE=legacy` — старый путь работает без регрессий (смоук-тест)
- [ ] `scan_results.pipeline_version='dag_v1'` после dag-скана
- [ ] Миграция `db/migrations/NNNN_*.sql` применяется через goose без ошибок
- [ ] Calibration regression: на тех же 4 артикулах, что использовались для FTR-050..053, DAG выдаёт ≥90% тех же критериев с numeric facts совпадающими 1-в-1
- [ ] Cost check: средний скан ≤ $0.05 (против ~$0.08 legacy)
- [ ] `finish_reason=length` никогда не возникает на 32-критериевых сканах (проверка на 10 прогонах)
- [ ] ADR-016 внесён в `architecture.md`

---

## Verification

1. `go test ./...`
2. `goose migrate up` (или runtime migration) — новая миграция проходит
3. `ANALYZER_PIPELINE=dag go run ./cmd/bot` → скан 3 калибровочных артикулов (apparel/beauty/electronics)
4. Открыть xlsx — проверить совпадение numeric facts с предыдущими сканами (до DAG)
5. `ANALYZER_PIPELINE=legacy` → скан тех же артикулов, сравнить `conclusion/task` за руку (качество не деградировало)
6. Dashboard OpenRouter — среднесуточный cost per scan с DAG
7. Grep `finish_reason=length` в логах — 0 occurrences

## Feedback Hook (после 1-2 недель DAG в canary)

- **Качество Gemini 3 Flash** на verdict: не галлюцинирует ли на редких категориях? A/B против Sonnet на 20 артикулах глазами
- **Per-block output tokens**: реально ли мы никогда не упираемся в лимит? Если block_card нежно трогает 4K — пересмотреть split
- **Extract cache hit rate**: стоит ли tune TTL или брать хэш по normalized texts
- **phase_timings** — какая фаза доминирует в latency? Если verdict — есть ли смысл делать частичный streaming?
- **data_missing count** — какие критерии чаще всего падают на missing facts? Прибавить больше fail-loud в collector если паттерн стабильный

## Risks

1. **Gemini 3 Flash quality regression** — mitigation: A/B gate на canary, Sonnet fallback остаётся рабочим
2. **Per-block parallel request fan-out** — 3 одновременных LLM вызовов утроят rate limit pressure. Mitigation: если upstream падает — serial fallback
3. **Migration scripts в prod** — `ALTER TABLE` на большой scan_results: только `ADD COLUMN` (фаст), не `ALTER COLUMN`. Проверить на backup
4. **Legacy path drift** — если `claude.go` забросим и потом вернёмся — регрессии. Mitigation: CI smoke test раз в день на обе ветки

## Notes

- Спек стартует **только после gate**: FTR-050/051/052/053 в проде ≥1 неделю с подтверждёнными паттернами
- Если при calibration выяснилось, что 4 фазы — не правильная декомпозиция (например, extract и compute склеиваются, или derive сливается с verdict), **этот спек переписывается**. Это нормально, такова цель откладывания рефакторинга
- Gemini 3 Flash цены: $0.50/$3.00 per M (2026-04 текущие на OpenRouter). Sonnet 4.6: $5/$25. Разница ×10 на input, ×8 на output
- Full DAG cost target: ≤ $0.05/scan, из них extract (~$0.005) + verdict (3×~$0.01) + synth (~$0.005) = $0.04
- Legacy path `claude.go` остаётся до week 6 migration для emergency rollback
- После ship — shadow mode и canary migration описаны отдельно (не в этом спеке), но gate-ы в этом спеке указаны
