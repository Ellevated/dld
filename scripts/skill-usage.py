#!/usr/bin/env python3
"""Счётчик реальных вызовов скиллов, слэш-команд и субагентов.

Читает локальные JSONL-логи Claude Code (`~/.claude/projects/*/*.jsonl`) и отвечает на
вопрос «что из установленного вообще срабатывает». В отличие от OTel-телеметрии работает
ретроспективно: логи уже лежат на диске, никакого backfill не требуется.

    python scripts/skill-usage.py                       # весь флот, вся история
    python scripts/skill-usage.py --days 30             # окно в 30 дней
    python scripts/skill-usage.py --project D--dev-dld  # один проект
    python scripts/skill-usage.py --json out.json       # машиночитаемо

Скилл считается использованным, если он вызывался как Skill tool, как слэш-команда ИЛИ
через своего субагента (`bughunt-qa-engineer` → скилл `bughunt`). Без последнего правила
скилл, работающий только через персон, ошибочно попадает в zero-usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

COMMAND_RE = re.compile(r"<command-name>/?([\w:-]+)</command-name>")

# Встроенные команды CLI — не наши скиллы, в отчёте только шумят.
BUILTIN_COMMANDS = {
    "add-dir",
    "agents",
    "artifacts",
    "bug",
    "clear",
    "compact",
    "config",
    "context",
    "cost",
    "doctor",
    "exit",
    "export",
    "fast",
    "help",
    "hooks",
    "ide",
    "init",
    "install-github-app",
    "login",
    "logout",
    "mcp",
    "memory",
    "migrate-installer",
    "model",
    "output-style",
    "permissions",
    "pr-comments",
    "privacy-settings",
    "release-notes",
    "resume",
    "rewind",
    "sandbox",
    "statusline",
    "status",
    "terminal-setup",
    "todos",
    "upgrade",
    "usage",
    "vim",
    "workflows",
}


def iter_records(path: Path):
    """Отдаёт (timestamp, message_content) из одного JSONL-файла сессии."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict):
                    continue
                msg = rec.get("message")
                if not isinstance(msg, dict):
                    continue
                yield rec.get("timestamp"), msg.get("content")
    except OSError as exc:
        print(f"warn: не прочитан {path}: {exc}", file=sys.stderr)


def parse_ts(raw):
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def collect(projects_dir: Path, since, only_project):
    """Считает вызовы по всем сессиям."""
    skills = Counter()
    commands = Counter()
    agents = Counter()
    agent_models = defaultdict(Counter)
    mcp = Counter()
    mcp_tools = defaultdict(Counter)
    by_project = defaultdict(Counter)
    by_day = defaultdict(Counter)
    first_ts = None
    last_ts = None
    sessions = 0

    def note_command(name, project, day):
        if name in BUILTIN_COMMANDS:
            return
        commands[name] += 1
        by_project[project]["/" + name] += 1
        by_day[day]["/" + name] += 1

    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        if only_project and project_dir.name != only_project:
            continue
        for session in sorted(project_dir.glob("*.jsonl")):
            sessions += 1
            for raw_ts, content in iter_records(session):
                ts = parse_ts(raw_ts)
                if since and ts and ts < since:
                    continue
                if ts:
                    first_ts = ts if first_ts is None or ts < first_ts else first_ts
                    last_ts = ts if last_ts is None or ts > last_ts else last_ts
                day = ts.date().isoformat() if ts else "unknown"

                # Слэш-команды приходят текстом в user-сообщении.
                if isinstance(content, str):
                    for name in COMMAND_RE.findall(content):
                        note_command(name, project_dir.name, day)
                    continue

                if not isinstance(content, list):
                    continue

                for block in content:
                    if not isinstance(block, dict):
                        continue

                    if block.get("type") == "text":
                        for name in COMMAND_RE.findall(str(block.get("text", ""))):
                            note_command(name, project_dir.name, day)

                    if block.get("type") != "tool_use":
                        continue

                    tool = block.get("name")
                    payload = block.get("input") or {}
                    if not isinstance(payload, dict):
                        continue

                    if tool == "Skill":
                        name = payload.get("skill")
                        if name:
                            skills[name] += 1
                            by_project[project_dir.name][name] += 1
                            by_day[day][name] += 1

                    # MCP-тулы: сервер может быть единственной точкой входа скилла.
                    elif isinstance(tool, str) and tool.startswith("mcp__"):
                        parts = tool.split("__")
                        server = parts[1] if len(parts) > 2 else tool
                        mcp[server] += 1
                        mcp_tools[server][parts[-1] if len(parts) > 2 else tool] += 1

                    # Task в старых версиях CLI, Agent в текущей — один и тот же механизм.
                    elif tool in ("Task", "Agent"):
                        name = payload.get("subagent_type") or "(без subagent_type)"
                        agents[name] += 1
                        agent_models[name][payload.get("model") or "(не задана)"] += 1

    meta = {
        "sessions": sessions,
        "first": first_ts.isoformat() if first_ts else None,
        "last": last_ts.isoformat() if last_ts else None,
    }
    return skills, commands, agents, agent_models, mcp, mcp_tools, by_project, by_day, meta


