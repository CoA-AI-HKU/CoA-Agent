from __future__ import annotations

import logging
import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from pydantic import BaseModel, Field

from backend.services.account_profiles import (
    PermissionDeniedError,
    PreferencePermissionError,
    PreferenceValidationError,
    choose_identity,
    get_or_create_profile,
    profile_to_me_response,
    record_consent,
    record_profile_info,
    require_permission,
    update_preferences,
)
from backend.services.accounts_database import SessionLocal, WebAccountProfile, WebContact
from backend.services.firebase_auth import FirebaseUser, delete_user, is_configured, verify_id_token
from src.user.conversation_flags import delete_flags_for_sender, get_monitoring_history, get_recent_flags
from src.health.blood_pressure import (
    delete_blood_pressure_reading,
    delete_blood_pressure_readings,
    get_blood_pressure_retention,
    list_blood_pressure_readings,
    set_blood_pressure_retention,
    update_blood_pressure_reading,
)
from src.user.monitoring_preferences import (
    get_monitoring_preferences,
    set_monitoring_pause,
    set_monitoring_preferences,
    set_monitoring_thresholds,
    set_patient_monitoring_consent,
)
from src.user.user_registry import (
    create_pairing_code,
    get_caregiver_records_for_user,
    get_linked_user_ids,
    get_registry_user_id,
    get_user_record_by_user_id,
    redeem_pairing_code,
    register_account,
    revoke_caregivers_for_user,
    unlink_caregiver,
)

logger = logging.getLogger(__name__)

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
    high_contrast_mode: bool | None = None
    auto_send: bool | None = None


