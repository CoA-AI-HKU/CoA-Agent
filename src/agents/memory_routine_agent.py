from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agents.types import AgentResult
from src.pipeline.language import AnswerLanguage, detect_answer_language
from src.reminders.trace_logging import log_reminder_checkpoint
from src.user.user_registry import get_display_name, get_user_record_by_user_id

logger = logging.getLogger(__name__)

try:
    from src.reminders.chat_reminders import (
        LOCAL_TIMEZONE,
        ParsedReminder,
        create_reminder_for_user,
        extract_reminder_text_only,
        parse_reminder_request,
        reminder_confirmation_text,
    )
    from src.reminders.llm_reminder_extractor import decide_reminder_via_llm
except ImportError:  # reminder deps (SQLAlchemy etc.) unavailable in this process
    LOCAL_TIMEZONE = None
    ParsedReminder = None
    create_reminder_for_user = None
    extract_reminder_text_only = None
    parse_reminder_request = None
    reminder_confirmation_text = None
    decide_reminder_via_llm = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA_ROOT = PROJECT_ROOT / "data" / "users"

PERSONAL_MEMORY_RESPONSE = "個人記憶功能正在開發中。之後可以由照顧者加入日常安排、家人稱呼和喜好。"
REMINDER_UNAVAILABLE_RESPONSE = "提醒功能暫時未能使用。現在你可以請照顧者先幫你記錄這個提醒。"
REMINDER_NEEDS_ACCOUNT_RESPONSE = "設定提醒需要先完成登記，請輸入 \\register 開始，或請照顧者幫忙。"
REMINDER_NEEDS_TIME_RESPONSE = "好呀，可以話我知幾點提醒你嗎？例如「12:30提醒我食藥」。"
ACTIVITY_RESPONSE = "我們可以做一個簡單小活動。你可以慢慢說出三種水果嗎？不用急，我會等你。"
LOCALIZED_RESPONSES: dict[str, dict[AnswerLanguage, str]] = {
    "memory": {
        "zh-Hant": PERSONAL_MEMORY_RESPONSE,
        "zh-Hans": "个人记忆功能正在开发中。之后可以由照顾者加入日常安排、家人称呼和喜好。",
        "en": "The personal memory feature is still being developed. Later, a caregiver can add routines, family names, and preferences.",
    },
    "routine_unavailable": {
        "zh-Hant": REMINDER_UNAVAILABLE_RESPONSE,
        "zh-Hans": "提醒功能暂时未能使用。现在你可以请照顾者先帮你记录这个提醒。",
        "en": "The reminder feature isn't available right now. For now, please ask a caregiver to help write down this reminder.",
    },
    "routine_needs_account": {
        "zh-Hant": REMINDER_NEEDS_ACCOUNT_RESPONSE,
        "zh-Hans": "设定提醒需要先完成登记，请输入 \\register 开始，或请照顾者帮忙。",
        "en": "Setting a reminder needs a registered account first — send \\register to begin, or ask a caregiver for help.",
    },
    "routine_needs_time": {
        "zh-Hant": REMINDER_NEEDS_TIME_RESPONSE,
        "zh-Hans": "好呀，可以话我知几点提醒你吗？例如「12:30提醒我食药」。",
        "en": "Sure — what time should I remind you? For example, \"remind me to take medicine at 12:30\".",
    },
    "activity": {
        "zh-Hant": ACTIVITY_RESPONSE,
        "zh-Hans": "我们可以做一个简单小活动。你可以慢慢说出三种水果吗？不用急，我会等你。",
        "en": "We can do a simple activity. Can you slowly name three fruits? No rush, I will wait.",
    },
}


def load_user_profile(user_id: str | None) -> dict[str, Any]:
    return _load_user_json(user_id, "profile.json")


def load_user_routines(user_id: str | None) -> dict[str, Any]:
    return _load_user_json(user_id, "routines.json")


def handle_personal_memory(message: str, user_id: str | None = None) -> dict[str, Any]:
    profile = load_user_profile(user_id)
    answer_language = detect_answer_language(message)
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["memory"][answer_language],
        intent="personal_memory",
        route="memory",
        safety_level="personal_memory_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine", "profile_loaded": bool(profile)},
    )


