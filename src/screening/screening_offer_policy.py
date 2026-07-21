from __future__ import annotations

from typing import Any


SIGNAL_TYPES = {"memory_concern", "orientation_confusion", "difficulty_following_steps"}


def should_offer_screening(
    user_id: str,
    role_context: str,
    current_signal: dict[str, Any] | None,
    recent_events: list[dict[str, Any]],
) -> dict[str, Any]:
    signal = current_signal or {}
    route = str(signal.get("route") or "")
    event_type = str(signal.get("event_type") or "")
    explicit_request = bool(signal.get("explicit_request"))
    result = {
        "offer": False,
        "reason": "no screening offer threshold met",
        "urgency": "none",
        "requires_consent": True,
        "send_link_now": False,
    }
    if route in {"safety", "wandering", "emergency"} or event_type in {"wandering_safety", "safety_alert"}:
        return {**result, "reason": "urgent safety route takes priority", "urgency": "urgent_safety"}
    if route == "medical_boundary":
        return {**result, "reason": "medical boundary takes priority"}
    if explicit_request:
        return {**result, "offer": True, "reason": "user explicitly requested a check-in", "urgency": "suggested"}
    caregiver_events = {"caregiver_reported_worsening", "caregiver_worsening_report"}
    if event_type in caregiver_events or any(
        event.get("event_type") in caregiver_events for event in recent_events
    ):
        return {**result, "offer": True, "reason": "caregiver worsening report", "urgency": "suggested"}
    if event_type == "medication_uncertainty":
        return {**result, "offer": True, "reason": "medication uncertainty; offer only after safety advice", "urgency": "optional"}
    concern_count = sum(1 for event in recent_events if event.get("event_type") in SIGNAL_TYPES)
    if concern_count >= 2:
        return {**result, "offer": True, "reason": "repeated cognitive concern signals within 7 days", "urgency": "suggested"}
    if event_type in SIGNAL_TYPES:
        return {**result, "reason": "single mild concern; supportive response only"}
    return result
