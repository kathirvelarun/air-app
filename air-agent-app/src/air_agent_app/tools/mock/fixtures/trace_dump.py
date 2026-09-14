"""Simulate a large, low-signal distributed-trace dump.

Continues the same three scenarios as ``log_dump.py`` (see its module
docstring): mostly fast, healthy call chains, with a handful of traces at
the same sparse offsets showing the scenario's own failure. Each trace has
two spans -- an outer request-handling span and an inner span for the
specific operation that actually fails -- so an error shows up as ERROR
status on both, same as a real call chain. Duration is deliberately *not*
uniformly "slow": ``payment-service`` times out slowly (~30s), while
``web-ui`` and ``ledger-service`` fail fast (contract/write errors, not a
network wait) -- TracesAgent's ``slow_span_count`` should only ever flag
the timeout scenario.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

DEFAULT_FAILURE_OFFSETS = (217, 486, 733, 1042, 1311)


@dataclass(frozen=True)
class TraceScenario:
    """One service's two operation names and its failure/healthy span shape."""

    failure_offsets: tuple[int, ...]
    outer_operation: str
    inner_operation: str
    error_spans: Callable[[int], tuple[float, float]]  # (outer_ms, inner_ms)
    healthy_spans: Callable[[int], tuple[float, float]]
    outer_error_type: str
    inner_error_type: str | None = None  # None means the inner span stays OK


def _payment_error_spans(index: int) -> tuple[float, float]:
    """A ~30 second span dominated by the upstream connect timeout."""
    return 30_100 + (index % 200), 30_000 + (index % 150)


def _payment_healthy_spans(index: int) -> tuple[float, float]:
    """A normal, fast call chain."""
    return 110 + (index % 40), 80 + (index % 30)


def _web_ui_error_spans(index: int) -> tuple[float, float]:
    """The downstream call itself is fast and fine; parsing its result is what fails."""
    return 180 + (index % 60), 90 + (index % 40)


def _web_ui_healthy_spans(index: int) -> tuple[float, float]:
    """A normal, fast downstream call the UI parses without issue."""
    return 130 + (index % 40), 90 + (index % 40)


def _ledger_error_spans(index: int) -> tuple[float, float]:
    """A write-ahead-log append that fails fast (ENOSPC), not a slow write."""
    return 70 + (index % 30), 50 + (index % 25)


def _ledger_healthy_spans(index: int) -> tuple[float, float]:
    """A normal, fast local write-ahead-log append."""
    return 25 + (index % 15), 15 + (index % 10)


_SCENARIOS: dict[str, TraceScenario] = {
    "payment-service": TraceScenario(
        DEFAULT_FAILURE_OFFSETS,
        outer_operation="handle_payment",
        inner_operation="call_payment_processor",
        error_spans=_payment_error_spans,
        healthy_spans=_payment_healthy_spans,
        inner_error_type="upstream_connect_timeout",
        outer_error_type="upstream_timeout",
    ),
    "web-ui": TraceScenario(
        DEFAULT_FAILURE_OFFSETS,
        outer_operation="render_checkout_page",
        inner_operation="call_order_api",
        error_spans=_web_ui_error_spans,
        healthy_spans=_web_ui_healthy_spans,
        outer_error_type="response_parse_error",
        # inner_error_type left at its default (None): the downstream call
        # itself succeeds -- only the outer parsing step fails.
    ),
    "ledger-service": TraceScenario(
        DEFAULT_FAILURE_OFFSETS,
        outer_operation="append_ledger_entry",
        inner_operation="fsync_wal",
        error_spans=_ledger_error_spans,
        healthy_spans=_ledger_healthy_spans,
        inner_error_type="disk_write_failed",
        outer_error_type="disk_write_failed",
    ),
}


def generate_trace_dump(
    service_name: str = "payment-service",
    environment: str = "production",
    start: datetime | None = None,
    count: int = 1500,
    failure_offsets: tuple[int, ...] = DEFAULT_FAILURE_OFFSETS,
) -> list[str]:
    """Return ``2 * count`` span lines (one trace = two spans) for the window.

    Each line has the shape ``TIMESTAMP key=value ...``, deterministic for a
    given ``start``. Only services with a modeled scenario get an injected
    failure (at ``failure_offsets``); any other service is fully healthy.
    """
    anchor = start or datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)
    scenario = _SCENARIOS.get(service_name)
    effective_offsets = failure_offsets if scenario is not None else ()
    outer_op = scenario.outer_operation if scenario else "handle_request"
    inner_op = scenario.inner_operation if scenario else "call_downstream"
    lines: list[str] = []
    for index in range(count):
        timestamp = (anchor + timedelta(seconds=index * 4)).strftime("%Y-%m-%dT%H:%M:%SZ")
        trace_id = f"tr-{1000 + index}"
        outer_id = f"{trace_id}-outer"
        inner_id = f"{trace_id}-inner"
        is_failure = scenario is not None and index in effective_offsets
        if is_failure:
            outer_duration, inner_duration = scenario.error_spans(index)
            outer_status, inner_status = "ERROR", ("ERROR" if scenario.inner_error_type else "OK")
            outer_error = f" error={scenario.outer_error_type}"
            inner_error = f" error={scenario.inner_error_type}" if scenario.inner_error_type else ""
        else:
            outer_duration, inner_duration = (
                scenario.healthy_spans(index)
                if scenario
                else (110 + (index % 40), 80 + (index % 30))
            )
            outer_status = inner_status = "OK"
            outer_error = inner_error = ""
        lines.append(
            f"{timestamp} trace_id={trace_id} span_id={outer_id} parent_span_id=- "
            f"service={service_name} env={environment} operation={outer_op} "
            f"duration_ms={outer_duration} status={outer_status}{outer_error}"
        )
        lines.append(
            f"{timestamp} trace_id={trace_id} span_id={inner_id} parent_span_id={outer_id} "
            f"service={service_name} env={environment} operation={inner_op} "
            f"duration_ms={inner_duration} status={inner_status}{inner_error}"
        )
    return lines
