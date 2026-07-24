from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional
from urllib.parse import urlparse
from uuid import uuid4

from .chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_documents
from .document import Document
from .embedder import Embedder
from .language import AnswerLanguage, detect_answer_language
from .prompts import FALLBACK_ANSWER, build_answer_prompt, get_fallback_answer, get_source_label
from .vector_store import get_default_vector_store
from ..intent_router import IntentResult, classify_intent
from ..rag.runtime_config import (
    DEFAULT_CHROMA_DIR as CANONICAL_CHROMA_DIR,
    load_rag_config,
    log_resolved_config,
)
from ..meds.medicine_normalizer import normalize_medicine_mentions
from ..safety.medication_guard import (
    build_short_medication_safety_response,
    detect_red_flags,
    is_medication_decision_question,
)


UNKNOWN_ANSWER = FALLBACK_ANSWER
logger = logging.getLogger(__name__)
RETRIEVE_TOP_K = 8
ANSWER_TOP_K = 2
MIN_RELEVANCE_SCORE = 0.35
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = CANONICAL_CHROMA_DIR.as_posix()
MEDICATION_OR_DIAGNOSIS_RESPONSE = (
    "我不能提供診斷或任何用藥建議。請詢問醫生、藥劑師或合資格醫護人員。"
)
SAFETY_SENSITIVE_RESPONSE = (
    "這個情況可能需要即時協助。請先確保安全，並盡快聯絡照顧者、醫護人員或緊急服務。"
)
LOCALIZED_RESPONSES: dict[str, dict[AnswerLanguage, str]] = {
    "medication_or_diagnosis": {
        "zh-Hant": MEDICATION_OR_DIAGNOSIS_RESPONSE,
        "zh-Hans": "我不能提供诊断或任何用药建议。请询问医生、药剂师或合资格医护人员。",
        "en": "I can't provide diagnosis or any medication advice. Please ask a doctor, pharmacist, or qualified clinician.",
    },
    "safety_sensitive": {
        "zh-Hant": SAFETY_SENSITIVE_RESPONSE,
        "zh-Hans": "这个情况可能需要即时协助。请先确保安全，并尽快联系照顾者、医护人员或紧急服务。",
        "en": "This situation may need immediate help. Please make sure everyone is safe and contact a caregiver, clinician, or emergency services as soon as possible.",
    },
}

