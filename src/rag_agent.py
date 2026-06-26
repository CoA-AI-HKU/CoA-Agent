from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, List, Optional

from .chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_documents
from .document import Document
from .embedder import Embedder
from .prompts import ANSWER_PROMPT, FALLBACK_ANSWER
from .vector_store import get_default_vector_store


UNKNOWN_ANSWER = FALLBACK_ANSWER
RETRIEVE_TOP_K = 8
ANSWER_TOP_K = 3
MIN_RELEVANCE_SCORE = 0.35

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
    cjk_chars = re.findall(r"[\u3400-\u9fff]", text)
    terms.update("".join(cjk_chars[index : index + 2]) for index in range(len(cjk_chars) - 1))
    terms.update("".join(cjk_chars[index : index + 3]) for index in range(len(cjk_chars) - 2))
    return terms


def _normalized_words(text: str) -> str:
    latin = re.findall(r"[a-z0-9]+", text.lower())
    cjk = re.findall(r"[\u3400-\u9fff]", text)
    return " ".join([*latin, "".join(cjk)])


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


def _normalized_relevance_score(query: str, document: Document) -> float:
    query_terms = _content_terms(query)
    if not query_terms:
        return 0.0

    document_terms = _content_terms(document.text)
    shared_ratio = len(query_terms & document_terms) / len(query_terms)
    lexical_score = min(_document_relevance_score(query, document) / 20.0, 1.0)
    distance = document.metadata.get("distance")
    distance_score = 0.0
    if isinstance(distance, (int, float)):
        distance_score = max(0.0, min(1.0, 1.0 / (1.0 + float(distance))))

    return max(shared_ratio, lexical_score, distance_score * 0.75)


def rewrite_query(question: str) -> str:
    query = question.strip()
    lowered = query.lower()
    replacements = {
        "dementia": "腦退化症",
        "symptoms": "症狀",
        "symptom": "症狀",
        "caregiver": "照顧者",
        "caregivers": "照顧者",
        "diagnosis": "診斷",
        "diagnose": "診斷",
        "treatment": "治療",
        "what is": "是什麼",
    }
    translated_terms = [value for key, value in replacements.items() if key in lowered]
    reversed_definition = re.search(r"什麼是([^？?，,。.\s]+)", query)
    if reversed_definition:
        translated_terms.append(f"{reversed_definition.group(1)}是什麼")
    if translated_terms:
        return f"{query} {' '.join(dict.fromkeys(translated_terms))}"
    return query


