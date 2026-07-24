from __future__ import annotations

import pytest

from src.agents.user_facing_formatter import answer_has_user_visible_leakage, guard_user_facing_answer


@pytest.mark.parametrize(
    "leak",
    [
        "private.md",
        "source: private notes",
        "來源：內部文件",
        "根據資料庫",
        "keyword_search",
        "semantic_search",
        "chunk_read",
        "MCP",
        "mcp_tool",
        "Chroma",
        "vector index",
        "debug details",
        "traceback follows",
        "/mnt/private/index",
        r"C:\\Users\\private\\index",
    ],
)
def test_production_output_guard_removes_internal_leakage(leak: str) -> None:
    result = guard_user_facing_answer(
        {
            "answer": f"Helpful answer. {leak}",
            "route": "rag_qa",
            "intent": "knowledge_qa",
            "sources": [],
            "debug": {},
        },
        "腦退化症是什麼？",
    )

    assert not answer_has_user_visible_leakage(result["answer"])
    assert leak.casefold() not in result["answer"].casefold()


@pytest.mark.parametrize(
    "answer",
    [
        "腦退化症是一種會影響記憶和思考能力的疾病。",
        "患者可能出現記憶力下降和判斷力改變。",
        "腦退化症並不是正常老化的一部分。",
        "腦退化症會影響記憶、語言及日常生活能力。",
        "腦退化症人士可能需要不同程度的支援。",
        "根據研究，患者可能出現語言能力改變。",
    ],
)
def test_general_dementia_education_is_allowed(answer: str) -> None:
    result = guard_user_facing_answer(
        {"answer": answer, "route": "rag_qa", "intent": "knowledge_qa", "debug": {}},
        "腦退化症是什麼？",
    )

    assert result["answer"] == answer
    assert result.get("debug") == {}


@pytest.mark.parametrize(
    "answer",
    [
        "你患有腦退化症。",
        "你的症狀證明你有失智症。",
        "你有腦退化症。",
    ],
)
def test_unsupported_direct_user_diagnosis_is_blocked(answer: str) -> None:
    result = guard_user_facing_answer(
        {"answer": answer, "route": "rag_qa", "intent": "knowledge_qa", "debug": {}},
        "最近有點健忘，怎麼辦？",
    )

    assert result["answer"] != answer
    assert result["debug"]["unsupported_dementia_assumption_removed"] is True


@pytest.mark.parametrize(
    "leak",
    ["/home/private/chroma/index", "Chroma", "MCP", "RAG", "private.md", "debug output"],
)
def test_required_internal_markers_remain_blocked(leak: str) -> None:
    answer = f"正常回答 {leak}"
    result = guard_user_facing_answer(
        {"answer": answer, "route": "rag_qa", "intent": "knowledge_qa", "debug": {}},
        "腦退化症是什麼？",
    )

    assert result["answer"] != answer
    assert result["debug"]["internal_leakage_removed"] is True


def test_output_guard_structured_logging_does_not_change_allowed_answer(caplog) -> None:
    answer = "腦退化症並不是正常老化的一部分。"

    with caplog.at_level("INFO"):
        result = guard_user_facing_answer(
            {"answer": answer, "route": "rag_qa", "intent": "knowledge_qa", "debug": {}},
            "腦退化症是什麼？",
        )

    assert result["answer"] == answer
    assert "has_internal_leakage=False" in caplog.text
    assert "has_unsupported_dementia_assumption=False" in caplog.text
    assert "fallback_reason=none" in caplog.text


def test_output_guard_replacement_log_contains_lengths_and_reason(caplog) -> None:
    answer = "你患有腦退化症。"

    with caplog.at_level("INFO"):
        result = guard_user_facing_answer(
            {"answer": answer, "route": "rag_qa", "intent": "knowledge_qa", "debug": {}},
            "最近有點健忘。",
        )

    assert result["answer"] != answer
    assert "fallback_reason=unsupported_dementia_assumption" in caplog.text
    assert "before_length=" in caplog.text
    assert "after_length=" in caplog.text
    assert "safe_answer_preview=" in caplog.text
