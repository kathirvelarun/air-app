# Evidence Collection: Context and Plan

Source material: `reference/Context_Engineering_Context_Rot.ipynb` and Sections
3-10 of `reference/AIR_Agentic_SRE_Implementation_Guide.pdf`.

**Status:** Milestones 1, 2, and 3 (LogsAgent, MetricsAgent, DeploymentAgent
- the guide's Sections 4, 5, and 6) are implemented, plus one specialist the
guide doesn't define (`TracesAgent`, see
`docs/extension_01_traces_agent.md`). Only `RecentIncidentAgent` (Section 7)
is left unimplemented among the guide's four. All four built agents share
the `Evidence` contract and `BaseEvidenceAgent`'s full
collect/normalize/summarize pipeline, run against offline tools continuing
the notebook's exact payment-service scenario, and are reachable at
`POST /api/v1/evidence/{logs,metrics,traces,deployments}`. Notably:
MetricsAgent materializes the notebook's cache-service decoy as a real,
correctly-flagged-but-unrelated `UNHEALTHY` finding; DeploymentAgent finds
the exact v2.4.1 deployment the notebook's `config_dump()` buries a comment
against, touching the same config file LogsAgent/TracesAgent's errors trace
back to. See
`src/air_agent_app/investigation/{logs_agent,metrics_agent,traces_agent,deployment_agent}.py`,
`tests/test_{logs,metrics,traces,deployment}_agent.py`,
`tests/test_evidence_api.py`, `docs/section_0{4,5,6}_*.md`, and
`docs/extension_01_traces_agent.md` for the detailed walkthroughs.

**Milestone 4 (Evidence Aggregation, Section 8) is implemented.**
`EvidenceInvestigator`
(`src/air_agent_app/investigation/evidence_investigator.py`) runs all four
agents in parallel via `POST /api/v1/investigate` and aggregates into
exactly Section 8.2's `AggregatedEvidence` schema: `investigation_id`,
`evidence`, `missing_agents`, `duplicate_count`, `timeline` - a deliberate
schema-based-context choice, not an ad hoc shape. Two things lived here
before and were removed rather than kept as convenient extras: a
`key_findings` digest (a confidence-ordered, redundant second view of the
same `evidence` list), and a preliminary `RootCauseAssessment` produced via
a deterministic confidence/correlation heuristic. Both were removed - not
disabled, the code is gone - because a digest duplicates data already in the
response, and the heuristic wasn't real reasoning. The response has no
`key_findings` and no `rca` field. See
`docs/section_08_investigate_service.md`,
`src/air_agent_app/investigation/evidence_investigator.py`, and
`tests/test_evidence_investigator.py`/`tests/test_investigate_api.py`.

**Milestone 5 (RCA, Section 9) is now implemented.** `RcaService`
(`src/air_agent_app/investigation/rca_service.py`) is the genuine
LLM-based RCA agent, following Section 1's Planner pattern
(`RcaPromptBuilder` + `RcaLLMService` + `create_rca_llm_service`, offline
fixture first) and consuming `/api/v1/investigate`'s exact response as its
own request body - the "Direct Evidence Collection Handoff" architecture
from `reference/AIR-Investigation.pdf`, which explicitly removes any
separate `EvidenceValidator` stage. It returns a real
`InvestigationResult` (Key Findings, RCA, Suggestion Plan,
`INCONCLUSIVE` as a valid outcome) behind `POST /api/v1/rca`, source
references checked post-hoc against the supplied evidence, and bounded
retry for execution failures only. See `docs/section_09_rca_agent.md`.

Only `RecentIncidentAgent` (Section 7) and the real Evidence Intelligence
Engine (Section 8.3) remain unimplemented.

## 1. The notebook: `Context_Engineering_Context_Rot.ipynb`

**Core lesson - "context rot":** having more context does not mean better
reasoning. Even well inside a model's context-window limit, reasoning quality
degrades when the useful signal gets buried under a lot of low-value
information.

**The demonstration:**

- A simulated payment-service incident investigation runs 16 tool calls. The
  real root cause (`connection_timeout_ms: 300 -> 30`) is buried inside a
  1,500-line config dump early on (step 2 of 16).
