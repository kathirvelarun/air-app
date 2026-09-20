# Extension 06 — Slack-Style Channel and AIR UI Integration

> Historical baseline. See the [current specification](extension_08_slack_integration_ui.md) for the latest implementation.
Status: implemented hackathon baseline. Specification date: 2026-09-20.

## Objective and scope

Demonstrate an engineer receiving an API-driven incident notification, reviewing
alert context in a messaging-style channel, and opening AIR to start an agent
investigation. The channel is hosted by AIR. It is not an installed Slack app.
No real Slack workspace, webhook, mobile push, email, or external message delivery
is configured. Labels such as `air-inc-0001` identify local channel filters.

Frontend: `/Users/user/Documents/Project/air-ai-sre/air-ui-app`.
Backend: `/Users/user/PycharmProjects/AIR/air-app/air-agent-app`.

## Component ownership

| File in frontend | Responsibility |
| --- | --- |
| `src/pages/SlackChannelPage.tsx` | Channel navigation, search, incident cards, thread panel |
| `src/pages/SlackChannelPage.css` | Messaging layout and responsive presentation |
| `src/api/alertIntake.ts` | Read notification feed; map incident to investigation request |
| `src/api/investigationApi.ts` | POST investigation request |
| `src/App.tsx` | Feed polling, navigation, browser-session investigation state |
| `src/pages/OperationsPage.tsx` | API-driven incident and grouped-alert tables |
| `src/pages/LiveIncidentPage.tsx` | Start investigation and display results |
| `vite.config.ts` | Strict frontend port and API proxy mapping |

Backend notification ownership is documented in
[Extension 05](extension_05_alert_intake_api.md).

## Port and route contract

| Browser route | Purpose |
| --- | --- |
| `http://127.0.0.1:5175/` | AIR operations portal |
| `http://127.0.0.1:5175/slack` | Messaging-style channel |
| `/incidents/INC-xxxx/investigation` | Selected incident investigation page |

Both Vite development and preview use `127.0.0.1:5175` with `strictPort: true`.
An occupied port causes startup to fail instead of selecting another port.

| Browser API request | Proxy destination |
| --- | --- |
| `/api/v1/alerts` | `http://127.0.0.1:8001` |
| `/api/v1/channel` | `http://127.0.0.1:8001` |
| Other `/api` requests | `http://127.0.0.1:8000` |

Investigation defaults to `/api/v1/incidents/investigate`.
`VITE_INVESTIGATE_URL` can override this URL. Direct cross-origin overrides require
matching backend CORS configuration. Browser-side code never contains OpenAI keys.

## End-to-end sequence

1. Postman sends a normalized ELF, UI, or Grafana event to port 8001.
2. Backend validation, deduplication, grouping and persistence complete atomically.
3. Frontend reads the committed notification feed on its next poll.
4. A new incident appears as a new card and local channel entry. A related new alert
   updates the existing card and alert count. A replay makes no change.
5. The engineer selects **View thread** to inspect source alerts and available results.
6. **Investigation Details** routes to the corresponding AIR incident page.
7. **Start investigation** calls the existing agent API on port 8000 through the proxy.
8. The engineer reviews planning, evidence, RCA and suggestions.
9. Selecting **Slack channel** returns to the channel, where results from this browser
   session are available in the thread.

Opening a channel, viewing a thread, or following Investigation Details does not
itself start an LLM call. No acknowledgement mutation is implemented.

## Feed state and notification behavior

The app starts with an empty incident array and polls immediately. Subsequent polls
are scheduled two seconds after the previous request finishes, avoiding overlapping
requests. Unmount aborts the request and clears the timer. Failed requests display
an error and retry on the next cycle; previously loaded data can remain visible.
Two seconds is a polling target, not a guaranteed delivery SLA.

No seeded incidents are injected into active channel or operations views. Existing
persisted records are loaded on restart, so an empty state requires an empty store.

| State | Presentation |
| --- | --- |
| No records | “Waiting for your first alert” and Postman instructions |
| Search has no match | “No matching incidents” |
| Intake unavailable | Error message; retries continue |
| New incident | New card, source context and complete alert context in thread |
| Grouped new event | Existing card updated; related count increases |
| No investigation | Invitation to open AIR and start investigation |
| Investigation running | Browser-session progress state |
| Investigation failed | Error surfaced by AIR; retry action in investigation page |
| Investigation returned | Available planning/evidence/RCA shown in AIR and thread |

No operating-system notification, sound, unread count, or phone push is implemented.

## Channel and thread design

