from __future__ import annotations

from typing import Any

from src.orchestrator import handle_dementia_user_message


def handle_user_message(message: str, sender_id: str, user_id: str | None = None) -> dict[str, Any]:
    resolved_user_id = user_id or sender_id
    result = handle_dementia_user_message(message, user_id=resolved_user_id)
    output = dict(result)
    output["role"] = output.get("role") or "user"
    output["user_id"] = resolved_user_id
    debug = dict(output.get("debug", {}))
    debug["user_mode"] = {"sender_id": sender_id, "user_id": resolved_user_id}
    output["debug"] = debug
    return output
