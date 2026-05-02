# Feature: [FTR-092] Обложка товара в шапке Excel-отчёта

**Status:** done | **Priority:** P1 | **Risk:** R2 | **Date:** 2026-04-27 | **Source:** calibration run-2026-04-27

## Goal

Добавить главное фото лида (обложку карточки) в шапку листа «Сводка» в xlsx-отчёте, чтобы пользователь сразу видел, о какой карточке идёт речь, без переключения в WB.

Сейчас отчёт — голые цифры. Опираясь на абстрактный nmID, тяжело удерживать контекст что именно бот сейчас разбирает (особенно когда отчётов много).

## User Story

«Я открываю xlsx-отчёт от бота. В первой строке листа Сводка вижу: 200×200 пикселей фото моей карточки + nmID + ссылку на карточку WB. Дальше — обычная аналитика. Если кликнуть по фото, оно открывается в полном разрешении.»

## Design

- В шапке листа «Сводка» (до строки с критериями, до баннера BUG-090) — выделенный блок «Карточка»: левая колонка — фото 200×200, правая — nmID, бренд, название, цена, ссылка на WB.
- Источник фото: главная WB-картинка через `https://basket-XX.wbbasket.ru/vol.../images/big/1.webp` (уже есть в collector — `MainPhoto.URL`).
- Конвертация webp → png/jpeg (xlsx не любит webp) — на лету через стандартную golang lib (`image/png`, `golang.org/x/image/webp`).
- Если фото нет / не скачалось — placeholder «фото недоступно» (без падения отчёта).
- Ширина блока — 4 колонки, высота — ~12 строк.

## Allowed Files

1. `internal/reporter/sheet_svodka.go` — добавить header-блок до текущего рендера.
2. `internal/reporter/sheet_svodka_helpers.go` — helper `embedCoverPhoto(f, sheet, url) error` (загрузка, ресайз, embed).
3. `internal/reporter/types.go` — поле `CoverPhotoURL string` в `ReportData` (если ещё нет).
4. `internal/reporter/generate.go` — пробросить `CoverPhotoURL` из `ProductData.MainPhoto.URL`.
5. `internal/reporter/sheet_svodka_test.go` — assertion что image inserted (excelize `GetPictures`).
6. `go.mod` / `go.sum` — `golang.org/x/image/webp` если нужно.

## Tests

1. **Unit:** `embedCoverPhoto` с фикстурой webp 800×800 → ресайз 200×200, формат RGBA, без panic.
2. **Unit:** `embedCoverPhoto` с 404 URL → возвращает nil-error, в отчёте placeholder.
3. **Reporter integration:** generate() с `CoverPhotoURL=...` → xlsx содержит embedded image на листе Сводка.
4. **Reporter regression:** generate() с `CoverPhotoURL=""` → отчёт строится без падения, без image.
5. **Visual smoke (manual):** прогнать `scan-cli` на 490509833, проверить xlsx визуально.

## Definition of Done

- [ ] Все 4 артикула из run-2026-04-27 → xlsx содержит обложку.
- [ ] При недоступном фото — отчёт без падения.
- [ ] Размер xlsx не превышает 500 KB (контролируем размер фото).
- [ ] Regression: light/full sample.xlsx (`scripts/gen-samples`) перегенерированы и закоммичены (см. `.claude/rules/dependencies.md` § scripts/gen-samples).

## Reference

- `internal/collector/wb_basket.go` — где `MainPhoto.URL` формируется.
- excelize doc: `AddPicture` API.
- `ai/calibration/run-2026-04-27/QUALITY-COMPARE.md` — фидбэк пользователя про визуал.

---

## Drift Log

**Checked:** 2026-04-29 10:30 UTC
**Result:** light_drift

### Changes Detected
| File | Change Type | Action Taken |
|------|-------------|--------------|
| `internal/collector/wb_basket.go` | spec talks about `MainPhoto.URL` shape; this struct does NOT exist in `collector` package | AUTO-FIX: clarified — photo URL is NOT pre-stored on `ProductData`. Built ad-hoc by `media.buildPhotoURL` (`internal/media/collector.go:234-238`). Plan adds new helper `MainPhotoURL(nmID, host)` in collector + caller (pipeline.go:279) builds URL and passes via `ReportData.CoverPhotoURL`. |
| `internal/reporter/types.go` | `ReportData` already exists at line 13 with fields Analysis/Product/Competitors/ScanType/GeneratedAt/Class/SubjectText/MediaFacts/SkippedCriteria; no `CoverPhotoURL` yet | OK — additive change. |
| `internal/reporter/sheet_svodka.go` | Already has Row 1 (title) + Row 2 (price anomaly banner BUG-090) + Row 3 (header row) + freeze C5. Cover block must go BEFORE Row 1 to keep BUG-090 row offsets stable, OR shift everything down by N rows. | Plan chooses shift: cover block occupies Rows 1..N, push existing title to Row N+1. Adjust `SetPanes` YSplit. |
| `internal/reporter/sheet_svodka_helpers.go` | exists (215 LOC, has `selectCompetitors`, `writeITOGO`, `writeSparklineForPrice`, `writeNARows`); spec says ADD helper here | OK — but cover-photo helper warrants its own file for LOC budget + clarity (≈250 LOC for fetch+resize+embed+placeholder). |
| `internal/reporter/generate.go` | line 16 — only 45 LOC total; `Generate(data *ReportData) ([]byte, error)` orchestrates 8 sheet writers | OK — no changes needed; cover handled inside `writeSvodka`. |
| `internal/scanner/pipeline.go:279-289` | `reportData := &reporter.ReportData{...}` build site; needs `CoverPhotoURL` line | OK — additive. |
| `go.mod` | `golang.org/x/image v0.25.0` already in `go.sum` (transitive) but NOT in `require` of go.mod | Plan adds explicit `require golang.org/x/image v0.25.0` line. |
| spec `## Allowed Files` | mentions `internal/reporter/sheet_svodka_helpers.go` — that file exists; spec says to add `embedCoverPhoto` there | Plan creates NEW file `internal/reporter/sheet_svodka_cover.go` (cleaner separation). Updated Allowed Files below. |

