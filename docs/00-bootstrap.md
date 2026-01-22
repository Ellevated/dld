# Step 0: Bootstrap

## Философия

Эти принципы — результат сотен часов проб и ошибок. Они работают, потому что:

1. **LLM понимает структуру** — colocation, flat, self-describing names
2. **Guardrails предотвращают хаос** — CI checks, immutable tests
3. **Skills дают workflow** — не думаешь "что делать дальше"

Но принципы бесполезны без понимания **что строишь**.

---

## Порядок запуска нового проекта

```
Step 0: Прочитай этот файл (5 мин)
     ↓
Step 1: /bootstrap — распаковка идеи с Claude (60-90 мин)
     ↓
     → ai/idea/vision.md
     → ai/idea/domain-context.md
     → ai/idea/product-brief.md
     → ai/idea/architecture.md
     ↓
Day 1: Структура проекта (09-onboarding.md)
     ↓
Day 2+: /spark для первой фичи
```

---

## Чеклист "Готов к /bootstrap"

- [ ] Есть идея (хотя бы смутная)
- [ ] Создал пустую папку проекта
- [ ] Скопировал `ai/principles/` в проект
- [ ] Запустил Claude Code в папке проекта
- [ ] Готов потратить 60-90 минут на честный разговор

---

## Что делает /bootstrap

**Это НЕ анкета.** Это интерактивная сессия с продуктовым партнёром.

| Фаза | Что происходит | Кто ведёт |
|------|----------------|-----------|
| 0. Фаундер | Мотивации, опыт, ограничения | Claude спрашивает |
| 1-4. Идея | Персона, боль, решение | Claude копает вглубь |
| 5-6. Бизнес | Деньги, конкуренты, advantage | Совместно |
| 7-8. Scope | MLP, словарь терминов | Claude режет лишнее |
| 9. Synthesis | Проверка понимания | Claude суммирует |
| 10. Архитектура | Домены, зависимости | **Claude предлагает** |
| 11. Документация | 4 файла | Claude создаёт |

**Ключевое:** Claude будет "душным" — уточнять размытое, возвращаться к противоречиям, не пропускать "мелочи".

---

## Результат /bootstrap

```
ai/idea/
├── vision.md           # Зачем проект, фаундер, успех
├── domain-context.md   # Отрасль, персона, словарь
├── product-brief.md    # MLP, scope, монетизация, assumptions
└── architecture.md     # Домены, зависимости, entry points
```

---

## Чеклист "Готов к Day 1"

После `/bootstrap` у тебя должны быть:

- [ ] **vision.md** — понятно зачем делаем
- [ ] **domain-context.md** — понятен мир и персона
- [ ] **product-brief.md** — понятен MLP scope (3-5 фич)
- [ ] **architecture.md** — понятны домены (3-5 шт)
- [ ] North Star metric определена
- [ ] Assumptions записаны
- [ ] Жёлтые флаги зафиксированы

**Не готов если:**
- "Для всех" — нет конкретной персоны
- "Всё нужно" — нет приоритизации
- "Потом разберёмся" — критичные unknowns не зафиксированы

---

## После bootstrap: Day 1

```bash
# 1. Создать структуру по architecture.md
mkdir -p src/domains/{domain1,domain2,domain3}
mkdir -p src/{shared,infra,api}
mkdir -p .claude/{contexts,skills}
mkdir -p tests/{integration,contracts,regression}

# 2. Создать CLAUDE.md из ai/idea/* файлов
# (Claude поможет на основе 04-claude-md-template.md)

# 3. Создать backlog
touch ai/backlog.md

# 4. Первая фича
/spark {первая фича из architecture.md}
```

---

## Минимальный набор для копирования в новый проект

```
ai/
├── principles/          # Скопировать целиком
└── idea/               # Создаст /bootstrap
    ├── vision.md
    ├── domain-context.md
    ├── product-brief.md
    └── architecture.md

.claude/
├── skills/             # Скопировать из principles/skills/
│   └── bootstrap/SKILL.md
└── settings.json       # Настроить
```

---

## Что читать из principles

**Перед /bootstrap (5 мин):**
- Этот файл

**После /bootstrap, перед Day 1 (15 мин):**
- `01-principles.md` — понять философию
- `03-project-structure.md` — понять структуру
- `09-onboarding.md` — чеклист Day 1-4

**По мере необходимости:**
- Остальные документы — reference material
