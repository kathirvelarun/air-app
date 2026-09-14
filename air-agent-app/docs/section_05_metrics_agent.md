# MetricsAgent: Request to Response, in Detail

Same structure as `docs/section_04_logs_agent.md`, for the second evidence
specialist. See `docs/section_03_evidence_collection_plan.md` for why this
agent is shaped this way, and
`docs/requests/section_05_metrics_evidence_request.json` for a sample
request body.

## 1. Request accepted (HTTP boundary)

`POST /api/v1/evidence/metrics` hits `collect_metric_evidence` in
`src/air_agent_app/api/evidence_routes.py`. As with `/logs`: FastAPI parses
the body against `MetricEvidenceRequest`
(`src/air_agent_app/models/metric_evidence.py`) - `investigation_id` a UUID,
`start_time`/`end_time` timezone-aware, `step_seconds` between 15 and 300,
`extra="forbid"` rejecting unknown fields, and a `model_validator` rejecting
`end_time <= start_time`. Any failure returns `422 {"detail": "Invalid request"}`
before `MetricsAgent` is ever constructed. `get_metrics_agent()`
(`src/air_agent_app/api/dependencies.py`) then resolves to
`MetricsAgent(OfflineMetricTool())` - the only `MetricTool` implementation
today; no real Prometheus/Datadog/Dynatrace adapter exists yet.

## 2. `execute()` - the same fixed pipeline as every evidence agent

`BaseEvidenceAgent.execute()` is shared with LogsAgent; `MetricsAgent` only
implements `collect`/`normalize`/`summarize`.

## 3. `collect()` - deriving a baseline window, then fetching both windows at once

```python
async def collect(self, request):
    query = _build_query(request)
    series = await self._tool.fetch_metrics(query)
    return query, series
```

`_build_query()` (`src/air_agent_app/investigation/metrics_agent.py`) does
something LogsAgent's query builder doesn't have to: it invents a **baseline
window**. The guide's Section 5.5 is explicit that a bare metric value is
often ambiguous ("CPU 67%" means nothing on its own) and must be compared
against a baseline. The request only carries one window
(`start_time`/`end_time` - the incident window), so the baseline window is
derived: same length, immediately before it.

```python
incident_span = request.end_time - request.start_time
window_start = request.start_time - incident_span   # baseline start
window_end = request.end_time                        # incident end
```

This is a local design choice (the guide doesn't specify how the baseline
window is chosen), documented here and in the code so it isn't mistaken for
a literal guide requirement. It also drops planning-only fields the tool
doesn't need (`required_metrics` becomes `metric_names`, defaulting to
`("cpu_pct", "memory_pct", "http_5xx_rate", "p95_latency_ms")` if the caller
didn't ask for anything specific) - the same "narrow the request down to a
vendor-agnostic query" pattern as LogsAgent's `LogQuery`.

That single `MetricQuery` - spanning *both* windows - goes to
`self._tool.fetch_metrics(query)`. `OfflineMetricTool`
(`src/air_agent_app/tools/mock/fixtures/offline_metric_tool.py`) generates
one series per requested metric via
`generate_metric_samples()` (`src/air_agent_app/tools/mock/fixtures/metric_series.py`),
which treats the window's **midpoint** as the incident boundary: samples
before it oscillate around a baseline target, samples at/after it oscillate
around an incident-window target. This lines up exactly with how
`_build_query` constructs the window (baseline span + incident span of equal
length), so the generator doesn't need the boundary passed in separately.

This generator continues the notebook's scenario for two services:

| Service | Metric | Baseline | Incident | Why |
| --- | --- | --- | --- | --- |
| `payment-service` | `cpu_pct` | 28% | 31% | healthy, matches guide 5.5 exactly |
| `payment-service` | `memory_pct` | 60% | 62% | healthy, matches guide 5.5 exactly |
| `payment-service` | `http_5xx_rate` | 1.2% | 18.6% | unhealthy, matches guide 5.6's own example |
| `payment-service` | `p95_latency_ms` | 240ms | 2800ms | unhealthy, matches guide 5.6's own example |
| `cache-service` | `memory_pct` | 62% | 91% | the notebook's decoy - real, but unrelated to payment-service |

Any other (service, metric) combination gets a flat, metric-appropriately-scaled
default (see `_DEFAULT_METRIC_PROFILES` in `metric_series.py`) so an
unrecognized request never produces a nonsensical value or fails.

## 4. `normalize()` - attaching context to raw samples

```python
def normalize(self, raw):
    query, series_by_metric = raw
    return [
        NormalizedMetricSeries(metric_name=name, service=query.service_name,
                                environment=query.environment, samples=samples)
        for name, samples in series_by_metric.items()
    ]
```

