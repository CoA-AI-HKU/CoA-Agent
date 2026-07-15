from __future__ import annotations

import json
import os
import secrets
import string
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "data" / "private" / "user_registry.json"


def normalize_sender_id(sender_id: str | None) -> str:
    normalized = str(sender_id or "").strip()
    if normalized.startswith("+"):
        normalized = normalized[1:]
    suffix = "@s.whatsapp.net"
    if normalized.lower().endswith(suffix):
        normalized = normalized[: -len(suffix)]
    return normalized.strip()


def _registry_path() -> Path:
    return Path(os.getenv("USER_REGISTRY_PATH") or DEFAULT_REGISTRY_PATH)


def save_user_registry(registry: dict[str, Any]) -> None:
    path = _registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def register_account(sender_id: str, role: str, display_name: str = "") -> dict[str, Any]:
    normalized = normalize_sender_id(sender_id)
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in {"user", "caregiver"}:
        raise ValueError("role must be user or caregiver")
    registry = load_user_registry()
    users = registry.setdefault("users", {})
    existing = users.get(normalized, {}) if isinstance(users.get(normalized), dict) else {}
    record = dict(existing)
    record["role"] = normalized_role
    if display_name.strip():
        record["display_name"] = display_name.strip()[:80]
    if normalized_role == "user":
        record["user_id"] = str(record.get("user_id") or f"patient_{secrets.token_hex(6)}")
        record.pop("linked_user_id", None)
        record.pop("linked_user_ids", None)
    users[normalized] = record
    save_user_registry(registry)
    return record


def create_pairing_code(sender_id: str, lifetime_minutes: int = 15) -> str:
    record = get_user_record(sender_id)
    if str(record.get("role") or "").lower() != "user":
        raise ValueError("only a registered patient can create a pairing code")
    alphabet = string.ascii_uppercase.replace("I", "").replace("O", "") + "23456789"
    registry = load_user_registry()
    codes = registry.setdefault("pairing_codes", {})
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    codes[code] = {
        "user_id": str(record.get("user_id") or normalize_sender_id(sender_id)),
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=lifetime_minutes)).isoformat(),
    }
    save_user_registry(registry)
    return code


def redeem_pairing_code(sender_id: str, code: str, *, replace_existing: bool = False) -> str:
    caregiver_id = normalize_sender_id(sender_id)
    record = get_user_record(caregiver_id)
    if str(record.get("role") or "").lower() != "caregiver":
        raise ValueError("register as a caregiver before linking")
    normalized_code = str(code or "").strip().upper()
    registry = load_user_registry()
    codes = registry.get("pairing_codes", {})
    entry = codes.get(normalized_code) if isinstance(codes, dict) else None
    if not isinstance(entry, dict):
        raise ValueError("invalid or expired pairing code")
    try:
        expires_at = datetime.fromisoformat(str(entry.get("expires_at") or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid or expired pairing code") from exc
    if expires_at.astimezone(timezone.utc) < datetime.now(timezone.utc):
        codes.pop(normalized_code, None)
        save_user_registry(registry)
        raise ValueError("invalid or expired pairing code")
    user_id = str(entry.get("user_id") or "").strip()
    users = registry.setdefault("users", {})
    caregiver = dict(users.get(caregiver_id) or {})
    linked = [] if replace_existing else (caregiver.get("linked_user_ids") or caregiver.get("linked_user_id") or [])
    linked_ids = list(linked) if isinstance(linked, list) else [linked]
    if user_id and user_id not in linked_ids:
        linked_ids.append(user_id)
    caregiver["linked_user_ids"] = [value for value in linked_ids if value]
    caregiver["linked_user_id"] = caregiver["linked_user_ids"][0]
    users[caregiver_id] = caregiver
    codes.pop(normalized_code, None)
    save_user_registry(registry)
    return user_id


def unlink_caregiver(sender_id: str, user_id: str | None = None) -> int:
    caregiver_id = normalize_sender_id(sender_id)
    registry = load_user_registry()
    users = registry.get("users", {})
    record = dict(users.get(caregiver_id) or {}) if isinstance(users, dict) else {}
    if str(record.get("role") or "").lower() != "caregiver":
        raise ValueError("only a registered caregiver can unlink a patient")
    existing = record.get("linked_user_ids") or record.get("linked_user_id") or []
    linked_ids = list(existing) if isinstance(existing, list) else [existing]
    target = str(user_id or "").strip()
    retained = [value for value in linked_ids if value and target and str(value) != target]
    removed = len([value for value in linked_ids if value]) - len(retained)
    record["linked_user_ids"] = retained
    if retained:
        record["linked_user_id"] = retained[0]
    else:
        record.pop("linked_user_id", None)
    users[caregiver_id] = record
    save_user_registry(registry)
    return removed


def revoke_caregivers_for_user(sender_id: str) -> int:
    patient = get_user_record(sender_id)
    if str(patient.get("role") or "").lower() != "user":
        raise ValueError("only a registered patient can revoke caregiver access")
    user_id = str(patient.get("user_id") or normalize_sender_id(sender_id))
    registry = load_user_registry()
    users = registry.get("users", {})
    changed = 0
    for caregiver_id, raw_record in list(users.items()):
        if not isinstance(raw_record, dict) or str(raw_record.get("role") or "").lower() != "caregiver":
            continue
        existing = raw_record.get("linked_user_ids") or raw_record.get("linked_user_id") or []
        linked_ids = list(existing) if isinstance(existing, list) else [existing]
        if user_id not in linked_ids:
            continue
        retained = [value for value in linked_ids if value != user_id]
        updated = dict(raw_record)
        updated["linked_user_ids"] = retained
        if retained:
            updated["linked_user_id"] = retained[0]
        else:
            updated.pop("linked_user_id", None)
        users[caregiver_id] = updated
        changed += 1
    save_user_registry(registry)
    return changed


def create_dashboard_access_token(sender_id: str, lifetime_minutes: int = 30) -> str:
    caregiver_id = normalize_sender_id(sender_id)
    record = get_user_record(caregiver_id)
    if str(record.get("role") or "").lower() != "caregiver":
        raise ValueError("only a registered caregiver can open the caregiver dashboard")
    if not get_linked_user_ids(caregiver_id):
        raise ValueError("pair with a patient before opening the caregiver dashboard")
    token = secrets.token_urlsafe(24)
    registry = load_user_registry()
    tokens = registry.setdefault("dashboard_tokens", {})
    tokens[token] = {
        "caregiver_sender_id": caregiver_id,
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=lifetime_minutes)).isoformat(),
    }
    save_user_registry(registry)
    return token


