from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Separate database file from coa_agent.db (reminders/patients) — web
# contacts are keyed by Firebase's identity, a distinct system from the
# chat-platform identity (sender_id) reminders and the rest of the message
# router use. Anchored to an absolute path for the same reason
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
    # is the account system; there is no local accounts table to join
    # against, deliberately, so there is only one place identity is issued.
    firebase_uid = Column(String, index=True, nullable=False)
    name = Column(String, nullable=False)
    detail = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


Base.metadata.create_all(bind=engine)
