"""HTTP endpoints for alert intake and the Slack-style notification feed."""

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException, Response

from air_agent_app.models.alert_input import AlertInput
from air_agent_app.tools import alert_store

router = APIRouter(prefix="/api/v1")


@router.post("/alerts")
def accept_alert(alert: AlertInput, response: Response) -> dict[str, Any]:
    """Validate delivery identity and return the committed incident."""
    try:
        result = alert_store.accept_alert(alert)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    response.status_code = 201 if result["outcome"] == "incident_created" else 200
    return result


@router.get("/channel")
def channel() -> dict[str, Any]:
    """Read committed incident notifications for the local Slack-style channel."""
    return alert_store.channel()


app = FastAPI(title="AIR Demo Alert Intake", version="1.0.0")
app.include_router(router)
