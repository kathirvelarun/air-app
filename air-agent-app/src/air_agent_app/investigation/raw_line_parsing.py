"""Shared parsing for the ``TIMESTAMP key=value key=value ...`` mock line format.

Used by TracesAgent and DeploymentAgent, whose raw tool output happens to
share this shape. LogsAgent's format additionally has positional LEVEL and
SERVICE tokens before the key=value pairs, so it parses lines itself.
"""

from datetime import datetime


def parse_key_value_line(line: str) -> tuple[datetime, dict[str, str]] | None:
    """Split one line into (timestamp, fields), or None if malformed.

    Returns None rather than raising for an empty line, a line with no
    parseable fields, or an unparsable timestamp, so a handful of unexpected
    lines cannot fail a caller's whole normalization pass.
    """
    tokens = line.split()
    if len(tokens) < 2:
        return None
    raw_timestamp, *pairs = tokens
    fields = dict(pair.split("=", 1) for pair in pairs if "=" in pair)
    try:
        timestamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp, fields
