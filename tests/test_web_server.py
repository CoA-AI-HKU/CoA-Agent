from __future__ import annotations

from src.metrics import log_event
from src.web_server import build_dashboard_payload
from src.user.message_router import handle_incoming_message
from src.user.user_registry import register_account


def test_web_dashboard_uses_live_structured_events(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    log_event("telegram_user", {"channel": "telegram", "event_type": "interaction", "intent": "knowledge_qa"})
    payload = build_dashboard_payload("telegram_user", 7)
    assert payload["metrics"]["total_interactions"] == 1
    assert payload["metrics"]["intent_counts"]["knowledge_qa"] == 1
    assert len(payload["daily_activity"]) == 7


def test_telegram_patient_message_flows_into_dashboard_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    patient = register_account("telegram_sender", "user", "Telegram Patient")
    monkeypatch.setattr(
        "src.user.message_router.handle_patient_user_message",
        lambda *args, **kwargs: {
            "answer": "ok", "route": "rag_qa", "intent": "knowledge_qa",
            "safety_level": "normal", "rag_called": True, "sources": [],
        },
    )

    handle_incoming_message("What support is available?", "telegram_sender", "telegram")
    payload = build_dashboard_payload(patient["user_id"], 7)

    assert payload["metrics"]["total_interactions"] == 1
    assert payload["metrics"]["intent_counts"]["knowledge_qa"] == 1
    assert payload["channel_counts"] == {"telegram": 1}
