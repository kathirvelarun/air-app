"""Section 6: DeploymentAgent - deterministic GitHub and change evidence.

Flow: DeploymentEvidenceRequest -> DeploymentTool -> raw event lines ->
DeploymentNormalizer -> DeploymentAnalyzer -> EvidenceBuilder -> Evidence[].
Section 6's own hard boundary: this agent must not interpret application
logs or infer that a change caused the incident -- only that a change
happened, and when, relative to the incident.
"""

from datetime import UTC, datetime
from typing import Any

from air_agent_app.agent.logging_config import get_logger
from air_agent_app.investigation.evidence_agent import BaseEvidenceAgent
from air_agent_app.investigation.raw_line_parsing import parse_key_value_line
from air_agent_app.models.deployment_evidence import (
    DeploymentEvidenceRequest,
    DeploymentQuery,
    NormalizedDeploymentEvent,
)
from air_agent_app.models.evidence import Evidence
from air_agent_app.tools.deployment.deployment_tool import DeploymentTool

logger = get_logger(__name__)

_REQUIRED_FIELDS = ("event_type", "repository")


def _build_query(request: DeploymentEvidenceRequest) -> DeploymentQuery:
    """Keep only the fields a deployment-platform query needs, dropping planning context."""
    return DeploymentQuery(
        repository=request.repository,
        service_name=request.service_name,
        environment=request.deployment_environment or request.environment,
        start_time=request.start_time,
        end_time=request.end_time,
        branch=request.branch,
        deployment_environment=request.deployment_environment,
    )


def _parse_deployment_line(line: str) -> NormalizedDeploymentEvent | None:
    """Parse one ``TIMESTAMP key=value ...`` deployment or commit event line.

    Returns ``None`` for any line missing a required field or an unparsable
    timestamp, rather than raising, so a handful of unexpected lines cannot
    fail the whole agent.
    """
    parsed = parse_key_value_line(line)
    if parsed is None:
        return None
    timestamp, fields = parsed
    if any(key not in fields for key in _REQUIRED_FIELDS):
        return None
    changed_files = fields.get("changed_files", "")
    return NormalizedDeploymentEvent(
        event_type=fields["event_type"],
        timestamp=timestamp,
        repository=fields["repository"],
        environment=fields.get("environment"),
        version=fields.get("version"),
        commit_sha=fields.get("commit_sha"),
        branch=fields.get("branch"),
        actor=fields.get("actor"),
        workflow_name=fields.get("workflow_name"),
        workflow_run_id=fields.get("workflow_run_id"),
        status=fields.get("status"),
        changed_files=changed_files.split(",") if changed_files else [],
        rollback=fields.get("rollback", "false").lower() == "true",
        reference_url=fields.get("reference_url"),
    )


def _extract_findings(
    events: list[NormalizedDeploymentEvent],
    request: DeploymentEvidenceRequest,
) -> dict[str, Any]:
    """Identify the latest deployment, its lead time, commits, and rollback presence.

    "Lead time" is measured against the request's own end time, which this
    agent treats as a stand-in for "the incident" -- the same convention
    LogsAgent/MetricsAgent/TracesAgent use for their query windows.
    """
    deployments = [event for event in events if event.event_type == "deployment"]
    commits = [event for event in events if event.event_type == "commit"]
    latest = max(deployments, key=lambda event: event.timestamp) if deployments else None
    minutes_before_incident = (
        (request.end_time - latest.timestamp).total_seconds() / 60 if latest else None
    )
    changed_files = sorted({path for event in events for path in event.changed_files})
    return {
        "total_events": len(events),
        "deployment_detected": latest is not None,
        "latest_deployment": (
            {
                "version": latest.version,
                "commit_sha": latest.commit_sha,
                "branch": latest.branch,
                "timestamp": latest.timestamp.isoformat(),
            }
            if latest is not None
            else None
        ),
        "minutes_before_incident": minutes_before_incident,
        "commit_count": len(commits),
        "commits": [
            {
                "commit_sha": commit.commit_sha,
                "actor": commit.actor,
                "timestamp": commit.timestamp.isoformat(),
            }
            for commit in commits
        ],
        "rollback_detected": any(event.rollback for event in events),
        "changed_files": changed_files,
    }


def _build_evidence(findings: dict[str, Any], request: DeploymentEvidenceRequest) -> list[Evidence]:
    """Turn findings into exactly one Evidence result, matching the guide's own example.

    Three deterministic tiers: zero events and "events but no deployment"
    are both successful evidence -- the latter is genuine negative evidence
    (ruling out a recent change), never a failure.
    """
    if findings["total_events"] == 0:
        title = "No deployment data returned for the requested window"
        summary = (
            f"The deployment source returned no events for {request.repository} "
            f"in {request.environment} for the requested time window."
        )
        confidence = 0.4
    elif not findings["deployment_detected"]:
        title = "No deployment detected before the incident"
        summary = (
            f"No deployment events were found for {request.repository} in "
            f"{request.environment} in the requested window."
        )
        confidence = 0.85
    else:
        version = findings["latest_deployment"]["version"] or "an unlabeled version"
        minutes = findings["minutes_before_incident"]
        title = "Deployment detected before incident"
        summary = f"Version {version} was deployed {minutes:.0f} minutes before the incident."
        if findings["rollback_detected"]:
            summary += " A rollback was also detected in the requested window."
        confidence = 0.99
    return [
        Evidence(
            investigation_id=request.investigation_id,
            agent_name="DeploymentAgent",
            evidence_type="DEPLOYMENT",
            source_system="GitHub",
            title=title,
            summary=summary,
            confidence=confidence,
            findings=findings,
            observed_from=request.start_time,
            observed_to=request.end_time,
            collected_at=datetime.now(UTC),
        )
    ]


class DeploymentAgent(
    BaseEvidenceAgent[DeploymentEvidenceRequest, list[str], list[NormalizedDeploymentEvent]]
):
    """GitHub/change evidence specialist. States facts only, never a root cause."""

    def __init__(self, tool: DeploymentTool) -> None:
        """Inject the deployment-platform tool adapter; never construct one internally."""
        self._tool = tool

    async def collect(self, request: DeploymentEvidenceRequest) -> list[str]:
        """Build a vendor-agnostic query and fetch raw event lines through it."""
        logger.info(
            "DeploymentAgent collection started investigation_id=%s tool=%s",
            request.investigation_id,
            type(self._tool).__name__,
        )
        return await self._tool.fetch_deployments(_build_query(request))

    def normalize(self, raw: list[str]) -> list[NormalizedDeploymentEvent]:
        """Parse raw lines, silently dropping any that do not match the known shape."""
        events: list[NormalizedDeploymentEvent] = []
        skipped = 0
        for line in raw:
            event = _parse_deployment_line(line)
            if event is None:
                skipped += 1
                continue
            events.append(event)
        if skipped:
            logger.debug("DeploymentAgent skipped unparsable lines count=%s", skipped)
        return events

    def summarize(
        self,
        normalized: list[NormalizedDeploymentEvent],
        request: DeploymentEvidenceRequest,
    ) -> list[Evidence]:
        """Compute deterministic deployment/commit findings and build the Evidence result."""
        findings = _extract_findings(normalized, request)
        evidence = _build_evidence(findings, request)
        logger.info(
            "DeploymentAgent collection completed investigation_id=%s deployment_detected=%s",
            request.investigation_id,
            findings["deployment_detected"],
        )
        return evidence
