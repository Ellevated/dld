# Business Blueprint: DLD Agent Orchestration → Vertical Agent

**Date:** 2026-02-27
**Board Round:** 1
**Strategy:** Hybrid (Strategy 3 → Strategy 2)
**Founder Approved:** 2026-02-27

---

## Executive Summary

The Board evaluated three strategies across six directors plus Devil's Advocate and resolved four fundamental conflicts (pricing floor, product scope, speed vs safety, OpenClaw as asset or trap). The chosen path is a sequenced hybrid: execute Strategy 3 ("Steal the Patterns") immediately to generate real revenue from existing IP with zero product risk, then time-box a 30-day build of Strategy 2 ("Vertical Wedge") for empirical PMF validation.

Days 1–30 are not a warm-up. The DLD multi-agent orchestration patterns (ADR-007 through ADR-010) represent 6–12 months of documented, debugged, production-tested IP that no other public project has. The consulting and premium support pipeline starts immediately. Content goes live in week one. This phase generates revenue from what already exists, satisfying the "Done = money in the account" rule without triggering anti-pattern #1 (starting new things before finishing existing ones).

Days 31–90 introduce a narrow, time-boxed product bet: a morning briefing agent for solo founders. This is the narrowest possible wedge — structured data synthesis is one of the few agent tasks where current LLMs achieve >90% reliability. A 14-day free trial goes live, and conversion data drives the kill/scale decision at day 90. If trial-to-paid exceeds 7%, double down on Strategy 2. If not, Strategy 3 is already generating revenue and the product attempt itself adds authentic authority to the consulting practice. The Board explicitly rejected Strategy 1 ("Trust Layer") as the opening move — its 60–90 day time-to-revenue, marketplace security pipeline requirement, and direct OpenAI extinction exposure make it the wrong first bet for a 2-person team.

---

## Target Customer

### Phase 1 (Days 1–30): Developer Teams Hitting Agent Scale Problems

**Who:** Senior engineers and tech leads at 10–200-person companies building internal agent systems on LangGraph, AutoGen, or CrewAI. They have working prototypes but are hitting orchestrator crashes, context flooding (ADR-010 class problems), and subagent failures at scale.

**Pain:** They lose 2–4 engineering weeks to problems the DLD framework already solved. The research is scattered across GitHub issues; no consolidated, production-tested pattern library exists.

**Willingness to pay:** $500/month for premium support access; $5K–25K for a consulting engagement that delivers their specific architecture in 2–4 weeks rather than re-discovering it independently.

**Segment size:** Developer tooling + agent infrastructure consulting. 72% of enterprises now using or testing AI agents (Zapier 2026 survey). Target addressable segment for consulting: 500–2,000 developer teams globally in active build phase.

### Phase 2 (Days 31–90): Solo Founders Wanting an Autonomous Morning Briefing Agent

**Who:** Indie hackers and solo founders running 1–3 products. The Mejba Ahmed persona: 17 active SaaS subscriptions, spends 2+ hours/day on manual information synthesis (HN, newsletters, Twitter, email, calendar). Wants a single agent that compiles a prioritized morning briefing while they sleep.

**Pain:** Current solutions are either generic (ChatGPT/Claude chat, requires daily prompting) or complex (OpenClaw self-hosting, 2–4 hour setup). No managed product delivers a personalized, reliable morning briefing with zero API key management.

**Willingness to pay:** $99/month after 14-day free trial. This audience pays for outcomes, not infrastructure. The frame is "replace 4 of your $30/month tools" not "buy an AI agent."

**Segment size:** SAM = 50K–200K solo founders globally willing to pay $99+/month for automated synthesis. SOM in 3 years = 500–2,000 paying customers = $600K–2.4M ARR.

**Excluded in both phases:** Non-technical end users (onboarding cost too high), EU market (EU AI Act compliance = $50K–500K upfront, not viable before month 12), enterprise (compliance overhead), anyone requiring >10-minute setup for Phase 2 product.

---

## Revenue Model

### Phase 1: Consulting + Premium Support

| Stream | Price | Unit economics |
|--------|-------|----------------|
| Premium support subscription | $500/month | COGS ~$0 (founder time already spent). 85–95% gross margin. |
| Consulting engagement (architecture) | $5,000–25,000/engagement | Typical: 2–4 weeks. Near-zero COGS. |
| Workshops / training | $2,000–5,000/session | Productized founder expertise. |

**CAC:** $20–100 (content-led via technical blog + Twitter/X). Near-zero paid acquisition.

