from __future__ import annotations

import re
from typing import Any

from src.meds.medicine_normalizer import normalize_medicine_mentions

from .retrieval_tools import chunk_read, keyword_search, semantic_search


NO_RETRIEVAL_ROUTES = {
    "system_command", "account_management",
}
MEMORY_ROUTES = {"memory_concern", "self_memory_concern"}
MEDICAL_ROUTES = {"medical_boundary", "medication_or_diagnosis"}
KNOWLEDGE_ROUTES = {
    "dementia_qa", "knowledge_qa", "rag_qa", "caregiver_guidance", "caregiver_support",
}
QUERY_STOPWORDS = {
    "about", "are", "can", "could", "does", "for", "from", "have", "how", "should",
    "that", "the", "this", "what", "when", "where", "which", "with", "would", "you", "your",
}
EXACT_DOMAIN_TERMS = (
    "dementia", "alzheimer", "腦退化症", "脑退化症", "認知障礙", "认知障碍", "失智症",
    "走失", "遊走", "游走", "症狀", "症状", "照顧者", "照顾者",
)


def _keywords(question: str) -> list[str]:
    terms: list[str] = []
    for medicine in normalize_medicine_mentions(question):
        terms.extend([str(medicine.get("matched_alias") or ""), str(medicine.get("canonical_name") or "")])
    for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,31}", question):
        if term.casefold() not in QUERY_STOPWORDS:
            terms.append(term)
    lowered = question.casefold()
    terms.extend(term for term in EXACT_DOMAIN_TERMS if term.casefold() in lowered)
    cjk = "".join(re.findall(r"[\u3400-\u9fff]", question))
    if 2 <= len(cjk) <= 16:
        terms.append(cjk)
    elif cjk:
        terms.extend(re.findall(r"[\u3400-\u9fff]{2,8}", question))
    return list(dict.fromkeys(term.strip() for term in terms if term.strip()))[:8]


def _question_terms(text: str) -> set[str]:
    latin = {
        term.casefold()
        for term in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text)
        if term.casefold() not in QUERY_STOPWORDS
    }
    cjk = re.findall(r"[\u3400-\u9fff]", text)
    latin.update("".join(cjk[index : index + 2]) for index in range(len(cjk) - 1))
    return latin


