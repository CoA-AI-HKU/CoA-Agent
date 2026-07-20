from __future__ import annotations

import json

from src.intent_router import classify_intent
from src.user.message_router import handle_incoming_message


UNCLEAR = "我未能清楚理解你的意思"


def test_memory_concern_with_cant_recall_is_not_unclear() -> None:
    result = handle_incoming_message("總是覺得有些事情想不起來怎麽辦", "memory-concern-user", "telegram")

    assert result["intent"] in {"self_memory_concern", "emotional_support"}
    assert UNCLEAR not in result["answer"]


def test_memory_concern_with_emotional_distress_is_not_unclear() -> None:
    result = handle_incoming_message(
        "有時候覺得很多事情想不起來，覺得很鬱悶怎麽辦",
        "distressed-memory-user",
        "telegram",
    )

    assert result["intent"] in {"self_memory_concern", "emotional_support"}
    assert UNCLEAR not in result["answer"]


def test_name_three_fruits_reply_uses_pending_activity(tmp_path, monkeypatch) -> None:
    state_path = tmp_path / "pending_activities.json"
    monkeypatch.setenv("PENDING_ACTIVITY_STATE_PATH", str(state_path))
    sender_id = "activity-user"

    prompt = handle_incoming_message("我好悶，有什麼可以做？", sender_id, "telegram")
    stored = json.loads(state_path.read_text(encoding="utf-8"))[sender_id]

    assert "三種水果" in prompt["answer"]
    assert stored["pending_activity_type"] == "name_three_items"
    assert stored["pending_activity_prompt"] == prompt["answer"]
    assert stored["pending_activity_expected_response"]
    assert stored["created_at"]
    assert stored["user_id"] == sender_id
    assert stored["sender_id"] == sender_id

    result = handle_incoming_message("蘋果，香蕉，梨子", sender_id, "telegram")

    assert result["answer"] == "很好，你做到了。你剛剛說了蘋果、香蕉和梨子。先慢慢呼吸一下。你現在覺得好一點嗎？"
    assert result["route"] == "activity_response"
    assert UNCLEAR not in result["answer"]
    assert sender_id not in json.loads(state_path.read_text(encoding="utf-8"))


def test_required_memory_and_emotional_terms_never_classify_as_unknown() -> None:
    for message in ["想不起來", "記不起", "忘記", "很鬱悶", "很煩", "不知道怎麼辦"]:
        assert classify_intent(message).intent in {"self_memory_concern", "emotional_support"}
