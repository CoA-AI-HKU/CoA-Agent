from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVENTS_PATH = PROJECT_ROOT / "data" / "private" / "events.jsonl"
ALLOWED_EVENT_FIELDS = {
    "timestamp",
    "user_id",
    "sender_id",
    "channel",
    "role",
    "intent",
    "route",
    "safety_level",
    "risk_level",
    "rag_called",
    "event_type",
    "event_value",
}


def _events_path() -> Path:
    return Path(os.getenv("EVENTS_LOG_PATH") or DEFAULT_EVENTS_PATH)


def log_event(user_id: str, event: dict[str, Any]) -> None:
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_event = {
        key: value
        for key, value in dict(event).items()
        if key in ALLOWED_EVENT_FIELDS and _is_json_scalar_or_simple(value)
    }
    safe_event["timestamp"] = safe_event.get("timestamp") or datetime.now(timezone.utc).isoformat()
    safe_event["user_id"] = str(user_id or safe_event.get("user_id") or "").strip()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_event, ensure_ascii=False, sort_keys=True) + "\n")


def load_events(user_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    path = _events_path()
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines[-max(limit * 3, limit) :]:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if user_id is not None and str(event.get("user_id") or "") != str(user_id):
            continue
        events.append(event)
    return events[-limit:]


def infer_event_type(result: dict[str, Any]) -> str:
    route = str(result.get("route") or "")
    intent = str(result.get("intent") or "")
    safety_level = str(result.get("safety_level") or "")

    if safety_level == "urgent_boundary" or route == "safety":
        return "safety_alert"
    if intent == "medication_or_diagnosis" or route == "medical_boundary":
        return "medication_unsure"
    if intent == "emotional_support":
        return "emotional_support_signal"
    if intent == "cognitive_concern_screening" or route == "screening":
        return "cognitive_screening"
    if intent == "cognitive_activity" or route == "activity":
        return "activity_request"
    if intent == "knowledge_qa" or route == "rag_qa":
        return "knowledge_qa"
    return "unknown"


def _is_json_scalar_or_simple(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (str, int, float, bool)) for item in value)
    return False
