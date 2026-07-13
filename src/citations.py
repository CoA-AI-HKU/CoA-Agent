from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse


INTERNAL_TYPES = {"internal", "rag", "local_file", "knowledge_base"}
EXTERNAL_TYPES = {"web", "url", "external", "public_web"}
INTERNAL_PATH_MARKERS = ("data/mds", ".chroma", "/mnt/", "/home/", "\\users\\", "\\documents\\")
DATABASE_PHRASES = (
    "根據資料庫嘅資料", "根據資料庫的資料", "根据资料库的资料", "根據資料庫", "根据资料库",
    "資料庫有提到", "資料庫提到", "资料库有提到", "资料库提到", "資料庫嘅指引", "資料庫的指引",
    "根據文件", "根据文件", "文件提到",
)


def classify_source(source: dict[str, Any] | str) -> str:
    metadata = source if isinstance(source, dict) else {}
    source_type = _source_type(metadata)
    if source_type in INTERNAL_TYPES:
        return "internal"
    value = _source_value(source)
    lowered = value.strip().lower().replace("\\", "/")
    if (
        ".md" in lowered
        or any(marker in lowered for marker in INTERNAL_PATH_MARKERS)
        or lowered.startswith(("/", "file://"))
        or re.match(r"^[a-z]:[/\\]", value.strip(), flags=re.IGNORECASE)
    ):
        return "internal"
    if source_type in EXTERNAL_TYPES:
        return "external"
    if lowered.startswith(("http://", "https://")):
        return "external"
    if not lowered:
        return "unknown"
    return "unknown"


def filter_user_facing_sources(
    sources: list[Any],
    allow_external_citations: bool = True,
    allow_internal_citations: bool = False,
    show_unknown_sources: bool = False,
) -> list[Any]:
    visible: list[Any] = []
    for source in sources or []:
        category = classify_source(source)
        if category == "external" and allow_external_citations:
            visible.append(source)
        elif category == "internal" and allow_internal_citations:
            visible.append(source)
        elif category == "unknown" and show_unknown_sources:
            visible.append(source)
    return visible


def clean_internal_citations_from_text(answer: str) -> str:
    """Remove internal evidence language and paths while preserving public URLs."""
    cleaned = str(answer or "")
    for phrase in DATABASE_PHRASES:
        cleaned = cleaned.replace(phrase, "")

    kept: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        if _line_has_internal_reference(stripped):
            without_parenthetical = re.sub(
                r"[（(](?:來源|来源|資料來源|资料来源|source)s?\s*[:：][^）)]*(?:\.md|data/mds|\.chroma|/mnt/|/home/)[^）)]*[）)]",
                "",
                stripped,
                flags=re.IGNORECASE,
            ).strip()
            if without_parenthetical and not _line_has_internal_reference(without_parenthetical):
                kept.append(without_parenthetical)
            continue
        kept.append(stripped)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip(" ，,。\n")


def source_display_value(source: Any) -> str:
    value = _source_value(source)
    if classify_source(source) != "external":
        return ""
    if isinstance(source, dict):
        label = source.get("title") or source.get("name") or source.get("domain")
        if label:
            return str(label).strip()
    try:
        host = urlparse(value).netloc.removeprefix("www.")
    except ValueError:
        host = ""
    return host or value


def _source_type(metadata: dict[str, Any]) -> str:
    nested = metadata.get("metadata") if isinstance(metadata.get("metadata"), dict) else {}
    value = metadata.get("source_type") or metadata.get("type") or nested.get("source_type") or nested.get("type")
    return str(value or "").strip().lower()


def _source_value(source: Any) -> str:
    if isinstance(source, str):
        return source
    if isinstance(source, dict):
        nested = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
        for key in ("url", "href", "source", "path", "filename", "id"):
            value = source.get(key) or nested.get(key)
            if value:
                return str(value)
    return str(source or "")


def _line_has_internal_reference(line: str) -> bool:
    lowered = line.lower().replace("\\", "/")
    if "http://" in lowered or "https://" in lowered:
        urls = re.findall(r"https?://\S+", line, flags=re.IGNORECASE)
        remainder = line
        for url in urls:
            remainder = remainder.replace(url, "")
        lowered = remainder.lower().replace("\\", "/")
    return (
        ".md" in lowered
        or "data/mds" in lowered
        or ".chroma" in lowered
        or "/mnt/" in lowered
        or "/home/" in lowered
        or lowered.strip().startswith(("/", "file://"))
        or bool(re.search(r"[a-z]:[/\\]", line, flags=re.IGNORECASE))
    )
