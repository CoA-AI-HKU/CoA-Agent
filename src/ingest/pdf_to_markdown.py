from __future__ import annotations

import re
from pathlib import Path
from typing import List

from ..pipeline.document import Document


def _normalize_whitespace(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def convert_text_to_markdown(text: str) -> str:
    """Convert extracted PDF text into a simple markdown-style form."""
    text = _normalize_whitespace(text)
    lines = []

    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue

        if re.match(r"^\s*[-–—*+]\s+", line):
            lines.append(stripped)
        elif re.match(r"^\s*\d+\.\s+", line):
            lines.append(stripped)
        elif re.match(r"^\s*[A-Z][^\n]{0,80}:$", line):
            lines.append(f"## {stripped}")
        else:
            lines.append(stripped)

    markdown = "\n".join(lines)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def _extract_text_with_pymupdf(path: Path) -> List[str]:
    try:
        import fitz
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for PDF extraction. Install it with `pip install pymupdf`."
        ) from exc

    document = fitz.open(path)
    pages = []
    for page_number in range(len(document)):
        page = document.load_page(page_number)
        page_text = page.get_text("text")
        pages.append(page_text)
    return pages


def _extract_text_with_pypdf(path: Path) -> List[str]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError(
            "pypdf is required for PDF extraction. Install it with `pip install pypdf`."
        ) from exc

    reader = PdfReader(path)
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return pages


def _extract_pdf_pages(path: Path) -> List[str]:
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file path, got: {path}")

    try:
        return _extract_text_with_pymupdf(path)
    except ImportError:
        return _extract_text_with_pypdf(path)


def load_pdf_pages_as_markdown_documents(path: Path) -> List[Document]:
    """Load a PDF and return one markdown document per page."""
    pages = _extract_pdf_pages(path)
    documents: List[Document] = []

    for page_index, page_text in enumerate(pages, start=1):
        markdown = convert_text_to_markdown(page_text)
        documents.append(
            Document(
                text=markdown,
                metadata={
                    "source": str(path),
                    "type": "pdf",
                    "page": page_index,
                    "page_count": len(pages),
                },
            )
        )

    return documents


def load_pdf_as_markdown(path: Path) -> Document:
    """Load a PDF and return a single markdown document for the whole file."""
    page_documents = load_pdf_pages_as_markdown_documents(path)
    text = "\n\n".join(page.text for page in page_documents if page.text)
    metadata = dict(page_documents[0].metadata) if page_documents else {}
    metadata["page_count"] = len(page_documents)
    return Document(text=text, metadata=metadata)
