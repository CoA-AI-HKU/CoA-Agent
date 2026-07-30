from __future__ import annotations

import threading
import time
from collections import deque
from typing import NamedTuple

# In-process only, deliberately not a database table — this is "what did we
# just say a moment ago" continuity within one sitting, not a retained
# record (see src/user/conversation_flags.py for the separate, deliberately
# minimal record that IS persisted). A backend restart clearing this is
# acceptable: it just means the next message starts a fresh conversation,
# same as if the user had been quiet past the TTL below.
MAX_TURNS = 6
TTL_SECONDS = 30 * 60  # inactivity beyond this counts as a new conversation


class Turn(NamedTuple):
    user_message: str
    reply: str


_lock = threading.Lock()
_buffers: dict[str, deque[Turn]] = {}
_last_active: dict[str, float] = {}


def record_turn(sender_id: str, user_message: str, reply: str) -> None:
    sender_id = str(sender_id or "").strip()
    if not sender_id:
        return
    with _lock:
        buffer = _buffers.setdefault(sender_id, deque(maxlen=MAX_TURNS))
        buffer.append(Turn(user_message, reply))
        _last_active[sender_id] = time.time()


def get_recent_turns(sender_id: str) -> list[Turn]:
    """Return this sender's recent turns, or [] if the gap since the last one
    is long enough that this should be treated as a new conversation.
    """
    sender_id = str(sender_id or "").strip()
    if not sender_id:
        return []
    with _lock:
        last_active = _last_active.get(sender_id)
        if last_active is None or (time.time() - last_active) > TTL_SECONDS:
            _buffers.pop(sender_id, None)
            _last_active.pop(sender_id, None)
            return []
        return list(_buffers.get(sender_id, ()))


def clear(sender_id: str) -> None:
    """Explicitly end a conversation early (e.g. on sign-out)."""
    sender_id = str(sender_id or "").strip()
    with _lock:
        _buffers.pop(sender_id, None)
        _last_active.pop(sender_id, None)
