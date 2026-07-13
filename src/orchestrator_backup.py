from __future__ import annotations

import os
import sys
from typing import Any

from .agents.coordinator_agent import coordinate_message
from .agents.memory_routine_agent import (
    handle_activity_request,
    handle_personal_memory,
    handle_routine_request,
)
from .agents.rag_evidence_agent import answer_with_dementia_evidence
from .agents.response_simplifier_agent import simplify_response
from .agents.safety_agent import handle_medical_boundary, handle_safety
from .agents.screening_agent import (
    handle_caregiver_observation_guidance,
    handle_cognitive_concern_screening,
    handle_memory_concern,
)
from .agents.types import AgentDecision
from .agents.user_facing_formatter import (
    answer_has_user_visible_leakage,
    format_user_facing_answer,
    guard_user_facing_answer,
)
from .pipeline.language import detect_answer_language

# 🆕 导入日志模块
from .metrics import log_event, infer_event_type


EMOTIONAL_SUPPORT_RESPONSE = (
    "我明白你可能有點不安。你可以慢慢說，我會用簡單的方式陪你整理。"
    "如果這件事和健康或安全有關，請同時告訴照顧者或醫護人員。"
)
UNKNOWN_RESPONSE = "我未能清楚理解你的意思。你可以用簡單一句再問一次嗎？"


def handle_dementia_user_message(
    message: str,
    user_id: str | None = None,
    show_sources: bool = False,
) -> dict[str, Any]:
    decision = coordinate_message(message, user_id)
    answer_language = detect_answer_language(message)

    if decision.route == "safety":
        result = handle_safety(message, decision)
    elif decision.route == "medical_boundary":
        result = handle_medical_boundary(message, decision)
    elif decision.route == "screening":
        result = handle_cognitive_concern_screening(message, user_id)
    elif decision.route in {"memory_concern", "self_memory_concern"}:
        result = handle_memory_concern(message, user_id)
    elif decision.route == "caregiver_guidance":
        result = handle_caregiver_observation_guidance(message, user_id)
    elif decision.route == "rag_qa":
        result = answer_with_dementia_evidence(message, user_id)
    elif decision.route == "memory":
        result = handle_personal_memory(message, user_id)
    elif decision.route == "routine":
        result = handle_routine_request(message, user_id)
    elif decision.route == "activity":
        result = handle_activity_request(message, user_id)
    elif decision.route == "supportive":
        result = _supportive_response(decision)
    else:
        result = _unknown_response(decision)

    result.setdefault("intent", decision.intent)
    result.setdefault("found", False)
    result.setdefault("sources", [])
    result.setdefault("rag_called", False)
    result.setdefault("route", decision.route)
    result.setdefault("safety_level", "normal")
    result["answer_language"] = result.get("answer_language", answer_language)
    _attach_coordinator_debug(result, decision)
    result["debug"]["user_message"] = message

    simplified = simplify_response(result, message, user_id)
    user_facing = format_user_facing_answer(simplified, show_sources=show_sources)
    if not show_sources and _answer_contains_source_text(str(user_facing.get("answer") or "")):
        user_facing = format_user_facing_answer(user_facing, show_sources=False)
        if _answer_contains_source_text(str(user_facing.get("answer") or "")):
            debug = dict(user_facing.get("debug", {}))
            debug["source_text_warning"] = True
            user_facing["debug"] = debug
    user_facing = guard_user_facing_answer(user_facing, message)
    if not show_sources and answer_has_user_visible_leakage(str(user_facing.get("answer") or "")):
        debug = dict(user_facing.get("debug", {}))
        debug["orchestrator_final_guard_retry"] = True
        user_facing["debug"] = debug
        user_facing = guard_user_facing_answer(user_facing, message)
    
    # 🆕 记录事件到 Dashboard（正式生产数据）
    try:
        event_type = infer_event_type(user_facing)
        log_event(
            user_id or "unknown",
            {
                "event_type": event_type,
                "intent": user_facing.get("intent", "unknown"),
                "route": user_facing.get("route", "unknown"),
                "safety_level": user_facing.get("safety_level", "unknown"),
                "rag_called": user_facing.get("rag_called", False),
            }
        )
    except Exception:
        # 日志记录失败不影响主流程（Dashboard 没启动或写入失败都不影响 Bot 回答）
        pass
    
    _emit_debug(user_id, message, user_facing)
    return user_facing


def _supportive_response(decision: AgentDecision) -> dict[str, Any]:
    return {
        "answer": EMOTIONAL_SUPPORT_RESPONSE,
        "intent": decision.intent,
        "safety_level": "supportive_non_clinical",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "supportive",
        "debug": {"agent": "coordinator"},
    }


def _unknown_response(decision: AgentDecision) -> dict[str, Any]:
    return {
        "answer": UNKNOWN_RESPONSE,
        "intent": decision.intent,
        "safety_level": "normal",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "unknown",
        "debug": {"agent": "coordinator"},
    }


def _attach_coordinator_debug(result: dict[str, Any], decision: AgentDecision) -> None:
    debug = dict(result.get("debug", {}))
    debug["coordinator"] = {
        "route": decision.route,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "reason": decision.reason,
        "matched_terms": decision.matched_terms,
        "rag_required": decision.rag_required,
        "safety_override": decision.safety_override,
        "user_role": decision.user_role,
    }
    debug["answer_language"] = result.get("answer_language")
    debug["source_count"] = len(result.get("sources") or [])
    result["debug"] = debug


def _emit_debug(user_id: str | None, message: str, result: dict[str, Any]) -> None:
    if os.getenv("ORCHESTRATOR_DEBUG", "").lower() not in {"1", "true", "yes"}:
        return
    debug = result.get("debug", {})
    coordinator = debug.get("coordinator", {}) if isinstance(debug, dict) else {}
    printable = {
        "user_id": user_id,
        "message_preview": message[:80],
        "coordinator_route": coordinator.get("route"),
        "user_role": coordinator.get("user_role"),
        "intent": result.get("intent"),
        "rag_called": result.get("rag_called"),
        "safety_level": result.get("safety_level"),
        "source_count": len(result.get("sources") or []),
    }
    print(f"ORCHESTRATOR_DEBUG {printable}", file=sys.stderr)


def _answer_contains_source_text(answer: str) -> bool:
    return any(
        phrase in answer
        for phrase in [
            "來源",
            ".md",
            "根據資料庫",
            "資料庫嘅指引",
            "資料庫的指引",
            "資料庫冇提到",
            "source:",
            "sources:",
        ]
    )