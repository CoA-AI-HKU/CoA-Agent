from __future__ import annotations

from src.dementia_rag import SAFE_FALLBACK_CONTEXT, _format_search_response
from src.dementia_rag_mcp_server import answer_from_dementia_knowledge_tool, search_dementia_knowledge_tool
from src.document import Document
from src.embedder import Embedder
from src.rag_agent import RagAgent
from src.vector_store import InMemoryVectorStore


def test_retrieval_response_returns_expected_chunk() -> None:
    documents = [
        Document(
            text="Dementia care plans should include familiar routines and caregiver support.",
            metadata={"source": "dementia.md", "chunk_index": 3},
        )
    ]
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(documents)

    retrieved = agent.retrieve("What helps dementia care?")
    result = _format_search_response("What helps dementia care?", retrieved)

    assert "familiar routines" in result["context"]
    assert result["sources"][0]["source"] == "dementia.md"


def test_mcp_tool_returns_context(monkeypatch) -> None:
    expected = {
        "context": "Source: dementia.md\nMemory support strategies include calendars.",
        "sources": [{"source": "dementia.md", "chunk_index": 1, "rank": 1}],
        "risk_level": None,
    }

    monkeypatch.setattr(
        "src.dementia_rag_mcp_server.search_dementia_knowledge",
        lambda question: expected,
    )

    result = search_dementia_knowledge_tool("What memory supports help?")

    assert result["context"] == expected["context"]
    assert result["sources"] == expected["sources"]


def test_mcp_answer_tool_returns_grounded_answer(monkeypatch) -> None:
    expected = {
        "found": True,
        "answer": "Memory support strategies include calendars.",
        "sources": ["dementia.md"],
        "context_used": "Source: dementia.md\nMemory support strategies include calendars.",
        "debug": {"best_score": 0.8},
    }

    monkeypatch.setattr(
        "src.dementia_rag_mcp_server.answer_from_dementia_knowledge",
        lambda question: expected,
    )

    result = answer_from_dementia_knowledge_tool("What memory supports help?")

    assert result["found"] is True
    assert result["answer"] == expected["answer"]


def test_empty_retrieval_returns_safe_fallback() -> None:
    result = _format_search_response("Unknown document question", [])

    assert result["context"] == SAFE_FALLBACK_CONTEXT
    assert result["sources"] == []
