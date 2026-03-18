# Idea: 20260318-183600
**Source:** openclaw
**Route:** spark
**Status:** processing
---

DLD цикл никогда не проходил полный прогон от начала до конца.

Три конкретных разрыва выявлены в сессии 2026-03-18:

1. **QA не находит спеку** — qa-loop.sh запускается без передачи spec-пути; агент
   видит "FTR-702 not found", спрашивает у пользователя, получает permission_denied,
   продолжает вслепую и возвращает exit 0. Это false pass.

2. **artifact-scan не читает QA файлы** — openclaw-artifact-scan.py матчит только
   формат `YYYYMMDD-HHMMSS-SPEC-ID.md`, но qa-loop.sh пишет файлы вида
   `2026-03-17-tech-151.md` (ISO date, lowercase) — они падают в статус `unknown`.
   OpenClaw не может ревьюить артефакты которые не видит.

3. **topic_id NULL для большинства проектов** — awardybot, dowry, dowry-mc, nexus,
   plpilot не имеют topic_id в БД. notify.py молча падает или роутит в General.

Нужна спека которая закрывает эти три разрыва и добавляет один smoke test —
полный прогон цикла от inbox до reflect без ручного вмешательства.
