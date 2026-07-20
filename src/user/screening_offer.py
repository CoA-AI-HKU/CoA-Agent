from __future__ import annotations

from typing import Any

from src.metrics import load_events
from src.pipeline.language import detect_answer_language
from src.screening.screening_offer_policy import should_offer_screening as evaluate_offer_policy
from src.screening.tokens import SCREENING_VERSION, create_screening_token, screening_url


YES = {"yes", "y", "好", "可以", "開始", "开始", "想", "ok", "okay"}
NO = {"no", "n", "唔使", "不用", "暫時不用", "暂时不用", "遲啲", "迟点", "later"}
OFFER_EVENT_TYPES = {"screening_offered", "screening_offer"}


def should_offer_screening(
    user_id: str,
    current_signal: dict[str, Any] | None,
    role_context: str = "user",
) -> bool:
    recent_events = load_events(user_id=user_id, days=7)
    if _has_resolved_recent_offer(recent_events):
        return False
    policy_events = list(recent_events)
    if current_signal and current_signal.get("event_type"):
        policy_events.append(dict(current_signal))
    return bool(evaluate_offer_policy(user_id, role_context, current_signal, policy_events)["offer"])


def screening_offer_decision(
    user_id: str,
    role_context: str,
    current_signal: dict[str, Any] | None,
) -> dict[str, Any]:
    events = load_events(user_id=user_id, days=7)
    decision = evaluate_offer_policy(user_id, role_context, current_signal, events)
    if decision["offer"] and _has_unanswered_offer(events):
        return {**decision, "offer": False, "reason": "screening consent is already pending"}
    if decision["offer"] and _has_resolved_recent_offer(events):
        return {**decision, "offer": False, "reason": "recent screening offer already resolved"}
    return decision


def consent_reply(message: str, user_id: str) -> bool | None:
    events = load_events(user_id=user_id, days=2)
    offer_indexes = [index for index, event in enumerate(events) if event.get("event_type") in OFFER_EVENT_TYPES]
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


def latest_offer_context(user_id: str) -> dict[str, Any]:
    events = load_events(user_id=user_id, days=2)
    for event in reversed(events):
        if event.get("event_type") in OFFER_EVENT_TYPES:
            return event
    return {}


def offer_answer(message: str, *, caregiver_requested: bool = False) -> str:
    if caregiver_requested:
        return "你的照顧者建議你做一個簡短的記憶與日常狀況小檢查。這不是診斷，也不能判斷是否有腦退化症。如果你願意，可以開始；你也可以選擇不做。"
    language = detect_answer_language(message)
    if language == "en":
        return "I noticed you mentioned some difficulty with memory or daily routines. This is not a diagnosis. If you wish, you can do a short memory and daily-functioning check-in. Would you like to start now?"
    if language == "zh-Hans":
        return "我留意到你提到一些记忆或日常安排上的困扰。这不代表诊断，也不能判断是否有脑退化症。如果你愿意，可以做一个简短的记忆与日常状况小检查，帮助决定是否需要进一步跟进。你想现在开始吗？"
    return "我留意到你提到一些記憶或日常安排上的困擾。這不代表診斷，也不能判斷是否有腦退化症。如果你願意，可以做一個簡短的記憶與日常狀況小檢查，幫助你和照顧者決定是否需要進一步跟進。你想現在開始嗎？"


def consent_answer(
    message: str,
    accepted: bool,
    user_id: str = "",
    *,
    created_by: str = "self",
    caregiver_id: str = "",
    group_chat: bool = False,
) -> str:
    if not accepted:
        return "沒問題，我不會繼續推送。之後如果你想做這個非診斷小檢查，可以再告訴我。"
    if group_chat:
        return "為了保護私隱，小檢查連結只會在私人聊天中發送。請先私訊我。"
    entry = create_screening_token(user_id, created_by, caregiver_id or None)
    return f"你可以在這裡開始簡短的記憶與日常狀況小檢查：{screening_url(entry['token'])}\n\n這不是診斷，你可以隨時停止。"


def _has_unanswered_offer(events: list[dict[str, Any]]) -> bool:
    latest_offer = max((index for index, event in enumerate(events) if event.get("event_type") in OFFER_EVENT_TYPES), default=-1)
    if latest_offer < 0:
        return False
    return not any(event.get("event_type") in {"screening_accepted", "screening_declined"} for event in events[latest_offer + 1:])


def _has_resolved_recent_offer(events: list[dict[str, Any]]) -> bool:
    return any(event.get("event_type") in {"screening_accepted", "screening_declined"} for event in events)