@me_router.get("/api/me")
def me(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    profile = get_or_create_profile(user)
    return profile_to_me_response(profile)


class ChooseIdentityRequest(BaseModel):
    role: str = Field(min_length=1, max_length=20)


@me_router.post("/api/me/identity")
def post_identity(
    payload: ChooseIdentityRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    # One-time, first-run only — see choose_identity's docstring for why a
    # second call (from an account that already picked) is rejected rather
    # than silently allowed to switch.
    get_or_create_profile(user)
    try:
        profile = choose_identity(user.uid, payload.role)
    except PreferencePermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PreferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return profile_to_me_response(profile)


class ProfileInfoRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    birthday: str = Field(default="", max_length=20)
    # Mainly meaningful for a patient account — the frontend only shows
    # these fields for role "companion" — but accepted unconditionally
    # here since an empty value is harmless for any other role.
    emergency_contact_name: str = Field(default="", max_length=100)
    emergency_contact_phone: str = Field(default="", max_length=40)


@me_router.post("/api/me/profile-info")
def post_profile_info(
    payload: ProfileInfoRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    get_or_create_profile(user)
    try:
        profile = record_profile_info(
            user.uid, payload.name, payload.birthday,
            payload.emergency_contact_name, payload.emergency_contact_phone,
        )
    except PreferenceValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    #
    # Prefers the name collected on the profile-info screen (see
    # record_profile_info) — that's what a caregiver actually sees identifying
    # this account, so it needs to be a real name, not Firebase's often-empty
    # display_name.
    profile = get_or_create_profile(user)
    display_name = (
        (payload.display_name or "").strip() or profile.name or user.email or user.display_name or ""
    )
    register_account(user.uid, "user", display_name=display_name)
    code = create_pairing_code(user.uid)
    return {"code": code, "expires_in_minutes": 15}


@me_router.get("/api/me/linked-caregivers")
def list_linked_caregivers(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    # The patient-side mirror of /api/me/linked-patients below — lets the
    # frontend tell "never paired yet" (registry_user_id is None: this
    # account has never even generated a code) and "already has a
    # caregiver" apart, so it knows when to stop offering to generate a new
    # pairing code (see web/index.html's loadLinkedCaregivers()).
    registry_user_id = get_registry_user_id(user.uid)
    caregivers = []
    if registry_user_id:
        for caregiver_sender_id, record in get_caregiver_records_for_user(registry_user_id):
            display_name = str(record.get("display_name") or "").strip() or caregiver_sender_id
            caregivers.append({"sender_id": caregiver_sender_id, "display_name": display_name})
    return {"linked_caregivers": caregivers}


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


class DeletePatientAccountRequest(BaseModel):
    # The typed confirmation phrase lives client-side (see web/index.html's
    # deletePatientAccount()) — this field just proves the request actually
    # went through that flow rather than being silently automatable.
    confirmation: str = Field(min_length=1, max_length=20)


REQUIRED_DELETE_CONFIRMATION = "確定刪除"


@me_router.delete("/api/me/linked-patients/{patient_user_id}/account")
def delete_linked_patient_account(
    patient_user_id: str,
    payload: DeletePatientAccountRequest,
    user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    """Permanently delete a linked patient's entire account — not just the
    link. Irreversible: removes their Firebase sign-in, their profile,
    contacts, and stored conversation flags. A caregiver may only do this
    to a patient actually linked to them (checked below), and only after
    the frontend's typed-confirmation step.
    """
    _require_permission(user, "caregiver_mode")
    if payload.confirmation.strip() != REQUIRED_DELETE_CONFIRMATION:
        raise HTTPException(status_code=422, detail=f"confirmation text must be {REQUIRED_DELETE_CONFIRMATION!r}")
    if patient_user_id not in get_linked_user_ids(user.uid):
        raise HTTPException(status_code=404, detail="patient not found or not linked to this account")

    sender_id, _ = get_user_record_by_user_id(patient_user_id)
    delete_blood_pressure_readings(patient_user_id)

    # Local cleanup first: if Firebase deletion below fails, the account is
    # still left in a safe, self-healing state (a login with no profile
    # just re-triggers onboarding), rather than a deleted login with
    # orphaned local data.
    if sender_id:
        db = SessionLocal()
        try:
            db.query(WebContact).filter(WebContact.firebase_uid == sender_id).delete(synchronize_session=False)
            db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == sender_id).delete(
                synchronize_session=False,
            )
            db.commit()
        finally:
            db.close()
        delete_flags_for_sender(sender_id)
        # revoke_caregivers_for_user takes the patient's sender_id, not the
        # opaque registry user_id — it resolves the user_id internally.
        revoke_caregivers_for_user(sender_id)
        try:
            delete_user(sender_id)
        except Exception:
            logger.exception("Failed to delete Firebase account for sender_id=%s", sender_id)

    return {"deleted_patient_user_id": patient_user_id, "linked_patients": _linked_patients(user.uid)}


def _linked_patients(caregiver_uid: str) -> list[dict[str, str | None]]:
    patients = []
    for patient_user_id in get_linked_user_ids(caregiver_uid):
        sender_id, record = get_user_record_by_user_id(patient_user_id)
        display_name = str(record.get("display_name") or "").strip() or patient_user_id
        # Only web-based patients have a WebAccountProfile row at all (a
        # Telegram-only patient won't, and that's fine — email stays None).
        email = None
        if sender_id:
            db = SessionLocal()
            try:
                patient_profile = (
                    db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == sender_id).first()
                )
                if patient_profile is not None:
                    email = patient_profile.email
            finally:
                db.close()
        patients.append({"user_id": patient_user_id, "display_name": display_name, "email": email})
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


def _readable_contact_owner_ids(user: FirebaseUser) -> list[str]:
    """This account's own contacts, plus (if it's a patient) any linked
    caregiver's — a caregiver manages the shared contact book, and a
    patient's Companion Mode (the "call caregiver" button) needs to read
    what they entered without the patient ever having write access to it.
    """
    owner_ids = [user.uid]
    registry_user_id = get_registry_user_id(user.uid)
    if registry_user_id:
        for caregiver_sender_id, _record in get_caregiver_records_for_user(registry_user_id):
            if caregiver_sender_id not in owner_ids:
                owner_ids.append(caregiver_sender_id)
    return owner_ids


@router.get("/contacts", response_model=list[ContactResponse])
def list_contacts(user: FirebaseUser = Depends(require_firebase_user)) -> list[WebContact]:
    db = SessionLocal()
    try:
        return (
            db.query(WebContact)
            .filter(WebContact.firebase_uid.in_(_readable_contact_owner_ids(user)))
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


def _resolve_linked_patient_sender_id(user: FirebaseUser, patient_user_id: str) -> str:
    """The patient's own chat/account identity, only for a patient actually
    linked to this caregiver — shared guard for every /linked-patients/{id}/
    contacts endpoint below."""
    if patient_user_id not in get_linked_user_ids(user.uid):
        raise HTTPException(status_code=404, detail="patient not found or not linked to this account")
    sender_id, _ = get_user_record_by_user_id(patient_user_id)
    if not sender_id:
        raise HTTPException(status_code=404, detail="patient has no resolvable account")
    return sender_id


def _own_blood_pressure_user_id(user: FirebaseUser) -> str:
    return get_registry_user_id(user.uid) or user.uid


class BloodPressureUpdateRequest(BaseModel):
    systolic: int = Field(ge=50, le=260)
    diastolic: int = Field(ge=30, le=160)
    pulse: int | None = Field(default=None, ge=30, le=250)
    notes: str = Field(default="", max_length=500)


class BloodPressureRetentionRequest(BaseModel):
    retention_days: int


class DeleteBloodPressureRequest(BaseModel):
    confirmation: str = Field(min_length=1, max_length=30)


def _update_reading(patient_user_id: str, reading_id: int, payload: BloodPressureUpdateRequest) -> dict[str, object]:
    try:
        reading = update_blood_pressure_reading(patient_user_id, reading_id, **payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if reading is None:
        raise HTTPException(status_code=404, detail="blood pressure reading not found")
    return reading


def _delete_reading(patient_user_id: str, reading_id: int) -> dict[str, int]:
    if not delete_blood_pressure_reading(patient_user_id, reading_id):
        raise HTTPException(status_code=404, detail="blood pressure reading not found")
    return {"removed": 1}


def _export_readings(patient_user_id: str) -> Response:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["measured_at", "systolic", "diastolic", "pulse", "notes"])
    for reading in list_blood_pressure_readings(patient_user_id, limit=10000):
        writer.writerow([reading["measured_at"], reading["systolic"], reading["diastolic"], reading["pulse"] or "", reading["notes"]])
    return Response(
        content="\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="blood-pressure-readings.csv"'},
    )


def _set_retention(patient_user_id: str, retention_days: int) -> dict[str, int]:
    try:
        return {"retention_days": set_blood_pressure_retention(patient_user_id, retention_days)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@me_router.get("/api/me/blood-pressure")
def get_own_blood_pressure(limit: int = Query(default=30, ge=1, le=90), user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    patient_user_id = _own_blood_pressure_user_id(user)
    return {"patient_user_id": patient_user_id, "readings": list_blood_pressure_readings(patient_user_id, limit=limit),
            "retention_days": get_blood_pressure_retention(patient_user_id)}


@me_router.patch("/api/me/blood-pressure/{reading_id}")
def patch_own_blood_pressure(reading_id: int, payload: BloodPressureUpdateRequest,
                             user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, object]:
    return _update_reading(_own_blood_pressure_user_id(user), reading_id, payload)


@me_router.delete("/api/me/blood-pressure/{reading_id}")
def delete_own_blood_pressure(reading_id: int, user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    return _delete_reading(_own_blood_pressure_user_id(user), reading_id)


@me_router.get("/api/me/blood-pressure-export")
def export_own_blood_pressure(user: FirebaseUser = Depends(require_firebase_user)) -> Response:
    return _export_readings(_own_blood_pressure_user_id(user))


@me_router.put("/api/me/blood-pressure-retention")
def put_own_blood_pressure_retention(payload: BloodPressureRetentionRequest,
                                     user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    return _set_retention(_own_blood_pressure_user_id(user), payload.retention_days)


@me_router.delete("/api/me/blood-pressure")
def delete_all_own_blood_pressure(payload: DeleteBloodPressureRequest,
                                  user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    if payload.confirmation.strip() != "刪除全部血壓記錄":
        raise HTTPException(status_code=422, detail="incorrect confirmation text")
    return {"removed": delete_blood_pressure_readings(_own_blood_pressure_user_id(user))}


@me_router.get("/api/me/linked-patients/{patient_user_id}/blood-pressure")
def get_linked_patient_blood_pressure(
    patient_user_id: str,
    limit: int = Query(default=30, ge=1, le=90),
    user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    return {
        "patient_user_id": patient_user_id,
        "readings": list_blood_pressure_readings(patient_user_id, limit=limit),
        "retention_days": get_blood_pressure_retention(patient_user_id),
    }


@me_router.patch("/api/me/linked-patients/{patient_user_id}/blood-pressure/{reading_id}")
def patch_linked_patient_blood_pressure(patient_user_id: str, reading_id: int, payload: BloodPressureUpdateRequest,
                                        user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, object]:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    return _update_reading(patient_user_id, reading_id, payload)


@me_router.delete("/api/me/linked-patients/{patient_user_id}/blood-pressure/{reading_id}")
def delete_linked_patient_blood_pressure(patient_user_id: str, reading_id: int,
                                         user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    return _delete_reading(patient_user_id, reading_id)


@me_router.get("/api/me/linked-patients/{patient_user_id}/blood-pressure-export")
def export_linked_patient_blood_pressure(patient_user_id: str,
                                         user: FirebaseUser = Depends(require_firebase_user)) -> Response:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    return _export_readings(patient_user_id)


@me_router.put("/api/me/linked-patients/{patient_user_id}/blood-pressure-retention")
def put_linked_patient_blood_pressure_retention(patient_user_id: str, payload: BloodPressureRetentionRequest,
                                                user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    return _set_retention(patient_user_id, payload.retention_days)


@me_router.delete("/api/me/linked-patients/{patient_user_id}/blood-pressure")
def delete_all_linked_patient_blood_pressure(patient_user_id: str, payload: DeleteBloodPressureRequest,
                                             user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, int]:
    _require_permission(user, "caregiver_mode")
    _resolve_linked_patient_sender_id(user, patient_user_id)
    if payload.confirmation.strip() != "刪除全部血壓記錄":
        raise HTTPException(status_code=422, detail="incorrect confirmation text")
    return {"removed": delete_blood_pressure_readings(patient_user_id)}


@me_router.get("/api/me/linked-patients/{patient_user_id}/contacts", response_model=list[ContactResponse])
def list_linked_patient_contacts(
    patient_user_id: str, user: FirebaseUser = Depends(require_firebase_user),
) -> list[WebContact]:
    # What's stored directly on this one patient's account — distinct from
    # the caregiver's own /api/account/contacts list, which is shared across
    # every patient they're linked to (see _readable_contact_owner_ids).
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    db = SessionLocal()
    try:
        return (
            db.query(WebContact)
            .filter(WebContact.firebase_uid == sender_id)
            .order_by(WebContact.id)
            .all()
        )
    finally:
        db.close()


@me_router.post(
    "/api/me/linked-patients/{patient_user_id}/contacts", response_model=ContactResponse, status_code=201,
)
def add_linked_patient_contact(
    patient_user_id: str, payload: ContactRequest, user: FirebaseUser = Depends(require_firebase_user),
) -> WebContact:
    # Stored under the patient's own firebase_uid, not the caregiver's — it
    # shows up the moment the patient reads /api/account/contacts (as one of
    # "this account's own contacts", see _readable_contact_owner_ids) and
    # stays scoped to this one patient, unlike the caregiver's blanket
    # contact list, which every linked patient reads.
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    db = SessionLocal()
    try:
        contact = WebContact(firebase_uid=sender_id, name=payload.name.strip(), detail=payload.detail.strip())
        db.add(contact)
        db.commit()
        db.refresh(contact)
        return contact
    finally:
        db.close()


@me_router.delete("/api/me/linked-patients/{patient_user_id}/contacts/{contact_id}")
def delete_linked_patient_contact(
    patient_user_id: str, contact_id: int, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, int]:
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    db = SessionLocal()
    try:
        deleted = (
            db.query(WebContact)
            .filter(WebContact.id == contact_id, WebContact.firebase_uid == sender_id)
            .delete(synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="contact not found")
    return {"removed": deleted}


class MonitoringPreferencesRequest(BaseModel):
    # Both optional — a caregiver can toggle one category at a time without
    # having to resend the other's current value (see
    # set_monitoring_preferences's partial-update semantics).
    safety: bool | None = None
    cognitive_decline: bool | None = None
    sleep: bool | None = None
    daily_activity: bool | None = None
    routine_adherence: bool | None = None
    thresholds: dict[str, int] | None = None
    pause_until: str | None = None


class MonitoringConsentRequest(BaseModel):
    safety: bool | None = None
    cognitive_decline: bool | None = None
    sleep: bool | None = None
    daily_activity: bool | None = None
    routine_adherence: bool | None = None


class MonitoringPauseRequest(BaseModel):
    pause_until: str | None = None


@me_router.get("/api/me/monitoring-consent")
def get_own_monitoring_consent(user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    return get_monitoring_preferences(user.uid)


@me_router.put("/api/me/monitoring-consent")
def put_own_monitoring_consent(payload: MonitoringConsentRequest,
                               user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    return set_patient_monitoring_consent(user.uid, **payload.model_dump())


@me_router.put("/api/me/monitoring-pause")
def put_own_monitoring_pause(payload: MonitoringPauseRequest,
                             user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    return set_monitoring_pause(user.uid, payload.pause_until)


@me_router.get("/api/me/monitoring-history")
def get_own_monitoring_history(days: int = Query(default=14, ge=1, le=14),
                               user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    return get_monitoring_history(user.uid, days=days)


@me_router.get("/api/me/linked-patients/{patient_user_id}/monitoring")
def get_linked_patient_monitoring(
    patient_user_id: str, user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    return get_monitoring_preferences(sender_id)


@me_router.get("/api/me/linked-patients/{patient_user_id}/monitoring-history")
def get_linked_patient_monitoring_history(patient_user_id: str, days: int = Query(default=14, ge=1, le=14),
                                          user: FirebaseUser = Depends(require_firebase_user)) -> dict[str, Any]:
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    return get_monitoring_history(sender_id, days=days)


@me_router.put("/api/me/linked-patients/{patient_user_id}/monitoring")
def put_linked_patient_monitoring(
    patient_user_id: str,
    payload: MonitoringPreferencesRequest,
    user: FirebaseUser = Depends(require_firebase_user),
) -> dict[str, Any]:
    # The caregiver selects requested categories; effective monitoring is
    # still independently gated by the patient's own consent settings.
    _require_permission(user, "caregiver_mode")
    sender_id = _resolve_linked_patient_sender_id(user, patient_user_id)
    preferences = set_monitoring_preferences(
        sender_id, safety=payload.safety, cognitive_decline=payload.cognitive_decline,
        sleep=payload.sleep, daily_activity=payload.daily_activity,
        routine_adherence=payload.routine_adherence,
    )
    if payload.thresholds is not None:
        try:
            preferences = set_monitoring_thresholds(sender_id, **payload.thresholds)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.pause_until is not None:
        preferences = set_monitoring_pause(sender_id, payload.pause_until)
    return preferences
