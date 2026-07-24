from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, List

from .intent_router import classify_intent
from .pipeline.chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from .pipeline.document import Document
from .pipeline.markdown_loader import load_markdown_documents
from .pipeline.prompts import FALLBACK_ANSWER
from .pipeline.rag_agent import (
    DEFAULT_CHROMA_DIR,
    RagAgent,
    answer_question as shared_answer_question,
    build_default_rag_config,
    get_runtime_agent,
)
from .pipeline.vector_store import get_default_vector_store
from .rag.runtime_config import load_rag_config


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_FALLBACK_CONTEXT = (
    "No relevant context was retrieved from the dementia knowledge base. "
    "Answer only with a transparent limitation statement and suggest consulting a qualified clinician for medical concerns."
)


def _debug(message: str) -> None:
    if os.getenv("RAG_DEBUG", "").lower() in {"1", "true", "yes"}:
        print(f"DEBUG: {message}", file=sys.stderr)


def _resolve_project_path(path_value: str | Path) -> Path:
    raw_path = str(path_value)
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    if raw_path.startswith("/"):
        return path
    return PROJECT_ROOT / path


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
            "found": False,
            "risk_level": _risk_level(question, []),
            "debug": {"retrieved_count": 0, "best_score": 0.0},
        }

    scores = [doc.metadata.get("relevance_score", doc.metadata.get("distance")) for doc in retrieved_docs]
    return {
        "context": _build_context(retrieved_docs, max_context_chars, per_chunk_chars),
        "sources": _format_sources(retrieved_docs),
        "found": True,
        "risk_level": _risk_level(question, retrieved_docs),
        "debug": {
            "retrieved_count": len(retrieved_docs),
            "scores": scores,
            "best_score": scores[0] if scores else None,
        },
    }


def _build_runtime_agent() -> RagAgent:
    return get_runtime_agent(load_rag_config("mcp"))


def _ensure_runtime_index(
    agent: RagAgent,
    data_dir: Path,
    persist_dir: Path,
    embedder_model: str | None,
    offline_embeddings: bool,
) -> None:
    if os.getenv("RAG_AUTO_INDEX", "1").lower() not in {"1", "true", "yes"}:
        return
    if agent.vector_store is None:
        return
    docs = load_markdown_documents(data_dir)
    if not docs:
        _debug(f"no markdown documents found under {data_dir}")
        return

    manifest_path = persist_dir / "index_manifest.json"
    current_manifest = _runtime_index_manifest(docs, agent, embedder_model)
    saved_manifest = _load_runtime_manifest(manifest_path)
    manifest_changed = saved_manifest != current_manifest

    try:
        if agent.vector_store.count() > 0 and not manifest_changed:
            return
    except Exception as exc:
        _debug(f"could not read vector store count; rebuilding index: {exc}")

    _debug(f"runtime index is empty or stale; indexing {len(docs)} markdown document(s) from {data_dir}")
    try:
        if hasattr(agent.vector_store, "clear"):
            agent.vector_store.clear()
        agent.index_documents(docs)
        _save_runtime_manifest(manifest_path, current_manifest)
    except RuntimeError as exc:
        config = load_rag_config("mcp")
        if (
            agent.embedder_provider != "auto"
            or not config["allow_dummy"]
            or config["rag_env"] == "production"
            or "No real embedding backend is available" not in str(exc)
        ):
            raise
        _debug("explicit dummy fallback enabled; rebuilding runtime index with dummy embedder")
        vector_store = agent.vector_store
        if hasattr(vector_store, "clear"):
            vector_store.clear()
        agent._embedder = None
        agent.embedder_provider = "dummy"
        agent.embedder_model_name = embedder_model
        agent.offline_embeddings = offline_embeddings
        agent.index_documents(docs)
        _save_runtime_manifest(manifest_path, _runtime_index_manifest(docs, agent, embedder_model))


