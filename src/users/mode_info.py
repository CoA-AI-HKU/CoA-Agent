from __future__ import annotations

def format_mode_info(role: str | None = None, user_id: str | None = None) -> str:
    """
    Return a short user-facing mode description.
    Keep this simple so MCP can start even before full mode UI is implemented.
    """
    role = role or "unknown"

    if role == "caregiver":
        return "你現在是照顧者模式，可以使用 /summary、/alerts 等指令。"

    if role == "user":
        return "你現在是使用者模式，可以和小安傾談、查詢資料或設定簡單提醒。"

    if role == "admin":
        return "你現在是管理員模式。"

    return "目前模式未設定。你仍可以先使用小安的一般支援功能。"
