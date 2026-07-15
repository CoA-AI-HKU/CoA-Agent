from __future__ import annotations

from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore
from src.rag.agentic_retriever import agentic_retrieve


def _agent() -> RagAgent:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [
            Document(
                text="Dementia can affect memory and daily activities. Caregivers can respond to repeated questions calmly, reassure the person, and use familiar routines.",
                metadata={"source": "care.md"},
            ),
            Document(
                text="Donepezil and aspirin details must be reviewed by a doctor or pharmacist.",
                metadata={"source": "medication.md"},
            ),
        ]
    )
    return agent


def test_rag_qa_allows_all_bounded_retrieval_tools() -> None:
    result = agentic_retrieve("What can dementia affect?", "rag_qa", rag_agent=_agent())
    assert set(result["retrieval_log"]["tools_used"]) == {
        "keyword_search",
        "semantic_search",
        "chunk_read",
    }


def test_caregiver_guidance_allows_care_advice_retrieval() -> None:
    result = agentic_retrieve(
        "How should caregivers respond to repeated questions?",
        "caregiver_guidance",
        rag_agent=_agent(),
    )
    assert result["evidence"]
    assert result["retrieval_log"]["answer_used_rag"] is True


def test_medical_route_never_reads_full_medication_content() -> None:
    result = agentic_retrieve("Can I take aspirin with donepezil?", "medical_boundary", rag_agent=_agent())
    assert "chunk_read" not in result["retrieval_log"]["tools_used"]
    assert all("text" not in item for item in result["evidence"])


def test_memory_concern_uses_at_most_one_chunk() -> None:
    result = agentic_retrieve("I keep forgetting things", "memory_concern", rag_agent=_agent())
    assert len(result["evidence"]) <= 1


def test_safety_and_caregiver_summary_skip_retrieval() -> None:
    for route in ("safety", "wandering_safety", "caregiver_summary"):
        result = agentic_retrieve("summary or urgent request", route, rag_agent=_agent())
        assert result["evidence"] == []
        assert result["retrieval_log"]["tools_used"] == []

