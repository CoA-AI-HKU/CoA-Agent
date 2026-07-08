from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


UserRole = Literal[
    "unknown",
    "caregiver_or_family",
    "self_with_cognitive_concern",
    "professional_or_researcher",
    "general_user",
]


Route = Literal[
    "safety",
    "medical_boundary",
    "rag_qa",
    "memory",
    "routine",
    "activity",
    "supportive",
    "unknown",
]


@dataclass
class AgentDecision:
    route: Route
    intent: str
    confidence: float
    reason: str
    matched_terms: list[str] = field(default_factory=list)
    rag_required: bool = False
    safety_override: bool = False
    user_role: UserRole = "unknown"


@dataclass
class AgentResult:
    answer: str
    intent: str
    safety_level: str
    found: bool = False
    sources: list[Any] = field(default_factory=list)
    rag_called: bool = False
    route: str = "unknown"
    debug: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "answer": self.answer,
            "intent": self.intent,
            "safety_level": self.safety_level,
            "found": self.found,
            "sources": self.sources,
            "rag_called": self.rag_called,
            "route": self.route,
            "debug": self.debug,
        }
