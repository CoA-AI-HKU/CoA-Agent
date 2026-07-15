from __future__ import annotations

import logging
import re
from typing import Any

from src.citations import (
    classify_source,
    clean_internal_citations_from_text,
    finalize_user_facing_result,
    filter_user_facing_sources,
    source_display_value,
)


SOURCE_INTRO_PATTERNS = [
    r"根據資料庫(?:嘅資料|的資料)?[，,:：\s…]*",
    r"根據文件[，,:：\s…]*",
    r"根據資料[，,:：\s…]*",
    r"資料庫提到[，,:：\s…]*",
    r"資料庫冇提到[^。！？\n]*[。！？]?",
    r"資料庫嘅指引(?:係清楚嘅)?[：:\s]*",
    r"資料庫的指引(?:是清楚的)?[：:\s]*",
    r"文件嘅指引[，,:：\s…]*",
    r"文件提到[，,:：\s…]*",
    r"根據資料庫(?:嘅資料|的資料)?[，,:：\s…]*",
    r"根據文件[，,:：\s…]*",
    r"根據資料[，,:：\s…]*",
    r"資料庫提到[，,:：\s…]*",
    r"資料庫冇提到[^。！？\n]*[。！？]?",
    r"資料庫嘅指引(?:係清楚嘅)?[：:\s]*",
    r"資料庫的指引(?:是清楚的)?[：:\s]*",
    r"文件嘅指引[，,:：\s…]*",
    r"文件提到[，,:：\s…]*",
]
SOURCE_MARKER_PATTERNS = [
    r"（來源：[^）]*）",
    r"\(來源：[^)]*\)",
    r"（資料來源：[^）]*）",
    r"\(資料來源：[^)]*\)",
    r"（资料来源：[^）]*）",
    r"（來源：[^）]*）",
    r"\(來源：[^)]*\)",
    r"（資料來源：[^）]*）",
    r"\(資料來源：[^)]*\)",
    r"（资料来源：[^）]*）",
    r"\(Sources?:[^)]*\)",
]
INTERNAL_LEAKAGE_TERMS = [
    "keyword_search",
    "semantic_search",
    "chunk_read",
    "agentic_retrieve",
    "handle_dementia_user_message",
    "search_dementia_knowledge",
    "answer_from_dementia_knowledge",
    "mcp_",
    "MCP",
    "tool",
    "function",
    "函數",
    "工具",
    "調用",
    "呼叫工具",
    "查資料庫",
    "Chroma",
    "chroma",
    ".md",
    "來源：",
    "根據資料庫",
    "資料庫嘅指引",
    "RAG_DEBUG",
    "debug",
    "traceback",
    "exception",
    "RAG",
    "MCP",
    "mcp",
    "tool",
    "Tool",
    "function",
    "Function",
    "debug",
    "Debug",
    "traceback",
    "Traceback",
    "exception",
    "Exception",
    "來源",
    "資料來源",
    "根據資料庫",
    "根據文件",
    "資料庫",
    "文件提到",
    "工具",
    "函數",
    "調用",
    "呼叫工具",
    "查資料庫",
    "handle_incoming_message",
    "mcp_dementia",
    "chroma",
    "Chroma",
]
KNOWLEDGE_FAILURE_FALLBACK = (
    "我暫時未能從資料中找到足夠資料回答這個問題。"
    "你可以用簡單一句再問一次，或請家人、照顧者或相關專業人士協助確認。"
)
MEDICATION_FALLBACK = (
    "我不能判斷你是否適合服用這種藥物，也不能提供診斷、劑量或用藥決定。"
    "請先詢問醫生或藥劑師；不要自行加藥、停藥或改變劑量。"
)
SAFETY_FALLBACK = "這個情況可能需要即時協助。請先確保安全，並盡快聯絡家人、照顧者、醫護人員或緊急服務。"


