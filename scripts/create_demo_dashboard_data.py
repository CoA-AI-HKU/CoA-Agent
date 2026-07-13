from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


EVENTS_PATH = Path.home() / ".nanobot" / "data" / "private" / "events.jsonl"


def main() -> None:
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    events = _demo_events()
    with EVENTS_PATH.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    print(f"Created demo dashboard data: {EVENTS_PATH}")
    print("To generate demo data:")
    print("python scripts/create_demo_dashboard_data.py")
    print("To run dashboard:")
    print("streamlit run src/dashboard.py")


def _demo_events() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    events: list[dict[str, Any]] = []
    for day_offset in range(7):
        timestamp = now - timedelta(days=day_offset)
        events.extend(
            [
                _event(
                    timestamp,
                    "patient_001",
                    event_type="interaction",
                    intent="daily_support",
                    route="supportive",
                    channel="whatsapp",
                ),
                _event(
                    timestamp - timedelta(hours=1),
                    "patient_001",
                    event_type="mood_check",
                    intent="emotional_support",
                    route="supportive",
                    score=4 if day_offset < 4 else 3,
                ),
                _event(
                    timestamp - timedelta(hours=2),
                    "patient_001",
                    event_type="activity_score",
                    intent="cognitive_activity",
                    route="activity",
                    score=4 if day_offset % 2 == 0 else 3,
                    exercise_type="word_recall",
                ),
                _event(
                    timestamp - timedelta(hours=3),
                    "patient_001",
                    event_type="medication_response",
                    intent="medication_reminder",
                    route="routine",
                    medication_status="taken" if day_offset != 5 else "missed",
                ),
            ]
        )

    events.append(
        _event(
            now - timedelta(days=1, hours=4),
            "patient_001",
            event_type="medication_uncertainty",
            intent="medication_or_diagnosis",
            route="medical_boundary",
            risk_level="medical_boundary",
            medication_status="unsure",
            event_value=True,
            rag_called=False,
        )
    )
    events.append(
        _event(
            now - timedelta(days=2, hours=2),
            "patient_001",
            event_type="wandering_safety",
            intent="safety",
            route="safety",
            risk_level="urgent_boundary",
            safety_level="urgent_boundary",
            event_value=True,
            rag_called=False,
        )
    )
    events.extend(
        [
            _event(
                now - timedelta(days=6),
                "patient_001",
                event_type="cognitive_check_completed",
                intent="cognitive_activity",
                route="activity",
                check_version="simple_cognitive_check_v1",
                total_score=14,
                max_score=15,
                risk_flag="normal",
                domain_scores={
                    "orientation": 2,
                    "immediate_recall": 3,
                    "attention": 3,
                    "category_fluency": 3,
                    "delayed_recall": 2,
                    "safety_reasoning": 1,
                },
                raw_answers_saved=False,
            ),
            _event(
                now - timedelta(days=3),
                "patient_001",
                event_type="cognitive_check_completed",
                intent="cognitive_activity",
                route="activity",
                check_version="simple_cognitive_check_v1",
                total_score=10,
                max_score=15,
                risk_flag="monitor",
                domain_scores={
                    "orientation": 1,
                    "immediate_recall": 3,
                    "attention": 2,
                    "category_fluency": 2,
                    "delayed_recall": 1,
                    "safety_reasoning": 1,
                },
                raw_answers_saved=False,
            ),
            _event(
                now - timedelta(days=1),
                "patient_001",
                event_type="cognitive_check_completed",
                intent="cognitive_activity",
                route="activity",
                check_version="simple_cognitive_check_v1",
                total_score=7,
                max_score=15,
                risk_flag="follow_up_suggested",
                domain_scores={
                    "orientation": 1,
                    "immediate_recall": 2,
                    "attention": 1,
                    "category_fluency": 1,
                    "delayed_recall": 1,
                    "safety_reasoning": 1,
                },
                raw_answers_saved=False,
            ),
            _event(
                now - timedelta(hours=8),
                "patient_001",
                event_type="memory_concern",
                intent="self_memory_concern",
                route="memory_concern",
                event_value=True,
            ),
            _event(
                now - timedelta(days=1, hours=8),
                "patient_001",
                event_type="memory_concern",
                intent="self_memory_concern",
                route="memory_concern",
                event_value=True,
            ),
            _event(
                now - timedelta(days=2, hours=8),
                "patient_001",
                event_type="orientation_confusion",
                intent="cognitive_concern_screening",
                route="screening",
                event_value=True,
            ),
        ]
    )

    for day_offset in range(5):
        timestamp = now - timedelta(days=day_offset)
        events.extend(
            [
                _event(
                    timestamp - timedelta(minutes=30),
                    "patient_002",
                    event_type="interaction",
                    intent="knowledge_qa",
                    route="rag_qa",
                    channel="telegram",
                    rag_called=True,
                ),
                _event(
                    timestamp - timedelta(hours=1, minutes=30),
                    "patient_002",
                    event_type="mood_check",
                    intent="emotional_support",
                    route="supportive",
                    score=3 if day_offset < 3 else 2,
                ),
                _event(
                    timestamp - timedelta(hours=2, minutes=30),
                    "patient_002",
                    event_type="activity_score",
                    intent="cognitive_activity",
                    route="activity",
                    score=3,
                    exercise_type="orientation",
                ),
                _event(
                    timestamp - timedelta(hours=3, minutes=30),
                    "patient_002",
                    event_type="medication_response",
                    intent="medication_reminder",
                    route="routine",
                    medication_status="taken" if day_offset in {0, 2, 4} else "unsure",
                ),
            ]
        )
    return sorted(events, key=lambda event: event["timestamp"])


def _event(
    timestamp: datetime,
    user_id: str,
    *,
    event_type: str,
    intent: str,
    route: str,
    role: str = "user",
    channel: str = "whatsapp",
    risk_level: str | None = None,
    safety_level: str = "normal",
    rag_called: bool = False,
    event_value: bool | int | float | str | None = None,
    score: int | float | None = None,
    exercise_type: str | None = None,
    medication_status: str | None = None,
    check_version: str | None = None,
    total_score: int | float | None = None,
    max_score: int | float | None = None,
    risk_flag: str | None = None,
    domain_scores: dict[str, int | float] | None = None,
    raw_answers_saved: bool | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "timestamp": timestamp.isoformat(),
        "user_id": user_id,
        "role": role,
        "channel": channel,
        "intent": intent,
        "route": route,
        "risk_level": risk_level,
        "safety_level": safety_level,
        "rag_called": rag_called,
        "event_type": event_type,
    }
    if event_value is not None:
        event["event_value"] = event_value
    if score is not None:
        event["score"] = score
    if exercise_type:
        event["exercise_type"] = exercise_type
    if medication_status:
        event["medication_status"] = medication_status
    if check_version:
        event["check_version"] = check_version
    if total_score is not None:
        event["total_score"] = total_score
    if max_score is not None:
        event["max_score"] = max_score
    if risk_flag:
        event["risk_flag"] = risk_flag
    if domain_scores is not None:
        event["domain_scores"] = domain_scores
    if raw_answers_saved is not None:
        event["raw_answers_saved"] = raw_answers_saved
    return event


if __name__ == "__main__":
    main()
