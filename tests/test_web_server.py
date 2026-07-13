from __future__ import annotations

from src.metrics import log_event
from src.web_server import build_dashboard_payload


def test_web_dashboard_uses_live_structured_events(tmp_path, monkeypatch):
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    log_event("telegram_user", {"channel": "telegram", "event_type": "interaction", "intent": "knowledge_qa"})
    payload = build_dashboard_payload("telegram_user", 7)
    assert payload["metrics"]["total_interactions"] == 1
    assert payload["metrics"]["intent_counts"]["knowledge_qa"] == 1
    assert len(payload["daily_activity"]) == 7
