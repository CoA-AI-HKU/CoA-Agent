from __future__ import annotations

import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "private" / "screening_outbox.jsonl"


def queue_screening_message(sender_id: str, user_id: str, message: str) -> dict[str, Any]:
    item = {
        "delivery_id": secrets.token_urlsafe(12),
        "recipient_sender_id": str(sender_id),
        "user_id": str(user_id),
        "message": str(message),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "delivered": False,
    }
    path = Path(os.getenv("SCREENING_OUTBOX_PATH", str(DEFAULT_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def mark_screening_message_delivered(delivery_id: str) -> None:
    path = Path(os.getenv("SCREENING_OUTBOX_PATH", str(DEFAULT_PATH)))
    if not path.exists() or not delivery_id:
        return
    retained: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            retained.append(line)
            continue
        if isinstance(item, dict) and item.get("delivery_id") == delivery_id:
            item["delivered"] = True
            item["delivered_at"] = datetime.now(timezone.utc).isoformat()
        retained.append(json.dumps(item, ensure_ascii=False))
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text("\n".join(retained) + ("\n" if retained else ""), encoding="utf-8")
    temporary.replace(path)
