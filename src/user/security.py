from __future__ import annotations

import os
import re


INJECTION_PATTERNS = (
    r"ignore (all |the )?(previous|prior|system|developer) (instructions|prompts?)",
    r"reveal (the )?(system|developer) prompt",
    r"bypass (the )?(safety|security|rules|instructions)",
    r"jailbreak",
    r"忽略.{0,12}(指示|指令|提示|規則|规则)",
    r"繞過.{0,8}(安全|限制|規則)",
    r"绕过.{0,8}(安全|限制|规则)",
)
DATA_MANIPULATION_PATTERNS = (
    r"(delete|erase|drop|overwrite|modify|change).{0,30}(database|registry|file|record|data|account)",
    r"(刪除|删除|清除|覆寫|覆盖|修改|更改).{0,20}(資料庫|数据库|檔案|文件|記錄|记录|資料|数据|帳戶|账户)",
)


def is_admin_sender(sender_id: str, telegram_username: str = "") -> bool:
    configured_ids = _values(os.getenv("ADMIN_TELEGRAM_SENDER_IDS", ""))
    configured_names = _values(os.getenv("ADMIN_TELEGRAM_USERNAMES", "ainezhang"))
    normalized_sender = str(sender_id or "").strip().lstrip("@").casefold()
    normalized_username = str(telegram_username or "").strip().lstrip("@").casefold()
    return normalized_sender in configured_ids or bool(normalized_username and normalized_username in configured_names)


def unsafe_control_request(message: str) -> bool:
    text = " ".join(str(message or "").strip().lower().split())
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in (*INJECTION_PATTERNS, *DATA_MANIPULATION_PATTERNS))


def _values(raw: str) -> set[str]:
    return {value.strip().lstrip("@").casefold() for value in raw.split(",") if value.strip()}
