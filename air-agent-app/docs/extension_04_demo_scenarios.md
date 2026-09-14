# Demo Scenarios: Three Root-Cause Classes, One Evidence Pipeline

Three named demo scenarios, each backed by mock data for all four evidence
agents, each a genuinely different root-cause class so the demo shows the
evidence pipeline and RCA layer distinguishing between them, not just
replaying the same failure with a different service name.

| # | Service | Root cause | Class |
| --- | --- | --- | --- |
| 1 | `payment-service` | `connection_timeout_ms` lowered 300 -> 30 | **Config change** |
| 2 | `web-ui` | UI code fails to parse a downstream response it doesn't expect | **Code/contract change** |
| 3 | `ledger-service` | Filesystem at 99.8%, writes failing (`ENOSPC`) | **Infrastructure capacity** |

Scenario 1 already existed (continuing
`reference/Context_Engineering_Context_Rot.ipynb`'s payment-service
narrative) and is documented throughout `docs/section_0{4,5,6,8,9}_*.md`.
This doc covers scenarios 2 and 3.

**No agent code changed to add these.** `LogsAgent`, `MetricsAgent`,
`TracesAgent`, and `DeploymentAgent` are all fully generic: they parse
whatever `key=value` fields and metric names appear in their mock data,
with no hardcoded reference to `payment-service` or `upstream_connect_timeout`
anywhere in agent code. Adding a scenario is purely a mock-data change --
new entries in the four `tools/mock/fixtures/*.py` generators, keyed by
service name, following the exact pattern already used for
`payment-service`/`cache-service`.

## Scenario 2: `web-ui` — a code/contract issue, not a timeout

