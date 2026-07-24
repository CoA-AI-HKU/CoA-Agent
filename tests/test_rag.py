from __future__ import annotations

# Core RAG configuration, retrieval, and answering

import re

import pytest

from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.prompts import FALLBACK_ANSWER_EN, FALLBACK_ANSWER_ZH_HANS
from src.pipeline.rag_agent import DEFAULT_CHROMA_DIR, PROJECT_ROOT, RagAgent, build_default_rag_config
from src.pipeline.vector_store import InMemoryVectorStore, get_default_vector_store


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def test_answer_question_returns_concise_grounded_answer() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Computational linguistics is the scientific and engineering discipline concerned with written and spoken language.",
                metadata={"source": "Introducing_computational_linguistics.md"},
            )
        ]
    )

    result = agent.answer_question("What is computational linguistics?")

    assert result["found"] is True
    assert "scientific" in result["answer"].lower()
    assert "engineering" in result["answer"].lower()
    assert "language" in result["answer"].lower()
    assert "Sources: Introducing_computational_linguistics.md" in result["answer_with_sources"]
    assert result["sources"] == ["Introducing_computational_linguistics.md"]
    assert result["debug"]["answer_language"] == "en"
    assert _sentence_count(result["answer"]) <= 3


def test_answer_question_falls_back_for_unrelated_question() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Dementia caregivers can respond with a calm voice and reassurance.",
                metadata={"source": "dementia.md"},
            )
        ]
    )

    result = agent.answer_question("What is the capital of France?")

    assert result["found"] is False
    assert result["answer"] == FALLBACK_ANSWER_EN
    assert result["sources"] == []


def test_simplified_question_uses_simplified_fallback_and_source_label() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="脑退化症照顾者可以用平静的语气回应，并用简单句子安抚患者，帮助患者慢慢理解眼前的情况。",
                metadata={"source": "dementia_cn.md"},
            )
        ]
    )

    result = agent.answer_question("脑退化症照顾者可以怎样回应？")

    assert result["debug"]["answer_language"] == "zh-Hans"
    assert "资料来源：dementia_cn.md" in result["answer_with_sources"]

    fallback = agent.answer_question("法国首都是什么？")
    assert fallback["answer"] == FALLBACK_ANSWER_ZH_HANS


def test_fake_answer_callable_receives_cross_language_prompt() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="腦退化症可能影響記憶、思考和日常生活。",
                metadata={"source": "dementia_hk.md"},
            )
        ]
    )

    def fake_answer(prompt: str) -> str:
        assert "Answer only in English." in prompt
        assert "Traditional Chinese, Simplified Chinese, or English" in prompt
        return "Dementia may affect memory, thinking, and daily life."

    result = agent.answer_question("What can dementia affect?", answer_callable=fake_answer)

    assert result["answer"] == "Dementia may affect memory, thinking, and daily life."
    assert result["debug"]["answer_language"] == "en"

def test_default_chroma_dir_uses_writable_cache_path(monkeypatch) -> None:
    monkeypatch.delenv("CHROMA_DIR", raising=False)

    config = build_default_rag_config("mcp")

    assert str(config["chroma_dir"]).replace("\\", "/") == DEFAULT_CHROMA_DIR


def test_chroma_dir_env_override_is_used(monkeypatch, tmp_path) -> None:
    chroma_dir = tmp_path / "chroma" / "ling_rag"
    monkeypatch.setenv("CHROMA_DIR", str(chroma_dir))

    config = build_default_rag_config("mcp")

    assert config["chroma_dir"] == chroma_dir


def test_relative_chroma_dir_still_resolves_under_project(monkeypatch) -> None:
    monkeypatch.setenv("CHROMA_DIR", ".chroma/ling_rag")

    config = build_default_rag_config("mcp")

    assert config["chroma_dir"] == PROJECT_ROOT / ".chroma/ling_rag"

def test_expected_source_is_retrieved() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Computational linguistics is a scientific and engineering field about language.",
                metadata={"source": "Introducing_computational_linguistics.md"},
            ),
            Document(text="Caregivers can keep a calm tone.", metadata={"source": "dementia.md"}),
        ]
    )

    retrieved = agent.retrieve("What is computational linguistics?", k=8)

    assert retrieved
    assert retrieved[0].metadata["source"] == "Introducing_computational_linguistics.md"


def test_no_chunks_found_does_not_crash() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())

    result = agent.answer_question("What is missing?")

    assert result["found"] is False
    assert result["sources"] == []

def test_chroma_vector_store_add_and_query(tmp_path: Path) -> None:
    store = get_default_vector_store(persist_directory=tmp_path / "chroma_store", collection_name="vector_store_test")
    documents = [
        Document(text="A short document about linguistics.", metadata={"source": "one.md"}),
        Document(text="A second document about computational linguistics.", metadata={"source": "two.md"}),
    ]
    embeddings = [[0.1] * 384, [0.2] * 384]

    store.add_documents(documents, embeddings)
    results = store.query("computational linguistics", n_results=1, query_embedding=[0.2] * 384)

    assert len(results) == 1
    assert results[0]["metadata"]["source"] == "two.md"


# Dementia RAG and MCP integration

from src.dementia_rag import SAFE_FALLBACK_CONTEXT, _format_search_response
from src.dementia_rag_mcp_server import answer_from_dementia_knowledge_tool, search_dementia_knowledge_tool
from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore


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



def test_required_persistent_store_does_not_silently_fallback(monkeypatch, tmp_path) -> None:
    import src.pipeline.vector_store as vector_store_module

    def unavailable_chroma(*args, **kwargs):
        raise ImportError("chromadb unavailable")

    monkeypatch.setattr(vector_store_module, "ChromaVectorStore", unavailable_chroma)

    with pytest.raises(RuntimeError, match="Persistent Chroma storage is unavailable"):
        vector_store_module.get_default_vector_store(
            persist_directory=tmp_path / "chroma",
            require_persistent=True,
        )

    fallback = vector_store_module.get_default_vector_store(persist_directory=tmp_path / "chroma")
    assert isinstance(fallback, InMemoryVectorStore)
