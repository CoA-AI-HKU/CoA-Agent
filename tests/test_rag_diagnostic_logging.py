from __future__ import annotations

import logging

from src.citations import finalize_user_facing_result
from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore
from src.user.message_router import _finalize_user_output


def _agent() -> RagAgent:
    agent = RagAgent(
        embedder=Embedder(provider="dummy"),
        vector_store=InMemoryVectorStore(),
        min_relevance_score=0.0,
    )
    agent.index_documents([
        Document(
            text="腦退化症可能影響記憶、思考和處理日常活動的能力。",
            metadata={"source": "definition.md", "heading": "腦退化症"},
        )
    ])
    return agent


def test_generation_diagnostics_do_not_change_answer(caplog) -> None:
    caplog.set_level(logging.INFO)
    expected = "這是測試回答。"

    result = _agent().answer_question("腦退化症有什麼影響？", answer_callable=lambda prompt: expected)

    assert result["answer"] == expected
    assert "event=retrieval_completed" in caplog.text
    assert "event=answer_callable_started" in caplog.text
    assert "event=answer_callable_completed" in caplog.text
    assert expected in caplog.text


def test_citation_diagnostics_do_not_change_finalized_result(caplog) -> None:
    caplog.set_level(logging.INFO)
    original = {"answer": "安全回答", "sources": ["private.md"], "found": True}

    result = finalize_user_facing_result(original)

    assert result["answer"] == "安全回答"
    assert result["answer_with_sources"] == "安全回答"
    assert "event=citation_finalizer_started" in caplog.text
    assert "event=citation_finalizer_completed" in caplog.text


def test_router_diagnostics_do_not_change_returned_answer(caplog) -> None:
    caplog.set_level(logging.INFO)
    original = {
        "answer": "安全回答", "sources": [], "found": True,
        "debug": {"scores": [0.92, 0.91]},
    }

    result = _finalize_user_output(original, "問題")

    assert result["answer"] == "安全回答"
    assert "ROUTER_FINALIZE_START" in caplog.text
    assert "ROUTER_FINALIZE_COMPLETED" in caplog.text
