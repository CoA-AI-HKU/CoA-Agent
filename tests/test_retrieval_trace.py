from __future__ import annotations

from src.agents.user_facing_formatter import guard_user_facing_answer
from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import RagAgent
from src.pipeline.vector_store import InMemoryVectorStore
from src.rag.agentic_retriever import agentic_retrieve


TRACE_FIELDS = {
    "route",
    "tools_used",
    "keyword_queries",
    "semantic_queries",
    "chunks_read",
    "evidence_sufficient",
    "retrieval_failed",
    "answer_used_rag",
}


def test_retrieval_trace_is_complete_but_not_user_visible() -> None:
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(
        [Document(text="Dementia can affect memory, thinking, and daily activities.", metadata={"source": "overview.md"})]
    )
    retrieval = agentic_retrieve("What can dementia affect?", "rag_qa", rag_agent=agent)
    trace = retrieval["retrieval_log"]
    assert TRACE_FIELDS <= trace.keys()

    result = guard_user_facing_answer(
        {
            "answer": "Dementia can affect memory, thinking, and daily activities.",
            "route": "rag_qa",
            "intent": "knowledge_qa",
            "debug": {"retrieval": trace},
        },
        "What can dementia affect?",
    )
    assert not any(field in result["answer"] for field in TRACE_FIELDS)

