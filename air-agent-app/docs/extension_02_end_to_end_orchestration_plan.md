# End-to-End Orchestration: Plan (Planning → Evidence Collection → RCA)

**Status: implemented.** This was written as a plan doc before any code —
matching how `docs/section_03_evidence_collection_plan.md` was written
before Evidence Collection was built — and is kept as-is below for that
history. See `docs/extension_03_end_to_end_orchestration_agent.md` for the
as-built design: what got decided on the 5 open questions below, the new
`EVIDENCE_REQUEST_INVALID`/`NO_EVIDENCE_COLLECTED` outcomes the field
mapping between `IncidentInput` and `InvestigateRequest` required, and the
verified request/response/log examples.

## 1. What exists today

Three independently built, independently verified stages, each its own
HTTP endpoint, with no code connecting them:

```
POST /api/v1/planning        POST /api/v1/investigate       POST /api/v1/rca
IncidentInput                InvestigateRequest              InvestigateResponse
     |                            |                               |
     v                            v                               v
PlanningResponse             InvestigateResponse            InvestigationResult
(PLAN_READY /                (evidence, timeline,           (key_findings, rca,
 PLANNER_FAILED)              missing_agents)                 suggestion_plan)
```

A caller today has to: call `/planning`, read `plan.parallel_agents` off
the response, hand-build an `InvestigateRequest`, call `/investigate`,
then pipe that response body straight into `/rca`. Nothing validates that
a caller does this correctly, and nothing stops a caller from skipping a
stage.

Each stage uses a different orchestration mechanism, deliberately:

| Stage | Mechanism | Why |
| --- | --- | --- |
| Planning | 2-node LangGraph (`build_planner_graph`) | needs conditional routing (`accepted` / `failed`) |
| Evidence Collection | `asyncio.gather(..., return_exceptions=True)` | 4 independent agents, no branching between them |
| RCA | Plain service call + bounded retry loop | one call, one retry policy |

## 2. What a single entry point needs to do

This maps directly onto `reference/AIR-Investigation.pdf`'s own "Updated
LangGraph Flow" diagram (`EvidenceCollection → LLM Investigation Agent →
Post-LLM Checks`, with conditional routing on `investigation_status`) —
extended one stage further back to start from Planning, since that
diagram already assumes evidence has been collected.

```
START
  |
  v
build_context + generate_plan          (existing planner_graph nodes)
  |
  +--> [PLANNER_FAILED] --> END (planning_failed response, stop here)
  |
  v
[PLAN_READY]
  |
  v
collect_evidence                        (EvidenceInvestigator.investigate,
  |                                       agents = plan.parallel_agents)
  v
run_rca                                 (RcaService.investigate)
  |
  +--> [COMPLETED]     --> END
  +--> [INCONCLUSIVE]  --> END  (valid outcome, not a failure)
  +--> [execution error, retries exhausted] --> END (escalation response)
```

Unlike Evidence Collection's internal fan-out (no branching → `gather`
was the right call), this outer flow *does* need conditional routing —
`PLANNER_FAILED` must stop the whole pipeline before evidence collection
ever runs — so a LangGraph is the right tool here, not another plain
async function.

## 3. Draft state schema

```python
class OrchestrationState(TypedDict, total=False):
    investigation_id: UUID
    incident: IncidentInput
    planning_status: Literal["PLAN_READY", "PLANNER_FAILED"]
    planner_output: PlannerOutput | None
    terminal_reason: str | None
    evidence: InvestigateResponse | None
    rca_result: InvestigationResult | None
    rca_error: str | None   # set only if RCA raised RcaExecutionError
```

Each node in section 2 reuses an *existing* service unchanged
(`PlannerService`, `EvidenceInvestigator`, `RcaService`) — this graph is
pure orchestration, no new business logic, matching Section 10's "thin
LangGraph nodes" rule already followed by `planner_graph.py`.

## 4. Response shape — open decision, see section 6

Two real options, not yet chosen:

**Option A — nested, everything in one response body:**
```json
{
  "investigation_id": "...",
  "planning": { "status": "PLAN_READY", "plan": { ... } },
  "evidence": { "evidence": [...], "missing_agents": [...], "timeline": [...] },
  "rca": { "investigation_status": "COMPLETED", "key_findings": [...], "rca": {...}, "suggestion_plan": {...} }
}
```
Simple, one round trip, but a large response body even when a caller
only wants the final RCA result; also means designing a 4th top-level
schema that partially duplicates the three that already exist.

**Option B — return exactly `InvestigationResult`, nothing more:**
The orchestrator's whole point is producing an RCA; intermediate
`planner_output`/`evidence` stay server-side (logged, not returned)
unless a caller separately hits the existing three endpoints for detail.
Smaller response, no new top-level schema — but a caller who wants to see
*why* an investigation stopped at `PLANNER_FAILED` (e.g. no agents
selected) loses that detail unless it's folded into `terminal_reason`.

## 5. Failure semantics (mapping existing per-stage outcomes)

| Where it fails | Existing signal | Orchestrator response |
| --- | --- | --- |
| Planning | `PLANNER_FAILED` (`MODEL_FAILURE` / `NO_AGENTS_SELECTED`) | Stop before evidence collection; `502`-equivalent or a terminal status field — not yet decided |
| One evidence agent | Already isolated into `missing_agents` (never fails the request) | Pipeline continues to RCA with partial evidence, same as today |
| All evidence agents | `missing_agents` == all requested | RCA still runs; `OfflineInvestigationModel`-equivalent live behavior would likely be `INCONCLUSIVE` given no evidence — real LLM behavior needs verifying, not assuming |
| RCA | `INCONCLUSIVE` | Not a failure — a normal terminal response |
| RCA | `RcaExecutionError` (retries exhausted) | Maps to `502` today at `/api/v1/rca`; same mapping likely correct here |

## 6. Open decisions before implementation starts

1. **Response shape**: Option A (nested, everything) vs Option B (final
   `InvestigationResult` only) — section 4.
2. **Latency / timeout model**: a single HTTP request would now block for
   a planner LLM call + parallel evidence fetch + an RCA LLM call with its
   own bounded retries — realistically several seconds to tens of
   seconds. Keep it synchronous (simplest, matches every existing
   endpoint), or introduce a `202 Accepted` + poll/webhook pattern for
   this one endpoint? The latter is a materially bigger design (needs a
   store for in-flight investigations) and shouldn't be adopted just
   because the request is slow.
3. **New endpoint vs extending an existing one**: a genuinely new route
   (e.g. `POST /api/v1/incidents/investigate`), or an optional
   `auto_run: bool` flag on `POST /api/v1/planning` that, when true, keeps
   going through evidence collection and RCA? A new route keeps every
   existing endpoint's contract untouched; a flag avoids a 4th top-level
   schema but complicates `/planning`'s otherwise simple two-outcome
   contract.
4. **Partial-evidence RCA behavior**: when every evidence agent fails
   (not just one), should the orchestrator skip the RCA call entirely and
   return early (cheaper, faster, avoids an LLM call that's almost
   certainly going to be `INCONCLUSIVE` anyway), or always call RCA and
   let the model make that determination? Skipping early is an
   optimization that needs to not silently violate "let the LLM decide
   INCONCLUSIVE" as the source of truth.
5. **Where the graph lives**: a new `agent/graph/orchestration_graph.py`
   next to `planner_graph.py`, or does `planner_graph.py` itself grow the
   extra nodes? Keeping them separate preserves `planner_graph.py`'s
   current single responsibility and lets `/api/v1/planning` keep using
   the small graph on its own.
