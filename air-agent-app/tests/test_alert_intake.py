"""Exercise intake persistence, validation and duplicate delivery invariants."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from air_agent_app.api.alert_intake import app


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Use a disposable database, never the user's demo records."""
    monkeypatch.setenv("AIR_INTAKE_DB", str(tmp_path / "test.sqlite3"))
    return TestClient(app)


def payload(event: str = "elf-1", source: str = "ELF") -> dict:
    """Build a normalized simulated alert."""
    return dict(
        eventId=event,
        source=source,
        service="payment-service",
        environment="demo",
        rule="payment-errors",
        severity="HIGH",
        summary="Payment errors",
        description="Errors exceed demo threshold",
        observedAt="2026-08-29T14:20:00Z",
    )


def test_create_duplicate_update_and_conflict(client: TestClient) -> None:
    """Exactly-once delivery and grouping update one persisted notification."""
    assert client.get("/api/v1/channel").json() == {"incidents": []}
    created = client.post("/api/v1/alerts", json=payload())
    assert created.status_code == 201
    assert client.post("/api/v1/alerts", json=payload()).json()["outcome"] == "duplicate"
    update = client.post("/api/v1/alerts", json=payload("grafana-1", "Grafana"))
    assert update.json()["outcome"] == "incident_updated"
    assert update.json()["incident"]["id"] == created.json()["incident"]["id"]
    assert (
        client.post("/api/v1/alerts", json={**payload(), "summary": "Changed"}).status_code == 409
    )
    record = TestClient(app).get("/api/v1/channel").json()["incidents"][0]
    assert record["alertCount"] == record["notificationRevision"] == 2


def test_validation_and_separate_groups(client: TestClient) -> None:
    """Bad input has no effects; service/environment/rule define grouping."""
    for changes in [
        {"source": "Unknown"},
        {"eventId": " "},
        {"observedAt": "yesterday"},
        {"severity": "URGENT"},
    ]:
        assert client.post("/api/v1/alerts", json={**payload(), **changes}).status_code == 422
    assert client.get("/api/v1/channel").json()["incidents"] == []
    for n, changes in enumerate(
        [{}, {"service": "web-ui"}, {"environment": "staging"}, {"rule": "other"}]
    ):
        assert client.post("/api/v1/alerts", json={**payload(str(n)), **changes}).status_code == 201
    assert len(client.get("/api/v1/channel").json()["incidents"]) == 4


def test_concurrent_replays(client: TestClient) -> None:
    """Concurrent delivery cannot create duplicate incidents or notifications."""
    with ThreadPoolExecutor(max_workers=5) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/v1/alerts", json=payload()), range(10))
        )
    assert sum(r.status_code == 201 for r in responses) == 1
    assert client.get("/api/v1/channel").json()["incidents"][0]["alertCount"] == 1


def test_postman_collection(client: TestClient) -> None:
    """All three delivered Postman payloads create distinct persisted incidents."""
    import json

    root = Path(__file__).resolve().parents[1]
    collection = json.loads(
        (root / "docs/postman/AIR-Alert-Intake.postman_collection.json").read_text()
    )
    for item in collection["item"]:
        body = json.loads(item["request"]["body"]["raw"])
        assert body["environment"] == "production"
        response = client.post("/api/v1/alerts", json=body)
        assert response.status_code == 201
        assert client.post("/api/v1/alerts", json=body).json()["outcome"] == "duplicate"
    records = client.get("/api/v1/channel").json()["incidents"]
    assert len(records) == 3
    assert {r["alerts"][0]["source"] for r in records} == {"ELF", "UI", "Grafana"}
