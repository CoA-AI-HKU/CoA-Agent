from __future__ import annotations

import logging
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
logger = logging.getLogger(__name__)


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
    had_internal_reference = _text_has_internal_reference(cleaned)
    for phrase in DATABASE_PHRASES:
        cleaned = cleaned.replace(phrase, "")

    kept: list[str] = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue

        # Preserve useful prose when a model appends an internal citation on
        # the same line, then reject the line if any unsafe reference remains.
        stripped = re.sub(
            r"[（(](?:來源|来源|資料來源|资料来源|source)s?\s*[:：][^）)]*?\.md[^）)]*[）)]",
            "",
            stripped,
            flags=re.IGNORECASE,
        ).strip()
        if not stripped:
            continue
        if _line_has_internal_reference(stripped):
            continue
        kept.append(stripped)
    cleaned = "\n".join(kept)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    trim_chars = " ，,。\n" if had_internal_reference else " ，,\n"
    return cleaned.strip(trim_chars)


def finalize_user_facing_result(result: dict[str, Any]) -> dict[str, Any]:
    """Enforce the final citation boundary while retaining internal evidence."""
    output = dict(result)
    answer_before = str(output.get("answer") or "")
    logger.info(
        "rag_diagnostic event=citation_finalizer_started answer_before_length=%d answer_before_preview=%r",
        len(answer_before), answer_before[:300],
    )
    all_sources = list(output.get("sources") or [])
    internal_sources = [source for source in all_sources if classify_source(source) == "internal"]
    external_sources = [source for source in all_sources if classify_source(source) == "external"]
    removed_internal_text = False

    for field in ("answer", "answer_with_sources", "user_facing_answer"):
        if field not in output:
            continue
        original = str(output.get(field) or "")
        cleaned = clean_internal_citations_from_text(original)
        if cleaned != original.strip() and _text_has_internal_reference(original):
            removed_internal_text = True
        output[field] = cleaned

    # Public aliases must never retain a stale, pre-cleaning source-appended
    # answer. The full source list and debug payload remain unchanged.
    if "answer" in output:
        answer = str(output.get("answer") or "")
        output["answer_with_sources"] = answer
        output["user_facing_answer"] = answer

    output["user_facing_sources"] = external_sources
    output["internal_sources_hidden"] = bool(internal_sources or removed_internal_text)
    answer_after = str(output.get("answer") or "")
    if answer_before.strip() and not answer_after.strip():
        logger.warning(
            "rag_diagnostic event=fallback_candidate reason_code=citation_finalizer_rejected "
            "answer_before_length=%d answer_after_length=%d",
            len(answer_before), len(answer_after),
        )
    logger.info(
        "rag_diagnostic event=citation_finalizer_completed answer_after_length=%d answer_after_preview=%r",
        len(answer_after), answer_after[:300],
    )
    return output


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
    parts = line.strip().split(maxsplit=1)
    if not parts:
        return False
    command = parts[0].lower()
    if command in {
        "\\summary", "\\alerts", "\\set_routine", "\\set_reminder", "\\help",
        "\\register", "\\paircode", "\\link", "\\relink", "\\unlink",
        "\\dashboard", "\\clearhistory", "\\accountcommands", "\\whichroleami",
        "/start", "\\initiate",
        "\\send_screening", "\\start_check",
    }:
        return False
    lowered = line.lower().replace("\\", "/")
    reference_text = line
    # Explicit internal markers are never public output, including when
    # embedded in an otherwise URL-shaped string.
    if any(marker in lowered for marker in (".md", "data/mds", ".chroma", "/mnt/", "/home/", "file://")):
        return True
    if "http://" in lowered or "https://" in lowered:
        urls = re.findall(r"https?://\S+", line, flags=re.IGNORECASE)
        remainder = line
        for url in urls:
            remainder = remainder.replace(url, "")
        lowered = remainder.lower().replace("\\", "/")
        reference_text = remainder
    return (
        lowered.strip().startswith("/")
        or bool(re.search(r"(?<![a-z0-9])[a-z]:[/\\]", reference_text, flags=re.IGNORECASE))
    )


def _text_has_internal_reference(text: str) -> bool:
    return any(_line_has_internal_reference(line) for line in str(text or "").splitlines())
