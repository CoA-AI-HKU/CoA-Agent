from __future__ import annotations

import logging
import os
import unicodedata
from functools import lru_cache
from typing import Any


_FALLBACK_S2T = str.maketrans({
    "脑": "腦", "么": "麼", "麽": "麼", "认": "認", "知": "知",
    "障": "障", "碍": "礙", "症": "症", "语": "語", "记": "記",
    "忆": "憶", "护": "護", "顾": "顧", "为": "為", "与": "與",
})


@lru_cache(maxsize=1)
def _opencc_converter() -> Any | None:
    try:
        from opencc import OpenCC

        return OpenCC("s2t")
    except (ImportError, OSError, RuntimeError):
        return None


def normalize_retrieval_query(value: str) -> str:
    """Canonicalize Chinese variants for retrieval only."""
    normalized = unicodedata.normalize("NFKC", str(value or ""))
    converter = _opencc_converter()
    if converter is not None:
        normalized = converter.convert(normalized)
    else:
        normalized = normalized.translate(_FALLBACK_S2T)
    normalized = normalized.replace("麽", "麼").replace("么", "麼")
    # Mainland usage often omits 症 in this exact disease-name question;
    # canonicalize only this retrieval phrase, never the original message.
    normalized = normalized.replace("腦退化是什麼", "腦退化症是什麼")
    return normalized


def log_string_diagnostic(
    logger: logging.Logger,
    event: str,
    value: str,
    **fields: Any,
) -> None:
    text = str(value or "")
    details = " ".join(f"{key}={item!r}" for key, item in fields.items())
    codepoints = ""
    if os.getenv("RAG_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}:
        codepoints = f" unicode_code_points={[f'U+{ord(char):04X}' for char in text[:200]]!r}"
    logger.info(
        "%s string_preview=%r string_length=%d%s%s",
        event, text[:200], len(text), codepoints, f" {details}" if details else "",
    )