def _runtime_index_manifest(docs: List[Document], agent: RagAgent, embedder_model: str | None) -> dict[str, Any]:
    document_entries = []
    for document in docs:
        source = str(document.metadata.get("source", ""))
        text_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
        document_entries.append({"source": source, "sha256": text_hash, "chars": len(document.text)})
    return {
        "schema_version": 2,
        "documents": sorted(document_entries, key=lambda item: item["source"]),
        "chunk_size": agent.chunk_size,
        "chunk_overlap": agent.chunk_overlap,
        "embedder_provider": agent.embedder_provider,
        "embedder_model": embedder_model or "all-MiniLM-L6-v2",
    }


def _load_runtime_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_runtime_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _extract_model_text(data: dict[str, Any]) -> str:
    if data.get("answer"):
        return str(data["answer"])
    if data.get("text"):
        return str(data["text"])
    choices = data.get("choices") or []
    if choices:
        first_choice = choices[0]
        message = first_choice.get("message") or {}
        if message.get("content"):
            return str(message["content"])
        if first_choice.get("text"):
            return str(first_choice["text"])
    return ""


def create_chat_answer():
    """Compatibility wrapper around the canonical provider-aware generator."""
    from .pipeline.rag_agent import create_chat_answer as build_chat_answer

    return build_chat_answer(load_rag_config("mcp"))


def search_dementia_knowledge(question: str) -> dict[str, Any]:
    """Compatibility wrapper returning the context selected by the shared answer pipeline."""
    _debug(f"search_dementia_knowledge called with question={question!r}")
    intent_result = classify_intent(question)
    if not question or not question.strip():
        return {
            "context": SAFE_FALLBACK_CONTEXT,
            "sources": [],
            "found": False,
            "risk_level": None,
            "intent": intent_result.intent,
            "intent_debug": {
                "confidence": intent_result.confidence,
                "matched_terms": intent_result.matched_terms,
                "reason": intent_result.reason,
            },
            "debug": {
                "retrieved_count": 0,
                "best_score": 0.0,
                "intent": intent_result.intent,
                "intent_debug": {
                    "confidence": intent_result.confidence,
                    "matched_terms": intent_result.matched_terms,
                    "reason": intent_result.reason,
                },
            },
        }

    answer_result = shared_answer_question(question, build_default_rag_config("mcp"))
    intent_debug = answer_result.get("intent_debug", {})
    boundary_handler = answer_result.get("debug", {}).get("boundary_handler")
    risk_level = "high" if boundary_handler == "safety_sensitive" else _risk_level(question, [])
    result = {
        "context": answer_result.get("answer")
        if boundary_handler
        else answer_result.get("context_used") or SAFE_FALLBACK_CONTEXT,
        "sources": answer_result.get("sources", []),
        "found": bool(answer_result.get("found")),
        "risk_level": risk_level,
        "intent": answer_result.get("intent", intent_result.intent),
        "intent_debug": intent_debug,
        "debug": answer_result.get("debug", {}),
    }
    _debug(f"retrieved_count={result.get('debug', {}).get('retrieved_count')}")
    _debug(f"sources={result.get('sources', [])}")
    return result


def answer_from_dementia_knowledge(question: str) -> dict[str, Any]:
    """Retrieve context and generate a concise grounded answer."""
    _debug(f"answer_from_dementia_knowledge called with question={question!r}")
    if not question or not question.strip():
        return {
            "found": False,
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "context_used": "",
            "debug": {"retrieved_count": 0, "best_score": 0.0},
        }

    result = shared_answer_question(question, build_default_rag_config("mcp"))
    debug = result.get("debug", {})
    _debug(f"retrieve_top_k={debug.get('top_k_retrieved')}")
    _debug(f"retrieved_count={debug.get('retrieved_count')}")
    _debug(f"best_score={debug.get('best_score')}")
    _debug(f"sources={result.get('sources', [])}")
    _debug(f"answer={str(result.get('answer', ''))[:300]!r}")
    return result
