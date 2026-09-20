"""SQLite persistence and atomic publication of local channel notifications."""

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from air_agent_app.models.alert_input import AlertInput


def connect() -> sqlite3.Connection:
    """Open the dedicated intake database, creating its schema on first use."""
    default = Path(__file__).resolve().parents[3] / "data" / "alert-intake.sqlite3"
    path = Path(os.environ.get("AIR_INTAKE_DB", str(default)))
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS incidents (
          id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, updated_at TEXT NOT NULL,
          document TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS incident_group ON incidents(fingerprint, updated_at);
        CREATE TABLE IF NOT EXISTS alerts (
          source TEXT NOT NULL, event_id TEXT NOT NULL, incident_id TEXT NOT NULL,
          payload TEXT NOT NULL, received_at TEXT NOT NULL,
          PRIMARY KEY(source,event_id));
        CREATE TABLE IF NOT EXISTS notifications (
          incident_id TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL);
    """)
    return db


def accept_alert(alert: AlertInput) -> dict[str, Any]:
    """Atomically deduplicate, group, persist and publish an incident notification."""
    payload = alert.model_dump(mode="json", by_alias=True)
    serialized = json.dumps(payload, sort_keys=True)
    now = datetime.now(UTC)
    fingerprint = json.dumps([alert.service, alert.environment, alert.rule])
    db = connect()
    try:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute(
            "SELECT * FROM alerts WHERE source=? AND event_id=?", (alert.source, alert.event_id)
        ).fetchone()
        if previous:
            if previous["payload"] != serialized:
                raise ValueError("eventId already exists with different content for this source")
            document = json.loads(
                db.execute(
                    "SELECT document FROM incidents WHERE id=?", (previous["incident_id"],)
                ).fetchone()[0]
            )
            return {"outcome": "duplicate", "incident": document}
        row = db.execute(
            (
                "SELECT * FROM incidents WHERE fingerprint=? AND updated_at>=? "
                "ORDER BY updated_at DESC LIMIT 1"
            ),
            (fingerprint, (now - timedelta(minutes=30)).isoformat()),
        ).fetchone()
        if row:
            document = json.loads(row["document"])
            outcome = "incident_updated"
        else:
            number = db.execute("SELECT COUNT(*) FROM incidents").fetchone()[0] + 1
            document = {
                "id": f"INC-{number:04d}",
                "uuid": str(uuid4()),
                "title": alert.summary,
                "service": alert.service,
                "environment": alert.environment,
                "rule": alert.rule,
                "severity": alert.severity,
                "description": alert.description,
                "owner": alert.owner,
                "repository": alert.repository,
                "openedAt": now.isoformat(),
                "observedAt": alert.observed_at.isoformat(),
                "status": "Open",
                "alerts": [],
                "requiredMetrics": [],
            }
            outcome = "incident_created"
        ranks = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        document["severity"] = max([document["severity"], alert.severity], key=ranks.index)
        document["alerts"].append({**payload, "receivedAt": now.isoformat()})
        document["requiredMetrics"] = sorted(
            set(document["requiredMetrics"] + alert.required_metrics)
        )
        document["alertCount"] = len(document["alerts"])
        document["updatedAt"] = now.isoformat()
        document["slackChannel"] = f"air-{document['id'].lower()}"
        document["investigationUrl"] = f"/incidents/{document['id']}/investigation"
        content = json.dumps(document)
        db.execute(
            (
                "INSERT INTO incidents VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE "
                "SET updated_at=excluded.updated_at, document=excluded.document"
            ),
            (document["id"], fingerprint, now.isoformat(), content),
        )
        db.execute(
            "INSERT INTO alerts VALUES (?,?,?,?,?)",
            (alert.source, alert.event_id, document["id"], serialized, now.isoformat()),
        )
        db.execute(
            (
                "INSERT INTO notifications VALUES (?,1,?) ON CONFLICT(incident_id) "
                "DO UPDATE SET revision=revision+1, document=excluded.document"
            ),
            (document["id"], content),
        )
        db.commit()
        return {"outcome": outcome, "incident": document}
    finally:
        db.close()


def channel() -> dict[str, Any]:
    """Return committed notifications with complete incident and alert context."""
    db = connect()
    try:
        rows = db.execute(
            "SELECT n.document, n.revision FROM notifications n JOIN incidents "
            "i ON i.id=n.incident_id ORDER BY i.updated_at DESC"
        ).fetchall()
        return {
            "incidents": [
                {**json.loads(row["document"]), "notificationRevision": row["revision"]}
                for row in rows
            ]
        }
    finally:
        db.close()
