from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterable, List

from .document import Document
from .rag_agent import RagAgent
from .vector_store import get_default_vector_store


SAFE_FALLBACK_CONTEXT = (
    "No relevant context was retrieved from the dementia knowledge base. "
    "Answer only with a transparent limitation statement and suggest consulting a qualified clinician for medical concerns."
)


def _risk_level(question: str, retrieved_docs: Iterable[Document]) -> str | None:
    combined = " ".join([question, *(doc.text for doc in retrieved_docs)]).lower()
    high_risk_terms = {
        "suicide",
        "self-harm",
        "self harm",
        "hurt myself",
        "violent",
        "violence",
        "abuse",
        "neglect",
        "emergency",
        "overdose",
        "choking",
        "wandering",
        "missing",
    }
    if any(term in combined for term in high_risk_terms):
        return "high"
    return None


def _format_sources(retrieved_docs: List[Document]) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any]] = set()
    for index, doc in enumerate(retrieved_docs, start=1):
        source = doc.metadata.get("source", "unknown")
        chunk_index = doc.metadata.get("chunk_index")
        key = (source, chunk_index)
        if key in seen:
            continue
        seen.add(key)
        sources.append(
            {
                "source": source,
                "chunk_index": chunk_index,
                "rank": index,
            }
        )
    return sources


def _build_context(retrieved_docs: List[Document], max_context_chars: int, per_chunk_chars: int) -> str:
    parts: list[str] = []
    total = 0
    for doc in retrieved_docs:
        text = doc.text or ""
        if len(text) > per_chunk_chars:
            text = text[:per_chunk_chars].rstrip() + "..."
        entry = f"Source: {doc.metadata.get('source', 'unknown')}\n{text}"
        if total + len(entry) > max_context_chars and parts:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


def _format_search_response(
    question: str,
    retrieved_docs: List[Document],
    max_context_chars: int = 3000,
    per_chunk_chars: int = 1000,
) -> dict[str, Any]:
    if not retrieved_docs:
        return {
            "context": SAFE_FALLBACK_CONTEXT,
            "sources": [],
            "risk_level": _risk_level(question, []),
        }

    return {
        "context": _build_context(retrieved_docs, max_context_chars, per_chunk_chars),
        "sources": _format_sources(retrieved_docs),
        "risk_level": _risk_level(question, retrieved_docs),
    }


def search_dementia_knowledge(question: str) -> dict[str, Any]:
    """Retrieve dementia knowledge-base context without calling a generation model."""
    if not question or not question.strip():
        return {
            "context": SAFE_FALLBACK_CONTEXT,
            "sources": [],
            "risk_level": None,
        }

    persist_dir = Path(os.getenv("CHROMA_DIR", ".chroma/ling_rag"))
    collection_name = os.getenv("CHROMA_COLLECTION", "ling_rag")
    embedder_provider = os.getenv("EMBEDDER_PROVIDER", "auto")
    embedder_model = os.getenv("EMBEDDER_MODEL") or None
    offline_embeddings = os.getenv("EMBEDDINGS_OFFLINE", "").lower() in {"1", "true", "yes"}
    top_k = int(os.getenv("RAG_TOP_K", "5"))
    max_context_chars = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "3000"))
    per_chunk_chars = int(os.getenv("RAG_PER_CHUNK_CHARS", "1000"))

    vector_store = get_default_vector_store(
        persist_directory=persist_dir,
        collection_name=collection_name,
    )
    agent = RagAgent(
        embedder_provider=embedder_provider,
        embedder_model_name=embedder_model,
        offline_embeddings=offline_embeddings,
        vector_store=vector_store,
        top_k=top_k,
        max_context_chars=max_context_chars,
        per_chunk_chars=per_chunk_chars,
    )
    retrieved_docs = agent.retrieve(question, k=top_k)
    return _format_search_response(
        question,
        retrieved_docs,
        max_context_chars=max_context_chars,
        per_chunk_chars=per_chunk_chars,
    )