**Payback:** Immediate. First consulting inquiry can convert in 7–14 days. Support subscriptions generate revenue from month 1.

**Path to $10K MRR:** 20 support subscribers, or 1–2 consulting engagements/month. Realistic by day 45–60.

### Phase 2: SaaS ($99/month after 14-day free trial)

| Tier | Price | Task cap | Notes |
|------|-------|----------|-------|
| Free trial | $0 | 50 tasks / 14 days | Full access, creates urgency. No credit card at signup. |
| Solo | $99/month | 500 tasks / workspace | Primary monetization tier. |
| Pro | $249/month | 2,000 tasks / 3 workspaces | Priority support included. |

**No $29/month tier.** This is an explicit Board decision. $29 cannot cover LLM COGS ($20–35/user/month for narrow task scope) plus acquisition cost. The free trial replaces the $29 "experimenter" function; $99 replaces the $29 revenue function.

**COGS (Phase 2, Solo tier):** $20–35/user/month. Narrow task scope enables cheap model routing — Haiku/GPT-4o-mini handles 80% of briefing compilation work. Gross margin: 65–80%.

**LTV (Solo, 20% annual churn):** $594. LTV:CAC = 2–4:1 at content-led CAC of $150–300.

**Payback:** 2–5 months.

---

## Go-to-Market

### Phase 1: Technical Authority Channel (Days 1–30)

**Primary channel:** Founder-led technical content on Twitter/X and personal blog. This is the ONE channel with zero competition. No one else can write "How DLD ADR-008 solves context flooding in multi-agent pipelines" with 246 commits, 50+ documented bugs, and production ADRs as evidence.

**Content cadence:**
- Week 1: Publish "Why your multi-agent orchestrator crashes at scale (and how we fixed it)" — covers ADR-010. Link to DLD GitHub. Include reproducible examples.
- Week 2: "The caller-writes pattern: why subagents can't reliably write files and what to do instead" — covers ADR-007. Targets LangGraph/AutoGen developers.
- Week 3: "Background fan-out in multi-agent systems: 300x context reduction" — covers ADR-008/009.
- Week 4: Announce consulting and premium support. Direct CTA.

**Inbound pipeline:** Blog post → GitHub star → support inquiry → consulting engagement. Proven playbook: Authzed (4,500 stars → 25 enterprise customers at $50K+ ACV, zero outbound), Netdata ($0 spend, 10K daily active users).

**OpenClaw community:** Target developers who starred OpenClaw but never activated due to CVE-2026-25253 security concerns. These are the highest-intent prospects — they already decided to solve the problem, just not with that tool.

**Conference/community:** Submit talk proposals to AI Eng Summit, LLM-native dev communities. Speaking is free distribution and authority building.

### Phase 2: Outcome-Led Content Channel (Days 31–90)

**Primary channel:** Founder-led content on IndieHackers.com and Twitter/X showing specific daily outcomes. Not "AI agent platform" content — outcome-specific demonstrations: "My agent compiled this from 12 sources at 6am. Here's what it found relevant to my projects."

**Frame:** "Replace your $180/month tool stack with one agent." The Mejba Ahmed persona manages 17 subscriptions. The angle is consolidation and elimination, not AI capability.

**Conversion funnel:**
- Content → signup: 5–8% (high-intent IndieHackers audience)
- Signup → activation (first briefing received): 60–70% (managed hosting, no API key setup, 10-minute onboarding)
- Activation → paid (day 14): 10–15% target

**Kill gate:** Trial-to-paid must exceed 7% by day 90. Below 7% = PMF not proven. Revert to Strategy 3 full-time.

---

## Operating Model

### Phase 1 (Days 1–30): Founder Only

- **Headcount:** 1 (founder)
- **COGS:** Near-zero. No LLM API costs per customer. No hosted infrastructure per customer. Time is the only cost.
- **Infrastructure cost:** $0–200/month (blog hosting, GitHub Actions, domain).
- **Agent/human split:** N/A. This is a services and IP business.
- **Bottleneck:** Founder time. Mitigated by productizing the first consulting engagements into reusable templates and documentation that reduce delivery time for subsequent engagements.

### Phase 2 (Days 31–90): Founder + 1 Engineer

