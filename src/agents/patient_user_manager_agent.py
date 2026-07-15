from __future__ import annotations

from typing import Any

from src.citations import finalize_user_facing_result
from src.orchestrator import handle_dementia_user_message
from src.user.user_memory import build_memory_for_user_id, build_user_memory


def handle_patient_user_message(
    message: str,
    sender_id: str,
    user_id: str | None = None,
    channel: str = "",
) -> dict[str, Any]:
    resolved_user_id = user_id or sender_id
    sender_memory = build_user_memory(sender_id)
    user_memory = build_memory_for_user_id(resolved_user_id)
    result = handle_dementia_user_message(message, user_id=resolved_user_id)
    output = dict(result)
    output["manager"] = "patient_user_manager"
    output["role"] = output.get("role") or "user"
    output["user_id"] = resolved_user_id
    output["memory"] = {
        "sender": sender_memory,
        "user": user_memory,
    }
    debug = dict(output.get("debug", {}))
    debug["patient_user_manager"] = {
        "sender_id": sender_id,
        "user_id": resolved_user_id,
        "channel": channel,
        "memory_loaded": True,
    }
    output["debug"] = debug
    return finalize_user_facing_result(output)
