# Security Architecture Research

**Persona:** Bruce (Security Architect)
**Focus:** Threat modeling, attack surface, STRIDE, defense-in-depth
**Mode:** Retrofit — brownfield system with active incidents
**Date:** 2026-05-23

---

## Research Conducted

**Note:** External search (Exa) unavailable — credits exhausted. Research conducted
via direct code analysis of the live system:

- `/home/dld/projects/dld/scripts/vps/callback.py` (1374 LOC) — primary gate
- `/home/dld/projects/dld/scripts/vps/lifecycle.py` (602 LOC) — CAS writer
- `/home/dld/projects/dld/scripts/vps/orchestrator.py` (667 LOC) — dispatcher
- `/home/dld/projects/dld/scripts/vps/spec_operator.py` — privileged CLI
- `/home/dld/projects/dld/scripts/vps/db.py` — SQLite state
- `/home/dld/projects/dld/ai/audit/deep-audit-report.md` — 85 findings from 6-persona audit
- `/home/dld/projects/dld/ai/architect/architecture-agenda.md` — retrofit scope

All claims below are anchored to specific file:line evidence from the audit report or
direct code read. "Quote-before-claim" is enforced throughout.

**Standard references applied from knowledge base (no live search needed):**
- STRIDE (Microsoft SDL threat categories)
- OWASP Top 10 (2021): A01 Broken Access Control, A02 Cryptographic Failures, A05 Security Misconfiguration, A08 Software and Data Integrity Failures, A09 Security Logging and Monitoring Failures
- MITRE ATT&CK for CI/CD: TA0001 Initial Access, TA0004 Privilege Escalation, TA0040 Impact
- CWE-732 (Incorrect Permission Assignment), CWE-522 (Insufficiently Protected Credentials), CWE-502 (Deserialization of Untrusted Data via YAML)

---

## Kill Question Answer

**"What's the threat model? What's the attack surface?"**

The system is a multi-project AI orchestration daemon running as a single Unix user (`dld`)
on a VPS. It has no network-facing ports of its own — but it does have a Telegram bot interface,
a local pueue daemon, filesystem-based authentication, and a git-based state store shared across
10+ projects.

The attack surface is almost entirely **insider/local**. The primary threat actors are:

1. **A compromised managed project** (malicious spec content influencing orchestrator decisions)
2. **A compromised Claude/Codex agent** (arbitrary code execution within a task — already the intended capability)
3. **A Telegram token holder** (anyone who obtained `TELEGRAM_BOT_TOKEN` from the public git history — confirmed incident)
4. **An attacker with VPS shell access** (either via compromised `dld` account or another user on the same machine)

---

## STRIDE Analysis by Component

