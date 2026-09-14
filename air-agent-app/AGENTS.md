# AIR agent module conventions

Keep reusable Python code in `src/air_agent_app/` under these packages:

- `api`: HTTP routes, application factory, dependencies and error handlers.
- `commands`: thin named command entry points.
- `agent`: application entry points, LangGraph orchestration, runtime configuration and CLI composition.
- `models`: typed contracts, state data and application exceptions.
- `tools`: IO adapters, model-provider clients and mock implementations.
- `context`: context preparation and prompt construction.
- `investigation`: planning policy and evidence-agent policy (`BaseEvidenceAgent`
  and concrete agents such as `LogsAgent`).

Do not construct mock adapters inside reusable agent, context or investigation
code. Mock data and composition belong under `tools/mock`; `agent/cli` can
select them. Implement future evidence-collection agents (logs, metrics,
deployment, recent-incident) under `tools`/`investigation` when they have
working behavior and a legitimate caller. Do not add empty adapter classes or
unused abstractions for future integrations.

Every function and method must have type hints and a docstring. Each file owns
one responsibility. Keep credentials out of source, fixtures, logs and reports.
The planner graph makes one logical model call and has only `PLAN_READY` and
`PLANNER_FAILED` outcomes. Failure reasons are `NO_AGENTS_SELECTED` and
`MODEL_FAILURE`; do not reintroduce graph-level retry or review routing implicitly.

This module implements the Investigation Planner (the guide's Section 1:
`IncidentInput` -> `ContextBuilder` -> `PromptBuilder` -> `LLMService` ->
`PlannerOutput`, orchestrated by a two-node LangGraph), a thin FastAPI layer
over it, and four evidence specialists: `LogsAgent`, `MetricsAgent`, and
`DeploymentAgent` from the guide's Sections 4-6, plus `TracesAgent` -
**not** one of the guide's four defined evidence agents
(Logs/Metrics/Deployment/RecentIncident); a locally designed fifth
specialist for distributed-tracing evidence, built to the same shape (see
`docs/extension_01_traces_agent.md`). Only `RecentIncidentAgent` (Section 7)
remains unimplemented. All four follow `BaseEvidenceAgent`'s
`collect` -> `normalize` -> `summarize` shape and are purely deterministic
(no LLM calls). `EvidenceInvestigator` (Section 8) aggregates their output,
and `RcaService` (Section 9, `POST /api/v1/rca`) is the one place an LLM
actually reasons over evidence to produce Key Findings, an RCA, and a
Suggestion Plan - see below and `docs/section_09_rca_agent.md`. See
`docs/section_03_evidence_collection_plan.md` for the full plan and its
connection to `reference/Context_Engineering_Context_Rot.ipynb`. Schema
compaction, technical retry, and usage/cost tracking were removed pending
a fresh design; do not reintroduce them ad hoc.

Evidence agents state facts only, never a root cause or a remediation
(Section 3.2's hard boundary) - this applies to `TracesAgent` too, even
though it isn't guide-specified. Each agent gets its own request/normalized
models and its own tool adapter under `tools/`; do not thread evidence
concerns back through the Planner's own models (`PlannerOutput`,
`PlannerContext`, `ContextBuilder`, `LLMService`). All four agents currently
have only offline tools
(`tools/mock/fixtures/offline_{log,metric,trace,deployment}_tool.py`) -
there is no real ELF, metrics-platform, tracing-platform, or GitHub adapter
yet - so do not add a `--live` switch for any of them until one exists with
a legitimate caller. Every single-agent evidence endpoint returns the shared
`EvidenceResponse` model (`models/evidence_response.py`); do not create a
new per-agent response model unless an agent's response shape genuinely
needs to differ. The shared `EvidenceType` literal (`models/evidence.py`)
documents which values are guide-defined
(`LOG`/`METRIC`/`DEPLOYMENT`/`HISTORICAL_INCIDENT`) versus local extensions
(`TRACE`) - keep that distinction visible if more get added. Doc filenames
follow the guide's own section numbers (`docs/section_0N_*.md`); non-guide
work uses a separate `docs/extension_NN_*.md` sequence so the two never
collide (`extension_01` is `TracesAgent`).