def inventory(repo):
    """Что вообще установлено: скиллы и команды, глобальные и проектные."""
    home = Path.home() / ".claude"
    found = {"skill": set(), "command": set()}

    def scan_skills(root: Path):
        if not root.is_dir():
            return
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "SKILL.md").exists():
                found["skill"].add(entry.name)
            elif entry.is_file() and entry.suffix == ".md" and entry.stem != "README":
                found["skill"].add(entry.stem)

    def scan_commands(root: Path):
        if not root.is_dir():
            return
        for entry in root.rglob("*.md"):
            found["command"].add(entry.stem)

    scan_skills(home / "skills")
    scan_commands(home / "commands")
    for plugin in (home / "plugins").glob("*/skills"):
        scan_skills(plugin)
    if repo:
        scan_skills(repo / ".claude" / "skills")
        scan_commands(repo / ".claude" / "commands")
    return found


def skills_reached_via_agents(agent_names, installed_skills):
    """`bughunt-qa-engineer` обслуживает скилл `bughunt` — это тоже использование."""
    reached = {}
    for agent in agent_names:
        for skill in installed_skills:
            if agent == skill or agent.startswith(skill + "-") or agent.startswith(skill + "_"):
                reached.setdefault(skill, set()).add(agent)
    return reached


def fleet_roots(repo, fleet_dir):
    """Текущий репозиторий + все соседние проекты, у которых есть свой .claude/."""
    roots = [repo] if repo else []
    if fleet_dir and fleet_dir.is_dir():
        for entry in sorted(fleet_dir.iterdir()):
            if entry.is_dir() and (entry / ".claude").is_dir():
                roots.append(entry)
    # dedup с сохранением порядка
    seen, out = set(), []
    for r in roots:
        key = str(r).lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def agents_with_own_model(repos):
    """Агенты, у которых model: задан в собственном frontmatter — модель НЕ из сессии.

    Сканируется ВЕСЬ флот, а не один репозиторий: сессия в Dowry вызывает агентов Dowry,
    и если смотреть только текущий репо, живой агент выглядит сиротой. Ровно эта ошибка
    в первой версии скрипта дала ложную тревогу на spark-patterns/spark-external.
    """
    named = set()
    roots = []
    for repo in repos:
        if repo and (repo / ".claude" / "agents").is_dir():
            roots.append(repo / ".claude" / "agents")
    if not roots:
        return named
    paths = [pp for root in roots for pp in root.rglob("*.md")]
    for path in paths:
        try:
            head = path.read_text(encoding="utf-8", errors="replace")[:1200]
        except OSError:
            continue
        if re.search(r"^model:", head, re.MULTILINE):
            match = re.search(r"^name:\s*(\S+)", head, re.MULTILINE)
            named.add(match.group(1) if match else path.stem)
    return named


