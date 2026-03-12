# Architecture: DLD GitHub Launch

**Дата:** 2026-01-22

---

## Домены подготовки

### `structure` — Чистка и консистентность
- Template без хардкода (MCP, hooks)
- Рефакторинг autopilot.md
- GitHub templates
- LICENSE, CONTRIBUTING, CODE_OF_CONDUCT

### `content` — Документация EN
- Перевод 20 docs
- Hero README
- COMPARISON.md, FAQ.md
- Launch posts

### `examples` — Real-world кейсы
- Marketplace launch
- AI autonomous company
- Content factory

### `branding` — Визуалы
- Comparison table image
- Workflow diagram
- Badges, og:image

---

## Граф зависимостей

```
structure → content + examples → branding → LAUNCH
```

---

## Структура репозитория

```
dld/
├── README.md           # Hero
├── LICENSE             # MIT
├── CONTRIBUTING.md
├── COMPARISON.md
├── FAQ.md
├── docs/               # 20 files EN
├── examples/           # 3 projects
├── template/           # Ready to copy
│   ├── .claude/skills/
│   ├── .claude/agents/
│   ├── ai/
│   └── CLAUDE.md
└── .github/            # Issue templates
```

---

## Timeline (7 дней)

**Day 1-2:** Structure (6h)
**Day 3-4:** Content (8h)
**Day 5:** Examples (3h)
**Day 6:** Branding (2h)
**Day 7:** Launch (1h)

---

## Launch Channels

1. **HackerNews** (Show HN) — приоритет #1
2. **Вайб-кодеры** Telegram — 1K прогретая аудитория
3. **Reddit** — r/ClaudeAI, r/programming, r/opensource
4. **Twitter/X** — thread с визуалами
5. **LinkedIn** — личный пост
6. **Dev.to** — longform article

---

## Comparison Prompt (killer feature)

```
Analyze DLD methodology (github.com/you/dld) and compare
it with my current skills setup. Which approach will write
better code and help scale my LLM-powered project?
```

---

## Критерии готовности

- [ ] Репо публичный
- [ ] Template работает без ошибок
- [ ] Comparison prompt убедителен
- [ ] Docs консистентны
- [ ] Examples показательны
- [ ] Launch content готов
