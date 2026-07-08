from __future__ import annotations

from src.pipeline.rag_agent import DEFAULT_CHROMA_DIR, PROJECT_ROOT, build_default_rag_config


def test_default_chroma_dir_uses_writable_cache_path(monkeypatch) -> None:
    monkeypatch.delenv("CHROMA_DIR", raising=False)

    config = build_default_rag_config("mcp")

    assert str(config["chroma_dir"]).replace("\\", "/") == DEFAULT_CHROMA_DIR


def test_chroma_dir_env_override_is_used(monkeypatch, tmp_path) -> None:
    chroma_dir = tmp_path / "chroma" / "ling_rag"
    monkeypatch.setenv("CHROMA_DIR", str(chroma_dir))

    config = build_default_rag_config("mcp")

    assert config["chroma_dir"] == chroma_dir


def test_relative_chroma_dir_still_resolves_under_project(monkeypatch) -> None:
    monkeypatch.setenv("CHROMA_DIR", ".chroma/ling_rag")

    config = build_default_rag_config("mcp")

    assert config["chroma_dir"] == PROJECT_ROOT / ".chroma/ling_rag"