- Near the end, a decoy appears: an APM anomaly report claims 94%-confidence
  cache-service memory leak - dramatic, recent, and confident-sounding.
- **Baseline (send everything, ~101K tokens):** the model picks the decoy.
  Wrong.
- **Sliding window (keep only the last few messages):** also fails - the
  decoy is recent, so it survives the window; the real cause doesn't.
- **Schema-based compaction (the fix):** instead of deciding which raw
  *messages* survive, the full transcript is converted into a small
  structured JSON state - explicitly instructed to *list every distinct
  root-cause candidate, even if they conflict, and never drop one because a
  later one looks more confident*. Re-asking the same question against this
  ~445-token compacted state (vs. 101K raw), the model correctly names the
  timeout and rejects the decoy.

**The generalizable rule:** ask "what would be dangerous for this agent to
forget?" - and design a durable, structured state around that, rather than
trusting an ever-growing conversation. The right question isn't "how much
context can I send?" but "what's the minimum context needed for a correct
decision?"

## 2. The guide: Section 3 (Evidence Collection Architecture) through Section 10

Evidence collection isn't self-contained in Section 3 - it's the
architecture that Sections 4-9 fill in.

**Section 3 - the shared shape.** Once the Planner is `READY`, a subgraph
runs independent evidence specialists in parallel. They never call each
other; LangGraph coordinates via shared state. Every agent returns the same
`Evidence` contract (`agent_name`, `evidence_type`, `source_system`, `title`,
`summary`, `confidence`, `findings: dict`, `references`, observation window,
`collected_at`). Every agent is a `BaseEvidenceAgent` with the same
three-step shape: `collect()` (raw IO) -> `normalize()` (typed records) ->
`summarize()` (-> `Evidence[]`). **Hard boundary: evidence agents state
facts, never root cause or remediation.**

**Sections 4-7 - the four specialists**, all following one recurring pattern
(request model -> tool adapter -> normalizer -> deterministic analyzer ->
`EvidenceBuilder` -> `Evidence[]`):

- **LogsAgent** (ELF): counts/classifies exceptions, first/last-seen,
  affected classes/pods - computed deterministically, never LLM-counted. If
  an LLM touches this at all, it only sees already-normalized patterns,
  never raw log lines, and is explicitly barred from root-cause or
  remediation language.
- **MetricsAgent** (Prometheus/Datadog/Dynatrace): computes
  count/min/max/avg/delta per series, and - critically - always compares
  against a baseline window. A raw "CPU 67%" is ambiguous; "baseline 28% ->
  current 67%" is real evidence. Preserves per-pod breakdown so one hot pod
  isn't hidden by a healthy average.
- **DeploymentAgent** (GitHub): deployment/commit/rollback history. Must not
  infer that a change caused the incident - only that it happened, and when,
  relative to the incident.
- **RecentIncidentAgent**: historical similarity. MVP version does
  deterministic metadata scoring (same service/env/alert-type/metric -
  weighted 0.40/0.20/0.20/0.20); enterprise version adds pgvector semantic
  search. Explicit rule: a past incident's root cause is contextual, never
  fact, for the current one.

