from __future__ import annotations

from datetime import datetime, timedelta

from src.user import conversation_flags
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
