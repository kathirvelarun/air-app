---
name: air-incident-investigation
description: >
  Investigate application incidents using Logs, Code Changes,
  Distributed Traces, System Metrics, and Similar Incident evidence.
  Produce an evidence-backed RCA, recommendations, and confidence score.
---

# AIR Incident Investigation Runbook

## Objective

Determine the most likely root cause of an application incident,
explain the customer or system impact, and recommend an appropriate
remediation.

Always gather evidence before recommending a change.

Do not infer causation from correlation alone.

The final investigation must be supported by evidence returned
from the AIR Evidence Collection Agents API.


# 1. Incident Context

Start with the incident supplied by the monitoring system,
application, ServiceNow, or user.

Capture:

- investigation_id
- incident_id
- affected service
- environment
- reported symptom
- incident start time
- current status
- severity, if available
- affected dependency, if known

Example:

Affected Service:
`payment-service`

Environment:
`production`

Reported Symptom:
Intermittent payment failures.

User Question:
"What is the most likely root cause of the payment-service outage,
and what is the recommended fix?"


# 2. Investigation Rules

Use UTC timestamps throughout the investigation.

Keep evidence from different environments separate.

Do not mix:

- production
- staging
- development

Use the same:

- service
- environment
- incident window
- correlation identifiers

across all evidence agents whenever possible.

A deployment close to an incident is a lead,
not proof that the deployment caused the incident.

Likewise:

- an error log is not automatically the root cause
- high CPU is not automatically the root cause
- a similar historical incident is not proof
- a recent code change is not automatically responsible

All conclusions must be supported by correlated evidence.


# 3. Establish the Investigation Window

Confirm:

- affected service
- environment
- reported symptom
- incident start time
- latest known healthy time

For the AIR MVP, start with:

Logs / Metrics / Traces:

    incident_time - 15 minutes
    incident_time + 15 minutes

Code / Deployment Changes:

    incident_time - 2 hours
    incident_time

Expand the window only when the existing evidence
provides a reason to do so.

Do not silently broaden the investigation
to unrelated services or time periods.


# 4. Evidence Collection

Invoke independent evidence agents through the
Evidence Collection Agents API.

Evidence agents should collect facts.

They should NOT independently declare the final RCA.


## 4.1 LogAgent

Purpose:

Collect application log evidence for the affected service.

Current source:

ELF / ELK

Future sources may include:

Splunk
Datadog
CloudWatch
other enterprise logging platforms

The investigation runbook must therefore depend on
the LogAgent contract rather than a specific vendor.


### LogAgent checks

Check:

- total log events
- error count
- warning count
- error rate
- recurring error patterns
- exception types
- dependency failures
- timeout errors
- connection errors
- database errors
- memory/resource errors

Group errors by:

- error code
- exception
- dependency
- operation
- endpoint

Return representative examples instead of thousands
of raw log entries.


### Example findings

Possible scenarios:

- upstream_connect_timeout
- database connection timeout
- database deadlock
- database disk-space exhaustion
- OutOfMemoryError
- connection pool exhaustion
- configuration error
- dependency unavailable


### Large log result handling

For large log responses:

- retrieve bounded pages
- calculate aggregate counts
- identify repeating patterns
- return only representative log samples

Record:

- rows scanned
- total matching rows
- pagination limits
- sampling limits
- retention limits

Do not calculate an application failure percentage
from an arbitrary log sample.


# 4.2 CodeChangeAgent

Purpose:

Determine whether recent code, configuration,
or deployment changes could explain the incident.

Current source:

GitHub

Future implementations may use:

GitLab
Bitbucket
other source-control platforms


### CodeChangeAgent checks

Identify:

- currently deployed revision
- previous healthy revision
- deployment timestamp
- commits included in deployment
- configuration changes
- dependency changes
- timeout changes
- retry changes
- feature-flag changes
- database configuration changes

Compare:

CURRENT REVISION

against:

LAST KNOWN HEALTHY REVISION


### Look for changes involving

- timeout configuration
- retry configuration
- connection pools
- DB queries
- dependency clients
- API contracts
- thread pools
- memory settings
- feature flags
- environment configuration


### Source references

Relevant findings should include:

- repository
- commit ID
- file
- line or code section
- deployment revision
- timestamp


### Important rule

Do not conclude:

"Recent deployment = root cause"

Instead determine whether the changed behavior
can explain the evidence observed in:

- logs
- traces
- metrics


# 4.3 TracingAgent

Purpose:

Analyze distributed traces and dependency behavior.

Current source:

Dynatrace


### TracingAgent checks

Analyze:

- request traces
- failed spans
- service dependencies
- upstream latency
- downstream latency
- timeout boundaries
- retry behavior
- slow operations
- dependency errors

Capture when available:

- trace ID
- span ID
- service
- endpoint
- dependency
- status
- duration
- timestamp


### Determine whether

- an upstream service became slower
- a downstream dependency became unavailable
- requests are timing out
- retries are amplifying traffic
- DB calls became slower
- failures are concentrated in one dependency


# 4.4 MetricsAgent

Purpose:

Analyze operational and infrastructure metrics.

Current source:

Grafana


### MetricsAgent checks

Check:

- request volume
- request success rate
- error rate
- p50 latency
- p95 latency
- p99 latency
- CPU
- memory
- heap
- GC
- thread usage
- connection pool usage
- disk
- network
- container/pod health
- restart count

Compare:

BASELINE PERIOD

