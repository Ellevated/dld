# Security Architecture Cross-Critique

**Persona:** Bruce (Security Architect)
**Phase:** 2 — Peer Review
**Date:** 2026-03-10

---

## Peer Analysis Reviews

### Analysis A (Operations)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

The ops persona correctly flagged the Claude CLI memory reality — 2-16 GB per session, not 200-500 MB — and that is a relevant security concern: OOM kills generate unpredictable process termination which creates race conditions on state files and can cause Claude processes to die mid-write with secrets still in memory. The `KillMode=control-group` recommendation is sound; without it, orphan Claude processes continue running with API keys loaded in environment, consuming quota, and generating unmonitored LLM output with no owner.

The dead man's switch design is directly relevant to security. An orchestrator that dies silently = no one monitoring for prompt injection attempts, failed auth attempts, or runaway Claude sessions. The three-layer heartbeat approach is reasonable.

What Analysis A misses from a security standpoint:

- The systemd `MemoryMax` constraint it proposes (14G on a 16G VPS) helps prevent DoS but does nothing about the attack scenario where a Claude process is prompt-injected and uses its legitimate memory allocation to exfiltrate data. Resource limits are not a confidentiality control.
- No mention of `KillMode=control-group` interaction with secret lifecycle. When systemd kills the control group, all processes die simultaneously. This means a Claude process holding an open API key file descriptor gets killed before it can clean up. This is correct behavior (no lingering access), but the analysis doesn't reason through it.
- The `/tmp/claude-semaphore/` semaphore directory is flagged as an ops concern but not as a security concern. World-writable `/tmp` allows any local process to create competing lock files, create TOCTOU races, or simply delete the semaphore files to cause lock confusion. Mode 700 on that directory is mandatory, not optional.

**Missed gaps:**

- No discussion of what gets logged and whether logs contain sensitive data (task names, project names, potentially fragments of prompts) that need restricted access.
- No audit trail design — who triggered what command, when, is entirely absent from the ops analysis.

---

### Analysis B (Devil's Advocate)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

The skeptic's core challenge — "Is this over-engineered for 2-3 projects?" — has direct security implications. Over-engineered systems have larger attack surfaces by definition. Every custom component (flock semaphore, hot-reload via inotifywait, custom state machine) is code that can have security bugs. The skeptic is right to pressure-test whether all this complexity is justified.

The SPOF analysis is security-relevant. Telegram as both control plane and alert channel means if Telegram is the attack vector (compromised account, API abuse), the attacker also controls your alerting system. This is a classic security anti-pattern: the alert mechanism shares a trust boundary with the control mechanism. The skeptic identified this implicitly but didn't name it as a security concern.

The "load-bearing shell script" warning has direct security implications: bash scripts with no standard error handling are easy to inject into. If `orchestrator.sh` grows to 400+ lines of accumulated conditionals, every new conditional is a potential code path that skips security checks.

The business case critique is valid from a security ROI standpoint. The most secure system is the one that doesn't exist. Not building the orchestrator in Phase 1 means zero new attack surface in Phase 1.

What Analysis B misses from a security standpoint:

- The skeptic proposes Pueue as the "simpler" alternative but never analyzes Pueue's own attack surface. Pueue is a daemon with a Unix socket (`~/.local/share/pueue/pueue.sock` by default). Anyone with filesystem access to the socket can issue Pueue commands. On a multi-tenant system this would be critical; on a single-user VPS it is lower risk but still worth acknowledging.
- The "why Telegram and not a CLI?" question ignores the comparative security of the alternatives. SSH access is actually a higher-privilege channel than a Telegram bot — SSH gives you a shell, Telegram gives you bot commands. From a least-privilege standpoint, the Telegram bot is the more restrictive interface, not the less.
- The contradiction about Telegram as control plane vs. notification sink has security implications that aren't drawn out. If GitHub Issues becomes primary, that introduces a new OAuth/webhook attack surface (discussed below under new questions).

**Missed gaps:**

- No analysis of Pueue's Unix socket security model.
- No analysis of whether the "simpler" alternatives actually reduce the attack surface or just move it.

---

### Analysis C (DX/Pragmatist)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

