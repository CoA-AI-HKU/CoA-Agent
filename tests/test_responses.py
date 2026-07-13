
from __future__ import annotations

import pytest

from src.pipeline.language import detect_answer_language


def test_detect_answer_language_for_supported_inputs() -> None:
    assert detect_answer_language("腦退化症有什麼症狀？") == "zh-Hant"
    assert detect_answer_language("脑退化症有什么症状？") == "zh-Hans"
    assert detect_answer_language("What are dementia symptoms?") == "en"


def test_detect_answer_language_defaults_ambiguous_chinese_to_traditional() -> None:
    assert detect_answer_language("媽媽走失了") == "zh-Hant"


def test_detect_answer_language_accepts_override() -> None:
    assert detect_answer_language("What are dementia symptoms?", "zh-Hans") == "zh-Hans"


def test_detect_answer_language_rejects_unknown_override() -> None:
    with pytest.raises(ValueError):
        detect_answer_language("hello", "fr")


# User-facing response formatting

from src.agents.user_facing_formatter import format_user_facing_answer
from src.orchestrator import handle_dementia_user_message


SOURCE_HEAVY_MEDICATION_ANSWER = """資料庫冇提到阿司匹林，所以我冇辦法話你知食唔食得。

資料庫嘅指引係清楚嘅：

「使用非處方藥物、保健食品、營養補充劑和中成藥前，請諮詢醫護人員或藥劑師」
（來源：dementia-medications-358f15bdfa.md）

「切勿自行購買藥物服用，以免出現不良的藥物反應」
（來源：what-is-dementia-2135bc8c1d.md）

請打電話問醫生或藥劑師，唔好自己決定食。"""


def _assert_no_source_dump(answer: str) -> None:
    blocked = [
        "根據資料庫",
        "根據文件",
        "來源",
        ".md",
        "資料庫提到",
        "資料庫嘅指引",
        "文件嘅指引",
        "source:",
    ]
    for phrase in blocked:
        assert phrase not in answer


def test_sources_are_removed_from_final_answer() -> None:
    result = {
        "answer": SOURCE_HEAVY_MEDICATION_ANSWER,
        "answer_with_sources": SOURCE_HEAVY_MEDICATION_ANSWER,
        "sources": ["dementia-medications-358f15bdfa.md", "what-is-dementia-2135bc8c1d.md"],
        "found": True,
        "debug": {"retrieved_count": 2},
        "rag_called": True,
    }

    formatted = format_user_facing_answer(result)

    _assert_no_source_dump(formatted["answer"])
    _assert_no_source_dump(formatted["answer_with_sources"])
    assert formatted["answer_with_sources"] == formatted["answer"]
    assert formatted["sources"] == ["dementia-medications-358f15bdfa.md", "what-is-dementia-2135bc8c1d.md"]
    assert formatted["found"] is True
    assert formatted["debug"]["retrieved_count"] == 2
    assert formatted["debug"]["raw_answer_before_formatting"] == SOURCE_HEAVY_MEDICATION_ANSWER


def test_sources_requested_are_metadata_not_answer_filenames() -> None:
    result = {
        "answer": "這是簡短回答。",
        "sources": ["abc.md"],
        "found": True,
        "debug": {},
        "rag_called": True,
    }

    formatted = format_user_facing_answer(result, show_sources=True)

    assert formatted["sources"] == ["abc.md"]
    assert formatted["sources_available"] is True
    assert formatted["source_count"] == 1
    assert ".md" not in formatted["answer"]
    assert "來源" not in formatted["answer"]
    assert ".md" not in formatted["answer_with_sources"]
    assert "來源" not in formatted["answer_with_sources"]


def test_aspirin_answer_is_short_and_no_sources() -> None:
    result = {
        "answer": SOURCE_HEAVY_MEDICATION_ANSWER,
        "answer_with_sources": SOURCE_HEAVY_MEDICATION_ANSWER,
        "sources": ["dementia-medications-358f15bdfa.md"],
        "found": True,
        "debug": {"user_message": "我有點頭疼該吃阿司匹林嗎？"},
        "rag_called": True,
        "route": "rag_qa",
    }

    formatted = format_user_facing_answer(result)

    assert "不能判斷你是否適合吃阿司匹林" in formatted["answer"]
    assert "醫生或藥劑師" in formatted["answer"]
    _assert_no_source_dump(formatted["answer"])
    assert "資料庫" not in formatted["answer"]
    assert len(formatted["answer"]) <= 250


def test_orchestrator_final_output_uses_formatter(monkeypatch) -> None:
    def fake_answer_question(message, config):
        return {
            "answer": "根據資料庫嘅資料，腦退化症會影響日常生活。\n\n「引用內容」\n（來源：abc.md）",
            "answer_with_sources": "根據資料庫嘅資料，腦退化症會影響日常生活。\n\n來源：abc.md",
            "sources": ["abc.md"],
            "found": True,
            "debug": {"retrieved_count": 1},
        }

    monkeypatch.setattr("src.agents.rag_evidence_agent.answer_question", fake_answer_question)

    result = handle_dementia_user_message("腦退化症是什麼？")

    _assert_no_source_dump(result["answer"])
    _assert_no_source_dump(result["answer_with_sources"])
    assert result["sources"] == ["abc.md"]
    assert result["debug"]["raw_answer_before_formatting"]


