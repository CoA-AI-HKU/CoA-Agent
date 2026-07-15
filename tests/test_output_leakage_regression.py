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

