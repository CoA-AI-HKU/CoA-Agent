from __future__ import annotations

import os
import sys
import logging
import json
import uuid
from typing import Any

from .agents.coordinator_agent import coordinate_message
from .agents.memory_routine_agent import (
    handle_activity_request,
    handle_personal_memory,
    handle_routine_request,
)
from .agents.response_simplifier_agent import simplify_response
from .agents.rag_evidence_agent import answer_with_dementia_evidence
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
from .pipeline.rag_agent import answer_question, build_default_rag_config
from .pipeline.query_normalization import log_string_diagnostic
from .rag.execution_metrics import record_retrieval


logger = logging.getLogger(__name__)

# 🆕 导入日志模块
EMOTIONAL_SUPPORT_RESPONSE = (
    "我明白你可能有點不安。你可以慢慢說，我會用簡單的方式陪你整理。"
    "如果這件事和健康或安全有關，請同時告訴照顧者或醫護人員。"
)
UNKNOWN_RESPONSE = "我未能清楚理解你的意思。你可以用簡單一句再問一次嗎？"
ROLE_CORRECTION_RESPONSE = "明白，我不會把你當成腦退化症患者。之後我會用中立方式回應你；除非你自己提到相關情況，我不會假設你有腦退化症或需要照顧者。"
ROLE_CORRECTION_CANTONESE_RESPONSE = "明白，我唔會當你係腦退化症患者。之後我會用中立方式回應；除非你自己提到相關情況，否則我唔會假設你有腦退化症或者需要照顧者。"
PROMPT_INJECTION_RESPONSE = "我不能更改安全規則或透露內部設定。不過，我可以繼續用安全、簡單的方式幫你。"
DIAGNOSIS_FORCING_RESPONSE = "我不能作診斷或提供風險分數。如果你擔心記憶或思考上的改變，我可以幫你整理情況，並建議是否需要找醫生或記憶診所評估。"


def handle_dementia_user_message(
    message: str,
    user_id: str | None = None,
    show_sources: bool = False,
) -> dict[str, Any]:
    log_string_diagnostic(
        logger, "orchestrator_input_message", message,
        sender_id=str(user_id or ""),
    )
    message_id = uuid.uuid4().hex
    decision = coordinate_message(message, user_id)
    logger.info(
        "orchestrator route selected",
        extra={
            "event": "orchestrator_route_selected",
            "user_id": user_id,
            "route": decision.route,
            "intent": decision.intent,
        },
    )
    answer_language = detect_answer_language(message)
    arag_result = answer_with_dementia_evidence(message, user_id) if decision.rag_required else {}
    arag_debug = dict(arag_result.get("debug") or {})
    scores = [float(score or 0.0) for score in arag_debug.get("scores") or []]
    retrieved_count = int(arag_debug.get("retrieved_count") or 0)
    record_retrieval(enabled=decision.rag_required, scores=scores, chunk_count=retrieved_count)

    if decision.route == "safety":
        result = handle_safety(message, decision)
    elif decision.route == "medical_boundary":
        result = handle_medical_boundary(message, decision)
    elif decision.route == "role_correction":
        result = _role_correction_response(message, decision)
    elif decision.route == "prompt_injection":
        result = _prompt_injection_response(message, decision)
    elif decision.route == "screening":
        result = handle_cognitive_concern_screening(message, user_id)
    elif decision.route in {"memory_concern", "self_memory_concern"}:
        result = handle_memory_concern(message, user_id)
    elif decision.route == "caregiver_guidance":
        result = handle_caregiver_observation_guidance(message, user_id, arag_result)
    elif decision.route == "rag_qa":
        result = dict(arag_result)
        result.update({"route": "rag_qa", "rag_called": True})
    elif decision.route == "memory":
        result = handle_personal_memory(message, user_id)
    elif decision.route == "routine":
        result = handle_routine_request(message, user_id)
    elif decision.route == "activity":
        result = handle_activity_request(message, user_id)
    elif decision.route == "supportive":
        result = _supportive_response(message, decision)
    elif decision.route == "daily_life":
        result = _daily_life_response(message, decision)
    elif decision.route == "general":
        result = _general_response(message, decision)
    else:
        result = _unknown_response(message, decision)

    result["intent"] = decision.intent
    result.setdefault("found", False)
    result.setdefault("sources", [])
    result.setdefault("rag_called", False)
    result.setdefault("route", decision.route)
    result.setdefault("safety_level", "normal")
    result.setdefault("fallback_reason", "insufficient_evidence" if decision.rag_required and not result.get("found") else "none")
    result["answer_language"] = result.get("answer_language", answer_language)
    trace = {
        "message_id": message_id,
        "user_id": user_id,
        "role": decision.user_role,
        "detected_intent": decision.intent,
        "selected_route": decision.route,
        "planner_decision": decision.reason,
        "retrieval_enabled": decision.rag_required,
        "retrieval_query": arag_debug.get("search_query"),
        "retrieved_chunk_count": retrieved_count,
        "top_similarity_scores": scores,
        "selected_documents": list(arag_result.get("sources") or []),
        "generation_model": arag_debug.get("llm_model"),
        "safety_decisions": {
            "override": decision.safety_override,
            "level": result.get("safety_level"),
        },
    }
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
    
    # Interaction events are owned by message_router, where sender role and
    # transport context are available. The orchestrator intentionally does not
    # log them, preventing duplicate events for one incoming message.
    trace["final_response"] = str(user_facing.get("answer") or "")
    debug = dict(user_facing.get("debug") or {})
    debug["execution_trace"] = trace
    user_facing["debug"] = debug
    if os.getenv("ARAG_DEBUG", "").lower() in {"1", "true", "yes"}:
        logger.info("ARAG_EXECUTION_TRACE %s", json.dumps(trace, ensure_ascii=False))
    _emit_debug(user_id, message, user_facing)
    return user_facing


