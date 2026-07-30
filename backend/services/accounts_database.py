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
    # False = "review before send" — reply is transcribed but held for the
    # user (or, in practice, mainly the developer role) to check before it's
    # actually sent to the chat pipeline.
    auto_send = Column(Boolean, nullable=False, default=True)
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
            "auto_send": "BOOLEAN NOT NULL DEFAULT 1",
        }
        for column, ddl_type in additions.items():
            if column not in existing_columns:
                connection.exec_driver_sql(f"ALTER TABLE web_account_profiles ADD COLUMN {column} {ddl_type}")
                connection.commit()


_migrate_add_missing_columns()