The main channel is `#air-incidents`. Each incident also has a sidebar filter named
from its persisted `slackChannel`. Search matches incident title, service and ID.

Incident card fields:

- AIR sender identity and monitoring source(s).
- Owner rendered as an `@` label; this is not a Slack user mention.
- First observation timestamp, severity, incident ID and status.
- Title, initial description, service and environment.
- Related alert count, grouping rule and last receipt/update timestamp.
- **Investigation Details** link and **View thread** action.

The thread lists source/event IDs, summaries, descriptions, severity, environment
and observed times for each alert. Available investigation data adds planning
reasoning, evidence summaries and root-cause assessment. It includes the same
investigation deep link and a close button.

Styles adapt to smaller screens: the sidebar hides below 540px and the thread
becomes an overlay below 800px. This is browser responsiveness, not a native app.

## Investigation mapping and state lifetime

`toScenario` maps persisted `uuid` to `incident.incident_id`. The display identifier
remains `INC-xxxx`. Service, environment, severity, title, description, repository,
owner and required metrics originate from intake. Source names are deduplicated
for display. The demo evidence window is fixed relative to first observation:
20 minutes before through 100 minutes after. This is demo mapping, not an inferred
incident duration or live query-window policy.

The existing agent performs planning → evidence → RCA. Planning and RCA need
server-side `OPENAI_API_KEY` and `AIR_MODEL_NAME`. Evidence adapters remain synthetic.

Intake records and notifications survive server/browser restarts. Investigation
results, errors, duration and progress currently live in React memory. Reloading
clears them. Investigation does not update the persisted intake lifecycle status,
which remains `Open`; browser status is an overlay. The UI's returned-result label
must not be interpreted as proof of system recovery. No recovery verification or
backend incident-close transition is introduced by this feature.

Browser navigation uses history updates and popstate handling. Investigation URLs
resolve against the polled incident feed. There is currently no dedicated incident
lookup endpoint or explicit unknown-ID screen; absent IDs can fall back to the
operations view.

## Startup and demo procedure

From the backend directory, in one terminal:

```sh
.venv/bin/python -m uvicorn air_agent_app.api.alert_intake:app --app-dir src --host 127.0.0.1 --port 8001
```

In another terminal, with OpenAI settings already configured:

```sh
.venv/bin/python -m uvicorn air_agent_app.api.app:create_app --factory --app-dir src --host 127.0.0.1 --port 8000
```

From the frontend directory:

```sh
npm run dev
```

Open `/slack` on port 5175. Import
`docs/postman/AIR-Alert-Intake.postman_collection.json` from the backend repository.
Keep collection `baseUrl=http://127.0.0.1:8001`.

| Request | Service | Expected first-send behavior |
| --- | --- | --- |
| ELF | `payment-service` | New payment incident/card |
| UI | `web-ui` | New front-end incident/card |
| Grafana | `ledger-service` | New disk-capacity incident/card; disk metric requested |

Replay an unchanged request to show deduplication. Change only its event ID to
show correlation within the 30-minute window. Open thread → Investigation Details
→ Start investigation → return to channel. Do not claim a real threshold breach
or real vendor integration: these are simulated monitoring events.

## Verification and acceptance criteria

1. Empty database yields no preloaded incidents or alerts in active views.
2. Each of the three Postman requests appears in both portal and channel.
3. A duplicate does not add a card, alert, or notification revision.
4. A related new event increments the same incident's count and thread details.
5. Invalid and conflicting payloads do not change visible records.
6. Investigation Details opens the matching incident, not a hardcoded scenario.
7. Starting investigation surfaces API progress, results or a visible error.
8. Returning to the channel retains investigation results within the same session.
9. Refresh preserves intake records but clears session-only investigation results.
10. Frontend dev/preview bind to 5175; backend origins and proxy contracts match.

Commands:

```sh
# Backend repository
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
.venv/bin/python -m air_agent_app.commands.planner --scenario ready

# Frontend repository
npm run build
npm run lint
node --test tests/*.test.mjs
```

Backend tests cover intake invariants and existing agent endpoints. Existing frontend
unit tests cover supporting utilities; they are not end-to-end coverage of channel
polling. Browser verification covers rendering and navigation separately.

## Hosting and unimplemented extensions

A deployed build needs SPA fallback and an `/api` reverse proxy. A plain static
server is insufficient for this workflow. Actual Slack posting, Slack request
signature verification, user-to-engineer mapping, acknowledgements, escalation,
email, mobile push and report/vector indexing are outside this implemented change.
