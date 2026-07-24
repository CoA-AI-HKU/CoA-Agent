from __future__ import annotations

import pytest

from src.orchestrator import handle_dementia_user_message
from src.rag.execution_metrics import retrieval_metrics_snapshot


@pytest.mark.parametrize(
    "message",
    [
        "你好",
        "你覺得數獨好玩嗎",
        "我最近覺得好累呀",
        "我最近成日唔記得嘢",
        "媽媽最近記性差咗好多",
        "腦退化症是什麼",
        "我唔記得食咗藥未",
    ],
)
def test_every_normal_message_has_an_arag_execution_trace(message: str) -> None:
    result = handle_dementia_user_message(message, user_id="arag-default-user")
    trace = result["debug"]["execution_trace"]

    assert trace["message_id"]
    assert trace["user_id"] == "arag-default-user"
    assert trace["detected_intent"]
    assert trace["selected_route"]
    assert trace["planner_decision"]
    assert trace["retrieval_enabled"] is True
    assert trace["retrieval_query"]
    assert isinstance(trace["retrieved_chunk_count"], int)
    assert isinstance(trace["top_similarity_scores"], list)
    assert isinstance(trace["selected_documents"], list)
    assert trace["generation_model"]
    assert trace["final_response"].strip()


def test_arag_metrics_record_default_retrieval() -> None:
    before = retrieval_metrics_snapshot()
    handle_dementia_user_message("你好", user_id="arag-metrics-user")
    after = retrieval_metrics_snapshot()

    assert after["total_messages"] == before["total_messages"] + 1
    assert after["retrieved_messages"] == before["retrieved_messages"] + 1
    assert after["skipped_retrieval"] == before["skipped_retrieval"]