against:

INCIDENT PERIOD

using equivalent filters.


### Detect conditions such as

- CPU saturation
- memory exhaustion
- heap pressure
- OOM
- disk-space exhaustion
- connection pool exhaustion
- thread pool exhaustion
- increased latency
- sudden traffic spike
- pod restart
- infrastructure degradation


# 4.5 RecentIncidentAgent

Purpose:

Find historical incidents that may provide
additional investigation context.

Current source:

Vector DB


### Search using

- service
- error message
- exception
- symptom
- dependency
- incident category
- environment


### Return

- similar incident ID
- similarity score
- previous RCA
- previous resolution
- relevant runbook
- resolution outcome


### Important rule

Historical similarity is supporting evidence.

It must not override stronger evidence from
the current incident.


# 5. Independent Evidence Collection

The agents should investigate independently wherever possible.

Example:

LogAgent
       \
CodeChangeAgent
        \
TracingAgent ------> Evidence Bundle
        /
MetricsAgent
       /
RecentIncidentAgent


Independent evidence collection reduces anchoring bias.

For example:

CodeChangeAgent should not receive:

"The deployment probably caused the incident."

Instead it should receive:

"Identify recent changes that could plausibly explain
the reported symptom."


# 6. Agent Responsibilities

## LogAgent

Question:

"What errors and patterns occurred during the incident window?"


## CodeChangeAgent

Question:

"What recent code, configuration, or deployment changes
could explain the observed symptom?"


## TracingAgent

Question:

"Where in the request path is latency or failure occurring?"


## MetricsAgent

Question:

"What system or application resource behavior changed
during the incident?"


## RecentIncidentAgent

Question:

"Have we previously seen a materially similar incident,
and what evidence and resolution were associated with it?"


# 7. Evidence Contract

Each agent should return evidence using the common AIR contract.

Example:

{
  "investigation_id": "8e9c44cd-43ef-4a8e-ae4e-06b05714ca09",
  "agent_name": "LogAgent",
  "evidence_type": "LOG",
  "source_system": "ELF",
  "title": "5 log error events observed",
  "summary": "Observed repeated upstream connection timeouts.",
  "confidence": 0.90,
  "findings": {},
  "references": [],
  "limitations": []
}


# 8. Evidence Quality Rules

Every important finding should retain:

- source system
- service
- environment
- timestamp
- investigation window
- query or filter
- evidence reference
- confidence
- known limitations

If evidence cannot be retrieved:

DO NOT fabricate it.

Return:

- source unavailable
- query failed
- access denied
- data outside retention window
- insufficient evidence

The LLM Investigation must know
where evidence is missing.


# 9. Correlate Evidence

After all available evidence is collected,
send the complete evidence array to the
LLM Investigation.

The investigation should correlate evidence
across sources.


### Example correlation

LogAgent:

Payment requests began failing with:

`upstream_connect_timeout`


MetricsAgent:

p95 latency increased:

250 ms → 5200 ms


TracingAgent:

Calls from:

payment-service

to:

payment-gateway

started timing out.


CodeChangeAgent:

A deployment 8 minutes before the incident changed:

PAYMENT_TIMEOUT_MS

from:

5000

to:

1000


RecentIncidentAgent:

A previous incident showed similar timeout symptoms.


### Supported inference

The configuration change is a strong RCA candidate because:

1. it occurred before the incident
2. the configured timeout matches the observed failure behavior
3. traces show the affected dependency taking longer than the new timeout
4. logs show timeout failures
5. latency metrics confirm dependency degradation


# 10. Competing Hypotheses

Do not immediately select the first plausible explanation.

Consider alternatives such as:

- code/configuration regression
- upstream dependency degradation
- database problem
- infrastructure/resource saturation
- unexpected traffic increase
- networking problem
- unrelated deployment
- missing telemetry

Compare the hypotheses against all available evidence.


# 11. Contradiction Handling

Evidence sources may disagree.

Example:

CodeChangeAgent:

"No relevant application change found."

MetricsAgent:

"Database connection pool reached 100% utilization."

TracingAgent:

"Requests are blocked waiting for database connections."


Do not force the deployment hypothesis.

The combined evidence points instead toward
database/resource saturation.


# 12. LLM Investigation

The LLM Investigation receives the collected evidence.

Its responsibilities are to produce:

- key findings
- probable root cause
- supporting evidence
- competing hypotheses
- recommended actions
- confidence score
- missing evidence


# 13. Required Investigation Output

The final response should contain:

## Key Findings

The most important facts discovered from
logs, traces, metrics, changes, and past incidents.


## Root Cause Analysis

State the most likely root cause.

Clearly distinguish:

FACTS

from:

INFERENCES


## Recommended Actions

Provide remediation steps ordered by priority.


## Confidence

Example:

0.92


## Supporting Evidence

Reference the evidence that supports
the RCA and recommendations.


## Missing Evidence

Explicitly identify evidence that could not
be retrieved or verified.


# 14. Safety Rules

Do not automatically execute remediation based solely
on an LLM-generated RCA.

Potentially destructive actions such as:

- rollback
- restart
- configuration change
- database operation
- production deployment

must require the appropriate approval mechanism.

Investigation and recommendation should remain separate
from execution.


# 15. Core Investigation Principle

Gather evidence first.

Correlate independent evidence.

Consider competing hypotheses.

Do not confuse correlation with causation.

State uncertainty.

Recommend action only after the evidence supports it.