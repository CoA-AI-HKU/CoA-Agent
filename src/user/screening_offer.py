from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from src.metrics import load_events
from src.pipeline.language import detect_answer_language


CONCERN_TYPES = {"memory_concern", "orientation_confusion", "caregiver_reported_worsening"}
YES = {"yes", "y", "好", "可以", "同意", "願意", "愿意", "開始", "开始"}
NO = {"no", "n", "不用", "唔使", "不要", "暫時不要", "暂时不要"}


def should_offer_screening(user_id: str, current_signal: dict[str, str] | None) -> bool:
    if not current_signal or current_signal.get("event_type") not in CONCERN_TYPES:
        return False
    events = load_events(user_id=user_id, days=14)
    if any(event.get("event_type") == "screening_offer" for event in events):
        return False
    today = datetime.now(timezone.utc).date()
    current_type = current_signal["event_type"]
    prior = [event for event in events if event.get("event_type") in CONCERN_TYPES]
    separate_day_memory = any(
        event.get("event_type") == "memory_concern"
        and _event_date(event) is not None
        and _event_date(event) != today
        for event in prior
    )
    different_related_signal = any(event.get("event_type") != current_type for event in prior)
    return (current_type == "memory_concern" and separate_day_memory) or different_related_signal


def consent_reply(message: str, user_id: str) -> bool | None:
    events = load_events(user_id=user_id, days=2)
    offer_indexes = [index for index, event in enumerate(events) if event.get("event_type") == "screening_offer"]
    if not offer_indexes:
        return None
    latest_offer = offer_indexes[-1]
    if any(event.get("event_type") in {"screening_accepted", "screening_declined"} for event in events[latest_offer + 1:]):
        return None
    normalized = " ".join(str(message or "").strip().lower().split())
    if normalized in YES:
        return True
    if normalized in NO:
        return False
    return None


def offer_answer(message: str) -> str:
    language = detect_answer_language(message)
    if language == "en":
        return "You have mentioned some memory-related concerns on separate occasions. Would you like to try a short optional exercise? It is not a diagnosis. Reply Yes or No."
    if language == "zh-Hans":
        return "你在不同时间提到过一些记忆方面的担心。你愿意做一个简短、可选的练习吗？这不是诊断。请回复“愿意”或“不要”。"
    return "你在不同時間提到過一些記憶方面的擔心。你願意做一個簡短、可選的練習嗎？這不是診斷。請回覆「願意」或「不要」。"


def consent_answer(message: str, accepted: bool) -> str:
    language = detect_answer_language(message)
    if not accepted:
        return {"en": "No problem. You can ask for the optional exercise at any time.", "zh-Hans": "没问题。你之后随时可以主动提出进行这个可选练习。"}.get(language, "沒問題。你之後隨時可以主動提出進行這個可選練習。")
    url = os.getenv("SCREENING_PUBLIC_URL", "http://localhost:8080/screening.html")
    return {"en": f"You can open the optional exercise here: {url}\n\nIt is not a diagnosis, and you may stop at any time.", "zh-Hans": f"你可以在这里打开可选练习：{url}\n\n这不是诊断，你可以随时停止。"}.get(language, f"你可以在這裡打開可選練習：{url}\n\n這不是診斷，你可以隨時停止。")


def _event_date(event: dict[str, Any]):
    try:
        return datetime.fromisoformat(str(event.get("timestamp") or "").replace("Z", "+00:00")).date()
    except ValueError:
        return None
