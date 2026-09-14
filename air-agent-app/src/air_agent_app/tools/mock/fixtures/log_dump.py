"""Simulate a large, low-signal application log dump.

Mirrors reference/Context_Engineering_Context_Rot.ipynb's ``log_dump()``:
mostly healthy lines with a handful of error lines sparsely buried inside,
so LogsAgent's deterministic pattern extraction -- not an LLM skimming a
huge transcript -- is what has to find them.

Three demo scenarios, one per affected service, each a genuinely different
root-cause class so LogsAgent (and the RCA layer downstream) sees three
distinct evidence signatures rather than the same failure with different
names:

- ``payment-service``: a config change (connection timeout lowered) causes
  slow upstream connects that time out -- ``upstream_connect_timeout``.
- ``web-ui``: a code/contract issue -- the UI's own parsing code breaks on
  a downstream response shape it doesn't expect -- ``response_parse_error``.
- ``ledger-service``: infrastructure capacity exhaustion, unrelated to any
  code or config change -- ``disk_write_failed`` (``ENOSPC``).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DEFAULT_FAILURE_OFFSETS = (217, 486, 733, 1042, 1311)


@dataclass(frozen=True)
class LogScenario:
    """One service's injected failure pattern: which lines fail, and how."""

    failure_offsets: tuple[int, ...]
    error_suffix: Callable[[int], str]
    healthy_suffix: Callable[[int], str]


def _payment_error_suffix(index: int) -> str:
    """A slow upstream connect that exceeds the (lowered) configured timeout."""
    return (
        "status=504 error=upstream_connect_timeout upstream=payment-processor "
        "configured_connect_timeout_ms=30 connect_elapsed_ms=30"
    )


def _payment_healthy_suffix(index: int) -> str:
    """A normal, fast upstream connect."""
    connect_ms = 12 + (index % 15)
    latency_ms = 110 + (index % 50)
    return f"status=200 upstream=payment-processor connect_ms={connect_ms} latency_ms={latency_ms}"


def _web_ui_error_suffix(index: int) -> str:
    """The downstream call succeeds, but the UI's own parsing of it fails."""
    return (
        "status=500 error=response_parse_error downstream=order-api "
        "field=orderId expected_type=string actual_type=object"
    )


def _web_ui_healthy_suffix(index: int) -> str:
    """A normal downstream call the UI parses without issue."""
    latency_ms = 90 + (index % 40)
    return f"status=200 downstream=order-api latency_ms={latency_ms}"


def _ledger_error_suffix(index: int) -> str:
    """A write-ahead-log append fails fast because the filesystem is nearly full."""
    return (
        "status=500 error=disk_write_failed errno=ENOSPC "
        "path=/var/lib/ledger/wal.log fs_usage_pct=99.8"
    )


def _ledger_healthy_suffix(index: int) -> str:
    """A normal, fast local write-ahead-log append."""
    latency_ms = 15 + (index % 10)
    return f"status=200 path=/var/lib/ledger/wal.log latency_ms={latency_ms}"


def _default_healthy_suffix(index: int) -> str:
    """A generic healthy line for any service with no modeled scenario."""
    latency_ms = 100 + (index % 40)
    return f"status=200 latency_ms={latency_ms}"


# Only these services carry an injected failure; any other service gets a
# clean, fully healthy dump -- a service uninvolved in the incident should
# not show unrelated errors just because it was queried.
_SCENARIOS: dict[str, LogScenario] = {
    "payment-service": LogScenario(
        DEFAULT_FAILURE_OFFSETS, _payment_error_suffix, _payment_healthy_suffix
    ),
    "web-ui": LogScenario(DEFAULT_FAILURE_OFFSETS, _web_ui_error_suffix, _web_ui_healthy_suffix),
    "ledger-service": LogScenario(
        DEFAULT_FAILURE_OFFSETS, _ledger_error_suffix, _ledger_healthy_suffix
    ),
}


def generate_application_log_dump(
    service_name: str = "payment-service",
    environment: str = "production",
    start: datetime | None = None,
    count: int = 1500,
    failure_offsets: tuple[int, ...] = DEFAULT_FAILURE_OFFSETS,
) -> list[str]:
    """Return ``count`` structured log lines with sparse, scenario-specific failures.

    Each line has the shape ``TIMESTAMP LEVEL SERVICE key=value ...``, and
    generation is deterministic for a given ``start`` so tests and demos are
    reproducible. Only services in ``_SCENARIOS`` get an injected failure
    (at ``failure_offsets``, or that scenario's own default); any other
    service is fully healthy throughout.
    """
    anchor = start or datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)
    scenario = _SCENARIOS.get(service_name)
    effective_offsets = failure_offsets if scenario is not None else ()
    lines: list[str] = []
    for index in range(count):
        timestamp = (anchor + timedelta(seconds=index * 4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pod = f"{service_name}-{index % 3}"
        request_id = 1000 + index
        if scenario is not None and index in effective_offsets:
            level = "ERROR"
            suffix = scenario.error_suffix(index)
        else:
            level = "INFO"
            suffix = scenario.healthy_suffix(index) if scenario else _default_healthy_suffix(index)
        lines.append(
            f"{timestamp} {level} {service_name} env={environment} pod={pod} "
            f"req_id={request_id} {suffix}"
        )
    return lines
