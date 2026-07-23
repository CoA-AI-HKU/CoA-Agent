from __future__ import annotations

from src.agents.types import AgentDecision
from src.intent_router import classify_intent
from src.safety.medication_guard import is_medication_decision_question


def infer_user_role(message: str) -> str:
    """Infer broad speaking context without diagnosing the user."""
    normalized = (message or "").strip().lower()
    if not normalized:
        return "unknown"

    caregiver_terms = [
        "媽媽",
        "媽咪",
        "爸爸",
        "爺爺",
        "嫲嫲",
        "奶奶",
        "公公",
        "婆婆",
        "老公",
        "老婆",
        "太太",
        "先生",
        "家人",
        "照顧",
        "照护",
        "caregiver",
        "carer",
        "my mother",
        "my father",
        "my parent",
        "my wife",
        "my husband",
        "family member",
    ]
    professional_terms = [
        "醫生",
        "護士",
        "社工",
        "治療師",
        "研究",
        "論文",
        "臨床",
        "doctor",
        "nurse",
        "clinician",
        "researcher",
        "study",
        "clinical",
    ]
    self_concern_terms = [
        "我有腦退化",
        "我有認知障礙",
        "我有mci",
        "醫生話我有腦退化",
        "醫生說我有腦退化",
        "醫生話我有認知障礙",
        "醫生說我有認知障礙",
        "醫生話我有mci",
        "醫生說我有mci",
        "我被診斷",
        "i have dementia",
        "i have mci",
        "i was diagnosed",
    ]
    general_terms = [
        "是什麼",
        "係咩",
        "是甚麼",
        "有什麼",
        "點解",
        "為什麼",
        "what is",
        "what are",
        "how does",
        "why",
    ]

    if any(term in normalized for term in caregiver_terms):
        return "caregiver_or_family"
    if any(term in normalized for term in self_concern_terms):
        return "self_with_cognitive_concern"
    if any(term in normalized for term in professional_terms):
        return "professional_or_researcher"
    if any(term in normalized for term in general_terms):
        return "general_user"
    return "unknown"


def coordinate_message(message: str, user_id: str | None = None) -> AgentDecision:
    intent_result = classify_intent(message)
    user_role = infer_user_role(message)

    if user_role == "self_with_cognitive_concern" and intent_result.intent == "self_memory_concern":
        return AgentDecision(
            route="rag_qa",
            intent="knowledge_qa",
            confidence=max(intent_result.confidence, 0.9),
            matched_terms=intent_result.matched_terms,
            reason="Explicit diagnosis context may use dementia support evidence.",
            rag_required=True,
            user_role=user_role,
        )

    if is_medication_decision_question(message):
        return AgentDecision(
            route="medical_boundary",
            intent="medication_or_diagnosis",
            confidence=max(intent_result.confidence, 0.95),
            matched_terms=intent_result.matched_terms,
            reason="Medication decision question detected by safety guard.",
            safety_override=True,
            user_role=user_role,
        )

    route_map = {
        "safety_sensitive": ("safety", False, True),
        "medication_or_diagnosis": ("medical_boundary", False, True),
        "role_correction": ("role_correction", False, False),
        "prompt_injection": ("prompt_injection", False, True),
        "self_memory_concern": ("memory_concern", False, False),
        "caregiver_support": ("caregiver_guidance", False, False),
        "cognitive_concern_screening": ("screening", False, False),
        "knowledge_qa": ("rag_qa", True, False),
        "emotional_support": ("supportive", False, False),
        "personal_memory": ("memory", False, False),
        "reminder_request": ("routine", False, False),
        "cognitive_activity": ("activity", False, False),
        "unknown": ("unknown", False, False),
        "general_conversation": ("general", False, False),
    }
    route, rag_required, safety_override = route_map.get(intent_result.intent, ("unknown", False, False))

    return AgentDecision(
        route=route,
        intent=intent_result.intent,
        confidence=intent_result.confidence,
        matched_terms=intent_result.matched_terms,
        reason=intent_result.reason,
        rag_required=rag_required,
        safety_override=safety_override,
        user_role=user_role,
    )
