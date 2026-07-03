from __future__ import annotations

from src.agents.types import AgentDecision
from src.intent_router import classify_intent
from src.safety.medication_guard import is_medication_decision_question


def coordinate_message(message: str, user_id: str | None = None) -> AgentDecision:
    intent_result = classify_intent(message)

    if is_medication_decision_question(message):
        return AgentDecision(
            route="medical_boundary",
            intent="medication_or_diagnosis",
            confidence=max(intent_result.confidence, 0.95),
            matched_terms=intent_result.matched_terms,
            reason="Medication decision question detected by safety guard.",
            safety_override=True,
        )

    route_map = {
        "safety_sensitive": ("safety", False, True),
        "medication_or_diagnosis": ("medical_boundary", False, True),
        "knowledge_qa": ("rag_qa", True, False),
        "emotional_support": ("supportive", False, False),
        "personal_memory": ("memory", False, False),
        "reminder_request": ("routine", False, False),
        "cognitive_activity": ("activity", False, False),
        "unknown": ("unknown", False, False),
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
    )
