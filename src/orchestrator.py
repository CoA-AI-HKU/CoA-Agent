from __future__ import annotations

import os
import sys
from typing import Any

from .intent_router import IntentResult, classify_intent
from .pipeline.rag_agent import answer_question, build_default_rag_config


SAFETY_RESPONSE = "這個情況可能需要即時協助。請先確保安全，並盡快聯絡照顧者、醫護人員或緊急服務。"
MEDICAL_BOUNDARY_RESPONSE = "我不能提供診斷、停藥、加藥、減藥或劑量建議。這類問題需要由醫生、藥劑師或合資格醫護人員判斷。"
EMOTIONAL_SUPPORT_RESPONSE = (
    "我明白你可能有點不安。你可以慢慢說，我會用簡單的方式陪你整理。"
    "如果這件事和健康或安全有關，請同時告訴照顧者或醫護人員。"
)
COGNITIVE_ACTIVITY_RESPONSE = "我們可以做一個簡單小活動。你可以慢慢說出三種水果嗎？不用急，我會等你。"
REMINDER_RESPONSE = "提醒功能正在開發中。現在你可以請照顧者先幫你記錄這個提醒。"
PERSONAL_MEMORY_RESPONSE = "個人記憶功能正在開發中。之後可以由照顧者加入日常安排、家人稱呼和喜好。"
UNKNOWN_RESPONSE = "我未能清楚理解你的意思。你可以用簡單一句再問一次嗎？"

DEMENTIA_CONTEXT_TERMS = [
    "腦退化",
    "認知障礙",
    "輕度認知障礙",
    "照顧",
    "照顧者",
    "記憶",
    "症狀",
    "長者",
    "失智",
    "癡呆",
    "dementia",
    "mci",
    "caregiver",
    "caregiving",
    "memory",
    "alzheimer",
]


def handle_dementia_user_message(message: str, user_id: str | None = None) -> dict[str, Any]:
    intent_result = classify_intent(message)
    route = intent_result.intent

    if intent_result.intent == "safety_sensitive":
        return _static_response(
            answer=SAFETY_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="urgent_boundary",
            user_id=user_id,
        )

    if intent_result.intent == "medication_or_diagnosis":
        return _static_response(
            answer=MEDICAL_BOUNDARY_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="medical_boundary",
            user_id=user_id,
        )

    if intent_result.intent == "knowledge_qa":
        return _rag_response(message, intent_result, route="knowledge_qa", user_id=user_id)

    if intent_result.intent == "emotional_support":
        if _mentions_dementia_context(message):
            return _rag_response(message, intent_result, route="emotional_support_rag", user_id=user_id)
        return _static_response(
            answer=EMOTIONAL_SUPPORT_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="supportive_non_clinical",
            user_id=user_id,
        )

    if intent_result.intent == "cognitive_activity":
        return _static_response(
            answer=COGNITIVE_ACTIVITY_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="activity_placeholder",
            user_id=user_id,
        )

    if intent_result.intent == "reminder_request":
        return _static_response(
            answer=REMINDER_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="reminder_placeholder",
            user_id=user_id,
        )

    if intent_result.intent == "personal_memory":
        return _static_response(
            answer=PERSONAL_MEMORY_RESPONSE,
            intent_result=intent_result,
            route=route,
            safety_level="personal_memory_placeholder",
            user_id=user_id,
        )

    return _static_response(
        answer=UNKNOWN_RESPONSE,
        intent_result=intent_result,
        route="unknown",
        safety_level="unknown_safe_fallback",
        user_id=user_id,
    )


def _rag_response(message: str, intent_result: IntentResult, route: str, user_id: str | None) -> dict[str, Any]:
    raw_result = answer_question(message, build_default_rag_config("mcp"))
    result = dict(raw_result) if isinstance(raw_result, dict) else {"answer": str(raw_result)}
    sources = result.get("sources") or []
    found = bool(result.get("found", False))
    debug = _debug_payload(
        intent_result=intent_result,
        route=route,
        rag_called=True,
        found=found,
        source_count=len(sources),
        safety_level="normal",
        user_id=user_id,
        existing_debug=result.get("debug") if isinstance(result.get("debug"), dict) else None,
    )
    result.update(
        {
            "intent": intent_result.intent,
            "intent_debug": _intent_debug(intent_result),
            "safety_level": "normal",
            "rag_called": True,
            "found": found,
            "sources": sources,
            "debug": debug,
        }
    )
    _emit_debug(debug)
    return result


def _static_response(
    answer: str,
    intent_result: IntentResult,
    route: str,
    safety_level: str,
    user_id: str | None,
) -> dict[str, Any]:
    debug = _debug_payload(
        intent_result=intent_result,
        route=route,
        rag_called=False,
        found=False,
        source_count=0,
        safety_level=safety_level,
        user_id=user_id,
    )
    result = {
        "answer": answer,
        "intent": intent_result.intent,
        "intent_debug": _intent_debug(intent_result),
        "safety_level": safety_level,
        "found": False,
        "sources": [],
        "rag_called": False,
        "debug": debug,
    }
    _emit_debug(debug)
    return result


def _debug_payload(
    intent_result: IntentResult,
    route: str,
    rag_called: bool,
    found: bool,
    source_count: int,
    safety_level: str,
    user_id: str | None,
    existing_debug: dict[str, Any] | None = None,
) -> dict[str, Any]:
    debug = dict(existing_debug or {})
    debug.update(
        {
            "intent": intent_result.intent,
            "matched_terms": intent_result.matched_terms,
            "reason": intent_result.reason,
            "rag_called": rag_called,
            "found": found,
            "source_count": source_count,
            "safety_level": safety_level,
            "route": route,
        }
    )
    if user_id:
        debug["user_id_present"] = True
    return debug


def _intent_debug(intent_result: IntentResult) -> dict[str, Any]:
    return {
        "confidence": intent_result.confidence,
        "matched_terms": intent_result.matched_terms,
        "reason": intent_result.reason,
    }


def _mentions_dementia_context(message: str) -> bool:
    normalized = message.lower()
    return any(term.lower() in normalized for term in DEMENTIA_CONTEXT_TERMS)


def _emit_debug(debug: dict[str, Any]) -> None:
    if os.getenv("ORCHESTRATOR_DEBUG", "").lower() not in {"1", "true", "yes"}:
        return
    printable = {
        key: debug.get(key)
        for key in ("intent", "matched_terms", "rag_called", "found", "source_count", "safety_level", "route")
    }
    print(f"ORCHESTRATOR_DEBUG {printable}", file=sys.stderr)