The investigated service is the UI itself: its own response-parsing code
breaks on a downstream API response shape it doesn't expect. Deliberately
**fast**-failing (unlike scenario 1's slow timeout) and **latency stays
healthy** (unlike scenario 1, where both error rate and latency spike) --
the downstream call itself succeeds; only the parsing step after it fails.

| Agent | Evidence |
| --- | --- |
| LogsAgent | `error=response_parse_error`, `downstream=order-api`, `field=orderId`, `expected_type=string`, `actual_type=object` — 5/1500 events |
| MetricsAgent | Only `http_5xx_rate` deviates (0.010 -> 0.140); `p95_latency_ms` (150ms -> 165ms), `cpu_pct`, `memory_pct` all stay `HEALTHY` |
| TracesAgent | Outer span `render_checkout_page`: `ERROR`. Inner span `call_order_api`: **`OK`** (the downstream call succeeded). `slow_span_count = 0` |
| DeploymentAgent | `web-ui` deployed `3.2.0`, 1 hour before the window ends; `changed_files: ["src/adapters/order-api-client.ts"]` — a **code** file, not a config file, unlike scenario 1 |

Two sample requests exist for this scenario, at the two levels the demo
can run at (see "Two request levels" below):
`docs/requests/scenario_02_web_ui_contract_request.json` (Evidence
Collection only) and
`docs/requests/scenario_02_web_ui_orchestration_request.json` (the full
single-call pipeline):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigate \
  -H 'content-type: application/json' \
  -d @docs/requests/scenario_02_web_ui_contract_request.json

curl -X POST http://127.0.0.1:8000/api/v1/incidents/investigate \
  -H 'content-type: application/json' \
  -d @docs/requests/scenario_02_web_ui_orchestration_request.json
```

## Scenario 3: `ledger-service` — infrastructure capacity, no deployment involved

Deliberately **not** deployment-caused: `ledger-service` has no entry in
`deployment_dump.py`'s profile table at all, so DeploymentAgent returns
real negative evidence ("No deployment data returned", confidence `0.4`)
rather than a deployment being invented to explain the incident. This
exercises Section 10's "historical/deployment correlation is not proof"
rule from the other direction -- there's nothing here for the RCA layer
to (wrongly) blame a deploy for.

`disk_usage_pct` is a **new metric name**, requested explicitly via
`required_metrics` (it is not one of `MetricsAgent.DEFAULT_METRICS`, so a
caller must ask for it -- matching how any scenario-specific metric works).

| Agent | Evidence |
| --- | --- |
| LogsAgent | `error=disk_write_failed`, `errno=ENOSPC`, `path=/var/lib/ledger/wal.log`, `fs_usage_pct=99.8` — 5/1500 events |
| MetricsAgent | `disk_usage_pct` climbs 62% -> ~98-99% (`UNHEALTHY`, past the 90% critical threshold); `http_5xx_rate` also deviates (write failures surfacing as errors); `p95_latency_ms` stays `HEALTHY` — `ENOSPC` fails fast, not slow |
| TracesAgent | Outer span `append_ledger_entry`: `ERROR`. Inner span `fsync_wal`: **also `ERROR`** (`disk_write_failed`) — both spans fail, unlike scenario 2. `slow_span_count = 0` |
| DeploymentAgent | `deployment_detected: false`, confidence `0.4` — genuinely no deployment to implicate |

Two sample requests exist for this scenario too:
`docs/requests/scenario_03_disk_exhaustion_request.json` (Evidence
Collection only) and
`docs/requests/scenario_03_disk_exhaustion_orchestration_request.json`
(the full single-call pipeline):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigate \
  -H 'content-type: application/json' \
  -d @docs/requests/scenario_03_disk_exhaustion_request.json

curl -X POST http://127.0.0.1:8000/api/v1/incidents/investigate \
  -H 'content-type: application/json' \
  -d @docs/requests/scenario_03_disk_exhaustion_orchestration_request.json
```

## Two request levels, and a real gap the orchestration payloads surfaced

Each scenario has a sample request at two levels: directly against
`POST /api/v1/investigate` (an `InvestigateRequest`, which can name exactly
which agents run and which metrics to fetch), and against
`POST /api/v1/incidents/investigate` (an `OrchestrationRequest`, which
starts from an `IncidentInput` and lets Planning decide which agents run).

Building the orchestration payload for scenario 3 surfaced a real gap:
`OrchestrationRequest` had no way to ask for `disk_usage_pct` at all. The
Planner produces a generic `required_evidence` list, never a per-agent
metric breakdown, so there was no path for a caller who *knows* a scenario
needs a metric outside `MetricsAgent.DEFAULT_METRICS` to say so through
the single-call endpoint - `disk_usage_pct` would have silently never been
requested, and the scenario's actual smoking gun would be missing from the
demo. Fixed by adding `required_metrics`/`required_operations` directly to
`OrchestrationRequest` (`models/orchestration.py`), passed straight
through to the built `InvestigateRequest` in `collect_evidence`
(`agent/graph/orchestration_graph.py`) - this was already flagged as the
concrete next step in
`docs/extension_03_end_to_end_orchestration_agent.md` section 9. Verified
end to end: `disk_usage_pct` now appears in `MetricsAgent`'s findings and
is correctly classified `UNHEALTHY` when reached through
`/api/v1/incidents/investigate`, not just `/api/v1/investigate` directly
(`tests/test_orchestration_application.py::test_required_metrics_passthrough_reaches_the_evidence_request`).

Note: the offline demo fixture (`OfflinePlanModel`) always selects the
same fixed `parallel_agents` regardless of the incident's content - it
does not dynamically read `web-ui`/`ledger-service` from the incident text
the way a live LLM planner would. Running these orchestration payloads
offline therefore only exercises `LogsAgent`/`MetricsAgent` (whatever
`OfflinePlanModel`'s canned plan selects), not all four agents; a live
planner call, given a real `OPENAI_API_KEY`, would be expected to select
agents based on each incident's actual description.

## A mock-data bug this surfaced: percentages above 100%

`metric_series.py`'s jitter model (`target ± 5%`) was written when no
profile's incident average was ever close to `1.0` (the highest before
this was `cache-service` memory at `0.91`). `ledger-service`'s
`disk_usage_pct` target of `0.998` pushed some individual samples past
`1.0` — a physically impossible `104.8%` reading. Fixed in
`generate_metric_samples`: when both a profile's baseline and incident
averages are `<= 1.0` (the generator's way of recognizing a fraction-style
metric without metric names being threaded through), every sample is
clamped to `[0.0, 1.0]`. Latency-style metrics (values in the hundreds or
thousands) are unaffected. This did shift `disk_usage_pct`'s window
average down slightly (clamping only clips the upper tail, pulling the
mean below the unclamped `0.998` target) — `current_avg` lands around
`0.98-0.99` rather than exactly `0.998`, still clearly `UNHEALTHY` and
still faithful to "the filesystem is nearly full."

## Verified

- `tests/test_demo_scenarios.py`: both scenarios' evidence signatures
  (exception type, which metric deviates, which trace spans error, slow
  vs. fast failure, deployment presence/absence) asserted directly, plus
  confirmation that adding these two named scenarios left every other
  service's mock output unchanged.
- Full offline chain (`/api/v1/investigate` -> `RcaService`) run for both
  scenarios via a real running server: both reach
  `investigation_status: "COMPLETED"`.
- Both orchestration-level payloads (`/api/v1/incidents/investigate`) run
  end to end via `TestClient`, reaching `status: "COMPLETED"`, with
  `disk_usage_pct` confirmed present and `UNHEALTHY` in the ledger-service
  response's nested `evidence`.
- 158/158 tests pass; ruff clean.
