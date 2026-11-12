"""Safe request tracing and structured event logging for Component 3."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

TRACE_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def request_trace_id(candidate: object = None) -> str:
    """Use a safe caller trace ID or create a random one for this operation."""
    if isinstance(candidate, str):
        normalized = candidate.strip()
        if TRACE_ID_PATTERN.fullmatch(normalized):
            return normalized
    return uuid.uuid4().hex


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return str(value)


def log_component3_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one machine-readable event without serializing the request payload."""
    payload = {
        "component": "component3",
        "event": event,
        **{key: _json_value(value) for key, value in fields.items()},
    }
    logger.log(
        level,
        "component3_event %s",
        json.dumps(payload, sort_keys=True, separators=(",", ":")),
    )
