from __future__ import annotations

import asyncio
import json
import os
from typing import Any
from urllib import parse, request

from clients.base import ClientAdapter, ClientMessage


class TelegramAdapter(ClientAdapter):
    """Long-polling adapter containing transport logic only."""

    def __init__(self, bot_token: str, backend_url: str, service_token: str) -> None:
        self.telegram_url = f"https://api.telegram.org/bot{bot_token}"
        self.backend_url = backend_url.rstrip("/")
        self.service_token = service_token
        self._offset = 0

    async def receive_message(self) -> ClientMessage:
        while True:
            updates = await asyncio.to_thread(self._telegram, "getUpdates", {"timeout": "25", "offset": str(self._offset)})
            for update in updates.get("result", []):
                self._offset = max(self._offset, int(update.get("update_id", 0)) + 1)
                message = update.get("message") or {}
                text = str(message.get("text") or "").strip()
                chat_id = str((message.get("chat") or {}).get("id") or "")
                if text and chat_id:
                    return ClientMessage(chat_id, text)

    async def send_response(self, user_id: str, response: str) -> None:
        await asyncio.to_thread(self._telegram, "sendMessage", {"chat_id": user_id, "text": response})

    async def run(self) -> None:
        while True:
            message = await self.receive_message()
            result = await asyncio.to_thread(self._chat, message)
            await self.send_response(message.user_id, str(result.get("response") or ""))

    def _chat(self, message: ClientMessage) -> dict[str, Any]:
        body = json.dumps({"user_id": message.user_id, "message": message.text, "platform": "telegram"}).encode()
        req = request.Request(f"{self.backend_url}/v1/chat", data=body, headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.service_token}"})
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read())

    def _telegram(self, method: str, values: dict[str, str]) -> dict[str, Any]:
        req = request.Request(f"{self.telegram_url}/{method}", data=parse.urlencode(values).encode())
        with request.urlopen(req, timeout=35) as response:
            return json.loads(response.read())


def main() -> None:
    adapter = TelegramAdapter(os.environ["TELEGRAM_BOT_TOKEN"], os.getenv("COA_BACKEND_URL", "http://127.0.0.1:8000"), os.environ["COA_SERVICE_TOKEN"])
    asyncio.run(adapter.run())


if __name__ == "__main__":
    main()
