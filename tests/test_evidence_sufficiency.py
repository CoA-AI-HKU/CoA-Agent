from __future__ import annotations

from src.agents.user_facing_formatter import guard_user_facing_answer
from src.rag.agentic_retriever import evidence_sufficiency_check


def test_relevant_chunks_are_sufficient_and_keep_internal_ids() -> None:
    check = evidence_sufficiency_check(
        "What can dementia affect?",
        [{"chunk_id": "chunk-1", "text": "Dementia can affect memory, thinking, and daily activities.", "score": 0.8}],
    )
    assert check["sufficient"] is True
    assert check["supporting_chunk_ids"] == ["chunk-1"]


def test_unrelated_and_empty_chunks_are_insufficient() -> None:
    unrelated = evidence_sufficiency_check(
        "What can dementia affect?",
        [{"chunk_id": "weather", "text": "Rain is expected in Paris tomorrow afternoon.", "score": 0.1}],
    )
    assert unrelated["sufficient"] is False
    assert evidence_sufficiency_check("What can dementia affect?", [])["sufficient"] is False


def test_weak_medication_evidence_uses_medication_fallback() -> None:
    guarded = guard_user_facing_answer(
        {
            "answer": "debug: weak evidence from chunk_read",
            "route": "medical_boundary",
            "intent": "medication_or_diagnosis",
            "safety_level": "medical_boundary",
            "debug": {},
        },
        "Can I take aspirin?",
    )
    assert "doctor" in guarded["answer"].lower() or "pharmacist" in guarded["answer"].lower() or "醫生" in guarded["answer"]
    assert "chunk_read" not in guarded["answer"]


def test_weak_safety_evidence_uses_urgent_fallback() -> None:
    guarded = guard_user_facing_answer(
        {
            "answer": "traceback from semantic_search",
            "route": "safety",
            "intent": "safety_sensitive",
            "safety_level": "urgent_boundary",
            "debug": {},
        },
        "My mother is missing",
    )
    assert "emergency" in guarded["answer"].lower() or "緊急" in guarded["answer"]
    assert "semantic_search" not in guarded["answer"]


def test_supporting_chunk_ids_never_enter_user_answer() -> None:
    check = evidence_sufficiency_check(
        "What is dementia?",
        [{"chunk_id": "secret-chunk-7", "text": "Dementia affects memory and thinking.", "score": 0.9}],
    )
    result = guard_user_facing_answer(
        {"answer": "Dementia can affect memory and thinking.", "route": "rag_qa", "intent": "knowledge_qa", "debug": {"evidence": check}},
        "What is dementia?",
    )
    assert "secret-chunk-7" not in result["answer"]

