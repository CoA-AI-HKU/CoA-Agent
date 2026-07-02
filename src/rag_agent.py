from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional

from .chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE, chunk_documents
from .document import Document
from .embedder import Embedder
from .intent_router import IntentResult, classify_intent
from .prompts import ANSWER_PROMPT, FALLBACK_ANSWER
from .vector_store import get_default_vector_store


UNKNOWN_ANSWER = FALLBACK_ANSWER
RETRIEVE_TOP_K = 8
ANSWER_TOP_K = 3
MIN_RELEVANCE_SCORE = 0.35
PROJECT_ROOT = Path(__file__).resolve().parents[1]

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


def _format_answer_with_sources(answer: str, sources: list[str]) -> str:
    if answer == FALLBACK_ANSWER or not sources:
        return answer

    source_names = []
    for source in sources[:2]:
        source_name = Path(source).name
        if source_name not in source_names:
            source_names.append(source_name)
    suffix = "; ".join(source_names)
    return f"{answer}\n\n\u8cc7\u6599\u4f86\u6e90\uff1a{suffix}"


def _resolve_project_path(path_value: str | Path) -> Path:
    path = Path(path_value).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def build_default_rag_config(mode: str = "shared", overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build the shared runtime config used by CLI and MCP."""
    overrides = overrides or {}
    config = {
        "cwd": str(Path.cwd()),
        "docs_dir": _resolve_project_path(overrides.get("docs_dir") or os.getenv("RAG_DATA_DIR", "data/mds")),
        "chroma_dir": _resolve_project_path(overrides.get("chroma_dir") or os.getenv("CHROMA_DIR", ".chroma/ling_rag")),
        "collection_name": overrides.get("collection_name") or os.getenv("CHROMA_COLLECTION", "ling_rag"),
        "embedder_provider": overrides.get("embedder_provider") or os.getenv("EMBEDDER_PROVIDER", "dummy"),
        "embedder_model": overrides.get("embedder_model") or os.getenv("EMBEDDER_MODEL") or None,
        "offline_embeddings": bool(
            overrides.get("offline_embeddings")
            if "offline_embeddings" in overrides
            else os.getenv("EMBEDDINGS_OFFLINE", "").lower() in {"1", "true", "yes"}
        ),
        "retrieve_top_k": int(overrides.get("retrieve_top_k") or os.getenv("RAG_RETRIEVE_TOP_K", RETRIEVE_TOP_K)),
        "answer_top_k": int(overrides.get("answer_top_k") or os.getenv("RAG_ANSWER_TOP_K", ANSWER_TOP_K)),
        "min_relevance_score": float(
            overrides.get("min_relevance_score") or os.getenv("RAG_MIN_RELEVANCE_SCORE", MIN_RELEVANCE_SCORE)
        ),
        "min_shared_query_terms": int(
            overrides.get("min_shared_query_terms") or os.getenv("RAG_MIN_SHARED_QUERY_TERMS", "1")
        ),
        "chunk_size": int(overrides.get("chunk_size") or os.getenv("RAG_CHUNK_SIZE", DEFAULT_CHUNK_SIZE)),
        "chunk_overlap": int(overrides.get("chunk_overlap") or os.getenv("RAG_CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP)),
        "max_context_chars": int(overrides.get("max_context_chars") or os.getenv("RAG_MAX_CONTEXT_CHARS", "1800")),
        "per_chunk_chars": int(overrides.get("per_chunk_chars") or os.getenv("RAG_PER_CHUNK_CHARS", "500")),
        "mode": overrides.get("mode") or mode or os.getenv("RAG_MODE", "shared"),
        "force_reindex": bool(overrides.get("force_reindex", False)),
        "auto_index": bool(
            overrides.get("auto_index")
            if "auto_index" in overrides
            else os.getenv("RAG_AUTO_INDEX", "1").lower() in {"1", "true", "yes"}
        ),
        "deepseek_url": overrides.get("deepseek_url") or os.getenv("DEEPSEEK_URL"),
        "deepseek_key": overrides.get("deepseek_key") or os.getenv("DEEPSEEK_API_KEY"),
        "deepseek_model": overrides.get("deepseek_model") or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        "openrouter_key": overrides.get("openrouter_key") or os.getenv("OPENROUTER_API_KEY"),
        "openrouter_model": overrides.get("openrouter_model") or os.getenv("OPENROUTER_MODEL"),
        "openrouter_base_url": overrides.get("openrouter_base_url")
        or os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions"),
    }
    config["embedding_model"] = config["embedder_model"] or config["embedder_provider"]
    config["llm_model"] = (
        config["openrouter_model"]
        or (config["deepseek_model"] if config["deepseek_url"] and config["deepseek_key"] else None)
        or "extractive-fallback"
    )
    return config


def _runtime_config(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    overrides = overrides or {}
    return build_default_rag_config(str(overrides.get("mode") or "shared"), overrides)


def _index_manifest(docs: List[Document], config: dict[str, Any], embedder_provider: str | None = None) -> dict[str, Any]:
    document_entries = []
    for document in docs:
        source = str(document.metadata.get("source", ""))
        text_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
        document_entries.append({"source": source, "sha256": text_hash, "chars": len(document.text)})
    return {
        "documents": sorted(document_entries, key=lambda item: item["source"]),
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "embedder_provider": embedder_provider or config["embedder_provider"],
        "embedder_model": config["embedder_model"] or "all-MiniLM-L6-v2",
    }


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _ensure_directory(path.parent)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_directory(path: Path) -> None:
    target = path.resolve(strict=False)
    workspace = PROJECT_ROOT.resolve()
    if target == workspace or workspace not in target.parents:
        raise ValueError(f"Refusing to create vector index directory outside the project: {target}")

    parts = []
    current = target
    while current != current.parent:
        parts.append(current)
        if current.exists():
            break
        current = current.parent

    for part in reversed(parts):
        if os.path.lexists(part) and not part.is_dir():
            part.unlink()
        try:
            part.mkdir(exist_ok=True)
        except FileExistsError:
            if part.is_dir():
                continue
            part.unlink()
            part.mkdir(exist_ok=True)


def _clear_chroma_dir(path: Path) -> None:
    target = path.resolve()
    workspace = PROJECT_ROOT.resolve()
    if target == workspace or workspace not in target.parents:
        raise ValueError(f"Refusing to clear vector index outside the project: {target}")
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


def _build_answer_callable(config: dict[str, Any]) -> Callable[[str], str] | None:
    try:
        import requests
    except ImportError:
        return None

    if config["openrouter_key"] and config["openrouter_model"]:
        url = str(config["openrouter_base_url"])
        model = str(config["openrouter_model"])
        headers = {"Authorization": f"Bearer {config['openrouter_key']}", "Content-Type": "application/json"}
    elif config["deepseek_url"] and config["deepseek_key"]:
        url = str(config["deepseek_url"])
        model = str(config["deepseek_model"])
        headers = {"Authorization": f"Bearer {config['deepseek_key']}", "Content-Type": "application/json"}
    else:
        return None

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


def _build_runtime_agent(config: dict[str, Any]) -> tuple[RagAgent, dict[str, Any]]:
    from .markdown_loader import load_markdown_documents

    docs = load_markdown_documents(config["docs_dir"])
    manifest_path = config["chroma_dir"] / "index_manifest.json"
    current_manifest = _index_manifest(docs, config)
    saved_manifest = _load_manifest(manifest_path)
    manifest_changed = saved_manifest != current_manifest

    if docs and config["auto_index"] and (config["force_reindex"] or manifest_changed):
        _clear_chroma_dir(config["chroma_dir"])

    _ensure_directory(config["chroma_dir"])
    vector_store = get_default_vector_store(
        persist_directory=config["chroma_dir"],
        collection_name=config["collection_name"],
    )
    agent = RagAgent(
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
    if docs and config["auto_index"] and (store_count <= 0 or config["force_reindex"] or manifest_changed):
        try:
            if hasattr(vector_store, "clear"):
                vector_store.clear()
            agent.index_documents(docs)
        except RuntimeError as exc:
            if agent.embedder_provider != "auto" or "No real embedding backend is available" not in str(exc):
                raise
            if hasattr(vector_store, "clear"):
                vector_store.clear()
            agent._embedder = None
            agent.embedder_provider = "dummy"
            agent.index_documents(docs)
            current_manifest = _index_manifest(docs, config, embedder_provider="dummy")
        _save_manifest(manifest_path, current_manifest)
        store_count = vector_store.count() if hasattr(vector_store, "count") else 0

    debug = {
        "cwd": config["cwd"],
        "docs_dir": str(config["docs_dir"]),
        "chroma_dir": str(config["chroma_dir"]),
        "collection_name": config["collection_name"],
        "embedding_model": config["embedding_model"],
        "embedder_provider": config["embedder_provider"],
        "llm_model": config["llm_model"],
        "llm_provider": "openrouter"
        if config["openrouter_key"] and config["openrouter_model"]
        else ("deepseek" if config["deepseek_url"] and config["deepseek_key"] else "extractive"),
        "mode": config["mode"],
        "fallback_active": config["llm_model"] == "extractive-fallback",
        "store_count": store_count,
        "chunk_count": store_count,
        "chunk_size": config["chunk_size"],
        "chunk_overlap": config["chunk_overlap"],
        "retrieve_top_k": config["retrieve_top_k"],
        "answer_top_k": config["answer_top_k"],
        "min_relevance_score": config["min_relevance_score"],
    }
    return agent, debug


def _emit_runtime_debug(result: dict[str, Any]) -> None:
    debug = result.get("debug", {})
    if debug.get("mode") != "mcp" and os.getenv("RAG_DEBUG", "").lower() not in {"1", "true", "yes"}:
        return
    fields = [
        "cwd",
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


def answer_question(question: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Shared high-level RAG answer pipeline used by CLI and MCP."""
    runtime_config = _runtime_config(config)
    intent_result = classify_intent(question)
    if not question or not question.strip():
        result = {
            "found": False,
            "answer": FALLBACK_ANSWER,
            "sources": [],
            "context_used": "",
            "debug": {
                "cwd": runtime_config["cwd"],
                "docs_dir": str(runtime_config["docs_dir"]),
                "chroma_dir": str(runtime_config["chroma_dir"]),
                "embedding_model": runtime_config["embedding_model"],
                "embedder_provider": runtime_config["embedder_provider"],
                "llm_model": runtime_config["llm_model"],
                "llm_provider": "openrouter"
                if runtime_config["openrouter_key"] and runtime_config["openrouter_model"]
                else ("deepseek" if runtime_config["deepseek_url"] and runtime_config["deepseek_key"] else "extractive"),
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

    agent, runtime_debug = _build_runtime_agent(runtime_config)
    answer_callable = _build_answer_callable(runtime_config)
    fallback_active = answer_callable is None
    try:
        result = agent.answer_question(question, answer_callable=answer_callable)
    except Exception as exc:
        runtime_debug["answer_model_error"] = str(exc)
        fallback_active = True
        result = agent.answer_question(question, answer_callable=None)

    result_debug = dict(result.get("debug", {}))
    result_debug.update(runtime_debug)
    result_debug["fallback_active"] = fallback_active
    result_debug["scores"] = result_debug.get("scores", [])
    result["debug"] = result_debug
    _attach_intent_debug(result, intent_result)
    _emit_runtime_debug(result)
    return result
