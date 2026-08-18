from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Separate database file from coa_agent.db (reminders/patients) — web
# contacts/profiles are keyed by Firebase's identity, a distinct system from
# the chat-platform identity (sender_id) reminders and the rest of the
# message router use. Anchored to an absolute path for the same reason
# src/reminders/database.py is: the process's CWD isn't guaranteed to match
# across launchers (systemd unit vs. local `uvicorn` invocation).
DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "web_accounts.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class WebContact(Base):
    __tablename__ = "web_contacts"
    id = Column(Integer, primary_key=True, index=True)
    # Firebase's stable per-user ID (the `uid` claim in a verified ID
    # token) — not a foreign key to a local accounts table. Firebase itself
    # is the sole identity authority; there is no local accounts/auth table,
    # deliberately, so there is only one place identity is issued.
    firebase_uid = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    detail = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class WebAccountProfile(Base):
    """Role and interface preferences for a Firebase account.

    Unlike WebContact's relationship to identity, this table does not
    compete with Firebase for "who is this" — Firebase remains the sole
    identity authority (see WebContact's comment above). This table only
    holds application data Firebase has no concept of: which mode/tools an
    account is allowed to use, and its saved interface preferences. `role`
    is never client-writable (see backend/api/web_account.py) — only
    server-side bootstrap logic or (in the future) an admin action may
    change it, precisely so a signed-in account can never grant itself
    elevated access by calling the preferences endpoint.
    """

    __tablename__ = "web_account_profiles"
    id = Column(Integer, primary_key=True, index=True)
    firebase_uid = Column(String, unique=True, index=True, nullable=False)
    role = Column(String, nullable=False, default="companion")
    default_mode = Column(String, nullable=False, default="companion")
    recognition_language = Column(String, nullable=False, default="zh-HK")
    talk_mode = Column(String, nullable=False, default="tap")  # "tap" or "hold"
    speech_speed = Column(Float, nullable=False, default=0.9)
    voice_name = Column(String, nullable=True)
    auto_speak = Column(Boolean, nullable=False, default=True)
    transcript_visible = Column(Boolean, nullable=False, default=True)
    high_contrast_mode = Column(Boolean, nullable=False, default=False)
    # False = "review before send" — reply is transcribed but held for the
    # user (or, in practice, mainly the developer role) to check before it's
    # actually sent to the chat pipeline.
    auto_send = Column(Boolean, nullable=False, default=True)
    # Patient-owned destination for optional "返屋企" navigation.
    home_address = Column(String, nullable=True)
    # NULL = has not agreed to the consent form yet. Set once, the first
    # time an account agrees (see backend/api/web_account.py's
    # POST /api/me/consent) — never cleared automatically, so an already-
    # registered account is never asked again.
    consent_accepted_at = Column(DateTime, nullable=True)
    # False until the account explicitly picks "companion" or "caregiver"
    # for itself (see POST /api/me/identity) — a brand-new row's `role`
    # column above is only a storage placeholder ("companion") until then,
    # not a real decision; the frontend gates entry on this flag instead of
    # trusting that placeholder. Bootstrap-elevated accounts (developer/
    # admin/caregiver via env var — see account_profiles.py) are considered
    # already decided and get this set True immediately, since the server
    # already made that call for them.
    identity_confirmed = Column(Boolean, nullable=False, default=False)
    # NULL until the account fills in the profile-info screen (see
    # POST /api/me/profile-info) — a self-reported name/birthday, distinct
    # from Firebase's own `display_name` (often empty for phone sign-ins).
    # This is what a caregiver actually sees identifying a linked patient.
    name = Column(String, nullable=True)
    birthday = Column(String, nullable=True)  # "YYYY-MM-DD"; free text, not validated as a real date
    # Mirrored from the verified Firebase ID token on every /api/me load
    # (see get_or_create_profile) purely so it can be shown to a linked
    # caregiver without a live Firebase Admin lookup per request — Firebase
    # itself remains the actual identity/auth authority.
    email = Column(String, nullable=True)
    # Collected alongside name/birthday on the profile-info screen — a
    # single, always-first-priority contact for Companion Mode's "call
    # caregiver"/emergency button (see handleCallCaregiver() in
    # web/index.html), distinct from the general contact list a caregiver
    # manages (which a patient can also read — see
    # _readable_contact_owner_ids in backend/api/web_account.py).
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


Base.metadata.create_all(bind=engine)


def _migrate_add_missing_columns() -> None:
    """Add columns introduced after a deployed web_accounts.db already exists.

    Base.metadata.create_all only creates missing TABLES, not missing
    COLUMNS on tables that already exist — mirrors src/reminders/database.py's
    own migration helper for the same reason.
    """
    with engine.connect() as connection:
        existing_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(web_account_profiles)")
        }
        additions = {
            "role": "VARCHAR NOT NULL DEFAULT 'companion'",
            "default_mode": "VARCHAR NOT NULL DEFAULT 'companion'",
            "recognition_language": "VARCHAR NOT NULL DEFAULT 'zh-HK'",
            "talk_mode": "VARCHAR NOT NULL DEFAULT 'tap'",
            "speech_speed": "FLOAT NOT NULL DEFAULT 0.9",
            "voice_name": "VARCHAR",
            "auto_speak": "BOOLEAN NOT NULL DEFAULT 1",
            "transcript_visible": "BOOLEAN NOT NULL DEFAULT 1",
            "high_contrast_mode": "BOOLEAN NOT NULL DEFAULT 0",
            "auto_send": "BOOLEAN NOT NULL DEFAULT 1",
            "home_address": "VARCHAR",
            "consent_accepted_at": "DATETIME",
            "identity_confirmed": "BOOLEAN NOT NULL DEFAULT 0",
            "name": "VARCHAR",
            "birthday": "VARCHAR",
            "email": "VARCHAR",
            "emergency_contact_name": "VARCHAR",
            "emergency_contact_phone": "VARCHAR",
        }
        for column, ddl_type in additions.items():
            if column not in existing_columns:
                connection.exec_driver_sql(f"ALTER TABLE web_account_profiles ADD COLUMN {column} {ddl_type}")
                connection.commit()


_migrate_add_missing_columns()