def _daily_life_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("出去走走", "出去散步", "出街行下", "go for a walk")):
        answer = ("可以呀，出去走走通常可以令人放鬆。出門前可以先看看天氣，帶好電話和鎖匙，"
                  "並告訴家人你會去哪裡；如果你感到頭暈、容易迷路或身體不舒服，最好先請家人陪同。")
    elif any(term in normalized for term in ("鎖匙", "鑰匙")):
        answer = "先別著急，可以依次看看門邊、袋子、外套口袋和最近用過鎖匙的地方；如果仍找不到，可以請家人一起找，並使用備用鎖匙。"
    elif any(term in normalized for term in ("煮飯", "cook")):
        answer = "如果你現在精神和身體狀況良好，可以準備簡單的一餐。開始前先把材料放好，煮食時不要離開爐火；如果感到頭暈、很疲倦或不確定爐具操作，請家人陪同或改吃不用開火的食物。"
    elif any(term in normalized for term in ("巴士", "bus")):
        answer = "可以先查看路線和回程時間，帶好電話、鎖匙和車費，並告訴家人目的地；如果你不熟悉路線、容易迷路或身體不舒服，最好請熟悉路線的人同行。"
    elif "打電話" in normalized:
        answer = "可以呀，你可以現在打給她。如果一時找不到號碼，可以看看通訊錄或請身邊的人幫你找，但不要把密碼或驗證碼告訴別人。"
    else:
        answer = "可以先按自己的能力和當時情況安排。出發前準備好電話和鎖匙，告訴家人目的地；如果身體不舒服、不熟悉路線或感到不安全，就請可信任的人陪同。"
    return {"answer": answer, "intent": decision.intent, "safety_level": "conditional_daily_life_safety",
            "found": False, "sources": [], "rag_called": False, "route": "daily_life",
            "fallback_reason": "none", "debug": {"agent": "coordinator"}}


def _supportive_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("你好", "您好", "早晨", "午安", "晚安", "hello", "hi")):
        answer = "你好！很高興見到你。今天有甚麼想聊，或需要我幫忙整理的事嗎？"
    elif any(term in normalized for term in ("好累", "很累", "攰", "疲倦", "tired", "exhausted")):
        answer = (
            "聽起來你今天很累。可以先讓自己休息一下、喝點水，慢慢來。"
            "如果疲倦持續、突然很嚴重，或同時有其他不適，請告訴家人並向醫護人員查詢。"
        )
    else:
        answer = EMOTIONAL_SUPPORT_RESPONSE
    return {
        "answer": answer,
        "intent": decision.intent,
        "safety_level": "supportive_non_clinical",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "supportive",
        "debug": {"agent": "coordinator"},
    }


def _general_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    normalized = str(message or "").lower()
    if any(term in normalized for term in ("數獨", "数独", "sudoku")):
        answer = (
            "我覺得數獨幾好玩，尤其是逐步推理、終於填對整個方格時很有滿足感。"
            "如果你喜歡安靜思考，可以由容易級開始玩。"
        )
    elif any(term in normalized for term in ("麻將", "麻将", "打牌", "mahjong")):
        answer = (
            "可以呀，如果你喜歡打麻將，和朋友輕鬆玩一會也可以是很好的社交活動。"
            "記得按自己的精神和時間安排，中途休息一下；如果涉及金錢，就先定好能接受的限額。"
        )
    elif any(term in normalized for term in ("吃什麼", "食什麼", "食咩", "晚上吃", "今晚食", "晚餐")):
        answer = (
            "今晚可以按你的口味選一頓簡單的飯，例如飯或麵配蔬菜，再加你喜歡的蛋、魚或豆腐。"
            "如果你有醫生建議的飲食限制，就以醫護人員的建議為先。"
        )
    else:
        answer = "我明白你的意思。你可以再告訴我多一點，我會陪你慢慢整理。"
    return {
        "answer": answer,
        "intent": decision.intent,
        "safety_level": "normal",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "general",
        "debug": {"agent": "coordinator"},
    }


def _role_correction_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    cantonese = any(term in message for term in ("唔", "冇", "係"))
    return {
        "answer": ROLE_CORRECTION_CANTONESE_RESPONSE if cantonese else ROLE_CORRECTION_RESPONSE,
        "intent": decision.intent,
        "safety_level": "role_correction",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "role_correction",
        "debug": {"agent": "coordinator"},
    }


def _prompt_injection_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    diagnosis_terms = ("診斷", "风险分数", "風險分數", "risk score", "dementia diagnosis", "pretend you are a doctor")
    return {
        "answer": DIAGNOSIS_FORCING_RESPONSE if any(term in message.lower() for term in diagnosis_terms) else PROMPT_INJECTION_RESPONSE,
        "intent": decision.intent,
        "safety_level": "prompt_injection_boundary",
        "found": False,
        "sources": [],
        "rag_called": False,
        "route": "prompt_injection",
        "debug": {"agent": "coordinator"},
    }


def _unknown_response(message: str, decision: AgentDecision) -> dict[str, Any]:
    cjk_count = sum("\u3400" <= char <= "\u9fff" for char in str(message or ""))
    latin_words = [word for word in str(message or "").split() if word.isalpha()]
    intelligible = cjk_count >= 3 or len(latin_words) >= 2
    return {
        "answer": (
            "我明白你的要求，但這個功能暫時未能處理。你可以問我記憶支援、腦退化症資訊或日常生活問題。"
            if intelligible
            else UNKNOWN_RESPONSE
        ),
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
