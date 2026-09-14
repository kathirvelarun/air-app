# DeploymentAgent: Request to Response, in Detail

Same structure as `docs/section_04_logs_agent.md` and
`docs/section_05_metrics_agent.md`, for the third guide-defined specialist:
**this one is in the guide.** Section 6 of
`reference/AIR_Agentic_SRE_Implementation_Guide.pdf` defines DeploymentAgent
exactly as implemented here. (`docs/extension_01_traces_agent.md` covers
the one agent in this repo that *isn't* guide-defined.) See
`docs/requests/section_06_deployment_evidence_request.json` for a sample
request body.

## 1. Request accepted (HTTP boundary)

`POST /api/v1/evidence/deployments` hits `collect_deployment_evidence` in
`src/air_agent_app/api/evidence_routes.py`. Same validation shape as the
other endpoints: FastAPI parses the body against `DeploymentEvidenceRequest`
(`src/air_agent_app/models/deployment_evidence.py`) - `investigation_id` a
UUID, `start_time`/`end_time` timezone-aware, `extra="forbid"`, and a
`model_validator` rejecting `end_time <= start_time`. Any failure returns
`422 {"detail": "Invalid request"}` before `DeploymentAgent` is ever
constructed. `get_deployment_agent()`
(`src/air_agent_app/api/dependencies.py`) resolves to
`DeploymentAgent(OfflineDeploymentTool())` - the only `DeploymentTool`
implementation today; no real GitHub adapter exists yet.

## 2. `execute()` - the same fixed pipeline as every evidence agent

Shared `BaseEvidenceAgent.execute()`; `DeploymentAgent` implements
`collect`/`normalize`/`summarize`.

## 3. `collect()` - building a query, then fetching events

```python
async def collect(self, request):
    return await self._tool.fetch_events(_build_query(request))
```

`_build_query()` narrows `DeploymentEvidenceRequest` to a `DeploymentQuery`
(drops `required_evidence` - planning context the tool doesn't need; folds
`deployment_environment` over `environment` when the caller distinguishes
the two) - the same vendor-agnostic query pattern as `LogQuery`,
`MetricQuery`, and `TraceQuery`. `OfflineDeploymentTool`
(`src/air_agent_app/tools/mock/fixtures/offline_deployment_tool.py`) then
calls `generate_deployment_events()`
(`src/air_agent_app/tools/mock/fixtures/deployment_dump.py`), which encodes
the notebook's own STEPS list **verbatim**:

> "payment-service deployed 2h ago (v2.4.1). cache-service deployed 6h ago
> (v1.9.0)."

This is the same deployment the notebook's `config_dump()` buries a comment
against: `connection_timeout_ms: 300 -> 30   # payment-service, v2.4.1
deploy, 2h ago`. DeploymentAgent reports that this deployment happened and
when, relative to the incident - Section 6's hard boundary is that it must
never claim the deployment *caused* anything.

The deployment lands at a fixed lead time before the query window's end
(`window_end`), with a commit five minutes earlier:

```text
2026-08-29T14:00:00Z event_type=deployment repository=org/air-services environment=production version=2.4.1 commit_sha=a1b2c3d branch=main actor=deploy-bot workflow_name=deploy workflow_run_id=98765 status=success rollback=false changed_files=config/payment-service.yaml
2026-08-29T13:55:00Z event_type=commit repository=org/air-services environment=production commit_sha=a1b2c3d branch=main actor=deploy-bot changed_files=config/payment-service.yaml
```

**Only `payment-service` and `cache-service` in `production` have a modeled
deployment**; any other (service, environment) - or a window that doesn't
actually contain the deployment's timestamp - returns an empty list, the
same as a real GitHub query scoped to that window would. This matters in
practice: querying `cache-service` with the same 2-hour window used for
`payment-service` finds **nothing**, because cache-service's deployment is 6
hours back, outside that window - not a bug, the same behavior a real
`git log --since` scoped that narrowly would have. Widen the window to see
it.

## 4. `normalize()` - raw event lines to typed records

`_parse_deployment_line()` splits each line into `key=value` pairs (same
positional-timestamp-plus-named-fields shape as `trace_dump.py`). A line
missing `event_type` or `repository`, or with an unparsable timestamp,
returns `None` and is dropped, not raised. `changed_files` is comma-split
into a list; `rollback` parses `"true"`/`"false"` into a real `bool`.

## 5. `summarize()` - deployment/commit analysis, then one `Evidence`

`_extract_findings()` (Section 6.4's exact analysis list):

- **`deployment_detected`** / **`latest_deployment`** - the most recent
  `event_type == "deployment"` event, if any.
- **`minutes_before_incident`** - `request.end_time` minus that
  deployment's timestamp. `request.end_time` is this agent's stand-in for
  "the incident", the same convention every other evidence agent uses for
  its query window.
- **`commit_count`** / **`commits`** - every `event_type == "commit"` event.
- **`rollback_detected`** - `True` if *any* event (deployment or commit)
  carries `rollback=true`.
- **`changed_files`** - the deduplicated union of changed files across all
  events, satisfying Section 6.4's "configuration file changes" requirement.

`_build_evidence()` picks one of three tiers:

| Condition | title | confidence |
| --- | --- | --- |
| `total_events == 0` | "No deployment data returned..." | 0.4 |
| events found, `deployment_detected == False` | "No deployment detected before the incident" | 0.85 |
| `deployment_detected == True` | "Deployment detected before incident" | 0.99 |

The middle tier is genuine negative evidence, not a failure: "nothing
deployed recently" rules out a deployment-caused regression as cleanly as a
positive finding rules one in. The summary text for the found case -
`"Version {version} was deployed {minutes:.0f} minutes before the
incident."` - and the 0.99 confidence match the guide's own Section 6.5
example almost verbatim.

## 6. Response sent

`EvidenceResponse` - the same shared response model all four endpoints use.
For the payment-service request:

```json
{
  "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
  "evidence": [
    {
      "agent_name": "DeploymentAgent",
      "evidence_type": "DEPLOYMENT",
      "source_system": "GitHub",
      "title": "Deployment detected before incident",
      "summary": "Version 2.4.1 was deployed 120 minutes before the incident.",
      "confidence": 0.99,
      "findings": {
        "latest_deployment": { "version": "2.4.1", "commit_sha": "a1b2c3d", "branch": "main" },
        "minutes_before_incident": 120.0,
        "commit_count": 1,
        "rollback_detected": false,
        "changed_files": ["config/payment-service.yaml"]
      }
    }
  ]
}
```

## What this adds to the Logs/Metrics/Traces picture

Four independent evidence sources now agree on the same `payment-service`
incident, each stating a different kind of fact: LogsAgent sees the error
lines, MetricsAgent sees the aggregate spike, TracesAgent sees the exact
slow span, and DeploymentAgent sees that v2.4.1 shipped 120 minutes earlier
touching `config/payment-service.yaml` - precisely the file the notebook's
buried comment says carried the timeout regression. **None of the four
agents connects these dots** - that correlation (a config change, followed
minutes later by errors in the exact service that change touched) is
squarely the Evidence Aggregator / Evidence Intelligence Engine's job
(Section 8), and it still doesn't exist. Today, a caller would have to
notice by eye that DeploymentAgent's `changed_files` overlaps with what
LogsAgent/TracesAgent are complaining about; nothing enforces or even
suggests that connection automatically.

## Known simplifications (declared, not hidden)

- **One deployment per service, hard-coded.** A real repository has an
  arbitrary deployment/commit history; the mock always produces exactly one
  deployment and one commit for two named services.
- **No release/workflow-run distinction.** `workflow_name`/`workflow_run_id`
  are populated but never varied or queried on.
- **Offline only**, like the other three agents - every request is logged
  with `tool=OfflineDeploymentTool`.
