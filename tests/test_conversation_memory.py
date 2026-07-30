from __future__ import annotations

import time

from src.user import conversation_memory


def setup_function() -> None:
    conversation_memory._buffers.clear()
    conversation_memory._last_active.clear()


def test_no_history_for_a_sender_never_seen_before():
    assert conversation_memory.get_recent_turns("brand-new-sender") == []


def test_recorded_turns_come_back_in_order():
    conversation_memory.record_turn("s1", "你好", "你好！")
    conversation_memory.record_turn("s1", "今日天氣點呀", "今日天氣唔錯。")
    turns = conversation_memory.get_recent_turns("s1")
    assert [t.user_message for t in turns] == ["你好", "今日天氣點呀"]
    assert [t.reply for t in turns] == ["你好！", "今日天氣唔錯。"]


def test_buffer_is_capped_at_max_turns():
    for i in range(conversation_memory.MAX_TURNS + 4):
        conversation_memory.record_turn("s2", f"message {i}", f"reply {i}")
    turns = conversation_memory.get_recent_turns("s2")
    assert len(turns) == conversation_memory.MAX_TURNS
    # Oldest turns should have been dropped, not the newest.
    assert turns[-1].user_message == f"message {conversation_memory.MAX_TURNS + 3}"


def test_turns_are_isolated_per_sender():
    conversation_memory.record_turn("sender-a", "A的說話", "回覆A")
    conversation_memory.record_turn("sender-b", "B的說話", "回覆B")
    assert [t.user_message for t in conversation_memory.get_recent_turns("sender-a")] == ["A的說話"]
    assert [t.user_message for t in conversation_memory.get_recent_turns("sender-b")] == ["B的說話"]


def test_stale_conversation_is_treated_as_new(monkeypatch):
    conversation_memory.record_turn("s3", "舊嘅說話", "舊嘅回覆")
    # Simulate enough elapsed time that this counts as a new conversation.
    conversation_memory._last_active["s3"] = time.time() - conversation_memory.TTL_SECONDS - 1
    assert conversation_memory.get_recent_turns("s3") == []
    # And the stale entry should have been cleared out, not just skipped.
    assert "s3" not in conversation_memory._buffers


def test_clear_removes_a_senders_history():
    conversation_memory.record_turn("s4", "說話", "回覆")
    conversation_memory.clear("s4")
    assert conversation_memory.get_recent_turns("s4") == []
