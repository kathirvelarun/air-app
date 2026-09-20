# Extension 08 — Slack Integration and AIR UI Specification (Current)

Status: implemented baseline, revision 2. Supersedes Extension 06. Specification date: 2026-09-20.

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
| `src/App.tsx` | Feed polling, navigation, synchronized investigation state |
| `src/utils/investigationSync.ts` | UUID-keyed localStorage snapshots and cross-tab events |
| `src/pages/InvestigationSummary.tsx` | Evidence, findings, RCA, and remediation summaries |
| `src/pages/OperationsPage.tsx` | API-driven incident and grouped-alert tables |
| `src/pages/LiveIncidentPage.tsx` | Start investigation and display results |
| `vite.config.ts` | Strict frontend port and API proxy mapping |

Backend notification ownership is documented in
[Extension 07](extension_07_alert_api_current.md).

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
5. The engineer selects **View thread** to inspect source alerts and available synchronized results.
6. **Investigation Details** opens the corresponding AIR incident page in a new tab
   using a normal link with `target="_blank"` and `rel="noopener noreferrer"`.
7. **Start investigation** calls the existing agent API on port 8000 through the proxy.
8. The engineer reviews planning, evidence, RCA and suggestions.
9. The original channel tab receives status and result updates automatically.
   **View investigation summary & evidence** opens the expanded thread.

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
| Investigation running | Synchronized Investigating status |
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
and observed times for each alert. Available investigation data adds:

- Agent outcome, terminal reason, and planning reasoning.
- Evidence summaries with agent/source labels and unavailable agents.
- Key findings with evidence source references.
- Root-cause assessment, uncertainty, and contributing factors.
- Remediation actions, rationale, priority, risk, and approval requirements.
- Verification steps, rollback plan, follow-up actions, and missing information.

Absent data is shown explicitly rather than filled with invented conclusions.
Remediation is advisory; channel actions do not execute it. It includes the same
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
server-side `OPENAI_API_KEY` and `AIR_MODEL_NAME`. Evidence adapters remain synthetic. Postman scenarios use the production environment.

Intake records and notifications survive server/browser restarts. Investigation
snapshots use localStorage key `air.investigation.v1.<incident UUID>` and contain
`uuid`, `status`, `startedAt`, optional `finishedAt`, `result`, and `error`.

Publishing writes storage and emits `air-investigation-update` for the current
tab. Other tabs subscribe to the browser `storage` event. State is rehydrated when
the incident feed loads and remains available after reload on the same origin.
Both tabs must use the same scheme, host, and port; `localhost:5175` and
`127.0.0.1:5175` do not share storage. Use `http://127.0.0.1:5175` consistently.

| Result/state | Channel status |
| --- | --- |
| No snapshot | Open |
| Request started | Investigating |
| Agent outcome `COMPLETED` | Investigated |
| Agent outcome `INCONCLUSIVE` | Inconclusive |
| Other returned outcomes or request error | Failed |

Starting a request first publishes Investigating. If initial storage publication
fails, the request is not started and an error is shown. Failed completion storage
writes are surfaced, but synchronization cannot be guaranteed when storage is
blocked or full. Keep the investigation tab open until completion: closing it
can interrupt the request and leave a stored Investigating status. There is no
heartbeat, timeout reconciliation, or server-side job resumption.

Synchronization is confined to the same browser profile and origin. It is not
cross-device or cross-user collaboration. Clearing site storage removes results.
There is no cross-tab request lock; starting the same investigation simultaneously
can issue multiple requests and the latest stored snapshot wins.

Backend intake status remains Open. Browser status is a separate overlay; a
completed investigation does not mean remediation was executed or recovery was
verified. No backend close transition is added.

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
8. The original channel tab receives status and results from the investigation tab.
9. Refresh preserves intake records and rehydrates stored investigation results by UUID.
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

Backend tests cover intake invariants and existing agent endpoints. Frontend tests include `tests/investigation-sync.test.mjs` for storage persistence,
UUID isolation, event subscriptions, cleanup, malformed data, and blocked storage.
They do not constitute end-to-end browser coverage of channel polling or new tabs. Browser verification covers rendering and navigation separately.

## Hosting and unimplemented extensions

A deployed build needs SPA fallback and an `/api` reverse proxy. A plain static
server is insufficient for this workflow. Actual Slack posting, Slack request
signature verification, user-to-engineer mapping, acknowledgements, escalation,
email, mobile push and report/vector indexing are outside this implemented change.

## Exact channel banner

> Source System → Validated alert → Create / Update Incident → Channel notification · Investigation Details opens AIR in a new tab, where you can start the live investigation.

## New-tab acceptance walkthrough

1. Create a production-environment incident using the Postman collection.
2. Open the channel at `http://127.0.0.1:5175/slack`.
3. Click Investigation Details; verify a second tab opens and the channel remains.
4. Click Start investigation in the new tab; the original card becomes Investigating.
5. Wait for the response; verify Investigated, Inconclusive, or Failed as appropriate.
6. In the original tab click View investigation summary & evidence.
7. Check evidence, findings, RCA and remediation against the actual agent response.
8. Refresh the channel; verify stored results are restored for the same UUID.
9. After a backed-up database reset, create another incident with the reused display
   number; verify results from the old UUID are not displayed.

## Documentation scope

These specifications describe the implemented code, not a claim that services are
currently running. Real Slack API delivery, backend result persistence and
cross-device synchronization remain outside this feature.