The Pueue recommendation is strong from a DX standpoint, and it has acceptable security properties: Pueue runs as a user daemon, not root; its Unix socket is scoped to the user's home directory; tasks run with the invoking user's permissions. These are the same security properties as the proposed flock approach.

The explicit innovation token accounting is useful for security reasoning. Fewer custom components = fewer novel attack surfaces. The observation that custom flock semaphore, custom state machine, custom hot-reload each represent attack surface is correct even if the analysis doesn't frame it that way.

The security cross-cutting section in Analysis C is minimal: "Pueue runs as user process. Project isolation: Pueue groups have separate working directories." This is incorrect on the isolation claim. Pueue groups are logical groupings for task management — they do NOT enforce filesystem isolation between projects. A Claude process submitted to the `saas-app` Pueue group can still `cat /home/user/side-project/.env` if it runs as the same Unix user. Groups are scheduling units, not security boundaries.

**Missed gaps:**

- The claim "Project isolation: Pueue groups have separate working directories" is wrong. Working directory is set per task by the caller, not enforced by Pueue groups. This is a security misconception that could lead the founder to believe cross-project isolation exists when it does not.
- No discussion of what happens to task logs in Pueue. `pueue log <id>` captures stdout/stderr of every task. If a Claude process prints an API key to stdout (e.g., in an error message), that key is now stored in Pueue's task log indefinitely. Log retention policy for Pueue logs needs to be defined.
- The "Telegram for notifications ONLY" recommendation is correct security hygiene (reduce control plane) but lacks the implementation detail about `from_user.id` validation, which is the actual security mechanism.

---

### Analysis E (LLM Architect)

**Agreement:** Agree

**Reasoning from security perspective:**

