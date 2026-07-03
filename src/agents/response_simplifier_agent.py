from __future__ import annotations

import re
from typing import Any


OBVIOUS_TRADITIONAL_REPLACEMENTS = {
    "数据库": "資料庫",
    "资料库": "資料庫",
    "资料": "資料",
    "痴呆症": "腦退化症",
    "知识": "知識",
    "故障": "問題",
    "问题": "問題",
}


def simplify_response(result: dict[str, Any], message: str, user_id: str | None = None) -> dict[str, Any]:
    output = dict(result)
    answer = str(output.get("answer") or "").strip()
    answer = re.sub(r"[ \t]+", " ", answer)
    answer = re.sub(r"\n{3,}", "\n\n", answer)

    if output.get("answer_language", "zh-Hant") == "zh-Hant":
        for source, replacement in OBVIOUS_TRADITIONAL_REPLACEMENTS.items():
            answer = answer.replace(source, replacement)

    if len(answer) > 220 and output.get("safety_level") not in {"urgent_boundary", "medical_boundary"}:
        paragraphs = [part.strip() for part in answer.split("\n\n") if part.strip()]
        if len(paragraphs) > 2:
            answer = "\n\n".join(paragraphs[:2])
        elif len(answer) > 220:
            answer = answer[:220].rstrip("，,。 .") + "。"

    output["answer"] = answer
    if "answer_with_sources" in output and output.get("sources"):
        output["answer_with_sources"] = output["answer_with_sources"]

    debug = dict(output.get("debug", {}))
    debug["simplifier_applied"] = True
    output["debug"] = debug
    return output
