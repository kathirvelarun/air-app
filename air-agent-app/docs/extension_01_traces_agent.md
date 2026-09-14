# TracesAgent: Request to Response, in Detail

Same structure as `docs/section_04_logs_agent.md` and
`docs/section_05_metrics_agent.md`, for a third evidence specialist.

**This one is not in the guide.** Sections 4-7 of
`reference/AIR_Agentic_SRE_Implementation_Guide.pdf` define exactly four
evidence agents: LogsAgent, MetricsAgent, DeploymentAgent, RecentIncidentAgent.
TracesAgent is a fifth specialist, designed locally to the same
`BaseEvidenceAgent` shape, for distributed-tracing platforms (Jaeger, Tempo,
OpenTelemetry) that a real SRE stack would also have. Nothing about it
should be read as a guide requirement. See
`docs/requests/extension_01_traces_evidence_request.json` for a sample request
body.

## 1. Request accepted (HTTP boundary)

`POST /api/v1/evidence/traces` hits `collect_trace_evidence` in
`src/air_agent_app/api/evidence_routes.py`. Same validation shape as the
other two endpoints: FastAPI parses the body against `TraceEvidenceRequest`
(`src/air_agent_app/models/trace_evidence.py`) - `investigation_id` a UUID,
`start_time`/`end_time` timezone-aware, `slow_span_threshold_ms` between 0
and 60,000, `extra="forbid"`, and a `model_validator` rejecting
`end_time <= start_time`. Any failure returns
`422 {"detail": "Invalid request"}` before `TracesAgent` is ever
constructed. `get_traces_agent()` (`src/air_agent_app/api/dependencies.py`)
resolves to `TracesAgent(OfflineTraceTool())` - the only `TraceTool`
implementation today.

## 2. `execute()` - the same fixed pipeline as every evidence agent

Shared `BaseEvidenceAgent.execute()`; `TracesAgent` implements
`collect`/`normalize`/`summarize`.

## 3. `collect()` - building a query, then fetching spans

```python
async def collect(self, request):
    return await self._tool.fetch_traces(_build_query(request))
```

`_build_query()` narrows `TraceEvidenceRequest` to a `TraceQuery` (drops
`required_operations` down to `operation_names`, drops nothing else the tool
doesn't need) - the same "vendor-agnostic query" pattern as `LogQuery` and
`MetricQuery`. `OfflineTraceTool`
(`src/air_agent_app/tools/mock/fixtures/offline_trace_tool.py`) then calls
`generate_trace_dump()` (`src/air_agent_app/tools/mock/fixtures/trace_dump.py`),
which continues the exact same scenario as `log_dump.py`: 1500 simulated
requests to `payment-service`, with the same 5 offsets (217/486/733/1042/1311)
failing - only now each request is a **trace** of two spans instead of one
log line:

```text
... trace_id=tr-1217 span_id=tr-1217-outer parent_span_id=- service=payment-service env=production operation=handle_payment duration_ms=30245 status=ERROR error=upstream_timeout
... trace_id=tr-1217 span_id=tr-1217-inner parent_span_id=tr-1217-outer service=payment-service env=production operation=call_payment_processor duration_ms=30012 status=ERROR error=upstream_connect_timeout
```

The outer `handle_payment` span's duration is dominated by the inner
`call_payment_processor` span - the actual outbound call that times out -
exactly like a real call chain. Healthy requests get two fast, `OK` spans
instead. `collect()` returns all `2 * 1500 = 3000` raw lines.

## 4. `normalize()` - raw span lines to typed records

`_parse_span_line()` splits each line into `key=value` pairs (no positional
fields this time, unlike `log_dump.py`'s `LEVEL`/`SERVICE` tokens - every
field here is named). A line missing any required key
(`trace_id`, `span_id`, `service`, `env`, `operation`, `duration_ms`,
`status`) or with an unparsable timestamp/duration returns `None` and is
dropped, not raised. `parent_span_id=-` (the root-span marker) becomes
`None`, not the literal string `"-"`.

## 5. `summarize()` - per-operation stats, then one `Evidence`

`_extract_patterns()` groups spans by `operation` and computes, per
operation: count, average duration, max duration, and error count - the
same kind of deterministic counting as `LogsAgent`/`MetricsAgent`, just
grouped by call-chain step instead of by exception type or metric name. Two
derived facts come out of that grouping:

- **`primary_error_operation`** - whichever operation has the most error
  spans. In the payment-service scenario this is a near-tie (5 errors each
  on `handle_payment` and `call_payment_processor`); ties break on
  insertion order, so it's consistently `handle_payment`.
- **`slowest_operation`** - whichever operation has the highest *average*
  duration. This is a genuinely different question from "which operation
  has the most errors" - a operation with only one very slow sample and no
  healthy samples to average against can out-rank a operation with more
  samples but a lower error ratio. Don't conflate the two.

`_build_evidence()` picks one of three tiers, the same shape as the other
two agents:

| Condition | title | confidence |
| --- | --- | --- |
| `total_spans == 0` | "No trace data returned..." | 0.4 |
| `error_span_count == 0 and slow_span_count == 0` | "All traces healthy" | 0.85 |
| otherwise | "N error span(s) observed" | 0.9 |

## 6. Response sent

`EvidenceResponse` - the same shared response model all three endpoints use.
For the payment-service request:

```json
{
  "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
  "evidence": [
    {
      "agent_name": "TracesAgent",
      "evidence_type": "TRACE",
      "source_system": "Jaeger",
      "title": "10 error span(s) observed",
      "summary": "Observed 10 error spans and 10 spans over 1000ms for payment-service in production; concentrated in 'handle_payment'.",
      "confidence": 0.9,
      "findings": {
        "total_spans": 3000,
        "error_span_count": 10,
        "operations": {
          "handle_payment": { "count": 1500, "avg_duration_ms": 229.5, "error_count": 5 },
          "call_payment_processor": { "count": 1500, "avg_duration_ms": 194.5, "error_count": 5 }
        },
        "primary_error_operation": "handle_payment"
      }
    }
  ]
}
```

## What this adds to the LogsAgent/MetricsAgent picture

Three independent evidence sources now agree on the *same* root cause for
`payment-service`, each from a different angle: LogsAgent sees 5
`upstream_connect_timeout` log lines, MetricsAgent sees the aggregate
HTTP 5xx/latency spike, TracesAgent sees exactly which call-chain step (span)
the time was actually spent in. None of the three infers causation or
mentions a root cause - that boundary holds across all three. Query
TracesAgent for `cache-service` and you'd get a clean "all traces healthy"
result (no trace data is modeled for that service in the mock), which is
itself an interesting asymmetry worth noticing: the notebook's decoy shows
up in metrics but not in traces, exactly as a real memory-leak-shaped
anomaly would - it doesn't run through the request path at all. Still no
Evidence Aggregator to actually correlate these three sources; see
`docs/section_03_evidence_collection_plan.md`.

## Known simplifications (declared, not hidden)

- **Two fixed operations only.** Real traces have arbitrarily deep call
  chains; the mock always produces exactly `handle_payment` ->
  `call_payment_processor`.
- **No cross-service spans.** A real trace for `payment-service` calling
  `payment-processor` would include a span *on* `payment-processor` too;
  the mock only ever returns spans labeled with the requested
  `service_name`.
- **Offline only**, like the other two agents - every request is logged
  with `tool=OfflineTraceTool`.
