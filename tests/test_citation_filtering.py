from __future__ import annotations

from src.agents.user_facing_formatter import format_user_facing_answer
from src.citations import (
    classify_source,
    clean_internal_citations_from_text,
    filter_user_facing_sources,
    finalize_user_facing_result,
)
from src.user.message_router import handle_incoming_message
from src.user.user_registry import register_account


def test_internal_markdown_citation_and_database_language_are_removed():
    answer = "根據資料庫資料：可以先保持規律生活。\n（來源：dementia-medications-358f15bdfa.md）"
    cleaned = clean_internal_citations_from_text(answer)
    assert "資料庫" not in cleaned
    assert "來源" not in cleaned
    assert ".md" not in cleaned
    assert "保持規律生活" in cleaned


def test_requested_parenthetical_markdown_variants_are_removed():
    answer = (
        "可先改善家中照明。（來源：caring-tips-fall-prevention-tips-5c91c2a4ac.md）\n"
        "(來源: second.md)\n"
        "（source: third.md）"
    )
    cleaned = clean_internal_citations_from_text(answer)
    assert cleaned == "可先改善家中照明"


def test_internal_paths_are_removed():
    answer = (
        "可先記下重要事項。\n"
        "/mnt/d/Documents/College/data/mds/private.md\n"
        "/home/user/.chroma/index\n"
        "file://server/private/source\n"
        "C:\\private\\source.txt"
    )
    cleaned = clean_internal_citations_from_text(answer)
    assert cleaned == "可先記下重要事項"


def test_external_url_is_classified_and_allowed():
    source = "https://www.alz.org/help-support/caregiving"
    assert classify_source(source) == "external"
    assert filter_user_facing_sources([source]) == [source]


def test_external_url_in_answer_is_preserved():
    answer = "詳情可參閱 https://www.alz.org 或 https://www.cdc.gov。"
    assert clean_internal_citations_from_text(answer) == answer


def test_mixed_sources_only_expose_external_source():
    internal = "dementia-medications.md"
    external = "https://www.cdc.gov/aging"
    assert filter_user_facing_sources([internal, external]) == [external]


def test_formatter_keeps_internal_metadata_but_hides_it_from_user():
    internal = {"source": "data/mds/home-safety.md", "type": "rag"}
    external = {"url": "https://www.chp.gov.hk/example", "source_type": "public_web", "title": "衞生防護中心"}
    result = format_user_facing_answer(
        {
            "answer": "根據資料庫，請保持通道暢通。\n來源：data/mds/home-safety.md",
            "sources": [internal, external],
            "answer_language": "zh-Hant",
        },
        show_sources=True,
    )
    assert result["sources"] == [internal, external]
    assert result["user_facing_sources"] == [external]
    assert result["debug"]["internal_sources"] == [internal]
    assert result["debug"]["external_sources"] == [external]
    assert result["internal_sources_hidden"] is True
    assert ".md" not in result["answer"]
    assert "資料庫" not in result["answer"]
    assert "衞生防護中心" in result["answer"]


def test_unknown_sources_hidden_by_default():
    assert classify_source("opaque-document-id") == "unknown"
    assert filter_user_facing_sources(["opaque-document-id"]) == []


def test_finalizer_keeps_internal_evidence_but_filters_public_fields():
    result = finalize_user_facing_result(
        {
            "answer": "安全建議。\n（來源：private.md）",
            "sources": ["private.md", "https://www.cdc.gov/aging"],
            "debug": {"retrieved_sources": ["private.md"]},
        }
    )
    assert result["answer"] == "安全建議"
    assert result["sources"] == ["private.md", "https://www.cdc.gov/aging"]
    assert result["debug"]["retrieved_sources"] == ["private.md"]
    assert result["user_facing_sources"] == ["https://www.cdc.gov/aging"]
    assert result["internal_sources_hidden"] is True


def test_patient_web_route_does_not_return_markdown_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(
        "src.user.message_router.handle_patient_user_message",
        lambda *args, **kwargs: {
            "answer": "可先保持通道暢通。（來源：patient-private.md）",
            "sources": ["patient-private.md"],
            "debug": {"retrieved_sources": ["patient-private.md"]},
        },
    )
    result = handle_incoming_message("如何防跌？", "web-patient", "web")
    assert ".md" not in result["answer"]
    assert result["sources"] == ["patient-private.md"]
    assert result["debug"]["retrieved_sources"] == ["patient-private.md"]


def test_caregiver_app_route_does_not_return_markdown_filename(tmp_path, monkeypatch):
    monkeypatch.setenv("USER_REGISTRY_PATH", str(tmp_path / "registry.json"))
    monkeypatch.setenv("EVENTS_LOG_PATH", str(tmp_path / "events.jsonl"))
    register_account("app-caregiver", "caregiver", "Carer")
    monkeypatch.setattr(
        "src.user.message_router.handle_caregiver_manager_message",
        lambda *args, **kwargs: {
            "answer": "請移走地上雜物。\n來源：caregiver-private.md",
            "sources": ["caregiver-private.md"],
            "debug": {"retrieved_sources": ["caregiver-private.md"]},
        },
    )
    result = handle_incoming_message("如何協助防跌？", "app-caregiver", "app")
    assert ".md" not in result["answer"]
    assert result["sources"] == ["caregiver-private.md"]
    assert result["debug"]["retrieved_sources"] == ["caregiver-private.md"]
