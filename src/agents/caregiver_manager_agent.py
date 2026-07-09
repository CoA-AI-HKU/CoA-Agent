from __future__ import annotations

from typing import Any

from src.caregiver_mode import handle_caregiver_message
from src.orchestrator import handle_dementia_user_message
from src.user_memory import build_memory_for_user_id, build_user_memory


CAREGIVER_COMMANDS = {"/help", "help", "/summary", "/alerts", "/set_routine", "/set_reminder"}


def handle_caregiver_manager_message(
    message: str,
    sender_id: str,
    linked_user_id: str | None = None,
    channel: str = "",
) -> dict[str, Any]:
    caregiver_memory = build_user_memory(sender_id)
    linked_user_memory = build_memory_for_user_id(linked_user_id) if linked_user_id else None
    command = (message or "").strip().split(maxsplit=1)[0].lower()
    if command in CAREGIVER_COMMANDS or command == "":
        result = handle_caregiver_message(message, sender_id, linked_user_id)
    elif command.startswith("/"):
        result = handle_caregiver_message(message, sender_id, linked_user_id)
    else:
        result = handle_dementia_user_message(message, user_id=linked_user_id or sender_id)
        result = dict(result)
        result["role"] = "caregiver"
        result["linked_user_id"] = linked_user_id

    output = dict(result)
    output["manager"] = "caregiver_manager"
    output["role"] = "caregiver"
    output["linked_user_id"] = linked_user_id
    output["memory"] = {
        "sender": caregiver_memory,
        "linked_user": linked_user_memory,
    }
    debug = dict(output.get("debug", {}))
    debug["caregiver_manager"] = {
        "sender_id": sender_id,
        "linked_user_id": linked_user_id,
        "channel": channel,
        "command": command,
        "memory_loaded": True,
    }
    output["debug"] = debug
    return output
