---
name: reflect
description: Analyze diary entries and create spec with proposed CLAUDE.md improvements
model: opus
---

# Reflect — Синтез дневника в правила

Анализирует diary entries и создаёт spec с предложениями для CLAUDE.md.

**Активация:** `/reflect`, "рефлексия", "давай разберём дневник"

---

## Терминология

| Действие | Триггеры | Что происходит |
|----------|----------|----------------|
| **Запись в дневник** | "запиши в дневник", "сохрани в дневник", "запомни для дневника" | Новая строка в index.md + файл |
| **Синтез (этот скилл)** | "/reflect", "рефлексия", "давай разберём дневник" | Анализ -> spec -> claude-md-writer |

---

## Когда использовать

- После 5+ pending entries в дневнике
- Еженедельное обслуживание
- После серии похожих багов
- Перед крупной работой (освежить память)

---

## Process

### Step 1: Читай индекс дневника

```bash
cat ai/diary/index.md
```

Найди все записи со статусом `pending`.

### Step 2: Читай pending entries

Для каждой pending записи — открой файл и проанализируй.

### Step 3: Анализируй паттерны

| Pattern Type | Threshold | Action |
|--------------|-----------|--------|
| User preference | 2+ | Consider adding |
| User preference | 3+ | **MUST** add to CLAUDE.md |
| Failure pattern | 2+ | Add as anti-pattern |
| Design decision | 3+ | Add as guideline |
| Tool/workflow | 2+ | Consider adding |

### Step 4: Проверь существующие правила

Сравни entries с CLAUDE.md:
- Rule violated? -> Усилить формулировку
- Rule helped? -> Оставить
- Rule outdated? -> Обновить или убрать

### Step 5: Создай spec (НЕ прямые правки!)

**КРИТИЧНО:** Никогда не редактируй CLAUDE.md напрямую! Создай spec.

**Расположение:** `ai/features/TECH-NNN-YYYY-MM-DD-reflect-synthesis.md`

**Формат:**

```markdown
# TECH-NNN: Reflect Diary Synthesis — [Month Year]

**Status:** queued | **Priority:** P2 | **Date:** YYYY-MM-DD

## Context
- Entries analyzed: [list from index.md]
- Period: [date range]

## Findings

### Patterns Found (threshold 2+ = MUST add)
| Pattern | Frequency | Source | Action |

### Anti-Patterns Found
| Anti-Pattern | Frequency | Source | Action |

### User Preferences Found
| Preference | Frequency | Source | Action |

## Proposed Changes

### 1. CLAUDE.md — [Section]
**Add/Update:**
```markdown
[exact content to add]
```

## Allowed Files
| File | Change Type |
|------|-------------|
| `CLAUDE.md` | Update |
| `.claude/rules/*.md` | Update (if needed) |

## Definition of Done
- [ ] `claude-md-writer` applied changes
- [ ] CLAUDE.md < 200 lines after changes
- [ ] Diary entries marked as done in index.md

## Integration
**Next step:** Run `/claude-md-writer` with this spec as input.

## After Integration
Update diary entries status in index.md:
```bash
# For each processed entry, change status from pending to done
```
```

### Step 6: Вывод

```yaml
entries_analyzed: N
patterns_found:
  - "Pattern 1"
  - "Pattern 2"
spec_created: ai/features/TECH-NNN-....md
next_action: "Run /claude-md-writer to integrate"
```

---

## Что НЕ делать

| Неправильно | Правильно |
|-------------|-----------|
| Редактировать CLAUDE.md напрямую | Создать spec -> claude-md-writer |
| Редактировать .claude/rules напрямую | Создать spec -> claude-md-writer |
| Помечать entries done до интеграции | Пометить после claude-md-writer |

---

## После claude-md-writer

1. Открой `ai/diary/index.md`
2. Для каждой обработанной записи измени status: `pending` -> `done`
3. Обнови timestamp:

```bash
date +%s > ai/diary/.last_reflect
```

---

## Quality Checklist

Перед завершением reflect:

- [ ] Все pending entries проанализированы
- [ ] Паттерны посчитаны корректно (frequency threshold)
- [ ] Spec создан (не прямые правки)
- [ ] Spec содержит "Proposed Changes" секцию
- [ ] Next action = "run claude-md-writer"