**Section 8 - Evidence Aggregation and InvestigationKnowledge.** This is the
section that is structurally identical to the notebook's compaction step.
Raw evidence never goes straight to RCA. An `EvidenceAggregator` merges
evidence from all completed agents, dedupes, builds a timeline, and reports
which requested agents are missing/failed. An `EvidenceIntelligenceEngine`
then infers only deterministic relationship types - `TEMPORAL`, `HEALTH`,
`CO_OCCURRENCE`, `HISTORICAL_SIMILARITY` (e.g. "exceptions started 18
minutes after deployment" - a temporal fact, explicitly not a causal claim).
The output is one `InvestigationKnowledge` object: timeline, evidence
groups, relationships, healthy components, affected components,
**contradictions** (kept, not resolved), historical context. This is the
durable, structured state that survives instead of a growing bag of raw
observations - exactly the notebook's "what would be dangerous to forget"
question, answered concretely for this domain.

**Section 9 - Handoff to RCA** (not in scope now, but it's the payoff): the
RCA agent only ever sees `InvestigationKnowledge`, never raw telemetry, and
`UNKNOWN`/low-confidence is a valid, expected output when evidence is
insufficient - never a fabricated cause.

**Section 10 - Engineering rules to preserve** (the constraints any
implementation must satisfy): evidence before reasoning; thin LangGraph
nodes (orchestration only, no business logic); tool adapters hide vendor
specifics behind one interface; structured Pydantic outputs everywhere,
never free text; every retry/replan loop has a bounded max; one failed
evidence agent must not take down the whole collection phase; negative/
healthy evidence is still evidence; historical similarity is context, never
truth.

## 3. Why these two documents were paired

They're the same lesson at two different layers:

| Notebook | Guide |
| --- | --- |
| Don't send 101K raw tokens; compact to structured state | Don't build agents that dump raw telemetry; extract deterministic facts first |
| Compaction must preserve conflicting candidates, not just the most recent/confident one | `InvestigationKnowledge` explicitly keeps contradictions; relationships are correlational (`TEMPORAL`), never causal |
| The compaction schema is an architectural decision, made once, upfront | The `Evidence` / `AggregatedEvidence` / `InvestigationKnowledge` contracts are that decision, already specified |
| Sliding window (recency-based) fails because recent != important | Metrics need a baseline, not a raw snapshot - the guide's own version of "don't trust what merely looks recent/confident" |

The practical implication for our build: the guide's architecture front-loads
the notebook's fix. Rather than letting evidence accumulate raw and
compacting afterward, each agent is required to normalize deterministically
at the source, and the Aggregator/Intelligence Engine step is the mandatory
"compaction stage" between evidence and reasoning - not optional cleanup.

## 4. Proposed plan (what/how/why) - not yet started

**What, in order:**

1. **Shared contract** (3.1-3.2): `Evidence` model, `EvidenceReference`,
   `BaseEvidenceAgent` ABC with `collect`/`normalize`/`summarize`/`execute`.
2. **One concrete specialist first - LogsAgent** (4): proves the full
   pattern (request -> tool adapter -> normalize -> deterministic pattern
   extraction -> `Evidence[]`) end-to-end before generalizing. Behind an
   offline fixture initially, mirroring how Section 1's `OfflinePlanModel`
   let us validate the planner without live credentials - no ELF cluster is
   available to us.
3. **A second specialist - MetricsAgent** (5): forces the
   baseline-comparison design to be real, not assumed, and proves the
   pattern generalizes across two different evidence shapes before we commit
   to it for four agents.
4. **EvidenceAggregator + `AggregatedEvidence`** (8.1-8.2): only meaningful
   once two or more agents can produce evidence to merge/timeline/dedupe.
5. **EvidenceIntelligenceEngine + `InvestigationKnowledge`** (8.3-8.4): the
   deterministic-relationship "compaction" layer - the direct payoff of the
   notebook's lesson.
6. **LangGraph wiring**: extend the existing single-pass planner graph with a
   parallel evidence-collection subgraph after `PLAN_READY`, with failure
   isolation per Section 10 (one agent's failure becomes evidence of a gap,
   not a crash).
7. DeploymentAgent, RecentIncidentAgent, and the RCA handoff (6, 7, 9) come
   after - deliberately not in this first milestone.

**How:** hold to what's already established in this codebase -
Pydantic-validated request/normalized/evidence models with `extra="forbid"`,
dependency-injected tool adapters (same `Protocol` pattern as `PlanModel`),
thin LangGraph nodes, a docstring and log on every method, offline fixtures
for anything without live credentials, tests before calling anything
"validated."

**Why this order specifically:** it's the minimum path to prove the
aggregation/compaction step for real (steps 4-5 need genuine multi-agent
evidence to be worth building), while never violating the guide's "evidence
before reasoning" rule by skipping straight to something that looks like
RCA.

## 5. Open decisions before implementation starts

1. **First-milestone scope**: Logs + Metrics only (recommended), or all four
   specialists before touching the Aggregator?
2. **Tool adapters**: offline fixtures first (matching how Section 1 was
   built), with live ELF/Prometheus wiring added later behind the same
   interface - or are real credentials/endpoints available to wire from the
   start?
3. **Persistence**: the guide's suggested layout has a `repositories/`
   package. Keep evidence/`InvestigationKnowledge` as in-memory return values
   for now (matching Section 1's no-persistence stance), or is durable
   storage in scope for this milestone?