- **Headcount:** 2 (founder + 1 contract/part-time engineer for product build)
- **COGS per user/month:** $20–35 (LLM API $8–20 + hosting $3–8 + auth/tooling $3–5 + support $5–10)
- **Infrastructure:** Fly.io at launch (single-region, auto-scaling). Turso for SQLite-based storage. Clerk for auth. LiteLLM for model routing.
- **Agent/human split (product):**
  - Agent handles: briefing compilation, email triage classification, calendar conflict detection, usage metering
  - Human handles: edge case resolution, customer success for first 50 users, product iteration from feedback
- **No marketplace.** No skill submission pipeline. No security review queue. Starter skills are founder-curated (10–15 pre-vetted). This eliminates the COO's primary scaling bottleneck until month 4+.
- **No on-call rotation in Phase 2.** Bounded task scope (no shell execution, no financial transactions) means liability exposure is low. Explicit TOS excludes agent action liability.

### Month 4+ (If Strategy 2 PMF Confirmed)

- Second engineer at $10K MRR milestone
- Support subscription tooling (Intercom or equivalent)
- Begin marketplace security pipeline design (required before opening skill submissions)
- EU compliance assessment at $20K MRR

---

## Technical Constraints

These are Board-level hard stops. Non-negotiable.

1. **No marketplace before security pipeline.** Opening skill submissions without a static analysis + sandboxed execution review pipeline creates CVE-2026-25253 class exposure. Marketplace opens at month 4 at earliest, with a named security review barrel in place.

2. **No pricing below $99/month for any paid tier.** LLM COGS ($20–35/user/month for Phase 2 narrow scope) plus acquisition cost make anything below $99 structurally inviable. The $29 tier is permanently eliminated. Free trial (14 days, full access) is the only sub-$99 entry point.

3. **No EU market before compliance investment.** EU AI Act enforcement begins August 2026. Compliance cost: $50K–500K for a 2-5 person team. US-only launch. EU market assessed at month 12 when revenue can fund compliance.

4. **Sub-10-minute time-to-first-value required.** OpenClaw requires 2–4 hours of setup. The product wins by being managed: no API key setup, pre-configured starter skills, guided first task completes within 10 minutes of signup. If this is not achievable, the onboarding is broken, not the user.

5. **No general autonomous agent scope in Phase 2.** Scope is locked to high-reliability tasks (>90% success rate with current Claude Sonnet): structured data synthesis (morning briefing), email triage classification, calendar conflict detection. No financial transactions, no shell execution, no social posting. Scope expands only when reliability data supports it.

6. **Hard usage caps before $10K MRR.** LLM costs at scale ($250K–400K/day at 10K users × 5 tasks/day) require infrastructure-level caps, not honor-system limits. Monthly caps enforced at infrastructure layer before soft limits are added to UX.

---

## Risks and Mitigations

### Risk 1: OpenAI ships native autonomous agents in ChatGPT (6–12 months)

**Director source:** Devil's Advocate (primary), confirmed by CTO and CFO.

**Probability:** High. OpenAI hired Zak Steinberger specifically to build agentic features. 6–12 month timeline is credible.

**Impact:** Existential for a general agent platform. Moderate for narrow vertical agent with deep personalization. None for consulting/infrastructure IP.

**Mitigation (Phase 1):** Zero exposure. Infrastructure expertise is platform-agnostic. If OpenAI ships native agents, enterprises need to integrate and configure them — that is a consulting opportunity, not a threat.

**Mitigation (Phase 2):** Speed (ship in 30–45 days, not 6 months) + depth (behavioral learning of user priorities at month 3+ creates switching cost ChatGPT Tasks cannot replicate because ChatGPT is generic). The kill gate at day 90 forces a decision before OpenAI's window closes.

**Acceptable outcome:** If OpenAI ships and kills the Phase 2 product, Phase 1 is already generating revenue. The product attempt adds authentic "tried to build, here's what I learned" authority to the consulting practice.

### Risk 2: Consulting does not scale (founder time ceiling)

**Director source:** COO, Devil.

**Probability:** Certain if no productization happens. Consulting headroom is $200K–500K/year for a solo founder.

**Impact:** Financially successful but does not build a recurring SaaS revenue stream. Acceptable as an outcome per founder profile ("Revenue. Clients. Money in the account.").

**Mitigation:** Productize the first 2–3 consulting engagements into reusable templates, architecture guides, and decision frameworks that reduce delivery time from 4 weeks to 1 week. This scales the consulting practice 3–4x without adding headcount. If Phase 2 SaaS proves PMF, transition consulting to lead generation rather than primary revenue.

### Risk 3: Phase 2 TAM ceiling is too low for venture ambition

**Director source:** Devil, CFO.

