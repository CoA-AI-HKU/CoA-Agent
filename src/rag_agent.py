from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional

from .chunker import chunk_documents
from .document import Document
from .embedder import Embedder
from .vector_store import get_default_vector_store


UNKNOWN_ANSWER = "I don't know."

STOPWORDS = {
    "about",
    "after",
    "again",
    "also",
    "and",
    "any",
    "are",
    "ask",
    "can",
    "could",
    "does",
    "for",
    "from",
    "has",
    "have",
    "how",
    "into",
    "its",
    "may",
    "more",
    "not",
    "our",
    "out",
    "should",
    "tell",
    "than",
    "that",
    "the",
    "their",
    "there",
    "these",
    "they",
    "this",
    "was",
    "what",
    "when",
    "where",
    "which",
    "who",
    "why",
    "will",
    "with",
    "would",
    "you",
    "your",
}


def _content_terms(text: str) -> set[str]:
    terms = set()
    for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]*", text.lower()):
        if len(term) < 3 or term in STOPWORDS:
            continue
        terms.add(term)
    return terms


def _normalized_words(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


def _query_phrase(query: str) -> str:
    return _normalized_words(query)


def _document_relevance_score(query: str, document: Document) -> float:
    query_terms = _content_terms(query)
    document_terms = _content_terms(document.text)
    source_text = _normalized_words(str(document.metadata.get("source", "")))
    body_text = _normalized_words(document.text)
    query_phrase = _query_phrase(query)

    shared_terms = query_terms & document_terms
    score = float(len(shared_terms) * 3)

    if query_phrase:
        if query_phrase in body_text:
            score += 12.0
        if query_phrase in source_text:
            score += 18.0

    if query_terms and all(term in source_text for term in query_terms):
        score += 8.0

    first_heading = ""
    for line in document.text.splitlines():
        if line.lstrip().startswith("#"):
            first_heading = _normalized_words(line)
            break
    if query_phrase and query_phrase in first_heading:
        score += 16.0
    elif query_terms and all(term in first_heading for term in query_terms):
        score += 6.0

    distance = document.metadata.get("distance")
    if isinstance(distance, (int, float)):
        score -= float(distance) * 0.05

    return score


class RagAgent:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        embedder_model_name: Optional[str] = None,
        embedder_provider: str = "auto",
        offline_embeddings: bool = False,
        chunk_size: int = 450,
        chunk_overlap: int = 75,
        top_k: int = 3,
        max_context_chars: int = 1800,
        per_chunk_chars: int = 500,
        min_shared_query_terms: int = 1,
    ) -> None:
        self._embedder = embedder
        self.embedder_model_name = embedder_model_name
        self.embedder_provider = embedder_provider
        self.offline_embeddings = offline_embeddings
        self.vector_store = vector_store  # lazily created when needed
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.top_k = top_k
        self.max_context_chars = max_context_chars
        self.per_chunk_chars = per_chunk_chars
        self.min_shared_query_terms = min_shared_query_terms

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = Embedder(
                model_name=self.embedder_model_name,
                provider=self.embedder_provider,
                offline=self.offline_embeddings,
            )
        return self._embedder

    def index_documents(self, documents: List[Document]) -> None:
        if self.vector_store is None:
            self.vector_store = get_default_vector_store()
        chunks = chunk_documents(documents, chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
        embeddings = self.embedder.encode_documents(chunks)
        self.vector_store.add_documents(chunks, embeddings)
        self.vector_store.persist()

    def retrieve(self, query: str, k: Optional[int] = None) -> List[Document]:
        k = k or self.top_k
        if self.vector_store is None:
            self.vector_store = get_default_vector_store()
        query_embedding = self.embedder.encode([query])[0]
        candidate_count = max(k * 10, 25)
        search_results = self.vector_store.query(query, n_results=candidate_count, query_embedding=query_embedding)
        documents = []
        for result in search_results:
            metadata = dict(result["metadata"])
            if "distance" in result:
                metadata["distance"] = result["distance"]
            documents.append(Document(text=result["text"], metadata=metadata))
        supported_documents = self._filter_supported_documents(query, documents)
        return sorted(
            supported_documents,
            key=lambda document: _document_relevance_score(query, document),
            reverse=True,
        )[:k]

    def _filter_supported_documents(self, query: str, documents: List[Document]) -> List[Document]:
        query_terms = _content_terms(query)
        if not query_terms:
            return []

        required_matches = min(max(self.min_shared_query_terms, 1), len(query_terms))
        supported = []
        for document in documents:
            document_terms = _content_terms(document.text)
            shared_terms = query_terms & document_terms
            if len(shared_terms) >= required_matches:
                metadata = dict(document.metadata)
                metadata["matched_query_terms"] = sorted(shared_terms)
                supported.append(Document(text=document.text, metadata=metadata))
        return supported

    def build_prompt(self, query: str, retrieved_docs: List[Document]) -> str:
        parts: List[str] = []
        total = 0
        for doc in retrieved_docs:
            text = doc.text or ""
            if len(text) > self.per_chunk_chars:
                text = text[: self.per_chunk_chars].rstrip() + "..."
            entry = f"Source: {doc.metadata.get('source', 'unknown')}\n{text}"
            entry_len = len(entry)
            if total + entry_len > self.max_context_chars and parts:
                break
            parts.append(entry)
            total += entry_len

        context = "\n\n".join(parts)

        return (
            "You are a helpful assistant.\n"
            "Answer the question using only the provided context.\n"
            "Keep the answer concise, specific, and well-defined: use 1-3 short paragraphs or bullets.\n"
            "Do not invent information from outside the context.\n"
            "If the context is only loosely related or does not explicitly answer the question, say \"I don't know.\"\n\n"
            "Context:\n"
            f"{context}\n\n"
            "Question:\n"
            f"{query}\n\n"
            "Answer:\n"
        )

    def answer(self, query: str, deepseek_callable, k: Optional[int] = None) -> str:
        retrieved = self.retrieve(query, k=k)
        if not retrieved:
            return UNKNOWN_ANSWER
        prompt = self.build_prompt(query, retrieved)
        return deepseek_callable(prompt)

    def answer_with_top_chunk(self, query: str, k: Optional[int] = None) -> str:
        retrieved = self.retrieve(query, k=k)
        if not retrieved:
            return UNKNOWN_ANSWER
        return retrieved[0].text
