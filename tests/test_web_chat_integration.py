from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


@pytest.fixture(autouse=True)
def explicit_test_rag_runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("EMBEDDER_PROVIDER", "dummy")
    monkeypatch.setenv("RAG_ALLOW_EXTRACTIVE_FALLBACK", "true")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("RAG_AUTO_INDEX", "false")


@pytest.mark.parametrize(
    "message",
    [
        "你好",
        "我今天晚上吃什麼好",
        "我最近覺得好累呀",
        "腦退化症是什麼",
    ],
)
def test_web_chat_always_returns_stable_user_facing_contract(message: str) -> None:
    response = client.post(
        "/api/chat",
        json={
            "message": message,
            "user_id": "integration-web-user",
            "session_id": "integration-session",
            "input_mode": "text",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["reply"], str)
    assert body["reply"].strip()
    assert isinstance(body["language"], str)
    assert body["language"].strip()
    assert body["session_id"] == "integration-session"
    if message == "你好":
        assert "不安" not in body["reply"]
        assert "你好" in body["reply"]


def test_unified_app_serves_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert 'fetch("/api/chat"' in response.text


@pytest.mark.parametrize(
    ("message", "expected_text"),
    [
        ("你覺得數獨好玩嗎", "數獨"),
        ("我想去打麻將可以嗎", "可以"),
    ],
)
def test_web_chat_answers_safe_casual_activity_questions(
    message: str, expected_text: str
) -> None:
    response = client.post(
        "/api/chat",
        json={
            "message": message,
            "user_id": "casual-web-user",
            "session_id": "casual-session",
            "input_mode": "text",
        },
    )

    assert response.status_code == 200
    reply = response.json()["reply"]
    assert expected_text in reply
    assert "功能暫時未能處理" not in reply
