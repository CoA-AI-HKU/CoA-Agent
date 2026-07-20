from __future__ import annotations

import re
from typing import Any

from src.agents.coordinator_agent import infer_user_role


OBVIOUS_TRADITIONAL_REPLACEMENTS = {
    "数据库": "資料庫",
    "资料库": "資料庫",
    "资料": "資料",
    "痴呆症": "腦退化症",
    "知识": "知識",
    "故障": "問題",
    "问题": "問題",
}


UNSUPPORTED_DEMENTIA_ASSUMPTION_REPLACEMENTS = {
    "因為你有腦退化症": "如果你或家人有相關情況",
    "因為你患有腦退化症": "如果你或家人有相關情況",
    "你有腦退化症": "如果你或家人有腦退化症",
    "你患有腦退化症": "如果你或家人有腦退化症",
    "你的腦退化症": "相關的腦退化症情況",
    "作為腦退化症患者": "如果這是關於腦退化症照顧",
    "作為一名腦退化症患者": "如果這是關於腦退化症照顧",
    "腦退化症人士都會遇到": "有些人可能會遇到",
    "因為你記性不好": "如果近期較難記住",
    "你的記憶力不好": "如果近期較難記住",
    "你有記憶力問題": "如果近期較難記住",
    "你有記憶問題": "如果近期較難記住",
    "你的記憶力衰退": "如果近期記憶有變化",
    "你有記憶力衰退": "如果近期記憶有變化",
    "你有記憶障礙": "如果近期記憶有變化",
    "因為你有記憶障礙": "如果近期記憶有變化",
    "你的照顧者": "家人、照顧者或醫護人員",
    "你的看護": "家人、照顧者或醫護人員",
    "你的護理員": "家人、照顧者或醫護人員",
    "你需要照顧者": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你需要看護": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你不能自己": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你唔可以自己": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你無能力": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你没有能力": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你沒有能力": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你不具備能力": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你不適合自己處理": "如有需要，可以請家人、照顧者或醫護人員協助",
    "你不适合自己处理": "如有需要，可以請家人、照顧者或醫護人員協助",
}


def _message_explicitly_supports_self_dementia_context(message: str) -> bool:
    normalized = (message or "").lower()
    explicit_terms = [
        "我有腦退化",
        "我患有腦退化",
        "醫生話我有腦退化",
        "醫生說我有腦退化",
        "我被診斷",
        "i have dementia",
        "i was diagnosed",
    ]
    return any(term in normalized for term in explicit_terms)


def remove_unsupported_dementia_assumptions(answer: str, message: str) -> tuple[str, bool]:
    user_role = infer_user_role(message)
    explicit_self_context = _message_explicitly_supports_self_dementia_context(message)
    rewritten = answer

    for source, replacement in UNSUPPORTED_DEMENTIA_ASSUMPTION_REPLACEMENTS.items():
        if source not in rewritten:
            continue
        if explicit_self_context and source in {
            "你有腦退化症",
            "你患有腦退化症",
            "你的腦退化症",
        }:
            continue
        rewritten = rewritten.replace(source, replacement)

    if user_role != "caregiver_or_family":
        rewritten = rewritten.replace("照顧你的家人", "家人、照顧者或醫護人員")

    return rewritten, rewritten != answer


def simplify_response(result: dict[str, Any], message: str, user_id: str | None = None) -> dict[str, Any]:
    output = dict(result)
    answer = str(output.get("answer") or "").strip()
    answer = re.sub(r"[ \t]+", " ", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer)

    if output.get("answer_language", "zh-Hant") == "zh-Hant":
        for source, replacement in OBVIOUS_TRADITIONAL_REPLACEMENTS.items():
            answer = answer.replace(source, replacement)

    if output.get("intent") == "role_correction":
        bias_guard_applied = False
    else:
        answer, bias_guard_applied = remove_unsupported_dementia_assumptions(answer, message)

    if len(answer) > 220 and output.get("safety_level") not in {
        "urgent_boundary",
        "medical_boundary",
        "screening_check_in",
        "memory_concern",
        "self_memory_concern",
        "caregiver_observation_guidance",
    }:
        paragraphs = [part.strip() for part in answer.split("\n\n") if part.strip()]
        if len(paragraphs) > 2:
            answer = "\n\n".join(paragraphs[:2])
        elif len(answer) > 220:
            answer = answer[:220].rstrip("，,。 .") + "。"

    output["answer"] = answer
    if "answer_with_sources" in output and isinstance(output.get("answer_with_sources"), str):
        answer_with_sources, sources_bias_guard_applied = remove_unsupported_dementia_assumptions(
            output["answer_with_sources"], message
        )
        output["answer_with_sources"] = answer_with_sources
        bias_guard_applied = bias_guard_applied or sources_bias_guard_applied

    debug = dict(output.get("debug", {}))
    debug["simplifier_applied"] = True
    debug["bias_guard_applied"] = bias_guard_applied
    output["debug"] = debug
    return output
