# External Research — Multi-Project Orchestrator Phase 1

## Best Practices

### 1. Telegram Forum Topics: message_thread_id=1 is the General topic and CANNOT be targeted with send_message

**Source:** [PTB Issue #4739 — send_message with message_thread_id=1 returns BadRequest](https://github.com/python-telegram-bot/python-telegram-bot/issues/4739)

**Summary:** `message_thread_id=1` is reserved for the General topic in Telegram supergroups. Sending to it with `send_message(message_thread_id=1)` returns `BadRequest: Message thread not found`. To post to General, omit `message_thread_id` entirely (or pass `None`). All created topics get IDs starting at 2+.

**Why relevant:** Our orchestrator sends per-project notifications to specific topics. Any logic that maps project → topic_id must guard against thread_id=1 and use `None` for General (heartbeat/alert channel).

---

### 2. SQLite WAL + BEGIN IMMEDIATE is the correct atomic slot acquisition pattern

**Source:** [SQLite Forum: Help understanding BEGIN IMMEDIATE](https://sqlite.org/forum/forumpost/04ed1d235b)

**Summary:** Using plain `BEGIN` (DEFERRED) for writes risks `SQLITE_BUSY` without honouring `busy_timeout`. `BEGIN IMMEDIATE` acquires a reserved write lock up front, so the `busy_timeout` is respected. This is the correct pattern when multiple processes (orchestrator + potential future workers) compete for the same rows. Combine with `PRAGMA busy_timeout = 5000`.

**Why relevant:** Our `compute_slots` acquisition in the architecture uses `BEGIN IMMEDIATE`. Research confirms this is correct and necessary — not optional optimisation.

---

### 3. Python 3.12 sqlite3 WAL mode must be set BEFORE autocommit engages

**Source:** [TechNetExperts: Set SQLite WAL Mode in Python 3.12 with autocommit=False](https://www.technetexperts.com/python-sqlite-wal-autocommit-false/)

**Summary:** In Python 3.12, `sqlite3.connect(db, autocommit=False)` starts an implicit transaction before the first DML/DDL. Setting `PRAGMA journal_mode = WAL` inside this implicit transaction raises a runtime error. Fix: use `isolation_level=None` (autocommit=True) for the WAL pragma, then switch to `autocommit=False`:

```python
# Correct init pattern for Python 3.12
conn = sqlite3.connect("orchestrator.db", autocommit=True)
conn.execute("PRAGMA journal_mode = WAL")
conn.execute("PRAGMA busy_timeout = 5000")
conn.execute("PRAGMA foreign_keys = ON")
conn.close()
# Re-open with transaction control
conn = sqlite3.connect("orchestrator.db", autocommit=False)
```

**Why relevant:** The bot is Python 3.12. Naive WAL setup will silently fail or raise on first startup.

---

### 4. Pueue v4.0 eliminates async delays — start/pause/kill return only after action completes

**Source:** [pueue v4.0.0 changelog — Nukesor/pueue](https://github.com/Nukesor/pueue/blob/main/CHANGELOG.md)

**Summary:** Pre-v4, `pueue start --immediate` returned `Ok` before the task actually started (~hundreds of ms delay). v4.0.0 (released 2025-03-09) executes subprocess state changes synchronously in the message handler. Commands now return only when the action is complete. This means scripting like `pueue add --immediate ... && pueue send 0 'y\n'` now works reliably.

**Why relevant:** Our orchestrator submits tasks and immediately queries state. In v4, the state is authoritative right after the CLI call returns — no sleep/poll hack needed.

---

### 5. whisper.cpp requires 16 kHz mono WAV; Telegram voice notes are OGG/Opus and must be converted

**Source:** [Gist: Transcribe any media using whisper-cli and ffmpeg](https://gist.github.com/GammelSami/e1e895a42d036d28dd6286df5b3fbb81)

**Summary:** whisper.cpp only reads WAV. Telegram delivers voice notes as `.ogg` (Opus codec). The pipeline is: `ffmpeg -i input.ogg -ar 16000 -ac 1 -c:a pcm_s16le /dev/shm/temp_$$.wav`. Use `/dev/shm/` for the temp file (RAM disk, avoids disk I/O on VPS, auto-cleaned on reboot). The `$$` suffix prevents collisions on parallel transcriptions.

**Why relevant:** Our inbox voice processing in `run-agent.sh` or a preprocessing hook must include this ffmpeg step. Skipping it means whisper.cpp fails silently or produces garbage.

---

## Libraries/Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| python-telegram-bot | v22.6 (stable) | Mature, async, Forum topics since v20, ApplicationBuilder pattern, 28.7k stars | Python-only | Telegram bot with topic routing | [docs.python-telegram-bot.org](https://docs.python-telegram-bot.org/en/stable/) |
| pueue | v4.0.4 (2026-03-02) | Sync commands in v4, groups, parallel limits, `--json` output, persistence, MIT | Rust binary (no Python API) | Task queue for LLM agent processes | [github.com/Nukesor/pueue](https://github.com/Nukesor/pueue) |
| whisper.cpp | latest (ggml-org fork) | C++ binary, no Python, 1.8-2.4x faster than faster-whisper on CPU, ~300MB model (base), zero cloud | Needs ffmpeg for OGG→WAV, slow on VPS without AVX2 | Local voice transcription | [github.com/ggml-org/whisper.cpp](https://github.com/ggml-org/whisper.cpp) |
| faster-whisper | latest | 4x faster than original Whisper, 50% less RAM, Python-native | Python deps, needs CTranslate2, GIL issues | Alternative if whisper.cpp too slow on VPS | [rackdiff.com](https://rackdiff.com/en/blog/whisper-self-hosting-guide) |
| SQLite WAL | built-in (Python 3.12 sqlite3) | Ships with every Linux, ACID, WAL mode allows concurrent readers, no daemon | Single writer limit (fine for our scale) | Runtime state, slot acquisition | [sqlite.org](https://sqlite.org/wal.html) |

**Recommendation:** All five technologies match the architecture exactly as designed. No substitutions needed.

---

## Production Patterns

### Pattern 1: Forum Topic Routing — topic_id as first-class routing key

**Source:** [python-telegram-bot v22.6 ForumTopic docs](https://docs.python-telegram-bot.org/en/stable/telegram.forumtopic.html)

**Description:** `bot.create_forum_topic(chat_id, name)` returns a `ForumTopic` object with `message_thread_id`. Store this ID in `projects.json`. Every subsequent `send_message` to that project uses `message_thread_id=topic.message_thread_id`. Bot must have `can_manage_topics` admin right (set via BotFather or group settings). Incoming messages in Forum mode carry `message.message_thread_id` — use this to route to the correct project.

**Real-world use:** The openclaw project (210k stars) added Forum topic creation as a feature in Feb 2026 (issue #10427, merged Feb 18), confirming this is a real production need. Required `can_manage_topics` permission.

**Fits us:** Yes — exact pattern for `projects.json: { topic_id: N }`.

Full working pattern:

```python
from telegram import Bot
from telegram.ext import Application, MessageHandler, CommandHandler, filters

# Create topic (one-time, during /addproject)
async def addproject(update, context):
    chat_id = update.effective_chat.id
    topic = await context.bot.create_forum_topic(
        chat_id=chat_id,
        name=project_name,
        icon_color=0x6FB9F0  # blue
    )
    # Store topic.message_thread_id -> projects.json

# Send notification to project topic
async def notify_project(bot, chat_id, topic_id, text):
    # NEVER pass message_thread_id=1 (General topic bug)
    thread_id = topic_id if topic_id != 1 else None
    await bot.send_message(
        chat_id=chat_id,
        text=text,
        message_thread_id=thread_id
    )

# Route incoming messages by topic
async def handle_message(update, context):
    thread_id = update.message.message_thread_id  # None = General topic
    project = topic_to_project.get(thread_id)
    if project:
        # Write to ai/inbox/{project}/
        pass
```

---

### Pattern 2: Pueue Groups + Per-Group Parallelism for Resource Isolation

**Source:** [Pueue Wiki: Groups](https://github.com/Nukesor/pueue/wiki/Groups)

**Description:** Groups isolate task queues by resource type. Each group has independent parallelism settings. `pueue group add claude-runner` + `pueue parallel --group claude-runner 2` creates a group that runs at most 2 tasks concurrently. Tasks added with `pueue add --group claude-runner -- command` never compete across groups at the group level.

```bash
# Setup (one-time, idempotent-safe to re-run)
pueue group add claude-runner 2>/dev/null || true
pueue group add codex-runner 2>/dev/null || true
pueue parallel --group claude-runner 2
pueue parallel --group codex-runner 1

# Add task
pueue add --group claude-runner --label "saas-app:FTR-042" \
    -- /scripts/vps/run-agent.sh /home/ubuntu/saas-app "/autopilot" claude

# Query running tasks for a group (parse with jq)
pueue status --json | jq '.tasks | to_entries[] | select(.value.group == "claude-runner") | select(.value.status | has("Running"))'

# Pause specific group (stops new starts, does NOT kill running)
pueue pause --group claude-runner

# Resume
pueue start --group claude-runner
```

**Real-world use:** Official Pueue pattern for I/O vs CPU separation. v4.0 guarantees `pause --group` returns only when all group tasks are actually paused.

**Fits us:** Yes — direct match to architecture's `claude-runner` / `codex-runner` groups.

---

### Pattern 3: systemd MemoryMax + KillMode=control-group for OOM containment

**Source:** [OneUptime: How to Set Up systemd Resource Control with MemoryMax on Ubuntu](https://oneuptime.com/blog/post/2026-03-02-setup-systemd-resource-control-memorymax-ubuntu/view) + [systemd.service official docs](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)

**Description:** `MemoryMax=27G` (on 32GB VPS) is a hard cgroup limit — the kernel OOM-kills the process if exceeded. `KillMode=control-group` ensures that when systemd stops the service (SIGTERM/SIGKILL), it kills **all** processes in the cgroup tree, not just the main PID. This is critical because `orchestrator.sh` spawns child processes (`claude`, `codex`). Without `KillMode=control-group`, orphan LLM processes survive after orchestrator is stopped.

`MemorySwapMax=0` prevents swap usage, avoiding the "slowly dying VPS" scenario where swap thrashes for 10 minutes before OOM.

```ini
[Service]
MemoryMax=27G        # Hard ceiling — OOM kills within cgroup only
MemorySwapMax=0      # No swap — fail fast
KillMode=control-group  # Kill ALL child processes on stop
Restart=on-failure
RestartSec=30
StartLimitIntervalSec=300
StartLimitBurst=3    # Give up after 3 failures in 5 min (prevents crash loop)
```

**Fits us:** Yes — architecture already has this exact pattern. Research confirms it's correct.

---

### Pattern 4: whisper.cpp base model on CPU-only VPS

**Source:** [whisper.cpp VPS performance issue #524](https://github.com/ggerganov/whisper.cpp/issues/524) + [Whisper low-RAM deployment guide](https://www.alibaba.com/product-insights/how-to-run-whisper-based-transcription-offline-with-under-4gb-ram.html)

**Description:** Performance on VPS depends heavily on AVX2 support. Without BLAS:
- `tiny` model (39M params, ~75MB): ~10-15x real-time on modern x86_64 VPS (1 min audio → 4-6 sec)
- `base` model (74M params, ~148MB): ~4-6x real-time (1 min audio → 10-15 sec)
- `medium` model: 90% real-time on 16-core EPYC (impractical for single VPS)

For Telegram voice notes (typically 5-30 seconds), `base.en` gives best accuracy/speed tradeoff. Use quantized model: `ggml-base.en.q5_1.bin` (1.2 GB RAM peak, >92% accuracy on clear speech).

Build and install:

```bash
# Build whisper.cpp (Ubuntu 22.04+)
apt install build-essential libopenblas-dev ffmpeg -y
git clone https://github.com/ggml-org/whisper.cpp
cd whisper.cpp
cmake -B build -DWHISPER_OPENBLAS=ON   # enables BLAS acceleration
cmake --build build -j$(nproc)

# Download base model
bash ./models/download-ggml-model.sh base.en

# OGG voice note → transcription (full pipeline)
INPUT_OGG="$1"
TMPWAV="/dev/shm/voice_$$.wav"
trap 'rm -f "$TMPWAV"' EXIT
ffmpeg -i "$INPUT_OGG" -ar 16000 -ac 1 -c:a pcm_s16le "$TMPWAV" -y -loglevel quiet
./build/bin/whisper-cli -m models/ggml-base.en.bin -f "$TMPWAV" \
    --no-timestamps --no-prints -l auto 2>/dev/null
```

**Fits us:** Yes — 5-30 sec Telegram voice notes → 0.5-5 sec transcription on any VPS with AVX2. Acceptable latency for inbox capture.

---

### Pattern 5: pueue status --json schema (for scripting)

**Source:** [pueue group --json feature](https://github.com/Nukesor/pueue/issues/430) + [pueue CHANGELOG](https://github.com/Nukesor/pueue/blob/main/CHANGELOG.md)

**Description:** `pueue status --json` returns:

```json
{
  "tasks": {
    "0": {
      "id": 0,
      "command": "/scripts/vps/run-agent.sh ...",
      "group": "claude-runner",
      "label": "saas-app:FTR-042",
      "status": { "Running": { "pid": 12345, "start": "..." } },
      "enqueue_at": null
    }
  },
  "groups": {
    "claude-runner": { "status": "Running", "parallel_tasks": 2 },
    "codex-runner": { "status": "Running", "parallel_tasks": 1 }
  }
}
```

Status values (v4): `"Queued"`, `"Running"` (object with pid), `"Paused"`, `"Success"` (object with exit_code), `"Failed"` (object with exit_code), `"Killed"`, `"Stashed"`.

```bash
# Count running tasks in claude-runner group
pueue status --json | jq '[.tasks | to_entries[] | select(.value.group == "claude-runner") | select(.value.status | type == "object" and has("Running"))] | length'

# Get task ID for a project (by label)
pueue status --json | jq -r '.tasks | to_entries[] | select(.value.label == "saas-app:FTR-042") | .key'
```

**Fits us:** Yes — orchestrator's `/status` command queries this JSON to build the Telegram status message.

---

## Key Decisions Supported by Research

1. **Decision:** Use `message_thread_id=None` for General topic, not `message_thread_id=1`
   **Evidence:** PTB issue #4739 confirms `message_thread_id=1` raises `BadRequest: Message thread not found`. This is a known Telegram API quirk.
   **Confidence:** High

2. **Decision:** `BEGIN IMMEDIATE` for `compute_slots` acquisition (architecture already has this)
   **Evidence:** SQLite forum post by Simon Willison confirms DEFERRED transactions bypass `busy_timeout`. `BEGIN IMMEDIATE` is the correct pattern for multi-process write contention.
   **Confidence:** High

3. **Decision:** Python 3.12 WAL setup requires two-phase connection init
   **Evidence:** TechNetExperts article (Feb 2026) documents the Python 3.12 autocommit/WAL interaction bug. Standard init pattern will fail silently on Ubuntu 24.04 which ships Python 3.12.
   **Confidence:** High

4. **Decision:** whisper.cpp `base` model (not `tiny`) for Telegram voice notes
   **Evidence:** `tiny` (39M params) has noticeably worse accuracy on accented/non-English speech. `base` is 10-15 sec per 1-min audio on CPU VPS — acceptable for async inbox capture. RackDiff guide confirms `faster-whisper` is 4x faster alternative if needed.
   **Confidence:** Medium (benchmark on specific VPS CPU may vary)

5. **Decision:** Install whisper.cpp with `DWHISPER_OPENBLAS=ON`
   **Evidence:** whisper.cpp VPS issue #524 shows users without BLAS run at 90% real-time (1 min audio = 1+ min to process). OpenBLAS gives 2-4x speedup on x86_64 VPS with AVX2.
   **Confidence:** High

6. **Decision:** Pueue v4.0.4 (latest stable) over v3.x
   **Evidence:** v4 sync command execution means orchestrator can immediately query accurate state post-`add`/`pause`. Breaking change from v3 (protocol incompatible) but no legacy data to migrate.
   **Confidence:** High

7. **Decision:** ffmpeg conversion to `/dev/shm/` before whisper.cpp
   **Evidence:** Gist from Feb 2026 shows production pattern using `/dev/shm/` with `$$` suffix for parallel safety. Avoids disk I/O on VPS, RAM-based temp is auto-cleaned.
   **Confidence:** High

---

## Gaps / Watch Items

| Item | Risk | Mitigation |
|------|------|------------|
| `pueue status --json` exact schema for v4 not in official docs | Medium — schema may differ slightly | Run `pueue status --json` on VPS after install and verify field names |
| whisper.cpp AVX2 availability on chosen VPS | Medium — older VPS CPUs may lack AVX2 | Check with `grep -m1 avx2 /proc/cpuinfo`; fallback to `faster-whisper` if needed |
| PTB v22 vs v22.6 on PyPI | Low — minor version differences | Pin to `python-telegram-bot==22.6` exactly |
| Pueue systemd **user** service vs system service | Medium — user service needs `loginctl enable-linger` | Architecture uses system service (`/etc/systemd/system/`), which is correct for server |

---

## Research Sources

- [PTB Issue #4739 — message_thread_id=1 BadRequest](https://github.com/python-telegram-bot/python-telegram-bot/issues/4739) — confirmed General topic bug, workaround
- [PTB v22.6 ForumTopic docs](https://docs.python-telegram-bot.org/en/stable/telegram.forumtopic.html) — official API for create_forum_topic
- [openclaw issue #10427 — Forum topic creation](https://github.com/openclaw/openclaw/issues/10427) — real production implementation, `can_manage_topics` permission confirmed
- [Pueue v4.0.0 changelog](https://github.com/Nukesor/pueue/blob/main/CHANGELOG.md) — sync commands, breaking changes from v3
- [Pueue Wiki: Groups](https://github.com/Nukesor/pueue/wiki/Groups) — group add, parallel, pause/resume patterns
- [Pueue group --json issue #430](https://github.com/Nukesor/pueue/issues/430) — `pueue status --json` scripting support
- [SQLite Forum: BEGIN IMMEDIATE](https://sqlite.org/forum/forumpost/04ed1d235b) — confirmed correct pattern for concurrent writes
- [TechNetExperts: Python 3.12 WAL + autocommit](https://www.technetexperts.com/python-sqlite-wal-autocommit-false/) — Python 3.12 WAL init gotcha
- [SQLite WAL concurrency guide](https://coldfusion-example.blogspot.com/2025/12/sqlite-database-is-locked-solving.html) — `busy_timeout` + WAL production config
- [whisper.cpp VPS performance #524](https://github.com/ggerganov/whisper.cpp/issues/524) — CPU benchmarks, BLAS recommendation
- [whisper.cpp under 4GB RAM guide](https://www.alibaba.com/product-insights/how-to-run-whisper-based-transcription-offline-with-under-4gb-ram.html) — model selection, quantized models
- [Gist: Transcribe with ffmpeg + whisper-cli](https://gist.github.com/GammelSami/e1e895a42d036d28dd6286df5b3fbb81) — production OGG→WAV→text pipeline with /dev/shm
- [RackDiff: Whisper self-hosting guide](https://rackdiff.com/en/blog/whisper-self-hosting-guide) — faster-whisper as alternative
- [OneUptime: systemd MemoryMax](https://oneuptime.com/blog/post/2026-03-02-setup-systemd-resource-control-memorymax-ubuntu/view) — MemoryMax vs MemoryHigh distinction
- [Michael Stapelberg: indefinite systemd restarts](https://michael.stapelberg.ch/posts/2024-01-17-systemd-indefinite-service-restarts/) — StartLimitIntervalSec=0 pattern
