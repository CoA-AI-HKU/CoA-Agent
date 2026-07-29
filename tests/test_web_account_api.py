from __future__ import annotations

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.accounts_database import SessionLocal, WebContact
from backend.services.firebase_auth import FirebaseUser

client = TestClient(app)


def _cleanup(firebase_uid: str) -> None:
    db = SessionLocal()
    try:
        db.query(WebContact).filter(WebContact.firebase_uid == firebase_uid).delete(synchronize_session=False)
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


def _authenticate_as(monkeypatch, uid: str) -> None:
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr(
        "backend.api.web_account.verify_id_token",
        lambda token: FirebaseUser(uid=uid, phone_number="+85212345678", display_name=None),
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


def test_me_endpoint_reflects_verified_firebase_user(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    monkeypatch.setattr(
        "backend.api.web_account.verify_id_token",
        lambda token: FirebaseUser(uid="pytest-me-uid", phone_number="+85298765432", display_name="Test User"),
    )
    response = client.get("/api/account/me", headers={"Authorization": "Bearer fake"})
    assert response.status_code == 200
    body = response.json()
    assert body["uid"] == "pytest-me-uid"
    assert body["phone_number"] == "+85298765432"
    assert body["display_name"] == "Test User"
