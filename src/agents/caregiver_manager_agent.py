from __future__ import annotations

from typing import Any

from src.caregiver_mode import handle_caregiver_message
from src.orchestrator import handle_dementia_user_message
from src.agents.screening_agent import handle_caregiver_observation_guidance
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
    elif _is_caregiver_cognitive_risk_question(message):
        result = handle_caregiver_observation_guidance(message, linked_user_id or sender_id)
        result = dict(result)
        result["role"] = "caregiver"
        result["linked_user_id"] = linked_user_id
        result["intent"] = "caregiver_guidance"
        result["route"] = "caregiver_guidance"
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


def _is_caregiver_cognitive_risk_question(message: str) -> bool:
    normalized = (message or "").strip().lower()
    if not normalized:
        return False
    memory_terms = [
        "記唔住",
        "記不住",
        "記性差",
        "記憶力變差",
        "忘記事情",
        "唔記得",
        "忘記",
        "重複問",
        "腦退化症",
        "認知障礙",
        "dementia",
        "memory",
        "forgetting",
    ]
    risk_terms = [
        "是不是",
        "是否",
        "會不會",
        "係咪",
        "係唔係",
        "最近",
        "成日",
        "常常",
        "經常",
        "測試",
        "测试",
        "篩查",
        "筛查",
        "評估",
        "评估",
        "想做",
        "test",
        "screening",
        "assessment",
    ]
    return any(term in normalized for term in memory_terms) and any(term in normalized for term in risk_terms)
