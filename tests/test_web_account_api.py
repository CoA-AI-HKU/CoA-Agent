from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.accounts_database import SessionLocal, WebAccountProfile, WebContact
from backend.services.firebase_auth import FirebaseUser

client = TestClient(app)


def _cleanup(firebase_uid: str) -> None:
    db = SessionLocal()
    try:
        db.query(WebContact).filter(WebContact.firebase_uid == firebase_uid).delete(synchronize_session=False)
        db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == firebase_uid).delete(
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def test_contacts_endpoint_returns_503_when_firebase_not_configured(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: False)
    response = client.get("/api/account/contacts", headers={"Authorization": "Bearer whatever"})
    assert response.status_code == 503


def test_contacts_endpoint_requires_bearer_token(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.get("/api/account/contacts")
    assert response.status_code == 401


def test_contacts_endpoint_rejects_invalid_token(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr("backend.api.web_account.verify_id_token", lambda token: None)
    response = client.get("/api/account/contacts", headers={"Authorization": "Bearer bad-token"})
    assert response.status_code == 401


def _authenticate_as(monkeypatch, uid: str, *, email: str | None = None) -> None:
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr(
        "backend.api.web_account.verify_id_token",
        lambda token: FirebaseUser(uid=uid, phone_number="+85212345678", display_name=None, email=email),
    )


def test_add_list_and_delete_contact(monkeypatch):
    uid = "pytest-firebase-uid-1"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake-id-token"}
    try:
        create = client.post("/api/account/contacts", json={"name": "陳太", "detail": "91234567"}, headers=headers)
        assert create.status_code == 201
        contact_id = create.json()["id"]

        listing = client.get("/api/account/contacts", headers=headers)
        assert listing.status_code == 200
        assert any(item["id"] == contact_id and item["name"] == "陳太" for item in listing.json())

        deletion = client.delete(f"/api/account/contacts/{contact_id}", headers=headers)
        assert deletion.status_code == 200
        assert deletion.json()["removed"] == 1

        listing_after = client.get("/api/account/contacts", headers=headers)
        assert all(item["id"] != contact_id for item in listing_after.json())
    finally:
        _cleanup(uid)


def test_contacts_are_isolated_per_firebase_uid(monkeypatch):
    uid_a = "pytest-firebase-uid-a"
    uid_b = "pytest-firebase-uid-b"
    try:
        _authenticate_as(monkeypatch, uid_a)
        client.post("/api/account/contacts", json={"name": "A的聯絡人", "detail": "111"}, headers={"Authorization": "Bearer a"})

        _authenticate_as(monkeypatch, uid_b)
        response_b = client.get("/api/account/contacts", headers={"Authorization": "Bearer b"})
        assert response_b.json() == []
    finally:
        _cleanup(uid_a)
        _cleanup(uid_b)


def test_delete_contact_cannot_remove_another_accounts_contact(monkeypatch):
    uid_a = "pytest-firebase-uid-owner"
    uid_b = "pytest-firebase-uid-intruder"
    try:
        _authenticate_as(monkeypatch, uid_a)
        create = client.post(
            "/api/account/contacts", json={"name": "私人聯絡人", "detail": "222"}, headers={"Authorization": "Bearer a"},
        )
        contact_id = create.json()["id"]

        _authenticate_as(monkeypatch, uid_b)
        deletion = client.delete(f"/api/account/contacts/{contact_id}", headers={"Authorization": "Bearer b"})
        assert deletion.status_code == 404

        _authenticate_as(monkeypatch, uid_a)
        listing = client.get("/api/account/contacts", headers={"Authorization": "Bearer a"})
        assert any(item["id"] == contact_id for item in listing.json())
    finally:
        _cleanup(uid_a)
        _cleanup(uid_b)


def test_me_endpoint_creates_a_default_companion_profile(monkeypatch):
    uid = "pytest-me-uid"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
        body = response.json()
        assert body["user_id"] == uid
        assert body["role"] == "companion"
        assert body["roles"] == ["companion"]
        assert body["permissions"] == ["chat", "voice"]
        assert body["default_mode"] == "companion"
        assert body["preferences"]["recognition_language"] == "zh-HK"
        assert body["preferences"]["auto_send"] is True
    finally:
        _cleanup(uid)


def test_me_endpoint_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.get("/api/me")
    assert response.status_code == 401


def test_bootstrap_admin_env_var_elevates_a_new_account(monkeypatch):
    uid = "pytest-bootstrap-admin-uid"
    monkeypatch.setenv("COA_BOOTSTRAP_ADMIN_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        body = response.json()
        assert body["role"] == "admin"
        assert "admin" in body["permissions"]
        assert "developer_mode" in body["permissions"]
    finally:
        _cleanup(uid)


def test_bootstrap_by_email_elevates_a_new_account(monkeypatch):
    uid = "pytest-bootstrap-email-uid"
    monkeypatch.setenv("COA_BOOTSTRAP_DEVELOPER_EMAILS", "dev@example.com")
    _authenticate_as(monkeypatch, uid, email="dev@example.com")
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["role"] == "developer"
    finally:
        _cleanup(uid)


def test_bootstrap_does_not_demote_an_already_elevated_account(monkeypatch):
    uid = "pytest-no-demote-uid"
    monkeypatch.setenv("COA_BOOTSTRAP_ADMIN_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        client.get("/api/me", headers={"Authorization": "Bearer fake"})  # becomes admin

        monkeypatch.delenv("COA_BOOTSTRAP_ADMIN_UIDS", raising=False)
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["role"] == "admin"
    finally:
        _cleanup(uid)


def test_preferences_update_is_applied_and_role_cannot_be_set_through_it(monkeypatch):
    uid = "pytest-preferences-uid"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)  # ensure a profile row exists first
        response = client.put(
            "/api/me/preferences",
            json={
                "recognition_language": "en-US",
                "talk_mode": "hold",
                "speech_speed": 1.2,
                "auto_speak": False,
                "auto_send": False,
                "role": "admin",  # must be silently ignored, not applied
            },
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "companion"  # unchanged despite the attempted override
        assert body["preferences"]["recognition_language"] == "en-US"
        assert body["preferences"]["talk_mode"] == "hold"
        assert body["preferences"]["speech_speed"] == 1.2
        assert body["preferences"]["auto_speak"] is False
        assert body["preferences"]["auto_send"] is False
    finally:
        _cleanup(uid)


def test_preferences_update_rejects_default_mode_the_role_does_not_permit_with_403(monkeypatch):
    # A real mode the account just isn't authorized for — the spec's "403
    # for a logged-in user without permission" case, not a 422 (the value
    # itself is a perfectly valid mode name, just not for this role).
    uid = "pytest-preferences-mode-uid"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        response = client.put("/api/me/preferences", json={"default_mode": "developer"}, headers=headers)
        assert response.status_code == 403
    finally:
        _cleanup(uid)


def test_preferences_update_rejects_an_unrecognized_mode_with_422(monkeypatch):
    uid = "pytest-preferences-badmode-uid"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        response = client.put("/api/me/preferences", json={"default_mode": "not-a-real-mode"}, headers=headers)
        assert response.status_code == 422
    finally:
        _cleanup(uid)


def test_new_developer_account_defaults_to_review_before_send(monkeypatch):
    uid = "pytest-new-developer-uid"
    monkeypatch.setenv("COA_BOOTSTRAP_DEVELOPER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        body = response.json()
        assert body["role"] == "developer"
        assert body["preferences"]["auto_send"] is False
    finally:
        _cleanup(uid)


def test_new_companion_account_defaults_to_auto_send(monkeypatch):
    uid = "pytest-new-companion-uid"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["preferences"]["auto_send"] is True
    finally:
        _cleanup(uid)


def test_new_account_has_not_given_consent_yet(monkeypatch):
    uid = "pytest-consent-new-uid"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["consent_given"] is False
    finally:
        _cleanup(uid)


def test_posting_consent_marks_the_account_as_consented(monkeypatch):
    uid = "pytest-consent-agree-uid"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        response = client.post("/api/me/consent", headers=headers)
        assert response.status_code == 200
        assert response.json()["consent_given"] is True

        # A later /api/me call (simulating a return visit / re-login) must
        # still report the account as consented — it should never be asked
        # again once it has agreed.
        follow_up = client.get("/api/me", headers=headers)
        assert follow_up.json()["consent_given"] is True
    finally:
        _cleanup(uid)


def test_consent_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.post("/api/me/consent")
    assert response.status_code == 401


def test_conversation_flags_endpoint_returns_this_accounts_own_flags(monkeypatch):
    from src.user.conversation_flags import maybe_flag_turn
    from src.user.conversation_flags_database import ConversationFlag, SessionLocal as FlagsSessionLocal

    uid = "pytest-me-conversation-flags-uid"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        empty = client.get("/api/me/conversation-flags", headers=headers)
        assert empty.status_code == 200
        assert empty.json() == {"flags": []}

        maybe_flag_turn(uid, "胸口好痛 chest pain", answer_callable=None)
        response = client.get("/api/me/conversation-flags", headers=headers)
        assert response.status_code == 200
        flags = response.json()["flags"]
        assert len(flags) == 1
        assert flags[0]["flag_type"] == "safety"
    finally:
        _cleanup(uid)
        db = FlagsSessionLocal()
        try:
            db.query(ConversationFlag).filter(ConversationFlag.sender_id == uid).delete(synchronize_session=False)
            db.commit()
        finally:
            db.close()


def test_conversation_flags_endpoint_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.get("/api/me/conversation-flags")
    assert response.status_code == 401
