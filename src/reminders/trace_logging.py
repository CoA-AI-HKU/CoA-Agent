from __future__ import annotations

import getpass
import os
from pathlib import Path
from typing import Any
import logging


logger = logging.getLogger("reminder_trace")

# Deliberately re-derives the same anchor as database.py rather than
# importing it, so this module has zero SQLAlchemy dependency and stays
# importable (and able to log a "tool unavailable" checkpoint) even in a
# process where `src.reminders.database` itself fails to import.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
REMINDER_DATABASE_PATH = _PROJECT_ROOT / "coa_agent.db"
REMINDER_TIMEZONE_NAME = os.getenv("REMINDER_TIMEZONE", "Asia/Hong_Kong")

# Captured once at import time: these describe the process, not the
# request, so recomputing them per log call would be pure overhead.
_SERVICE_USER = getpass.getuser()
_WORKING_DIRECTORY = str(Path.cwd())


def log_reminder_checkpoint(event: str, **fields: Any) -> None:
    """Emit one structured checkpoint in the reminder request trace.

    Callers must only pass identifiers (user_id, reminder_id, channel,
    normalized times, booleans) in `fields` — never the raw message or
    reminder text, so reminder content never reaches logs.
    """
    logger.info(
        event,
        extra={
            "event": event,
            "service_user": _SERVICE_USER,
            "working_directory": _WORKING_DIRECTORY,
            "reminder_db_path": str(REMINDER_DATABASE_PATH),
            "application_timezone": REMINDER_TIMEZONE_NAME,
            **fields,
        },
    )


def check_reminder_db_write_access() -> dict[str, Any]:
    """Report whether this process can write the reminder DB, for startup diagnostics.

    Checks the DB file itself when it already exists (the common case after
    first run), otherwise falls back to the parent directory, since a
    missing file is created on first write.
    """
    target = REMINDER_DATABASE_PATH if REMINDER_DATABASE_PATH.exists() else REMINDER_DATABASE_PATH.parent
    return {
        "path_checked": str(target),
        "writable": os.access(target, os.W_OK),
    }