**Probability:** High. SAM for "solo founders willing to pay $99/month for morning briefing" = 50K–200K globally. SOM in 3 years = 500–2,000 paying customers = $600K–2.4M ARR. This is a lifestyle business ceiling, not a Series A outcome.

**Impact:** Phase 2 becomes a cash-flow positive but sub-$3M ARR business. Acceptable given founder profile and the hybrid structure (Phase 1 generates real revenue regardless).

**Mitigation:** If Phase 2 hits 200+ paying customers, evaluate expansion to adjacent tasks (email management, project coordination) where reliability data now supports it. The vertical wedge strategy's design is specifically to earn scope expansion through proved reliability, not to cap at the briefing use case forever.

### Risk 4: "Morning briefing" does not feel like a $99/month product

**Director source:** Devil, CMO.

**Probability:** Medium. Willingness-to-pay must be validated empirically — the Board cannot resolve this without trial data.

**Impact:** Trial-to-paid conversion stays below 7%, kill gate triggers at day 90.

**Mitigation:** The 14-day free trial is the validation mechanism. Do not pre-optimize pricing. Do not add features to justify the price. Let the trial data speak. If conversion fails, the lesson costs 30 days of engineering time — acceptable because Phase 1 already covers baseline revenue.

---

## Unit Economics

### Phase 1: Consulting + Premium Support

| Metric | Value | Source |
|--------|-------|--------|
| CAC | $20–100 | Content-led. CMO Research, channel benchmarks. |
| Gross margin | 85–95% | Pure IP/service, near-zero COGS. CFO Research. |
| Revenue per support subscriber | $6,000/year | $500/month × 12. CFO Research. |
| Revenue per consulting engagement | $5,000–25,000 | CFO Research, Strategy 3 pricing. |
| Time to first revenue | 7–14 days | Inbound from week-1 content. |
| Break-even | Day 1 | Zero infrastructure cost. |

### Phase 2: SaaS (Solo Tier, $99/month)

| Metric | Value | Source |
|--------|-------|--------|
| TAM | ~$7B (2025), 45% CAGR | CFO Research, multiple analyst sources. |
| SAM (solo founder segment) | $800M–1.5B | CFO Research (developer/prosumer subset). |
| SOM (3-year, 2-person team) | $600K–2.4M ARR | CFO Research, Strategy 2 model. |
| CAC | $150–300 | Content-led, IndieHackers/Twitter. CMO Research. |
| COGS/user/month | $20–35 | LLM ($8–20) + hosting ($3–8) + auth/tooling ($3–5) + support ($5–10). CFO Cross-Critique. |
| Gross margin | 65–80% | At average usage. CFO Cross-Critique. |
| LTV (20% annual churn) | $594 | $99 × 12 × (1 / 0.2 churn). CFO Research. |
| LTV:CAC | 2–4:1 | At $150–300 CAC. Acceptable; target >3:1. |
| Payback period | 2–5 months | Content-led CAC. CFO Research. |
| Break-even (subscribers) | ~100 | $10K MRR. CFO Research, Strategy 2 model. |
| Target break-even timeline | 6–9 months | From Phase 2 launch (month 4–5 total). |

---

## Decisions Made

1. **Hybrid sequence chosen (Strategy 3 → Strategy 2), not Strategy 1.** Strategy 1's 60–90-day time-to-revenue, marketplace security pipeline requirement, and direct OpenAI extinction exposure make it the wrong opening move for a 2-person team. Strategy 3 generates real revenue from existing IP with zero product risk. Strategy 2 is a time-boxed bet with a binary kill gate.

2. **No $29/month tier. Ever.** Board resolved Conflict 1 definitively. LLM COGS plus acquisition cost make sub-$99 pricing structurally inviable. Free trial (14-day) replaces the experimenter function. Minimum paid tier = $99/month.

3. **No marketplace at launch.** Board resolved Conflict 3. Curated 10–15 starter skills (founder-vetted) eliminate the marketplace security pipeline as a launch blocker. Marketplace opens at month 4+ with a named security review owner in place.

4. **Do NOT fork OpenClaw.** CTO's position, accepted by Board. Use concepts (heartbeat, skills-as-config, multi-platform); different implementation (sandboxed, permission-scoped, audited). DLD ADR-007 through ADR-010 are the technical foundation.

5. **Scope Phase 2 to >90% reliability tasks only at launch.** CTO and Devil agree: general autonomous agents fail 70% of the time (Carnegie Mellon). Launch scope = structured data synthesis (morning briefing), email triage classification, calendar conflict detection. No financial transactions, no shell execution.

