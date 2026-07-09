from __future__ import annotations

import json

from src.metrics import load_events, log_event


def test_dashboard_event_log_drops_raw_conversation_fields(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    log_event(
        "patient_001",
        {
            "user_id": "patient_001",
            "role": "user",
            "channel": "whatsapp",
            "intent": "emotional_support",
            "route": "supportive",
            "event_type": "mood_check",
            "score": 4,
            "raw_text": "我今日好唔開心",
            "message": "我今日好唔開心",
            "event_value": "我今日好唔開心",
        },
    )

    content = events_path.read_text(encoding="utf-8")
    event = json.loads(content)

    assert "raw_text" not in event
    assert "message" not in event
    assert "我今日好唔開心" not in content
    assert "event_value" not in event
    assert event["score"] == 4
    assert event["event_type"] == "mood_check"


def test_dashboard_metrics_load_structured_events_only(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))

    log_event(
        "patient_001",
        {
            "role": "user",
            "channel": "whatsapp",
            "intent": "medication_or_diagnosis",
            "route": "medical_boundary",
            "event_type": "medication_uncertainty",
            "event_value": True,
            "medication_status": "unsure",
        },
    )

    events = load_events("patient_001", days=7)

    assert len(events) == 1
    assert events[0]["event_value"] is True
    assert events[0]["medication_status"] == "unsure"