SELF_MEMORY_CONCERN_RESPONSE = (
    "記不住事情會令人很困擾，也可能和壓力、睡眠不足、情緒、藥物、身體狀況或認知變化有關。"
    "你可以先用一些簡單方法幫自己：把重要事情寫下來、用手機提醒、把常用物品放在固定位置、每天保持規律作息。\n\n"
    "如果這種情況最近明顯變多、影響日常生活，或家人也有留意到，建議和醫生或醫護人員討論，找出原因。"
    "你也可以告訴我有什麼事情想記住，我可以幫你整理成簡單提醒。"
)
CAREGIVER_GUIDANCE_RESPONSE = (
    "如果你留意到家人最近較常忘記事情，可以先觀察和記錄，不要急著下結論。"
    "請留意是否影響日常生活或安全，以及是否和睡眠、壓力、情緒、藥物或身體不適有關。"
    "如果情況持續、變嚴重，建議陪同家人向醫生或醫護人員查詢。"
)

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
        "dementia": "\u8166\u9000\u5316\u75c7",
        "symptoms": "\u75c7\u72c0",
        "symptom": "\u75c7\u72c0",
        "caregiver": "\u7167\u9867\u8005",
        "caregivers": "\u7167\u9867\u8005",
        "diagnosis": "\u8a3a\u65b7",
        "diagnose": "\u8a3a\u65b7",
        "treatment": "\u6cbb\u7642",
        "what is": "\u662f\u4ec0\u9ebc",
    }
    translated_terms = [value for key, value in replacements.items() if key in lowered]
    reversed_definition = re.search("\u4ec0\u9ebc\u662f([^\uff1f?\uff0c,\u3002.\\s]+)", query)
    if reversed_definition:
        translated_terms.append(f"{reversed_definition.group(1)}\u662f\u4ec0\u9ebc")
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

    def build_prompt(
        self,
        query: str,
        retrieved_docs: List[Document],
        answer_language: AnswerLanguage | None = None,
    ) -> str:
        answer_language = answer_language or detect_answer_language(query)
        context = self.format_context(retrieved_docs)
        return build_answer_prompt(context=context, question=query, answer_language=answer_language)

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
            return get_fallback_answer(detect_answer_language(query))
        prompt = self.build_prompt(query, retrieved, answer_language=detect_answer_language(query))
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
        answer_language: AnswerLanguage | None = None,
        route: str = "dementia_qa",
    ) -> dict[str, Any]:
        from src.rag.agentic_retriever import agentic_retrieve

        answer_language = answer_language or detect_answer_language(question)
        fallback_answer = get_fallback_answer(answer_language)
        search_query = rewrite_query(question)
        retrieve_k = retrieve_top_k or self.retrieve_top_k
        use_k = answer_top_k or self.answer_top_k
        threshold = self.min_relevance_score if min_relevance_score is None else min_relevance_score

        retrieval = agentic_retrieve(
            search_query,
            route,
            max_steps=3,
            rag_agent=self,
            answer_top_k=use_k,
            search_top_k=retrieve_k,
        )
        evidence = retrieval.get("evidence", [])
        scored = []
        for item in evidence:
            metadata = dict(item.get("metadata") or {})
            metadata["chunk_id"] = item.get("chunk_id")
            document = Document(text=str(item.get("text") or ""), metadata=metadata)
            evidence_score = float(item.get("score") or 0.0)
            metadata_score = _normalized_relevance_score(search_query, document)
            scored.append(document.copy_with_metadata(relevance_score=max(evidence_score, metadata_score)))
        scored.sort(key=lambda doc: doc.metadata.get("relevance_score", 0.0), reverse=True)
        best_score = float(scored[0].metadata.get("relevance_score", 0.0)) if scored else 0.0
        sufficiency = retrieval.get("sufficiency", {})

        if not scored or best_score < threshold or not sufficiency.get("sufficient", False):
            return {
                "found": False,
                "answer": fallback_answer,
                "sources": [],
                "context_used": "",
                "debug": {
                    "answer_language": answer_language,
                    "search_query": search_query,
                    "top_k_retrieved": retrieve_k,
                    "top_k_used": 0,
                    "retrieved_count": len(scored),
                    "best_score": best_score,
                    "min_relevance_score": threshold,
                    "retrieval": retrieval.get("retrieval_log", {}),
                    "evidence_sufficiency": sufficiency,
                },
            }

        best_chunks = scored[:use_k]
        context = self.format_context(best_chunks)
        prompt = build_answer_prompt(context=context, question=question, answer_language=answer_language)
        answer = (
            answer_callable(prompt).strip()
            if answer_callable
            else self._extractive_answer(search_query, best_chunks, fallback_answer=fallback_answer)
        )
        if not answer:
            answer = fallback_answer

        sources = []
        for doc in best_chunks:
            source = str(doc.metadata.get("source", "unknown"))
            if source not in sources:
                sources.append(source)

        answer_with_sources = _format_answer_with_sources(answer, sources, answer_language)
        return {
            "found": answer != fallback_answer,
            "answer": answer,
            "answer_with_sources": answer_with_sources,
            "sources": sources,
            "context_used": context,
            "debug": {
                "answer_language": answer_language,
                "search_query": search_query,
                "top_k_retrieved": retrieve_k,
                "top_k_used": len(best_chunks),
                "retrieved_count": len(scored),
                "best_score": best_score,
                "min_relevance_score": threshold,
                "scores": [doc.metadata.get("relevance_score", 0.0) for doc in best_chunks],
                "retrieval": retrieval.get("retrieval_log", {}),
                "evidence_sufficiency": sufficiency,
            },
        }

    def _extractive_answer(
        self,
        question: str,
        retrieved_docs: List[Document],
        fallback_answer: str = FALLBACK_ANSWER,
    ) -> str:
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
            return fallback_answer

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
    return [sentence.strip() for sentence in re.split("(?<=[.!?\u3002\uff01\uff1f])\\s*", normalized) if sentence.strip()]


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
    return any(pattern in normalized for pattern in ("what is", "\u4ec0\u9ebc\u662f", "\u662f\u4ec0\u9ebc", "\u4f55\u8b02"))


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
            if definition_question and ("\u662f" in paragraph or " is " in f" {paragraph.lower()} "):
                score += 4.0
            if definition_question and re.match(r"^[\u3400-\u9fff]{2,12}\u662f", normalized_paragraph):
                score += 6.0
            if definition_question and ("what-is" in source_text or "\u662f\u4ec0\u9ebc" in heading_text):
                score += 4.0
            if definition_question and "\u662f\u5426" in paragraph:
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


