from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.services.account_profiles import (
    PermissionDeniedError,
    PreferencePermissionError,
    PreferenceValidationError,
    get_or_create_profile,
    profile_to_me_response,
    record_consent,
    require_permission,
    update_preferences,
)
from backend.services.accounts_database import SessionLocal, WebContact
from backend.services.firebase_auth import FirebaseUser, is_configured, verify_id_token
from src.user.conversation_flags import get_recent_flags
from src.user.user_registry import (
    create_pairing_code,
    get_linked_user_ids,
    get_user_record_by_user_id,
    redeem_pairing_code,
    register_account,
    unlink_caregiver,
)

router = APIRouter(prefix="/api/account", tags=["account"])
# No prefix — the spec for this endpoint names it exactly /api/me, and it is
# conceptually account-wide (role, permissions, preferences) rather than a
# sub-resource of /api/account.
me_router = APIRouter(tags=["me"])


def require_firebase_user(authorization: str | None = Header(default=None)) -> FirebaseUser:
    if not is_configured():
        raise HTTPException(status_code=503, detail="account sign-in is not set up on this server yet")
    scheme, _, token = str(authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="bearer ID token is required")
    user = verify_id_token(token)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid or expired sign-in")
    return user


def _require_permission(user: FirebaseUser, permission: str) -> None:
    profile = get_or_create_profile(user)
    try:
        require_permission(profile, permission)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


class PreferencesUpdateRequest(BaseModel):
    # Deliberately no `role` field — role is never client-writable (see
    # backend/services/account_profiles.py). Anything sent for `role` here
    # is silently ignored, not just rejected, since Pydantic drops unknown
    # fields by default and this model never declares one.
    default_mode: str | None = None
    recognition_language: str | None = None
    talk_mode: str | None = None
    speech_speed: float | None = None
    voice_name: str | None = None
    auto_speak: bool | None = None
    transcript_visible: bool | None = None
    auto_send: bool | None = None


@me_router.get("/api/me")
def me(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    profile = get_or_create_profile(user)
    return profile_to_me_response(profile)


@me_router.post("/api/me/consent")
def post_consent(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    # No request body — agreeing is a single, all-or-nothing action (see the
    # consent gate in web/index.html); there is nothing partial to submit.
    get_or_create_profile(user)
    profile = record_consent(user.uid)
    return profile_to_me_response(profile)


@me_router.put("/api/me/preferences")
def put_preferences(
    payload: PreferencesUpdateRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    # Ensures a profile row exists (and applies any bootstrap-role upgrade)
    # before attempting the update, so a brand-new account's first API call
    # ever doesn't have to be GET /api/me before this can succeed.
    get_or_create_profile(user)
    updates = {key: value for key, value in payload.model_dump().items() if value is not None}
    try:
        profile = update_preferences(user.uid, updates)
    except PreferencePermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PreferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profile_to_me_response(profile)


@me_router.get("/api/me/conversation-flags")
def get_conversation_flags(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    # This account's own flags, plus any linked patient's (see the pairing
    # endpoints below) — each entry tagged with whose it is. Never includes
    # raw message text, only the short stored reason (see ConversationFlag).
    combined = [dict(flag, source="自己") for flag in get_recent_flags(user.uid)]
    for patient in _linked_patients(user.uid):
        sender_id, _ = get_user_record_by_user_id(patient["user_id"])
        if not sender_id:
            continue
        combined.extend(dict(flag, source=patient["display_name"]) for flag in get_recent_flags(sender_id))
    combined.sort(key=lambda flag: flag["created_at"], reverse=True)
    return {"flags": combined}


class PairingCodeRequest(BaseModel):
    display_name: str | None = None


@me_router.post("/api/me/pairing-code")
def create_my_pairing_code(
    payload: PairingCodeRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    # Registers this account as a "patient" in the same registry Telegram's
    # \paircode command uses (src/user/user_registry.py) — the code this
    # returns works identically whether it's redeemed from Telegram's \link
    # or from a web caregiver's /api/me/link-patient below.
    register_account(user.uid, "user", display_name=payload.display_name or user.display_name or "")
    code = create_pairing_code(user.uid)
    return {"code": code, "expires_in_minutes": 15}


class LinkPatientRequest(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@me_router.post("/api/me/link-patient")
def link_patient(
    payload: LinkPatientRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    # Redeeming a code is the caregiver-side action — a companion-only
    # account can still generate its own code above (that's the patient
    # side, open to every role), but only a caregiver-capable role may
    # link *to* someone else's account.
    _require_permission(user, "caregiver_mode")
    register_account(user.uid, "caregiver", display_name=user.display_name or "")
    try:
        redeem_pairing_code(user.uid, payload.code)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"linked_patients": _linked_patients(user.uid)}


@me_router.get("/api/me/linked-patients")
def list_linked_patients(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    _require_permission(user, "caregiver_mode")
    return {"linked_patients": _linked_patients(user.uid)}


@me_router.delete("/api/me/linked-patients/{patient_user_id}")
def remove_linked_patient(
    patient_user_id: str, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    _require_permission(user, "caregiver_mode")
    try:
        removed = unlink_caregiver(user.uid, patient_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"removed": removed, "linked_patients": _linked_patients(user.uid)}


def _linked_patients(caregiver_uid: str) -> list[dict[str, str]]:
    patients = []
    for patient_user_id in get_linked_user_ids(caregiver_uid):
        _, record = get_user_record_by_user_id(patient_user_id)
        display_name = str(record.get("display_name") or "").strip() or patient_user_id
        patients.append({"user_id": patient_user_id, "display_name": display_name})
    return patients


class ContactRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    detail: str = Field(min_length=1, max_length=200)


class ContactResponse(BaseModel):
    id: int
    name: str
    detail: str

    class Config:
        from_attributes = True


@router.get("/contacts", response_model=list[ContactResponse])
def list_contacts(user: FirebaseUser = Depends(require_firebase_user)) -> list[WebContact]:
    db = SessionLocal()
    try:
        return (
            db.query(WebContact)
            .filter(WebContact.firebase_uid == user.uid)
            .order_by(WebContact.id)
            .all()
        )
    finally:
        db.close()


@router.post("/contacts", response_model=ContactResponse, status_code=201)
def add_contact(payload: ContactRequest, user: FirebaseUser = Depends(require_firebase_user)) -> WebContact:
    # Reading contacts stays open to every role (Companion Mode's "call
    # caregiver" button needs to read them) — only adding/removing is
    # gated, since managing the contact list is a caregiver action.
    _require_permission(user, "contacts")
    db = SessionLocal()
    try:
        contact = WebContact(firebase_uid=user.uid, name=payload.name.strip(), detail=payload.detail.strip())
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return contact
    finally:
        db.close()


@router.delete("/contacts/{contact_id}")
def delete_contact(contact_id: int, user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    _require_permission(user, "contacts")
    db = SessionLocal()
    try:
        deleted = (
            db.query(WebContact)
            .filter(WebContact.id == contact_id, WebContact.firebase_uid == user.uid)
            .delete(synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="contact not found")
    return {"removed": deleted}
