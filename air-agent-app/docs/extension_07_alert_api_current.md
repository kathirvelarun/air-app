# Extension 07 — Agent Alert API Specification (Current)

Status: implemented baseline, revision 2. Supersedes Extension 05. Specification date: 2026-09-20.

## Purpose and ownership

Accept normalized monitoring alerts from Postman, validate and deduplicate them,
persist them, create or update a correlated incident, and publish a committed
notification for the AIR-hosted Slack-style channel. Alert intake is deterministic
and does not invoke an LLM. The engineer starts investigation separately in AIR.

Backend repository: `/Users/user/PycharmProjects/AIR/air-app/air-agent-app`.

| Responsibility | Source |
| --- | --- |
| Input contract | `src/air_agent_app/models/alert_input.py` |
| HTTP routes and standalone app | `src/air_agent_app/api/alert_intake.py` |
| SQLite transactions and notification storage | `src/air_agent_app/tools/alert_store.py` |
| Main application registration | `src/air_agent_app/api/app.py` |
| Acceptance tests | `tests/test_alert_intake.py` |
| Three Postman requests | `docs/postman/AIR-Alert-Intake.postman_collection.json` |

## Deployment contract

| Component | Address |
| --- | --- |
| UI and channel | `http://127.0.0.1:5175` |
| Standalone intake API | `http://127.0.0.1:8001` |
| Existing investigation agent | `http://127.0.0.1:8000` |

Both API routes are also registered in the main application factory. The current
frontend proxy specifically sends alert/channel traffic to 8001 and other API
traffic to 8000. Running only the main application does not satisfy that proxy
configuration. The standalone intake app relies on the same-origin frontend proxy;
it does not install CORS middleware. Main-app default CORS origins are
`http://localhost:5175` and `http://127.0.0.1:5175`, overridable by `AIR_UI_ORIGINS`.

## POST /api/v1/alerts

Request content type: `application/json`. Public field names use camelCase.
Unknown fields are rejected. Strings are trimmed before validation. Enum values
are case-sensitive. Timestamps must include timezone information.

| Field | Required/default | Validation |
| --- | --- | --- |
| `eventId` | Required | String, 1–160 characters |
| `source` | Required | `ELF`, `UI`, or `Grafana` |
| `service` | Required | String, 1–120 characters |
| `environment` | Required | `demo`, `development`, `staging`, or `production` |
| `rule` | Required | String, 1–160 characters |
| `severity` | Required | `LOW`, `MEDIUM`, `HIGH`, or `CRITICAL` |
| `summary` | Required | String, 1–500 characters |
| `description` | Required | String, 1–4000 characters |
| `observedAt` | Required | Timezone-aware datetime |
| `owner` | `SRE on-call` | String, 1–120 characters |
| `repository` | `org/air-services` | String, 1–200 characters |
| `requiredMetrics` | Empty list | At most 30 string entries |
| `simulated` | `true` | Literal true; this is the simulated-event contract |

Example:

```json
{
  "eventId": "elf-payment-prod-001",
  "source": "ELF",
  "service": "payment-service",
  "environment": "production",
  "rule": "payment-error-rate",
  "severity": "HIGH",
  "summary": "Payment errors spiking",
  "description": "ELF detected repeated payment request errors above the demo threshold.",
  "observedAt": "2026-08-29T14:20:00Z",
  "simulated": true
}
```

The fixed observation date in delivered Postman examples aligns with existing
synthetic evidence fixtures. `receivedAt`, `openedAt`, and `updatedAt` use actual
server receipt times. There is no freshness check on `observedAt`.

### Responses

| HTTP | `outcome` | Effect |
| --- | --- | --- |
| 201 | `incident_created` | New incident, alert, and notification |
| 200 | `incident_updated` | New related alert attached; incident/card updated |
| 200 | `duplicate` | Existing current incident returned; no writes |
| 409 | Not present | Same source/event ID reused with different normalized content |
| 422 | Not present | Request validation failed; no intake transaction |

Successful response envelope:

```json
{
  "outcome": "incident_created",
  "incident": {
    "id": "INC-0001",
    "uuid": "<generated UUID>",
    "title": "Payment errors spiking",
    "service": "payment-service",
    "environment": "production",
    "rule": "payment-error-rate",
    "severity": "HIGH",
    "description": "ELF detected repeated payment request errors above the demo threshold.",
    "owner": "SRE on-call",
    "repository": "org/air-services",
    "openedAt": "<server receipt timestamp>",
    "observedAt": "2026-08-29T14:20:00+00:00",
    "status": "Open",
    "alerts": ["<full normalized alert object plus receivedAt>"],
    "requiredMetrics": [],
    "alertCount": 1,
    "updatedAt": "<server receipt timestamp>",
    "slackChannel": "air-inc-0001",
    "investigationUrl": "/incidents/INC-0001/investigation"
  }
}
```

Angle-bracket values above describe generated values, not literal API data. Each
`alerts` entry is an object containing the complete normalized request plus
`receivedAt`; the string above abbreviates that object.

Conflict detail: `eventId already exists with different content for this source`.
The standalone app uses FastAPI's default validation error envelope; the main
application uses its registered validation handler. Clients should branch on
HTTP status rather than assume identical validation envelopes in both modes.

## Processing rules