SELF_MEMORY_CONCERN_FALLBACK = (
    "記不住事情會令人很困擾，也可能和壓力、睡眠不足、情緒、藥物、身體狀況或認知變化有關。"
    "你可以先用一些簡單方法幫自己：把重要事情寫下來、用手機提醒、把常用物品放在固定位置、每天保持規律作息。\n\n"
    "如果這種情況最近明顯變多、影響日常生活，或家人也有留意到，建議和醫生或醫護人員討論，找出原因。"
    "你也可以告訴我有什麼事情想記住，我可以幫你整理成簡單提醒。"
)
ADDITIONAL_BLOCKED_TERMS = [
    "keyword_search",
    "semantic_search",
    "chunk_read",
    "agentic_retrieve",
    "來源",
    ".md",
    "資料庫",
    "根據",
    "根據資料庫",
    "資料庫指出",
    "資料庫講到",
    "資料庫提到",
    "handle_dementia_user_message",
    "handle_incoming_message",
    "MCP",
    "RAG_DEBUG",
    "RAG",
    "你有腦退化症",
    "你嘅腦退化症",
    "你的腦退化症",
    "作為腦退化症患者",
    "病情嘅一部分",
    "病情的一部分",
    "你之前都問過",
    "你重複問",
    "腦退化症好常見",
    "腦退化症嘅一部分",
    "腦退化症的一部分",
]


def format_user_facing_answer(
    result: dict[str, Any],
    show_sources: bool = False,
    *,
    allow_external_citations: bool = True,
    allow_internal_citations: bool = False,
    show_unknown_sources: bool = False,
    debug_mode: bool = False,
) -> dict[str, Any]:
    """Return a messaging-friendly result while preserving internal evidence fields."""
    output = dict(result)
    answer = str(output.get("answer") or "").strip()
    debug = dict(output.get("debug", {}))
    if "raw_answer_before_formatting" not in debug:
        debug["raw_answer_before_formatting"] = answer

    medication_answer = _medication_safety_answer_if_needed(answer, output, debug)
    if medication_answer:
        answer = medication_answer
        effective_safety_level = "medical_boundary"
    else:
        effective_safety_level = output.get("safety_level")

    all_sources = list(output.get("sources") or [])
    internal_sources = [source for source in all_sources if classify_source(source) == "internal"]
    external_sources = [source for source in all_sources if classify_source(source) == "external"]
    user_facing_sources = filter_user_facing_sources(
        all_sources,
        allow_external_citations=allow_external_citations,
        allow_internal_citations=allow_internal_citations and debug_mode,
        show_unknown_sources=show_unknown_sources,
    )

    answer = clean_internal_citations_from_text(answer)
    answer = _clean_source_text(answer)
    answer = _compact_answer(answer, effective_safety_level)
    if not show_sources and _contains_user_visible_source_text(answer):
        debug["source_text_cleanup_retry"] = True
        answer = _clean_source_text(answer)
        answer = _compact_answer(answer, effective_safety_level)

    if show_sources and user_facing_sources:
        labels = list(dict.fromkeys(filter(None, (source_display_value(source) for source in user_facing_sources))))[:3]
        if labels:
            reference_label = "References" if str(output.get("answer_language") or "").startswith("en") else "參考"
            answer = f"{answer}\n\n{reference_label}：{' / '.join(labels)}"

    output["answer"] = answer
    output["answer_with_sources"] = answer
    output["user_facing_answer"] = answer
    output["show_sources"] = show_sources
    output["source_count"] = len(output.get("sources") or [])
    output["sources_available"] = bool(output.get("sources"))
    output["user_facing_sources"] = user_facing_sources
    output["internal_sources_hidden"] = bool(internal_sources) and not (allow_internal_citations and debug_mode)
    debug["user_facing_formatter_applied"] = True
    debug["show_sources"] = show_sources
    debug["source_count"] = output["source_count"]
    debug["internal_sources"] = internal_sources
    debug["external_sources"] = external_sources
    debug["source_text_removed"] = debug["raw_answer_before_formatting"] != answer
    output["debug"] = debug
    return finalize_user_facing_result(output)


def guard_user_facing_answer(result: dict[str, Any], message: str = "") -> dict[str, Any]:
    """Replace any user-visible implementation leakage with a safe fallback."""
    output = dict(result)
    answer = str(output.get("answer") or "")
    has_internal_leakage = _contains_internal_leakage(answer)
    has_unsupported_assumption = _contains_unsupported_dementia_assumption(answer, message)
    if not has_internal_leakage and not has_unsupported_assumption:
        return output

    debug = dict(output.get("debug", {}))
    if "raw_answer_before_output_guard" not in debug:
        debug["raw_answer_before_output_guard"] = answer
    debug["output_guard_applied"] = True
    debug["unsupported_dementia_assumption_removed"] = has_unsupported_assumption
    output["answer"] = _fallback_for_route(output, message)
    output["answer_with_sources"] = output["answer"]
    output["user_facing_answer"] = output["answer"]
    output["debug"] = debug
    logging.warning("Output guard removed internal leakage from user-facing answer")
    return output


