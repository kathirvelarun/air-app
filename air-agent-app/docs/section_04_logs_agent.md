# LogsAgent: Request to Response, in Detail

This walks through exactly what happens for one call to
`POST /api/v1/evidence/logs`, from the HTTP request landing to the JSON
response leaving, with file/line references into the actual implementation.
See `docs/section_03_evidence_collection_plan.md` for why this agent is
shaped this way, and `docs/requests/section_04_logs_evidence_request.json`
for a sample request body.

## 1. Request accepted (HTTP boundary)

`POST /api/v1/evidence/logs` hits `collect_log_evidence` in
`src/air_agent_app/api/evidence_routes.py`. Two things happen before your
code ever runs:

**a) FastAPI parses the JSON body against `LogEvidenceRequest`**
(`src/air_agent_app/models/log_evidence.py`). Pydantic validates every
field - `investigation_id` must be a UUID, `start_time`/`end_time` must be
timezone-aware datetimes, `max_results` must be 1-50000, and
`extra="forbid"` rejects any unknown field outright. A `model_validator`
(`validate_time_order`) then rejects `end_time <= start_time`. If any of
this fails, FastAPI raises `RequestValidationError` before the route
function body executes at all - that's caught globally by
`validation_error_handler` (`src/air_agent_app/api/error_handlers.py`),
which returns `422 {"detail": "Invalid request"}` without ever calling
`LogsAgent` or echoing what you sent.

**b) FastAPI resolves the `LogsAgent` dependency.** The route signature has
`agent: Annotated[LogsAgent, Depends(get_logs_agent)]`. `get_logs_agent()`
in `src/air_agent_app/api/dependencies.py` runs and returns
`LogsAgent(OfflineLogTool())` - a fresh agent instance per request, wired to
the only `LogTool` implementation that exists today (no real ELF adapter
yet).

Only once both succeed does `collect_log_evidence` run its one line:
`evidence = await agent.execute(request)`.

## 2. `execute()` - the fixed three-step pipeline

`BaseEvidenceAgent.execute()` (`src/air_agent_app/investigation/evidence_agent.py`)
is not overridden by `LogsAgent` - it's the shared shape every evidence
agent gets for free:

```python
async def execute(self, request):
    raw = await self.collect(request)
    normalized = self.normalize(raw)
    return self.summarize(normalized, request)
```

`LogsAgent` only implements the three pieces inside it.

## 3. `collect()` - building a query, then fetching logs

```python
async def collect(self, request):
    logger.info("LogsAgent collection started ...")
    return await self._tool.fetch_logs(_build_query(request))
```

`_build_query()` (`src/air_agent_app/investigation/logs_agent.py`) narrows
the full `LogEvidenceRequest` down to a `LogQuery` - it drops fields the log
platform has no business seeing (`hypothesis_context`, `required_evidence` -
those are planning context, not query parameters) and keeps only
`service_name`, `environment`, `start_time`/`end_time`,
`namespace`/`cluster`/`pod`, `max_results`. This is the vendor-agnostic
boundary: `LogTool` (the Protocol in `src/air_agent_app/tools/logs/log_tool.py`)
only ever sees a `LogQuery`, never the richer request.

That `LogQuery` goes to `self._tool.fetch_logs(query)`. Today `self._tool`
is always `OfflineLogTool`
(`src/air_agent_app/tools/mock/fixtures/offline_log_tool.py`), which
**ignores the filters** and calls
`generate_application_log_dump(service_name=query.service_name, environment=query.environment, start=query.start_time)`.

That generator (`src/air_agent_app/tools/mock/fixtures/log_dump.py`)
deterministically builds 1500 raw text lines anchored at `query.start_time`,
spaced 4 seconds apart. 1495 are healthy:

```text
2026-08-29T14:00:00Z INFO payment-service env=production pod=payment-service-0 req_id=1000 status=200 upstream=payment-processor connect_ms=12 latency_ms=110
```

and exactly 5 (at fixed offsets 217/486/733/1042/1311) are errors:

```text
2026-08-29T14:14:28Z ERROR payment-service env=production pod=payment-service-1 req_id=1217 status=504 error=upstream_connect_timeout upstream=payment-processor configured_connect_timeout_ms=30 connect_elapsed_ms=30
```

`collect()` returns this `list[str]` - the "raw" type in the pipeline.

## 4. `normalize()` - raw lines to typed records

