from __future__ import annotations

import pytest

from src.pipeline.document import Document
from src.pipeline.embedder import Embedder
from src.pipeline.rag_agent import (
    RagAgent,
    get_runtime_agent,
    rebuild_runtime_index,
)
from src.pipeline.vector_store import InMemoryVectorStore
from src.rag.runtime_config import load_rag_config


def _config(tmp_path, **overrides):
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "definition.md").write_text(
        "# 腦退化症是什麼\n\n腦退化症是一組影響記憶、思考和日常生活能力的腦部疾病。",
        encoding="utf-8",
    )
    return load_rag_config(
        "test",
        {
            "docs_dir": docs,
            "chroma_dir": tmp_path / "chroma",
            "collection_name": "test_collection",
            "embedder_provider": "dummy",
            "embedder_model": "all-MiniLM-L6-v2",
            "allow_extractive_fallback": True,
            **overrides,
        },
        environ={},
    )


def test_production_rejects_dummy_embedding() -> None:
    with pytest.raises(RuntimeError, match="requires a real embedding backend"):
        load_rag_config(
            "mcp",
            {
                "rag_env": "production",
                "embedder_provider": "dummy",
                "allow_extractive_fallback": True,
            },
            environ={},
        )


def test_dummy_is_only_used_when_explicitly_requested(monkeypatch, tmp_path) -> None:
    config = _config(tmp_path)
    agent = get_runtime_agent(config)
    assert agent.embedder.resolved_provider == "dummy"

    auto_config = _config(
        tmp_path / "auto",
        embedder_provider="auto",
        allow_dummy=False,
        offline_embeddings=True,
    )
    monkeypatch.setattr(
        "src.pipeline.rag_agent.Embedder",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("backend unavailable")),
    )
    with pytest.raises(RuntimeError, match="Dummy fallback is disabled"):
        get_runtime_agent(auto_config)


def test_index_model_mismatch_is_detected(tmp_path) -> None:
    config = _config(tmp_path, force_reindex=True)
    get_runtime_agent(config)
    mismatched = {**config, "force_reindex": False, "embedder_provider": "local"}

    class FakeLocalEmbedder:
        resolved_provider = "local"
        dimension = 3

        def __init__(self, *args, **kwargs):
            pass

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("src.pipeline.rag_agent.Embedder", FakeLocalEmbedder)
        with pytest.raises(RuntimeError, match="does not match runtime configuration"):
            get_runtime_agent(mismatched)


def test_reload_rebuilds_with_configured_provider(tmp_path) -> None:
    result = rebuild_runtime_index(_config(tmp_path))

    assert result["chunk_count"] > 0
    assert result["manifest"]["embedder_provider"] == "dummy"
    assert result["manifest"]["embedder_model"] == "dummy"
    assert result["manifest"]["embedding_dimension"] == 384
    assert result["manifest"]["collection_name"] == "test_collection"
    assert result["manifest"]["docs_dir"].endswith("/docs")


def test_reload_replaces_dummy_collection_with_local_vectors(monkeypatch, tmp_path) -> None:
    dummy_config = _config(tmp_path, force_reindex=True)
    dummy_agent = get_runtime_agent(dummy_config)
    old_results = dummy_agent.retrieve("腦退化症", k=1)

    class FakeLocalEmbedder:
        resolved_provider = "local"
        dimension = 3

        def __init__(self, *args, **kwargs):
            pass

        def encode(self, texts):
            return [[1.0, float(len(text) % 7), 0.5] for text in texts]

        def encode_documents(self, documents):
            return self.encode([document.text for document in documents])

    monkeypatch.setattr("src.pipeline.rag_agent.Embedder", FakeLocalEmbedder)
    local_config = {
        **dummy_config, "embedder_provider": "local", "embedder_model": "fake-local",
        "force_reindex": False,
    }
    rebuilt = rebuild_runtime_index(local_config)
    new_agent = get_runtime_agent(local_config)
    new_results = new_agent.retrieve("腦退化症", k=1)

    assert rebuilt["manifest"]["embedder_provider"] == "local"
    assert rebuilt["manifest"]["embedder_model"] == "fake-local"
    assert rebuilt["manifest"]["embedding_dimension"] == 3
    assert old_results[0].metadata.get("distance") != new_results[0].metadata.get("distance")


def test_definition_query_prefers_definition_source() -> None:
    agent = RagAgent(
        embedder=Embedder(provider="dummy"),
        vector_store=InMemoryVectorStore(),
        min_relevance_score=0.0,
    )
    agent.index_documents(
        [
            Document(
                text=(
                    "腦退化症是一組影響記憶、思考和日常生活能力的腦部疾病，"
                    "不同病症的表現和進展可能有所不同。"
                ),
                metadata={"source": "what-is-dementia.md", "heading": "腦退化症是什麼"},
            ),
            Document(
                text="照顧者可以用平靜語氣溝通，並安排熟悉的日常活動。",
                metadata={"source": "caregiver-tips.md"},
            ),
        ]
    )

    result = agent.answer_question("腦退化症是什麼？")
    assert result["found"] is True
    assert result["sources"][0] == "what-is-dementia.md"


def test_cli_and_mcp_resolve_identical_storage_configuration() -> None:
    cli = load_rag_config("cli", environ={})
    mcp = load_rag_config("mcp", environ={})

    for key in ("repository_root", "docs_dir", "chroma_dir", "collection_name", "embedder_model"):
        assert cli[key] == mcp[key]
