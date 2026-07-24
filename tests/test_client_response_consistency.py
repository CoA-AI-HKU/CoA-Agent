from __future__ import annotations

import pytest

from backend.services.conversation import ConversationRequest, ConversationService


@pytest.mark.parametrize("message", ["你覺得數獨好玩嗎", "我想去打麻將可以嗎"])
def test_web_telegram_and_cli_use_the_same_conversation_pipeline(message: str) -> None:
    service = ConversationService()
    replies = {
        platform: service.respond(
            ConversationRequest(
                user_id=f"consistency-{platform}",
                message=message,
                platform=platform,
            )
        ).response
        for platform in ("web", "telegram", "cli")
    }

    assert replies["web"] == replies["telegram"] == replies["cli"]
    assert replies["web"].strip()
    assert "功能暫時未能處理" not in replies["web"]
