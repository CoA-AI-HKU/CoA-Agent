from __future__ import annotations

import os
from datetime import datetime
from typing import Any

from backend.services.accounts_database import SessionLocal, WebAccountProfile
from backend.services.firebase_auth import FirebaseUser

# Lowest to highest privilege. Used only to decide whether a bootstrap match
# (see _bootstrap_role below) should *raise* an existing role — never to
# lower one. There is no self-service or API path that lowers a role either;
# role changes only ever happen via this bootstrap check or direct DB access,
# both server-side and outside any request a signed-in account controls.
ROLE_RANK = {"companion": 0, "caregiver": 1, "developer": 2, "admin": 3}

# What each role may do. Checked server-side on every protected request
# (see backend/api/web_account.py) — the frontend's mode switcher only
# reads this same list to decide what UI to show; it is not itself a
# security boundary.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "companion": ["chat", "voice"],
    "caregiver": ["chat", "voice", "contacts", "reminders_info", "preferences", "caregiver_mode"],
    "developer": [
        "chat", "voice", "contacts", "reminders_info", "preferences",
        "caregiver_mode", "developer_mode",
    ],
    "admin": [
        "chat", "voice", "contacts", "reminders_info", "preferences",
        "caregiver_mode", "developer_mode", "admin",
    ],
}

# Which modes an account may set as its default_mode. A companion-only
# account can never default into caregiver/developer mode even by editing
# its own preferences — see update_preferences's validation below.
ROLE_ALLOWED_MODES: dict[str, list[str]] = {
    "companion": ["companion"],
    "caregiver": ["companion", "caregiver"],
    "developer": ["companion", "caregiver", "developer"],
    "admin": ["companion", "caregiver", "developer", "admin"],
}

# Every mode that exists at all, regardless of role — used to tell "not a
# real mode" (422, malformed input) apart from "a real mode this role just
# isn't permitted to use" (403, a permission decision) in update_preferences.
MODE_LABELS_KNOWN = frozenset(ROLE_ALLOWED_MODES["admin"])

PREFERENCE_FIELDS = (
    "default_mode", "recognition_language", "talk_mode", "speech_speed",
    "voice_name", "auto_speak", "transcript_visible", "auto_send",
)


def _bootstrap_role(user: FirebaseUser) -> str | None:
    """Check env-configured allowlists for a role this account should have.

    There is no admin UI yet to promote an account, so the first
    developer/admin has to be granted somehow without direct DB surgery:
    set COA_BOOTSTRAP_DEVELOPER_UIDS / _EMAILS (or _ADMIN_...) to a
    comma-separated list of Firebase UIDs and/or verified emails, restart
    the backend, and sign in — get_or_create_profile below re-checks this
    on every load and raises the stored role to match, but never lowers it,
    so removing the env var later does not silently demote anyone.
    """
    candidates = {value.strip() for value in (user.uid, user.email or "") if value.strip()}

    def _matches(env_var: str) -> bool:
        configured = {v.strip() for v in os.getenv(env_var, "").split(",") if v.strip()}
        return bool(candidates & configured)

    if _matches("COA_BOOTSTRAP_ADMIN_UIDS") or _matches("COA_BOOTSTRAP_ADMIN_EMAILS"):
        return "admin"
    if _matches("COA_BOOTSTRAP_DEVELOPER_UIDS") or _matches("COA_BOOTSTRAP_DEVELOPER_EMAILS"):
        return "developer"
    if _matches("COA_BOOTSTRAP_CAREGIVER_UIDS") or _matches("COA_BOOTSTRAP_CAREGIVER_EMAILS"):
        return "caregiver"
    return None


def get_or_create_profile(user: FirebaseUser) -> WebAccountProfile:
    db = SessionLocal()
    try:
        profile = db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == user.uid).first()
        bootstrap = _bootstrap_role(user)
        if profile is None:
            # A brand-new developer/admin account starts in review-before-
            # send mode (auto_send=False) — lets a Cantonese speaker talk
            # while the developer inspects/corrects the transcript before
            # it's actually submitted. Every other role keeps the normal
            # auto_send=True default.
            initial_role = bootstrap if bootstrap else "companion"
            profile = WebAccountProfile(
                firebase_uid=user.uid,
                role=initial_role,
                default_mode="companion",
                auto_send=initial_role not in ("developer", "admin"),
            )
            db.add(profile)
            db.commit()
            db.refresh(profile)
            return profile

        if bootstrap and ROLE_RANK.get(bootstrap, 0) > ROLE_RANK.get(profile.role, 0):
            profile.role = bootstrap
            # A newly-elevated account's default_mode must stay one it's
            # actually allowed into — "companion" always qualifies, so this
            # never needs to change unless it was already, impossibly, set
            # to something outside the (now-larger) allowed set.
            db.commit()
            db.refresh(profile)
        return profile
    finally:
        db.close()


