from __future__ import annotations

from typing import Any

from src.metrics import load_events


HELP_RESPONSE = """照顧者模式指令：
/summary 查看今日摘要
/alerts 查看近期安全提醒
/set_routine 設定日常安排
/set_reminder 設定提醒"""
SUMMARY_EMPTY_RESPONSE = "今日暫時沒有足夠記錄生成摘要。"
ALERTS_EMPTY_RESPONSE = "暫時沒有安全提醒。"
SET_ROUTINE_RESPONSE = "日常安排功能正在開發中。之後可以由照顧者加入覆診、飲水、活動和休息安排。"
SET_REMINDER_RESPONSE = "提醒功能正在開發中。之後可以由照顧者加入提醒文字。系統只會提醒，不會決定藥物劑量或更改醫囑。"
UNKNOWN_COMMAND_RESPONSE = "我未能理解這個照顧者指令。你可以輸入 /help 查看可用指令。"


def handle_caregiver_message(
    message: str,
    sender_id: str,
    linked_user_id: str | None = None,
) -> dict[str, Any]:
    command = (message or "").strip().split(maxsplit=1)[0].lower()
    if command in {"", "/help", "help"}:
        answer = HELP_RESPONSE
        event_counts: dict[str, int] = {}
    elif command == "/summary":
        answer, event_counts = _summary_answer(linked_user_id)
    elif command == "/alerts":
        answer, event_counts = _alerts_answer(linked_user_id)
    elif command == "/set_routine":
        answer = SET_ROUTINE_RESPONSE
        event_counts = {}
    elif command == "/set_reminder":
        answer = SET_REMINDER_RESPONSE
        event_counts = {}
    else:
        answer = UNKNOWN_COMMAND_RESPONSE
        event_counts = {}

    return {
        "answer": answer,
        "role": "caregiver",
        "route": "caregiver_mode",
        "linked_user_id": linked_user_id,
        "sources": [],
        "found": False,
        "rag_called": False,
        "intent": "caregiver_command",
        "safety_level": "normal",
        "debug": {
            "agent": "caregiver_mode",
            "sender_id": sender_id,
            "command": command or "/help",
            "event_counts": event_counts,
        },
    }


def _summary_answer(linked_user_id: str | None) -> tuple[str, dict[str, int]]:
    events = load_events(linked_user_id, limit=100) if linked_user_id else []
    if not events:
        return SUMMARY_EMPTY_RESPONSE, {}

    counts = _count_event_types(events)
    answer = (
        "今日摘要：\n"
        f"- 互動次數：{len(events)}\n"
        f"- 用藥不確定：{counts.get('medication_unsure', 0)}\n"
        f"- 安全提醒：{counts.get('safety_alert', 0)}\n"
        f"- 情緒支援訊號：{counts.get('emotional_support_signal', 0)}\n"
        f"- 活動請求：{counts.get('activity_request', 0)}"
    )
    return answer, counts


def _alerts_answer(linked_user_id: str | None) -> tuple[str, dict[str, int]]:
    events = load_events(linked_user_id, limit=100) if linked_user_id else []
    safety_events = [event for event in events if event.get("event_type") in {"safety_alert", "wandering_or_lost"}]
    if not safety_events:
        return ALERTS_EMPTY_RESPONSE, {}

    counts = _count_event_types(safety_events)
    answer = (
        "近期安全提醒：\n"
        f"- 安全提醒：{counts.get('safety_alert', 0)}\n"
        f"- 走失或失聯相關：{counts.get('wandering_or_lost', 0)}"
    )
    return answer, counts


def _count_event_types(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        event_type = str(event.get("event_type") or "unknown")
        counts[event_type] = counts.get(event_type, 0) + 1
    return counts
