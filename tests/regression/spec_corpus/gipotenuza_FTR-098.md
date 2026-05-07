# Feature: [FTR-098] Reviews → Physical Aspects (a) — Review Tagger

**Status:** done | **Priority:** P2 | **Risk:** R2 | **Date:** 2026-05-01 | **Parent:** FTR-096

## Goal

Часть (a) из разбитой FTR-096. Создать LLM-tagger отзывов по 7 физическим категориям (упаковка/ткань/посадка/запах/комплектация/прочность/доставка) с filesystem cache. БЕЗ wiring в pipeline и БЕЗ изменений в registry — это делает FTR-099.

## Scope (Tasks 1-3 из FTR-096)

См. полный план: [FTR-096](FTR-096-2026-04-27-reviews-as-physical-product-source.md) § Implementation Plan, Tasks 1-3.

### Task 1 — Bump comments limit 50→200

- Modify: `internal/collector/mpstats_extended.go` — `fetchComments` хардкод `"limit=50"` → константа `commentsFetchLimit = 200`.
- Cache namespace `"comments"` остаётся (старые 50-сэмплы инвалидируются за счёт другого hash от response shape).
- Acceptance: `go test ./internal/collector/...` зелёный.

### Task 2 — `extract.ReviewTagger` (Haiku 4.5)

- Create: `internal/analyzer/extract/review_tagger.go` (~120 LOC) — клон pattern'а `extract.PainExtractor`.
- Create: `internal/analyzer/extract/prompts/review_tags_v1.md` (русский, 7 категорий, JSON-only, дословные цитаты, эмодзи запрещены, max 3 цитаты на категорию).
- Create: `internal/analyzer/extract/review_tagger_test.go` — 3 теста (cache_hit, llm_fallback, parse_correctness на фикстуре из 10 реальных отзывов run-2026-04-27).
- `PromptVerTagsV1 = "review_tags_v1"`.
- Cache key: `sha256Sorted({"texts": texts}, promptVer, modelSlug)`.
- Graceful fallback: LLM error → пустой `TaggedReviews{Degraded: true, DegradedReason: ...}`.

### Task 3 — `PhysicalAspects` type + `AggregatePhysical`

- Create: `internal/analyzer/physical_product.go` (~80 LOC) — `PhysicalAspects` + `AggregatePhysical`.
- Create: `internal/analyzer/physical_product_test.go` (~100 LOC).
- ВАЖНО: тип лежит в `collector` package (НЕ analyzer), чтобы избежать circular import collector→analyzer. Поле `PhysicalAspects *PhysicalAspects` добавляется в `collector.ProductData` ТОЛЬКО в FTR-099.

```go
type PhysicalAspects struct {
    Categories map[string]CategoryStats // "packaging" | "fabric_quality" | "fit" | "smell" | "extras" | "durability" | "delivery"
    Source     string                   // "mpstats_comments"
}
type CategoryStats struct {
    PositivePct float64
    NeutralPct  float64
    NegativePct float64
    TopQuotes   [3]string
}
```

## Out of Scope (делает FTR-099)

- Wiring в `scanner.NewPipeline`.
- Поле `PhysicalAspects` в `collector.ProductData`.
- Registry flip 23-27 Manual→LLM.
- Prompt injection.
- Config флаги.

## Out of Scope (делает FTR-100)

- Reporter rendering.
- Calibration smoke на 4 артикулах.

## Definition of Done

- [x] `go test ./internal/collector/... ./internal/analyzer/extract/... ./internal/analyzer/...` зелёный.
- [x] `data/review_tagger_cache/` в `.gitignore`.
- [x] `.claude/rules/dependencies.md` секция «analyzer/review_tagger — `PromptVerTagsV1` персистится в cache key».
- [x] Manual smoke на 1 фикстуре отзывов: `TestReviewTagger_ParseCorrectness_GoldenFixture` + `TestReviewTagger_CacheMiss_ThenCacheHit` на `goldenReviews()` (10 отзывов, 7 категорий заполнены).

## Cost Note

COGS: ~18₽/full-scan (200 текстов × 5 nmID × Haiku 4.5). Полная стоимость full-scan ≈ light-scan + 140₽ Jam + 18₽ tagger. Pricing.yaml не трогаем — экспозиция только на платных Full, в budget guard уже учтено через `Pipeline.cogsKop`.

## Reference

- Parent spec: [FTR-096](FTR-096-2026-04-27-reviews-as-physical-product-source.md)
- Pattern: `internal/analyzer/extract/pain_clusters.go`
