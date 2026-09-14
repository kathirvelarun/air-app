# The Investigate Service: Schema-Based Evidence Aggregation

This covers `POST /api/v1/investigate` - the service that runs all four
evidence agents in parallel and returns one aggregated response. It
implements the guide's **Section 8** (Evidence Aggregation): parallel
dispatch, aggregated evidence, and a timeline. It does **not** implement
**Section 9** (Root Cause Assessment) yet - there is no `rca` field in the
response. That's deliberate, not an oversight; see "On RCA" below.

The response is exactly the guide's Section 8.2 `AggregatedEvidence` shape -
`investigation_id`, `evidence`, `missing_agents`, `duplicate_count`,
`timeline` - and nothing else. This is a deliberate "schema-based context"
choice, in the same sense as the notebook's schema-based compaction
(`reference/Context_Engineering_Context_Rot.ipynb`): one structured contract
that preserves every agent's raw evidence untouched, rather than a second,
derived view (a "key findings" digest) sitting next to the data it
summarizes. See "On key findings" below for why that digest was removed.

See `docs/requests/section_08_investigate_request.json` for a sample
request body, and `docs/section_03_evidence_collection_plan.md` for how this
fits the overall plan.

## 1. Request accepted (HTTP boundary)

`POST /api/v1/investigate` hits `investigate` in
`src/air_agent_app/api/investigate_routes.py`. The body is validated against
`InvestigateRequest` (`src/air_agent_app/models/investigate.py`) - a
**superset** of every individual agent's own request model, since one call
has to carry enough information to build all four:

```python
class InvestigateRequest(TimeWindowRequest):
    investigation_id: UUID
    service_name: ShortText
    environment: ShortText
    agents: list[AgentName] = [...]       # which agents to run; defaults to all four
    repository: ShortText | None = None   # required only if DeploymentAgent is requested
    ...                                    # every other agent-specific field, all optional
```

Two validators run before any agent is touched:

- **`agents`** is typed `Literal["LogsAgent", "MetricsAgent", "TracesAgent", "DeploymentAgent"]`,
  not a bare `str`. An unrecognized name is a `422` at the request boundary,
  not a `ValueError` raised deep inside the service.
- **`validate_repository_for_deployment_agent`** rejects `"DeploymentAgent"`
  in `agents` when `repository` is `None`, since `DeploymentAgent`
  structurally cannot run without one.

`get_evidence_investigator()` (`src/air_agent_app/api/dependencies.py`) then
composes an `EvidenceInvestigator` from all four agents.

## 2. Parallel dispatch, with per-agent failure isolation

```python
async def investigate(self, request):
    requested = list(dict.fromkeys(request.agents))
    results = await asyncio.gather(
        *(self._run_one(name, request) for name in requested),
        return_exceptions=True,
    )
```

`_build_agent_request()` narrows the shared `InvestigateRequest` down to
each agent's own request type. Each agent then runs its own
`collect -> normalize -> summarize` pipeline exactly as it does behind its
individual `/api/v1/evidence/*` endpoint - `EvidenceInvestigator` doesn't
duplicate or reimplement any agent logic.

**This uses plain `asyncio.gather`, not a LangGraph subgraph.** There is no
conditional routing between these four agents - they're independent and
always all attempted - so a LangGraph state schema and node-wiring layer
would add machinery `gather` already provides, for no behavioral gain. If
branching logic is ever needed (e.g. skip `TracesAgent` unless `LogsAgent`
found something), that's the point to introduce a real subgraph.

`return_exceptions=True` plus a plain loop is what makes failure isolation
work (Section 10's rule: one failed evidence agent must not fail the whole
investigation):

```python
for name, result in zip(requested, results, strict=True):
    if isinstance(result, BaseException):
        missing_agents.append(name)
        continue
    evidence.extend(result)
```

A simulated ELF outage during development confirmed this: with `LogsAgent`
raising `ConnectionError`, the response still comes back `200` with
`"missing_agents": ["LogsAgent"]` and the other three agents' evidence intact
- see `tests/test_evidence_investigator.py::test_one_agent_failing_does_not_fail_the_investigation`.

## 3. Timeline (Section 8.1)

