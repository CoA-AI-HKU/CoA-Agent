from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


DEFAULT_EVENTS_PATH = Path.home() / ".nanobot" / "data" / "private" / "events.jsonl"
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
    "score",
    "exercise_type",
    "medication_status",
}


class MetricsCollector:
    def get_all_users(self) -> list[str]:
        users = {
            str(event.get("user_id") or "").strip()
            for event in load_events(user_id=None, days=None)
            if str(event.get("user_id") or "").strip()
        }
        return sorted(users)

    def get_user_metrics(self, user_id: str, days: int = 7) -> dict[str, Any]:
        events = load_events(user_id=user_id, days=days)
        interaction_events = [event for event in events if event.get("event_type") == "interaction"]
        count_base = interaction_events if interaction_events else events
        mood_history = [
            {"timestamp": event.get("timestamp"), "score": _to_float(event.get("score"))}
            for event in events
            if event.get("event_type") == "mood_check" and _to_float(event.get("score")) is not None
        ]
        cognitive_history = [
            {
                "timestamp": event.get("timestamp"),
                "score": _to_float(event.get("score")),
                "exercise_type": str(event.get("exercise_type") or "activity"),
            }
            for event in events
            if event.get("event_type") == "activity_score" and _to_float(event.get("score")) is not None
        ]
        intent_counts: dict[str, int] = {}
        for event in events:
            intent = str(event.get("intent") or "unknown").strip() or "unknown"
            intent_counts[intent] = intent_counts.get(intent, 0) + 1

        medication_responses = [
            event
            for event in events
            if event.get("event_type") == "medication_response"
            and str(event.get("medication_status") or "").strip().lower() in {"taken", "missed", "unsure"}
        ]
        taken_count = sum(
            1
            for event in medication_responses
            if str(event.get("medication_status") or "").strip().lower() == "taken"
        )

        return {
            "avg_mood": _average(item["score"] for item in mood_history),
            "avg_cognitive": _average(item["score"] for item in cognitive_history),
            "total_interactions": len(count_base),
            "medication_adherence": (
                taken_count / len(medication_responses) if medication_responses else None
            ),
            "mood_history": mood_history,
            "cognitive_history": cognitive_history,
            "intent_counts": intent_counts,
        }


def load_events(
    user_id: str | None = None,
    days: int | None = 7,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    path = _events_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    cutoff = _utc_now() - timedelta(days=days) if days is not None else None
    events: list[dict[str, Any]] = []
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        if user_id is not None and str(event.get("user_id") or "") != str(user_id):
            continue
        if cutoff is not None:
            event_time = _parse_timestamp(event.get("timestamp"))
            if event_time is None or event_time < cutoff:
                continue
        events.append(event)

    events.sort(key=lambda event: str(event.get("timestamp") or ""))
    return events[-limit:] if limit is not None else events


def log_event(user_id: str, event: dict[str, Any]) -> None:
    path = _events_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_event: dict[str, Any] = {}
    for key, value in dict(event).items():
        if key not in ALLOWED_EVENT_FIELDS:
            continue
        sanitized = _sanitize_event_field(key, value)
        if sanitized is not _DROP:
            safe_event[key] = sanitized
    safe_event["timestamp"] = safe_event.get("timestamp") or _utc_now().isoformat()
    safe_event["user_id"] = str(user_id or safe_event.get("user_id") or "").strip()
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(safe_event, ensure_ascii=False, sort_keys=True) + "\n")


def infer_event_type(result: dict[str, Any]) -> str:
    route = str(result.get("route") or "")
    intent = str(result.get("intent") or "")
    safety_level = str(result.get("safety_level") or "")

    if safety_level == "urgent_boundary" or route == "safety":
        return "safety_alert"
    if intent == "medication_or_diagnosis" or route == "medical_boundary":
        return "medication_uncertainty"
    if intent == "emotional_support":
        return "emotional_support_signal"
    if intent == "cognitive_concern_screening" or route == "screening":
        return "cognitive_screening"
    if intent == "caregiver_guidance" or route == "caregiver_guidance":
        return "caregiver_guidance"
    if intent == "cognitive_activity" or route == "activity":
        return "activity_request"
    if intent == "knowledge_qa" or route == "rag_qa":
        return "knowledge_qa"
    return "interaction"


def _events_path() -> Path:
    return Path(os.getenv("EVENTS_LOG_PATH") or DEFAULT_EVENTS_PATH)


def _average(values: Any) -> float | None:
    numeric = [value for value in values if isinstance(value, (int, float))]
    return sum(numeric) / len(numeric) if numeric else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _is_json_scalar_or_simple(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(item is None or isinstance(item, (str, int, float, bool)) for item in value)
    return False


_DROP = object()


def _sanitize_event_field(key: str, value: Any) -> Any:
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if key == "event_value":
        return value if isinstance(value, (int, float, bool)) else _DROP
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
        if key in {"timestamp", "user_id", "sender_id"}:
            return text[:128]
        if key in {
            "channel",
            "role",
            "intent",
            "route",
            "safety_level",
            "risk_level",
            "event_type",
            "exercise_type",
            "medication_status",
        }:
            return text[:64] if _looks_like_structured_token(text) else _DROP
        return _DROP
    return _DROP


def _looks_like_structured_token(text: str) -> bool:
    return bool(repr(text)) and len(text) <= 64 and all(
        char.isalnum() or char in {"_", "-", ":", ".", "/", "@"} for char in text
    )