def get_dashboard_patient_accounts(access_token: str) -> list[dict[str, str]]:
    token = str(access_token or "").strip()
    registry = load_user_registry()
    tokens = registry.get("dashboard_tokens", {})
    entry = tokens.get(token) if isinstance(tokens, dict) else None
    if not isinstance(entry, dict):
        return []
    try:
        expires_at = datetime.fromisoformat(str(entry.get("expires_at") or "").replace("Z", "+00:00"))
    except ValueError:
        return []
    if expires_at.astimezone(timezone.utc) < datetime.now(timezone.utc):
        tokens.pop(token, None)
        save_user_registry(registry)
        return []
    caregiver_id = str(entry.get("caregiver_sender_id") or "")
    allowed = set(get_linked_user_ids(caregiver_id))
    return [account for account in get_registered_patient_accounts() if account["user_id"] in allowed]


def load_user_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def get_user_record(sender_id: str) -> dict[str, Any]:
    return get_sender_record(sender_id)


def get_sender_record(sender_id: str) -> dict[str, Any]:
    registry = load_user_registry()
    users = registry.get("users", {})
    if not isinstance(users, dict):
        return {}
    record = users.get(normalize_sender_id(sender_id), {})
    return record if isinstance(record, dict) else {}


def iter_sender_records() -> list[tuple[str, dict[str, Any]]]:
    registry = load_user_registry()
    users = registry.get("users", {})
    if not isinstance(users, dict):
        return []
    records: list[tuple[str, dict[str, Any]]] = []
    for sender_id, record in users.items():
        if isinstance(record, dict):
            records.append((normalize_sender_id(sender_id), record))
    return records


def get_user_role(sender_id: str) -> str:
    role = str(get_user_record(sender_id).get("role") or "unknown").strip().lower()
    return role if role in {"caregiver", "user"} else "unknown"


def get_linked_user_id(sender_id: str) -> str | None:
    linked_user_ids = get_linked_user_ids(sender_id)
    return linked_user_ids[0] if linked_user_ids else None


def get_linked_user_ids(sender_id: str) -> list[str]:
    record = get_user_record(sender_id)
    linked = record.get("linked_user_ids")
    if linked is None:
        linked = record.get("linked_user_id")
    if linked is None:
        return []
    values = linked if isinstance(linked, list) else [linked]
    linked_ids: list[str] = []
    for value in values:
        linked_id = str(value or "").strip()
        if linked_id and linked_id not in linked_ids:
            linked_ids.append(linked_id)
    return linked_ids


def get_display_name(sender_id: str) -> str | None:
    display_name = get_user_record(sender_id).get("display_name")
    return str(display_name).strip() if display_name else None


def get_registry_user_id(sender_id: str) -> str | None:
    user_id = get_user_record(sender_id).get("user_id")
    return str(user_id).strip() if user_id else None


def get_user_record_by_user_id(user_id: str | None) -> tuple[str | None, dict[str, Any]]:
    target_user_id = str(user_id or "").strip()
    if not target_user_id:
        return None, {}
    for sender_id, record in iter_sender_records():
        if str(record.get("role") or "").strip().lower() != "user":
            continue
        if str(record.get("user_id") or "").strip() == target_user_id:
            return sender_id, record
    return None, {}


def get_registered_patient_accounts() -> list[dict[str, str]]:
    """Return registered patient accounts suitable for dashboard selection."""
    accounts_by_user_id: dict[str, dict[str, str]] = {}
    for sender_id, record in iter_sender_records():
        if str(record.get("role") or "").strip().lower() != "user":
            continue
        user_id = str(record.get("user_id") or sender_id).strip()
        if not user_id:
            continue
        display_name = str(record.get("display_name") or user_id).strip() or user_id
        accounts_by_user_id[user_id] = {
            "user_id": user_id,
            "display_name": display_name,
        }
    return sorted(
        accounts_by_user_id.values(),
        key=lambda account: (account["display_name"].casefold(), account["user_id"].casefold()),
    )


def get_caregiver_records_for_user(user_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    target_user_id = str(user_id or "").strip()
    if not target_user_id:
        return []
    caregivers: list[tuple[str, dict[str, Any]]] = []
    for sender_id, record in iter_sender_records():
        if str(record.get("role") or "").strip().lower() != "caregiver":
            continue
        if target_user_id in get_linked_user_ids(sender_id):
            caregivers.append((sender_id, record))
    return caregivers
