from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.api import web_chat as chat_api
from backend.main import app
from backend.services.conversation import ConversationService, process_user_message


client = TestClient(app)


def test_health_returns_success():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_empty_message_is_rejected():
    response = client.post(
        "/api/chat",
        json={"message": "   ", "user_id": "web-demo-user", "input_mode": "text"},
    )
    assert response.status_code == 400
    assert response.json() == {"error": "請先輸入訊息。"}


def test_valid_text_reaches_shared_processor_and_privileged_fields_are_ignored(monkeypatch):
    received = {}

    async def fake_process(**kwargs):
        received.update(kwargs)
        return {
            "reply": "安全回覆",
            "language": "zh-HK",
            "session_id": "session-1",
            "route": "internal-route",
            "tool_name": "private-tool",
        }

    monkeypatch.setattr(chat_api, "process_user_message", fake_process)
    response = client.post(
        "/api/chat",
        json={
            "message": "  今日有甚麼要做？  ",
            "user_id": "web-demo-user",
            "session_id": "session-1",
            "input_mode": "voice",
            "role": "administrator",
            "caregiver": True,
            "raw_audio": "not-used",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "安全回覆",
        "language": "zh-HK",
        "session_id": "session-1",
    }
    assert received["message"] == "今日有甚麼要做？"
    assert received["channel"] == "web"
    assert "role" not in received
    assert "raw_audio" not in received


def test_shared_processor_returns_only_user_safe_fields():
    class StubContexts:
        def load(self, sender_id):
            return type("Context", (), {"role": "user", "user_id": sender_id})()

    def handler(*args):
        return {
            "answer": "可閱讀的回覆",
            "route": "rag",
            "debug": {"tool": "secret"},
            "sources": ["private-file.md"],
        }

    result = asyncio.run(
        process_user_message(
            "web-user",
            "你好",
            "web",
            "session-2",
            service=ConversationService(handler=handler, context_service=StubContexts()),
        )
    )
    assert result == {
        "reply": "可閱讀的回覆",
        "language": "zh-HK",
        "session_id": "session-2",
    }


def test_agent_exception_returns_safe_error(monkeypatch):
    async def failed_process(**kwargs):
        raise RuntimeError("private failure details")

    monkeypatch.setattr(chat_api, "process_user_message", failed_process)
    response = client.post(
        "/api/chat",
        json={"message": "你好", "user_id": "web-demo-user", "input_mode": "text"},
    )
    assert response.status_code == 500
    assert response.json() == {"error": "CoA-Agent 暫時無法處理這個訊息，請稍後再試。"}
    assert "private" not in response.text


def test_agent_timeout_returns_safe_error(monkeypatch):
    async def timed_out_process(**kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(chat_api, "process_user_message", timed_out_process)
    response = client.post(
        "/api/chat",
        json={"message": "你好", "user_id": "web-demo-user", "input_mode": "voice"},
    )
    assert response.status_code == 504
    assert response.json() == {"error": "CoA-Agent 暫時無法處理這個訊息，請稍後再試。"}
