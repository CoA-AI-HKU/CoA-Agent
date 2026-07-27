from __future__ import annotations

import pytest

from src.pipeline.rag_agent import answer_question, create_chat_answer
from src.rag.runtime_config import load_rag_config


DEEPSEEK_ENV = {
    "LLM_PROVIDER": "deepseek",
    "DEEPSEEK_API_KEY": "deepseek-secret",
    "DEEPSEEK_MODEL": "deepseek-chat",
    "EMBEDDER_PROVIDER": "local",
    "EMBEDDER_MODEL": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
}


class _Response:
    status_code = 200
    text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return {"choices": [{"message": {"content": "answer"}}]}


def test_deepseek_uses_openai_compatible_url_and_bearer_key(monkeypatch) -> None:
    captured = {}

    def fake_post(url, **kwargs):
        captured.update(url=url, **kwargs)
        return _Response()

    monkeypatch.setattr("requests.post", fake_post)
    answer = create_chat_answer(load_rag_config(environ=DEEPSEEK_ENV))

    assert answer is not None
    assert answer("hello") == "answer"
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer deepseek-secret"


def test_deepseek_generation_and_local_embeddings_are_independent() -> None:
    config = load_rag_config(environ=DEEPSEEK_ENV)

    assert config["llm_provider"] == "deepseek"
    assert config["llm_model"] == "deepseek-chat"
    assert config["embedder_provider"] == "local"
    assert config["embedding_model"].startswith("sentence-transformers/")
    assert "deepseek" not in config["embedding_model"].lower()

    result = answer_question("", config)
    assert result["debug"]["fallback_active"] is False


def test_mcp_main_enters_server_loop_after_successful_initialization(monkeypatch) -> None:
    import src.dementia_rag_mcp_server as server

    calls = []

    class FakeMcp:
        def run(self):
            calls.append("run")

    monkeypatch.setattr(server, "mcp", FakeMcp())
    monkeypatch.setattr(server, "diagnose_runtime", lambda validate_llm=False: {"status": "ok"})
    monkeypatch.setattr(server, "load_rag_config", lambda mode: {"chroma_dir": "/tmp/chroma", "collection_name": "test"})
    monkeypatch.setattr("sys.argv", ["dementia-rag-mcp"])

    server.main()
    assert calls == ["run"]


def test_all_entrypoints_resolve_the_same_provider_configuration() -> None:
    configs = [load_rag_config(mode, environ=DEEPSEEK_ENV) for mode in ("cli", "mcp", "telegram", "web")]
    fields = ("llm_provider", "llm_model", "llm_base_url", "embedder_provider", "embedding_model")

    assert all(tuple(config[field] for field in fields) == tuple(configs[0][field] for field in fields) for config in configs)


def test_deepseek_missing_key_fails_clearly() -> None:
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        load_rag_config(environ={"LLM_PROVIDER": "deepseek"})


@pytest.mark.parametrize("embedder_provider", ["dummy"])
def test_production_never_uses_dummy(embedder_provider) -> None:
    with pytest.raises(RuntimeError, match="dummy is not allowed"):
        load_rag_config(
            overrides={"rag_env": "production", "embedder_provider": embedder_provider},
            environ=DEEPSEEK_ENV,
        )


def test_production_never_uses_extractive_fallback() -> None:
    with pytest.raises(RuntimeError, match="extractive fallback is not allowed"):
        load_rag_config(
            overrides={"rag_env": "production", "allow_extractive_fallback": True},
            environ={"EMBEDDER_PROVIDER": "local"},
        )