The first version of this sorted by `Evidence.observed_from` - which is
*wrong* in a subtle way: every agent sets `observed_from` to the query
window's start, so all four evidence items shared the same timestamp and
the "timeline" carried no real ordering information. This was caught by
actually running the full scenario and looking at the output, not by
reasoning about it in the abstract.

The fix (`_evidence_timestamp()` in
`src/air_agent_app/investigation/evidence_investigator.py`) prefers a
specific finding time when one exists in the agent's own `findings`:
`latest_deployment.timestamp` for `DEPLOYMENT`, `first_error_at` for `LOG`
and `TRACE`. `MetricsAgent` has no single-event timestamp to offer (its
findings are baseline-vs-window averages, not one occurrence), so it falls
back to the window start. For the payment-service scenario this produces:

```text
14:00:00Z  MetricsAgent     2 metric(s) show unhealthy deviation from baseline
14:00:00Z  DeploymentAgent  Deployment detected before incident
14:14:28Z  LogsAgent        5 log error event(s) observed
14:14:28Z  TracesAgent      10 error span(s) observed
```

The deployment visibly precedes the errors by 14 minutes 28 seconds -
matching the guide's own Section 8.3 example format ("Deployment 09:54 | +18
minutes | Application exception 10:12"), computed here without needing that
section's Evidence Intelligence Engine (also not implemented).

## 4. Response sent

```json
{
  "investigation_id": "...",
  "evidence": [ /* every Evidence returned, unmodified, for full auditability */ ],
  "missing_agents": [],
  "duplicate_count": 0,
  "timeline": [ /* chronologically ordered */ ]
}
```

No `key_findings` key, no `rca` key. Confirmed against the live OpenAPI
schema and the actual response body - both list exactly
`investigation_id, evidence, missing_agents, duplicate_count, timeline`.

`duplicate_count` is always `0` today: every agent currently returns exactly
one `Evidence` per run, so no two evidence items can collide. The field is
real, not decorative - Section 8.1 requires the aggregator to "deduplicate
or link duplicate observations" - it just has nothing to count yet. It
becomes load-bearing once an agent can return more than one `Evidence`, or
once `RecentIncidentAgent` (Section 7, not yet implemented) can overlap with
the others.

## On key findings

An earlier version of this service also returned a `key_findings` field: a
digest of each `Evidence` into `agent_name` / `evidence_type` / `title` /
`summary` / `confidence`, dropping the raw `findings` dict, sorted by
confidence descending. It was removed - not hidden behind a flag, actually
deleted (`KeyFinding` is gone from `models/investigate.py`, and
`_build_key_findings` is gone from `evidence_investigator.py`) - because it
was a second, redundant view of the same `evidence` list computed from data
already in the response. "Schema-based context" means committing to one
deliberate structure per concern, not a derived summary sitting next to the
data it summarizes: callers who want confidence-ordered evidence can sort
`evidence` themselves, and callers who want the raw `findings` no longer
have to reach past the digest to get them.

## On RCA

An earlier version of this service computed a `rca` field using a
deterministic, rule-based heuristic (confidence-threshold notability +
"did DeploymentAgent precede other notable evidence" correlation). It was
removed - not hidden behind a flag, actually deleted (`RootCause`,
`AlternativeCause`, `RootCauseAssessment` are gone from
`models/investigate.py`, and `_build_preliminary_rca` is gone from
`evidence_investigator.py`) - for two reasons:

1. It wasn't real reasoning, and shipping it risked being mistaken for the
   guide's actual Section 9 RCA Agent, which reasons over consolidated
   `InvestigationKnowledge` with an LLM.
2. The real RCA integration will need its own schema design once it exists
   (likely informed by what `InvestigationKnowledge` looks like, which
   depends on Section 8.3's Evidence Intelligence Engine - also not built).
   Keeping the heuristic's schema around as a placeholder would just be
   something to redesign later anyway, and an unused-but-present model is
   exactly the kind of premature abstraction this codebase avoids elsewhere.

**What's planned instead:** an LLM-based RCA agent, following the same
pattern Section 1's Planner already establishes in this codebase
(`PromptBuilder` + `LLMService` + `model_factory`, structured output via
Pydantic, offline fixture first, `--live` opt-in second). It will consume
this endpoint's aggregated evidence (or `InvestigationKnowledge`, if that
gets built first) and return a real `RootCauseAssessment`, added back into
this response - or as a separate endpoint - at that point, not before.