def answer_has_user_visible_leakage(answer: str) -> bool:
    """Public predicate for final-channel checks before returning to Telegram/WhatsApp."""
    return _contains_internal_leakage(answer) or _contains_user_visible_source_text(answer)


def answer_has_user_visible_source_text(answer: str) -> bool:
    return _contains_user_visible_source_text(answer)


def _clean_source_text(answer: str) -> str:
    cleaned = clean_internal_citations_from_text(answer).strip()
    cleaned = _remove_cited_quote_blocks(cleaned)
    for pattern in SOURCE_INTRO_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    for pattern in SOURCE_MARKER_PATTERNS:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    kept_lines = []
    for line in cleaned.splitlines():
        stripped = line.strip()
        if not stripped:
            kept_lines.append("")
            continue
        if ".md" in stripped.lower():
            continue
        if re.match(r"^(來源|資料來源|资料来源|Sources?)\s*[:：]", stripped, flags=re.IGNORECASE):
            continue
        kept_lines.append(stripped)

    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return cleaned.strip(" ，,。")


def _remove_cited_quote_blocks(answer: str) -> str:
    lines = answer.splitlines()
    remove_indexes: set[int] = set()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not _is_source_line(stripped):
            continue
        remove_indexes.add(index)
        previous = index - 1
        while previous >= 0 and not lines[previous].strip():
            remove_indexes.add(previous)
            previous -= 1
        if previous >= 0 and _looks_like_quote_block(lines[previous].strip()):
            remove_indexes.add(previous)
            before_quote = previous - 1
            while before_quote >= 0 and not lines[before_quote].strip():
                remove_indexes.add(before_quote)
                before_quote -= 1

    kept = [line for index, line in enumerate(lines) if index not in remove_indexes]
    return "\n".join(kept)


def _is_source_line(line: str) -> bool:
    lowered = line.lower()
    return (
        ".md" in lowered
        or "來源：" in line
        or "（來源：" in line
        or "資料來源：" in line
        or "资料来源：" in line
        or "source:" in lowered
        or "sources:" in lowered
    )


def _looks_like_quote_block(line: str) -> bool:
    return (
        line.startswith("「")
        or line.endswith("」")
        or line.startswith('"')
        or line.startswith("'")
        or line.startswith("“")
        or line.startswith("‘")
    )


def _compact_answer(answer: str, safety_level: str | None) -> str:
    if not answer:
        return answer

    if safety_level in {"screening_check_in", "self_memory_concern", "memory_concern", "caregiver_observation_guidance"}:
        max_chars = 650
    elif safety_level in {"urgent_boundary", "medical_boundary"}:
        max_chars = 250
    else:
        max_chars = 120
    normalized = _remove_excess_numbering(answer)
    if len(normalized) <= max_chars:
        return normalized

    sentences = _split_sentences(normalized)
    if not sentences:
        return normalized[:max_chars].rstrip("，,。 .") + "。"

    selected: list[str] = []
    total = 0
    for sentence in sentences:
        if selected and total + len(sentence) > max_chars:
            break
        selected.append(sentence)
        total += len(sentence)
    if not selected:
        selected = [sentences[0][:max_chars].rstrip("，,。 .") + "。"]
    return "".join(selected).strip()


def _remove_excess_numbering(answer: str) -> str:
    lines = []
    for line in answer.splitlines():
        stripped = re.sub(r"^\s*(?:\d+[.)、]|[-*+])\s*", "", line.strip())
        if stripped:
            lines.append(stripped)
    return "\n".join(lines) if lines else answer.strip()


def _split_sentences(answer: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])\s*", answer.replace("\n", " "))
    return [part.strip() for part in parts if part.strip()]


def _contains_user_visible_source_text(answer: str) -> bool:
    if any(term in answer for term in ADDITIONAL_BLOCKED_TERMS):
        return True
    return any(
        phrase in answer
        for phrase in [
            "來源",
            ".md",
            "根據資料庫",
            "資料庫嘅指引",
            "資料庫的指引",
            "資料庫冇提到",
            "source:",
            "sources:",
        ]
    )


