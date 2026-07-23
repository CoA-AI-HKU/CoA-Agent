from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ClientMessage:
    user_id: str
    text: str


class ClientAdapter(ABC):
    @abstractmethod
    async def receive_message(self) -> ClientMessage:
        raise NotImplementedError

    @abstractmethod
    async def send_response(self, user_id: str, response: str) -> None:
        raise NotImplementedError
