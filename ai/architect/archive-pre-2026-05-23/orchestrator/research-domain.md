# Domain Architecture Research

**Persona:** Eric (Domain Modeler)
**Focus:** Bounded contexts, ubiquitous language, domain boundaries for the Multi-Project Orchestrator
**Date:** 2026-03-10

---

## Research Conducted

- [DDD Beyond the Basics: Mastering Multi-Bounded Context Integration](https://medium.com/ssense-tech/ddd-beyond-the-basics-mastering-multi-bounded-context-integration-ca0c7cec6561) — when a term changes meaning across parts of a system, you have a context boundary. Applied: "project" means different things to a routing layer vs. a lifecycle manager.
- [Integration of Bounded Contexts — Software Architecture Guild](https://software-architecture-guild.com/guide/architecture/domains/integration-of-bounded-contexts/) — every seam between contexts is an explicit contract; integration patterns (ACL, Customer-Supplier, Published Language) must be chosen deliberately.
- [Orchestrate or Choreograph? — Ben Johns](https://www.bennyjohns.com/posts/20210116-orchestrate-or-choreograph) — rule of thumb that emerged from research: **use orchestration within a single bounded context; use choreography (domain events) across bounded contexts.** This is the key to how the orchestrator should work.
- [Steward Agents — Agentic DDD](https://www.bennyjohns.com/posts/20260222-steward-agents-agentic-ddd) — DDD bounded contexts are natural boundaries for agent responsibility. Each context can have a steward agent that understands its portion of the domain deeply. This directly validates the Project context being agent-aware.
- [Application Layer Orchestrators vs Domain Services](https://hector-reyesaleman.medium.com/application-layer-orchestrators-service-facades-9b71b6e2ff7f) — orchestration is an APPLICATION LAYER concern, not a domain concern. The orchestrator coordinates domain operations but contains no domain rules itself. Critical for the "is orchestrator a domain?" question.
- [AgentOps: It's Not Agent Orchestration. It's Context Orchestration.](https://www.bodenfuller.com/context-orchestration) — the real leverage in multi-agent systems is what is in the context window when an agent starts. This reframes the orchestrator's primary job: context delivery, not process management.
- [From Prompt Spaghetti to Bounded Contexts: DDD for Agentic Codebases](https://gitnation.com/contents/from-prompt-spaghetti-to-bounded-contexts-ddd-for-agentic-codebases) — DDD applied to agentic systems: bounded contexts for agent responsibilities, ubiquitous language for consistent tool inputs/outputs, context maps that make integrations explicit.
- [Domain Services vs Application Services](https://enterprisecraftsmanship.com/posts/domain-vs-application-services/) — domain services carry domain knowledge; application services orchestrate without containing domain rules. The shell orchestrator in the existing spec is an application service that should delegate to domain services per project.
- [How We Built an Agent Context Management System — Venture Crane](https://venturecrane.com/articles/agent-context-management-system/) — practical architecture for multi-agent context management: session continuity, parallel awareness, enterprise knowledge, work queue visibility. Directly maps to the "context delivery" problem in the orchestrator.
- [Determing Bounded Contexts using DDD Crew Methods — ArchiLab](https://www.archi-lab.io/infopages/ddd/ddd-crew-bounded-context.html) — systematic methods for identifying bounded contexts: Domain Message Flow Modelling and EventStorming to find where language changes.

**Total queries:** 8 web searches + 1 code context search conducted before forming opinion.

---

## Kill Question Answer

**"Can you explain the architecture using only business terms, without mentioning any technology?"**

Here is the test, applied to the existing spec:

*Existing spec explanation attempt:* "The orchestrator reads `projects.json`, runs a bash event loop, uses `flock` semaphore, routes by `message_thread_id`, stores state in `.orchestrator-state.json`."

**Result: FAILS.** Every concept in that explanation is a technical implementation detail. There is no business concept in the sentence. `flock`, `message_thread_id`, `projects.json`, `bash` — none of these belong in a domain model.

**What a correct business-language description sounds like:**

"A founder manages a portfolio of projects. When a founder sends a message about a specific project, it is captured as an idea and placed in that project's inbox. A scheduler periodically picks up work from each project according to its priority. One project runs at a time (limited by available compute). When a project completes a task, the founder is notified."

This description reveals the actual domain concepts: Portfolio, Project, Inbox, Idea, Scheduler, Priority, Notification. These are the entities that belong in the domain model. The existing spec conflated all of them with their technical implementations.

**Assessment:** The proposed shell-script architecture is a valid implementation choice, but it is not a domain model. The domain must be identified separately from the implementation. The fact that it runs on bash or Python is irrelevant to whether the boundaries are correct.

---

## Proposed Domain Decisions

### Bounded Contexts Identified

*Listening to the language in the problem description, I hear three distinct dialects.*

---

#### 1. Portfolio Context (Core)

- **Responsibility:** Knows what projects exist. Owns the definition of a Project as a business asset. Decides which project gets attention when. Enforces the priority model across all projects.
- **Core Entities:**
  - `Portfolio` (Aggregate Root) — the founder's collection of active projects. Has a concurrency budget (max active agents at once).
  - `Project` — a named work item with a path, priority level, and lifecycle state. NOT a codebase. A project is the business concept; the codebase is its physical location.
  - `Priority` (Value Object) — high/medium/low. Determines scheduling weight.
  - `ProjectStatus` (Value Object) — idle, active, paused, archived.
  - `ConcurrencyBudget` (Value Object) — how many projects can run simultaneously given VPS constraints.
- **Ubiquitous Language:**
  - *Project* — a named unit of work that a founder manages. Has an inbox and a backlog.
  - *Portfolio* — the complete set of projects a founder is managing.
  - *Priority* — the relative importance of a project for scheduling purposes.
  - *Activate* (verb) — assign a concurrency slot to a project so it can run.
  - *Pause* — remove a project from scheduling without removing it from the portfolio.
  - NOT called: workspace (that belongs to the morning briefing product), task, instance, process.
- **Subdomain Type:** Core — this is the primary value of the orchestrator. The ability to manage multiple projects simultaneously IS the product.

---

#### 2. Inbox Context (Supporting)

- **Responsibility:** Captures raw founder input and routes it to the correct project. The inbox is where unstructured ideas go to become structured work items. This context knows about capture channels (Telegram topics, voice, screenshots) but treats them as inputs, not as the source of truth.
- **Core Entities:**
  - `InboxItem` (Aggregate Root) — a raw piece of input. Has a source (text/voice/screenshot), a timestamp, a destination project. NOT yet an idea. An InboxItem is unclassified.
  - `Idea` — an InboxItem that has been classified as a potential feature, bug, or task. Lives in a project's inbox.
  - `Channel` (Value Object) — where the input came from. A Telegram topic IS a channel. A voice message IS a channel. The channel is not the project — it is the routing mechanism.
  - `RoutingKey` (Value Object) — the identifier used to map a channel message to a project. In Telegram: `message_thread_id`. But the domain should not know that — it should know "the key that identifies which project this message belongs to."
- **Ubiquitous Language:**
  - *Capture* — receiving a founder message and creating an InboxItem.
  - *Route* — determining which project an InboxItem belongs to.
  - *Idea* — a classified InboxItem ready for spark processing.
  - *Inbox* — the collection of Ideas awaiting processing for a project.
  - NOT called: topic (that is a Telegram concept, not an inbox concept), thread (technical), message (too generic).
- **Subdomain Type:** Supporting — essential but not differentiating. The routing logic is simple; the value is in what happens after routing.

---

#### 3. Pipeline Context (Core)

- **Responsibility:** Knows the DLD lifecycle for a single project. Owns the state machine: inbox -> spark -> autopilot -> QA -> done. Decides what the next action is for a given project. This context is the bridge between the orchestrator and an individual DLD instance.
- **Core Entities:**
  - `ProjectPipeline` (Aggregate Root) — the lifecycle state of one project's work. Has a current phase and a queue of pending work.
  - `Phase` (Value Object) — the current DLD lifecycle stage: idle, processing_inbox, running_spark, running_autopilot, running_qa.
  - `PipelineRun` (Entity) — a single execution of a pipeline step. Has start time, end time, outcome.
  - `PipelineSlot` (Value Object) — a reference to a ConcurrencyBudget slot this pipeline is consuming.
- **Ubiquitous Language:**
  - *Pipeline* — the sequence of DLD lifecycle steps for a project.
  - *Phase* — the current step a project is in.
  - *Run* — a single execution of a pipeline step.
  - *Slot* — a unit of concurrency consumed by a running pipeline.
  - NOT called: job, process, worker, task (these are all technical terms with no business meaning in this domain).
- **Subdomain Type:** Core — this is the mechanism that makes DLD multi-project management possible.

---

#### 4. Notification Context (Supporting)

- **Responsibility:** Delivers status information to the founder. Knows how to format and route messages back to the founder across channels. The inverse of Inbox — Inbox brings messages in, Notification sends messages out.
- **Core Entities:**
  - `Notification` (Aggregate Root) — a message to the founder. Has a target project, a severity (info/warning/critical), and content.
  - `DeliveryChannel` (Value Object) — where to send the notification. Telegram topic for a given project. Could also be email or other channels in the future.
- **Ubiquitous Language:**
  - *Notify* — send the founder a status update about a project.
  - *Alert* — a high-priority notification requiring founder attention.
  - NOT called: send, push, message (too generic), topic (technical).
- **Subdomain Type:** Supporting — important but generic. Telegram is replaceable.

---

#### Is "Orchestrator" a Domain or Infrastructure?

*This is the most important question.*

**Answer: The orchestrator is an APPLICATION SERVICE, not a domain concept.**

The orchestrator coordinates the Portfolio, Pipeline, and Inbox contexts. It is the use case layer. It contains no domain rules of its own. When the founder sends a message:

1. Inbox context captures and routes it (domain).
2. Portfolio context decides whether to activate the project (domain).
3. Pipeline context executes the next phase (domain).
4. Notification context reports back (domain).

The orchestrator script/process just calls these in the right order. This is identical to how an HTTP handler calls domain services in a web application. The handler is not a domain concept.

**Implication:** The existing spec's `orchestrator.sh` is correctly placed as application-layer glue. The error is treating it as the primary artifact. The primary artifacts are the domain concepts (Portfolio, Project, Inbox, Pipeline) that it coordinates.

---

#### Is There a Portfolio Context (Cross-Project Prioritization)?

**Yes, and it is Core.**

The morning briefing product (existing domain-map.md) has no concept of managing multiple projects. It manages one workspace. The multi-project orchestrator needs a concept that does not exist anywhere in the existing domain model: the ability to reason across projects simultaneously.

The Portfolio context owns this. When the founder asks "what is the status of all my projects?" that question is answered by the Portfolio context. When the scheduler decides "which project runs next?" the Portfolio context makes that decision based on priorities, concurrency budget, and project states.

This is NOT a technical concept (it is not a job queue or a process manager). It is a business concept: a founder managing a portfolio of work with limited attention and compute resources.

---

### Context Map

```
External World
   |
   +-- Telegram API --------[ACL: TelegramAdapter]--------+
   +-- Voice/Whisper --------[ACL: VoiceAdapter]----------+ --> Inbox Context
   +-- Screenshots ----------[ACL: ImageAdapter]----------+
   |
   +-- Claude CLI ----------[ACL: ClaudeAdapter]----------> Pipeline Context
   +-- File System ---------[ACL: FileSystemAdapter]------> Pipeline Context

Portfolio Context (owns Project registry, priority, concurrency budget)
     |
     +--[ProjectActivated]--> Pipeline Context
     +--[ProjectPaused]----> Pipeline Context
     |
Inbox Context
     +--[IdeaCaptured]-----> Portfolio Context (update project last_activity)
     +--[InboxReady]-------> Pipeline Context (trigger inbox processing)
     |
Pipeline Context
     +--[PhaseCompleted]---> Portfolio Context (release slot)
     +--[PhaseStarted]-----> Portfolio Context (consume slot)
     +--[PipelineFailed]---> Notification Context
     +--[PipelineIdle]-----> Portfolio Context (project back to idle)
     |
Notification Context
     +--[Notify founder in correct channel per project]
```

**Relationships:**

| From | To | Pattern | Why |
|------|----|---------|-----|
| Telegram API -> Inbox | Anti-Corruption Layer | Telegram speaks `message_thread_id`; the domain speaks `RoutingKey`. The ACL translates. |
| Claude CLI -> Pipeline | Anti-Corruption Layer | CLI has flags, exit codes, stdout. The domain speaks in phases and outcomes. ACL translates. |
| Inbox -> Portfolio | Published Language | `IdeaCaptured` is a fact that portfolio needs to know (last activity timestamp) |
| Portfolio -> Pipeline | Customer-Supplier | Portfolio is upstream authority on which projects can run and when |
| Pipeline -> Notification | Published Language | Pipeline publishes facts (started, completed, failed); Notification subscribes |
| Pipeline -> Portfolio | Customer-Supplier | Pipeline reports slot consumption back to Portfolio |

---

### Domain Events

| Event | Source Context | Triggered By | Consumed By |
|-------|---------------|--------------|-------------|
| `IdeaCaptured` | Inbox | Founder sends message to project channel | Portfolio (update activity), Pipeline (queue inbox check) |
| `InboxProcessingRequested` | Inbox | Inbox has unprocessed Ideas | Pipeline (run spark) |
| `ProjectActivated` | Portfolio | Scheduler assigns slot to project | Pipeline (begin run) |
| `ProjectPaused` | Portfolio | Founder command or auto-pause | Pipeline (stop current run) |
| `ConcurrencySlotAcquired` | Portfolio | Project starts a pipeline run | Pipeline (proceed) |
| `ConcurrencySlotReleased` | Portfolio | Pipeline run completes/fails | Portfolio (schedule next) |
| `PhaseStarted` | Pipeline | Pipeline begins a phase | Notification (inform founder) |
| `PhaseCompleted` | Pipeline | Phase finishes successfully | Portfolio (update state), Notification (inform founder) |
| `PipelineFailed` | Pipeline | Phase fails or times out | Portfolio (release slot), Notification (alert founder) |
| `ProjectStatusRequested` | Portfolio | Founder `/status` command | Portfolio (query, respond) |
| `PortfolioStatusRequested` | Portfolio | Founder `/projects` command | Portfolio (query all, respond) |

---

### Aggregate Design

**Portfolio Context Aggregates:**

- **Portfolio** (Aggregate Root)
  - Entities: `Project` (N projects)
  - Value Objects: `ConcurrencyBudget`, `SchedulingPolicy`
  - Invariants:
    - Active project count <= ConcurrencyBudget
    - Every project has a unique name and path
    - Paused projects do not consume concurrency slots
    - Priority ordering is consistent across all projects
  - Boundary Reason: Portfolio and its Projects must be consistent together. You cannot activate a project without checking the concurrency budget. These decisions must be atomic.

**Inbox Context Aggregates:**

- **InboxItem** (Aggregate Root)
  - Entities: none (InboxItem is atomic)
  - Value Objects: `RoutingKey`, `CaptureChannel`, `RawContent`
  - Invariants:
    - An InboxItem must have a valid RoutingKey that maps to a known Project
    - InboxItems are immutable once created (they are facts)
    - An InboxItem transitions to Idea exactly once
  - Boundary Reason: Capture and routing happen atomically. An InboxItem is either valid (routed) or rejected (unknown project). No partial state.

**Pipeline Context Aggregates:**

- **ProjectPipeline** (Aggregate Root)
  - Entities: `PipelineRun` (history of runs)
  - Value Objects: `Phase`, `PipelineSlot`, `PhaseOutcome`
  - Invariants:
    - A pipeline can only be in one phase at a time
    - A pipeline in active phase holds exactly one ConcurrencySlot
    - Phase transitions are forward-only within a run (idle -> active -> complete/failed)
    - A PipelineRun records its full lifecycle for observability
  - Boundary Reason: The state machine for one project's lifecycle must be consistent. A project cannot simultaneously be in spark AND autopilot. These invariants belong together.

---

## Cross-Cutting Implications

### For Data Architecture

- Portfolio context owns the canonical project registry. Every other context that needs to know "what projects exist" asks Portfolio, not files.
- The existing `projects.json` is a valid persistence mechanism for Portfolio context — a JSON file IS a valid repository for a simple aggregate. But it should be treated as the Portfolio's private storage, not as a shared configuration file that all scripts read directly.
- Pipeline state (`.orchestrator-state.json`) belongs to Pipeline context. No other context should write to it.
- Inbox items (files in `ai/inbox/`) belong to Inbox context. The file system IS the storage layer for Inbox; this is fine for this scale.
- Domain events can be implemented as filesystem events (inotifywait) for the simplest cases, or as an in-memory event bus if implemented in a single process.

### For API Design (Telegram as Interface)

- Telegram topics are NOT a domain concept. They are a delivery channel in the Inbox context.
- The mapping `topic_id -> project` is a RoutingKey lookup in the Inbox context's ACL layer.
- Telegram commands (`/status`, `/run`, `/pause`) are NOT domain commands. They are translated by the Telegram ACL into domain commands: `StatusRequested(project_id)`, `ActivateRequested(project_id)`, `PauseRequested(project_id)`.
- GitHub Issues as an alternative interface would be another ACL adapter in the Inbox context. The domain does not change. Only the adapter changes.

### For Agent Architecture

- Each Project is naturally a Steward Agent boundary (per Agentic DDD research). The orchestrator manages WHICH agent runs; the agent manages HOW it runs.
- The orchestrator's job is Context Delivery (per Boden Fuller's research): loading the right project context into Claude's window at the right moment. This is the primary value, not the scheduling.
- Claude CLI processes map 1:1 to PipelineRun entities. A PipelineRun starts when Claude is invoked, ends when Claude exits.

### For Operations

- The concurrency budget (max N Claude processes) is a Portfolio concept, not an infrastructure concept. The Portfolio knows about it because it enforces business-level resource allocation.
- Recovery after VPS reboot is a Pipeline context concern: on startup, Pipeline context reads its state file and determines which runs were interrupted (status = started but no completion event).
- Log aggregation is cross-context infrastructure, not a domain concept.

---

## Concerns and Recommendations

### Critical Issues

- **"Orchestrator" is not a domain concept, it is a process.** The existing spec treats `orchestrator.sh` as the primary artifact. In reality, it is the application service layer that coordinates three distinct domains (Portfolio, Inbox, Pipeline). The risk: all domain logic gets buried in the shell script with no clear boundaries. Fix: define the three contexts explicitly before writing any code. Even if the implementation is a single Python script or bash file, the logical boundaries must be clear.
  - **Rationale:** Application services that contain domain logic become "big balls of mud." The DLD framework has already documented this anti-pattern (TECH-145, ADR-007 etc.). The same discipline applies here.

- **The word "project" is doing too much work.** In the existing spec, "project" simultaneously means: a directory path, a Telegram topic, a scheduling unit, a pipeline state, and a business entity. This is the classic DDD warning sign — one word, multiple meanings across different parts of the system.
  - **Fix:** Define "project" precisely per context.
    - In Portfolio: a `Project` is a named business asset with a priority and a status.
    - In Inbox: a `Project` is the destination for routed messages (referenced by ID only).
    - In Pipeline: a `Project` has a `ProjectPipeline` — the lifecycle state machine for that project.
    - In Notification: a `Project` has a `DeliveryChannel` — the Telegram topic to notify on.
  - **Rationale:** The same word meaning different things in different parts of the system IS a context boundary. Forcing one model to serve all four meanings creates coupling that makes the system brittle to change.

- **Telegram topics are leaking into the domain model.** The existing spec has `topic_id` in the projects.json and throughout the routing logic. Topics are a Telegram-specific concept that should live only in the Telegram ACL adapter. If Telegram changes or is replaced, the domain model should not need to change.
  - **Fix:** The domain knows about `RoutingKey` (an abstract identifier). The Telegram ACL maps `message_thread_id` -> `RoutingKey` -> `Project.id`. The domain never sees `message_thread_id`.
  - **Rationale:** This is exactly what the existing morning briefing domain-map.md does correctly: Gmail API concepts never leak past GmailAdapter. Same discipline required here.

### Important Considerations

- **Is there a Portfolio subdomain?** Yes. The business need "manage N projects with limited compute" is distinct from "run a DLD lifecycle for one project." These are separate problems that happen to coexist. The Portfolio context solves the resource allocation and prioritization problem. The Pipeline context solves the lifecycle management problem. Both are Core subdomains because neither is generic (you cannot buy a Portfolio-of-DLD-projects off the shelf) and neither is merely supporting (both are primary value generators).

- **GitHub Issues as primary interface — domain perspective.** From a domain modeling standpoint, GitHub Issues could serve as the persistence layer for Inbox context (issues = inbox items) and Pipeline context (issue state = pipeline phase). The domain model does not care. What matters: whichever storage mechanism is chosen, it must be wrapped in an ACL so that GitHub API concepts (labels, assignees, milestones) never leak into the domain model. The domain speaks Idea, Phase, Run — not label, assignee, milestone.

- **The "portfolio" framing matters for the founder.** The founder does not think of themselves as "running processes." They think of themselves as "managing projects." The domain model should reflect this. When the founder opens the General topic and types `/projects`, they want to see their portfolio status — which projects are running, which are idle, which need attention. This is a Portfolio query, not an infrastructure status check. The language in the UI should match the domain language: "Project X is active (running autopilot on FTR-042)" not "process 12345 is running in slot 1."

### Questions for Clarification

- When you say a project is "registered" in the orchestrator, does that mean the founder is actively working on it, or does it include archived/paused projects? The answer determines whether Portfolio needs an Archive concept or whether paused = low visibility.
- Does "priority" in the orchestrator mean scheduling frequency (high priority = checked more often) or importance (high priority = gets a slot before medium priority)? These are different business rules with different implementations. Currently the spec conflates them.
- What happens to an idea captured in a project's inbox if that project is paused? Does it wait? Does the founder get notified? This is an important invariant for the Inbox -> Pipeline relationship.
- Does the founder ever need to see cross-project dependencies — e.g., "Project B is blocked waiting for Project A to finish X"? If yes, that is a Portfolio-level concept (dependency graph) that needs explicit modeling. If no, Portfolio stays simple.

---

## Final Position: Is "Orchestrator" a Domain or Infrastructure?

**It is neither, precisely. It is an Application Service.**

The word "orchestrator" describes what it does (coordinates), not what it IS in domain terms. The domains are Portfolio, Inbox, Pipeline, and Notification. The orchestrator script/process is the application layer that invokes these domains in the right order. This is a critical distinction:

- If "orchestrator" were a domain concept, it would have business rules: "the orchestrator must ensure that..." But the actual business rules belong to Portfolio ("no more than N active projects"), Pipeline ("phases are forward-only"), and Inbox ("every idea belongs to exactly one project").
- The orchestrator script has no rules of its own. It is pure coordination. That makes it application layer.

**Practical implication:** Whether the implementation is `orchestrator.sh` (bash) or a Python daemon or a Node.js process matters zero to the domain model. The domain model is the same regardless. The contexts, their invariants, their ubiquitous language, and their events are implementation-independent.

The existing spec correctly identified the right pieces (projects.json, state file, inbox, pipeline phases). It just categorized them incorrectly as "the orchestrator" rather than as distinct domain contexts that the orchestrator coordinates.

---

## References

- [Eric Evans — Domain-Driven Design: Tackling Complexity in the Heart of Software](https://www.domainlanguage.com/ddd/)
- [DDD Beyond the Basics: Multi-Bounded Context Integration](https://medium.com/ssense-tech/ddd-beyond-the-basics-mastering-multi-bounded-context-integration-ca0c7cec6561)
- [Integration of Bounded Contexts — Software Architecture Guild](https://software-architecture-guild.com/guide/architecture/domains/integration-of-bounded-contexts/)
- [Orchestrate or Choreograph? — Ben Johns](https://www.bennyjohns.com/posts/20210116-orchestrate-or-choreograph)
- [Steward Agents — Agentic DDD — Ben Johns](https://www.bennyjohns.com/posts/20260222-steward-agents-agentic-ddd)
- [Application Layer Orchestrators in DDD](https://hector-reyesaleman.medium.com/application-layer-orchestrators-service-facades-9b71b6e2ff7f)
- [AgentOps: Context Orchestration — Boden Fuller](https://www.bodenfuller.com/writing/context-orchestration)
- [Domain Services vs Application Services — Vladimir Khorikov](https://enterprisecraftsmanship.com/posts/domain-vs-application-services/)
- [How We Built an Agent Context Management System — Venture Crane](https://venturecrane.com/articles/agent-context-management-system/)
- [Anti-Corruption Layer Pattern — OneUptime](https://oneuptime.com/blog/post/2026-01-30-anti-corruption-layer-pattern/view)
