"""Simulate a small, realistic deployment history.

Continues reference/Context_Engineering_Context_Rot.ipynb's STEPS list
verbatim: "payment-service deployed 2h ago (v2.4.1). cache-service deployed
6h ago (v1.9.0)." The payment-service deployment is the same one the
notebook's ``config_dump()`` buries a comment against
("connection_timeout_ms: 300 -> 30   # payment-service, v2.4.1 deploy, 2h
ago") -- DeploymentAgent reports that the deployment happened and when,
never that it caused anything.

Two more demo scenarios: ``web-ui`` deployed a version that changed its
own downstream-parsing code (``changed_files`` points at a code file, not
a config file, unlike ``payment-service``'s config change) shortly before
its incident window -- a genuine code-change lead. ``ledger-service`` is
deliberately *not* in this profile: its incident (disk exhaustion) has no
deployment to implicate, and DeploymentAgent should say so as real
negative evidence, not have one invented for it.
"""

from datetime import datetime, timedelta

# service_name -> (version, lead time before the window end, commit sha).
_DEPLOYMENT_PROFILES: dict[str, tuple[str, timedelta, str]] = {
    "payment-service": ("2.4.1", timedelta(hours=2), "a1b2c3d"),
    "cache-service": ("1.9.0", timedelta(hours=6), "d4e5f6a"),
    "web-ui": ("3.2.0", timedelta(hours=1), "b7c8d9e"),
}

# service_name -> changed file path, for services whose changed file isn't
# the default `config/{service_name}.yaml` config-file convention.
_CHANGED_FILES: dict[str, str] = {
    "web-ui": "src/adapters/order-api-client.ts",
}


def generate_deployment_events(
    repository: str,
    service_name: str,
    environment: str,
    window_start: datetime,
    window_end: datetime,
) -> list[str]:
    """Return deployment + commit lines for the window, or an empty list.

    Only services in ``_DEPLOYMENT_PROFILES``, in ``production``, have a
    modeled deployment; any other (service, environment) -- including
    ``ledger-service``, deliberately -- returns no events, matching a real
    repository with no recent activity for that service. The deployment
    lands at a fixed lead time before ``window_end``; if that point falls
    outside ``[window_start, window_end]``, no event is returned, same as a
    real query scoped to that window would behave.
    """
    profile = _DEPLOYMENT_PROFILES.get(service_name)
    if profile is None or environment != "production":
        return []
    version, lead_time, commit_sha = profile
    deployed_at = window_end - lead_time
    if not (window_start <= deployed_at <= window_end):
        return []
    committed_at = deployed_at - timedelta(minutes=5)
    deploy_timestamp = deployed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    commit_timestamp = committed_at.strftime("%Y-%m-%dT%H:%M:%SZ")
    changed_file = _CHANGED_FILES.get(service_name, f"config/{service_name}.yaml")
    return [
        f"{deploy_timestamp} event_type=deployment repository={repository} "
        f"environment={environment} version={version} commit_sha={commit_sha} branch=main "
        f"actor=deploy-bot workflow_name=deploy workflow_run_id=98765 status=success "
        f"rollback=false changed_files={changed_file}",
        f"{commit_timestamp} event_type=commit repository={repository} "
        f"environment={environment} commit_sha={commit_sha} branch=main actor=deploy-bot "
        f"changed_files={changed_file}",
    ]