1. Validate the request before database writes.
2. Start `BEGIN IMMEDIATE` to serialize writers.
3. Look up delivery identity `(source, eventId)`.
4. Compare canonical JSON of the validated payload, including expanded defaults.
   Equal content is a duplicate. Different content is a conflict. JSON key order
   is irrelevant; array order is not normalized for this comparison.
5. For a new delivery, group by the exact tuple `(service, environment, rule)`.
   Source is excluded, permitting cross-source correlation with matching keys.
6. Select the most recently updated matching incident whose last receipt is within
   30 minutes. Browser investigation state is not part of this decision.
7. Otherwise allocate `INC-` plus a minimum four-digit sequence and a UUID.
8. Append the alert; increase severity only; union and sort required metrics;
   update alert count and receipt time.
9. Upsert one notification per incident and increment its revision for a new alert.
10. Commit alert, incident, and notification together, then return the result.

Title, description, owner, repository, and first observation remain those of the
first alert. Later details are preserved in the `alerts` array. A duplicate does
not extend the grouping window or increment the notification revision. After the
window expires, a new event can create another incident; an old replay is still
a duplicate. No explicit close/reopen lifecycle is implemented by intake.

## Persistence model

Default database: `<backend-repository>/data/alert-intake.sqlite3`.
`AIR_INTAKE_DB` overrides the path. Database files are git-ignored.

| Table | Identity | Stored data |
| --- | --- | --- |
| `alerts` | Primary key `(source, event_id)` | Incident ID, normalized payload JSON, receipt time |
| `incidents` | Primary key `id` | Group fingerprint, update time, complete incident JSON |
| `notifications` | Primary key `incident_id` | Revision and complete incident snapshot JSON |

Schema is created on first connection. SQLite lock timeout is 15 seconds.
Connections close after each operation; uncommitted writes roll back on failure.
There is no reset/delete endpoint, retention policy, migration framework, or
foreign-key enforcement. Incident numbering uses row count plus one and assumes
records are not manually deleted. This is a local-demo store, not a production
multi-node database design.

## GET /api/v1/channel

Returns `200` with `{ "incidents": [] }` when empty. Otherwise each item is the
committed notification's complete incident document with an added
`notificationRevision` integer. Items are ordered by latest receipt descending.
The feed returns all records; pagination and cursor-based incremental delivery
are not implemented. This persisted snapshot is the notification mechanism;
there is no external message broker, WebSocket, or Slack delivery receipt.

## Test coverage and acceptance

`tests/test_alert_intake.py` verifies empty state, create/update/duplicate/conflict,
invalid inputs, separate service/environment/rule groups, concurrent replays,
persistence across client instances, and all three delivered Postman requests.
Tests use a disposable database and do not populate the user's demo store.

Manual acceptance: send ELF → observe one incident; replay unchanged → unchanged
count; change only event ID → same incident with two alerts; send UI and Grafana
→ separate incidents. See [integration specification](extension_08_slack_integration_ui.md)
and [Postman instructions](postman/README.md).

## Current boundaries

No production authentication, vendor webhook parsing, monitoring-system connection,
threshold evaluation, actual Slack delivery, or automatic investigation is added.
OpenAI is required only when the existing investigation workflow is explicitly
started. Intake does not generate reports or write to a vector database. These
are boundaries of this implemented feature, not claims about future work.

### Deployment evidence compatibility

Postman scenarios use `production` with `simulated: true`. The offline deployment
fixture models production only. Ledger and unknown services retain no-deployment
evidence. Updated event IDs contain `-prod-` to avoid conflicting with earlier
persisted demo-environment deliveries; historical records are not rewritten.

## Production scenario contract

All three delivered Postman scenarios use `environment: production` and
`simulated: true`. The environment selects the existing production evidence
fixtures; it does not connect this demonstration to production telemetry.

| Source | Event ID | Service | Evidence scenario |
| --- | --- | --- | --- |
| ELF | `elf-payment-prod-001` | `payment-service` | Payment errors and deployment/configuration evidence |
| UI | `ui-checkout-prod-001` | `web-ui` | Front-end response parsing issue |
| Grafana | `grafana-disk-prod-001` | `ledger-service` | Disk-capacity issue; includes `disk_usage_pct` |

Deployment fixtures remain production-only. The payment profile returns v2.4.1
and a configuration-file change when selected and queried with the supported
window. Ledger and unknown services must not gain fabricated deployment evidence.
The planner still chooses which evidence agents to invoke; intake does not force
DeploymentAgent selection.

## Fresh-test reset procedure

The fresh-test operation backs up the dedicated SQLite database, then deletes
`notifications`, `alerts`, and `incidents` in one transaction. It is an explicit
maintenance operation, not a public reset endpoint or an automatic startup action.
Verify all three counts are zero before starting the next demonstration. With the
current numbering implementation, the next incident is `INC-0001` with a new UUID.
Never reset unrelated application databases.

Previously stored browser investigation snapshots are not deleted by this database
operation. The frontend keys them by UUID, so reusing a display ID does not attach
old results to a newly created incident. API deduplication identities are cleared
with the alert table, allowing the delivered requests to be sent again.

## Relationship to investigation updates

This API persists intake records and notification snapshots. It does not persist
agent results or synchronize investigation lifecycle back into SQLite. Current
cross-tab status/result updates use browser localStorage; see Extension 08.