6. **US-only launch.** EU AI Act compliance ($50K–500K) is not a launch requirement. Assess at month 12.

7. **14-day free trial (full access, 50 tasks), not freemium.** Trial creates urgency and pre-qualifies users. Freemium creates a permanent support burden from users who will never pay. Trial-to-paid target: 10–15%.

8. **Kill gate at day 90: trial-to-paid > 7%.** This is the single binary decision point. Above = scale Strategy 2. Below = full commitment to Strategy 3 consulting practice. No moving the goalposts.

9. **Infrastructure-level usage caps before $10K MRR.** LLM cost spiral is fatal at scale. Hard caps enforced at infrastructure layer (not UX honor system) before the product reaches any meaningful user base.

10. **Sub-10-minute time-to-first-value is a launch requirement, not a nice-to-have.** If a new user cannot receive their first agent output within 10 minutes of signup, the product is not ready to launch.

---

## Open for Architect

The Board leaves the following questions explicitly open for the Architect to resolve in the System Blueprint:

1. **Skill execution sandbox for Phase 2.** Phase 2 (morning briefing) has a bounded task scope. Does it require E2B Firecracker microVM isolation, or is a lightweight Node.js worker process with network-scoped permissions sufficient? The security surface of "read from 12 RSS feeds + Gmail API + Google Calendar API + synthesize" is different from general shell execution. Architect should evaluate E2B ($21M Series A, production-proven) vs. lighter alternatives given the narrow Phase 2 scope.

2. **LLM routing for COGS management.** The COGS model assumes cheap model routing (Haiku/GPT-4o-mini for 80% of briefing work). Architect should design the model routing layer (LiteLLM or direct) with explicit fallback logic, cost-per-task tracking, and hard caps at both task and monthly levels.

3. **Behavioral memory architecture.** The Phase 2 retention model depends on "agent learns user priorities over time." What is the specific data model for learned preferences (which sources matter, which email senders are urgent, which calendar events to protect)? This is the switching cost mechanism — it must be designed for durability and portability, not as a side effect of prompt history.

4. **Auth and multi-workspace for Phase 2.** Clerk for auth is the Board's assumption. Architect should validate this against the Phase 2 scope: 1 workspace per Solo tier, 3 per Pro. Key question: does Clerk's org model map cleanly to the workspace isolation requirement, or does it introduce unnecessary complexity for a 2-person team?

5. **Data storage for Phase 1 consulting toolkit.** Phase 1 publishes DLD orchestration patterns as a standalone developer toolkit. What is the artifact format? Git repository with documented ADRs + runnable examples? npm package? Docker image? Architect should define the packaging that maximizes adoption velocity for the developer target customer.

6. **Reliability measurement pipeline.** Both phases require measuring task success rate against the ">90% reliability" threshold. What is the specific measurement mechanism? Human eval sample? LLM-as-judge? Deterministic output validation? Architect should define this as a first-class system component, not a post-hoc measurement.

---

## Kill Gates

### Day 90 Kill Gate (Primary)

**Metric:** Phase 2 free trial → paid conversion rate at 14 days

| Result | Decision |
|--------|----------|
| Trial-to-paid > 7% | Double down on Strategy 2. Hire second engineer. Expand task scope per reliability data. |
| Trial-to-paid 3–7% | Iterate for 30 more days on onboarding and activation. One more measurement at day 120. |
| Trial-to-paid < 3% | Kill Strategy 2. Full commitment to Strategy 3. Product attempt adds consulting authority. |

### Phase 1 Kill Gate (Day 30)

**Metric:** Consulting pipeline inbound inquiries

| Result | Decision |
|--------|----------|
| 3+ consulting inquiries by day 30 | Phase 1 is working. Continue Phase 1 in parallel with Phase 2 build. |
| 0–2 inquiries by day 30 | Content channel is not working. Revise content angle or distribution. Do not launch Phase 2 until Phase 1 shows signal. |

### Ongoing Hard Stops (Any Phase)

- **LLM cost burn > $500/month before 50 paying users** → pause, fix cost model before acquiring more users
- **Support ticket volume > 10/week with 1 founder handling support** → hire support before acquiring more users
- **Any regulatory inquiry (EU, financial, healthcare)** → halt affected user type, legal assessment before resuming
- **Agent action causes user data loss or financial harm** → immediate incident response, TOS review, public disclosure if required
