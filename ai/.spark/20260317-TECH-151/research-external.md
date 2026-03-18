# External Research — TECH-151: Align Orchestrator to North-Star Linear Pipeline

## Best Practices

### 1. Single-Writer Queue (Singular Update Queue Pattern)
**Source:** [Singular Update Queue — Patterns of Distributed Systems (Martin Fowler)](https://martinfowler.com/articles/patterns-of-distributed-systems/singular-update-queue.html)
**Summary:** The Singular Update Queue pattern mandates that exactly one actor owns writes to a shared state queue. Multiple concurrent producers create ordering ambiguity, duplicate dispatch risk, and hard-to-trace causality. A single thread (or single writer) processes the queue, ensuring one-at-a-time execution with clear ownership.
**Why relevant:** The north-star design assigns OpenClaw as the sole writer to `ai/inbox/`. The pueue-callback.sh must not write inbox items — it is a secondary actor that would break the single-writer invariant. Any autonomous enqueue from a callback is a second producer that corrupts the ownership model.

---

### 2. Approval Gate as a Risk Gate, Not a Universal Speed Bump
**Source:** [Approvals for autonomous AI agents: fast human gates — Cordum](https://cordum.io/blog/approvals-for-autonomous-workflows)
**Summary:** Approval gates should target high-impact, irreversible, or out-of-policy actions. The goal is "stop the risky actions, capture human intent, and keep safe automation moving quickly." Gates must be narrow and well-justified — making everything require approval defeats the purpose and makes humans the bottleneck queue.
**Why relevant:** The spec factory (Spark) currently produces `draft` specs that require human approval before autopilot. The north-star collapses this: Spark produces `queued` specs (low-risk, reversible) directly. The human gate moves to the end of the cycle (after QA + Reflect) where the human decides whether to start the next cycle. This is correct gate placement: approve the work order before it executes, not after it completes.

---

### 3. Immutable State Machine with Terminal States
**Source:** [6 Patterns That Turned My Pipeline from Chaotic to Production-Grade — Jaroslaw Wasowski, Medium](https://medium.com/@wasowski.jarek/6-patterns-that-turned-my-pipeline-from-chaotic-to-production-grade-agentic-workflows-cdd45d2d314a)
**Summary:** A production agentic pipeline of 27 skills uses an immutable state machine as its backbone. Each stage has defined inputs, outputs, and position. The key insight: "Pipeline state managed as immutable objects makes resumption and auditing trivial." The pipeline advances only when a step emits its artifact — it does not self-loop. Every stage writes a durable artifact file; the next stage reads that file, not a transient message.
**Why relevant:** QA writing a durable file report (not an inbox item) matches this pattern exactly. The file IS the artifact. The callback's job is to signal completion, not to chain work. Chaining from callbacks makes causality opaque and breaks the immutable state machine model.

---

### 4. Human-in-the-Loop as Cycle Boundary, Not Mid-Cycle Interrupt
**Source:** [Control Loops for Agentic AI: HITL and AITL Design Patterns — Medium](https://medium.com/%40mjgmario/control-loops-for-agentic-ai-practical-hitl-and-aitl-design-patterns-e27357078531)
**Summary:** The article distinguishes "layered autonomy" from full-autonomy vs. full-manual. In production: "The real question is where and how you place control loops as a system evolves." HITL should interrupt before irreversible, regulated, or high-impact actions. For low-impact, reversible work like code generation, HITL belongs at the cycle boundary — human decides whether to start the next cycle, not whether to allow each step within a cycle.
**Why relevant:** The current pipeline interrupts mid-cycle (draft approval gate before autopilot). The north-star moves HITL to the cycle boundary: after Reflect writes its report, the cycle stops and the human decides what to do next. OpenClaw facilitates that decision. This is correct layered autonomy for a dev pipeline.

---

### 5. Callback = Notification + State Update Only (No Side Effects)
**Source:** [Pueue v4.0.4 Configuration Wiki — GitHub/Nukesor](https://github.com/Nukesor/pueue/wiki/Configuration)
**Summary:** Pueue's `daemon.callback` is designed for notification and state recording on task completion. The official examples show `notify-send` (desktop notification) and parameterized status messages. The callback receives: `{{ id }}`, `{{ result }}`, `{{ group }}`, `{{ command }}`, `{{ path }}`. It is a fire-and-forget hook, not a dispatch mechanism. Pueue's design goal: "task management tool for sequential and parallel execution" — scheduling is done by adding tasks to queues, not by callback-triggered re-enqueue.
**Why relevant:** Using `pueue-callback.sh` to dispatch QA and Reflect (Step 7 in the current implementation) contradicts Pueue's design intent. The callback is executing business logic (dispatch decisions) that belongs in the orchestrator's poll cycle. This is the root cause of the feedback loop problem: the callback is doing the orchestrator's job.

---

## Libraries / Tools

| Library | Version | Pros | Cons | Use Case | Source |
|---------|---------|------|------|----------|--------|
| Pueue | v4.0.4 | Durable queue, group isolation, stash/hold support | Callback is limited (no `{{ label }}` in templates) | Task queue for autopilot/QA/Reflect dispatch | [GitHub](https://github.com/Nukesor/pueue) |
| SQLite via db.py | stdlib | Single-file, parameterized, ACID | Not distributed | Phase state SSOT — track what stage each project is in | Current implementation |
| n8n approval gate | v1.x | Visual workflow, wait node, approval webhook | Self-hosted complexity | Reference for human-gate pattern design | [Medium](https://medium.com/@bhagyarana80/the-n8n-approval-gate-pattern-fast-and-safe-6624390c9ea1) |
| LangGraph interrupt_before | 0.2.x | Formal interrupt API for HITL in Python agentic pipelines | LangGraph-specific | Pattern reference for mid-pipeline pause | [GitHub/paperclipai](https://github.com/paperclipai/paperclip/issues/762) |

**Recommendation:** No new libraries needed. The fix is behavioral: move dispatch decisions from `pueue-callback.sh` into the orchestrator's poll cycle. The orchestrator already reads `project_state.phase` from SQLite — it can detect `qa_pending` and `reflect_pending` phases and dispatch accordingly. This keeps Pueue callbacks as pure notification hooks.

---

## Production Patterns

### Pattern 1: Immutable Pipeline with Durable Artifact Files
**Source:** [6 Patterns That Turned My Pipeline from Chaotic to Production-Grade — Medium (March 2026)](https://medium.com/@wasowski.jarek/6-patterns-that-turned-my-pipeline-from-chaotic-to-production-grade-agentic-workflows-cdd45d2d314a)
**Description:** Each stage in the pipeline writes a durable artifact (file) as its output. The next stage reads that file. Stages do not communicate via transient messages or callbacks. State advancement is explicit and persisted. The pipeline can be replayed, audited, or resumed at any point by reading the artifact files.
**Real-world use:** Production agentic pipeline running 27 specialized skills for content production (Wasowski, 2026). Assembly-line model: each workstation has defined input file, output file, and position in sequence.
**Fits us:** Yes — QA should write `ai/reports/qa-{SPEC-ID}.md` as its durable artifact. This replaces QA writing to `ai/inbox/` entirely. The human (via OpenClaw) reads this file when reviewing results.

---

### Pattern 2: Phase-Driven Orchestrator Poll (No Callback Dispatch)
**Source:** [Agentic Workflow Orchestration: Architecture Patterns That Scale — Chrono Innovation](https://www.chronoinnovation.com/resources/agentic-ai-workflows-architecture)
**Description:** The orchestrator polls a state store (SQLite, Redis, Postgres) each cycle. State transitions happen inside the task executor, not in callbacks. The orchestrator detects the new state on next poll and makes dispatch decisions. Callbacks only write state. The orchestrator only reads state and dispatches.
**Real-world use:** LangGraph, Temporal, and Orkes all implement this pattern — the workflow engine polls for state, agents write state, the engine decides next transitions. Used at production scale by Stripe (Temporal), Shopify (Temporal), and Netflix (internal systems).
**Fits us:** Yes — `orchestrator.sh` already polls every 300 seconds and reads `project_state.phase`. Moving QA/Reflect dispatch from `pueue-callback.sh` to `orchestrator.sh`'s poll cycle is the correct fix. The callback sets `phase=qa_pending`; the orchestrator detects it and dispatches QA.

---

### Pattern 3: Terminal State + Human Trigger for Next Cycle
**Source:** [Human-in-the-Loop for Mission-Critical Pipelines with OpenClaw — Medium (Feb 2026)](https://building.theatlantic.com/human-in-the-loop-for-mission-critical-pipelines-with-openclaw-cd5c2ae7f6b0)
**Description:** Durable automation workflows that "can run unattended, pause safely, ask for human judgement with the right context, and resume precisely once a decision is made." The key: workflows pause at a well-defined terminal state, not mid-execution. The human receives context (the QA/Reflect artifacts) and makes a decision. The decision triggers the next cycle start.
**Real-world use:** OpenClaw + Trigger.dev pattern used in mission-critical pipelines (Atlantic Media, 2026). Human approval bound to a policy snapshot and job hash to prevent drift.
**Fits us:** Yes — after Reflect completes, the cycle reaches terminal state `idle`. OpenClaw notifies the human with a summary of QA report + Reflect findings. Human decides: "start next task", "fix issue", or "ignore". This is the north-star's stop point.

---

### Pattern 4: Guard Against Callback-Triggered Feedback Loops
**Source:** [5 CI/CD Pipeline Disasters I Caused — DEV Community (March 2026)](https://dev.to/sanjaysundarmurthy/5-cicd-pipeline-disasters-i-caused-and-how-i-fixed-them-79j)
**Description:** One post-mortem documents a pipeline that "deployed on every commit to main" because a callback triggered a commit which triggered another deployment. The pattern: callbacks that enqueue new work create implicit feedback loops that are invisible in the code. The fix: callbacks must have no dispatch logic. Dispatch is the orchestrator's exclusive responsibility.
**Real-world use:** Documented production incident in Azure DevOps pipeline. Same pattern found in Jenkins "build triggered by build" loops that caused cascading queue floods.
**Fits us:** Yes — the current `pueue-callback.sh` Step 7 dispatches QA + Reflect after autopilot. This is structurally the same anti-pattern. If QA writes to inbox, inbox triggers Spark, Spark completes and triggers QA again. The fix is removing Step 7 from the callback and moving that logic to the orchestrator's poll cycle.

---

## Key Decisions Supported by Research

1. **Decision:** Remove dispatch logic from `pueue-callback.sh` (Step 7: QA + Reflect dispatch after autopilot)
   **Evidence:** Pueue wiki confirms callbacks are for notification only. Wasowski (2026) and Chrono Innovation document that dispatch belongs in the poll-cycle orchestrator, not in completion callbacks. The callback-as-dispatcher anti-pattern is the root cause of feedback loop risk.
   **Confidence:** High

2. **Decision:** Spark spec factory produces `queued` status directly (no draft approval gate)
   **Evidence:** Cordum (2026) establishes that approval gates should be narrow and placed at high-impact decision points. Generating a spec is low-risk and reversible. The correct gate is at cycle start (human approves the task order in OpenClaw) not mid-pipeline. The draft-to-queued manual transition is waste without safety value.
   **Confidence:** High

3. **Decision:** QA writes a durable file report to `ai/reports/qa-{SPEC-ID}.md`, not to `ai/inbox/`
   **Evidence:** Wasowski's immutable state machine pattern (2026) requires each stage to produce a durable artifact file, not a transient message. Writing to inbox makes QA a producer, violating the single-writer invariant (Martin Fowler's Singular Update Queue). File-based artifacts are auditable, replayable, and don't auto-trigger downstream work.
   **Confidence:** High

4. **Decision:** Move QA + Reflect dispatch to `orchestrator.sh` poll cycle (phase-driven dispatch)
   **Evidence:** Chrono Innovation architecture pattern (2026): orchestrator detects state changes on poll, not via callback side effects. Already partially implemented: `orchestrator.sh` handles `qa_pending` phase (FTR-146 Task 8). Pueue-callback sets phase; orchestrator dispatches. This is the correct separation of concerns.
   **Confidence:** High

5. **Decision:** After Reflect completes, cycle reaches terminal `idle` state — no auto-enqueue
   **Evidence:** HITL pattern from Medium (Jan 2026) establishes that pipelines must have explicit terminal states where human review occurs. The OpenClaw + Trigger.dev article (Feb 2026) confirms: "pause safely, ask for human judgement with right context, resume precisely once decision is made." The cycle stops; OpenClaw delivers the summary; human decides the next cycle.
   **Confidence:** High

---

## Research Sources

- [Singular Update Queue — Patterns of Distributed Systems (Martin Fowler / O'Reilly 2023)](https://martinfowler.com/articles/patterns-of-distributed-systems/singular-update-queue.html) — single-writer queue architecture; why multiple producers break state ordering
- [Approvals for autonomous AI agents: fast human gates — Cordum, Jan 2026](https://cordum.io/blog/approvals-for-autonomous-workflows) — approval gate placement at high-risk actions only; gates as risk filters not universal checkpoints
- [6 Patterns That Turned My Pipeline from Chaotic to Production-Grade — Medium, March 2026](https://medium.com/@wasowski.jarek/6-patterns-that-turned-my-pipeline-from-chaotic-to-production-grade-agentic-workflows-cdd45d2d314a) — immutable state machine, durable artifact files, assembly-line model for 27-skill production pipeline
- [Control Loops for Agentic AI: HITL and AITL Patterns — Medium, Jan 2026](https://medium.com/%40mjgmario/control-loops-for-agentic-ai-practical-hitl-and-aitl-design-patterns-e27357078531) — layered autonomy; HITL at cycle boundaries not mid-cycle; irreversible action gating
- [Human-in-the-Loop for Mission-Critical Pipelines with OpenClaw — Medium, Feb 2026](https://building.theatlantic.com/human-in-the-loop-for-mission-critical-pipelines-with-openclaw-cd5c2ae7f6b0) — durable automation with defined terminal states; human resumes cycle with context
- [Pueue v4.0.4 Configuration Wiki — GitHub/Nukesor](https://github.com/Nukesor/pueue/wiki/Configuration) — official callback design: notification/state only, not dispatch; `{{ label }}` unavailable in callback templates
- [Agentic AI Workflows: Architecture Patterns That Scale — Chrono Innovation, March 2026](https://www.chronoinnovation.com/resources/agentic-ai-workflows-architecture) — poll-cycle orchestrator as SSOT for dispatch; callbacks write state only
- [5 CI/CD Pipeline Disasters — DEV Community, March 2026](https://dev.to/sanjaysundarmurthy/5-cicd-pipeline-disasters-i-caused-and-how-i-fixed-them-79j) — callback-triggered re-enqueue as a known production disaster pattern; callbacks must have no dispatch logic
- [n8n Approval Gate Pattern: Fast and Safe — Medium, Feb 2026](https://medium.com/@bhagyarana80/the-n8n-approval-gate-pattern-fast-and-safe-6624390c9ea1) — approval gate as pause point, not universal checkpoint; risk-scored gating
- [Enabling deduplication for single-producer/consumer system — AWS SQS Docs](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/single-producer-single-consumer.html) — single-producer pattern with FIFO queue; content-based deduplication when one writer owns the queue