```python
def normalize(self, raw):
    events = []
    for line in raw:
        event = _parse_line(line)
        if event is None:
            skipped += 1
            continue
        events.append(event)
    return events
```

`_parse_line()` (`src/air_agent_app/investigation/logs_agent.py`) splits
each line on whitespace: token 0 is the timestamp, token 1 the level, token
2 the service, everything after is `key=value` pairs turned into a dict. It
requires an `env=` field to exist and the timestamp to parse as ISO-8601 -
anything that doesn't match returns `None` and is silently skipped (counted,
logged once as a debug total) rather than crashing the whole agent over one
bad line. Matching lines become a `NormalizedLogEvent`
(`src/air_agent_app/models/log_evidence.py`) - `http_status` becomes an
`int`, `error=` becomes `exception_type`, everything else stays a typed
field. Out of 1500 raw lines, you get 1500 `NormalizedLogEvent` records here
(nothing is dropped in the normal case).

## 5. `summarize()` - deterministic counting, then one `Evidence`

```python
def summarize(self, normalized, request):
    findings = _extract_patterns(normalized)
    evidence = _build_evidence(findings, request)
    return evidence
```

`_extract_patterns()` (`src/air_agent_app/investigation/logs_agent.py`) is
pure counting - no LLM involved, by design (this is the whole point of the
exercise: a model reading 1500 lines is the context-rot failure mode from
`reference/Context_Engineering_Context_Rot.ipynb`; Python counting them is
not):

- filters events by `level == "ERROR"` / `"WARNING"`
- tallies `exception_type` occurrences into a dict (`{"upstream_connect_timeout": 5}`)
- collects the sorted, deduped set of `pod`s and `class_name`s seen on error events
- tallies `http_status` occurrences across *all* events (`{"200": 1495, "504": 5}`)
- finds the min/max timestamp among error events only

`_build_evidence()` (`src/air_agent_app/investigation/logs_agent.py`) then
picks one of three deterministic tiers based on `total_events`/`error_count`,
and constructs exactly one `Evidence` object
(`src/air_agent_app/models/evidence.py`):

| Condition | title | confidence |
| --- | --- | --- |
| `total_events == 0` | "No log data returned..." | 0.4 |
| `error_count == 0` | "No error events observed" | 0.85 |
| `error_count > 0` | "N log error event(s) observed" | 0.9 |

For the payment-service case, that's tier 3: `title="5 log error event(s) observed"`,
`findings` = the full dict from the step above, `observed_from`/`observed_to`
= the request's own window, `collected_at` = real wall-clock time of this
call.

## 6. Response sent

Back in the route, `LogEvidenceResponse(investigation_id=..., evidence=evidence)`
(`src/air_agent_app/models/evidence_response.py`) wraps the one-item list,
and FastAPI serializes it to JSON as the `200` body:

```json
{
  "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
  "evidence": [
    {
      "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
      "agent_name": "LogsAgent",
      "evidence_type": "LOG",
      "source_system": "ELF",
      "title": "5 log error event(s) observed",
      "summary": "Observed 5 error events out of 1500 log events for payment-service in production; the most common is 'upstream_connect_timeout' (5 occurrences).",
      "confidence": 0.9,
      "findings": {
        "total_events": 1500,
        "error_count": 5,
        "warning_count": 0,
        "exceptions": { "upstream_connect_timeout": 5 },
        "affected_classes": [],
        "affected_pods": ["payment-service-0", "payment-service-1"],
        "http_statuses": { "200": 1495, "504": 5 },
        "first_error_at": "2026-08-29T14:14:28+00:00",
        "last_error_at": "2026-08-29T15:27:24+00:00"
      },
      "references": [],
      "observed_from": "2026-08-29T14:00:00Z",
      "observed_to": "2026-08-29T16:00:00Z",
      "collected_at": "2026-09-13T20:38:55.936989Z"
    }
  ]
}
```

## Logging trail

One log line per phase traces the whole request by `investigation_id`:

1. `LogsAgent collection started investigation_id=... tool=OfflineLogTool`
2. *(debug, only if any line failed to parse)* `LogsAgent skipped unparsable lines count=...`
3. `LogsAgent collection completed investigation_id=... error_count=5 total_events=1500`
4. `Log evidence HTTP request completed investigation_id=... evidence_count=1`

No raw log content, incident text, or request payload appears in any of
them - only counts and IDs.
