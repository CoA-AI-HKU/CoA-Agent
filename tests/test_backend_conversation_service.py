from backend.services.conversation import ConversationRequest, ConversationService


class StubContexts:
    def load(self, sender_id):
        return type("Context", (), {"role": "user", "user_id": "patient-1"})()


def test_conversation_service_maps_generic_contract_without_transport_logic():
    calls = []

    def handler(message, sender_id, channel, telegram_username):
        calls.append((message, sender_id, channel, telegram_username))
        return {
            "answer": "A safe answer",
            "role": "user",
            "user_id": "patient-1",
            "intent": "knowledge_qa",
            "route": "rag",
            "outbound_messages": [{"recipient_sender_id": "caregiver"}],
        }

    service = ConversationService(handler=handler, context_service=StubContexts())
    result = service.respond(
        ConversationRequest("telegram-42", " Hello ", "Telegram", {"telegram_username": "mei"})
    )

    assert calls == [("Hello", "telegram-42", "telegram", "mei")]
    assert result.response == "A safe answer"
    assert result.tts == "A safe answer"
    assert result.events == [{"recipient_sender_id": "caregiver"}]
    assert result.metadata["user_id"] == "patient-1"


def test_conversation_service_rejects_empty_identity_and_message():
    service = ConversationService(handler=lambda *args: {}, context_service=StubContexts())
    for request in (
        ConversationRequest("", "hello"),
        ConversationRequest("user", "  "),
    ):
        try:
            service.respond(request)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid request was accepted")