def record_consent(firebase_uid: str) -> WebAccountProfile:
    """Mark the consent form as agreed to. Idempotent — a second call from an
    already-consented account just keeps the original timestamp, it does not
    matter here whether the account is new or returning.
    """
    db = SessionLocal()
    try:
        profile = db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == firebase_uid).first()
        if profile is None:
            raise PreferenceValidationError("no profile found for this account")
        if profile.consent_accepted_at is None:
            profile.consent_accepted_at = datetime.utcnow()
            db.commit()
            db.refresh(profile)
        return profile
    finally:
        db.close()


def profile_to_me_response(profile: WebAccountProfile) -> dict[str, Any]:
    role = profile.role
    return {
        "user_id": profile.firebase_uid,
        "role": role,
        "roles": [role],
        "permissions": ROLE_PERMISSIONS.get(role, ROLE_PERMISSIONS["companion"]),
        "default_mode": profile.default_mode,
        "consent_given": profile.consent_accepted_at is not None,
        "preferences": {
            "recognition_language": profile.recognition_language,
            "talk_mode": profile.talk_mode,
            "speech_speed": profile.speech_speed,
            "voice_name": profile.voice_name,
            "auto_speak": profile.auto_speak,
            "transcript_visible": profile.transcript_visible,
            "auto_send": profile.auto_send,
        },
    }


class PreferenceValidationError(ValueError):
    """A preference value is malformed — maps to 422 (bad input)."""


class PreferencePermissionError(ValueError):
    """The value is well-formed but this account's role isn't allowed to set it — maps to 403."""


def update_preferences(firebase_uid: str, updates: dict[str, Any]) -> WebAccountProfile:
    """Apply a partial preferences update. Never touches `role`.

    `updates` may come straight from a request body — only the known
    preference fields are read from it, and default_mode is validated
    against the account's current role so this can never be used to land
    on a mode the role doesn't permit (the actual privilege check still
    happens per-request server-side regardless; this just keeps the stored
    default honest).
    """
    db = SessionLocal()
    try:
        profile = db.query(WebAccountProfile).filter(WebAccountProfile.firebase_uid == firebase_uid).first()
        if profile is None:
            raise PreferenceValidationError("no profile found for this account")

        if "default_mode" in updates:
            requested_mode = str(updates["default_mode"])
            allowed = ROLE_ALLOWED_MODES.get(profile.role, ["companion"])
            if requested_mode not in MODE_LABELS_KNOWN:
                raise PreferenceValidationError(f"default_mode {requested_mode!r} is not a recognized mode")
            if requested_mode not in allowed:
                raise PreferencePermissionError(
                    f"role {profile.role!r} is not permitted to use default_mode {requested_mode!r}"
                )
            profile.default_mode = requested_mode

        if "recognition_language" in updates:
            profile.recognition_language = str(updates["recognition_language"])
        if "talk_mode" in updates:
            talk_mode = str(updates["talk_mode"])
            if talk_mode not in ("tap", "hold"):
                raise PreferenceValidationError("talk_mode must be 'tap' or 'hold'")
            profile.talk_mode = talk_mode
        if "speech_speed" in updates:
            speed = float(updates["speech_speed"])
            if not (0.5 <= speed <= 2.0):
                raise PreferenceValidationError("speech_speed must be between 0.5 and 2.0")
            profile.speech_speed = speed
        if "voice_name" in updates:
            profile.voice_name = str(updates["voice_name"]) if updates["voice_name"] else None
        if "auto_speak" in updates:
            profile.auto_speak = bool(updates["auto_speak"])
        if "transcript_visible" in updates:
            profile.transcript_visible = bool(updates["transcript_visible"])
        if "auto_send" in updates:
            profile.auto_send = bool(updates["auto_send"])

        db.commit()
        db.refresh(profile)
        return profile
    finally:
        db.close()