class RagAgent:
    def __init__(
        self,
        embedder: Optional[Embedder] = None,
        vector_store: Optional[ChromaVectorStore] = None,
        embedder_model_name: Optional[str] = None,
        embedder_provider: str = "auto",
        offline_embeddings: bool = False,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
        top_k: int = 3,
        max_context_chars: int = 1800,
        per_chunk_chars: int = 500,
        min_shared_query_terms: int = 1,
        retrieve_top_k: int = RETRIEVE_TOP_K,
        answer_top_k: int = ANSWER_TOP_K,
        min_relevance_score: float = MIN_RELEVANCE_SCORE,
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
        self.retrieve_top_k = retrieve_top_k
        self.answer_top_k = answer_top_k
        self.min_relevance_score = min_relevance_score

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
        context = self.format_context(retrieved_docs)
        return ANSWER_PROMPT.format(context=context, question=query)

    def format_context(self, retrieved_docs: List[Document]) -> str:
        parts: List[str] = []
        total = 0
        for index, doc in enumerate(retrieved_docs, start=1):
            text = doc.text or ""
            if len(text) > self.per_chunk_chars:
                text = text[: self.per_chunk_chars].rstrip() + "..."
            source = doc.metadata.get("source", "unknown")
            heading = doc.metadata.get("heading")
            label = f"{source} - {heading}" if heading else str(source)
            entry = f"[Source {index}: {label}]\n{text}"
            entry_len = len(entry)
            if total + entry_len > self.max_context_chars and parts:
                break
            parts.append(entry)
            total += entry_len
        return "\n\n".join(parts)

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

    def answer_question(
        self,
        question: str,
        answer_callable: Optional[Callable[[str], str]] = None,
        retrieve_top_k: Optional[int] = None,
        answer_top_k: Optional[int] = None,
        min_relevance_score: Optional[float] = None,
    ) -> dict[str, Any]:
        search_query = rewrite_query(question)
        retrieve_k = retrieve_top_k or self.retrieve_top_k
        use_k = answer_top_k or self.answer_top_k
        threshold = self.min_relevance_score if min_relevance_score is None else min_relevance_score

        retrieved = self.retrieve(search_query, k=retrieve_k)
        scored = [
            doc.copy_with_metadata(relevance_score=_normalized_relevance_score(search_query, doc))
            for doc in retrieved
        ]
        scored.sort(key=lambda doc: doc.metadata.get("relevance_score", 0.0), reverse=True)
        best_score = float(scored[0].metadata.get("relevance_score", 0.0)) if scored else 0.0

        if not scored or best_score < threshold:
            return {
                "found": False,
                "answer": FALLBACK_ANSWER,
                "sources": [],
                "context_used": "",
                "debug": {
                    "search_query": search_query,
                    "top_k_retrieved": retrieve_k,
                    "top_k_used": 0,
                    "retrieved_count": len(scored),
                    "best_score": best_score,
                    "min_relevance_score": threshold,
                },
            }

        best_chunks = scored[:use_k]
        context = self.format_context(best_chunks)
        prompt = ANSWER_PROMPT.format(context=context, question=question)
        answer = answer_callable(prompt).strip() if answer_callable else self._extractive_answer(search_query, best_chunks)
        if not answer:
            answer = FALLBACK_ANSWER

        sources = []
        for doc in best_chunks:
            source = str(doc.metadata.get("source", "unknown"))
            if source not in sources:
                sources.append(source)

        answer_with_sources = _format_answer_with_sources(answer, sources)
        return {
            "found": answer != FALLBACK_ANSWER,
            "answer": answer,
            "answer_with_sources": answer_with_sources,
            "sources": sources,
            "context_used": context,
            "debug": {
                "search_query": search_query,
                "top_k_retrieved": retrieve_k,
                "top_k_used": len(best_chunks),
                "retrieved_count": len(scored),
                "best_score": best_score,
                "min_relevance_score": threshold,
                "scores": [doc.metadata.get("relevance_score", 0.0) for doc in best_chunks],
            },
        }

    def _extractive_answer(self, question: str, retrieved_docs: List[Document]) -> str:
        direct_answer = _extract_direct_paragraph_answer(question, retrieved_docs)
        if direct_answer:
            return direct_answer

        question_terms = _content_terms(question)
        candidate_sentences: list[tuple[float, str]] = []
        for doc in retrieved_docs:
            for sentence in _split_answer_sentences(doc.text):
                if _is_low_value_answer_sentence(sentence):
                    continue
                sentence_terms = _content_terms(sentence)
                shared = question_terms & sentence_terms
                if not shared:
                    continue
                score = float(len(shared))
                if len(sentence) > 80:
                    score += 0.5
                if re.search(r"\bis\b|\bare\b|\bmeans\b|\brefers\b", sentence.lower()):
                    score += 0.5
                candidate_sentences.append((score, sentence.strip()))

        if not candidate_sentences:
            return FALLBACK_ANSWER

        candidate_sentences.sort(key=lambda item: item[0], reverse=True)
        answer = candidate_sentences[0][1]
        return answer if answer.endswith((".", "!", "?")) else f"{answer}."


def _split_answer_sentences(text: str) -> list[str]:
    prose_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            prose_lines.append("")
            continue
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[Source "):
            continue
        if re.fullmatch(r"\[[^\]]+\]\([^)]+\)", stripped):
            continue
        if re.fullmatch(r"[-*+]\s*", stripped):
            continue
        prose_lines.append(re.sub(r"^[-*+]\s+", "", stripped))

    normalized = re.sub(r"\s+", " ", "\n".join(prose_lines)).strip()
    if not normalized:
        return []
    return [sentence.strip() for sentence in re.split(r"(?<=[.!?。！？])\s*", normalized) if sentence.strip()]


def _is_low_value_answer_sentence(sentence: str) -> bool:
    stripped = sentence.strip()
    if len(stripped) < 40:
        return True
    if stripped.startswith("#"):
        return True
    if stripped.endswith("?"):
        return True
    if re.fullmatch(r"\[[^\]]+\]\([^)]+\).*", stripped):
        return True
    return False


def _is_definition_question(question: str) -> bool:
    normalized = question.lower()
    return any(pattern in normalized for pattern in ("what is", "什麼是", "是什麼", "何謂"))


def _paragraphs_after_headings(text: str) -> list[tuple[str, str]]:
    output: list[tuple[str, str]] = []
    current_heading = ""
    for block in re.split(r"\n\s*\n+", text):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            current_heading = stripped.lstrip("#").strip()
            continue
        if re.fullmatch(r"\[[^\]]+\]\([^)]+\)", stripped):
            continue
        output.append((current_heading, stripped))
    return output


def _extract_direct_paragraph_answer(question: str, retrieved_docs: List[Document]) -> str:
    query_terms = _content_terms(question)
    definition_question = _is_definition_question(question)
    candidates: list[tuple[float, str]] = []

    for doc in retrieved_docs:
        source_text = str(doc.metadata.get("source", "")).lower()
        for heading, paragraph in _paragraphs_after_headings(doc.text):
            if _is_low_value_answer_sentence(paragraph):
                continue
            paragraph_terms = _content_terms(paragraph)
            shared = query_terms & paragraph_terms
            if not shared:
                continue

            score = float(len(shared))
            heading_text = heading.lower()
            normalized_paragraph = paragraph.strip()
            if definition_question and ("是" in paragraph or " is " in f" {paragraph.lower()} "):
                score += 4.0
            if definition_question and re.match(r"^[\u3400-\u9fff]{2,12}是", normalized_paragraph):
                score += 6.0
            if definition_question and ("what-is" in source_text or "是什麼" in heading_text):
                score += 4.0
            if definition_question and "是否" in paragraph:
                score -= 3.0
            if heading and query_terms & _content_terms(heading):
                score += 2.0
            if len(paragraph) > 60:
                score += 0.5
            candidates.append((score, paragraph))

    if not candidates:
        return ""

    candidates.sort(key=lambda item: item[0], reverse=True)
    answer = candidates[0][1].strip()
    first_sentence = _split_answer_sentences(answer)
    if first_sentence:
        return first_sentence[0]
    return answer


def _format_answer_with_sources(answer: str, sources: list[str]) -> str:
    if answer == FALLBACK_ANSWER or not sources:
        return answer

    source_names = []
    for source in sources[:2]:
        source_name = Path(source).name
        if source_name not in source_names:
            source_names.append(source_name)
    suffix = "; ".join(source_names)
    return f"{answer}\n\n資料來源：{suffix}"
