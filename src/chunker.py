from __future__ import annotations

import re
from typing import Iterable, List

from .document import Document

DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 160


def _normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\s+", " ", text)


def _normalize_block(block: str) -> str:
    lines = [line.rstrip() for line in block.replace("\r\n", "\n").replace("\r", "\n").splitlines()]
    return "\n".join(line for line in lines if line.strip()).strip()


def _split_markdown_blocks(text: str) -> List[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []

    raw_blocks = re.split(r"\n\s*\n+", text)
    blocks = [_normalize_block(block) for block in raw_blocks]
    return [block for block in blocks if block]


def _split_sentences(text: str) -> List[str]:
    normalized = _normalize_text(text)
    if not normalized:
        return []

    sentences = re.split(r"(?<=[.!?。！？])\s*", normalized)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def _split_clauses(text: str) -> List[str]:
    clauses = re.split(r"(?<=[,;:，；：、])\s*", text.strip())
    return [clause.strip() for clause in clauses if clause.strip()]


def _split_long_sentence(sentence: str, max_size: int) -> List[str]:
    if len(sentence) <= max_size:
        return [sentence]

    clauses = _split_clauses(sentence)
    if len(clauses) > 1:
        chunks: List[str] = []
        current: list[str] = []
        current_length = 0
        for clause in clauses:
            separator_length = 1 if current else 0
            if current and current_length + len(clause) + separator_length > max_size:
                chunks.append(" ".join(current))
                current = []
                current_length = 0
            if len(clause) > max_size:
                chunks.extend(_split_long_sentence(clause, max_size))
                continue
            current.append(clause)
            current_length += len(clause) + separator_length
        if current:
            chunks.append(" ".join(current))
        return chunks

    if not re.search(r"\s", sentence):
        return [sentence[index : index + max_size] for index in range(0, len(sentence), max_size)]

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


def _retained_overlap(units: List[str], overlap: int) -> List[str]:
    if overlap <= 0 or not units:
        return []

    retained: List[str] = []
    total = 0
    for unit in reversed(units):
        unit_length = len(unit) + 2
        if total + unit_length > overlap and retained:
            break
        retained.insert(0, unit)
        total += unit_length

    return retained


def _split_large_block(block: str, chunk_size: int) -> List[str]:
    if len(block) <= chunk_size:
        return [block]

    if block.lstrip().startswith(("- ", "* ", "+ ")) or re.match(r"^\s*\d+\.\s+", block):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        chunks: List[str] = []
        current: List[str] = []
        current_length = 0
        for line in lines:
            if current and current_length + len(line) + 1 > chunk_size:
                chunks.append("\n".join(current))
                current = []
                current_length = 0
            current.append(line)
            current_length += len(line) + 1
        if current:
            chunks.append("\n".join(current))
        return chunks

    sentence_chunks: List[str] = []
    for sentence in _split_sentences(block):
        sentence_chunks.extend(_split_long_sentence(sentence, chunk_size))
    return sentence_chunks


def _join_units(units: List[str]) -> str:
    return "\n\n".join(unit.strip() for unit in units if unit.strip()).strip()


def _extract_heading(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return None


def chunk_text(text: str, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[str]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    chunk_overlap = max(0, min(chunk_overlap, chunk_size // 3))
    blocks = _split_markdown_blocks(text)
    chunks: List[str] = []
    current_units: List[str] = []
    current_length = 0

    for block in blocks:
        block_parts = _split_large_block(block, chunk_size)
        for block_part in block_parts:
            separator_length = 2 if current_units else 0
            if current_units and current_length + len(block_part) + separator_length > chunk_size:
                chunks.append(_join_units(current_units))
                current_units = _retained_overlap(current_units, chunk_overlap)
                current_length = len(_join_units(current_units))

            if len(block_part) > chunk_size:
                if current_units:
                    chunks.append(_join_units(current_units))
                    current_units = []
                    current_length = 0
                chunks.append(block_part.strip())
                continue

            current_units.append(block_part)
            current_length = len(_join_units(current_units))

            if current_length >= chunk_size:
                chunks.append(_join_units(current_units))
                current_units = _retained_overlap(current_units, chunk_overlap)
                current_length = len(_join_units(current_units))

    if current_units:
        final_chunk = _join_units(current_units)
        if not chunks or chunks[-1] != final_chunk:
            chunks.append(final_chunk)

    return chunks


def chunk_document(document: Document, chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[Document]:
    text_chunks = chunk_text(document.text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    output: List[Document] = []
    current_heading = document.metadata.get("title")

    for index, chunk in enumerate(text_chunks, start=1):
        heading = _extract_heading(chunk)
        if heading:
            current_heading = heading
        metadata = {
            **document.metadata,
            "chunk_index": index,
            "chunk_size": len(chunk),
        }
        if current_heading:
            metadata["heading"] = current_heading
        output.append(Document(text=chunk, metadata=metadata))

    return output


def chunk_documents(documents: Iterable[Document], chunk_size: int = DEFAULT_CHUNK_SIZE, chunk_overlap: int = DEFAULT_CHUNK_OVERLAP) -> List[Document]:
    output: List[Document] = []
    for document in documents:
        output.extend(chunk_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return output
