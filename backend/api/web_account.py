from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from backend.services.account_profiles import (
    PreferencePermissionError,
    PreferenceValidationError,
    get_or_create_profile,
    profile_to_me_response,
    record_consent,
    update_preferences,
)
from backend.services.accounts_database import SessionLocal, WebContact
from backend.services.firebase_auth import FirebaseUser, is_configured, verify_id_token

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
