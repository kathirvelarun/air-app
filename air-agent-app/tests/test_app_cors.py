"""CORS preflight support for air-ui-app's browser requests.

Without CORS middleware, a browser's OPTIONS preflight for a cross-origin
POST (triggered by the `content-type: application/json` header) gets a
plain 404/405 with no `access-control-*` headers, and the browser blocks
the real request before it's even sent -- a backend-side gap, not
something fixable from the UI side.
"""

from fastapi.testclient import TestClient

from air_agent_app.api.app import create_app

UI_ORIGIN = "http://localhost:5175"


def test_preflight_for_incidents_investigate_is_allowed() -> None:
    """The browser's OPTIONS preflight succeeds and names the UI origin explicitly."""
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/incidents/investigate",
            headers={
                "Origin": UI_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == UI_ORIGIN


def test_actual_response_carries_the_cors_header_too() -> None:
    """A real cross-origin request (not just its preflight) is also readable by the browser."""
    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/rca",
            json={"not": "a valid payload"},
            headers={"Origin": UI_ORIGIN},
        )
    assert response.headers["access-control-allow-origin"] == UI_ORIGIN


def test_an_unlisted_origin_is_not_granted_cors_access() -> None:
    """Only the configured UI origins get an access-control-allow-origin header back."""
    with TestClient(create_app()) as client:
        response = client.options(
            "/api/v1/incidents/investigate",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    assert "access-control-allow-origin" not in response.headers
