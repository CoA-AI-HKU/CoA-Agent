from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlencode


_CURRENT_LOCATION_PATTERNS = (
    "我而家係邊", "我而家喺邊", "我現在在哪", "我現在在那", "我的位置",
    "current location", "where am i",
)
_NEARBY_MARKERS = ("最近", "附近", "nearest", "nearby", "closest")
_PLACE_CATEGORIES = {
    "醫院": "醫院", "医院": "醫院", "診所": "診所", "诊所": "診所",
    "巴士站": "巴士站", "地鐵站": "地鐵站", "地铁站": "地鐵站",
    "警署": "警署", "hospital": "hospital", "clinic": "clinic",
    "bus stop": "bus stop", "mtr": "MTR station",
}
_DESTINATION_PREFIXES = (
    "我想去", "我要去", "帶我去", "带我去", "點樣去", "怎样去", "怎麼去",
    "點去", "去到", "navigate to", "directions to", "take me to",
)
_DESTINATION_SUFFIX_RE = re.compile(
    r"(?:喺|係|在)?(?:邊度|哪里|哪裡|邊|哪)[？?。！!]*$|[？?。！!]+$"
)


def build_maps_action(message: str) -> tuple[str, dict[str, Any]]:
    """Return a Cantonese reply and a safe, identifier-free Google Maps action."""
    text = " ".join(str(message or "").strip().split())
    lowered = text.lower()

    if any(pattern in lowered for pattern in _CURRENT_LOCATION_PATTERNS):
        return (
            "我可以幫你喺 Google 地圖顯示目前位置。地圖會使用你部手機嘅定位；開啟前會先問你確認。",
            _action("current_location", "https://www.google.com/maps/@?api=1&map_action=map",
                    "開啟目前位置？", "Google 地圖可能會要求使用你部手機嘅位置。CoA-Agent唔會儲存你嘅位置。"),
        )

    category = next((value for key, value in _PLACE_CATEGORIES.items() if key in lowered), None)
    if category and any(marker in lowered for marker in _NEARBY_MARKERS):
        url = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": category})
        return (
            f"我可以幫你喺 Google 地圖搜尋附近嘅{category}。開啟前會先問你確認。",
            _action("nearby_search", url, f"搜尋附近嘅{category}？",
                    f"Google 地圖會使用你部手機嘅位置搜尋附近嘅{category}。CoA-Agent唔會儲存你嘅位置。"),
        )

    destination = _extract_destination(text)
    if destination:
        url = "https://www.google.com/maps/dir/?" + urlencode(
            {"api": "1", "destination": destination, "dir_action": "navigate"}
        )
        return (
            f"你係咪想去「{destination}」？確認後，我會幫你用 Google 地圖睇路線。",
            _action("directions", url, "確認目的地",
                    f"你係咪想開啟 Google 地圖，前往「{destination}」？Google可能會使用你部手機嘅位置。",
                    confirm_label="開始導航"),
        )

    query = category or "醫院"
    url = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": query})
    return (
        f"我可以幫你喺 Google 地圖搜尋{query}。開啟前會先問你確認。",
        _action("place_search", url, f"開啟 Google 地圖搜尋{query}？",
                "Google 地圖可能會使用你部手機嘅位置。CoA-Agent唔會儲存你嘅位置。"),
    )


def _extract_destination(message: str) -> str:
    lowered = message.lower()
    for prefix in _DESTINATION_PREFIXES:
        index = lowered.find(prefix)
        if index >= 0:
            candidate = message[index + len(prefix):].strip(" ，,：:")
            candidate = _DESTINATION_SUFFIX_RE.sub("", candidate).strip()
            if candidate:
                return candidate[:120]

    named_place = re.match(
        r"^(.{1,100}(?:醫院|医院|診所|诊所|站|公園|商場))(?:喺|係|在)?(?:邊度|哪里|哪裡|邊|哪)", message
    )
    if named_place:
        candidate = named_place.group(1).strip()
        if candidate not in _PLACE_CATEGORIES:
            return candidate
    return ""


def _action(kind: str, url: str, title: str, message: str, *, confirm_label: str = "開啟地圖") -> dict[str, Any]:
    return {"kind": kind, "url": url, "title": title, "message": message,
            "confirm_label": confirm_label, "external": True}
