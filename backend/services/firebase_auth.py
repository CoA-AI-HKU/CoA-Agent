from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_initialized = False
_init_error: str | None = None


@dataclass(frozen=True)
class FirebaseUser:
    uid: str
    phone_number: str | None
    display_name: str | None


def _ensure_initialized() -> bool:
    """Lazily initialize firebase-admin from a service account file.

    Never raises — a missing/misconfigured credential means "sign-in isn't
    available yet", not a startup crash, since the rest of the app (chat,
    reminders) must keep working without it. Checked, and only actually
    attempted, on first use rather than at import time, so importing this
    module in tests or before the credential exists is always safe.
    """
    global _initialized, _init_error
    if _initialized:
        return True
    if _init_error is not None:
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
    except ImportError as exc:
        _init_error = f"firebase-admin not installed: {exc}"
        logger.error(_init_error)
        return False

    # GOOGLE_APPLICATION_CREDENTIALS is the standard Google Cloud client
    # library convention; FIREBASE_SERVICE_ACCOUNT_PATH is accepted too so
    # this doesn't collide with some other Google Cloud credential the
    # deployment might already set that var for.
    credential_path = os.getenv("FIREBASE_SERVICE_ACCOUNT_PATH") or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if not credential_path:
        _init_error = "no FIREBASE_SERVICE_ACCOUNT_PATH or GOOGLE_APPLICATION_CREDENTIALS configured"
        logger.warning("Firebase sign-in not configured: %s", _init_error)
        return False
    try:
        cred = credentials.Certificate(credential_path)
        firebase_admin.initialize_app(cred)
    except Exception as exc:
        _init_error = f"failed to initialize firebase-admin: {exc}"
        logger.exception("Firebase initialization failed")
        return False
    _initialized = True
    return True


def is_configured() -> bool:
    return _ensure_initialized()


def verify_id_token(id_token: str) -> FirebaseUser | None:
    """Verify a client-supplied Firebase ID token; None if invalid/expired/unconfigured.

    This is the only place a request is allowed to claim a Firebase
    identity — verification happens against Google's public keys via
    firebase-admin, so a request cannot simply assert its own uid.
    """
    if not _ensure_initialized():
        return None
    from firebase_admin import auth as firebase_auth_sdk

    try:
        decoded = firebase_auth_sdk.verify_id_token(id_token)
    except Exception:
        logger.info("Firebase ID token verification failed", exc_info=True)
        return None
    uid = str(decoded.get("uid") or "")
    if not uid:
        return None
    return FirebaseUser(
        uid=uid,
        phone_number=decoded.get("phone_number"),
        display_name=decoded.get("name"),
    )
