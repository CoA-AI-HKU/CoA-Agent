from fastapi.testclient import TestClient

from backend.api import web_chat as chat_api
from backend.main import app
from reminder_backend.app import app as reminder_app


def test_dedicated_coa_api_exposes_shared_rag_chat_route(monkeypatch):
    async def fake_process(**kwargs):
        assert kwargs["message"] == "記憶健康有甚麼建議？"
        assert kwargs["channel"] == "web"
        return {
            "reply": "這是經共用處理流程產生的回覆。",
            "language": "zh-HK",
            "session_id": "browser-session",
        }

    monkeypatch.setattr(chat_api, "process_user_message", fake_process)
    response = TestClient(app).post(
        "/api/chat",
        json={
            "message": "記憶健康有甚麼建議？",
            "user_id": "web-demo-user",
            "session_id": "browser-session",
            "input_mode": "text",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "這是經共用處理流程產生的回覆。",
        "language": "zh-HK",
        "session_id": "browser-session",
    }


def test_coa_and_reminder_apis_have_separate_responsibilities():
    coa_paths = app.openapi()["paths"]
    reminder_paths = reminder_app.openapi()["paths"]

    assert "get" in coa_paths["/health"]
    assert "post" in coa_paths["/api/chat"]
    assert "/api/reminders" not in coa_paths
    assert "/api/auth/login" not in coa_paths
    assert "/api/chat" not in reminder_paths
    assert "get" in reminder_paths["/api/reminders"]
    assert "post" in reminder_paths["/api/auth/login"]