Analysis E is the most security-aware of the non-security analyses. The cross-session contamination finding (GitHub #30348) is a genuine security concern: if Project A's Claude session can inject content into Project B's context, that is an information disclosure and tampering vulnerability. The recommendation to use separate `CLAUDE_CODE_CONFIG_DIR` per project is correct and directly addresses the concern.

The `CLAUDE_CODE_CONFIG_DIR` isolation approach is better than the alternative of relying on separate Unix users for this specific issue — it addresses the Claude-specific contamination vector while remaining simpler to implement. However, it does not address the broader cross-project filesystem access problem (which requires either separate users or bubblewrap).

The `--allowedTools` per-phase recommendation is a genuine defense-in-depth measure I did not include in my original analysis. Restricting inbox-processor to `Read,Write,Bash,Glob,Grep` and excluding `Edit` from phases that don't need it reduces the blast radius of prompt injection. If an attacker injects a command into an inbox item processed by a triage agent that only has `Read` and `Glob`, the attacker cannot write files or execute arbitrary shell commands. This is the principle of least privilege applied correctly to LLM tool access.

The `--max-budget-usd` safety valve is also a security control I underweighted. At $2.00 per autopilot run, a prompt injection that triggers runaway LLM execution hits a hard cost ceiling. This prevents financial DoS (burning the entire API budget) from injected instructions.

**Missed gaps:**

- Analysis E correctly identifies session contamination as a risk but does not connect it to the broader trust boundary model: if sessions can contaminate, the entire "project isolation" security property collapses. The security implication (not just the reliability implication) deserves explicit treatment.
- No discussion of what `--output-format json` does to security. Machine-readable JSON output means the orchestrator is parsing Claude's output programmatically. If Claude is prompted to emit malicious JSON (prompt injection into the output format), the orchestrator's JSON parser becomes the attack surface. Output validation before acting on Claude's structured output is necessary.

---

### Analysis F (Evolutionary Architect)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

The fitness function approach to architecture is directly applicable to security. Several of the proposed fitness functions are implicitly security controls:

- "Project path validation" fitness function: this catches path traversal before it causes damage.
- "Semaphore slot correctness" fitness function: this detects when the concurrency model has been violated, which could indicate an attacker spawning unauthorized Claude processes.
- `projects.json` schema validity check: this detects tampering.

The escape hatch via `claude-runner.sh` as the sole Claude invocation point is actually a good security design: centralizing all Claude CLI invocations means you can add security controls (sandbox flags, `--allowedTools`, `--max-budget-usd`) in one place. If you add `--dangerously-skip-permissions` somewhere other than `claude-runner.sh`, the fitness function can catch it.

The atomic state write recommendation (write-to-temp then `mv`) is security-relevant: non-atomic writes create TOCTOU windows where a partial write creates an inconsistent state that the orchestrator might act on incorrectly — including potentially running the wrong project or releasing a semaphore prematurely.

What Analysis F misses from a security standpoint:

- The fitness function for "project path validation" is described as checking that a path exists, not as a security control. It should explicitly validate that the path is under an allowed base directory (`/home/projects/*` only) and does not contain path traversal sequences. This is a different check.
- The symlinked release pattern for zero-downtime upgrades introduces a security concern: if an attacker can write to the `releases/` directory (e.g., via prompt injection that writes to the VPS), they can stage a malicious release and wait for the upgrade process to activate it. The `releases/` directory should be owned by root, not the deploy user.

**Missed gaps:**

- No fitness function for security-specific properties: failed auth attempts per time window, unauthorized command attempts, secrets appearing in logs.

---

### Analysis G (Data Architect)

**Agreement:** Agree

**Reasoning from security perspective:**

Analysis G contains the most important single security finding across all peer analyses: GitHub issue #29158, 335 JSON corruption events in 7 days from concurrent Claude Code instances writing to `~/.claude.json`. This is not just a reliability problem — it is a security problem. A corrupted state file can cause the orchestrator to:

1. Believe a project is idle when it is not (runs a second Claude process for the same project = two processes with the same secrets loaded).
2. Fail to release a semaphore slot correctly (causes incorrect concurrency accounting).
3. Fail to start on VPS reboot (the orchestrator is down but no one knows — a security monitoring gap).

The SQLite-for-state recommendation is correct and I endorse it. WAL mode with `BEGIN IMMEDIATE` for slot acquisition is the right pattern: it eliminates the race condition where two orchestrator cycles both believe a slot is available and each launches a Claude process.

The usage ledger in SQLite is a security artifact I did not propose in my original analysis. A cost record of every Claude session gives the founder an audit trail for anomalous API usage — if a prompt injection causes a runaway session, the cost spike is visible. This is a detection mechanism.

The `projects.json` atomic write via `os.replace()` is security-essential for the `/addproject` command. The original spec had no atomic write — a crash during `/addproject` could leave a partially-written JSON file that the orchestrator cannot parse, causing complete shutdown.

**Missed gaps:**

- The SQLite semaphore implementation is correct but the cleanup logic needs a security note: `acquired_at < NOW() - INTERVAL '30 minutes'` cleanup on startup could be abused if an attacker can manipulate the system clock or the SQLite file (which contains the slot state). The cleanup threshold should be based on `max_turns × estimated_time_per_turn`, not an arbitrary 30 minutes.
- The idempotency key for inbox items (prevent duplicate processing on crash recovery) needs to include the Telegram message_id AND the content hash. Using message_id alone is spoofable if the Telegram API returns the same message_id for different messages in a topic migration scenario.

---

### Analysis H (Domain Architect)

**Agreement:** Partially Agree

**Reasoning from security perspective:**

The domain modeling perspective has an important security implication that Analysis H identifies indirectly: the Anti-Corruption Layer pattern around Telegram. If Telegram concepts (topic_id, message_thread_id) do not leak into the domain model, then a change in Telegram's security model (e.g., new bot token format, new webhook auth requirements) only requires changing the ACL, not the domain logic. This is defense-in-depth at the architecture layer.

The observation that "orchestrator is an application service, not a domain" matters for security: application services should not contain authentication logic. Authentication (verifying the Telegram sender is the authorized founder) belongs in the ACL layer (the TelegramAdapter), not in the orchestrator. If auth is in the orchestrator, a refactoring that modifies the orchestrator might accidentally bypass auth. If auth is in the ACL, it is always the first thing that happens before any domain processing.

The context map showing Portfolio → Pipeline via domain events is security-relevant: if the Portfolio context activates a project, it emits a `ProjectActivated` event. The Pipeline context consumes it. This means the Pipeline context never needs to trust the Portfolio context's claims about "which project should run" — it just responds to events. This reduces the blast radius of a Portfolio context compromise.

**Missed gaps:**

- No security analysis of the ACL layers themselves. The TelegramAdapter ACL is where the `from_user.id` whitelist should live. This is the most important security control in the entire system, and the domain analysis doesn't address it.
- The domain model proposes RoutingKey as an abstraction over Telegram's `message_thread_id`. From a security standpoint, the RoutingKey validation (is this RoutingKey known? does it map to an enabled project?) is a critical authorization check. The analysis doesn't call this out.
- No analysis of what happens when a domain event is forged. The event bus (even if it is an in-memory Python event bus or filesystem inotifywait) can be an attack surface if external input can trigger domain events directly without going through the ACL.

---

## Ranking

**Best Analysis:** E (LLM Architect)

**Reason:** Analysis E produced the most actionable security finding beyond my own research: the `--allowedTools` per-phase restriction and the `--max-budget-usd` cost ceiling. Both are direct security controls (least privilege and financial DoS prevention respectively) that I underweighted in Phase 1. The cross-session contamination finding (#30348) with a concrete mitigation (`CLAUDE_CODE_CONFIG_DIR` per project) is also the kind of empirically grounded, exploitable vulnerability finding that good security analysis requires. Analysis E thinks like an attacker who understands the specific technology stack.

**Worst Analysis:** C (DX/Pragmatist)

**Reason:** The explicit security section contains a factual error — "Pueue groups have separate working directories" as an isolation mechanism — that would lead to a false belief that cross-project isolation is solved when it is not. An analysis that introduces security misconceptions is worse than an analysis that ignores security entirely. A developer reading Analysis C and believing the isolation claim would skip the per-user isolation work I recommended, leaving every project's secrets accessible to every other project's Claude process.

---

## New Questions: Founder Addendum

### Question 1: Multi-LLM Attack Surface — Claude Code + Codex CLI

*Two different API keys, two different auth models. Attack surface expands.*

This is a genuine security concern that none of the peer analyses addressed, including my own Phase 1 research.

**The expanded attack surface:**

Running both Claude Code and Codex CLI on the same orchestrator introduces three new attack vectors:

**Vector 1: Dual secret exposure.** The orchestrator now holds two sets of high-value API credentials: `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`. If the orchestrator process is compromised (e.g., via prompt injection that exfiltrates environment variables), the attacker gets both. The blast radius of a single compromise doubles. Mitigation: each credential should be scoped to only the processes that need it. If a project uses only Claude, it should not have `OPENAI_API_KEY` in its environment. Per-project `.env` files already handle this if scoped correctly.

**Vector 2: Asymmetric auth models create inconsistent security posture.** Claude Code authenticates via `ANTHROPIC_API_KEY` (environment variable, API-key-based, no browser flow required for CLI). Codex CLI supports two auth modes:
- API key mode: `OPENAI_API_KEY` environment variable, same pattern as Claude
- "Sign in with ChatGPT" mode: OAuth browser flow, stores an access token locally

On a headless VPS, Codex CLI requires API key mode (the ChatGPT login flow requires a browser — GitHub issue #3820 confirms this is a known limitation). This means Codex will use `OPENAI_API_KEY`. Both tools can be managed with the same per-project `.env` pattern. However, the auth architecture is different: Anthropic API keys are organization-scoped and can be rotated without disrupting other users; OpenAI API keys are also organization-scoped but the token refresh model differs.

**Vector 3: Different sandboxing models running simultaneously.** This is the critical new finding from research:

- Claude Code: governance via hooks (17 lifecycle event types), bubblewrap/Seatbelt for filesystem isolation
- Codex CLI: governance via OS-level kernel enforcement (Landlock + seccomp on Linux, Seatbelt on macOS)

These are architecturally different security models. Claude Code's hook system can be extended by the orchestrator (you can write hooks that enforce additional security checks). Codex's Landlock+seccomp model operates at the kernel level and is not extensible from the orchestrator layer.

**Critical concern:** If both tools are running on the same VPS in the same project directory, they share the same `CLAUDE_CODE_CONFIG_DIR` (or equivalent) unless explicitly separated. More importantly, their sandboxing models do not compose — having Claude Code bubblewrap active does not protect Codex's execution, and vice versa. You need separate sandboxing configuration for each tool.

**Recommended security model for multi-LLM orchestration:**

```
Per-project environment:
  ANTHROPIC_API_KEY=...  (scoped to this project only)
  OPENAI_API_KEY=...     (scoped to this project only, if Codex enabled)

Per-tool invocation:
  Claude Code: bwrap --bind $PROJECT_DIR --ro-bind ~/.claude claude ...
  Codex CLI:   codex --sandbox (uses Landlock+seccomp natively)

Separate config dirs:
  CLAUDE_CODE_CONFIG_DIR=/var/orchestrator/$PROJECT/claude-state
  # Codex stores state in ~/.codex/ — per-project isolation requires:
  HOME=/var/orchestrator/$PROJECT/codex-home codex ...
```

**Trust boundary addition:** With two LLM CLI tools, the orchestrator must track which tool executed which action for repudiation. The audit log needs a `tool` field: `{timestamp, user_id, project, tool: "claude|codex", command, result}`. Without this, if a prompt injection causes data exfiltration, you cannot determine which tool was exploited.

**Token rotation complexity:** Two sets of API keys means two rotation schedules, two breach notification sources, and two sets of usage monitoring dashboards to watch for anomalous usage. This is non-trivial operational overhead that increases with each additional LLM tool added to the orchestrator.

---

### Question 2: Same VPS as Docker Containers — Shared Kernel Security

*Docker containers for projects + orchestrator on same VPS: security implications.*

This question has a clear security answer that the research confirms: **shared kernel = shared blast radius**.

**The architectural reality:**

If the founder already runs Docker containers for projects on the same VPS, and then adds:
- The orchestrator process (bash/Python, running as deploy user)
- Claude CLI processes (running as deploy user or per-project users)
- Codex CLI processes

...all on the same host, the attack surface diagram looks like:

```
VPS (shared kernel)
├── Docker containers (project apps)
│   └── Each app has its own secrets, database connections
├── Claude CLI processes (direct host, no Docker)
│   └── Running as deploy user
│   └── Has ANTHROPIC_API_KEY, GITHUB_TOKEN, etc.
├── Codex CLI processes (direct host, no Docker)
│   └── Running as deploy user (same user as Claude!)
└── Orchestrator (direct host)
    └── Has ALL secrets to dispatch jobs
```

**The kernel escape scenario:** CVE-2024-21626 (runc, January 2024) allowed container escape via a leaked file descriptor. A compromised Docker container could escape to the host and access Claude CLI processes, their environment variables (API keys), and the `.env` files for every project. This is not a theoretical risk — kernel escape CVEs in container runtimes appear regularly (6-12 months cycle for critical ones).

**Specific risk for this architecture:** If an attacker compromises any of the founder's Docker containers (via a supply chain attack in a project dependency — this is documented in the npm-malware-targets-telegram-bots research from Phase 1), they can potentially:
1. Escape the container via a kernel exploit
2. Read `/proc/$(pgrep claude)/environ` to get the Anthropic API key from the Claude process environment
3. Read per-project `.env` files from the host filesystem
4. Inject commands into the orchestrator's inbox files

**Security recommendation: Separate the trust zones.**

Option A: Keep everything on one VPS, accept the risk, add detection.
- Rationale: For a solo founder running personal projects, the probability of targeted attack is low. The risk is primarily supply chain (compromised npm package) rather than targeted attack.
- Mitigation: Rootless Docker (cannot escape to root-owned processes), seccomp profiles on containers, regular CVE scanning of container images.

Option B: Separate orchestrator VPS from project hosting VPS.
- Rationale: The orchestrator holds all high-value secrets (API keys, GitHub tokens, Telegram bot token). Separating it from the Docker containers limits blast radius. Even if a project container escapes, it cannot reach the orchestrator's secrets.
- Cost: ~$10-20/month for a minimal orchestrator VPS (2GB RAM is sufficient for the orchestrator itself — Claude CLI processes are heavy but still need the project files which live on the project VPS).
- Security gain: The orchestrator VPS has no Docker daemon, no container runtime, no project code. Its only exposure is SSH, the Telegram bot, and outbound Claude/Codex API calls.

**My recommendation:** For Phase 1 (consulting, 2-3 projects), Option A is acceptable IF rootless Docker is used and containers are treated as potentially hostile. The orchestrator process should NOT run inside a Docker container on the same host as the project containers — this creates confusing trust boundary overlap. The orchestrator runs directly on the host; project apps run in Docker; Claude CLI processes run directly on the host under per-project users.

The separation point: orchestrator and Claude CLI = host processes; project applications = Docker containers. Never mix.

---

### Question 3: Codex CLI Security Model vs. Claude Code Security Model

*Differences that matter for this orchestrator.*

This is where the research produced genuinely new information beyond Phase 1.

**Claude Code's security model: hooks-based governance (application layer)**

```
Anthropic API → Claude reasoning
     ↓
17 lifecycle hook events:
  PreToolUse, PostToolUse, Stop, etc.
     ↓
Hook scripts (deterministic, run by you)
     ↓
bubblewrap/Seatbelt filesystem isolation (OS layer, optional)
```

Claude Code's primary governance is at the application layer via hooks. Hooks are shell scripts or Python scripts that the operator controls. This means:
- The orchestrator CAN enforce security via hooks (e.g., a hook that blocks any `Bash` tool call containing `curl attacker.com`)
- Hooks run as the same user as Claude — if Claude is compromised, the hooks are also potentially compromised
- Bubblewrap is optional and must be explicitly configured

**Codex CLI's security model: kernel-enforced sandboxing (OS layer)**

```
OpenAI API → GPT-5.4 reasoning
     ↓
Landlock (Linux kernel filesystem isolation)
+ seccomp (syscall filtering)
     ↓
Application sees a restricted kernel interface
```

Codex's primary governance is at the OS/kernel layer. This means:
- Sandboxing is ON by default (full sandbox mode is the default for autonomous operation)
- The orchestrator CANNOT extend or override Codex's sandbox via hooks (no hook system)
- A compromised Codex process cannot escape its sandbox even with root-level code execution inside the sandbox (Landlock persists across privilege escalation within the sandbox)
- Codex's sandbox is harder to bypass because it operates below the application layer

**Security comparison for this orchestrator:**

| Property | Claude Code | Codex CLI |
|----------|-------------|-----------|
| Default sandboxing | Optional (must enable bubblewrap) | On by default |
| Orchestrator-extensible security | Yes (hooks) | No |
| Prompt injection blast radius | Larger (no default sandbox) | Smaller (default kernel sandbox) |
| Audit hooks | Yes (17 lifecycle events) | No |
| Cross-project contamination risk | Higher (shared config dir) | Lower (separate HOME isolation) |
| Secret exfiltration via env | Possible without bubblewrap | Harder with Landlock (network restricted) |

**The critical implication for orchestrator design:**

If the orchestrator runs Claude Code without bubblewrap and Codex with its default sandbox, the attack surface is asymmetric. An attacker who can control which tool processes a given task (e.g., via a prompt in the task specification) can preference Claude Code for tasks where they want broader filesystem access.

**Recommendation:** When both tools are available:
1. Enable Claude Code bubblewrap to match Codex's default sandboxing level.
2. Define per-task tool routing that cannot be overridden by task content (routing decisions happen in the orchestrator based on project config, not based on LLM-generated content).
3. For high-sensitivity operations (any task involving billing code, authentication code, secret rotation), force Claude Code bubblewrap regardless of which tool is "preferred" for that project.

**The --dangerously-skip-permissions asymmetry:** Claude Code has `--dangerously-skip-permissions` which disables all permission prompts. This flag should never appear in any orchestrated invocation. Codex CLI has no equivalent flag — its sandbox cannot be disabled via a runtime argument (you would need to change the system-level Landlock configuration). This makes Codex safer against accidental or attacker-induced permission disabling.

---

## Revised Position

**Revised Verdict:** Partially changed from Phase 1.

**Change Reason:**

Three things from peer analyses revised my position:

1. **From Analysis E:** `--allowedTools` per-phase is a stronger mitigation than I credited. Combined with structural prompt injection defense, it creates genuine defense-in-depth at the LLM tool layer. I am now more confident that prompt injection can be mitigated to an acceptable level without mandatory bubblewrap, IF `--allowedTools` is scoped tightly per phase.

2. **From Analysis G:** The SQLite-for-state recommendation resolves a race condition I identified (state file tampering) more elegantly than my `projects.json` integrity check approach. SQLite with `BEGIN IMMEDIATE` is the correct primitive for the slot acquisition problem. I should have recommended this in Phase 1.

3. **From research on Codex CLI:** The Landlock+seccomp default sandboxing model is meaningfully stronger than Claude Code's optional bubblewrap model. For cross-project isolation, running Codex with default sandbox is preferable to running Claude Code without bubblewrap. The orchestrator's tool routing should factor in sandboxing level when assigning tasks to tools.

**Final Security Recommendation:**

The security priority stack from Phase 1 remains valid. Two additions after cross-critique:

**Addition 1 (P1): SQLite replaces both `.orchestrator-state.json` and `flock` semaphore.**
Analysis G's evidence (335 corruption events, GitHub #29158) establishes that daemon-frequency JSON writes are unreliable. SQLite with WAL mode and `BEGIN IMMEDIATE` for slot acquisition is the correct architecture. This is not just a reliability improvement — it eliminates a class of state corruption that can cause the orchestrator to launch duplicate Claude processes and double-spend API budget.

**Addition 2 (P1): `--allowedTools` per-phase scoping.**
Analysis E's finding: restricting inbox-processor to `Read,Glob,Write` eliminates the RCE path from prompt injection during triage. The orchestrator's Claude invocations should have explicit tool allowlists, not full tool access. This is least privilege applied correctly to LLM agents.

**Revised Priority Stack (additions in bold):**

| Priority | Fix | Source |
|----------|-----|--------|
| P0 | Telegram `from_user.id` whitelist | Phase 1 |
| P0 | Claude `--max-turns` + `timeout` | Phase 1 |
| **P1** | **SQLite for runtime state (replaces JSON + flock)** | Analysis G evidence |
| P1 | Local whisper.cpp instead of OpenAI API | Phase 1 |
| P1 | Prompt injection: structural separation + `--allowedTools` per phase | Phase 1 + Analysis E |
| P1 | Per-project Unix user isolation (or `CLAUDE_CODE_CONFIG_DIR` per project minimum) | Phase 1 + Analysis E (#30348) |
| **P1** | **Multi-LLM: separate API keys per project, separate HOME per tool** | New question research |
| P2 | Fine-grained GitHub PAT per project | Phase 1 |
| P2 | Audit log with `tool` field for multi-LLM traceability | New question research |
| P2 | `projects.json` path validation on write | Phase 1 |
| P2 | Docker containers on same VPS: rootless Docker, accept risk or separate VPS | New question research |
| P3 | systemd credentials for bot secrets | Phase 1 |
| P3 | Rate limiting on bot commands | Phase 1 |
| P3 | Codex default sandbox (on by default), Claude Code bubblewrap (enable explicitly) | New question research |

---

## References

- [Claude Code vs Codex CLI — Security Model Comparison](https://blakecrosley.com/blog/claude-code-vs-codex) — hooks vs. kernel-level governance
- [Codex Authentication — API Key vs ChatGPT Sign-in](https://developers.openai.com/codex/auth/) — headless VPS requires API key mode
- [Container Security: Shared Kernel Risks](https://edera.dev/stories/what-we-wish-we-knew-about-container-isolation) — kernel escape blast radius
- [Container Filesystem Isolation Multi-Tenant Workloads](https://systemweakness.com/i-am-breaking-my-head-in-analyzing-container-filesystem-isolation-for-multi-tenant-workloads-so-f4982a44d81f) — defaults protect trusted workloads; untrusted requires VM isolation
- [Claude Code Sandboxing Guide](https://claudefa.st/blog/guide/sandboxing-guide) — bubblewrap setup on Linux
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [Trail of Bits: Prompt Injection to RCE](https://blog.trailofbits.com/2025/10/22/prompt-injection-to-rce-in-ai-agents/)
- [GitHub #29158: ~/.claude.json corruption](https://github.com/anthropics/claude-code/issues/29158)
- [GitHub #30348: Cross-session contamination](https://github.com/anthropics/claude-code/issues/30348)