### Component 1: Lifecycle Writer (lifecycle.py + git CAS)

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — writer claims false identity via `by=` parameter | High | `_ALLOWED_WRITERS = frozenset({"callback", "orchestrator", "spark", "operator", ...})` — this is a string check, not a cryptographic assertion. Any caller can pass `by="callback"` | Partially — string allowlist exists at lifecycle.py:49-51, but there is no verification that the Python process *is* callback. Anyone who can `import lifecycle` can write as "callback". |
| **Tampering** — directly overwrite lifecycle YAML in working tree | High | `migrate_backlog_to_lifecycle.py:224-225` uses `Path.write_text()` directly, bypassing CAS entirely (Coroner audit finding, confirmed in deep-audit-report.md Root 2 table row #5) | No — the CAS path is optional; `Path.write_text()` is a persistent bypass that survives as dead code |
| **Tampering** — CAS race exploitation | Medium | `git update-ref refs/heads/{branch} new_commit head_sha` at lifecycle.py:233 — this is correct CAS, but with only 3 retries and no distributed lock between machines | Partially — within one machine the `_write_lock` (threading.Lock) prevents concurrent writes. Multi-machine: git CAS is the only guard, push is best-effort (debug log only, lifecycle.py:265) |
| **Repudiation** — false identity in audit trail | High | `reconcile_orphans` writes lifecycle with `by="callback"` (lifecycle.py:551) but is called from orchestrator — audit trail states callback wrote something orchestrator wrote (deep-audit-report.md Root 2, row #3) | No — this is a confirmed misattribution in production today |
| **Information Disclosure** | Low | YAML files contain spec_id, status, transitions with timestamps. No secrets. | Accepted |
| **DoS** — infinite hang blocking all writes | High | `_run()` in lifecycle.py:77-88 has no timeout. All 8 git plumbing ops can hang indefinitely under `_write_lock`, blocking the entire callback process for all subsequent pueue completions (deep-audit-report.md finding #12) | No |
| **Elevation of Privilege** — WT sync allows stale blob injection | Medium | After CAS write, `git checkout-index --force --` uses the main index, but the private `GIT_INDEX_FILE` was deleted in the `finally` block. This causes checkout-index to read stale data, leaving 13 deleted files in awardybot WT (deep-audit-report.md finding #10) | No — best-effort only, `assert_clean_lifecycle_tree` is the backstop |

### Component 2: callback.py (Gate + Dispatcher)

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — pueue task label forgery | Medium | callback.py receives `pueue_id`, `group`, `result` from pueue daemon via CLI. Any local process that can invoke `python3 callback.py <id> <group> <result>` can trigger the gate. | Partially — pueue restricts who can add tasks (see Component 3), but the callback itself has no authentication |
| **Tampering** — audit JSONL injection | High | `callback-audit.jsonl` is a plaintext append-only file at `SCRIPT_DIR/callback-audit.jsonl`. orchestrator.py:520 reads the last 200 lines of this file to make dispatch decisions (skip if recently blocked/done). An attacker who can write to this file can suppress dispatch of a specific spec_id for 30 minutes. | No — the file has no signature, no checksum, no append-only guarantee at the filesystem level |
| **Tampering** — spec file content injection | High | callback.py:1093 reads the spec .md file to extract `## Allowed Files`. The spec file lives in the project WT, which is writable by any agent running in that project. A malicious agent could modify allowed files list to include files outside its scope. | Partially — Rule 3 (project boundary) and Rule 8 (cross-project) exist, but `_parse_allowed_files` has no integrity check on the spec file content |
| **Repudiation** — bare exceptions swallow errors | High | callback.py has 19 bare `except Exception` (deep-audit-report.md finding #17). Gate decisions that fail silently are not recorded, making it impossible to audit "why did spec X stay queued?" | No |
| **Information Disclosure** | Low | Logs at SCRIPT_DIR contain task labels, spec IDs, project paths. No secrets in logs (confirmed by code review). | Accepted |
| **DoS** — circuit breaker manipulation | Medium | Circuit breaker trips on >3 demotes in 10 minutes. A malicious project repeatedly triggering false demotes via spec content could trip the circuit breaker, halting all dispatch for all projects. | Partially — TECH-169 exists but threshold is not project-scoped |
| **Elevation of Privilege** — `_reset_circuit_cli` accessible via spec_operator | Medium | spec_operator.py:116 calls `callback._reset_circuit_cli()` directly — a private function imported cross-module. Any process with filesystem access to scripts/vps/ can reset the circuit breaker by running `python3 spec_operator.py reset-circuit` with zero authentication. | No |

### Component 3: pueue Daemon

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — any local user can enqueue tasks | High | pueue communicates via a Unix socket at `~/.local/share/pueue/pueue.sock` (default). Socket permissions are user-level: only the `dld` user can reach it. On a single-tenant VPS with one user this is acceptable. On a multi-tenant system this would be critical. | Accepted for single-tenant — if VPS is compromised to another user, this becomes critical |
| **Tampering** — pueue task injection via writable socket | Medium | If attacker gains `dld` shell access (e.g., via compromised Telegram token → bot command injection), they can `pueue add` arbitrary tasks which callback.py will process | No structural isolation — pueue access = task execution |
| **DoS** — task queue flooding | Medium | No rate limit on pueue task addition. Circuit breaker only guards demote-storm, not task-addition storm. | Partial |
| **Elevation of Privilege** — pueue tasks run as `dld` | Accepted | pueue is not a privilege boundary — all tasks run as the same user. This is by design for a single-user orchestrator. | Accepted — threat model assumes `dld` user is the trust boundary |

### Component 4: SQLite (orchestrator.db)

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** | N/A | No authentication layer | Accepted — local process only |
| **Tampering** — DB_PATH redirection | High | `DB_PATH = os.environ.get("DB_PATH", ...)` at db.py:19. A process that controls the environment (e.g., a malicious test runner) can point orchestrator at an arbitrary database. Confirmed incident: today's bug 5 was test poisoning prod-DB (deep-audit-report.md Root 4). | No |
| **Tampering** — direct file modification | Medium | `orchestrator.db` is a plaintext SQLite file at `SCRIPT_DIR/orchestrator.db`. No encryption at rest. Anyone with filesystem read access gets the full DB. | Accepted — single-tenant, filesystem access = full trust |
| **Repudiation** | Medium | `task_log` has no append-only guarantee. A sufficiently privileged attacker can DELETE rows. | Accepted |
| **Information Disclosure** | Low | DB contains project_id, task labels, pueue IDs, timing, cost_usd. No credentials stored in DB. | Accepted |
| **DoS** — unbounded table growth | Medium | `task_log`, `callback_decisions`, `sdk_post_result_errors` have no retention. Will grow indefinitely (deep-audit-report.md finding 28 area). | No |

### Component 5: Telegram Bot Interface

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — token impersonation | Critical | `TELEGRAM_BOT_TOKEN` was committed plaintext to `scripts/vps/.env` in a git-tracked file (deep-audit-report.md Scout finding #7, architecture-agenda.md line 69). Token is **public** — anyone with git access to this repo has it. | No — token NOT yet rotated (confirmed still active as of audit) |
| **Tampering** — command injection via Telegram | High | If the bot processes user commands that become shell arguments or spec content, a malicious Telegram user can inject data that reaches the orchestrator pipeline | Unknown — event_writer.py is the integration point; full bot implementation not audited here |
| **Repudiation** | Medium | Telegram message sender identity cannot be cryptographically verified by the bot itself — only Telegram's platform authenticates users | Accepted — Telegram user IDs provide sufficient audit trail for this threat level |
| **Information Disclosure** — token allows bot enumeration | High | With the token, an attacker can call `getUpdates` to read all messages sent to the bot, including operator commands and spec IDs | Active risk — token is public |
| **DoS** — bot flooding | Medium | Telegram can throttle malicious bots, but the bot itself has no rate limiting | Low priority given token exposure is the more urgent issue |

### Component 6: spec_operator.py (Privileged CLI)

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — `--by` is honor system | High | `spec_operator.py:134` `choices=["operator", "qa", "audit", "autopilot", "spark"]` — this is argparse validation only. Any shell user can pass `--by=operator`. There is no verification that the caller is who they claim to be. | No |
| **Elevation of Privilege** — force-done bypasses TECH-166 guard | Critical | `cmd_force_done` at spec_operator.py:107 explicitly bypasses the implementation guard. The docstring says so: "bypasses TECH-166 guard". The system's primary integrity check can be circumvented by anyone with filesystem access running one CLI command. | No |
| **Tampering** — can set any status for any spec | High | `_set_status` accepts any `target` string that reaches `write_lifecycle`. Combined with filesystem access = full status control. | Partially — `write_lifecycle` validates `by` against `_ALLOWED_WRITERS`, but target status is not validated against a state machine |

### Component 7: Multi-Project Isolation

| Threat | Risk | Evidence | Mitigated? |
|--------|------|----------|-----------|
| **Spoofing** — Project A spec claims Project B spec_id | Medium | Rule 8 (`pueue_has_active_spec`) checks only that the spec_id is not currently live in pueue. It does not verify the spec belongs to the project dispatching it. (orchestrator.py:167-195) | Partially — Rule 3 in verify_status_sync checks `lifecycle.read_lifecycle(project_path, spec_id)` — if the yaml doesn't exist in Project B, it's a noop. But this check is in callback, not at dispatch time. |
| **Tampering** — spec content in Project A references files in Project B | High | `_parse_allowed_files` parses the `## Allowed Files` section from the spec markdown. There is no validation that listed paths are within the project directory. A spec could list `../other-project/sensitive-file` as an allowed file, and the `_commit_stats` git log would scan that path. | Partially — git log `--` only scans within the repo, so cross-repo path traversal is blocked by git semantics. But within the same repo, a spec could reference any file. |
| **Tampering** — bootstrap reads dirty WT backlog.md | Critical | `orchestrator.py:295` reads `ai/backlog.md` from the working tree (not HEAD) for bootstrap_new_specs. If a malicious agent writes to backlog.md before bootstrap runs, it can cause bootstrap to create lifecycle yamls with arbitrary initial statuses. | No — confirmed root cause of today's 15 fake-done flips (deep-audit-report.md Root 1) |
| **Repudiation** — cross-project audit JSONL shared file | Medium | All projects share one `callback-audit.jsonl` file. A high-volume project can push old entries beyond the 200-line scan window, effectively erasing anti-recency protection for another project's spec. | No |

---

## Attack Surface Summary

**External Entry Points:**

| Entry Point | Authentication | Risk |
|-------------|---------------|------|
| Telegram Bot | Bot token (compromised) | Critical |
| pueue Unix socket | OS-level user match | Medium (single-tenant) |
| spec .md files (read by agents) | None — filesystem | High |
| backlog.md WT (read by bootstrap) | None | Critical |
| callback-audit.jsonl (read by scan_queued) | None — append-only by convention only | High |
| spec_operator.py CLI | None — any shell user | High |
| DB_PATH env override | None | High |

**Trust Boundaries:**

| Boundary | Trust Assumption | Verified? |
|----------|-----------------|----------|
| pueue daemon → callback.py | pueue is honest about task completion | Partially (socket is user-locked) |
| callback.py → lifecycle.py | caller is the declared identity | No — string check only |
| orchestrator.py → backlog.md | file content matches committed state | No — reads dirty WT |
| scan_queued → callback-audit.jsonl | file is unmodified since callback wrote it | No |
| managed project agents → spec .md | agents don't modify spec content maliciously | No |
| Telegram → event_writer | message sender is authorized | No — token is compromised |

---

## Already-Compromised: Rotate Now

These are not "potential vulnerabilities" — they are confirmed current incidents or
confirmed non-functional security controls:

### Incident 1: TELEGRAM_BOT_TOKEN is Public

**Evidence:** deep-audit-report.md Scout finding #7 — `TELEGRAM_BOT_TOKEN` committed plaintext to `scripts/vps/.env`. architecture-agenda.md line 69: "TELEGRAM_BOT_TOKEN коммитнут открытым текстом в scripts/vps/.env (git-tracked, не в .gitignore)".

**Exposure scope:** Anyone with read access to this git repository has the token. The token allows:
- Reading all messages sent to the bot (getUpdates API)
- Sending messages as the bot to any chat it is in
- Depending on bot capabilities: triggering operator commands if the bot processes them

**Required action (before any other work):**
1. Rotate the token immediately via BotFather (`/revoke`)
2. Remove .env from git tracking: `git rm --cached scripts/vps/.env`
3. Add `scripts/vps/.env` to `.gitignore`
4. Move secret to Nexus / environment variable only
5. Audit git history — the old token is in every clone of the repo

**Note:** Rotating the token does not remove it from git history. The history needs to be cleaned (git filter-repo or BFG Repo Cleaner) if this repo is or may become public.

### Incident 2: Identity Enforcement is Non-Functional Everywhere

**Evidence:** deep-audit-report.md Root 2 and findings #4, #5: "pre-commit-lifecycle-guard.mjs мёртв — `core.hooksPath=.git/hooks` во всех 3+ репо, guard в `.git-hooks/`. Не работает нигде, даже в DLD."

The pre-commit hook is the enforcement mechanism for lifecycle write identity. It is not installed in any repository. This means:
- Any agent, script, or human with filesystem access can write arbitrary content to `ai/lifecycle/*.yaml`
- The `_ALLOWED_WRITERS` check in lifecycle.py is a string comparison — it validates the `by=` argument you pass, not who you are
- `migrate_backlog_to_lifecycle.py` bypasses even this string check via `Path.write_text()` (deep-audit-report.md Root 2, row #5)

**Required action:**
1. Install pre-commit hook in all 10 managed projects via a registration script
2. Fix `core.hooksPath` to point to `.git-hooks/` in all repos
3. Remove or disable `migrate_backlog_to_lifecycle.py` (it's a one-shot migration that already ran — keeping it is pure liability)

### Incident 3: orchestrator.py reads backlog.md from dirty WT (active exploit path)

**Evidence:** deep-audit-report.md Root 1, specifically "orchestrator.py:295 читает backlog.md из dirty WT". This was the direct cause of 15 fake-done lifecycle flips today.

This is not just a data quality bug — it is an integrity attack vector: any agent that can write to `ai/backlog.md` in a project's working tree before bootstrap runs can influence which specs get bootstrapped and with what initial status. The attack requires no special access beyond what any Claude autopilot task already has.

**Required action:**
1. `bootstrap_new_specs` must read from HEAD (`git show HEAD:ai/backlog.md`) or be removed entirely in favor of Spark as the sole lifecycle creator
2. Add `Rule 1 gate` (`_is_done_on_develop` check) to any bootstrap path that creates lifecycle yamls with non-`queued` status

---

## Proposed Security Decisions

### Authentication Architecture

The system is internal/single-tenant. Full PKI or OAuth is inappropriate. However, the existing identity system is broken. The right fix is to eliminate the fiction of software identity and replace it with a verifiable mechanism.

**Recommended approach: git signed commits as identity**

Instead of `by="callback"` string in YAML, identity is `git log --format="%ae %GS" -- ai/lifecycle/{spec_id}.yaml` — the git author email and GPG signature of the committing process.

This requires:
- A dedicated GPG key for the orchestrator service (callback/lifecycle)
- `GIT_COMMITTER_EMAIL` and `GIT_COMMITTER_NAME` set per-process
- No signature verification on reads — only on writes (via pre-commit hook)

**Pragmatic alternative (lower cost):** eliminate `by=` from the public API and derive it from the calling context (process name, environment variable set at service startup). The current `_ALLOWED_WRITERS` check is security theater — replace it with a process-level capability token (a random secret set in the systemd unit file, required by lifecycle.write_lifecycle).

**Actor Types:**

| Actor | Current Auth | Recommended Auth | Priority |
|-------|-------------|-----------------|----------|
| callback (systemd service) | None — any process | Process token (env var in systemd unit) | P1 |
| orchestrator (systemd service) | None | Same process token | P1 |
| spec_operator (human CLI) | None | require sudo OR separate token | P1 |
| managed project agents | None | Project-scoped env token | P2 |
| Telegram bot | Compromised token | Rotated token + chat ID allowlist | P0 |

---

### Authorization Model

The current implicit model: "if you have filesystem access, you have all permissions."

**Recommended RBAC (minimal viable):**

| Role | Permissions | Enforcement |
|------|-------------|------------|
| orchestrator-service | read lifecycle, write lifecycle (queued→in_progress), dispatch pueue | Process token in systemd |
| callback-service | read lifecycle, write lifecycle (any→done/blocked), write audit JSONL | Process token in systemd |
| operator-human | force-done, demote, reset-circuit | Explicit `sudo python3 spec_operator.py` (requires TTY) |
| project-agent (Claude task) | write spec .md, write project code | Sandboxed to project directory only |

**Privilege Escalation Prevention:**
- `force-done` is the most dangerous operation — it bypasses all gates. It should require a separate confirmation step or a TTY check (`if not sys.stdin.isatty(): reject`)
- `reset-circuit` resets a safety mechanism — same treatment

---

### Data Protection Strategy

| Data Type | Sensitivity | Current Protection | Recommended |
|-----------|------------|-------------------|-------------|
| TELEGRAM_BOT_TOKEN | Critical | None (plaintext in tracked .env) | Nexus + env-only + rotate NOW |
| lifecycle YAML | Medium | git CAS (integrity) but no confidentiality | Accepted — no PII |
| orchestrator.db | Medium | Filesystem permissions (dld user only) | Accepted — add WAL checkpoint + periodic backup |
| callback-audit.jsonl | Medium | None — writable by any process as dld | HMAC append signature (see below) |
| pueue task labels | Low | pueue socket user-lock | Accepted |
| claude-runner.py stderr logs | Low | File at SCRIPT_DIR | Ensure not world-readable |

**Audit JSONL integrity (callback-audit.jsonl):**

The file influences dispatch decisions. It should be tamper-evident. Recommended: append an HMAC-SHA256 of each line using a key stored in the systemd environment. The reader (`scan_queued`) skips lines with invalid HMAC. This doesn't prevent injection but makes injection detectable.

Cost: 10 lines of code. Eliminates the "suppress dispatch by injecting fake entries" threat.

---

### Defense-in-Depth Layers

**Current state:** There is effectively ONE security layer — filesystem user ownership. Everything else (identity enforcement, pre-commit hooks, process tokens) is either not deployed or broken.

**Proposed layered defense:**

**Layer 0: Credential hygiene (do now)**
- Rotate TELEGRAM_BOT_TOKEN
- Remove .env from git
- Audit all secrets currently in git history

**Layer 1: Process identity (low cost, high value)**
- Set `ORCHESTRATOR_PROCESS_TOKEN=<random-64-bytes>` in systemd unit
- `lifecycle.write_lifecycle()` requires this token in the calling environment
- This does NOT stop a compromised Claude agent that inherits the environment — it stops accidental writes from test runners, migration scripts, etc.

**Layer 2: Input validation at trust boundaries**
- `bootstrap_new_specs`: read from HEAD, not WT
- `scan_queued`: validate JSONL lines are well-formed JSON before processing
- `_parse_allowed_files`: reject paths containing `..` or paths outside the project directory
- `spec_operator.py force-done`: require TTY check + explicit confirmation prompt

**Layer 3: Pre-commit enforcement (deploy to all managed projects)**
- `register-project.sh` script that sets `core.hooksPath=.git-hooks` and copies the lifecycle guard hook
- This is the only control that prevents unauthorized lifecycle writes from any process, not just well-behaved ones

**Layer 4: Audit and detection**
- Promote `_push_best_effort` failures from DEBUG to WARNING (currently invisible in INFO logs)
- Alert when `bootstrap_new_specs` creates more than N yamls in one pass (mass-bootstrap anomaly detection)
- HMAC on callback-audit.jsonl entries
- Daily `git log --format="%ae %H %s" -- ai/lifecycle/` anomaly check to detect unexpected writers

**Layer 5: Isolation (longer term)**
- DB_PATH should not be overridable from environment in production — hardcode after setup or require a separate configuration file not readable by agents
- Consider running callback and orchestrator as separate systemd services (they currently share the same process context when imported)

---

### Supply Chain Security

**git plumbing as security primitive:**

The CAS approach in lifecycle.py is sound for single-machine use. The `git update-ref` with expected-value is a genuine atomic compare-and-swap at the git object store level. The weakness is:
- Multi-machine: no distributed lock, only eventual consistency via push/pull
- The "push best-effort at DEBUG" means divergence is silent

**Python dependencies:**

No CVE scan was performed (Exa unavailable). Known risk areas:
- `pyyaml`: `yaml.safe_load` is used correctly — this is the safe API. `yaml.load` without Loader would be a CWE-502 risk. Code is correct here.
- `claude_agent_sdk`: third-party SDK with `stderr` callback (BUG-188 Layer 2). SDK compromise = arbitrary code in the callback process context. This is an accepted risk for an AI-first system.
- `subprocess` calls: all use list form (not shell=True). No shell injection surface identified in the reviewed code.

**Managed project agents as supply chain:**

Each Claude/Codex agent running in a managed project is a third-party process with write access to that project's filesystem. This is the intended design. The security model must assume agents are capable but not malicious — the controls exist to limit blast radius of an agent mistake, not to defend against a deliberately adversarial agent.

---

## Threat Categories: Accept vs Mitigate

### Accept (threat is present but within acceptable risk given context)

| Threat | Reason Accepted |
|--------|----------------|
| pueue socket access (local user) | Single-tenant VPS — user `dld` is the trust boundary. If `dld` is compromised, all controls fail anyway. |
| orchestrator.db confidentiality | No sensitive data stored. Integrity is more important than confidentiality here. |
| YAML file confidentiality | lifecycle YAMLs contain no PII or credentials. Integrity is the concern, not secrecy. |
| Agent arbitrary code execution within project | This is the intended capability. Sandbox is the project directory. |
| Multi-machine git CAS without distributed lock | Current deployment is single-machine. Accept until multi-machine is actually deployed. |
| spec_lint.py zombie validator | Low security impact — produces false confidence about spec format compliance, not a security boundary. |

### Must Mitigate (not accepted)

| Threat | Required Mitigation | Priority |
|--------|--------------------|---------| 
| TELEGRAM_BOT_TOKEN in git | Rotate + remove from history | P0 (now) |
| backlog.md WT read in bootstrap | Read from HEAD only | P0 (now, caused today's incident) |
| Pre-commit hook not deployed | register-project.sh | P0 |
| force-done with no authentication | TTY check + confirmation | P1 |
| audit JSONL not tamper-evident | HMAC per line | P1 |
| DB_PATH env override | Hardcode in prod or require config file | P1 |
| `_push_best_effort` silent failures | Promote to WARNING | P1 |
| git plumbing calls without timeout | Add 30s timeout to `_run()` | P1 (DoS) |
| migrate_backlog_to_lifecycle.py Path.write_text bypass | Remove file or disable | P1 |
| reconcile_orphans misattributed as `by="callback"` | Fix identity to `by="orchestrator"` | P2 (audit trail) |

---

## Cross-Cutting Implications

### For Domain Architecture

The security analysis confirms what the domain analysis will find: the god module pattern in callback.py is a security liability. When one module holds 7 responsibilities, every security control touches all 7 responsibilities, making it harder to reason about the security boundary of any one of them.

Bounded context separation proposed by the domain architect will directly improve security: a dedicated `gate.py` module with explicit inputs/outputs is easier to add input validation and audit logging to than 202 lines inside `verify_status_sync`.

### For Data Architecture

The three-store split-brain (lifecycle yaml HEAD + backlog.md WT + spec body) creates three different attack surfaces for status manipulation. Eliminating two of the three is not just a data quality improvement — it removes two attack vectors simultaneously.

### For Operations

From a security ops standpoint, the audit infrastructure is broken:
- 5 hours elapsed between the bootstrap flip incident and detection (deep-audit-report.md)
- The circuit breaker is the only automated response, and it fires only on mass-demotes, not on mass-bootstraps
- `_push_best_effort` at DEBUG means multi-machine divergence is silent until an operator manually checks git status

The operations architect (Charity) should know: the security monitoring gap is equivalent to the observability gap here. Fixing one fixes the other.

### For API Design

spec_operator.py is a privileged CLI with no authentication. It imports a private function from callback.py (`_reset_circuit_cli`). This cross-module coupling of a privileged operator tool to a private function of the gate module is an architectural anti-pattern and a security smell. If callback.py is decomposed, spec_operator.py's dependency graph needs to be revisited.

---

## Critical Issues (Prioritized)

### P0: Rotate TELEGRAM_BOT_TOKEN — Active Incident

**Attack scenario:** Attacker calls `https://api.telegram.org/bot{TOKEN}/getUpdates` from any machine. Reads all bot messages including operator commands. Sends arbitrary bot messages to any chat the bot is in.

**Fix:** `BotFather → /mybots → [bot] → API Token → Revoke`. Then Nexus. Then `git rm --cached scripts/vps/.env` + `.gitignore` entry. Then `git filter-repo --path scripts/vps/.env --invert-paths` to clean history.

### P0: bootstrap_new_specs reads dirty WT — Active Exploit Path

**Attack scenario:** Claude agent completes a task, writes to `ai/backlog.md` (it has write access to the project), bootstrap runs in the next orchestrator cycle and creates lifecycle yamls reflecting the agent-modified backlog content. Agent can flip any spec from `queued` to `done` without triggering the TECH-166 gate.

**Fix:** Replace `Path(project_dir) / "ai" / "backlog.md"` read in orchestrator.py with `git show HEAD:ai/backlog.md` subprocess call. Or remove bootstrap_new_specs entirely (Spark creates the yaml directly).

### P1: force-done Has No Authentication

**Attack scenario:** Any process that can exec Python and has access to `scripts/vps/` can call `python3 spec_operator.py force-done <any-project> <any-spec> "reason" --by=operator`. The TECH-166 guard is bypassed. This is the most powerful command in the system and requires zero credentials.

**Fix:** Add `if not sys.stdin.isatty(): sys.exit(2)` at the top of `cmd_force_done`. Require explicit `--confirm=SPEC_ID` flag (double-entry confirmation). Log the calling process name and environment.

### P1: audit JSONL is Tamper-Without-Detection

**Attack scenario:** Attacker (or a misbehaving agent) appends a fake entry to `callback-audit.jsonl`:
`{"spec_id": "FTR-999", "target_out": "blocked", "ts": "2026-05-23T10:00:00Z", "reason": "failed_gate"}`

scan_queued in orchestrator.py will suppress dispatch of FTR-999 for the next 30 minutes. This can be used to selectively delay execution of any spec without triggering the circuit breaker.

**Fix:** HMAC-SHA256 each line using a 32-byte key in the systemd environment. Reader skips unsigned lines (or treats them as suspicious). Cost: ~15 LOC.

### P1: git plumbing calls without timeout — DoS

**Attack scenario:** `git push origin develop` hangs indefinitely (network unreachable, git lock, etc.) while holding `_write_lock`. All subsequent lifecycle writes block. All subsequent pueue task completions hang. Orchestrator effectively DoS'd.

**Fix:** Add `timeout=30` to all `subprocess.run` calls in `_run()`. Currently `lifecycle.py:77-88` — the `check=False, capture_output=True` call has no timeout.

---

## Questions for Clarification

1. **Is the git repository private or public?** If public (or has ever been made public), the TELEGRAM_BOT_TOKEN incident extends to every clone made during the exposure window. The token rotation removes future access but not past access.

2. **What is the Telegram bot's current capability surface?** Can users send commands that become spec content? If yes, the token exposure is a command injection vector into the pipeline, not just a read access issue.

3. **Are there other credentials in `.env` beyond TELEGRAM_BOT_TOKEN?** The file was not accessible in this review session (not in working tree). The audit report mentions only the Telegram token but the `.env` file may contain other secrets (API keys, DB passwords for managed projects).

4. **Multi-machine intent?** ADR-023 describes multi-machine convergence via git push/pull as a design goal. If this is actually deployed or planned imminently, the "accepted" status on multi-machine CAS without distributed lock needs to be revisited.

5. **Is `scripts/vps/` accessible to managed project agents during their tasks?** If Claude agents running awardybot tasks have access to `scripts/vps/`, the attack surface for spec_operator.py and the lifecycle writer is much larger than assumed.

---

## References

- STRIDE: https://learn.microsoft.com/en-us/azure/security/develop/threat-modeling-tool-threats
- OWASP Top 10 2021: https://owasp.org/www-project-top-ten/
- CWE-732 Incorrect Permission Assignment: https://cwe.mitre.org/data/definitions/732.html
- CWE-522 Insufficiently Protected Credentials: https://cwe.mitre.org/data/definitions/522.html
- MITRE ATT&CK T1552.001 Credentials in Files: https://attack.mitre.org/techniques/T1552/001/
- Primary sources: deep-audit-report.md (85 findings), architecture-agenda.md (Bruce section), direct code analysis of scripts/vps/ contour
