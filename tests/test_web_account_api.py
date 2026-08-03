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
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid)  # managing contacts requires the "contacts" permission
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
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid_a)
    try:
        _authenticate_as(monkeypatch, uid_a)
        created = client.post(
            "/api/account/contacts", json={"name": "A的聯絡人", "detail": "111"}, headers={"Authorization": "Bearer a"},
        )
        assert created.status_code == 201

        _authenticate_as(monkeypatch, uid_b)
        response_b = client.get("/api/account/contacts", headers={"Authorization": "Bearer b"})
        assert response_b.json() == []
    finally:
        _cleanup(uid_a)
        _cleanup(uid_b)


def test_delete_contact_cannot_remove_another_accounts_contact(monkeypatch):
    uid_a = "pytest-firebase-uid-owner"
    uid_b = "pytest-firebase-uid-intruder"
    # Both need the "contacts" permission so this test exercises the
    # ownership check (404) rather than the role check (403).
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", f"{uid_a},{uid_b}")
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


def test_generate_pairing_code_returns_a_usable_code(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-pairing-generator"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/pairing-code", json={}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body["code"]) == 8
        assert body["expires_in_minutes"] == 15
    finally:
        _cleanup(uid)


def test_pairing_code_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.post("/api/me/pairing-code", json={})
    assert response.status_code == 401


def test_link_patient_with_a_valid_code_links_both_accounts(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-pairing-patient", "pytest-pairing-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid)
        code = client.post(
            "/api/me/pairing-code", json={"display_name": "阿婆"}, headers={"Authorization": "Bearer patient"},
        ).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        link_response = client.post(
            "/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer caregiver"},
        )
        assert link_response.status_code == 200
        linked = link_response.json()["linked_patients"]
        assert len(linked) == 1
        assert linked[0]["display_name"] == "阿婆"

        listing = client.get("/api/me/linked-patients", headers={"Authorization": "Bearer caregiver"})
        assert listing.json()["linked_patients"] == linked
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_link_patient_with_an_invalid_code_returns_422(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-pairing-bad-code"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.post(
            "/api/me/link-patient", json={"code": "NOTREAL1"}, headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 422
    finally:
        _cleanup(uid)


def test_unlinking_a_patient_removes_it_from_the_list(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-pairing-unlink-patient", "pytest-pairing-unlink-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid)
        code = client.post(
            "/api/me/pairing-code", json={}, headers={"Authorization": "Bearer patient"},
        ).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        headers = {"Authorization": "Bearer caregiver"}
        linked = client.post("/api/me/link-patient", json={"code": code}, headers=headers).json()["linked_patients"]
        patient_user_id = linked[0]["user_id"]

        removal = client.delete(f"/api/me/linked-patients/{patient_user_id}", headers=headers)
        assert removal.status_code == 200
        assert removal.json()["linked_patients"] == []
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_conversation_flags_include_a_linked_patients_flags_with_source_label(monkeypatch, tmp_path):
    from src.user.conversation_flags import get_recent_flags as _get_recent_flags
    from src.user.conversation_flags_database import ConversationFlag, SessionLocal as FlagsSessionLocal
    from src.user.conversation_flags import maybe_flag_turn

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-flags-linked-patient", "pytest-flags-linked-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid)
        code = client.post(
            "/api/me/pairing-code", json={"display_name": "爸爸"}, headers={"Authorization": "Bearer patient"},
        ).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        headers = {"Authorization": "Bearer caregiver"}
        client.post("/api/me/link-patient", json={"code": code}, headers=headers)

        maybe_flag_turn(patient_uid, "胸口好痛 chest pain", answer_callable=None)

        response = client.get("/api/me/conversation-flags", headers=headers)
        assert response.status_code == 200
        flags = response.json()["flags"]
        assert len(flags) == 1
        assert flags[0]["source"] == "爸爸"
        assert flags[0]["flag_type"] == "safety"
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)
        db = FlagsSessionLocal()
        try:
            db.query(ConversationFlag).filter(ConversationFlag.sender_id == patient_uid).delete(
                synchronize_session=False,
            )
            db.commit()
        finally:
            db.close()


def test_companion_role_cannot_add_a_contact(monkeypatch):
    uid = "pytest-perm-companion-add-contact"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)  # creates a default companion profile
        response = client.post("/api/account/contacts", json={"name": "X", "detail": "123"}, headers=headers)
        assert response.status_code == 403
    finally:
        _cleanup(uid)


def test_companion_role_can_still_read_contacts(monkeypatch):
    uid = "pytest-perm-companion-read-contacts"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        response = client.get("/api/account/contacts", headers=headers)
        assert response.status_code == 200
        assert response.json() == []
    finally:
        _cleanup(uid)