`EvidenceInvestigator` (`investigation/evidence_investigator.py`) composes
all four agents behind `POST /api/v1/investigate`: parallel dispatch via
`asyncio.gather(..., return_exceptions=True)` (not a LangGraph subgraph -
there is no conditional routing between agents, so gather does the job with
less machinery; introduce a real subgraph only if branching logic is ever
needed), per-agent failure isolation into `missing_agents`, and a timeline.
The response is exactly the guide's Section 8.2 `AggregatedEvidence` schema
(`investigation_id`, `evidence`, `missing_agents`, `duplicate_count`,
`timeline`) - a deliberate schema-based-context choice, not an ad hoc
convenience shape. **There is no `key_findings` digest and no `rca` field
on this response.** An earlier version computed both: a confidence-ordered
`key_findings` digest of the same `evidence` list, and a
deterministic-heuristic `RootCauseAssessment`. Both were deleted, not
disabled - the digest because it was a redundant second view of data already
in the response, and the heuristic RCA because it wasn't real reasoning.
See `docs/section_08_investigate_service.md`.

Root-cause assessment (the guide's Section 9) is now `RcaService`
(`investigation/rca_service.py`) behind `POST /api/v1/rca`: a genuine
LLM-based agent, following Section 1's Planner pattern
(`RcaPromptBuilder` + `RcaLLMService` + `create_rca_llm_service`, offline
fixture first). Per `reference/AIR-Investigation.pdf` ("LLM Integration -
Direct Evidence Collection Handoff"), this is a **direct handoff**: the
`/api/v1/rca` request body is typed as `InvestigateResponse` - literally
what `/api/v1/investigate` returns - and there is **no separate
`EvidenceValidator` stage**. Pydantic validating the request body at the
HTTP boundary is the only "acceptance" check; nothing re-judges evidence
quality before the model sees it. What *does* run after the model call are
two output-contract checks (`investigation/rca_post_checks.py`):
`validate_source_refs` (the model may only cite
`{agent_name}/{evidence_type}` references actually present in the
evidence - `investigation/rca_source_refs.py` - never an invented ID) and
`enforce_human_approval` (any production-changing suggestion gets
`requires_human_approval = True` regardless of what the model itself set).
Both are frozen-model `model_copy` rebuilds, never in-place mutation,
matching every other model in this codebase.
`investigation/rca_retry.py::run_with_retry` bounds retries at
`MAX_RCA_ATTEMPTS = 2` for execution failures only (invalid structured
output, transport failure, invented references) - never for
`investigation_status = "INCONCLUSIVE"`, which is a valid, expected
outcome (Section 9's "Unknown is a valid result" rule), not a failure. The
system prompt lives in its own versioned file
(`context/prompts/rca.py`), matching `context/prompts/planner.py`'s
pattern; evidence never goes in that file, only in the per-request user
message (`context/rca_prompt_builder.py`). See
`docs/section_09_rca_agent.md`.

`POST /api/v1/incidents/investigate` (`agent/orchestration_application.py`
+ `agent/graph/orchestration_graph.py`) chains all three stages -
Planning -> Evidence Collection -> RCA - in one call, for callers who don't
want to make three separate requests and wire the outputs together
themselves. It is a genuinely new 3-node LangGraph, kept separate from
`planner_graph.py` (different single responsibility), and every node calls
one *existing* service unchanged (`PlanningApplication`,
`EvidenceInvestigator`, `RcaService`) - no business logic duplicated into
the graph itself. Both conditional routers share one shape: a node stops
the pipeline by setting `status` in the state dict it returns, and every
router just checks `"status" in state` - do not add per-stage routing
logic that duplicates this check. The response
(`OrchestrationResponse`) nests each stage's own existing response type
unchanged (`planning`, `evidence`, `rca`) plus one outer `status` -
`COMPLETED`, `INCONCLUSIVE`, `PLANNER_FAILED`,
`EVIDENCE_REQUEST_INVALID`, `NO_EVIDENCE_COLLECTED`, or `RCA_FAILED`. RCA
is skipped only when evidence collection produced *zero* evidence
(`NO_EVIDENCE_COLLECTED`) - never on evidence that merely looks weak; that
judgment stays entirely the RCA model's own `INCONCLUSIVE` call, so do not
add a second "is this evidence good enough" check anywhere in this graph.
The graph's mermaid diagram is logged once per process at compile time
(not per request - the topology never changes); every node logs its own
start/completion as a capitalized stage-status line
(`PLANNING completed ...`, `EVIDENCE_COLLECTION completed ...`,
`RCA completed ...`) for exactly this reason - keep that pattern for any
new node. `OrchestrationRequest` also carries `required_metrics`/
`required_operations` (passed straight through to the built
`InvestigateRequest` in `collect_evidence`) - the Planner produces no
per-agent metric breakdown today, so a scenario needing a metric outside
`MetricsAgent.DEFAULT_METRICS` (e.g. `disk_usage_pct`) has no other way to
reach evidence collection through this single endpoint; do not try to
infer these from the incident text instead of making the caller state
them. See `docs/extension_02_end_to_end_orchestration_plan.md` (the
pre-build plan) and `docs/extension_03_end_to_end_orchestration_agent.md`
(the as-built design, including why `OrchestrationRequest` carries more
than `IncidentInput` alone and how the Planner's free-text
`parallel_agents` gets safely narrowed to evidence collection's known
agent set).

Building the investigator surfaced a real bug in existing mock data:
`log_dump.py` and `trace_dump.py` originally injected the payment-service
failure pattern for *any* service name, unlike `metric_series.py` and
`deployment_dump.py`, which correctly gated on a service profile. If you
add a new mock generator, make sure it gates on service name the same way
- an ungated generator will silently make every service look broken.

Three named demo scenarios exist, each a different root-cause class, each
purely a mock-data addition -- **no agent code changes required to add
one**, since all four evidence agents parse whatever `key=value`
fields/metric names their mock data contains, with nothing hardcoded to
any one service: `payment-service` (config change, Sections 4-9's running
example), `web-ui` (a code/contract issue - the UI's own parsing code
fails on a downstream response shape, fast-failing, latency stays
healthy), and `ledger-service` (infrastructure capacity exhaustion -
`disk_usage_pct` is a new metric name, requested via `required_metrics`
since it isn't in `MetricsAgent.DEFAULT_METRICS`; deliberately has no
entry in `deployment_dump.py`'s profile table, so DeploymentAgent reports
genuine negative evidence instead of a deployment being invented to
explain it). Each of the four `tools/mock/fixtures/*.py` generators keys
its per-service failure pattern off a small profile dict/dataclass (see
`log_dump.py`'s `LogScenario` / `trace_dump.py`'s `TraceScenario` /
`metric_series.py`'s `_METRIC_PROFILES` / `deployment_dump.py`'s
`_DEPLOYMENT_PROFILES`) - add a new scenario by adding an entry to each,
not by branching on service name inline. `generate_metric_samples`
clamps fraction-style metrics (both profile values `<= 1.0`) to `[0.0,
1.0]`; percentages can't physically exceed 100%, a real bug the
`ledger-service` scenario's `disk_usage_pct` (target `0.998`) surfaced.
See `docs/extension_04_demo_scenarios.md`.

Before finalizing changes, run pytest and Ruff, exercise the planner CLI
(`python -m air_agent_app.commands.planner`) and the API test suite
(including `/api/v1/evidence/logs`, `/api/v1/evidence/metrics`,
`/api/v1/evidence/traces`, `/api/v1/evidence/deployments`,
`/api/v1/investigate`, `/api/v1/rca`, and
`/api/v1/incidents/investigate`), and trace every new function/class/method
to its call site.
