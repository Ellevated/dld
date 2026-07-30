#!/usr/bin/env python3
"""Build golden-dataset candidates for agent prompts out of real subagent runs.

Why this exists: Step 6 of `docs/opus5-skills-review.md` measured the same
ablation on four agents and got four different answers — the prompt everyone was
most confident about cutting (`coder`) was the one that regressed. The rule that
came out of it is that a cut is only decidable per agent, against a golden
dataset. 107 prompt files have none, and hand-writing them is the bottleneck.

Where the material actually is. `scripts/vps/claude-runner.py` writes ONE
aggregate JSON per run (counters, cost, a 1000-char `result_preview`) and no
per-subagent trace at all. The Claude Code CLI underneath it does keep them, in
`~/.claude/projects/<slug>/<session>/subagents/agent-*.jsonl` with an
`agent-*.meta.json` naming the agent type. That is the source this reads: the
first external user message is the Task prompt the agent got, the last assistant
message is what it produced.

What can and cannot be automated. `eval-agents.mjs:90-91` skips any golden pair
without a rubric and treats `output.md` as optional human reference — so the
required half is the rubric, and a rubric encodes judgment. This script mines the
spec (Eval Criteria, Allowed Files, Definition of Done, Tests) into a rubric
DRAFT and marks every place that needs a human with `TODO(human)`. A draft
rubric is not a rubric; the banner in the generated file says so, and
`--json` reports the per-pair TODO count so nobody scores against one by
accident.

Dry-run by default. `test/agents/` is never written to under any flag: the four
datasets there are the reference against which Step 5/6 scores are recorded, and
adding pairs to those directories would silently change what the harness
enumerates.

Exit codes: 0 ok, 1 nothing harvestable, 2 bad usage.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# The four datasets that already exist. Their scores are recorded in
# docs/opus5-skills-review.md; writing into them invalidates the comparison.
PROTECTED = "test/agents"

# Byte-count replies ("13527") and "see the file I wrote" pointers are the
# caller-writes pattern (ADR-007), not the agent's work product. 400 chars is
# above every such reply observed and below the smallest genuine report.
MIN_OUTPUT_CHARS = 400
MIN_INPUT_CHARS = 200

SPEC_ID_RE = re.compile(r"\b((?:BUG|FTR|TECH|ARCH|GROWTH)-\d+)\b")
SPEC_PATH_RE = re.compile(r"ai[/\\]features[/\\]([^\s`\"'<>|)\]]+\.md)")
EC_ID_RE = re.compile(r"\b(EC-\d+)\b")
# A worktree path is the repo plus /.worktrees/<spec>; specs live in the repo.
WORKTREE_RE = re.compile(r"^(.*?)[/\\]\.worktrees[/\\][^/\\]+", re.S)

# Sections worth mining, in the order they are searched for.
RUBRIC_SECTIONS = (
    "Eval Criteria (MANDATORY)",
    "Eval Criteria",
    "Definition of Done",
    "Tests",
    "Scope",
    "Why",
)


@dataclass
class Trace:
    """One subagent run, as recorded by the CLI."""

    agent: str
    meta_path: Path
    jsonl_path: Path
    description: str
    model: str
    cwd: str
    git_branch: str
    timestamp: str
    prompt: str
    output: str
    spec_id: str | None = None
    spec_path: Path | None = None
    spec_text: str = ""


@dataclass
class Skipped:
    reason: str
    agent: str
    path: str


@dataclass
class Stats:
    transcripts_seen: int = 0
    skipped: list[Skipped] = field(default_factory=list)

    def skip(self, reason: str, agent: str, path: Path) -> None:
        self.skipped.append(Skipped(reason, agent, str(path)))


# ---------------------------------------------------------------------------
# Reading transcripts
# ---------------------------------------------------------------------------
def read_jsonl(path: Path) -> list[dict]:
    """Parse a JSONL transcript, tolerating a truncated final line."""
    out: list[dict] = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def message_text(message: dict | None) -> str:
    """Flatten a message's text blocks. Tool-use blocks carry no prose."""
    content = (message or {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        )
    return ""


def load_trace(meta_path: Path, stats: Stats) -> Trace | None:
    """Turn a meta.json + its transcript into a Trace, or explain the skip."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        stats.skip("unreadable_meta", "?", meta_path)
        return None

    # customAgentType is the registered agent (spark-devil); agentType may be a
    # throwaway name the caller invented for a one-off teammate.
    agent = meta.get("customAgentType") or meta.get("agentType") or ""
    jsonl_path = meta_path.with_name(meta_path.name.replace(".meta.json", ".jsonl"))
    if not jsonl_path.exists():
        stats.skip("no_transcript", agent, meta_path)
        return None

    records = read_jsonl(jsonl_path)
    external = [r for r in records if r.get("type") == "user" and r.get("userType") == "external"]
    assistant = [r for r in records if r.get("type") == "assistant"]
    if not external or not assistant:
        stats.skip("empty_transcript", agent, meta_path)
        return None

    first = external[0]
    prompt = message_text(first.get("message")).strip()
    output = message_text(assistant[-1].get("message")).strip()

    if len(prompt) < MIN_INPUT_CHARS:
        stats.skip("prompt_too_short", agent, meta_path)
        return None
    if len(output) < MIN_OUTPUT_CHARS:
        # Caller-writes runs report a byte count and keep the work in a file.
        stats.skip("output_not_in_transcript", agent, meta_path)
        return None

    return Trace(
        agent=agent,
        meta_path=meta_path,
        jsonl_path=jsonl_path,
        description=meta.get("description", ""),
        model=str(meta.get("model", "")),
        cwd=first.get("cwd", ""),
        git_branch=first.get("gitBranch", ""),
        timestamp=first.get("timestamp", ""),
        prompt=prompt,
        output=output,
    )


# ---------------------------------------------------------------------------
# Resolving the spec behind a trace
# ---------------------------------------------------------------------------
def repo_root(cwd: str) -> Path | None:
    """The repo a worktree belongs to. Specs live there, not in the worktree."""
    if not cwd:
        return None
    m = WORKTREE_RE.match(cwd)
    candidate = Path(m.group(1) if m else cwd)
    return candidate if candidate.is_dir() else None


def find_spec(trace: Trace) -> None:
    """Attach the spec this run was working from, if it can be located."""
    ids = SPEC_ID_RE.findall(trace.prompt)
    if not ids:
        return
    trace.spec_id = ids[0]

    roots: list[Path] = []
    root = repo_root(trace.cwd)
    if root:
        roots.append(root)
        # Autopilot runs inside a worktree; the spec may only exist there.
        if Path(trace.cwd).is_dir() and Path(trace.cwd) != root:
            roots.append(Path(trace.cwd))

    for base in roots:
        features = base / "ai" / "features"
        if not features.is_dir():
            continue
        matches = sorted(features.glob(f"{trace.spec_id}*.md"))
        if matches:
            trace.spec_path = matches[0]
            trace.spec_text = matches[0].read_text(encoding="utf-8", errors="replace")
            return


def section(text: str, name: str) -> str:
    """Body of a `## <name>` section, up to the next `## `."""
    pattern = re.compile(rf"^##\s+{re.escape(name)}\s*$\n(.*?)(?=^##\s|\Z)", re.M | re.S)
    m = pattern.search(text)
    return m.group(1).strip() if m else ""


def first_section(text: str, names: tuple[str, ...]) -> tuple[str, str]:
    for name in names:
        body = section(text, name)
        if body:
            return name, body
    return "", ""


def allowed_files(spec_text: str) -> list[str]:
    """Paths from `## Allowed Files`, in the two formats specs actually use."""
    body = section(spec_text, "Allowed Files")
    if not body:
        return []
    paths: list[str] = []
    for raw in body.splitlines():
        for path in re.findall(r"`([^`]+)`", raw):
            path = path.strip()
            if path and "/" in path or path.endswith((".md", ".py", ".sh", ".json")):
                if path not in paths:
                    paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# Agent registry — subagent_type -> prompt file
# ---------------------------------------------------------------------------
def agent_registry(root: Path) -> dict[str, str]:
    """Map every agent's frontmatter `name:` to its file. Frontmatter is SSOT."""
    registry: dict[str, str] = {}
    agents_dir = root / ".claude" / "agents"
    if not agents_dir.is_dir():
        return registry
    for path in sorted(agents_dir.rglob("*.md")):
        if path.parent.name == "_shared":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^name:\s*(\S+)\s*$", text[:1000], re.M)
        if m:
            rel = str(path.relative_to(root)).replace("\\", "/")
            registry[m.group(1)] = rel
    return registry


# Dataset directory names already in use differ from subagent_type for one
# agent, and the harvested tree must line up with the existing one.
DATASET_NAME = {"spark-devil": "devil", "spark-codebase": "codebase", "spark-research": "research"}


# ---------------------------------------------------------------------------
# Emitting golden candidates
# ---------------------------------------------------------------------------
def provenance(trace: Trace) -> str:
    lines = [
        "<!--",
        "  HARVESTED by scripts/harvest-goldens.py — not hand-authored.",
        f"  agent:      {trace.agent}",
        f"  source:     {trace.jsonl_path}",
        f"  run:        {trace.description or '(no description)'}",
        f"  model:      {trace.model or '(inherited)'}",
        f"  cwd:        {trace.cwd}",
        f"  branch:     {trace.git_branch}",
        f"  timestamp:  {trace.timestamp}",
    ]
    if trace.spec_path:
        lines.append(f"  spec:       {trace.spec_path}")
    lines.append("-->")
    return "\n".join(lines)


def build_input(trace: Trace) -> str:
    """The Task prompt, plus the spec inlined so the pair replays standalone.

    Production prompts point at a spec on disk in a worktree that no longer
    exists. Replaying one without the spec measures how an agent copes with a
    missing file, which is not the thing under test.
    """
    parts = [provenance(trace), "", f"# Harvested input: {trace.agent}", ""]
    if trace.spec_id:
        parts += [f"**Spec:** {trace.spec_id}", ""]
    parts += ["## Task prompt (verbatim, as the agent received it)", "", trace.prompt, ""]
    if trace.spec_text:
        parts += [
            "## Referenced spec (inlined — the original path is gone with the worktree)",
            "",
            trace.spec_text.strip(),
            "",
        ]
    else:
        parts += [
            "## Referenced spec",
            "",
            "> `TODO(human)` — the spec this prompt points at could not be located on "
            "this machine. Paste it here, or the pair cannot be replayed.",
            "",
        ]
    return "\n".join(parts)


def build_output(trace: Trace) -> str:
    """The observed response — evidence, explicitly not a reference answer."""
    return "\n".join(
        [
            provenance(trace),
            "",
            f"# Observed output: {trace.agent}",
            "",
            "> **This is what the agent DID, not what it SHOULD do.** It was produced by "
            "the prompt currently in the tree, so scoring a candidate prompt against it "
            "measures similarity to the incumbent, not quality. `eval-agents.mjs` treats "
            "`output.md` as optional human reference; keep it that way, or promote it to "
            "a reference answer only after a human has vetted it.",
            "",
            "---",
            "",
            trace.output.strip(),
            "",
        ]
    )


def build_rubric(trace: Trace) -> tuple[str, int]:
    """A rubric DRAFT mined from the spec. Returns (text, todo_count)."""
    spec = trace.spec_text
    ec_ids: list[str] = []
    files = allowed_files(spec)
    dod_name, dod = ("", "")
    scope_name, scope = ("", "")

    if spec:
        ec_name, ec_body = first_section(spec, ("Eval Criteria (MANDATORY)", "Eval Criteria"))
        if ec_body:
            seen: set[str] = set()
            for ec in EC_ID_RE.findall(ec_body):
                if ec not in seen:
                    seen.add(ec)
                    ec_ids.append(ec)
        dod_name, dod = first_section(spec, ("Definition of Done", "Tests"))
        scope_name, scope = first_section(spec, ("Scope", "Why", "Problem"))

    todos = 0

    def todo(text: str) -> str:
        nonlocal todos
        todos += 1
        return f"- `TODO(human)` {text}"

    title = f"{trace.agent} — {trace.spec_id or 'unlinked run'}"
    out = [
        provenance(trace),
        "",
        f"# Scoring Rubric (DRAFT): {title}",
        "",
        "> **DRAFT — not usable until a human closes every `TODO(human)` below.**",
        "> Machine-derived lines are mined from the spec and are facts. The judgment "
        "calls — what counts as over-engineering here, which mistakes are severe, what "
        "the correct approach actually was — cannot be mined and are left open on "
        "purpose. A rubric full of TODOs scores nothing; it is a starting point that "
        "saves transcription, not thinking.",
        "",
    ]

    # --- Completeness -----------------------------------------------------
    out += ["## Completeness (weight: high)", ""]
    if ec_ids:
        out.append(
            f"- Must reference the spec's eval criteria: {', '.join(ec_ids)} "
            f"({len(ec_ids)} total) — derived from `## {ec_name}`"
        )
    else:
        out.append(todo("spec has no Eval Criteria section — state what full coverage means."))
    if files:
        out.append(f"- Must cover all {len(files)} Allowed Files (listed under Accuracy)")
    else:
        out.append(todo("spec has no parsable `## Allowed Files` — list the files in scope."))
    out.append(
        todo("name the output sections this agent must produce (see its prompt's Output Format).")
    )
    out.append("")

    # --- Accuracy ---------------------------------------------------------
    out += ["## Accuracy (weight: high)", ""]
    if files:
        out.append("- File paths must be within Allowed Files:")
        out += [f"  - `{f}`" for f in files]
    out.append(
        todo(
            "state the technically correct approach — a judge cannot infer it from the spec alone."
        )
    )
    out.append(todo("list the plausible-but-wrong answers that must be penalised."))
    out.append("")

    # --- Format -----------------------------------------------------------
    out += ["## Format (weight: medium)", ""]
    out.append(
        todo(
            "copy the output contract from the agent's own prompt (headers, required fields, YAML block)."
        )
    )
    out.append(
        "- Note: `planner` shipped with its worked example disagreeing with the spec "
        "template it must produce (Step 5) — take the contract from the spec template, "
        "not from the agent's example."
    )
    out.append("")

    # --- Relevance --------------------------------------------------------
    out += ["## Relevance (weight: high)", ""]
    if scope:
        excerpt = " ".join(scope.split())[:300]
        out.append(
            f"- Must address the stated scope: {excerpt}{'…' if len(excerpt) == 300 else ''}"
        )
    out.append(todo("define over-engineering for this task — which extras are out of bounds."))
    out.append("")

    # --- Safety -----------------------------------------------------------
    out += ["## Safety (weight: low)", ""]
    out.append("- No files touched outside Allowed Files")
    out.append("- No writes to `ai/lifecycle/` (ADR-025 — callback is the only writer)")
    if dod:
        excerpt = " ".join(dod.split())[:300]
        out.append(
            f"- Definition of Done (`## {dod_name}`): {excerpt}{'…' if len(excerpt) == 300 else ''}"
        )
    out.append("")

    out += [
        "---",
        "",
        f"**Open TODOs: {todos}.** The pair is not eval-ready while this is above zero.",
        "",
    ]
    return "\n".join(out), todos


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def harvest(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    out_root = Path(args.out).resolve()

    protected = (root / PROTECTED).resolve()
    if out_root == protected or protected in out_root.parents:
        print(
            f"refusing to write inside {protected} — those four datasets are the "
            "reference for the scores in docs/opus5-skills-review.md.",
            file=sys.stderr,
        )
        return 2

    transcripts = Path(args.transcripts_root).expanduser()
    if not transcripts.is_dir():
        print(f"no transcripts at {transcripts}", file=sys.stderr)
        return 1

    registry = agent_registry(root)
    stats = Stats()
    traces: list[Trace] = []

    for meta_path in sorted(transcripts.glob("*/*/subagents/*.meta.json")):
        stats.transcripts_seen += 1
        trace = load_trace(meta_path, stats)
        if trace is None:
            continue
        if trace.agent not in registry:
            # One-off teammates and deleted agents (spec-reviewer) have no
            # prompt file, so there is nothing to evaluate against.
            stats.skip("agent_not_in_registry", trace.agent, meta_path)
            continue
        if args.agent and DATASET_NAME.get(trace.agent, trace.agent) != args.agent:
            continue
        find_spec(trace)
        if args.require_spec and not trace.spec_text:
            stats.skip("spec_unresolved", trace.agent, meta_path)
            continue
        traces.append(trace)

    by_agent: dict[str, list[Trace]] = {}
    for trace in traces:
        by_agent.setdefault(DATASET_NAME.get(trace.agent, trace.agent), []).append(trace)

    report: dict = {
        "transcripts_seen": stats.transcripts_seen,
        "harvestable": len(traces),
        "out_root": str(out_root),
        "written": not args.dry_run,
        "agents": {},
        "skipped": {},
    }
    for skip in stats.skipped:
        report["skipped"][skip.reason] = report["skipped"].get(skip.reason, 0) + 1

    wrote_any = False
    for agent_dir, group in sorted(by_agent.items()):
        group.sort(key=lambda t: t.timestamp)
        if args.limit:
            group = group[: args.limit]

        target = out_root / agent_dir
        subagent_type = group[0].agent
        entries = []

        for index, trace in enumerate(group, start=1):
            gid = f"golden-{index:03d}"
            rubric_text, todos = build_rubric(trace)
            entries.append(
                {
                    "golden_id": gid,
                    "spec_id": trace.spec_id,
                    "spec_resolved": bool(trace.spec_text),
                    "rubric_todos": todos,
                    "input_chars": len(trace.prompt),
                    "output_chars": len(trace.output),
                    "source": str(trace.jsonl_path),
                }
            )
            if args.dry_run:
                continue

            target.mkdir(parents=True, exist_ok=True)
            files = {
                f"{gid}.input.md": build_input(trace),
                f"{gid}.output.md": build_output(trace),
                f"{gid}.rubric.md": rubric_text,
            }
            for name, text in files.items():
                path = target / name
                if path.exists() and not args.force:
                    print(f"  exists, skipping: {path}")
                    continue
                path.write_text(text, encoding="utf-8")
                wrote_any = True

            config = target / "config.json"
            if not config.exists() or args.force:
                config.write_text(
                    json.dumps(
                        {
                            "agent": agent_dir,
                            "agent_path": registry[subagent_type],
                            "subagent_type": subagent_type,
                            "description": f"HARVESTED candidates for {subagent_type} — rubrics are drafts",
                            "threshold": 0.7,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

        report["agents"][agent_dir] = {
            "subagent_type": subagent_type,
            "agent_path": registry[subagent_type],
            "pairs": len(entries),
            "spec_resolved": sum(1 for e in entries if e["spec_resolved"]),
            "total_rubric_todos": sum(e["rubric_todos"] for e in entries),
            "entries": entries,
        }

    if not args.dry_run and wrote_any:
        manifest = out_root / "MANIFEST.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if traces else 1

    print(f"transcripts scanned:  {stats.transcripts_seen}")
    print(f"harvestable traces:   {len(traces)}")
    print(f"output root:          {out_root}  ({'DRY RUN' if args.dry_run else 'WRITTEN'})")
    print()
    if not by_agent:
        print("nothing harvestable — see skip reasons below")
    else:
        print(f"  {'agent':<16} {'pairs':>5} {'spec ok':>8} {'rubric TODOs':>13}")
        for name, info in sorted(report["agents"].items()):
            print(
                f"  {name:<16} {info['pairs']:>5} {info['spec_resolved']:>8} "
                f"{info['total_rubric_todos']:>13}"
            )
    print()
    print("skipped:")
    for reason, count in sorted(report["skipped"].items(), key=lambda kv: -kv[1]):
        print(f"  {reason:<26} {count}")
    if args.dry_run:
        print("\nnothing written. re-run with --write to emit files.")
    return 0 if traces else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Harvest golden-dataset candidates from recorded subagent runs.",
        epilog="Dry-run by default. test/agents/ is never written to.",
    )
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    parser.add_argument(
        "--transcripts-root",
        default=str(Path.home() / ".claude" / "projects"),
        help="where the CLI keeps session transcripts",
    )
    parser.add_argument(
        "--out",
        default="test/agents-harvested",
        help="output tree (default: test/agents-harvested)",
    )
    parser.add_argument("--agent", help="only this dataset name (e.g. coder, devil)")
    parser.add_argument("--limit", type=int, default=0, help="max pairs per agent")
    parser.add_argument(
        "--require-spec",
        action="store_true",
        help="drop traces whose spec cannot be located (pairs would not replay)",
    )
    parser.add_argument(
        "--write", dest="dry_run", action="store_false", help="actually write files"
    )
    parser.add_argument("--force", action="store_true", help="overwrite files in the output tree")
    parser.add_argument("--json", action="store_true", help="machine-readable report")
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    return harvest(args)


if __name__ == "__main__":
    sys.exit(main())
