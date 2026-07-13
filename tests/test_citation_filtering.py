from __future__ import annotations

from src.agents.user_facing_formatter import format_user_facing_answer
from src.citations import classify_source, clean_internal_citations_from_text, filter_user_facing_sources


def test_internal_markdown_citation_and_database_language_are_removed():
    answer = "根據資料庫資料：可以先保持規律生活。\n（來源：dementia-medications-358f15bdfa.md）"
    cleaned = clean_internal_citations_from_text(answer)
    assert "資料庫" not in cleaned
    assert "來源" not in cleaned
    assert ".md" not in cleaned
    assert "保持規律生活" in cleaned


def test_internal_paths_are_removed():
    answer = "可先記下重要事項。\n/mnt/d/Documents/College/data/mds/private.md\n/home/user/.chroma/index"
    cleaned = clean_internal_citations_from_text(answer)
    assert cleaned == "可先記下重要事項"


def test_external_url_is_classified_and_allowed():
    source = "https://www.alz.org/help-support/caregiving"
    assert classify_source(source) == "external"
    assert filter_user_facing_sources([source]) == [source]


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