def evidence_sufficiency_check(question: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """Require topical overlap and substantive content before generation."""
    question_terms = _question_terms(question)
    supported: list[str] = []
    reasons: list[str] = []
    for item in evidence:
        text = str(item.get("text") or item.get("snippet") or "").strip()
        # CJK evidence can be substantively complete in far fewer characters
        # than equivalent English prose.
        min_length = 10 if re.search(r"[\u3400-\u9fff]", text) else 24
        if len(text) < min_length:
            continue
        evidence_terms = _question_terms(text)
        shared = question_terms & evidence_terms
        score = float(item.get("score") or 0.0)
        if shared or score >= 0.55 or (not question_terms and score >= 0.5):
            supported.append(str(item.get("chunk_id") or ""))
            reasons.append(f"{len(shared)} shared topical term(s)")
    supported = [value for value in dict.fromkeys(supported) if value]
    sufficient = bool(supported)
    return {
        "sufficient": sufficient,
        "reason": "; ".join(reasons[:3]) if sufficient else "Retrieved text does not directly support the question.",
        "supporting_chunk_ids": supported,
    }


def _merge_candidates(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for group in groups:
        for item in group:
            chunk_id = str(item.get("chunk_id") or "")
            if not chunk_id:
                continue
            existing = merged.get(chunk_id)
            if existing is None or float(item.get("score") or 0.0) > float(existing.get("score") or 0.0):
                merged[chunk_id] = dict(item)
    return sorted(merged.values(), key=lambda item: float(item.get("score") or 0.0), reverse=True)


def agentic_retrieve(
    question: str,
    route: str,
    max_steps: int = 3,
    *,
    rag_agent: Any = None,
    answer_top_k: int = 3,
    search_top_k: int = 5,
) -> dict[str, Any]:
    """Perform bounded, route-aware search and return evidence rather than an answer."""
    normalized_route = str(route or "unknown")
    step_limit = min(max(int(max_steps), 0), 3)
    log: dict[str, Any] = {
        "route": normalized_route,
        "requires_retrieval": normalized_route not in NO_RETRIEVAL_ROUTES,
        "rewritten_query": question,
        "tools_used": [],
        "keyword_queries": [],
        "semantic_queries": [],
        "chunks_read": [],
        "evidence_sufficient": False,
        "retrieval_failed": False,
        "answer_used_rag": False,
    }
    empty_check = evidence_sufficiency_check(question, [])
    if step_limit == 0 or normalized_route in NO_RETRIEVAL_ROUTES or rag_agent is None:
        log["retrieval_failed"] = normalized_route not in NO_RETRIEVAL_ROUTES
        return {"evidence": [], "sufficiency": empty_check, "retrieval_log": log}

    # Medical routes are normally intercepted before this layer. If called
    # directly, cap them to one snippet-stage search and never read full text.
    if normalized_route in MEDICAL_ROUTES:
        keywords = _keywords(question)[:4]
        matches = keyword_search(keywords, top_k=2, vector_store=rag_agent.vector_store) if keywords else []
        if keywords:
            log["tools_used"].append("keyword_search")
            log["keyword_queries"].append(keywords)
        check = evidence_sufficiency_check(question, matches)
        log["evidence_sufficient"] = check["sufficient"]
        log["retrieval_failed"] = not bool(matches)
        return {"evidence": matches, "sufficiency": check, "retrieval_log": log}

    keywords = _keywords(question)
    keyword_matches: list[dict[str, Any]] = []
    semantic_matches: list[dict[str, Any]] = []
    steps = 0
    if keywords and steps < step_limit:
        keyword_matches = keyword_search(
            keywords,
            top_k=min(max(search_top_k, 1), 20),
            vector_store=rag_agent.vector_store,
        )
        log["tools_used"].append("keyword_search")
        log["keyword_queries"].append(keywords)
        steps += 1

    if steps < step_limit and (normalized_route in KNOWLEDGE_ROUTES or not keyword_matches):
        semantic_matches = semantic_search(
            question,
            top_k=min(max(search_top_k, 1), 20),
            rag_agent=rag_agent,
        )
        log["tools_used"].append("semantic_search")
        log["semantic_queries"].append(question)
        steps += 1

    candidates = _merge_candidates(keyword_matches, semantic_matches)
    if normalized_route in MEMORY_ROUTES:
        candidates = candidates[:1]
    read_limit = 1 if normalized_route in MEMORY_ROUTES else min(max(answer_top_k, 1), 3)
    tracker: dict[str, Any] = {"read_chunks": set()}
    evidence: list[dict[str, Any]] = []
    if candidates and steps < step_limit:
        selected_ids = [str(item["chunk_id"]) for item in candidates[:read_limit]]
        evidence = chunk_read(selected_ids, tracker, vector_store=rag_agent.vector_store)
        candidate_by_id = {str(item["chunk_id"]): item for item in candidates}
        for item in evidence:
            item["score"] = float(candidate_by_id.get(str(item["chunk_id"]), {}).get("score") or 0.0)
            item["snippet"] = str(candidate_by_id.get(str(item["chunk_id"]), {}).get("snippet") or "")
        log["tools_used"].append("chunk_read")
        log["chunks_read"] = [str(item["chunk_id"]) for item in evidence]

    check = evidence_sufficiency_check(question, evidence)
    log["evidence_sufficient"] = check["sufficient"]
    log["retrieval_failed"] = not bool(candidates) or not bool(evidence)
    log["answer_used_rag"] = check["sufficient"]
    return {"evidence": evidence, "sufficiency": check, "retrieval_log": log}