Unlike log lines, a `MetricSample` (`timestamp`, `value`) carries no
service/environment of its own - a real Prometheus range-query result
doesn't either; that context comes from the query, not the payload. So
`collect()` returns the query alongside the raw samples
(`tuple[MetricQuery, dict[str, list[MetricSample]]]`), and `normalize()`
uses it to build one `NormalizedMetricSeries` per requested metric.

## 5. `summarize()` - baseline comparison, health classification, one `Evidence`

```python
def summarize(self, normalized, request):
    findings = _extract_findings(normalized, boundary=request.start_time)
    evidence = _build_evidence(findings, request)
    return evidence
```

`_extract_findings()` splits each series' samples at `request.start_time`
(the *real* incident boundary now, not the query's derived midpoint - the
query window is twice as long as the incident window specifically so this
split lands exactly on `request.start_time`) and computes, per metric:
sample count, min, max, average, delta, and percent change - exactly
Section 5.4's list, service-level only (per-pod/instance breakdown is a
known, deferred simplification; see the caveat at the end).

`_classify_health()` is two checks, applied in this order:

1. **Absolute threshold** - is the current average past a hard limit
   (`memory_pct >= 0.85`, `http_5xx_rate >= 0.05`, `p95_latency_ms >= 1000`,
   etc.)? This exists because of the cache-service decoy: its memory was
   *already* elevated throughout the baseline window (62% -> 91% is only a
   47% relative change - under the relative threshold below), so a
   relative-only check would miss it, understating a genuinely critical
   value just because it wasn't a sharp step change.
2. **Relative threshold** - is `|percent_change| > 50%`? Not specified by
   the guide; chosen so Section 5.5's own worked example classifies
   correctly (CPU +10.7% and memory +3.3% stay `HEALTHY`; HTTP 5xx +1450%
   and P95 latency +1067% are `UNHEALTHY`).

`_build_evidence()` then picks one of three tiers - the same shape as
LogsAgent:

| Condition | title | confidence |
| --- | --- | --- |
| zero samples across all metrics | "No metric data returned..." | 0.4 |
| no metric unhealthy | "All requested metrics are healthy" | 0.85 |
| any metric unhealthy | "N metric(s) show unhealthy deviation from baseline" | 0.99 |

The 0.99 confidence for the unhealthy case matches the guide's own Section
5.6 example exactly. All metrics' findings go into **one** `Evidence`
object's `findings` dict (one entry per metric name) - not one `Evidence`
per metric - matching that same example.

## 6. Response sent

`EvidenceResponse` (`src/air_agent_app/models/evidence_response.py`) - the
same response model `/logs` uses, since both endpoints return the identical
`{investigation_id, evidence}` shape. For the payment-service request:

```json
{
  "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
  "evidence": [
    {
      "agent_name": "MetricsAgent",
      "evidence_type": "METRIC",
      "source_system": "Prometheus",
      "title": "2 metric(s) show unhealthy deviation from baseline",
      "summary": "http_5xx_rate, p95_latency_ms deviated from baseline for payment-service in production; other requested metrics stayed normal.",
      "confidence": 0.99,
      "findings": {
        "cpu_pct": { "baseline_avg": 0.28, "current_avg": 0.31, "health": "HEALTHY", "...": "..." },
        "http_5xx_rate": { "baseline_avg": 0.012, "current_avg": 0.186, "health": "UNHEALTHY", "...": "..." }
      }
    }
  ]
}
```

## What this does and doesn't prove about context engineering

Same relationship to the notebook as LogsAgent (see
`docs/section_04_logs_agent.md`'s closing note): MetricsAgent never sends a
raw time series to an LLM - `_extract_findings`/`_classify_health` are plain
arithmetic - so it can't suffer the volume-burying-signal failure mode at
all. What it newly demonstrates is the *other* half: a **second, independent
evidence source that can disagree**. Query MetricsAgent for
`cache-service` and you get a confident, genuine `UNHEALTHY` finding
(memory at 91%) that has nothing to do with the payment-service incident -
this is the notebook's decoy, now materialized as a real API response rather
than a hypothetical. Nothing in the system today stops a future consumer
from being fooled by it the same way the notebook's baseline run was; that
arbitration is explicitly the Evidence Aggregator / Evidence Intelligence
Engine's job (Section 8), still not built.

## Known simplifications (declared, not hidden)

- **Service-level only.** Section 5.4 also asks for instance/pod breakdown
  ("one hot pod is not hidden by a healthy average"). The mock tool has no
  concept of multiple pods, so this isn't implemented yet.
- **Two fixed thresholds, not per-metric-tuned.** The 50%
  relative-change and the four absolute limits are one reasonable default
  each, not a config surface. A real deployment would very likely want these
  tunable per metric.
- **Offline only.** Like LogsAgent, there is no live adapter; every request
  runs against `OfflineMetricTool`, and every log line says so
  (`tool=OfflineMetricTool`).
