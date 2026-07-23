from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.pipeline.document import Document


MAX_SNIPPET_CHARS = 280
MAX_KEYWORDS = 8
MAX_KEYWORD_CHARS = 48


def _chunk_id(document: Document) -> str:
    existing = str(document.metadata.get("chunk_id") or "").strip()
    if existing:
        return existing
    source = str(document.metadata.get("source") or document.metadata.get("title") or "document")
    index = int(document.metadata.get("chunk_index") or 1)
    source_key = hashlib.sha256(source.encode("utf-8")).hexdigest()[:12]
    return f"chunk_{source_key}_{index:04d}"


def _source_title(document: Document) -> str:
    title = str(document.metadata.get("title") or document.metadata.get("heading") or "").strip()
    if title:
        return title
    source = str(document.metadata.get("source") or "Document")
    return Path(source).stem.replace("_", " ").replace("-", " ").strip() or "Document"


def _all_documents(vector_store: Any) -> list[Document]:
    if vector_store is None:
        return []
    if hasattr(vector_store, "all_documents"):
        return list(vector_store.all_documents())
    items = list(getattr(vector_store, "items", []))
    metadatas = list(getattr(vector_store, "metadatas", []))
    return [Document(text=text, metadata=dict(metadata)) for text, metadata in zip(items, metadatas)]


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?\u3002\uff01\uff1f])\s*", normalized) if part.strip()]


def _snippet(text: str, terms: Sequence[str]) -> str:
    lowered_terms = [term.casefold() for term in terms if term]
    ranked: list[tuple[int, str]] = []
    for sentence in _sentences(text):
        lowered = sentence.casefold()
        matches = sum(lowered.count(term) for term in lowered_terms)
        if matches:
            ranked.append((matches, sentence))
    selected = max(ranked, default=(0, _sentences(text)[0] if _sentences(text) else ""))[1]
    if len(selected) <= MAX_SNIPPET_CHARS:
        return selected
    return selected[: MAX_SNIPPET_CHARS - 3].rstrip() + "..."


def _clean_keywords(keywords: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for keyword in keywords:
        value = re.sub(r"\s+", " ", str(keyword or "")).strip()
        if not value or len(value) > MAX_KEYWORD_CHARS:
            continue
        if value.casefold() not in {item.casefold() for item in cleaned}:
            cleaned.append(value)
        if len(cleaned) >= MAX_KEYWORDS:
            break
    return cleaned


def keyword_search(
    keywords: list[str],
    top_k: int = 5,
    *,
    vector_store: Any = None,
) -> list[dict[str, Any]]:
    """Return exact-match snippets without exposing full stored chunks."""
    terms = _clean_keywords(keywords)
    if not terms or top_k <= 0:
        return []
    results: list[dict[str, Any]] = []
    for document in _all_documents(vector_store):
        lowered = document.text.casefold()
        raw_score = sum(lowered.count(term.casefold()) * max(1, len(term)) for term in terms)
        opening = lowered[:500]
        # Definition queries should prefer a chunk whose heading/opening states
        # the full question, instead of a later care article that merely repeats
        # the broad disease term many times.
        definition_markers = ("是什麼", "是甚麼", "係咩", "什麼是", "甚麼是", "what is", "define")
        for term in terms:
            normalized_term = term.casefold()
            if any(marker in normalized_term for marker in definition_markers) and normalized_term in opening:
                raw_score += 500
        if raw_score <= 0:
            continue
        matched = [term for term in terms if term.casefold() in lowered]
        results.append(
            {
                "chunk_id": _chunk_id(document),
                "source_title": _source_title(document),
                "snippet": _snippet(document.text, matched),
                "score": round(raw_score / (raw_score + 10.0), 4),
                "matched_keywords": matched,
            }
        )
    results.sort(key=lambda item: (-float(item["score"]), str(item["chunk_id"])))
    return results[: min(max(top_k, 0), 20)]


def semantic_search(
    query: str,
    top_k: int = 5,
    *,
    rag_agent: Any = None,
) -> list[dict[str, Any]]:
    """Use the existing vector retriever while returning snippets only."""
    if not str(query or "").strip() or rag_agent is None or top_k <= 0:
        return []
    documents = rag_agent.retrieve(query, k=min(max(top_k, 1), 20))
    query_terms = re.findall(r"[A-Za-z][A-Za-z0-9'-]*|[\u3400-\u9fff]{2,8}", query)
    output: list[dict[str, Any]] = []
    for rank, document in enumerate(documents, start=1):
        distance = document.metadata.get("distance")
        score = 1.0 / rank
        if isinstance(distance, (int, float)):
            score = max(0.0, min(1.0, 1.0 / (1.0 + float(distance))))
        output.append(
            {
                "chunk_id": _chunk_id(document),
                "source_title": _source_title(document),
                "snippet": _snippet(document.text, query_terms),
                "score": round(score, 4),
            }
        )
    return output


def chunk_read(
    chunk_ids: list[str],
    context_tracker: dict[str, Any] | None = None,
    *,
    vector_store: Any = None,
) -> list[dict[str, Any]]:
    """Read selected chunks once and record them in the supplied tracker."""
    tracker = context_tracker if context_tracker is not None else {}
    read_chunks = tracker.setdefault("read_chunks", set())
    if not isinstance(read_chunks, set):
        read_chunks = set(read_chunks)
        tracker["read_chunks"] = read_chunks
    requested = [str(value) for value in dict.fromkeys(chunk_ids) if value and str(value) not in read_chunks]
    if not requested:
        return []

    if vector_store is not None and hasattr(vector_store, "get_documents_by_chunk_ids"):
        documents = list(vector_store.get_documents_by_chunk_ids(requested))
    else:
        wanted = set(requested)
        documents = [document for document in _all_documents(vector_store) if _chunk_id(document) in wanted]
    by_id = {_chunk_id(document): document for document in documents}
    output: list[dict[str, Any]] = []
    for chunk_id in requested:
        document = by_id.get(chunk_id)
        if document is None:
            continue
        read_chunks.add(chunk_id)
        output.append(
            {
                "chunk_id": chunk_id,
                "source_title": _source_title(document),
                "text": document.text,
                "metadata": dict(document.metadata),
            }
        )
    return output
