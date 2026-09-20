# AIR UI

Frontend source: `/Users/user/Documents/Project/air-ai-sre/air-ui-app`.
Backend source: `/Users/user/PycharmProjects/AIR/air-app/air-agent-app`.

## Start locally

From this frontend directory, using Node.js 24 or newer:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5175/slack for the Slack-style channel or `/` for the AIR portal.
Both `npm run dev` and `npm run preview` use port 5175 and fail if it is occupied, rather than silently switching ports. Port 5175 is not started automatically by build or tests.

The Vite development proxy forwards:

| Route | Backend |
| --- | --- |
| `/api/v1/alerts` | `http://127.0.0.1:8001` |
| `/api/v1/channel` | `http://127.0.0.1:8001` |
| Other `/api` routes, including investigation | `http://127.0.0.1:8000` |

Start alert intake from the backend directory:

```sh
.venv/bin/python -m uvicorn air_agent_app.api.alert_intake:app --app-dir src --host 127.0.0.1 --port 8001
```

Keep the existing investigation API running on port 8000. The alert endpoints are
also registered in its main app factory; the dedicated 8001 process lets intake
run without restarting the existing investigation process.

## Postman to channel to investigation

Import the backend's `docs/postman/AIR-Alert-Intake.postman_collection.json`.
Send an ELF, UI, or Grafana request to `POST http://127.0.0.1:8001/api/v1/alerts`.

- The portal and channel load persisted records from `/api/v1/channel` every two seconds.
- No incident or alert scenarios are preloaded into these views.
- Repeated event IDs are deduplicated; related new events update the existing incident card.
- **View thread** displays source alerts and any investigation results from this session.
- **Investigation Details** opens `/incidents/INC-xxxx/investigation` in a new browser tab.
- **Start investigation** calls the existing agent API.
- Return through **Slack channel** to view results in the thread.

Alert and incident persistence lives in the backend. Investigation status and results are synchronized through localStorage across tabs
on the same origin and survive reloads. Records are keyed by the incident UUID.
This does not synchronize across browsers or devices or update backend incident
status. Keep the investigation tab open until its request completes; closing it
early can leave a stored Investigating status. Clearing site storage removes results. Evidence adapters
are synthetic demo adapters. This is an AIR-hosted Slack-style interface; no real
Slack workspace is connected and no external Slack messages are sent.

## Implementation files

- `src/pages/SlackChannelPage.tsx` and `.css`: channel, cards, and thread panel.
- `src/api/alertIntake.ts`: notification feed and incident-to-investigation mapping.
- `src/api/investigationApi.ts`: agent request.
- `src/App.tsx`: polling, state, and navigation.
- `vite.config.ts`: local backend routing.

## Verify

```sh
npm run build
npm run lint
node --test tests/*.test.mjs
```

For deployment, serve the built `dist` directory with SPA fallback and an `/api`
reverse proxy. A plain static Python server does not provide the API proxy or
investigation deep-link fallback required for this workflow.

The channel thread includes evidence, key findings, root-cause assessment, uncertainty,
and remediation recommendations with verification, rollback and follow-up steps.
Completed, inconclusive and failed investigations are distinguished.
