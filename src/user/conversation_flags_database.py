from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Deliberately its own database, separate from reminders/patients and from
# the web accounts DB: this table exists purely so a caregiver can see
# *that* something worth attention came up recently, without either of
# those systems (or anything else) needing to know this exists. Keyed by
# sender_id (Telegram chat id or Firebase uid) so it works the same for
# either channel — see src/user/conversation_flags.py for what writes here.
DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "conversation_flags.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


class ConversationFlag(Base):
    """A single flagged moment from a conversation.

    Intentionally holds no raw message text — only a short, LLM- or
    rule-generated reason. This is the whole privacy design of this
    feature: a caregiver sees that and why something was flagged, never a
    transcript of what was actually said.
    """

    __tablename__ = "conversation_flags"
    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(String, index=True, nullable=False)
    flag_type = Column(String, nullable=False)  # "safety" | "cognitive_decline"
    reason = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


Base.metadata.create_all(bind=engine)