def test_companion_role_cannot_delete_a_contact(monkeypatch):
    companion_uid = "pytest-perm-companion-delete-contact"
    caregiver_uid = "pytest-perm-companion-delete-contact-caregiver"
    try:
        monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
        _authenticate_as(monkeypatch, caregiver_uid)
        create = client.post(
            "/api/account/contacts", json={"name": "Y", "detail": "456"}, headers={"Authorization": "Bearer c"},
        )
        contact_id = create.json()["id"]

        _authenticate_as(monkeypatch, companion_uid)
        response = client.delete(
            f"/api/account/contacts/{contact_id}", headers={"Authorization": "Bearer p"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(companion_uid)
        _cleanup(caregiver_uid)


def test_caregiver_role_can_still_add_and_delete_contacts(monkeypatch):
    uid = "pytest-perm-caregiver-contacts"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        create = client.post("/api/account/contacts", json={"name": "Z", "detail": "789"}, headers=headers)
        assert create.status_code == 201
        deletion = client.delete(f"/api/account/contacts/{create.json()['id']}", headers=headers)
        assert deletion.status_code == 200
    finally:
        _cleanup(uid)


def test_companion_role_can_still_generate_a_pairing_code(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-perm-companion-generate-code"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.post("/api/me/pairing-code", json={}, headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
    finally:
        _cleanup(uid)


def test_companion_role_cannot_redeem_a_pairing_code(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, companion_uid = "pytest-perm-link-patient", "pytest-perm-link-companion"
    try:
        _authenticate_as(monkeypatch, patient_uid)
        code = client.post(
            "/api/me/pairing-code", json={}, headers={"Authorization": "Bearer patient"},
        ).json()["code"]

        _authenticate_as(monkeypatch, companion_uid)
        response = client.post(
            "/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer companion"},
        )
        assert response.status_code == 403
    finally:
        _cleanup(patient_uid)
        _cleanup(companion_uid)


def test_companion_role_cannot_list_or_unlink_patients(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-perm-companion-list-linked"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        assert client.get("/api/me/linked-patients", headers=headers).status_code == 403
        assert client.delete("/api/me/linked-patients/whatever", headers=headers).status_code == 403
    finally:
        _cleanup(uid)


def test_new_account_has_not_confirmed_its_identity_yet(monkeypatch):
    uid = "pytest-identity-new-uid"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["identity_confirmed"] is False
        assert response.json()["role"] == "companion"  # storage placeholder, not a real decision yet
    finally:
        _cleanup(uid)


def test_bootstrapped_account_has_identity_confirmed_automatically(monkeypatch):
    uid = "pytest-identity-bootstrap-uid"
    monkeypatch.setenv("COA_BOOTSTRAP_DEVELOPER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["identity_confirmed"] is True
        assert response.json()["role"] == "developer"
    finally:
        _cleanup(uid)


def test_choosing_companion_identity_succeeds(monkeypatch):
    uid = "pytest-identity-choose-companion"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/identity", json={"role": "companion"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "companion"
        assert body["identity_confirmed"] is True
    finally:
        _cleanup(uid)


def test_choosing_caregiver_identity_succeeds(monkeypatch):
    uid = "pytest-identity-choose-caregiver"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/identity", json={"role": "caregiver"}, headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "caregiver"
        assert body["identity_confirmed"] is True
        assert "caregiver_mode" in body["permissions"]
    finally:
        _cleanup(uid)


def test_choosing_developer_or_admin_identity_is_rejected(monkeypatch):
    uid = "pytest-identity-choose-developer"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/identity", json={"role": "developer"}, headers=headers)
        assert response.status_code == 422
        # and the account is still unconfirmed, not silently left half-applied
        assert client.get("/api/me", headers=headers).json()["identity_confirmed"] is False
    finally:
        _cleanup(uid)


def test_identity_cannot_be_chosen_twice(monkeypatch):
    uid = "pytest-identity-choose-twice"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        first = client.post("/api/me/identity", json={"role": "companion"}, headers=headers)
        assert first.status_code == 200
        second = client.post("/api/me/identity", json={"role": "caregiver"}, headers=headers)
        assert second.status_code == 403
        # role from the first choice must be unchanged
        assert client.get("/api/me", headers=headers).json()["role"] == "companion"
    finally:
        _cleanup(uid)


def test_choose_identity_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.post("/api/me/identity", json={"role": "companion"})
    assert response.status_code == 401


def test_linked_caregivers_is_empty_for_an_account_that_never_generated_a_code(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-linked-caregivers-fresh"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me/linked-caregivers", headers={"Authorization": "Bearer fake"})
        assert response.status_code == 200
        assert response.json()["linked_caregivers"] == []
    finally:
        _cleanup(uid)


def test_linked_caregivers_is_empty_before_a_generated_code_is_redeemed(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-linked-caregivers-pending"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.post("/api/me/pairing-code", json={}, headers=headers)
        response = client.get("/api/me/linked-caregivers", headers=headers)
        assert response.json()["linked_caregivers"] == []
    finally:
        _cleanup(uid)


def test_linked_caregivers_shows_up_once_a_caregiver_redeems_the_code(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-linked-caregivers-patient", "pytest-linked-caregivers-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid)
        code = client.post(
            "/api/me/pairing-code", json={}, headers={"Authorization": "Bearer patient"},
        ).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        client.post("/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer caregiver"})

        _authenticate_as(monkeypatch, patient_uid)
        response = client.get("/api/me/linked-caregivers", headers={"Authorization": "Bearer patient"})
        caregivers = response.json()["linked_caregivers"]
        assert len(caregivers) == 1
        assert caregivers[0]["sender_id"] == caregiver_uid
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_linked_caregivers_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.get("/api/me/linked-caregivers")
    assert response.status_code == 401


def test_choosing_caregiver_identity_defaults_into_caregiver_mode(monkeypatch):
    uid = "pytest-default-mode-choose-caregiver"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/identity", json={"role": "caregiver"}, headers=headers)
        assert response.json()["default_mode"] == "caregiver"
    finally:
        _cleanup(uid)


def test_choosing_companion_identity_defaults_into_companion_mode(monkeypatch):
    uid = "pytest-default-mode-choose-companion"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/identity", json={"role": "companion"}, headers=headers)
        assert response.json()["default_mode"] == "companion"
    finally:
        _cleanup(uid)


def test_bootstrapped_caregiver_account_defaults_into_caregiver_mode(monkeypatch):
    uid = "pytest-default-mode-bootstrap-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["default_mode"] == "caregiver"
    finally:
        _cleanup(uid)


def test_new_account_has_not_given_profile_info_yet(monkeypatch):
    uid = "pytest-profile-info-new"
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["profile_info_given"] is False
        assert response.json()["name"] is None
    finally:
        _cleanup(uid)


def test_saving_profile_info_succeeds(monkeypatch):
    uid = "pytest-profile-info-save"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post(
            "/api/me/profile-info", json={"name": "陳大文", "birthday": "1950-01-01"}, headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["profile_info_given"] is True
        assert body["name"] == "陳大文"
        assert body["birthday"] == "1950-01-01"
    finally:
        _cleanup(uid)


def test_profile_info_requires_a_name(monkeypatch):
    uid = "pytest-profile-info-blank-name"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        response = client.post("/api/me/profile-info", json={"name": "  ", "birthday": ""}, headers=headers)
        assert response.status_code == 422
    finally:
        _cleanup(uid)


def test_profile_info_can_be_saved_again_later(monkeypatch):
    uid = "pytest-profile-info-update"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.post("/api/me/profile-info", json={"name": "陳大文", "birthday": ""}, headers=headers)
        second = client.post("/api/me/profile-info", json={"name": "陳小文", "birthday": ""}, headers=headers)
        assert second.status_code == 200
        assert second.json()["name"] == "陳小文"
    finally:
        _cleanup(uid)


def test_profile_info_requires_authentication(monkeypatch):
    monkeypatch.setattr("backend.api.web_account.is_configured", lambda: True)
    response = client.post("/api/me/profile-info", json={"name": "X", "birthday": ""})
    assert response.status_code == 401


def test_email_is_mirrored_from_firebase_onto_the_profile(monkeypatch):
    uid = "pytest-profile-email-mirror"
    _authenticate_as(monkeypatch, uid, email="chan@example.com")
    try:
        response = client.get("/api/me", headers={"Authorization": "Bearer fake"})
        assert response.json()["email"] == "chan@example.com"
    finally:
        _cleanup(uid)


def test_pairing_code_uses_the_collected_name_as_the_registry_display_name(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-pairing-name-patient", "pytest-pairing-name-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid)
        headers = {"Authorization": "Bearer patient"}
        client.post("/api/me/profile-info", json={"name": "王小明", "birthday": ""}, headers=headers)
        code = client.post("/api/me/pairing-code", json={}, headers=headers).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        linked = client.post(
            "/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer caregiver"},
        ).json()["linked_patients"]
        assert linked[0]["display_name"] == "王小明"
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_linked_patients_includes_the_patients_email(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    patient_uid, caregiver_uid = "pytest-linked-email-patient", "pytest-linked-email-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        _authenticate_as(monkeypatch, patient_uid, email="patient@example.com")
        headers = {"Authorization": "Bearer patient"}
        code = client.post("/api/me/pairing-code", json={}, headers=headers).json()["code"]

        _authenticate_as(monkeypatch, caregiver_uid)
        linked = client.post(
            "/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer caregiver"},
        ).json()["linked_patients"]
        assert linked[0]["email"] == "patient@example.com"
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def _link_patient_to_caregiver(monkeypatch, patient_uid, caregiver_uid, *, patient_email=None):
    _authenticate_as(monkeypatch, patient_uid, email=patient_email)
    code = client.post(
        "/api/me/pairing-code", json={}, headers={"Authorization": "Bearer patient"},
    ).json()["code"]
    _authenticate_as(monkeypatch, caregiver_uid)
    linked = client.post(
        "/api/me/link-patient", json={"code": code}, headers={"Authorization": "Bearer caregiver"},
    ).json()["linked_patients"]
    return linked[0]["user_id"]


def test_deleting_a_linked_patient_account_removes_their_profile(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setattr("backend.api.web_account.delete_user", lambda uid: None)
    patient_uid, caregiver_uid = "pytest-delete-patient", "pytest-delete-patient-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        patient_user_id = _link_patient_to_caregiver(monkeypatch, patient_uid, caregiver_uid)

        _authenticate_as(monkeypatch, caregiver_uid)
        response = client.request(
            "DELETE",
            f"/api/me/linked-patients/{patient_user_id}/account",
            json={"confirmation": "確定刪除"},
            headers={"Authorization": "Bearer caregiver"},
        )
        assert response.status_code == 200
        assert response.json()["linked_patients"] == []

        # The deleted account's profile should be gone — a fresh GET /api/me
        # for that uid creates a brand-new, unconfirmed profile again.
        _authenticate_as(monkeypatch, patient_uid)
        fresh = client.get("/api/me", headers={"Authorization": "Bearer patient"})
        assert fresh.json()["identity_confirmed"] is False
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_deleting_a_patient_account_requires_the_exact_confirmation_phrase(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setattr("backend.api.web_account.delete_user", lambda uid: None)
    patient_uid, caregiver_uid = "pytest-delete-wrong-phrase-patient", "pytest-delete-wrong-phrase-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        patient_user_id = _link_patient_to_caregiver(monkeypatch, patient_uid, caregiver_uid)
        _authenticate_as(monkeypatch, caregiver_uid)
        response = client.request(
            "DELETE",
            f"/api/me/linked-patients/{patient_user_id}/account",
            json={"confirmation": "delete"},
            headers={"Authorization": "Bearer caregiver"},
        )
        assert response.status_code == 422
        # and the patient must still be linked — nothing was actually removed
        listing = client.get("/api/me/linked-patients", headers={"Authorization": "Bearer caregiver"})
        assert len(listing.json()["linked_patients"]) == 1
    finally:
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)


def test_deleting_a_non_linked_patient_account_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-delete-not-linked-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", uid)
    _authenticate_as(monkeypatch, uid)
    try:
        response = client.request(
            "DELETE",
            "/api/me/linked-patients/patient_doesnotexist/account",
            json={"confirmation": "確定刪除"},
            headers={"Authorization": "Bearer fake"},
        )
        assert response.status_code == 404
    finally:
        _cleanup(uid)


def test_deleting_a_patient_account_requires_caregiver_mode_permission(monkeypatch, tmp_path):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    uid = "pytest-delete-companion-forbidden"
    _authenticate_as(monkeypatch, uid)
    headers = {"Authorization": "Bearer fake"}
    try:
        client.get("/api/me", headers=headers)
        response = client.request(
            "DELETE", "/api/me/linked-patients/whatever/account", json={"confirmation": "確定刪除"}, headers=headers,
        )
        assert response.status_code == 403
    finally:
        _cleanup(uid)


def test_deleting_a_patient_account_also_removes_their_conversation_flags(monkeypatch, tmp_path):
    from src.user.conversation_flags import delete_flags_for_sender, get_recent_flags as _get_recent_flags, maybe_flag_turn

    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setattr("backend.api.web_account.delete_user", lambda uid: None)
    patient_uid, caregiver_uid = "pytest-delete-flags-patient", "pytest-delete-flags-caregiver"
    monkeypatch.setenv("COA_BOOTSTRAP_CAREGIVER_UIDS", caregiver_uid)
    try:
        delete_flags_for_sender(patient_uid)  # in case a prior failed run left flags behind
        patient_user_id = _link_patient_to_caregiver(monkeypatch, patient_uid, caregiver_uid)
        maybe_flag_turn(patient_uid, "chest pain", answer_callable=None)
        assert len(_get_recent_flags(patient_uid)) == 1

        _authenticate_as(monkeypatch, caregiver_uid)
        client.request(
            "DELETE",
            f"/api/me/linked-patients/{patient_user_id}/account",
            json={"confirmation": "確定刪除"},
            headers={"Authorization": "Bearer caregiver"},
        )
        assert _get_recent_flags(patient_uid) == []
    finally:
        delete_flags_for_sender(patient_uid)
        _cleanup(patient_uid)
        _cleanup(caregiver_uid)