def test_wandering_answer_is_concise_and_has_no_source_filename() -> None:
    result = handle_dementia_user_message("媽媽走失了怎麼辦？")

    assert "報警" in result["answer"] or "緊急" in result["answer"]
    assert "近照" in result["answer"] or "衣著" in result["answer"]
    _assert_no_source_dump(result["answer"])
    assert len(result["answer"]) <= 250
    assert "sources" in result
    assert "debug" in result


def test_medication_uncertainty_answer_is_safe_and_has_no_source_dump() -> None:
    result = handle_dementia_user_message("我忘記了我有沒有吃過藥怎麼辦？")

    assert "不要自行再服一次" in result["answer"] or "不要自行补吃" in result["answer"]
    assert "照顧者" in result["answer"] or "照顾者" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    _assert_no_source_dump(result["answer"])
    assert "sources" in result
    assert "debug" in result


def test_aspirin_question_boundary_has_warning_signs_and_no_source_dump() -> None:
    result = handle_dementia_user_message("我有點頭疼該吃阿司匹林嗎？")

    assert "不能判斷" in result["answer"] or "不能判断" in result["answer"]
    assert "醫生" in result["answer"] or "医生" in result["answer"]
    assert "藥劑師" in result["answer"] or "药剂师" in result["answer"]
    assert "立即求醫" in result["answer"] or "立即求医" in result["answer"]
    assert "可以吃阿司匹林" not in result["answer"]
    assert "不可以吃阿司匹林" not in result["answer"]
    _assert_no_source_dump(result["answer"])


# Output leakage guards

from src.agents.user_facing_formatter import (
    KNOWLEDGE_FAILURE_FALLBACK,
    MEDICATION_FALLBACK,
    SELF_MEMORY_CONCERN_FALLBACK,
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


def test_real_source_and_rag_terms_are_replaced() -> None:
    result = {
        "answer": "根據資料庫，請查看 RAG_DEBUG 來源：care-plan.md",
        "sources": ["care-plan.md"],
        "debug": {},
        "intent": "knowledge_qa",
        "route": "rag_qa",
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == KNOWLEDGE_FAILURE_FALLBACK
    assert "根據資料庫" not in guarded["answer"]
    assert "RAG" not in guarded["answer"]
    assert "來源" not in guarded["answer"]
    assert ".md" not in guarded["answer"]


def test_real_tool_and_mcp_terms_are_replaced() -> None:
    result = {
        "answer": "我會呼叫工具 handle_incoming_message，再用 MCP tool 回覆。",
        "sources": [],
        "debug": {},
        "intent": "knowledge_qa",
        "route": "rag_qa",
    }

    guarded = guard_user_facing_answer(result)

    assert guarded["answer"] == KNOWLEDGE_FAILURE_FALLBACK
    assert "handle_incoming_message" not in guarded["answer"]
    assert "MCP" not in guarded["answer"]
    assert "工具" not in guarded["answer"]


def test_memory_concern_leak_uses_neutral_memory_fallback() -> None:
    result = {
        "answer": "資料庫講到，記性變差係腦退化症好常見，呢個係腦退化症嘅一部分。",
        "sources": ["dementia.md"],
        "debug": {},
        "intent": "self_memory_concern",
        "route": "self_memory_concern",
    }

    guarded = guard_user_facing_answer(result, "最近覺得很多事情好像都有點記不住")

    assert guarded["answer"] == SELF_MEMORY_CONCERN_FALLBACK
    assert "資料庫" not in guarded["answer"]
    assert ".md" not in guarded["answer"]
    assert "腦退化症嘅一部分" not in guarded["answer"]


def test_medication_completion_has_no_citations_or_dementia_assumption() -> None:
    result = handle_dementia_user_message("已經吃過今天需要吃的藥了")

    assert result["medication_status"] == "taken"
    assert "今天已經服藥" in result["answer"]
    for blocked in ["來源", ".md", "資料庫", "腦退化", "dementia"]:
        assert blocked.lower() not in result["answer"].lower()


def test_exact_leaking_reply_is_replaced_at_final_output_guard() -> None:
    leaking_answer = """叻叻！記得準時食藥好重要 😺

資料庫提到，定時服藥同維持規律生活對腦退化症人士好有幫助。
（來源：dementia-medications-358f15bdfa.md）

繼續保持，有咩需要提你嘅話我幫手都得㗎！"""
    guarded = guard_user_facing_answer(
        {
            "answer": leaking_answer,
            "route": "medical_boundary",
            "intent": "medication_or_diagnosis",
            "safety_level": "medical_boundary",
            "sources": ["dementia-medications-358f15bdfa.md"],
        },
        "已經吃過今天需要吃的藥了",
    )

    for blocked in ["來源", ".md", "資料庫", "腦退化", "dementia"]:
        assert blocked.lower() not in guarded["answer"].lower()
    assert guarded["debug"]["unsupported_dementia_assumption_removed"] is True


def test_production_mcp_result_excludes_internal_source_and_debug_fields(monkeypatch) -> None:
    from src.dementia_rag_mcp_server import handle_incoming_message_tool

    monkeypatch.setattr(
        "src.dementia_rag_mcp_server.handle_incoming_message",
        lambda message, sender_id, channel: {
            "answer": "安全回答",
            "route": "supportive",
            "intent": "unknown",
            "sources": ["private-source.md"],
            "debug": {"raw_answer_before_formatting": "來源：private-source.md"},
            "answer_with_sources": "安全回答（來源：private-source.md）",
        },
    )

    result = handle_incoming_message_tool("你好", "user_1", "telegram")

    assert result == {"answer": "安全回答", "route": "supportive", "intent": "unknown"}
