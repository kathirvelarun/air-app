# air-ui-app

Frontend for AIR (Agentic Incident Response), sibling to the `air-agent-app` backend. Operations overview includes Active incidents, Incidents cleared, Outstanding incidents, and Incident clearance rate. Post-mortem includes five sections and a progress timeline.

## Run from source
Use Node.js 24 or newer:

    npm ci
    npm run dev -- --host 127.0.0.1

Open the URL printed in the terminal.

## Run the built preview
With Python 3 installed:

    python3 -m http.server 8080 --directory dist

Open http://localhost:8080/ . Serve over HTTP rather than double-clicking index.html.

## Build and test

    npm run build
    node --test tests/*.test.mjs

This is a synthetic demo with in-memory state. Slack, AI investigation, approvals, and recovery are simulated. Post-mortem exports support Markdown and HTML. Internet access is needed to install dependencies and load externally hosted fonts.
