from __future__ import annotations

from typing import Any

from src.agents.caregiver_manager_agent import handle_caregiver_manager_message
from src.agents.patient_user_manager_agent import handle_patient_user_message
from src.agents.user_facing_formatter import (
    answer_has_user_visible_leakage,
    answer_has_user_visible_source_text,
    format_user_facing_answer,
    guard_user_facing_answer,
)
from src.metrics import infer_event_type, log_event
from src.user.mode_info import format_mode_info
from src.user.user_registry import (
    get_linked_user_id,
    get_registry_user_id,
    get_user_record,
    get_user_role,
    normalize_sender_id,
)
from src.user.user_memory import build_memory_for_user_id, build_user_memory


def handle_incoming_message(message: str, sender_id: str, channel: str = "") -> dict[str, Any]:
    normalized_sender_id = normalize_sender_id(sender_id)
    role = get_user_role(normalized_sender_id)
    record = get_user_record(normalized_sender_id)
    sender_memory = build_user_memory(normalized_sender_id)
    linked_user_id = get_linked_user_id(normalized_sender_id) if role == "caregiver" else None
    linked_user_memory = build_memory_for_user_id(linked_user_id) if linked_user_id else None

    if _is_mode_info_command(message):
        result = _mode_info_result(normalized_sender_id, role, record)
        event_user_id = linked_user_id or get_registry_user_id(normalized_sender_id) or normalized_sender_id
    elif role == "caregiver":
        result = handle_caregiver_manager_message(message, normalized_sender_id, linked_user_id, channel)
        event_user_id = linked_user_id or normalized_sender_id
    else:
        registry_user_id = get_registry_user_id(normalized_sender_id) if role == "user" else None
        user_id = registry_user_id or normalized_sender_id
        result = handle_patient_user_message(message, normalized_sender_id, user_id, channel)
        event_user_id = user_id

    output = dict(result)
    output["role"] = role
    output["sender_id"] = normalized_sender_id
    output["channel"] = channel
    if role == "user":
        output["user_id"] = event_user_id
    if role == "caregiver":
        output["linked_user_id"] = linked_user_id
    output["memory"] = {
        "sender": sender_memory,
        "linked_user": linked_user_memory,
    }

    debug = dict(output.get("debug", {}))
    debug["message_router"] = {
        "sender_id": normalized_sender_id,
        "role": role,
        "channel": channel,
        "linked_user_id": linked_user_id or None,
        "memory_loaded": True,
    }

    try:
        log_event(
            event_user_id,
            {
                "user_id": event_user_id,
                "sender_id": normalized_sender_id,
                "channel": channel,
                "role": role,
                "intent": output.get("intent"),
                "route": output.get("route"),
                "safety_level": output.get("safety_level"),
                "risk_level": output.get("risk_level"),
                "rag_called": output.get("rag_called"),
                "event_type": infer_event_type(output),
            },
        )
    except Exception as exc:  # pragma: no cover - defensive; user response must continue.
        debug["metrics_warning"] = str(exc)

    output["debug"] = debug
    output = _finalize_user_output(output, message)
    return output


def _is_mode_info_command(message: str) -> bool:
    return (message or "").strip().lower() in {"/whichroleami", "\\whichroleami"}


def _mode_info_result(sender_id: str, role: str, record: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": format_mode_info(sender_id, role, record),
        "role": role,
        "route": "mode_info",
        "manager": "message_router",
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": "mode_info",
        "safety_level": "normal",
        "debug": {"agent": "message_router", "mode_info": True},
    }


def _finalize_user_output(result: dict[str, Any], message: str) -> dict[str, Any]:
    output = dict(result)
    if answer_has_user_visible_source_text(str(output.get("answer") or "")):
        output = format_user_facing_answer(output, show_sources=False)
    output = guard_user_facing_answer(output, message)
    answer = str(output.get("answer") or "")
    if answer_has_user_visible_leakage(answer):
        debug = dict(output.get("debug", {}))
        debug["router_final_guard_retry"] = True
        output["debug"] = debug
        output = guard_user_facing_answer(output, message)
    return output
