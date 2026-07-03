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
from .agents.types import AgentDecision
from .pipeline.language import detect_answer_language


EMOTIONAL_SUPPORT_RESPONSE = (
    "我明白你可能有點不安。你可以慢慢說，我會用簡單的方式陪你整理。"
    "如果這件事和健康或安全有關，請同時告訴照顧者或醫護人員。"
)
UNKNOWN_RESPONSE = "我未能清楚理解你的意思。你可以用簡單一句再問一次嗎？"


def handle_dementia_user_message(message: str, user_id: str | None = None) -> dict[str, Any]:
    decision = coordinate_message(message, user_id)
    answer_language = detect_answer_language(message)

    if decision.route == "safety":
        result = handle_safety(message, decision)
    elif decision.route == "medical_boundary":
        result = handle_medical_boundary(message, decision)
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

    simplified = simplify_response(result, message, user_id)
    _emit_debug(user_id, message, simplified)
    return simplified


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
        "intent": result.get("intent"),
        "rag_called": result.get("rag_called"),
        "safety_level": result.get("safety_level"),
        "source_count": len(result.get("sources") or []),
    }
    print(f"ORCHESTRATOR_DEBUG {printable}", file=sys.stderr)
