from fastapi.testclient import TestClient

from backend.api import web_chat as chat_api
from backend.main import app
from backend.services.firebase_auth import FirebaseUser


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
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr(
        "backend.api.web_account.verify_id_token",
        lambda token: FirebaseUser(uid="web-demo-user", phone_number=None, display_name=None, email=None),
    )
    response = TestClient(app).post(
        "/api/chat",
        json={
            "message": "記憶健康有甚麼建議？",
            "session_id": "browser-session",
            "input_mode": "text",
        },
        headers={"Authorization": "Bearer fake-id-token"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "reply": "這是經共用處理流程產生的回覆。",
        "language": "zh-HK",
        "session_id": "browser-session",
    }


def test_unified_app_includes_health_and_chat_routes():
    coa_paths = app.openapi()["paths"]

    assert "get" in coa_paths["/health"]
    assert "post" in coa_paths["/api/chat"]
