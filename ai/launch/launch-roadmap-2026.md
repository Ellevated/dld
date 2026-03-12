# DLD Launch Roadmap 2026

> Исследование лучших практик open source launch (Feb 2026)
> Источники: Exa MCP + Sequential Thinking analysis

---

## Ключевые источники

| Источник | Результат | Ключевой инсайт |
|----------|-----------|-----------------|
| **Calmops Guide** (Dec 2025) | 500+ upvotes formula | Timing: Вт-Чт, 8-10 AM PT |
| **Bob Singor** (Aug 2025) | #1 HN, 500+ stars/24h | "Overdeliver" стратегия |
| **Rybbit** (May 2025) | 5000 stars/9 дней | r/SideProject + r/selfhosted = #1 hot |
| **Flo Merian** (Dec 2025) | 200+ PH launches | Hunter + первые 4 часа критичны |
| **Arc.dev** | #1 Product of Day | 26 запусков до успеха |

---

## Оптимальная стратегия: 3 волны

### Волна 1: Soft Launch (День 1-2)

**Цель:** Feedback + testimonials

| Платформа | Время | Что делать |
|-----------|-------|------------|
| **Twitter/X** | Утро | Тред 5-7 твитов с GIF |
| **r/SideProject** | +2 часа | Story-first пост |
| **r/ClaudeAI** | +1 день | Technical deep-dive |

---

### Волна 2: Main Launch — Hacker News (День 3-4)

**Цель:** Maximum visibility

```
TIMING: Вторник-Четверг, 8:00 AM PT (19:00 MSK)
```

#### Первые 2 часа определяют ВСЁ

| Время | Действие |
|-------|----------|
| 0:00 | Пост появляется |
| 0:05 | First comment (ОБЯЗАТЕЛЬНО!) |
| 0:10 | Оповести 10-15 людей (НЕ просить upvotes!) |
| 0:30 | Первые ответы на комменты |
| 2:00 | Рейтинг стабилизируется |

#### Title formula

```
Show HN: DLD – Turn Claude Code into an autonomous developer
```

Альтернативы:
- `Show HN: DLD – From 90% debugging to 90% building with AI`
- `Show HN: DLD – Architecture patterns for predictable AI coding`

#### First comment template (≤800 символов)

```
Hi HN! After a year of AI coding, I tracked my time: 90% debugging,
6% features. The issue wasn't the LLM — it was architecture.

DLD is a methodology that fixes this:
• Spec-first: AI writes spec before touching code
• Worktree isolation: each task = clean git worktree
• Fresh context per task: no hallucinations from previous sessions
• Domain-driven: max 400 LOC files, explicit dependencies

Try it: npx create-dld my-project
Live demo: [GIF in README]
GitHub: https://github.com/Ellevated/dld

Built over 6 months of production use. Happy to answer questions!
```

---

### Волна 3: Sustained Growth (Неделя 2+)

**Цель:** Long-term awareness

| День | Платформа | Формат |
|------|-----------|--------|
| +7 | **Product Hunt** | Найти Hunter'а заранее! |
| +9 | **r/programming** | Technical article |
| +11 | **Dev.to** | "How I built..." story |
| +14 | **r/MachineLearning** | AI-focused angle |

---

## Бенчмарки успеха

| Метрика | Хороший результат | Отличный результат |
|---------|-------------------|-------------------|
| HN upvotes | 100+ | 400+ |
| GitHub stars (24h) | 200+ | 500+ |
| HN comments | 50+ | 100+ |
| Traffic spike | 5,000 | 15,000+ |
| PH ranking | Top 10 | Top 3 |

---

## Критические ошибки (избегать!)

| Ошибка | Почему плохо |
|--------|--------------|
| Просить upvotes | HN flags мгновенно, пост исчезает |
| Координировать voting | Детектится, бан |
| Hype в title | "Revolutionary", "Best ever" = downvotes |
| No first comment | Теряешь контроль над narrative |
| Исчезнуть после поста | Комменты без ответов = смерть поста |
| Signup wall | Demo должен работать БЕЗ регистрации |

---

## Чеклист перед launch

### Технический

