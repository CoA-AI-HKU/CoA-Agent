from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from src.user.message_router import handle_incoming_message

from .user_context import UserContextService


@dataclass(frozen=True)
class ConversationRequest:
    user_id: str
    message: str
    platform: str = "api"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConversationResponse:
    response: str
    tts: str | None
    events: list[dict[str, Any]]
    metadata: dict[str, Any]


class ConversationService:
    """The single client-independent entrypoint into the existing orchestrator."""

    def __init__(
        self,
        handler: Callable[..., dict[str, Any]] = handle_incoming_message,
        context_service: UserContextService | None = None,
    ) -> None:
        self._handler = handler
        self._contexts = context_service or UserContextService()

    def respond(self, request: ConversationRequest) -> ConversationResponse:
        sender_id = request.user_id.strip()
        message = request.message.strip()
        platform = request.platform.strip().lower() or "api"
        if not sender_id:
            raise ValueError("user_id is required")
        if not message:
            raise ValueError("message is required")

        # Loading is explicit at the application boundary even though the legacy
        # router also loads the same state while it is being incrementally split.
        context = self._contexts.load(sender_id)
        result = self._handler(
            message,
            sender_id,
            platform,
            str(request.metadata.get("telegram_username") or ""),
        )
        outbound = result.get("outbound_messages")
        events = list(outbound) if isinstance(outbound, list) else []
        answer = str(result.get("answer") or "").strip()
        return ConversationResponse(
            response=answer,
            tts=answer or None,
            events=events,
            metadata={
                "role": result.get("role", context.role),
                "user_id": result.get("user_id", context.user_id),
                "linked_user_id": result.get("linked_user_id"),
                "intent": result.get("intent"),
                "route": result.get("route"),
                "safety_level": result.get("safety_level"),
            },
        )


async def process_user_message(
    user_id: str,
    message: str,
    channel: str,
    session_id: str | None = None,
    *,
    timeout_seconds: float = 30.0,
    service: ConversationService | None = None,
) -> dict[str, str]:
    """Run a channel message through the shared agent pipeline.

    Only the small, user-safe contract returned here may cross the prototype
    web boundary. Agent metadata remains server-side.
    """
    conversation_service = service or ConversationService()
    result = await asyncio.wait_for(
        asyncio.to_thread(
            conversation_service.respond,
            ConversationRequest(user_id=user_id, message=message, platform=channel),
        ),
        timeout=timeout_seconds,
    )
    if not result.response:
        raise RuntimeError("agent returned an empty response")
    return {
        "reply": result.response,
        "language": "zh-HK",
        "session_id": session_id or uuid.uuid4().hex,
    }