def _contains_internal_leakage(answer: str) -> bool:
    lowered = answer.lower()
    for term in ADDITIONAL_BLOCKED_TERMS:
        haystack = lowered if term.isascii() else answer
        needle = term.lower() if term.isascii() else term
        if needle in haystack:
            return True
    for term in INTERNAL_LEAKAGE_TERMS:
        haystack = lowered if term.isascii() else answer
        needle = term.lower() if term.isascii() else term
        if needle in haystack:
            return True
    return False


def _contains_unsupported_dementia_assumption(answer: str, message: str) -> bool:
    user_text = str(message or "").lower()
    answer_text = str(answer or "").lower()
    explicit_user_terms = (
        "腦退化",
        "脑退化",
        "認知障礙",
        "认知障碍",
        "失智",
        "dementia",
        "alzheimer",
        "mci",
    )
    answer_terms = explicit_user_terms
    user_explicitly_raised_topic = any(term in user_text for term in explicit_user_terms)
    answer_introduces_topic = any(term in answer_text for term in answer_terms)
    return answer_introduces_topic and not user_explicitly_raised_topic


def _fallback_for_route(result: dict[str, Any], message: str) -> str:
    safety_level = str(result.get("safety_level") or "")
    route = str(result.get("route") or "")
    intent = str(result.get("intent") or "")
    combined = f"{message}\n{result.get('answer', '')}"

    if safety_level == "urgent_boundary" or route == "safety" or intent == "safety_sensitive":
        return SAFETY_FALLBACK
    if route in {"memory_concern", "self_memory_concern"} or intent == "self_memory_concern" or _looks_like_self_memory_concern(message):
        return SELF_MEMORY_CONCERN_FALLBACK
    if (
        safety_level == "medical_boundary"
        or route == "medical_boundary"
        or intent == "medication_or_diagnosis"
        or _looks_like_medication_question(combined)
    ):
        return MEDICATION_FALLBACK
    return KNOWLEDGE_FAILURE_FALLBACK


def _looks_like_medication_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered
        for term in [
            "阿司匹林",
            "亞士匹靈",
            "阿士匹靈",
            "阿斯匹靈",
            "aspirin",
            "藥",
            "药",
            "止痛",
            "medicine",
            "medication",
            "dose",
        ]
    )


def _looks_like_self_memory_concern(text: str) -> bool:
    lowered = text.lower()
    return any(
        term in lowered
        for term in [
            "我最近覺得很多事情記不住",
            "我最近覺得很多事情好像都有點記不住",
            "我成日唔記得嘢",
            "最近記性差",
            "我好似忘記好多事",
            "我經常忘記事情",
            "記唔住",
            "記不住",
            "記性差",
            "記憶力變差",
            "忘記事情",
            "我是不是有腦退化症",
            "我是否有腦退化症",
            "我係咪有腦退化症",
            "i keep forgetting",
            "do i have dementia",
            "am i getting dementia",
        ]
    )


def _medication_safety_answer_if_needed(answer: str, result: dict[str, Any], debug: dict[str, Any]) -> str:
    if str(result.get("medication_status") or "").strip().lower() == "taken":
        return ""
    message = str(debug.get("user_message") or debug.get("message") or "")
    combined = f"{message}\n{answer}".lower()
    medication_terms = [
        "阿司匹林",
        "亞士匹靈",
        "阿士匹靈",
        "阿斯匹靈",
        "aspirin",
        "止痛藥",
        "止痛药",
        "非處方藥",
        "非处方药",
        "保健食品",
        "營養補充劑",
        "营养补充剂",
        "中成藥",
        "中成药",
        "藥",
        "药",
        "medicine",
        "medication",
        "supplement",
    ]
    decision_terms = ["該吃", "應該", "可唔可以", "可以食", "吃嗎", "食唔食", "take", "should"]
    if not any(term.lower() in combined for term in medication_terms):
        return ""
    if not any(term.lower() in combined for term in decision_terms) and result.get("safety_level") != "medical_boundary":
        return ""

    if any(term.lower() in combined for term in ["阿司匹林", "亞士匹靈", "阿士匹靈", "阿斯匹靈", "aspirin"]):
        return (
            "我不能判斷你是否適合吃阿司匹林。使用非處方藥前，請先詢問醫生或藥劑師；"
            "不要自行決定服用。如果頭痛突然很嚴重，或伴隨說話不清、手腳無力、胸痛、"
            "呼吸困難或視力改變，請立即求醫。"
        )

    return "我不能判斷你是否適合服用這種藥物或補充品。使用前請先詢問醫生或藥劑師；不要自行決定服用。"
