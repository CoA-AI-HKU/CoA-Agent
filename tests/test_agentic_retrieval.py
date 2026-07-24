from __future__ import annotations

from src.agents.user_facing_formatter import guard_user_facing_answer
from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore
from src.rag.agentic_retriever import agentic_retrieve, evidence_sufficiency_check
from src.rag.retrieval_tools import chunk_read, keyword_search, semantic_search


def _agent(*documents: Document) -> RagAgent:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(list(documents))
    return agent


def test_keyword_search_returns_snippet_not_full_chunk() -> None:
    full_text = "Donepezil may cause nausea or headache. " + ("private trailing detail " * 40)
    agent = _agent(Document(text=full_text, metadata={"source": "medications.md", "title": "Medicines"}))

    results = keyword_search(["donepezil"], vector_store=agent.vector_store)

    assert results
    assert results[0]["chunk_id"]
    assert results[0]["source_title"] == "Medicines"
    assert "Donepezil" in results[0]["snippet"]
    assert results[0]["snippet"] != full_text
    assert "text" not in results[0]


def test_semantic_search_returns_relevant_chunk_id_without_full_text() -> None:
    agent = _agent(
        Document(text="Caregivers can reduce distress by using a calm voice and familiar routine.", metadata={"source": "care.md"}),
        Document(text="Balanced meals include vegetables and grains.", metadata={"source": "food.md"}),
    )

    results = semantic_search("How can caregivers reduce distress?", rag_agent=agent)

    assert results
    assert results[0]["chunk_id"]
    assert "calm voice" in results[0]["snippet"]
    assert "text" not in results[0]


def test_chunk_read_returns_only_selected_full_chunk_and_deduplicates_reads() -> None:
    agent = _agent(
        Document(text="First complete chunk about familiar routines.", metadata={"source": "care.md"}),
        Document(text="Second complete chunk about safe home design.", metadata={"source": "home.md"}),
    )
    matches = keyword_search(["familiar", "safe"], top_k=5, vector_store=agent.vector_store)
    selected_id = next(item["chunk_id"] for item in matches if "familiar" in item["snippet"])
    tracker = {"read_chunks": set()}

    first = chunk_read([selected_id], tracker, vector_store=agent.vector_store)
    second = chunk_read([selected_id], tracker, vector_store=agent.vector_store)

    assert first == [
        {
            "chunk_id": selected_id,
            "source_title": "care",
            "text": "First complete chunk about familiar routines.",
            "metadata": first[0]["metadata"],
        }
    ]
    assert "safe home design" not in first[0]["text"]
    assert second == []
    assert selected_id in tracker["read_chunks"]


def test_agentic_retrieve_reads_bounded_evidence_for_knowledge_route() -> None:
    agent = _agent(
        Document(text="Dementia can affect memory, thinking, and daily activities.", metadata={"source": "overview.md"}),
        Document(text="Care plans can use familiar routines and calm communication.", metadata={"source": "care.md"}),
    )

    result = agentic_retrieve("What can dementia affect?", "dementia_qa", rag_agent=agent)

    assert result["sufficiency"]["sufficient"] is True
    assert 1 <= len(result["evidence"]) <= 3
    assert result["retrieval_log"]["chunks_read"]
    assert result["retrieval_log"]["answer_used_rag"] is True


def test_route_policies_retrieve_for_urgent_and_unknown_messages() -> None:
    agent = _agent(Document(text="If someone is missing, act immediately.", metadata={"source": "safety.md"}))

    wandering = agentic_retrieve("My family member is missing", "wandering_safety", rag_agent=agent)
    unknown = agentic_retrieve("Tell me the weather", "unknown", rag_agent=agent)

    assert wandering["retrieval_log"]["requires_retrieval"] is True
    assert wandering["retrieval_log"]["tools_used"]
    assert unknown["retrieval_log"]["requires_retrieval"] is True
    assert unknown["retrieval_log"]["tools_used"]


def test_medication_route_never_reads_full_chunks() -> None:
    agent = _agent(Document(text="Donepezil dosage information must be reviewed by a clinician.", metadata={"source": "meds.md"}))

    result = agentic_retrieve("Can I stop donepezil?", "medication_or_diagnosis", rag_agent=agent)

    assert "chunk_read" not in result["retrieval_log"]["tools_used"]
    assert all("text" not in item for item in result["evidence"])


def test_insufficient_evidence_blocks_unrelated_answer() -> None:
    check = evidence_sufficiency_check(
        "What support helps with dementia care?",
        [{"chunk_id": "x", "snippet": "Paris is the capital of France.", "score": 0.1}],
    )

    assert check["sufficient"] is False
    assert check["supporting_chunk_ids"] == []


def test_rag_answer_exposes_internal_retrieval_log_only_in_debug() -> None:
    agent = _agent(Document(text="Dementia may affect memory and everyday activities.", metadata={"source": "overview.md"}))

    result = agent.answer_question("What can dementia affect?")

    assert result["found"] is True
    assert result["debug"]["retrieval"]["evidence_sufficient"] is True
    for blocked in ("keyword_search", "semantic_search", "chunk_read", ".md", "debug"):
        assert blocked not in result["answer"]


def test_output_guard_blocks_agentic_retrieval_names() -> None:
    guarded = guard_user_facing_answer(
        {
            "answer": "semantic_search used chunk_read on private-source.md",
            "route": "rag_qa",
            "intent": "knowledge_qa",
            "sources": ["private-source.md"],
            "debug": {},
        }
    )

    for blocked in ("semantic_search", "chunk_read", ".md", "debug"):
        assert blocked not in guarded["answer"]
