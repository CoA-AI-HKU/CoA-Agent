from __future__ import annotations

# Cognitive dashboard metrics

import json
from datetime import datetime, timedelta, timezone

from src.insights import InsightGenerator
from src.metrics import MetricsCollector, detect_concern_signal, infer_event_type, load_events, log_event
from src.user.message_router import handle_incoming_message
from src.user.user_registry import get_registered_patient_accounts


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


# Dashboard privacy

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


# Concern-signal logging and caregiver alerts

def test_concern_signal_classifier_returns_structured_follow_up_codes() -> None:
    cases = [
        (
            "我最近成日唔記得嘢",
            "user",
            {"route": "memory_concern", "intent": "self_memory_concern"},
            "memory_concern",
            "follow_up_suggested",
        ),
        (
            "我唔知自己喺邊",
            "user",
            {"route": "supportive", "intent": "unknown"},
            "orientation_confusion",
            "follow_up_suggested",
        ),
        (
            "我唔記得食咗藥未",
            "user",
            {"route": "medical_boundary", "intent": "medication_or_diagnosis"},
            "medication_uncertainty",
            "caregiver_followup_recommended",
        ),
        (
            "媽媽走失咗，我搵唔到佢",
            "caregiver",
            {"route": "safety", "intent": "safety_sensitive"},
            "wandering_safety",
            "caregiver_followup_recommended",
        ),
        (
            "媽媽最近記性差咗好多",
            "caregiver",
            {"route": "caregiver_guidance", "intent": "caregiver_guidance"},
            "caregiver_reported_worsening",
            "caregiver_followup_recommended",
        ),
    ]

    for message, role, result, event_type, follow_up_status in cases:
        signal = detect_concern_signal(message, role, result)
        assert signal == {
            "event_type": event_type,
            "follow_up_status": follow_up_status,
        }

    generic_medication_result = {"route": "medical_boundary", "intent": "medication_or_diagnosis"}
    assert detect_concern_signal("Can I take aspirin for a headache?", "user", generic_medication_result) is None
    assert infer_event_type(generic_medication_result) == "medication_question"
    assert detect_concern_signal(
        "How can we prevent wandering?",
        "caregiver",
        {"route": "rag_qa", "intent": "knowledge_qa"},
    ) is None


def test_message_router_logs_concern_signals_without_conversation_text(tmp_path, monkeypatch) -> None:
    events_path = tmp_path / "events.jsonl"
    registry_path = tmp_path / "user_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "users": {
                    "caregiver_1": {
                        "role": "caregiver",
                        "linked_user_id": "patient_1",
                    }
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVENTS_LOG_PATH", str(events_path))
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))

    messages = [
        ("我最近成日唔記得嘢", "user_memory"),
        ("我唔知自己喺邊", "user_orientation"),
        ("我唔記得食咗藥未", "user_medication"),
        ("媽媽走失咗，我搵唔到佢", "user_wandering"),
        ("媽媽最近記性差咗好多", "caregiver_1"),
    ]
    for message, sender_id in messages:
        handle_incoming_message(message, sender_id, "whatsapp")

    events = load_events(user_id=None, days=7)
    event_types = {event["event_type"] for event in events}
    content = events_path.read_text(encoding="utf-8")

    assert {
        "memory_concern",
        "orientation_confusion",
        "medication_uncertainty",
        "wandering_safety",
        "caregiver_reported_worsening",
    } <= event_types
    assert all(event.get("follow_up_status") for event in events)
    assert all(message not in content for message, _ in messages)
    assert "raw_text" not in content
    assert "message" not in content


def test_concern_signals_create_non_diagnostic_caregiver_alerts(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    for event_type in [
        "memory_concern",
        "memory_concern",
        "orientation_confusion",
        "medication_uncertainty",
        "wandering_safety",
        "caregiver_reported_worsening",
    ]:
        log_event("patient_1", {"event_type": event_type})

    alerts = InsightGenerator().get_alerts("patient_1", days=7)
    messages = " ".join(alert["message"] for alert in alerts)
    codes = {alert.get("code") for alert in alerts}

    assert "follow_up_suggested" in codes
    assert "caregiver_followup_recommended" in codes
    assert any(alert["level"] == "urgent" for alert in alerts)
    assert all("這不是診斷" in alert["message"] for alert in alerts)
    assert "dementia risk" not in messages.lower()
    assert "腦退化風險" not in messages


def test_dashboard_users_come_from_registered_patient_accounts(tmp_path, monkeypatch) -> None:
    registry_path = tmp_path / "user_registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "users": {
                    "patient_sender_1": {
                        "role": "user",
                        "user_id": "patient_1",
                        "display_name": "陳太",
                    },
                    "patient_sender_2": {
                        "role": "user",
                        "display_name": "李先生",
                    },
                    "caregiver_1": {
                        "role": "caregiver",
                        "linked_user_id": "patient_1",
                        "display_name": "照顧者",
                    },
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_REGISTRY_PATH", str(registry_path))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    log_event("unregistered_event_user", {"event_type": "interaction"})

    accounts = get_registered_patient_accounts()

    assert accounts == [
        {"user_id": "patient_sender_2", "display_name": "李先生"},
        {"user_id": "patient_1", "display_name": "陳太"},
    ]
    assert all(account["user_id"] != "caregiver_1" for account in accounts)
    assert all(account["user_id"] != "unregistered_event_user" for account in accounts)
