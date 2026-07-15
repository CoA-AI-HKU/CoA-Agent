from __future__ import annotations

import json

from src.insights import InsightGenerator
from src.metrics import MetricsCollector, load_events, log_event


def test_arag_events_remain_dashboard_compatible_and_private(tmp_path, monkeypatch) -> None:
    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENTS_LOG_PATH", str(path))
    user_id = "arag-dashboard-user"
    required = ("memory_concern", "medication_uncertainty", "wandering_safety", "knowledge_qa")
    for event_type in required:
        log_event(
            user_id,
            {
                "event_type": event_type,
                "intent": "knowledge_qa" if event_type == "knowledge_qa" else event_type,
                "route": "rag_qa" if event_type == "knowledge_qa" else event_type,
                "safety_level": "normal",
                "rag_called": event_type == "knowledge_qa",
                "message": "raw private conversation",
                "answer": "raw private answer",
            },
        )

    events = load_events(user_id=user_id, days=None)
    assert [event["event_type"] for event in events] == list(required)
    assert all("message" not in event and "answer" not in event for event in events)
    assert all({"timestamp", "user_id", "event_type", "intent", "route"} <= event.keys() for event in events)
    metrics = MetricsCollector().get_user_metrics(user_id)
    assert metrics["total_interactions"] == 4
    assert metrics["intent_counts"]
    assert InsightGenerator().get_alerts(user_id)
    assert "raw private conversation" not in path.read_text(encoding="utf-8")


def test_one_incoming_message_does_not_log_duplicate_interaction(tmp_path, monkeypatch) -> None:
    path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENTS_LOG_PATH", str(path))
    monkeypatch.setattr(
        "src.agents.rag_evidence_agent.answer_question",
        lambda *_args, **_kwargs: {
            "answer": "腦退化症會影響記憶、思考及日常生活能力。",
            "found": True,
            "sources": ["private.md"],
            "debug": {"retrieval": {"answer_used_rag": True, "evidence_sufficient": True}},
        },
    )
    from src.user.message_router import handle_incoming_message

    handle_incoming_message("腦退化症是什麼？", "dedupe-user")
    events = load_events(user_id="dedupe-user", days=None)
    matching = [event for event in events if event.get("route") == "rag_qa" and event.get("intent") == "knowledge_qa"]
    assert len(matching) == 1

