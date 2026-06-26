from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, List

from .chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from .document import Document
from .markdown_loader import load_markdown_documents
from .prompts import FALLBACK_ANSWER
from .rag_agent import RagAgent, answer_question as shared_answer_question, build_default_rag_config
from .vector_store import get_default_vector_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAFE_FALLBACK_CONTEXT = (
    "No relevant context was retrieved from the dementia knowledge base. "
    "Answer only with a transparent limitation statement and suggest consulting a qualified clinician for medical concerns."
)


def _debug(message: str) -> None:
    if os.getenv("RAG_DEBUG", "").lower() in {"1", "true", "yes"}:
        print(f"DEBUG: {message}", file=sys.stderr)


def _resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
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
    persist_dir = _resolve_project_path(os.getenv("CHROMA_DIR", ".chroma/ling_rag"))
    collection_name = os.getenv("CHROMA_COLLECTION", "ling_rag")
    embedder_provider = os.getenv("EMBEDDER_PROVIDER", "dummy")
    embedder_model = os.getenv("EMBEDDER_MODEL") or None
    offline_embeddings = os.getenv("EMBEDDINGS_OFFLINE", "").lower() in {"1", "true", "yes"}
    data_dir = _resolve_project_path(os.getenv("RAG_DATA_DIR", "data/mds"))
    top_k = int(os.getenv("RAG_TOP_K", "3"))
    max_context_chars = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "1800"))
    per_chunk_chars = int(os.getenv("RAG_PER_CHUNK_CHARS", "500"))
    min_shared_query_terms = int(os.getenv("RAG_MIN_SHARED_QUERY_TERMS", "1"))
    retrieve_top_k = int(os.getenv("RAG_RETRIEVE_TOP_K", "8"))
    answer_top_k = int(os.getenv("RAG_ANSWER_TOP_K", "3"))
    min_relevance_score = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.35"))
    chunk_size = int(os.getenv("RAG_CHUNK_SIZE", str(DEFAULT_CHUNK_SIZE)))
    chunk_overlap = int(os.getenv("RAG_CHUNK_OVERLAP", str(DEFAULT_CHUNK_OVERLAP)))

    vector_store = get_default_vector_store(
        persist_directory=persist_dir,
        collection_name=collection_name,
    )
    _debug(f"using_chroma_dir={persist_dir}")
    agent = RagAgent(
        embedder_provider=embedder_provider,
        embedder_model_name=embedder_model,
        offline_embeddings=offline_embeddings,
        vector_store=vector_store,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        top_k=top_k,
        max_context_chars=max_context_chars,
        per_chunk_chars=per_chunk_chars,
        min_shared_query_terms=min_shared_query_terms,
        retrieve_top_k=retrieve_top_k,
        answer_top_k=answer_top_k,
        min_relevance_score=min_relevance_score,
    )
    _ensure_runtime_index(agent, data_dir, persist_dir, embedder_model, offline_embeddings)
    return agent


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
        if agent.embedder_provider != "auto" or "No real embedding backend is available" not in str(exc):
            raise
        _debug("auto embedding backend unavailable; rebuilding runtime index with dummy embedder")
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


def _build_answer_callable():
    deepseek_url = os.getenv("DEEPSEEK_URL")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    deepseek_model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    openrouter_model = os.getenv("OPENROUTER_MODEL")

    if not ((deepseek_url and deepseek_key) or (openrouter_key and openrouter_model)):
        return None

    try:
        import requests
    except ImportError:
        _debug("requests is not installed; using extractive answer fallback")
        return None

    if openrouter_key and openrouter_model:
        url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions")
        headers = {
            "Authorization": f"Bearer {openrouter_key}",
            "Content-Type": "application/json",
        }
        model = openrouter_model
    else:
        url = str(deepseek_url)
        headers = {
            "Authorization": f"Bearer {deepseek_key}",
            "Content-Type": "application/json",
        }
        model = deepseek_model

    def answer_callable(prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in {400, 404, 422}:
            response = requests.post(url, headers=headers, json={"prompt": prompt}, timeout=30)
        response.raise_for_status()
        return _extract_model_text(response.json()).strip()

    return answer_callable


def search_dementia_knowledge(question: str) -> dict[str, Any]:
    """Compatibility wrapper returning the context selected by the shared answer pipeline."""
    _debug(f"search_dementia_knowledge called with question={question!r}")
    if not question or not question.strip():
        return {
            "context": SAFE_FALLBACK_CONTEXT,
            "sources": [],
            "found": False,
            "risk_level": None,
            "debug": {"retrieved_count": 0, "best_score": 0.0},
        }

    answer_result = shared_answer_question(question, build_default_rag_config("mcp"))
    result = {
        "context": answer_result.get("context_used") or SAFE_FALLBACK_CONTEXT,
        "sources": answer_result.get("sources", []),
        "found": bool(answer_result.get("found")),
        "risk_level": _risk_level(question, []),
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
