from __future__ import annotations

import re
from typing import Iterable, List

from .document import Document

DEFAULT_CHUNK_SIZE = 450
DEFAULT_CHUNK_OVERLAP = 75


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\s+", " ", text)


def _split_sentences(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?])\s+", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _split_long_sentence(sentence: str, max_size: int) -> List[str]:
    if len(sentence) <= max_size:
        return [sentence]

    words = sentence.split()
    chunks: List[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])
        if len(candidate) > max_size and current:
            chunks.append(" ".join(current))
            current = []

        if len(word) > max_size:
            chunks.extend(word[i : i + max_size] for i in range(0, len(word), max_size))
            continue

        current.append(word)

    if current:
        chunks.append(" ".join(current))

    return chunks


def _retained_overlap(sentences: List[str], overlap: int) -> List[str]:
    if overlap <= 0 or not sentences:
        return []

    retained: List[str] = []
    total = 0
    for sentence in reversed(sentences):
        sentence_length = len(sentence) + 1
        if total + sentence_length > overlap and retained:
            break
        retained.insert(0, sentence)
        total += sentence_length

    return retained


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    sentences = _split_sentences(text)
    chunks: List[str] = []
    current_sentences: List[str] = []
    current_length = 0

    for sentence in sentences:
        sentence_parts = _split_long_sentence(sentence, chunk_size)
        for sentence_part in sentence_parts:
            if current_length + len(sentence_part) + 1 > chunk_size and current_sentences:
                chunks.append(" ".join(current_sentences).strip())
                current_sentences = _retained_overlap(current_sentences, chunk_overlap)
                current_length = len(" ".join(current_sentences))

            if len(sentence_part) > chunk_size:
                if current_sentences:
                    chunks.append(" ".join(current_sentences).strip())
                    current_sentences = []
                    current_length = 0
                chunks.append(sentence_part)
                continue

            current_sentences.append(sentence_part)
            current_length = len(" ".join(current_sentences))

            if current_length >= chunk_size:
                chunks.append(" ".join(current_sentences).strip())
                current_sentences = _retained_overlap(current_sentences, chunk_overlap)
                current_length = len(" ".join(current_sentences))

    if current_sentences:
        final_chunk = " ".join(current_sentences).strip()
        if not chunks or chunks[-1] != final_chunk:
            chunks.append(final_chunk)

    return chunks


def chunk_document(document: Document, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[Document]:
    text_chunks = chunk_text(document.text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    return [
        Document(
            text=chunk,
            metadata={
                **document.metadata,
                "chunk_index": index,
                "chunk_size": len(chunk),
            },
        )
        for index, chunk in enumerate(text_chunks, start=1)
    ]


def chunk_documents(documents: Iterable[Document], chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[Document]:
    output: List[Document] = []
    for document in documents:
        output.extend(chunk_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return output
