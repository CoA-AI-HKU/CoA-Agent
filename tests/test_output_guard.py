from __future__ import annotations

from src.agents.user_facing_formatter import (
    KNOWLEDGE_FAILURE_FALLBACK,
    MEDICATION_FALLBACK,
    guard_user_facing_answer,
)


def test_tool_name_leak_is_replaced_with_safe_fallback() -> None:
    result = {
        "answer": "你可以用 handle_dementia_user_message 查資料庫",
        "sources": ["internal.md"],
        "debug": {"route": "rag_qa"},
        "found": False,
        "intent": "knowledge_qa",
        "route": "rag_qa",
        "rag_called": True,
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == KNOWLEDGE_FAILURE_FALLBACK
    assert "handle_dementia_user_message" not in guarded["answer"]
    assert "工具" not in guarded["answer"]
    assert "資料庫" not in guarded["answer"]
    assert guarded["sources"] == ["internal.md"]
    assert guarded["debug"]["output_guard_applied"] is True


def test_mcp_internal_name_is_replaced() -> None:
    result = {
        "answer": "請使用 mcp_dementia_rag_search_dementia_knowledge function",
        "sources": [],
        "debug": {},
        "intent": "knowledge_qa",
        "route": "rag_qa",
        "rag_called": False,
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == KNOWLEDGE_FAILURE_FALLBACK
    assert "mcp_dementia_rag_search_dementia_knowledge" not in guarded["answer"]
    assert "function" not in guarded["answer"]


def test_debug_chroma_text_is_replaced() -> None:
    result = {
        "answer": "RAG_DEBUG chroma_dir=/home/aine/.cache/coa-agent/chroma/ling_rag",
        "sources": [],
        "debug": {"cwd": "kept"},
        "intent": "knowledge_qa",
        "route": "rag_qa",
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == KNOWLEDGE_FAILURE_FALLBACK
    assert "RAG_DEBUG" not in guarded["answer"]
    assert "chroma" not in guarded["answer"].lower()
    assert guarded["debug"]["cwd"] == "kept"


def test_medication_leak_uses_medication_boundary() -> None:
    result = {
        "answer": "可以調用 search_dementia_knowledge 查資料庫，再看 aspirin.md",
        "sources": ["aspirin.md"],
        "debug": {},
        "intent": "knowledge_qa",
        "route": "rag_qa",
    }

    guarded = guard_user_facing_answer(result, "我有點頭疼該吃阿司匹林嗎")

    assert guarded["answer"] == MEDICATION_FALLBACK
    assert "search_dementia_knowledge" not in guarded["answer"]
    assert ".md" not in guarded["answer"]
    assert guarded["sources"] == ["aspirin.md"]


def test_clean_answer_is_not_changed() -> None:
    result = {
        "answer": "可以先休息一下，慢慢告訴我你想問的事情。",
        "sources": [],
        "debug": {"existing": True},
        "intent": "unknown",
        "route": "unknown",
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == result["answer"]
    assert guarded["debug"] == {"existing": True}