- [ ] `npx create-dld` работает
- [ ] GIF в README отображается на GitHub
- [ ] Demo/landing выдержит 10K visitors
- [ ] Discord ссылка рабочая
- [ ] Analytics настроен (отдельно трекать PH/HN traffic)

### Контент

- [ ] HN title протестирован на 3-5 людях
- [ ] First comment написан (≤800 символов)
- [ ] Twitter тред готов (5-7 твитов)
- [ ] Reddit посты готовы (разные для каждого сабреддита!)
- [ ] Dev.to статья в черновиках

### Операционный

- [ ] 10-15 людей готовы попробовать и комментировать
- [ ] Заблокировано 6+ часов на день HN launch
- [ ] Уведомления на телефоне включены
- [ ] Backup plan если что-то сломается

---

## Product Hunt специфика (2026)

### Алгоритм

- Upvotes от verified/active users весят больше
- Первые 4 часа критичны (upvotes скрыты, но алгоритм работает)
- Comments и discussion важнее чем raw upvotes
- Новые аккаунты и координированные upvotes = unfeatured

### Hunter

Рекомендуется найти Hunter'а заранее:
- Проверяет позиционирование
- Даёт feedback на gallery/copy
- Помогает с первым впечатлением

### Gallery images

1. **Первое изображение** — hook, кто target audience
2. **2-3 изображение** — product workflow screenshots
3. **4-5 изображение** — outcomes/results
4. **Последнее** — clear CTA

### Maker comment

- ≤800 символов
- Что это + почему это важно + CTA
- Можно переиспользовать как blog post и social post
- Personal touch важен

---

## Reddit специфика

### Сабреддиты для DLD

| Subreddit | Аудитория | Подход |
|-----------|-----------|--------|
| r/ClaudeAI | Claude users | Technical, how it works with Claude |
| r/SideProject | Indie hackers | Story-first, journey |
| r/selfhosted | Self-hosters | Installation, local-first |
| r/programming | Developers | Technical deep-dive |
| r/MachineLearning | ML engineers | AI architecture angle |

### Правила

- **Разные посты** для разных сабреддитов
- **1-2 дня** между постами (не спамить)
- **НЕ звучать как маркетолог** — Reddit банит моментально
- **Engage genuinely** в комментах

---

## Twitter/X специфика (2026)

### Что работает

- Threads > single tweets
- Video content приоритизируется
- Verified accounts получают boost
- Real-time engagement критичен

### Thread structure

1. **Hook** — pain point или surprising stat
2. **Problem** — why current solutions fail
3. **Solution** — what DLD does differently
4. **Demo** — GIF или video
5. **Social proof** — если есть
6. **CTA** — link to repo

---

## Конкретный план

| День | Действие | Статус |
|------|----------|--------|
| День 0 | Push commits, verify all links | [ ] |
| День 1 | Twitter тред + r/ClaudeAI | [ ] |
| День 2 | r/SideProject + собрать feedback | [ ] |
| День 3-4 | **HN Launch** (Вт/Ср, 8:00 AM PT) | [ ] |
| День 5 | Respond to all HN comments | [ ] |
| День 7 | Product Hunt (с Hunter'ом) | [ ] |
| День 9 | r/programming | [ ] |
| День 11 | Dev.to article | [ ] |
| День 14 | r/MachineLearning | [ ] |

---

## Источники

- [Calmops: HN 500+ Upvotes Guide](https://calmops.com/indie-hackers/hacker-news-launch-500-upvotes/)
- [Bob Singor: #1 HN, 500 stars/24h](https://forem.com/bobsingor/how-i-got-500-stars-in-24-hours-on-my-first-public-github-repo-1afg)
- [Rybbit: 5000 stars in 9 days](https://rybbit.io/blog/5k-stars)
- [Hackmamba: PH Launch 2026 with Flo Merian](https://hackmamba.io/developer-marketing/how-to-launch-on-product-hunt/)
- [GitHub Blog: Promoting Open Source](https://github.blog/open-source/maintainers/5-tips-for-promoting-your-open-source-project)
- [Awesome Directories: HN Front Page Guide](https://awesome-directories.com/blog/hacker-news-front-page-guide/)
- [Product Hunt Official Launch Guide](https://www.producthunt.com/launch)

---

*Создано: 2026-02-03*
*Метод: Exa MCP research + Sequential Thinking analysis*