def handle_routine_request(
    message: str,
    user_id: str | None = None,
    channel: str = "",
    message_id: str = "",
    sender_id: str = "",
) -> dict[str, Any]:
    answer_language = detect_answer_language(message)

    tool_available = create_reminder_for_user is not None and parse_reminder_request is not None
    log_reminder_checkpoint(
        "reminder_tool_available",
        user_id=user_id, channel=channel, message_id=message_id, available=tool_available,
    )
    if not tool_available:
        logger.warning("src.reminders unavailable in this process; falling back to placeholder")
        return _placeholder_result(
            answer=LOCALIZED_RESPONSES["routine_unavailable"][answer_language],
            intent="reminder_request",
            route="routine",
            safety_level="reminder_placeholder",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "reminder_backend_available": False},
        )

    if not user_id:
        return _placeholder_result(
            answer=LOCALIZED_RESPONSES["routine_needs_account"][answer_language],
            intent="reminder_request",
            route="routine",
            safety_level="reminder_needs_account",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "reason": "no_user_id"},
        )

    parsed = parse_reminder_request(message)
    llm_decision = None
    if parsed is None and decide_reminder_via_llm is not None:
        # The regex parser only recognizes fixed phrasings ("5:25", "五點",
        # "兩分鐘後"...) — real messages drift outside those ("食完飯後",
        # "遲啲", typos, unseen constructions). Rather than keep hand-patching
        # every new phrasing as it's found in production, fall back to asking
        # the LLM to make the actual judgment call: is this really a
        # reminder, what's the time, what's the recurrence, and — if it
        # can't tell — compose its own clarifying reply instead of the fixed
        # template below. Only reached when the fast deterministic path
        # already found nothing, so well-formed messages never pay this
        # latency/cost.
        llm_decision = decide_reminder_via_llm(message, datetime.now(LOCAL_TIMEZONE), answer_language)

    if llm_decision is not None and not llm_decision.is_reminder:
        return _placeholder_result(
            answer=llm_decision.response or LOCALIZED_RESPONSES["routine_needs_time"][answer_language],
            intent="reminder_request",
            route="routine",
            safety_level="reminder_declined_by_model",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "reason": "llm_declined"},
        )

    if llm_decision is not None and llm_decision.time is not None:
        parsed = ParsedReminder(
            time=llm_decision.time,
            text=llm_decision.task or extract_reminder_text_only(message),
            days=llm_decision.days,
        )

    if parsed is None:
        return _placeholder_result(
            answer=(llm_decision.response if llm_decision is not None and llm_decision.response
                    else LOCALIZED_RESPONSES["routine_needs_time"][answer_language]),
            intent="reminder_request",
            route="routine",
            safety_level="reminder_needs_time",
            answer_language=answer_language,
            debug={
                "agent": "memory_routine",
                "reason": "no_time_found",
                # message_router.py reads these to arm a short-lived "waiting
                # for a time" state, so a bare-time follow-up like "3:41"
                # (which alone wouldn't classify as a reminder request) can
                # still complete this reminder instead of confusing the user.
                # The language is carried over from *this* message because a
                # bare time reply like "3:41" has no CJK characters to detect
                # a language from on its own.
                "reminder_pending_text": extract_reminder_text_only(message),
                "reminder_pending_language": answer_language,
            },
        )

    display_name = get_display_name((get_user_record_by_user_id(user_id)[0]) or "") or ""
    log_reminder_checkpoint(
        "reminder_tool_invoked",
        user_id=user_id, channel=channel, message_id=message_id,
        normalized_due_time=parsed.time, days=parsed.days,
    )
    try:
        reminder = create_reminder_for_user(
            user_id, display_name, parsed.text, parsed.time, days=parsed.days,
            channel=channel, message_id=message_id, chat_sender_id=sender_id,
        )
    except Exception:
        logger.exception("Failed to create reminder for user_id=%s", user_id)
        return _placeholder_result(
            answer=LOCALIZED_RESPONSES["routine_unavailable"][answer_language],
            intent="reminder_request",
            route="routine",
            safety_level="reminder_placeholder",
            answer_language=answer_language,
            debug={"agent": "memory_routine", "reason": "create_failed"},
        )

    return _placeholder_result(
        answer=reminder_confirmation_text(parsed.time, parsed.text, parsed.days, answer_language),
        intent="reminder_request",
        route="routine",
        safety_level="reminder_created",
        answer_language=answer_language,
        debug={
            "agent": "memory_routine",
            "reminder_id": reminder.id,
            "reminder_time": parsed.time,
            "reminder_text": parsed.text,
            "reminder_days": parsed.days,
        },
    )


def handle_activity_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    answer_language = detect_answer_language(message)
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["activity"][answer_language],
        intent="cognitive_activity",
        route="activity",
        safety_level="activity_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine"},
    )


def _load_user_json(user_id: str | None, filename: str) -> dict[str, Any]:
    if not user_id:
        return {}
    safe_user_id = _safe_user_id(user_id)
    if not safe_user_id:
        return {}
    path = USER_DATA_ROOT / safe_user_id / filename
    try:
        resolved = path.resolve(strict=False)
        if USER_DATA_ROOT.resolve() not in resolved.parents:
            return {}
        if not resolved.exists():
            return {}
        data = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_user_id(user_id: str) -> str:
    return "".join(char for char in str(user_id) if char.isalnum() or char in {"_", "-"}).strip()


def _placeholder_result(
    answer: str,
    intent: str,
    route: str,
    safety_level: str,
    answer_language: AnswerLanguage,
    debug: dict[str, Any],
) -> dict[str, Any]:
    result = AgentResult(
        answer=answer,
        intent=intent,
        safety_level=safety_level,
        found=False,
        sources=[],
        rag_called=False,
        route=route,
        debug=debug,
    ).to_dict()
    result["answer_language"] = answer_language
    return result
