from __future__ import annotations

from typing import Any

from src.metrics import log_event


class EventLogger:
    """Small boundary for service-level events (the orchestrator logs turn events)."""

    def log(self, user_id: str, event_type: str, **fields: Any) -> None:
        log_event(user_id, {"event_type": event_type, **fields})