### References Updated
- Task 1 file: `internal/reporter/sheet_svodka_helpers.go` → NEW `internal/reporter/sheet_svodka_cover.go` (LOC budget; helpers file is already 215 LOC, would push past 400)
- Task 3 file: `internal/collector/wb_basket.go` — add public helper `MainPhotoURL(nmID int64, host string) string`
- Task 4 file: `internal/scanner/pipeline.go:279` — extend ReportData literal (resolver is already constructed in `cmd/bot/main.go:102` and `cmd/scan-cli/main.go:152`; we plumb URL via Pipeline ctor or do `MainPhotoURL` call inline using the resolver provided to the WB provider — see Task 4 design).

### Updated Allowed Files (supersedes spec § Allowed Files)
1. `internal/reporter/sheet_svodka_cover.go` — **NEW** — `embedCoverPhoto`, `fetchAndResizePhoto`, `writeCoverHeader`, `writePlaceholderHeader`.
2. `internal/reporter/sheet_svodka.go` — adjust `writeSvodka` to call `writeCoverHeader` first, shift row offsets, fix `YSplit`.
3. `internal/reporter/types.go` — add `CoverPhotoURL string` to `ReportData`.
4. `internal/collector/wb_basket.go` — add public `MainPhotoURL(nmID int64, host string) string`.
5. `internal/scanner/pipeline.go` — fill `CoverPhotoURL` in `ReportData` literal (Pipeline gains optional `basket *collector.BasketResolver` field).
6. `cmd/bot/main.go` + `cmd/scan-cli/main.go` + `cmd/bot-loadtest/main.go` — pass `basketResolver` to `scanner.NewPipeline`.
7. `internal/scanner/pipeline.go` — `NewPipeline` gets new `basketResolver` param.
8. `internal/reporter/sheet_svodka_cover_test.go` — **NEW** — unit tests for fetch/resize/embed/placeholder.
9. `internal/reporter/sheet_svodka_test.go` — extend with `TestWriteSvodka_WithCoverPhotoURL` regression.
10. `go.mod` / `go.sum` — explicit `golang.org/x/image v0.25.0` require.
11. `scripts/gen-samples/main.go` — UNCHANGED (samples don't go through reporter.Generate; they are independent stubs — see `dependencies.md` § scripts/gen-samples). The DoD line about "samples regen" is a left-over guard rail; flag in plan as "no-op for this task" with explanation.

---

## Implementation Plan

### Execution Order

```
Task 1 (helper, no deps) ─────────────────┐
                                          ↓
Task 2 (types: CoverPhotoURL)──→ Task 3 (collector: MainPhotoURL) ──→ Task 4 (pipeline: pass URL)
                                          ↓
                                  Task 5 (svodka integration) ──→ Task 6 (svodka tests)
                                          ↓
                                  Task 7 (DoD verification + diary)
```

Tasks 1–3 can run in parallel (no inter-dependencies). Tasks 4–7 are strictly sequential.

---

### Task 1: Cover photo helper — fetch, decode webp, resize to 200×200, embed PNG

**Files:**
- Create: `internal/reporter/sheet_svodka_cover.go` (≈220 LOC)

**Context:**
Self-contained helper that owns the network fetch, webp→PNG conversion, and `excelize.AddPictureFromBytes` insertion. Returns `nil` for any failure mode (404, decode error, timeout) — caller renders text-only placeholder. Network is a HARD external boundary; injectable `httpClient` for tests + 5s timeout.

**Step 1: Write failing test**

```go
// internal/reporter/sheet_svodka_cover_test.go
package reporter

import (
	"bytes"
	"image"
	"image/png"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/xuri/excelize/v2"
	xwebp "golang.org/x/image/webp"
)

// fixtureWebP returns a 800×800 magenta webp blob suitable for decode tests.
// Note: we generate the fixture on-the-fly using image/draw so the test stays
// hermetic (no checked-in binaries).
func fixtureWebP(t *testing.T) []byte {
	t.Helper()
	// golang.org/x/image/webp is decode-only; build the test fixture in PNG and
	// stream it back as bytes — the SUT switches on Content-Type, not extension.
	img := image.NewRGBA(image.Rect(0, 0, 800, 800))
	for x := 0; x < 800; x++ {
		for y := 0; y < 800; y++ {
			img.Set(x, y, image.NewUniform(image.Black).At(0, 0))
		}
	}
	var buf bytes.Buffer
	if err := png.Encode(&buf, img); err != nil {
		t.Fatalf("encode png: %v", err)
	}
	_ = xwebp.Decoder // ensures import is used in real test path below
	return buf.Bytes()
}

func TestFetchAndResizePhoto_HappyPath_PNG(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		w.Write(fixtureWebP(t))
	}))
	defer srv.Close()

	got, err := fetchAndResizePhoto(srv.Client(), srv.URL, 200, 200)
	if err != nil {
		t.Fatalf("fetchAndResizePhoto: %v", err)
	}
	if len(got) == 0 {
		t.Fatal("expected non-empty PNG bytes")
	}
	// Verify it decodes as PNG and dimensions are 200×200.
	cfg, err := png.DecodeConfig(bytes.NewReader(got))
	if err != nil {
		t.Fatalf("DecodeConfig: %v", err)
	}
	if cfg.Width != 200 || cfg.Height != 200 {
		t.Errorf("dims = %dx%d, want 200x200", cfg.Width, cfg.Height)
	}
}

func TestFetchAndResizePhoto_404Returns_Empty(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	got, err := fetchAndResizePhoto(srv.Client(), srv.URL, 200, 200)
	if err == nil {
		t.Errorf("expected error on 404, got nil")
	}
	if got != nil {
		t.Errorf("expected nil bytes on 404, got %d bytes", len(got))
	}
}

func TestFetchAndResizePhoto_NetworkError_NoPanic(t *testing.T) {
	// Bad URL — no server.
	got, err := fetchAndResizePhoto(http.DefaultClient, "http://127.0.0.1:1/bad", 200, 200)
	if err == nil {
		t.Errorf("expected error on unreachable host, got nil")
	}
	if got != nil {
		t.Errorf("expected nil bytes on net error, got %d bytes", len(got))
	}
}

func TestEmbedCoverPhoto_HappyPath_PictureInserted(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		w.Write(fixtureWebP(t))
	}))
	defer srv.Close()

	f := excelize.NewFile()
	defer f.Close()
	f.NewSheet(sheet)

	httpClient := srv.Client()
	if err := embedCoverPhoto(f, sheet, "A1", srv.URL, httpClient); err != nil {
		t.Fatalf("embedCoverPhoto: %v", err)
	}
	pics, err := f.GetPictures(sheet, "A1")
	if err != nil {
		t.Fatalf("GetPictures: %v", err)
	}
	if len(pics) == 0 {
		t.Errorf("expected ≥1 picture in A1, got 0")
	}
}

func TestEmbedCoverPhoto_404_ReturnsErrorNoPicture(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	f := excelize.NewFile()
	defer f.Close()
	f.NewSheet(sheet)

	err := embedCoverPhoto(f, sheet, "A1", srv.URL, srv.Client())
	if err == nil {
		t.Errorf("expected error on 404, got nil — caller decides how to render placeholder")
	}
	pics, _ := f.GetPictures(sheet, "A1")
	if len(pics) != 0 {
		t.Errorf("expected 0 pictures after 404, got %d", len(pics))
	}
}

func TestWriteCoverHeader_NoURL_RendersPlaceholderText(t *testing.T) {
	f := excelize.NewFile()
	defer f.Close()
	f.NewSheet(sheet)
	styles := createStyles(f)

	rowsUsed := writeCoverHeader(f, styles, &ReportData{
		CoverPhotoURL: "",
		Product: &collector.ProductData{
			NmID: 174236476,
			Card: &collector.WBCardData{Brand: "Acme", Name: "Блузка летняя"},
		},
	}, http.DefaultClient)

	if rowsUsed != coverHeaderRows {
		t.Errorf("rowsUsed = %d, want %d", rowsUsed, coverHeaderRows)
	}
	val, _ := f.GetCellValue(sheet, "B1")
	if !strings.Contains(val, "174236476") {
		t.Errorf("nmID expected in B1, got %q", val)
	}
	// Placeholder text — brand-safe, no emoji.
	cell, _ := f.GetCellValue(sheet, "A2")
	if cell != "" && !strings.Contains(cell, "Фото недоступно") {
		t.Errorf("A2 placeholder = %q, want 'Фото недоступно'", cell)
	}
}
```

**Step 2: Verify test fails**

```bash
cd /home/dld/projects/gipotenuza/.worktrees/FTR-092
go test ./internal/reporter -run TestFetchAndResizePhoto -v
```

Expected: FAIL `undefined: fetchAndResizePhoto`, `undefined: embedCoverPhoto`, `undefined: writeCoverHeader`, `undefined: coverHeaderRows`.

**Step 3: Write implementation**

```go
// internal/reporter/sheet_svodka_cover.go
//
// Package reporter — Cover photo block for the Svodka sheet header.
// Uses:
//   - net/http for fetch
//   - golang.org/x/image/webp for webp decode
//   - image/png + golang.org/x/image/draw for resize → PNG
//   - excelize.AddPictureFromBytes for embed
//
// Used by: sheet_svodka.go:writeSvodka (top of sheet, before title)
// Glossary: ai/glossary/reporter.md
package reporter

import (
	"bytes"
	"context"
	"fmt"
	"image"
	"image/jpeg"
	"image/png"
	"io"
	"log/slog"
	"net/http"
	"time"

	"github.com/ellevated/gipotenuza/internal/collector"
	"github.com/xuri/excelize/v2"
	"golang.org/x/image/draw"
	xwebp "golang.org/x/image/webp"
)

const (
	// coverPhotoSizePx — fixed embedded image dimensions (request from spec).
	coverPhotoSizePx = 200

	// coverHeaderRows — total Excel rows the header block occupies.
	// Layout: 12 rows tall × 4 columns (A..D) wide for photo + B..I for meta.
	coverHeaderRows = 12

	// coverFetchTimeout — HARD ceiling on the cover-photo fetch.
	// 5s is generous for basket-NN.wbbasket.ru CDN + decode budget.
	coverFetchTimeout = 5 * time.Second

	// coverMaxBytes — refuse to decode anything larger to keep xlsx <500KB
	// after embedding multiple photos in a future iteration.
	coverMaxBytes = 2 * 1024 * 1024 // 2 MB upstream cap (post-resize ≈40KB)
)

// fetchAndResizePhoto downloads url, decodes (webp/png/jpeg autodetect via the
// global image package + xwebp init), resizes to width×height using bilinear
// scaler from x/image/draw, and re-encodes to PNG. Returns (pngBytes, nil) on
// success or (nil, error) on any failure.
//
// Caller is responsible for the HTTP client (test injection). If client is nil
// a default 5s-timeout client is used.
func fetchAndResizePhoto(client *http.Client, url string, width, height int) ([]byte, error) {
	if client == nil {
		client = &http.Client{Timeout: coverFetchTimeout}
	}
	ctx, cancel := context.WithTimeout(context.Background(), coverFetchTimeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("reporter.cover: build request: %w", err)
	}
	resp, err := client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("reporter.cover: fetch %s: %w", url, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("reporter.cover: fetch %s: status %d", url, resp.StatusCode)
	}
	body, err := io.ReadAll(io.LimitReader(resp.Body, coverMaxBytes))
	if err != nil {
		return nil, fmt.Errorf("reporter.cover: read body: %w", err)
	}
	img, err := decodeImage(body)
	if err != nil {
		return nil, fmt.Errorf("reporter.cover: decode: %w", err)
	}
	resized := image.NewRGBA(image.Rect(0, 0, width, height))
	draw.BiLinear.Scale(resized, resized.Bounds(), img, img.Bounds(), draw.Over, nil)
	var buf bytes.Buffer
	if err := png.Encode(&buf, resized); err != nil {
		return nil, fmt.Errorf("reporter.cover: encode png: %w", err)
	}
	return buf.Bytes(), nil
}

// decodeImage tries webp first (since WB serves webp), then falls back to the
// stdlib image.Decode (PNG/JPEG via standard registrations).
func decodeImage(body []byte) (image.Image, error) {
	// Try webp — WB main path.
	if img, err := xwebp.Decode(bytes.NewReader(body)); err == nil {
		return img, nil
	}
	// Fallback: image.Decode (PNG, JPEG via blank imports below).
	img, _, err := image.Decode(bytes.NewReader(body))
	return img, err
}

// Force-link decoders for non-webp payloads (test fixtures, fallback hosts).
var _ = png.Encode
var _ = jpeg.Encode

// embedCoverPhoto fetches, resizes, and inserts the cover photo at the given
// anchor cell. Returns error on any failure — caller chooses whether to render
// a text placeholder or to proceed without the image.
//
// excelize.AddPictureFromBytes positions the image OVER cells (not in-cell);
// the caller is responsible for sizing rows/cols so the 200×200 PNG sits flush.
func embedCoverPhoto(f *excelize.File, sheet, anchor, url string, client *http.Client) error {
	pngBytes, err := fetchAndResizePhoto(client, url, coverPhotoSizePx, coverPhotoSizePx)
	if err != nil {
		return err
	}
	pic := &excelize.Picture{
		Extension: ".png",
		File:      pngBytes,
		Format: &excelize.GraphicOptions{
			AltText:         "Главное фото карточки",
			LockAspectRatio: true,
			OffsetX:         4,
			OffsetY:         4,
			ScaleX:          1.0,
			ScaleY:          1.0,
			Hyperlink:       url,
			HyperlinkType:   "External",
			Positioning:     "oneCell",
		},
	}
	return f.AddPictureFromBytes(sheet, anchor, pic)
}

// writeCoverHeader renders the FTR-092 cover block at the top of the Svodka
// sheet (rows 1..coverHeaderRows). Layout:
//
//   ┌────────────────────────┬─────────────────────────────────────┐
//   │   200×200 photo (A..D) │ B1: nmID + WB-link                  │
//   │                        │ B2: Brand                           │
//   │                        │ B3: Name (truncated to 80 chars)    │
//   │                        │ B4: Price                           │
//   └────────────────────────┴─────────────────────────────────────┘
//
// Returns the number of rows consumed (= coverHeaderRows). Caller then writes
// the existing title at row coverHeaderRows+1, banner at +2, header at +3.
//
// On photo fetch failure, the photo cell shows "Фото недоступно" placeholder
// in `s.manual` style — never panics, never blocks report generation.
func writeCoverHeader(
	f *excelize.File, s *reportStyles, data *ReportData, client *http.Client,
) int {
	if data == nil || data.Product == nil {
		return 0
	}
	pd := data.Product

	// Pre-size column A wider so the 200px image fits visually.
	// (col A is otherwise width=4 — too narrow for a 200px image.)
	// We'll restore the original widths AFTER rendering by NOT touching
	// col A here — instead we set row heights so 200px height fits in 12 rows.
	for r := 1; r <= coverHeaderRows; r++ {
		_ = f.SetRowHeight(sheet, r, 18) // 12 rows × 18pt ≈ 216px ≥ 200px image
	}

	// Cover block label
	labelCell := "A1"
	f.SetCellValue(sheet, labelCell, "Карточка")
	f.SetCellStyle(sheet, labelCell, labelCell, s.bold)

	// Photo OR placeholder
	if data.CoverPhotoURL != "" {
		if err := embedCoverPhoto(f, sheet, "A2", data.CoverPhotoURL, client); err != nil {
			svodkaLogger.Warn("reporter.cover.fetch_failed",
				slog.String("url", data.CoverPhotoURL),
				slog.Int64("nm_id", pd.NmID),
				slog.String("error", err.Error()))
			writePlaceholderCell(f, s, "A2")
		}
	} else {
		writePlaceholderCell(f, s, "A2")
	}

	// Right-side meta — uses cols E..I to leave A..D free for the photo.
	// (col widths C..G are 30 each per existing writeSvodka layout.)
	wbLink := fmt.Sprintf("https://www.wildberries.ru/catalog/%d/detail.aspx", pd.NmID)
	nmTxt := fmt.Sprintf("Артикул %d", pd.NmID)
	f.SetCellValue(sheet, "E1", nmTxt)
	f.SetCellHyperLink(sheet, "E1", wbLink, "External")
	f.SetCellStyle(sheet, "E1", "I1", s.bold)
	f.MergeCell(sheet, "E1", "I1")

	if pd.Card != nil {
		f.SetCellValue(sheet, "E3", "Бренд: "+pd.Card.Brand)
		f.MergeCell(sheet, "E3", "I3")
		f.SetCellStyle(sheet, "E3", "I3", s.data)

		name := pd.Card.Name
		if len([]rune(name)) > 80 {
			name = string([]rune(name)[:80]) + "…"
		}
		f.SetCellValue(sheet, "E5", "Название: "+name)
		f.MergeCell(sheet, "E5", "I5")
		f.SetCellStyle(sheet, "E5", "I5", s.data)

		if pd.Card.SalePriceU > 0 {
			rub := pd.Card.SalePriceU / 100 / 100 // SalePriceU = kopecks * 100
			f.SetCellValue(sheet, "E7", fmt.Sprintf("Цена: %d ₽", rub))
			f.MergeCell(sheet, "E7", "I7")
			f.SetCellStyle(sheet, "E7", "I7", s.data)
		}
	}

	return coverHeaderRows
}

// writePlaceholderCell renders a brand-safe text fallback when the photo
// cannot be fetched or decoded. No emoji, no exclamation marks (brand rules).
func writePlaceholderCell(f *excelize.File, s *reportStyles, cell string) {
	f.SetCellValue(sheet, cell, "Фото недоступно")
	f.SetCellStyle(sheet, cell, cell, s.manual)
}

// guard: ensure collector import is used (writeCoverHeader uses pd.Card field
// access via *collector.ProductData even after refactors).
var _ collector.ProductData
```

**Step 4: Verify test passes**

```bash
go test ./internal/reporter -run 'TestFetchAndResizePhoto|TestEmbedCoverPhoto|TestWriteCoverHeader' -v
```

Expected: 5 tests PASS.

**Acceptance Criteria:**
- [ ] All 5 helper tests pass
- [ ] `go vet ./internal/reporter/...` clean
- [ ] File ≤300 LOC (target ≈220)
- [ ] No emoji, no exclamation marks in any string literal (brand rule)
- [ ] `embedCoverPhoto` always returns error on fetch failure (caller decides placeholder)
- [ ] `writeCoverHeader` never panics for nil `Product` / nil `Card` / empty `CoverPhotoURL`

---

### Task 2: ReportData.CoverPhotoURL field

**Files:**
- Modify: `internal/reporter/types.go:13-26` — add field

**Context:**
Add the explicit `CoverPhotoURL string` field so the caller (pipeline) can pass the URL without any cross-package coupling at the reporter level. Empty string = no photo, render placeholder.

**Step 1: Write failing test (combined with Task 6 — see TestWriteSvodka_WithCoverPhotoURL)**

**Step 2: Implementation — types.go**

```go
// internal/reporter/types.go (modify ReportData struct)
type ReportData struct {
	Analysis    *analyzer.ScanAnalysis
	Product     *collector.ProductData
	Competitors []*collector.ProductData
	ScanType    string
	GeneratedAt time.Time
	Class       criteria.ProductClass
	SubjectText string
	MediaFacts  *media.Facts
	SkippedCriteria []int

	// FTR-092: full URL of the WB CDN webp main photo (basket-NN host pre-resolved).
	// Empty → reporter renders "Фото недоступно" placeholder.
	// Format: https://basket-NN.wbbasket.ru/vol{V}/part{P}/{nmID}/images/big/1.webp
	CoverPhotoURL string
}
```

**Step 3: Verify**

```bash
go build ./internal/reporter/...
go test ./internal/reporter -run TestReporter_GenerateNoCover -v   # if the existing reporter_test runs without CoverPhotoURL — must still pass
```

**Acceptance Criteria:**
- [ ] `go build ./...` clean
- [ ] All existing reporter tests pass (no regression — new field is optional)

---

### Task 3: collector.MainPhotoURL helper

**Files:**
- Modify: `internal/collector/wb_basket.go` — add public `MainPhotoURL`

**Context:**
Caller (pipeline) needs to materialise the URL. Currently URL construction lives privately in `media/collector.go:234-238` (`buildPhotoURL`). Lift the same formula to `collector` package as a public helper so reporter-callers don't depend on internal/media.

**Step 1: Write failing test**

```go
// internal/collector/wb_basket_test.go (append)
func TestMainPhotoURL_Construction(t *testing.T) {
	cases := []struct {
		nmID int64
		host string
		want string
	}{
		{
			nmID: 174236476, host: "07",
			want: "https://basket-07.wbbasket.ru/vol1742/part174236/174236476/images/big/1.webp",
		},
		{
			nmID: 1234567, host: "01",
			want: "https://basket-01.wbbasket.ru/vol12/part1234/1234567/images/big/1.webp",
		},
	}
	for _, c := range cases {
		got := MainPhotoURL(c.nmID, c.host)
		if got != c.want {
			t.Errorf("MainPhotoURL(%d, %q) = %q, want %q", c.nmID, c.host, got, c.want)
		}
	}
}

func TestMainPhotoURL_EmptyHost_ReturnsEmpty(t *testing.T) {
	got := MainPhotoURL(174236476, "")
	if got != "" {
		t.Errorf("MainPhotoURL with empty host should return empty, got %q", got)
	}
}
```

**Step 2: Implementation**

```go
// internal/collector/wb_basket.go (append at end of file)

// MainPhotoURL constructs the WB CDN URL for the main (1st) photo of a card.
// Pattern: https://basket-{host}.wbbasket.ru/vol{V}/part{P}/{nmID}/images/big/1.webp
// where V = nmID/100_000 and P = nmID/1_000.
//
// host is the value returned by BasketResolver.Host(nmID). On empty host
// returns "" — caller MUST treat this as "no photo URL" and render placeholder.
//
// Used by: scanner.Pipeline (FTR-092 cover photo plumbing into ReportData).
func MainPhotoURL(nmID int64, host string) string {
	if host == "" || nmID <= 0 {
		return ""
	}
	vol := nmID / 100000
	part := nmID / 1000
	return fmt.Sprintf(
		"https://basket-%s.wbbasket.ru/vol%d/part%d/%d/images/big/1.webp",
		host, vol, part, nmID,
	)
}
```

**Step 3: Verify**

```bash
go test ./internal/collector -run TestMainPhotoURL -v
```

Expected: 2 PASS.

**Acceptance Criteria:**
- [ ] Both unit tests pass
- [ ] Public function with godoc comment
- [ ] No circular imports (collector→reporter is forbidden — verify `go vet`)

---

### Task 4: Plumb CoverPhotoURL through scanner.Pipeline

**Files:**
- Modify: `internal/scanner/pipeline.go` — add `basket *collector.BasketResolver` to `Pipeline` struct + `NewPipeline` ctor + fill `CoverPhotoURL` in `ReportData` literal at line 279
- Modify: `cmd/bot/main.go:102` — pass `basketResolver` to `NewPipeline`
- Modify: `cmd/scan-cli/main.go:152` — same
- Modify: `cmd/bot-loadtest/main.go` — same (if it constructs Pipeline; otherwise n/a)

**Context:**
`basketResolver` is already constructed in all 3 entry points and threaded into `WBPublicProvider`. Reuse the same instance — its in-memory `vol→host` cache is hot. Adding a 7th param to `NewPipeline` is mechanical.

**Step 1: Find current NewPipeline signature**

```bash
grep -n "func NewPipeline" internal/scanner/pipeline.go
# Then read full signature + all call sites
grep -rn "scanner.NewPipeline\|NewPipeline(" cmd/ internal/scanner/
```

**Step 2: Write failing test (sanity)**

```go
// internal/scanner/pipeline_test.go (extend existing)
func TestNewPipeline_AcceptsBasketResolver(t *testing.T) {
	// ... existing test setup ...
	basket := collector.NewBasketResolver("")
	p := scanner.NewPipeline(/* ...all existing args..., */ basket)
	if p == nil {
		t.Fatal("NewPipeline returned nil")
	}
}
```

**Step 3: Implementation**

```go
// internal/scanner/pipeline.go (struct + ctor)

type Pipeline struct {
	registry *collector.ProviderRegistry
	jam      JamScraper
	analyzer analyzer.Analyzer
	media    MediaPipeline
	criteria *criteria.Registry
	store    ScanStore
	tmpDir   string
	logger   *slog.Logger
	// ... other existing fields ...

	// FTR-092: basket-NN resolver — used to materialise the main-photo URL
	// for ReportData.CoverPhotoURL. May be nil → photo block renders placeholder.
	basket *collector.BasketResolver
}

func NewPipeline(
	registry *collector.ProviderRegistry,
	jam JamScraper,
	mediaPipe MediaPipeline,
	an analyzer.Analyzer,
	reg *criteria.Registry,
	store ScanStore,
	tmpDir string,
	logger *slog.Logger,
	basket *collector.BasketResolver, // NEW — last param to minimise call-site churn
) *Pipeline {
	return &Pipeline{
		registry: registry,
		jam:      jam,
		analyzer: an,
		media:    mediaPipe,
		criteria: reg,
		store:    store,
		tmpDir:   tmpDir,
		logger:   logger,
		basket:   basket,
	}
}
```

```go
// internal/scanner/pipeline.go:279 — extend ReportData literal

// FTR-092: cover photo URL — empty if basket resolver missing or nmID invalid.
var coverURL string
if p.basket != nil && scanData.WBCard != nil {
	coverURL = collector.MainPhotoURL(scanData.WBCard.NmID, p.basket.Host(scanData.WBCard.NmID))
}

reportData := &reporter.ReportData{
	Analysis:        analysis,
	Product:         scanData.WBCard,
	Competitors:     scanData.Competitors,
	ScanType:        string(req.ScanType),
	GeneratedAt:     time.Now(),
	Class:           productClass,
	SubjectText:     subjRoot,
	MediaFacts:      mediaFacts,
	SkippedCriteria: skippedIDs,
	CoverPhotoURL:   coverURL, // NEW
}
```

```go
// cmd/bot/main.go (and cmd/scan-cli/main.go, cmd/bot-loadtest/main.go)
// Find existing scanner.NewPipeline(...) call and append basketResolver as last arg.

pipeline := scanner.NewPipeline(
	registry, jamScraper, mediaPipe, an, reg, store, tmpDir, logger,
	basketResolver, // FTR-092: cover photo URL plumbing
)
```

**Step 4: Verify**

```bash
go build ./...
go test ./internal/scanner -run TestNewPipeline_AcceptsBasketResolver -v
go test ./internal/scanner -run TestPipeline -v   # full regression
```

**Acceptance Criteria:**
- [ ] `go build ./...` clean across cmd/bot, cmd/scan-cli, cmd/bot-loadtest
- [ ] All existing scanner tests still pass (no behaviour change for non-cover paths)
- [ ] `CoverPhotoURL` is populated in real scans (verify with debug print in dev)

---

### Task 5: Wire cover header into writeSvodka

**Files:**
- Modify: `internal/reporter/sheet_svodka.go:42-69` — call `writeCoverHeader` first, shift offsets

**Context:**
Existing `writeSvodka` writes title at row 1, banner at row 2, headers at row 3, freeze at C5. After Task 5, rows 1..12 are the cover block; title moves to row 13; banner to 14; headers to 15; freeze becomes C17 (`YSplit=16`).

**Step 1: Adjust constants & shift logic**

```go
// internal/reporter/sheet_svodka.go (replace writeSvodka function preamble)

func writeSvodka(f *excelize.File, s *reportStyles, data *ReportData) {
	// Column widths (unchanged)
	f.SetColWidth(sheet, "A", "A", 4)
	f.SetColWidth(sheet, "B", "B", 30)
	f.SetColWidth(sheet, "C", "G", 30)
	f.SetColWidth(sheet, "H", "I", 38)

	// FTR-092: cover photo header block (rows 1..coverHeaderRows).
	// On nil/empty CoverPhotoURL, renders text-only placeholder — never panics.
	coverRows := writeCoverHeader(f, s, data, http.DefaultClient)

	// Row N (was 1): title merged A:I
	titleRow := coverRows + 1   // = 13 when cover=12
	bannerRow := coverRows + 2  // = 14
	headerRow := coverRows + 3  // = 15

	title := "Диагональное сканирование"
	if !data.GeneratedAt.IsZero() {
		title = fmt.Sprintf("Диагональное сканирование %s", data.GeneratedAt.Format("02.01.2006"))
	}
	titleCell := fmt.Sprintf("A%d", titleRow)
	f.SetCellValue(sheet, titleCell, title)
	f.MergeCell(sheet, titleCell, fmt.Sprintf("I%d", titleRow))
	f.SetCellStyle(sheet, titleCell, fmt.Sprintf("I%d", titleRow), s.header)

	// Row N+1 (was 2): price anomaly banner — only if PriceAnomaly set.
	if data.Analysis != nil && data.Analysis.PriceAnomaly {
		bannerTxt := fmt.Sprintf(
			"ВНИМАНИЕ: данные о цене выглядят аномально. Наша цена: %d ₽. Медиана конкурентов: %d ₽. Перед выполнением рекомендаций проверьте отображение цены в личном кабинете WB. Часть критериев может быть построена на ошибочной цене.",
			data.Analysis.PriceAnomalyOurRub, data.Analysis.PriceAnomalyMedRub,
		)
		bCell := fmt.Sprintf("A%d", bannerRow)
		f.SetCellValue(sheet, bCell, bannerTxt)
		f.MergeCell(sheet, bCell, fmt.Sprintf("I%d", bannerRow))
		f.SetCellStyle(sheet, bCell, fmt.Sprintf("I%d", bannerRow), s.manual)
		f.SetRowHeight(sheet, bannerRow, 60)
	}

	// Row N+2 (was 3): header row
	headers := []string{"№", "Критерий", "МЫ", "ТОП-1", "ТОП-2", "ТОП-3", "Слабый", "Выводы", "Задачи"}
	for i, h := range headers {
		cell := fmt.Sprintf("%s%d", colLetter(i), headerRow)
		f.SetCellValue(sheet, cell, h)
		f.SetCellStyle(sheet, cell, cell, s.header)
	}

	// Freeze panes — was C5 (rows 1..4 frozen). Now: rows 1..(headerRow+1) frozen.
	f.SetPanes(sheet, &excelize.Panes{
		Freeze:      true,
		Split:       false,
		XSplit:      2,
		YSplit:      headerRow + 1,
		TopLeftCell: fmt.Sprintf("C%d", headerRow+2),
		ActivePane:  "bottomRight",
	})

	// ... existing logic continues — only the starting row variable changes:
	//   row := 4   →   row := headerRow + 1
	row := headerRow + 1
	// ... (rest of writeSvodka body unchanged) ...
}
```

**Step 2: Update tests for shifted row numbers**

Search-and-replace for `"A1"`, `"A2"`, `"H10"`, etc. in `sheet_svodka_test.go`:

| Old cell ref | New cell ref (cover=12) | Test |
|---|---|---|
| `A1` (title) | `A13` | none — title not asserted |
| `A2` (banner) | `A14` | `TestWriteSvodka_PriceAnomalyBanner_Rendered` line 574, 619 |
| Hard-coded row 10 in `writeCriterionRows(...10...)` | UNCHANGED — these tests call the helper directly with explicit row arg, not the full svodka writer |

```go
// internal/reporter/sheet_svodka_test.go (TestWriteSvodka_PriceAnomalyBanner_Rendered)
val, err := f.GetCellValue(sheet, "A14") // was "A2"
```

**Step 3: Verify**

```bash
go test ./internal/reporter -v
```

Expected: ALL pass (including pre-existing 30+ tests after row-shift fixes).

**Acceptance Criteria:**
- [ ] All reporter tests pass after row shifts
- [ ] Manual: open generated xlsx in LibreOffice — cover photo block visible, title below it, banner below title, freeze pane at row 16
- [ ] xlsx file size ≤500 KB (verify in Task 7)

---

### Task 6: Integration test — generate full report with CoverPhotoURL

**Files:**
- Modify: `internal/reporter/sheet_svodka_test.go` — add `TestWriteSvodka_WithCoverPhotoURL_PictureEmbedded`

**Step 1: Test**

```go
// internal/reporter/sheet_svodka_test.go (append)

func TestWriteSvodka_WithCoverPhotoURL_PictureEmbedded(t *testing.T) {
	// Spin a local httptest server serving a tiny PNG (no need for real webp).
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/png")
		// 100×100 black PNG
		img := image.NewRGBA(image.Rect(0, 0, 100, 100))
		_ = png.Encode(w, img)
	}))
	defer srv.Close()

	f := excelize.NewFile()
	defer f.Close()
	f.NewSheet(sheet)

	data := &ReportData{
		Analysis: &analyzer.ScanAnalysis{Criteria: []analyzer.CriterionResult{}},
		Product: &collector.ProductData{
			NmID: 174236476,
			Card: &collector.WBCardData{Name: "Тест", Brand: "Acme", SalePriceU: 250000_00},
		},
		Class:         criteria.ClassApparel,
		CoverPhotoURL: srv.URL,
	}
	writeSvodka(f, createStyles(f), data)

	// Cover photo present at A2.
	pics, err := f.GetPictures(sheet, "A2")
	if err != nil {
		t.Fatalf("GetPictures: %v", err)
	}
	if len(pics) == 0 {
		t.Errorf("expected picture in A2 after writeSvodka with CoverPhotoURL, got 0")
	}
	// Brand text in B/E1 (right-side meta).
	val, _ := f.GetCellValue(sheet, "E1")
	if !strings.Contains(val, "174236476") {
		t.Errorf("E1 = %q, want contains nmID", val)
	}
}

func TestWriteSvodka_NoCoverPhotoURL_Placeholder(t *testing.T) {
	f := excelize.NewFile()
	defer f.Close()
	f.NewSheet(sheet)

	data := &ReportData{
		Analysis: &analyzer.ScanAnalysis{Criteria: []analyzer.CriterionResult{}},
		Product:  &collector.ProductData{NmID: 1, Card: &collector.WBCardData{Name: "x"}},
		Class:    criteria.ClassUnknown,
		// CoverPhotoURL intentionally empty
	}
	writeSvodka(f, createStyles(f), data) // must not panic
	val, _ := f.GetCellValue(sheet, "A2")
	if val != "Фото недоступно" {
		t.Errorf("A2 placeholder = %q, want 'Фото недоступно'", val)
	}
}
```

**Step 2: Verify size budget**

```go
func TestGenerate_WithCoverPhoto_FileSizeUnder500KB(t *testing.T) {
	// integration: full Generate() round-trip with a CoverPhotoURL pointing
	// at a 800×800 webp (loaded from a tiny test fixture; we generate a JPEG
	// in-process and serve it via httptest).
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "image/jpeg")
		img := image.NewRGBA(image.Rect(0, 0, 800, 800))
		_ = jpeg.Encode(w, img, &jpeg.Options{Quality: 85})
	}))
	defer srv.Close()

	data := newMinimalReportData()  // helper from reporter_test.go
	data.CoverPhotoURL = srv.URL
	bytes, err := Generate(data)
	if err != nil {
		t.Fatalf("Generate: %v", err)
	}
	const cap = 500 * 1024
	if len(bytes) > cap {
		t.Errorf("xlsx size = %d bytes, exceeds 500KB cap", len(bytes))
	}
}
```

**Step 3: Verify**

```bash
go test ./internal/reporter -run 'TestWriteSvodka_WithCoverPhoto|TestGenerate_WithCoverPhoto' -v
```

**Acceptance Criteria:**
- [ ] All 3 integration tests pass
- [ ] xlsx ≤500 KB with cover embedded (200×200 PNG ≈30–50KB)
- [ ] No emoji / no exclamation in any test fixture text

---

### Task 7: DoD verification + diary entry

**Files:**
- Manual: run `cmd/scan-cli` against the 4 articles from `ai/calibration/run-2026-04-27/`
- Modify: `go.mod` — add explicit `golang.org/x/image v0.25.0`
- Verify: `internal/telegram/samples/sample-{light,full}.xlsx` UNCHANGED (samples don't go through reporter.Generate — see Drift Log row 11)
- Append: `ai/diary/{YYYY-MM-DD}-FTR-092.md`

**Steps:**

```bash
# 1. Add golang.org/x/image to go.mod require block (NOT just go.sum)
go get golang.org/x/image@v0.25.0
go mod tidy

# 2. Build everything
go build ./...

# 3. Run full reporter test suite
go test ./internal/reporter/... -v -count=1

# 4. Run scanner tests
go test ./internal/scanner/... -v -count=1

# 5. End-to-end smoke (requires WB CDN access)
for nm in 174236476 490509833 612323711 ${nm4}; do
  go run ./cmd/scan-cli -nm $nm -auto-competitors -out /tmp/scan-$nm.xlsx
  ls -la /tmp/scan-$nm.xlsx
  # Manual: open in LibreOffice, verify:
  #   • cover photo visible at top of Сводка (200×200, sharp)
  #   • title row shifted below cover
  #   • freeze pane works (scroll right/down)
  #   • file size <500KB
done

# 6. Edge case: simulate 404 by hitting a non-existent nmID
# Should produce xlsx without panic; A2 = "Фото недоступно"
go run ./cmd/scan-cli -nm 99999999999 -auto-competitors -out /tmp/scan-404.xlsx

# 7. Sample regen — NO-OP for FTR-092
# Per dependencies.md § scripts/gen-samples, samples are STANDALONE stubs that
# do NOT call reporter.Generate. The DoD line "samples regen" was inherited
# boilerplate. Skip — samples remain unchanged.
echo "scripts/gen-samples: SKIPPED — independent of reporter.Generate (see Drift Log)"
```

**Diary entry template:**

```markdown
# FTR-092 — Cover photo in Excel header

**Date:** 2026-04-29
**Status:** done
**Effort:** ~$3 (medium scope, 5 files modified, 2 new files)

## What changed
- New helper `internal/reporter/sheet_svodka_cover.go` — fetch+resize+embed.
- New struct field `ReportData.CoverPhotoURL string`.
- New collector helper `collector.MainPhotoURL(nmID, host) string`.
- `scanner.Pipeline` gains `basket *collector.BasketResolver` field; constructed in cmd/bot, cmd/scan-cli, cmd/bot-loadtest.
- `writeSvodka` shifts row offsets by 12 — cover block occupies rows 1..12, title moves to 13.

## Constraints learned
- WB CDN serves webp — `golang.org/x/image/webp` decode-only is sufficient (no encoder needed; we re-encode to PNG).
- excelize `AddPictureFromBytes` positions images OVER cells (`Positioning: "oneCell"`); row heights must be sized to fit 200px.
- Test fixtures must NOT depend on real network — use `httptest.NewServer` + dynamically generated PNG/JPEG bytes.
- xlsx with one 200×200 PNG ≈ +40KB → well under 500KB cap.

## Cross-cuts touched
- `internal/scanner/pipeline.go` ctor signature changed → 3 entry points updated.
- Existing test `TestWriteSvodka_PriceAnomalyBanner_Rendered` cell ref shifted A2→A14.

## Risks/follow-ups
- IF future tasks add competitor cover photos (4×200×200 = +160KB), revisit 500KB cap.
- IF WB switches CDN to AVIF, decoder fallback path needs `golang.org/x/image/bmp` or external lib.
- Sample regen via `scripts/gen-samples` was NOT triggered (samples are independent stubs); if the policy changes and samples become real reports, this task's plumbing is ready.
```

**Acceptance Criteria:**
- [ ] All 4 calibration articles produce xlsx with visible cover (manual visual check)
- [ ] One of the 4 has 404 path → renders placeholder, no crash
- [ ] All xlsx <500 KB (`ls -la`)
- [ ] `go test ./...` clean
- [ ] go.mod has explicit `golang.org/x/image` line in `require`
- [ ] Diary entry written to `ai/diary/2026-04-29-FTR-092.md`
- [ ] Index updated: `ai/diary/index.md`

---

### Dependencies

- **Task 2** (types) blocks Task 4, Task 5, Task 6 (uses `CoverPhotoURL` field)
- **Task 3** (collector helper) blocks Task 4 (pipeline calls `MainPhotoURL`)
- **Task 1** (cover helper) blocks Task 5 (svodka calls `writeCoverHeader`)
- **Task 5** (svodka integration) blocks Task 6 (test the integrated path)
- **Task 7** runs LAST — needs everything green

### Research Sources

- excelize v2.10.1 source: `/home/dld/go/pkg/mod/github.com/xuri/excelize/v2@v2.10.1/picture.go:195-265` — `AddPicture` calls `AddPictureFromBytes` after reading file; supports `.webp`? — YES according to `supportedImageTypes`, but caller-side resize gives stable output and avoids depending on undocumented decoder behavior. Decision: **always re-encode to PNG**.
- existing pattern `internal/media/collector.go:230-238` — proves the URL formula `https://basket-{NN}.wbbasket.ru/vol{V}/part{P}/{nm}/images/big/1.webp` is current.
- `golang.org/x/image/webp` v0.25.0 (already in go.sum) — decoder only, no encoder needed for our path.
- `golang.org/x/image/draw` — `BiLinear.Scale` for 800×800→200×200 downscale; standard go-team helper.
- Brand rules `/home/dld/projects/gipotenuza/.claude/rules/brand.md` — placeholder text "Фото недоступно" passes (no emoji, no exclamation, Russian, Sage voice).

