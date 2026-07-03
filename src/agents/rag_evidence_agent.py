from __future__ import annotations

from typing import Any

from src.pipeline.prompts import FALLBACK_ANSWER
from src.pipeline.rag_agent import answer_question, build_default_rag_config


def answer_with_dementia_evidence(message: str, user_id: str | None = None) -> dict[str, Any]:
    raw = answer_question(message, build_default_rag_config("mcp"))

    if isinstance(raw, str):
        return {
            "answer": raw or FALLBACK_ANSWER,
            "intent": "knowledge_qa",
            "safety_level": "normal",
            "found": bool(raw and "找不到足夠資料" not in raw),
            "sources": [],
            "rag_called": True,
            "route": "rag_qa",
            "debug": {"agent": "rag_evidence", "rag_result_type": "str"},
        }

    if isinstance(raw, dict):
        result = dict(raw)
        result.setdefault("answer", FALLBACK_ANSWER)
        if not result.get("found") and not result.get("answer"):
            result["answer"] = FALLBACK_ANSWER
        result.setdefault("intent", "knowledge_qa")
        result.setdefault("found", False)
        result.setdefault("sources", [])
        result.setdefault("safety_level", "normal")
        result["rag_called"] = True
        result["route"] = "rag_qa"
        debug = dict(result.get("debug", {}))
        debug["agent"] = "rag_evidence"
        debug["rag_result_type"] = "dict"
        result["debug"] = debug
        return result

    return {
        "answer": FALLBACK_ANSWER,
        "intent": "knowledge_qa",
        "safety_level": "normal",
        "found": False,
        "sources": [],
        "rag_called": True,
        "route": "rag_qa",
        "debug": {"agent": "rag_evidence", "rag_result_type": type(raw).__name__},
    }
