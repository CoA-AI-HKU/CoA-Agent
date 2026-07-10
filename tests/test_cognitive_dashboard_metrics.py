from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from src.insights import InsightGenerator
from src.metrics import MetricsCollector, load_events, log_event


def _timestamp(days_ago: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _log_cognitive_check(
    user_id: str,
    *,
    total_score: int,
    risk_flag: str,
    days_ago: int = 0,
) -> None:
    log_event(
        user_id,
        {
            "timestamp": _timestamp(days_ago),
            "event_type": "cognitive_check_completed",
            "check_version": "simple_cognitive_check_v1",
            "total_score": total_score,
            "max_score": 15,
            "risk_flag": risk_flag,
            "domain_scores": {
                "orientation": 1,
                "immediate_recall": 3,
                "attention": 2,
                "category_fluency": 2,
                "delayed_recall": 0,
                "safety_reasoning": 1,
            },
            "raw_answers_saved": False,
            "raw_answers": ["不應保存"],
            "raw_text": "不應保存",
            "message": "不應保存",
        },
    )


def test_cognitive_check_completed_appears_in_cognitive_history(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    _log_cognitive_check("patient_001", total_score=9, risk_flag="monitor")

    metrics = MetricsCollector().get_user_metrics("patient_001", days=7)

    assert metrics["cognitive_check_count"] == 1
    assert metrics["latest_risk_flag"] == "monitor"
    assert metrics["latest_cognitive_check"]["total_score"] == 9
    assert {
        "timestamp": metrics["cognitive_history"][0]["timestamp"],
        "score": 9.0,
        "exercise_type": "簡單認知小練習",
    } in metrics["cognitive_history"]


def test_follow_up_suggested_generates_caregiver_alert(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    _log_cognitive_check("patient_001", total_score=7, risk_flag="follow_up_suggested")

    alerts = InsightGenerator().get_alerts("patient_001", days=7)
    summary = InsightGenerator().get_summary("patient_001", days=7)

    messages = " ".join(alert["message"] for alert in alerts)
    assert "建議照顧者留意，並考慮安排專業評估" in messages
    assert "診斷" in messages
    assert "dementia detected" not in messages.lower()
    assert "diagnosed" not in messages.lower()
    assert summary["latest_risk_flag"] == "follow_up_suggested"
    assert summary["cognitive_check_status"] == "建議照顧者跟進"


def test_memory_concern_threshold_generates_alert(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    for days_ago, event_type in enumerate(["memory_concern", "memory_concern", "orientation_confusion"]):
        log_event(
            "patient_001",
            {
                "timestamp": _timestamp(days_ago),
                "event_type": event_type,
                "intent": "self_memory_concern",
                "route": "memory_concern",
                "event_value": True,
            },
        )

    alerts = InsightGenerator().get_alerts("patient_001", days=3)
    metrics = MetricsCollector().get_user_metrics("patient_001", days=7)

    messages = " ".join(alert["message"] for alert in alerts)
    assert "最近出現多次記憶或方向感相關擔憂" in messages
    assert metrics["concern_signal_counts"]["memory_concern"] == 2
    assert metrics["concern_signal_counts"]["orientation_confusion"] == 1


def test_cognitive_check_log_drops_raw_answers(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))
    _log_cognitive_check("patient_001", total_score=9, risk_flag="monitor")

    content = events_path.read_text(encoding="utf-8")
    event = json.loads(content)
    metrics = MetricsCollector().get_user_metrics("patient_001", days=7)

    assert "raw_answers" not in event
    assert "raw_text" not in event
    assert "message" not in event
    assert "不應保存" not in content
    assert event["raw_answers_saved"] is False
    assert metrics["latest_cognitive_check"]["raw_answers_saved"] is False


def test_old_dashboard_fields_still_exist(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    log_event(
        "patient_001",
        {
            "timestamp": _timestamp(),
            "event_type": "mood_check",
            "score": 4,
            "intent": "emotional_support",
            "route": "supportive",
        },
    )

    metrics = MetricsCollector().get_user_metrics("patient_001", days=7)
    summary = InsightGenerator().get_summary("patient_001", days=7)

    for key in [
        "avg_mood",
        "avg_cognitive",
        "total_interactions",
        "medication_adherence",
        "mood_history",
        "cognitive_history",
        "intent_counts",
    ]:
        assert key in metrics
    assert "mood_status" in summary
    assert "cognitive_status" in summary
    assert "medication_status" in summary
    assert summary["cognitive_check_status"] == "尚無小練習記錄"
