from __future__ import annotations

import re
from typing import Iterable, List

from .document import Document

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 200


def _split_paragraphs(text: str) -> List[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    return paragraphs


def _split_long_paragraph(paragraph: str, max_size: int) -> List[str]:
    if len(paragraph) <= max_size:
        return [paragraph]

    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    chunks: List[str] = []
    current: List[str] = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_length + len(sentence) + 1 > max_size and current:
            chunks.append(" ".join(current).strip())
            current = []
            current_length = 0

        if len(sentence) > max_size:
            for i in range(0, len(sentence), max_size):
                chunks.append(sentence[i : i + max_size].strip())
            continue

        current.append(sentence)
        current_length += len(sentence) + 1

    if current:
        chunks.append(" ".join(current).strip())

    return chunks


def _retained_overlap(paragraphs: List[str], overlap: int) -> List[str]:
    if overlap <= 0 or not paragraphs:
        return []

    retained: List[str] = []
    total = 0
    for paragraph in reversed(paragraphs):
        paragraph_length = len(paragraph) + 1
        if total + paragraph_length > overlap and retained:
            break
        retained.insert(0, paragraph)
        total += paragraph_length

    return retained


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    paragraphs = _split_paragraphs(text)
    chunks: List[str] = []
    current_paragraphs: List[str] = []
    current_length = 0

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            long_paragraph_chunks = _split_long_paragraph(paragraph, chunk_size)
            for chunk in long_paragraph_chunks:
                if current_paragraphs:
                    chunks.append(" ".join(current_paragraphs).strip())
                    current_paragraphs = _retained_overlap(current_paragraphs, chunk_overlap)
                    current_length = len(" ".join(current_paragraphs))
                chunks.append(chunk)
            continue

        if current_length + len(paragraph) + 1 > chunk_size and current_paragraphs:
            chunks.append(" ".join(current_paragraphs).strip())
            current_paragraphs = _retained_overlap(current_paragraphs, chunk_overlap)
            current_length = len(" ".join(current_paragraphs))

        current_paragraphs.append(paragraph)
        current_length = len(" ".join(current_paragraphs))

    if current_paragraphs:
        chunks.append(" ".join(current_paragraphs).strip())

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
