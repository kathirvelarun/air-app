# AIR alert-driven demo

Import `AIR-Alert-Intake.postman_collection.json` into Postman. It contains exactly
three POST requests: ELF/payment-service, UI/web-ui, and Grafana/ledger-service.
The collection's `baseUrl` defaults to `http://127.0.0.1:8001`.

Open http://127.0.0.1:5175/slack alongside Postman. The channel starts empty and
polls committed notifications every two seconds. Send any request to create its
incident and notification. Open **View thread** for every source alert, then
**Investigation Details** to open AIR and **Start investigation** to call the
existing investigation agent. Returning via **Slack channel** preserves results
within the current browser session. Investigation results are not persisted by
this intake feature; refreshing the browser clears those results.

## Start locally

Run the backend from `/Users/user/PycharmProjects/AIR/air-app/air-agent-app`:

```sh
.venv/bin/python -m uvicorn air_agent_app.api.alert_intake:app --app-dir src --host 127.0.0.1 --port 8001
```

Keep the existing investigation API running on port 8000. Vite forwards alert
intake and channel requests to 8001 and investigation requests to 8000. Intake
also registers on the main Python application when using its normal factory.
API documentation: http://127.0.0.1:8001/docs

## Acceptance walkthrough

1. Send ELF: HTTP 201, `outcome: incident_created`, one incident in the channel.
2. Resend ELF unchanged: HTTP 200, `outcome: duplicate`, same count and incident.
3. Change only ELF `eventId` to `elf-payment-prod-002`: HTTP 200,
   `outcome: incident_updated`, same incident, related alerts increases to two.
4. Send UI and Grafana: each creates a separate incident and notification card.
5. Reuse an existing source/eventId with changed content: HTTP 409, no changes.
6. Omit service or use an invalid severity: HTTP 422, no changes.

The exact identity is `(source, eventId)`. Grouping is exact
`(service, environment, rule)`, across sources, within 30 minutes of last receipt.
After 30 minutes without an event, a new event creates a new incident. Replays
remain duplicates even after the grouping window. Severity only increases.
No lifecycle/close endpoint is part of this change; grouping is receipt-window
based, not inferred from the in-browser investigation state.

## Data and notifications

SQLite file: `air-agent-app/data/alert-intake.sqlite3` (git-ignored).
Override the path with `AIR_INTAKE_DB`. Alerts, incident updates and one versioned
notification per incident are committed atomically. Restarting intake preserves
records. A new unique event updates the existing notification rather than posting
a duplicate card. The initial database is empty; no previous application database
is erased. Seeded records are removed from the active portal/channel views.

This is a local hackathon endpoint, bound to loopback, without production auth.
It accepts a normalized alert envelope, not raw vendor webhooks. Postman simulates
ELF/UI/Grafana events; it does not connect to those products or measure thresholds.
The fixed observed date aligns with existing synthetic evidence fixtures. The
receipt time on each card reflects the actual request time.

The destination is the existing AIR-hosted Slack-style channel. No external Slack
messages are sent. The existing investigation agent uses demo evidence adapters;
these alert payloads provide context, not a live telemetry integration.

The API routes are also registered in `air_agent_app.api.app:create_app`, alongside the investigation routes on port 8000 after restart. The standalone port 8001 serves the same intake code while the existing investigation process continues running.

UI source remains `/Users/user/Documents/Project/air-ai-sre/air-ui-app`.

All three requests use `environment: production` and `simulated: true`. Re-import
the collection to pick up the production event IDs. Existing demo records remain
historical; run investigations from the newly created production incidents.
