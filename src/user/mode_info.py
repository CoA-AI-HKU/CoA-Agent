from __future__ import annotations

from typing import Any


def format_mode_info(sender_id: str, role: str, record: dict[str, Any] | None = None) -> str:
    record = record or {}
    if role == "caregiver":
        linked_user_id = str(record.get("linked_user_id") or "").strip()
        suffix = f"\n\nsender_id：{sender_id}\nlinked_user_id：{linked_user_id}" if linked_user_id else f"\n\nsender_id：{sender_id}"
        return (
            "你目前是：照顧者模式\n\n"
            "你可以使用：\n"
            "\\summary 查看今日摘要\n"
            "\\alerts 查看近期安全提醒\n"
            "\\set_routine 設定日常安排\n"
            "\\set_reminder 設定提醒\n"
            "\\help 查看指令"
            f"{suffix}"
        )
    if role == "user":
        user_id = str(record.get("user_id") or "").strip()
        suffix = f"\n\nsender_id：{sender_id}\nuser_id：{user_id}" if user_id else f"\n\nsender_id：{sender_id}"
        return (
            "你目前是：使用者模式\n\n"
            "我會用簡短、清楚的方式提供日常支援、活動建議和安全提醒。"
            f"{suffix}"
        )
    return (
        "你目前是：未登記使用者\n\n"
        "我可以提供一般資訊和簡單支援，但照顧者設定、摘要和提醒功能只開放給已登記帳號。"
        f"\n\nsender_id：{sender_id}"
    )
