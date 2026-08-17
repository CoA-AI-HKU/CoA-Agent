from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlparse

from backend.services.conversation import ConversationService, process_user_message
from src.intent_router import classify_intent
from src.location.maps import build_maps_action


def test_current_location_uses_key_free_map_url() -> None:
    reply, action = build_maps_action("我而家係邊度？")

    assert action["kind"] == "current_location"
    assert action["url"] == "https://www.google.com/maps/@?api=1&map_action=map"
    assert action["external"] is True
    assert "唔會儲存" in action["message"]
    assert "確認" in reply


def test_nearby_hospital_search_contains_no_patient_identifier() -> None:
    _, action = build_maps_action("最近嘅醫院係邊？")
    parsed = urlparse(action["url"])

    assert action["kind"] == "nearby_search"
    assert parsed.hostname == "www.google.com"
    assert parse_qs(parsed.query) == {"api": ["1"], "query": ["醫院"]}
    assert "user" not in parsed.query
    assert "patient" not in parsed.query


def test_named_destination_is_confirmed_and_encoded() -> None:
    reply, action = build_maps_action("我想去瑪麗醫院")
    query = parse_qs(urlparse(action["url"]).query)

    assert action["kind"] == "directions"
    assert query["destination"] == ["瑪麗醫院"]
    assert query["dir_action"] == ["navigate"]
    assert "瑪麗醫院" in reply
    assert action["confirm_label"] == "開始導航"


def test_recently_is_not_a_location_intent_without_a_place() -> None:
    assert classify_intent("我最近瞓得唔好").intent != "location_query"


def test_location_action_crosses_web_boundary_but_debug_does_not() -> None:
    class StubContexts:
        def load(self, sender_id):
            return type("Context", (), {"role": "user", "user_id": sender_id})()

    def handler(*_args):
        return {
            "answer": "請確認目的地。",
            "answer_language": "zh-HK",
            "route": "route_guide",
            "map_action": {
                "kind": "directions",
                "url": "https://www.google.com/maps/dir/?api=1&destination=test",
                "title": "確認目的地",
                "message": "要開啟地圖嗎？",
                "confirm_label": "開始導航",
                "external": True,
            },
            "debug": {"secret": "must-not-cross-boundary"},
        }

    result = asyncio.run(process_user_message(
        "web-user", "我想去瑪麗醫院", "web", "location-session",
        service=ConversationService(handler=handler, context_service=StubContexts()),
    ))

    assert result["map_action"]["kind"] == "directions"
    assert "debug" not in result
    assert "secret" not in str(result)
