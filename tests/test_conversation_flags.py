from __future__ import annotations

from datetime import datetime, timedelta

from src.user import conversation_flags, monitoring_preferences
from src.user.conversation_flags_database import ConversationFlag, SessionLocal


def _cleanup(sender_id: str) -> None:
    db = SessionLocal()
    try:
        db.query(ConversationFlag).filter(ConversationFlag.sender_id == sender_id).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_a_safety_red_flag_term_is_recorded_without_calling_the_llm():
    sender_id = "pytest-flag-safety"
    try:
        called = []
        conversation_flags.maybe_flag_turn(
            sender_id, "我突然胸口好痛 chest pain", answer_callable=lambda p: called.append(p) or "unused",
        )
        flags = conversation_flags.get_recent_flags(sender_id)
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "safety"
        assert not called  # the decline classifier must be skipped once a safety flag already fires
    finally:
        _cleanup(sender_id)


def test_decline_classifier_flags_when_the_llm_says_yes():
    sender_id = "pytest-flag-decline"
    try:
        conversation_flags.maybe_flag_turn(
            sender_id, "今日禮拜幾呀？我唔記得咗", answer_callable=lambda p: "FLAG: 是\nREASON: 對日期感到混亂",
        )
        flags = conversation_flags.get_recent_flags(sender_id)
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "cognitive_decline"
        assert flags[0]["reason"] == "對日期感到混亂"
    finally:
        _cleanup(sender_id)


def test_decline_classifier_does_not_flag_when_the_llm_says_no():
    sender_id = "pytest-flag-no-decline"
    try:
        conversation_flags.maybe_flag_turn(
            sender_id, "今晚食咩好呢", answer_callable=lambda p: "FLAG: 否\nREASON: ",
        )
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_no_answer_callable_and_no_safety_term_records_nothing():
    sender_id = "pytest-flag-no-callable"
    try:
        conversation_flags.maybe_flag_turn(sender_id, "你好", answer_callable=None)
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_a_classifier_exception_never_raises():
    sender_id = "pytest-flag-broken-callable"

    def broken(_prompt: str) -> str:
        raise RuntimeError("network down")

    try:
        conversation_flags.maybe_flag_turn(sender_id, "今日禮拜幾呀", answer_callable=broken)
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_get_recent_flags_only_returns_the_requested_senders_flags():
    sender_a, sender_b = "pytest-flag-isolation-a", "pytest-flag-isolation-b"
    try:
        conversation_flags.maybe_flag_turn(sender_a, "chest pain again", answer_callable=None)
        assert conversation_flags.get_recent_flags(sender_b) == []
        assert len(conversation_flags.get_recent_flags(sender_a)) == 1
    finally:
        _cleanup(sender_a)
        _cleanup(sender_b)


def test_flags_older_than_retention_window_are_purged():
    sender_id = "pytest-flag-expired"
    db = SessionLocal()
    try:
        old = ConversationFlag(
            sender_id=sender_id,
            flag_type="safety",
            reason="old entry",
            created_at=datetime.utcnow() - timedelta(days=conversation_flags.RETENTION_DAYS + 1),
        )
        db.add(old)
        db.commit()
    finally:
        db.close()
    try:
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_safety_flags_are_skipped_when_that_category_is_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-safety-disabled"
    monitoring_preferences.set_monitoring_preferences(sender_id, safety=False)
    try:
        conversation_flags.maybe_flag_turn(sender_id, "我突然胸口好痛 chest pain", answer_callable=None)
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_cognitive_decline_flags_are_skipped_when_that_category_is_turned_off(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-decline-disabled"
    monitoring_preferences.set_monitoring_preferences(sender_id, cognitive_decline=False)

    def fail_if_called(_prompt: str) -> str:
        raise AssertionError("decline classifier must not be called when that category is disabled")

    try:
        conversation_flags.maybe_flag_turn(sender_id, "今日禮拜幾呀？我唔記得咗", answer_callable=fail_if_called)
        assert conversation_flags.get_recent_flags(sender_id) == []
    finally:
        _cleanup(sender_id)


def test_disabling_one_category_leaves_the_other_active(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-one-disabled"
    monitoring_preferences.set_monitoring_preferences(sender_id, cognitive_decline=False)
    try:
        conversation_flags.maybe_flag_turn(sender_id, "我突然胸口好痛 chest pain", answer_callable=None)
        flags = conversation_flags.get_recent_flags(sender_id)
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "safety"
    finally:
        _cleanup(sender_id)


def test_no_raw_message_text_is_ever_stored():
    sender_id = "pytest-flag-no-raw-text"
    secret_message = "呢句唔應該原文儲存 super-secret-detail-xyz"
    try:
        conversation_flags.maybe_flag_turn(
            sender_id, secret_message, answer_callable=lambda p: "FLAG: 是\nREASON: 表達混亂",
        )
        flags = conversation_flags.get_recent_flags(sender_id)
        assert len(flags) == 1
        assert "super-secret-detail-xyz" not in flags[0]["reason"]
    finally:
        _cleanup(sender_id)


def test_sleep_signal_requires_both_request_and_patient_consent(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-sleep-consent"
    monitoring_preferences.set_monitoring_preferences(sender_id, sleep=True)
    try:
        conversation_flags.maybe_flag_turn(sender_id, "我成晚瞓唔著", answer_callable=None)
        assert conversation_flags.get_recent_flags(sender_id) == []
        monitoring_preferences.set_patient_monitoring_consent(sender_id, sleep=True)
        conversation_flags.maybe_flag_turn(sender_id, "我成晚瞓唔著", answer_callable=None)
        flags = conversation_flags.get_recent_flags(sender_id)
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "sleep"
    finally:
        _cleanup(sender_id)


def test_daily_activity_and_routine_adherence_signals_are_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-activity-routine"
    monitoring_preferences.set_monitoring_preferences(sender_id, daily_activity=True, routine_adherence=True)
    monitoring_preferences.set_patient_monitoring_consent(sender_id, daily_activity=True, routine_adherence=True)
    try:
        conversation_flags.maybe_flag_turn(sender_id, "今日沖涼都做唔到", answer_callable=None)
        conversation_flags.maybe_flag_turn(sender_id, "我唔記得食藥", answer_callable=None)
        types = {flag["flag_type"] for flag in conversation_flags.get_recent_flags(sender_id)}
        assert types == {"daily_activity", "routine_adherence"}
    finally:
        _cleanup(sender_id)


def test_monitoring_history_returns_counts_and_threshold_status(tmp_path, monkeypatch):
    monkeypatch.setenv("MONITORING_PREFERENCES_PATH", str(tmp_path / "monitoring.json"))
    sender_id = "pytest-flag-history"
    monitoring_preferences.set_monitoring_preferences(sender_id, sleep=True)
    monitoring_preferences.set_patient_monitoring_consent(sender_id, sleep=True)
    monitoring_preferences.set_monitoring_thresholds(sender_id, sleep=2)
    try:
        conversation_flags.maybe_flag_turn(sender_id, "我瞓唔著", answer_callable=None)
        history = conversation_flags.get_monitoring_history(sender_id)
        assert history["counts"]["sleep"] == 1
        assert history["threshold_met"]["sleep"] is False
        conversation_flags.maybe_flag_turn(sender_id, "今晚又失眠", answer_callable=None)
        assert conversation_flags.get_monitoring_history(sender_id)["threshold_met"]["sleep"] is True
    finally:
        _cleanup(sender_id)
