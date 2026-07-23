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
    routes = {(route.path, method) for route in app.routes for method in getattr(route, "methods", set())}
    reminder_routes = {
        (route.path, method) for route in reminder_app.routes for method in getattr(route, "methods", set())
    }
    assert ("/health", "GET") in routes
    assert ("/api/chat", "POST") in routes
    assert ("/api/reminders", "GET") not in routes
    assert ("/api/auth/login", "POST") not in routes
    assert ("/api/chat", "POST") not in reminder_routes
    assert ("/api/reminders", "GET") in reminder_routes
    assert ("/api/auth/login", "POST") in reminder_routes
