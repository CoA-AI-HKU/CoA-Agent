from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .document import Document
from .language import detect_answer_language


def discover_markdown_files(markdown_root: Path) -> List[Path]:
    return sorted(markdown_root.rglob("*.md"))


def _extract_title(text: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped.removeprefix("# ").strip()
    return None


def load_markdown_documents(markdown_root: Path, source_type: str = "markdown") -> List[Document]:
    documents: List[Document] = []
    for path in discover_markdown_files(markdown_root):
        text = path.read_text(encoding="utf-8")
        title = _extract_title(text)
        metadata = {
            "source": str(path),
            "type": source_type,
            "language": detect_answer_language(text),
        }
        if title:
            metadata["title"] = title
        documents.append(
            Document(
                text=text,
                metadata=metadata,
            )
        )
    return documents
