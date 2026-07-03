from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.types import AgentResult
from src.pipeline.language import AnswerLanguage, detect_answer_language


PROJECT_ROOT = Path(__file__).resolve().parents[2]
USER_DATA_ROOT = PROJECT_ROOT / "data" / "users"

PERSONAL_MEMORY_RESPONSE = "個人記憶功能正在開發中。之後可以由照顧者加入日常安排、家人稱呼和喜好。"
REMINDER_RESPONSE = "提醒功能正在開發中。現在你可以請照顧者先幫你記錄這個提醒。"
ACTIVITY_RESPONSE = "我們可以做一個簡單小活動。你可以慢慢說出三種水果嗎？不用急，我會等你。"
LOCALIZED_RESPONSES: dict[str, dict[AnswerLanguage, str]] = {
    "memory": {
        "zh-Hant": PERSONAL_MEMORY_RESPONSE,
        "zh-Hans": "个人记忆功能正在开发中。之后可以由照顾者加入日常安排、家人称呼和喜好。",
        "en": "The personal memory feature is still being developed. Later, a caregiver can add routines, family names, and preferences.",
    },
    "routine": {
        "zh-Hant": REMINDER_RESPONSE,
        "zh-Hans": "提醒功能正在开发中。现在你可以请照顾者先帮你记录这个提醒。",
        "en": "The reminder feature is still being developed. For now, please ask a caregiver to help write down this reminder.",
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


def handle_routine_request(message: str, user_id: str | None = None) -> dict[str, Any]:
    routines = load_user_routines(user_id)
    answer_language = detect_answer_language(message)
    return _placeholder_result(
        answer=LOCALIZED_RESPONSES["routine"][answer_language],
        intent="reminder_request",
        route="routine",
        safety_level="reminder_placeholder",
        answer_language=answer_language,
        debug={"agent": "memory_routine", "routines_loaded": bool(routines)},
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
