# TECH-178 — Pre-commit hook откатывает коммиты на trailing whitespace в research-md

**Status:** queued
**Priority:** P2
**Risk:** R2
**Created:** 2026-05-04

---

## Problem

Pre-commit hook (trailing-whitespace fixer) систематически срабатывает на research-md файлах от scout/spark/bughunt и **откатывает коммит**: hook чинит файлы, но возвращает non-zero → git commit fails → autopilot ретраит, теряет минуты per цикл.

**Симптом (awardybot, 2026-05-04):** в логах FTR-923/FTR-925 несколько подряд retry на одном и том же коммите из-за whitespace в `ai/.spark/**/research-*.md`.

## Root Cause Hypothesis

1. Scout/spark пишут md-файлы без финальной нормализации (trailing whitespace в строках, отсутствие newline в конце).
2. Pre-commit hook `trailing-whitespace` запускается, чинит, exits 1 — стандартное поведение pre-commit.
3. Autopilot не делает auto-restage + retry — просто видит fail и пробует тот же коммит, который снова падает.

## Fix Direction

Три варианта (выбрать в planner):

**A. Whitelist research/diary в hook config (быстро).** Исключить `ai/.spark/**`, `ai/.bughunt/**`, `ai/diary/**`, `ai/reflect/**` из trailing-whitespace check. Research-выхлоп — disposable, форматирование не важно.

**B. Auto-restage retry в autopilot/wrapper (системно).** После fail-коммита: `git add -u` → retry. Standard pre-commit pattern.

**C. Нормализация на стороне писателя.** Scout/spark при записи md делают `.rstrip() + "\n"` per line. Чище, но scattered.

Recommended: **A + B**. A снимает 90% случаев сразу, B защищает от прочих fixer-hooks (end-of-file, mixed-line-ending) для остальных файлов.

## Allowed Files

<!-- callback-allowlist v1 -->
- `.pre-commit-config.yaml`
- `scripts/vps/run-agent.sh`
- `scripts/vps/claude-runner.py`
<!-- callback-allowlist END -->

## Tests

1. **Hook config:** коммит с trailing whitespace в `ai/.spark/foo.md` проходит без модификации.
2. **Hook config:** коммит с trailing whitespace в `src/**/*.py` по-прежнему отлавливается и чинится.
3. **Auto-restage retry (если выбран B):** sim-тест — pre-commit вернул 1 + изменил файлы → wrapper делает `git add -u && git commit` → success on 2nd try.
4. **Latency:** на репродукции awardybot incident'а коммит с research-md проходит с первого раза (нет retry-loop).

## Acceptance

- [ ] Research/diary md-файлы не блокируют коммит на whitespace
- [ ] Production code/tests по-прежнему форматируются hook'ом
- [ ] Autopilot wall-clock per-task снижается (no retry-loop)

## Out of Scope

- Migrate ко всем pre-commit hooks 4.x (отдельный TECH).
- Black/ruff format-on-save (другой hook).

## Related

- TECH-177: callback false-positive (тот же incident — awardybot 2026-05-04)