def _format_answer_with_sources(
    answer: str,
    sources: list[str],
    answer_language: AnswerLanguage = "zh-Hant",
) -> str:
    if answer == get_fallback_answer(answer_language) or not sources:
        return answer

    source_names = []
    for source in sources[:2]:
        source_name = Path(source).name
        if source_name not in source_names:
            source_names.append(source_name)
    suffix = "; ".join(source_names)
    separator = ": " if answer_language == "en" else "："
    return f"{answer}\n\n{get_source_label(answer_language)}{separator}{suffix}"


def _resolve_project_path(path_value: str | Path) -> Path:
    raw_path = str(path_value)
    path = Path(raw_path).expanduser()
    if path.is_absolute():
        return path
    if raw_path.startswith("/"):
        return path
    return PROJECT_ROOT / path


def build_default_rag_config(mode: str = "shared", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the shared runtime config used by CLI and MCP."""
    return load_rag_config(mode, overrides)


def _runtime_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    return build_default_rag_config(str(overrides.get("mode") or "shared"), overrides)


def _index_manifest(
    docs: List[Document],
    config: dict[str, Any],
    *,
    embedder_provider: str,
    embedding_dimension: int,
) -> dict[str, Any]:
    document_entries = []
    for document in docs:
        source = str(document.metadata.get("source", ""))
        text_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
        document_entries.append({"source": source, "sha256": text_hash, "chars": len(document.text)})
    return {
        "schema_version": 3,
        "documents": sorted(document_entries, key=lambda item: item["source"]),
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "embedder_provider": embedder_provider,
        "embedder_model": "dummy" if embedder_provider == "dummy" else config["embedder_model"],
        "embedding_dimension": embedding_dimension,
        "docs_dir": str(config["docs_dir"].resolve()),
        "collection_name": config["collection_name"],
    }


def _manifest_embedding_identity(manifest: dict[str, Any] | None) -> tuple[Any, ...] | None:
    if not manifest:
        return None
    return (
        manifest.get("embedder_provider"),
        manifest.get("embedder_model"),
        manifest.get("embedding_dimension"),
        manifest.get("docs_dir"),
        manifest.get("collection_name"),
        manifest.get("chunk_size"),
        manifest.get("chunk_overlap"),
    )


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _ensure_directory(path.parent)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def _ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _clear_chroma_dir(path: Path) -> None:
    target = path.resolve(strict=False)
    chroma_parts = {part.lower() for part in target.parts}
    if not any("chroma" in part for part in chroma_parts):
        raise ValueError(f"Refusing to clear non-Chroma vector index directory: {target}")
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


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


def create_chat_answer(config: dict[str, Any]) -> Callable[[str], str] | None:
    try:
        import requests
    except ImportError:
        return None

    if config["llm_provider"] == "extractive":
        return None
    base_url = str(config["llm_base_url"]).rstrip("/")
    url = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    model = str(config["llm_model"])
    headers = {"Authorization": f"Bearer {config['llm_api_key']}", "Content-Type": "application/json"}

    def answer_callable(prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            if response.status_code >= 400:
                detail = response.text.strip()[:500]
                logger.error(
                    "LLM request failed status=%s provider=%s model=%s endpoint=%s error=%s",
                    response.status_code, config["llm_provider"], model, urlparse(url).hostname, detail,
                )
                raise RuntimeError(
                    f"{config['llm_provider']} upstream API error (HTTP {response.status_code}): {detail}"
                )
            response.raise_for_status()
        except RuntimeError:
            raise
        except Exception as exc:
            logger.exception(
                "LLM request error provider=%s model=%s endpoint=%s",
                config["llm_provider"], model, urlparse(url).hostname,
            )
            raise RuntimeError(f"{config['llm_provider']} upstream API request failed: {exc}") from exc
        return _extract_model_text(response.json()).strip()

    return answer_callable


def _build_runtime_agent(config: dict[str, Any]) -> tuple[RagAgent, dict[str, Any]]:
    from .markdown_loader import load_markdown_documents

    log_resolved_config(config)
    docs = load_markdown_documents(config["docs_dir"])
    try:
        embedder = Embedder(
            model_name=config["embedder_model"],
            provider=config["embedder_provider"],
            offline=config["offline_embeddings"],
        )
    except RuntimeError as exc:
        if config["embedder_provider"] == "auto" and config["allow_dummy"] and config["rag_env"] != "production":
            embedder = Embedder(model_name=config["embedder_model"], provider="dummy")
        else:
            raise RuntimeError(
                "Real embedding backend unavailable. Install sentence-transformers or configure "
                "the selected provider. Dummy fallback is disabled."
            ) from exc
    resolved_provider = embedder.resolved_provider
    embedding_dimension = embedder.dimension
    manifest_path = Path(config.get("manifest_path") or config["chroma_dir"] / "index_manifest.json")
    current_manifest = _index_manifest(
        docs,
        config,
        embedder_provider=resolved_provider,
        embedding_dimension=embedding_dimension,
    )
    saved_manifest = _load_manifest(manifest_path)
    manifest_changed = saved_manifest != current_manifest
    identity_changed = (
        saved_manifest is not None
        and _manifest_embedding_identity(saved_manifest) != _manifest_embedding_identity(current_manifest)
    )

    if identity_changed and not config["force_reindex"]:
        raise RuntimeError(
            "Existing Chroma index embedding configuration does not match runtime configuration. "
            "Refusing to query it. Rebuild the configured collection with python -m src.cli --force-reindex."
        )

    _ensure_directory(config["chroma_dir"])
    vector_store = get_default_vector_store(
        persist_directory=config["chroma_dir"],
        collection_name=config["collection_name"],
        require_persistent=True,
    )
    agent = RagAgent(
        embedder=embedder,
        embedder_provider=config["embedder_provider"],
        embedder_model_name=config["embedder_model"],
        offline_embeddings=config["offline_embeddings"],
        vector_store=vector_store,
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        max_context_chars=config["max_context_chars"],
        per_chunk_chars=config["per_chunk_chars"],
        min_shared_query_terms=config["min_shared_query_terms"],
        retrieve_top_k=config["retrieve_top_k"],
        answer_top_k=config["answer_top_k"],
        min_relevance_score=config["min_relevance_score"],
    )

    store_count = vector_store.count() if hasattr(vector_store, "count") else 0
    if store_count > 0 and saved_manifest is None and not config["force_reindex"]:
        raise RuntimeError(
            "Existing Chroma collection has no valid index_manifest.json. Refusing to query stale vectors; rebuild it."
        )
    if docs and config["auto_index"] and (store_count <= 0 or config["force_reindex"] or manifest_changed):
        if hasattr(vector_store, "clear"):
            vector_store.clear()
        agent.index_documents(docs)
        _save_manifest(manifest_path, current_manifest)
        store_count = vector_store.count() if hasattr(vector_store, "count") else 0

    debug = {
        "cwd": config["cwd"],
        "docs_dir": str(config["docs_dir"]),
        "chroma_dir": str(config["chroma_dir"]),
        "collection_name": config["collection_name"],
        "embedding_model": config["embedding_model"],
        "embedder_provider": resolved_provider,
        "embedding_dimension": embedding_dimension,
        "llm_model": config["llm_model"],
        "llm_provider": config["llm_provider"],
        "mode": config["mode"],
        "fallback_active": config["llm_provider"] == "extractive",
        "store_count": store_count,
        "chunk_count": store_count,
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "retrieve_top_k": config["retrieve_top_k"],
        "answer_top_k": config["answer_top_k"],
        "min_relevance_score": config["min_relevance_score"],
    }
    return agent, debug


def rebuild_runtime_index(config: dict[str, Any] | None = None) -> dict[str, Any]:
    resolved = _runtime_config({**(config or {}), "force_reindex": True, "auto_index": True})
    target_name = str(resolved["collection_name"])
    temporary_name = f"{target_name}__rebuild_{uuid4().hex}"
    temporary_manifest = resolved["chroma_dir"] / f"index_manifest.{temporary_name}.json"
    print(
        f"Rebuild started: provider={resolved['embedder_provider']} model={resolved['embedder_model']} "
        f"temporary_collection={temporary_name}", flush=True,
    )
    staged_agent = None
    try:
        staged_agent, debug = _build_runtime_agent({
            **resolved, "collection_name": temporary_name, "manifest_path": temporary_manifest,
        })
        if debug["chunk_count"] <= 0:
            raise RuntimeError("Rebuild produced an empty collection; the live collection was not replaced.")
        staged_agent.vector_store.replace_collection(target_name)
        manifest = _load_manifest(temporary_manifest)
        if manifest is None:
            raise RuntimeError("Rebuild did not produce a valid index manifest.")
        manifest["collection_name"] = target_name
        manifest_path = resolved["chroma_dir"] / "index_manifest.json"
        _save_manifest(manifest_path, manifest)
    except Exception:
        if staged_agent is not None:
            try:
                staged_agent.vector_store.drop_collection()
            except Exception:
                pass
        raise
    finally:
        temporary_manifest.unlink(missing_ok=True)
    print(
        f"Rebuild complete: chunk_count={debug['chunk_count']} provider={debug['embedder_provider']} "
        f"model={manifest['embedder_model']} vector_dimension={debug['embedding_dimension']}", flush=True,
    )
    return {
        "chunk_count": debug["chunk_count"],
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def get_runtime_agent(config: dict[str, Any] | None = None) -> RagAgent:
    resolved = _runtime_config(config)
    agent, _ = _build_runtime_agent(resolved)
    return agent


def _emit_runtime_debug(result: dict[str, Any]) -> None:
    debug = result.get("debug", {})
    if debug.get("mode") != "mcp" and os.getenv("RAG_DEBUG", "").lower() not in {"1", "true", "yes"}:
        return
    fields = [
        "cwd",
        "answer_language",
        "docs_dir",
        "chroma_dir",
        "embedding_model",
        "embedder_provider",
        "llm_model",
        "llm_provider",
        "mode",
        "collection_name",
        "chunk_count",
        "retrieve_top_k",
        "answer_top_k",
        "min_relevance_score",
        "fallback_active",
        "sources",
        "scores",
    ]
    for field in fields:
        value = result.get("sources") if field == "sources" else debug.get(field)
        print(f"RAG_DEBUG {field}={value}", file=sys.stderr)


def _intent_debug(intent_result: IntentResult) -> dict[str, Any]:
    return {
        "confidence": intent_result.confidence,
        "matched_terms": intent_result.matched_terms,
        "reason": intent_result.reason,
    }


def _attach_intent_debug(result: dict[str, Any], intent_result: IntentResult) -> dict[str, Any]:
    result["intent"] = intent_result.intent
    result["intent_debug"] = _intent_debug(intent_result)
    debug = dict(result.get("debug", {}))
    debug["intent"] = intent_result.intent
    debug["intent_debug"] = result["intent_debug"]
    result["debug"] = debug
    return result


def _boundary_response(intent_result: IntentResult, runtime_config: dict[str, Any]) -> dict[str, Any] | None:
    answer_language = runtime_config["resolved_answer_language"]
    if intent_result.intent == "medication_or_diagnosis":
        answer = LOCALIZED_RESPONSES["medication_or_diagnosis"][answer_language]
    elif intent_result.intent == "safety_sensitive":
        answer = LOCALIZED_RESPONSES["safety_sensitive"][answer_language]
    elif intent_result.intent == "self_memory_concern":
        answer = SELF_MEMORY_CONCERN_RESPONSE
    else:
        return None

    result = {
        "found": False,
        "answer": answer,
        "answer_with_sources": answer,
        "sources": [],
        "context_used": "",
        "debug": {
            "cwd": runtime_config["cwd"],
            "answer_language": answer_language,
            "docs_dir": str(runtime_config["docs_dir"]),
            "chroma_dir": str(runtime_config["chroma_dir"]),
            "embedding_model": runtime_config["embedding_model"],
            "embedder_provider": runtime_config["embedder_provider"],
            "llm_model": runtime_config["llm_model"],
            "llm_provider": "boundary-handler",
            "mode": runtime_config["mode"],
            "collection_name": runtime_config["collection_name"],
            "chunk_count": 0,
            "retrieve_top_k": 0,
            "answer_top_k": 0,
            "min_relevance_score": runtime_config["min_relevance_score"],
            "fallback_active": False,
            "retrieved_count": 0,
            "best_score": 0.0,
            "scores": [],
            "boundary_handler": intent_result.intent,
        },
    }
    return _attach_intent_debug(result, intent_result)


def _medication_guardrail_response(
    question: str,
    runtime_config: dict[str, Any],
    intent_result: IntentResult,
) -> dict[str, Any] | None:
    if not is_medication_decision_question(question):
        return None

    detected_medicines = normalize_medicine_mentions(question)
    patient_profile = _profile_with_current_medications(
        runtime_config.get("patient_profile"),
        runtime_config.get("current_medications"),
    )
    caregiver_available = bool(
        runtime_config.get("caregiver_available")
        if "caregiver_available" in runtime_config
        else _has_caregiver(patient_profile)
    )
    symptoms = runtime_config.get("symptoms")
    if isinstance(symptoms, list):
        symptoms_text = " ".join(str(symptom) for symptom in symptoms)
    else:
        symptoms_text = str(symptoms or question)
    red_flags = detect_red_flags(symptoms_text)
    answer = build_short_medication_safety_response(
        patient_profile=patient_profile,
        detected_medicines=detected_medicines,
        red_flags=red_flags,
        answer_language=runtime_config["resolved_answer_language"],
    )

    result = {
        "found": False,
        "answer": answer,
        "answer_with_sources": answer,
        "sources": [],
        "context_used": "",
        "detected_medicines": [
            {
                "canonical_name": mention.get("canonical_name"),
                "matched_alias": mention.get("matched_alias"),
                "confidence": mention.get("confidence"),
                "source": mention.get("source"),
            }
            for mention in detected_medicines
        ],
        "debug": {
            "cwd": runtime_config["cwd"],
            "answer_language": runtime_config["resolved_answer_language"],
            "docs_dir": str(runtime_config["docs_dir"]),
            "chroma_dir": str(runtime_config["chroma_dir"]),
            "embedding_model": runtime_config["embedding_model"],
            "embedder_provider": runtime_config["embedder_provider"],
            "llm_model": runtime_config["llm_model"],
            "llm_provider": "medication-safety-guardrail",
            "mode": runtime_config["mode"],
            "collection_name": runtime_config["collection_name"],
            "chunk_count": 0,
            "retrieve_top_k": 0,
            "answer_top_k": 0,
            "min_relevance_score": runtime_config["min_relevance_score"],
            "fallback_active": False,
            "retrieved_count": 0,
            "best_score": 0.0,
            "scores": [],
            "boundary_handler": "medication_safety",
            "normal_rag_skipped": True,
            "red_flags": red_flags,
            "caregiver_available": caregiver_available,
        },
    }
    return _attach_intent_debug(result, intent_result)


def _profile_with_current_medications(patient_profile: Any, current_medications: Any) -> Any:
    if not current_medications:
        return patient_profile
    if isinstance(patient_profile, dict):
        profile = dict(patient_profile)
    else:
        profile = {}
    profile["current_medications"] = current_medications
    return profile


def _has_caregiver(patient_profile: Any) -> bool:
    if not isinstance(patient_profile, dict):
        return False
    caregivers = patient_profile.get("caregivers") or patient_profile.get("caregiver_names")
    return bool(caregivers)


def answer_question(question: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shared high-level RAG answer pipeline used by CLI and MCP."""
    runtime_config = _runtime_config(config)
    answer_language = detect_answer_language(question, str(runtime_config.get("answer_language", "auto")))
    runtime_config["resolved_answer_language"] = answer_language
    if config:
        for key in ("patient_profile", "current_medications", "symptoms", "caregiver_available"):
            if key in config:
                runtime_config[key] = config[key]
    intent_result = classify_intent(question)
    assert intent_result is not None, "ARAG planner is unavailable"
    if not question or not question.strip():
        result = {
            "found": False,
            "answer": get_fallback_answer(answer_language),
            "sources": [],
            "context_used": "",
            "debug": {
                "cwd": runtime_config["cwd"],
                "answer_language": answer_language,
                "docs_dir": str(runtime_config["docs_dir"]),
                "chroma_dir": str(runtime_config["chroma_dir"]),
                "embedding_model": runtime_config["embedding_model"],
                "embedder_provider": runtime_config["embedder_provider"],
                "llm_model": runtime_config["llm_model"],
                "llm_provider": runtime_config["llm_provider"],
                "mode": runtime_config["mode"],
                "collection_name": runtime_config["collection_name"],
                "chunk_count": 0,
                "retrieve_top_k": runtime_config["retrieve_top_k"],
                "answer_top_k": runtime_config["answer_top_k"],
                "min_relevance_score": runtime_config["min_relevance_score"],
                "fallback_active": runtime_config["llm_model"] == "extractive-fallback",
                "retrieved_count": 0,
                "best_score": 0.0,
                "scores": [],
            },
        }
        _attach_intent_debug(result, intent_result)
        _emit_runtime_debug(result)
        return result

    force_retrieval = bool(config and config.get("force_retrieval"))
    if not force_retrieval:
        medication_guardrail_result = _medication_guardrail_response(question, runtime_config, intent_result)
        if medication_guardrail_result is not None:
            _emit_runtime_debug(medication_guardrail_result)
            return medication_guardrail_result

        boundary_result = _boundary_response(intent_result, runtime_config)
        if boundary_result is not None:
            _emit_runtime_debug(boundary_result)
            return boundary_result

    agent, runtime_debug = _build_runtime_agent(runtime_config)
    answer_callable = create_chat_answer(runtime_config)
    if answer_callable is None and not runtime_config["allow_extractive_fallback"]:
        raise RuntimeError(
            "No LLM generation provider is configured and extractive fallback is disabled. "
            "Configure LLM_PROVIDER or explicitly set RAG_ALLOW_EXTRACTIVE_FALLBACK=true."
        )
    assert agent is not None and callable(agent.answer_question), "ARAG retriever is unavailable"
    generator = answer_callable or agent._extractive_answer
    assert callable(generator), "ARAG generator is unavailable"
    fallback_active = answer_callable is None
    try:
        result = agent.answer_question(
            question,
            answer_callable=answer_callable,
            answer_language=answer_language,
            route=str((config or {}).get("planner_route") or intent_result.intent),
        )
    except Exception as exc:
        runtime_debug["answer_model_error"] = str(exc)
        if runtime_config["rag_env"] == "production" or not runtime_config["allow_extractive_fallback"]:
            raise RuntimeError(
                "Configured LLM generation failed and extractive fallback is disabled."
            ) from exc
        fallback_active = True
        result = agent.answer_question(
            question,
            answer_callable=None,
            answer_language=answer_language,
            route=str((config or {}).get("planner_route") or intent_result.intent),
        )

    result_debug = dict(result.get("debug", {}))
    result_debug.update(runtime_debug)
    result_debug["answer_language"] = answer_language
    result_debug["fallback_active"] = fallback_active
    result_debug["scores"] = result_debug.get("scores", [])
    result["debug"] = result_debug
    _attach_intent_debug(result, intent_result)
    _emit_runtime_debug(result)
    return result
