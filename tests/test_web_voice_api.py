from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.api import web_chat as chat_api
from backend.main import app
from backend.services.conversation import ConversationService, process_user_message
from backend.services.firebase_auth import FirebaseUser


client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer fake-id-token"}
AUTHENTICATED_UID = "firebase-verified-uid"


@pytest.fixture(autouse=True)
def authenticated_web_chat_user(monkeypatch):
    # /api/chat now requires a verified Firebase sign-in (see
    # backend/api/web_chat.py); applied to every test in this file since
    # they all exercise that endpoint.
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr(
        "backend.api.web_account.verify_id_token",
        lambda token: FirebaseUser(uid=AUTHENTICATED_UID, phone_number=None, display_name=None, email=None),
    )


def test_health_returns_success():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_endpoint_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.post(
        "/api/chat",
        json={"message": "你好", "session_id": "session-noauth", "input_mode": "text"},
    )
    assert response.status_code == 401


def test_empty_message_is_rejected():
    response = client.post(
        "/api/chat",
        json={
            "message": "   ",
            "session_id": "session-empty",
            "input_mode": "text",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 400
    assert response.json() == {"error": "請先輸入訊息。"}


def test_valid_text_reaches_shared_processor_using_verified_identity_not_client_input(monkeypatch):
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
            "session_id": "session-1",
            "input_mode": "voice",
            # None of these should reach the pipeline — a client can send
            # whatever it likes here, only the verified token's uid governs
            # identity, and the request model doesn't even declare these
            # fields (silently dropped, not just ignored downstream).
            "user_id": "someone-elses-uid",
            "role": "administrator",
            "caregiver": True,
            "raw_audio": "not-used",
        },
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "安全回覆",
        "language": "zh-HK",
        "session_id": "session-1",
    }
    assert received["message"] == "今日有甚麼要做？"
    assert received["channel"] == "web"
    # Identity came from the verified Firebase token, not the client-supplied
    # (and different) user_id field above.
    assert received["user_id"] == AUTHENTICATED_UID
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
        json={
            "message": "你好",
            "session_id": "session-error",
            "input_mode": "text",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json() == {
        "reply": "我暫時未能處理這個訊息。請稍後再試，我會繼續在這裡陪你。",
        "language": "zh-HK",
        "session_id": "session-error",
    }
    assert "private" not in response.text


def test_agent_timeout_returns_safe_error(monkeypatch):
    async def timed_out_process(**kwargs):
        raise asyncio.TimeoutError

    monkeypatch.setattr(chat_api, "process_user_message", timed_out_process)
    response = client.post(
        "/api/chat",
        json={
            "message": "你好",
            "session_id": "session-timeout",
            "input_mode": "voice",
        },
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["reply"].strip()
    assert response.json()["session_id"] == "session-timeout"