def render(skills, commands, agents, agent_models, mcp, mcp_tools, by_project, by_day, meta, inv, days, own_model):
    installed = inv["skill"] | inv["command"]
    via_agents = skills_reached_via_agents(agents.keys(), inv["skill"])
    used = set(skills) | set(commands) | set(via_agents)
    zero = sorted(installed - used)

    window = f"последние {days} дней" if days else "вся история логов"
    print()
    print(f"=== Вызовы скиллов и команд * {window} ===")
    print(f"сессий: {meta['sessions']} * период: {meta['first']} .. {meta['last']}")
    print()

    print(f"-- Скиллы через Skill tool ({len(skills)} шт, {sum(skills.values())} вызовов) --")
    for name, count in skills.most_common():
        print(f"  {count:5d}  {name}")
    if not skills:
        print("  (нет вызовов)")

    print()
    print(f"-- Слэш-команды ({len(commands)} шт, {sum(commands.values())} вызовов) --")
    for name, count in commands.most_common():
        print(f"  {count:5d}  /{name}")
    if not commands:
        print("  (нет вызовов)")

    print()
    print(f"-- Субагенты ({len(agents)} типов, {sum(agents.values())} запусков) --")
    for name, count in agents.most_common():
        models = ", ".join(f"{m}x{c}" for m, c in agent_models[name].most_common())
        origin = "frontmatter" if name in own_model else "МОДЕЛЬ СЕССИИ"
        print(f"  {count:5d}  {name:28s} [{models}] <- {origin}")
    stray = sorted(n for n in agents if n not in own_model)
    if stray:
        print()
        print(f"  Без своего файла агента ({len(stray)}): {', '.join(stray)}")
        print("  -- у них модель приходит из сессии, а не из frontmatter.")

    if via_agents:
        print()
        print("-- Скиллы, живущие через своих субагентов (сам Skill tool не вызывается) --")
        for skill in sorted(via_agents):
            personas = ", ".join(sorted(via_agents[skill]))
            total = sum(agents[a] for a in via_agents[skill])
            print(f"  {total:5d}  {skill}: {personas}")

    print()
    print(f"-- MCP-серверы ({len(mcp)} шт, {sum(mcp.values())} вызовов) --")
    for server, count in mcp.most_common():
        top = ", ".join(f"{t}x{c}" for t, c in mcp_tools[server].most_common(3))
        print(f"  {count:5d}  {server:24s} {top}")
    if not mcp:
        print("  (нет вызовов)")
    print("  ВНИМАНИЕ: для скилла, чья точка входа — MCP-сервер, ноль в разделе Skill tool")
    print("  ничего не значит. Смотреть надо сюда. И ни один раздел не видит вызовов через Bash.")

    print()
    print(f"-- ZERO-USAGE: ни Skill, ни команда, ни субагент ({len(zero)} из {len(installed)}) --")
    for name in zero:
        kind = "skill" if name in inv["skill"] else "command"
        print(f"         {name}  ({kind})")
    if not zero:
        print("  (таких нет)")

    print()
    print("-- По проектам --")
    for project, counter in sorted(by_project.items(), key=lambda kv: -sum(kv[1].values())):
        top = ", ".join(f"{n}x{c}" for n, c in counter.most_common(5))
        print(f"  {sum(counter.values()):5d}  {project}: {top}")

    if by_day:
        print()
        print("-- По дням (последние 14) --")
        for day in sorted(by_day)[-14:]:
            counter = by_day[day]
            top = ", ".join(f"{n}x{c}" for n, c in counter.most_common(4))
            print(f"  {sum(counter.values()):5d}  {day}: {top}")


def main() -> int:
    # Консоль Windows по умолчанию cp1251 — русский текст её роняет.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="Счётчик вызовов скиллов по логам Claude Code")
    parser.add_argument("--days", type=int, default=None, help="окно в днях (по умолчанию всё)")
    parser.add_argument("--project", default=None, help="имя папки проекта в ~/.claude/projects")
    parser.add_argument("--repo", default=".", help="репозиторий, чьи .claude/ учитывать")
    parser.add_argument("--projects-dir", default=None, help="путь к ~/.claude/projects")
    parser.add_argument(
        "--fleet",
        default=str(Path("D:/dev")) if sys.platform == "win32" else str(Path.home() / "projects"),
        help="каталог с остальными проектами — их агенты тоже считаются существующими",
    )
    parser.add_argument("--json", dest="json_out", default=None, help="выгрузить JSON")
    args = parser.parse_args()

    if args.projects_dir:
        projects_dir = Path(args.projects_dir)
    else:
        projects_dir = Path.home() / ".claude" / "projects"
    if not projects_dir.is_dir():
        print(f"Нет каталога логов: {projects_dir}", file=sys.stderr)
        return 1

    since = datetime.now(timezone.utc) - timedelta(days=args.days) if args.days else None
    repo = Path(args.repo).resolve() if args.repo else None

    skills, commands, agents, agent_models, mcp, mcp_tools, by_project, by_day, meta = collect(
        projects_dir, since, args.project
    )
    inv = inventory(repo)
    fleet = Path(args.fleet) if args.fleet else None
    roots = fleet_roots(repo, fleet)
    own_model = agents_with_own_model(roots)
    render(
        skills, commands, agents, agent_models, mcp, mcp_tools,
        by_project, by_day, meta, inv, args.days, own_model,
    )

    if args.json_out:
        via_agents = skills_reached_via_agents(agents.keys(), inv["skill"])
        used = set(skills) | set(commands) | set(via_agents)
        payload = {
            "meta": meta,
            "window_days": args.days,
            "skills": dict(skills),
            "commands": dict(commands),
            "agents": dict(agents),
            "mcp_servers": dict(mcp),
            "mcp_tools": {k: dict(v) for k, v in mcp_tools.items()},
            "agent_models": {k: dict(v) for k, v in agent_models.items()},
            "skills_via_agents": {k: sorted(v) for k, v in via_agents.items()},
            "agents_without_own_model": sorted(n for n in agents if n not in own_model),
            "by_project": {k: dict(v) for k, v in by_project.items()},
            "by_day": {k: dict(v) for k, v in by_day.items()},
            "installed": {k: sorted(v) for k, v in inv.items()},
            "zero_usage": sorted((inv["skill"] | inv["command"]) - used),
        }
        out_path = Path(args.json_out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print()
        print(f"JSON: {args.json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
