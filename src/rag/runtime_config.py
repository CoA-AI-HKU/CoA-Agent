from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / "private" / "chroma" / "ling_rag"
DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
logger = logging.getLogger(__name__)


def _bool(value: object, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _path(value: object, default: Path) -> Path:
    path = Path(str(value or default)).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


def load_rag_config(
    mode: str = "shared",
    overrides: Mapping[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    values = dict(overrides or {})
    env = environ if environ is not None else os.environ
    rag_env = str(values.get("rag_env") or env.get("RAG_ENV") or "development").lower()
    provider = str(values.get("embedder_provider") or env.get("EMBEDDER_PROVIDER") or "local").lower()
    model = str(values.get("embedder_model") or env.get("EMBEDDER_MODEL") or DEFAULT_EMBEDDING_MODEL)
    allow_dummy = provider == "dummy" or _bool(values.get("allow_dummy", env.get("RAG_ALLOW_DUMMY")))
    allow_extractive = _bool(
        values.get("allow_extractive_fallback", env.get("RAG_ALLOW_EXTRACTIVE_FALLBACK")),
        default=False,
    )
    requested_llm_provider = str(values.get("llm_provider") or env.get("LLM_PROVIDER") or "").strip().lower()
    if not requested_llm_provider:
        if values.get("deepseek_key") or env.get("DEEPSEEK_API_KEY"):
            requested_llm_provider = "deepseek"
        else:
            requested_llm_provider = "openrouter" if env.get("OPENROUTER_API_KEY") else "extractive"
    if requested_llm_provider == "deepseek":
        llm_api_key = values.get("llm_api_key") or values.get("deepseek_key") or env.get("DEEPSEEK_API_KEY") or env.get("LLM_API_KEY")
        llm_model = str(values.get("llm_model") or values.get("deepseek_model") or env.get("DEEPSEEK_MODEL") or env.get("LLM_MODEL") or "deepseek-chat")
        llm_base_url = str(values.get("llm_base_url") or values.get("deepseek_base_url") or values.get("deepseek_url") or env.get("DEEPSEEK_BASE_URL") or env.get("DEEPSEEK_URL") or env.get("LLM_BASE_URL") or DEFAULT_DEEPSEEK_BASE_URL)
        if not llm_api_key:
            raise RuntimeError("LLM_PROVIDER=deepseek requires DEEPSEEK_API_KEY or LLM_API_KEY.")
    elif requested_llm_provider == "openrouter":
        llm_api_key = values.get("llm_api_key") or values.get("openrouter_key") or env.get("LLM_API_KEY") or env.get("OPENROUTER_API_KEY")
        llm_model = str(values.get("llm_model") or values.get("openrouter_model") or env.get("LLM_MODEL") or env.get("OPENROUTER_MODEL") or "")
        llm_base_url = str(values.get("llm_base_url") or values.get("openrouter_base_url") or env.get("LLM_BASE_URL") or env.get("OPENROUTER_BASE_URL") or DEFAULT_OPENROUTER_BASE_URL)
        if not llm_api_key or not llm_model:
            raise RuntimeError("LLM_PROVIDER=openrouter requires an API key and model.")
    elif requested_llm_provider == "extractive":
        llm_api_key, llm_model, llm_base_url = None, "extractive-fallback", ""
    else:
        raise RuntimeError(f"Unsupported LLM_PROVIDER={requested_llm_provider!r}.")
    llm_provider = requested_llm_provider

    if rag_env == "production" and provider == "dummy":
        raise RuntimeError(
            "RAG_ENV=production requires a real embedding backend; EMBEDDER_PROVIDER=dummy is not allowed."
        )
    if rag_env == "production" and llm_provider == "extractive":
        raise RuntimeError(
            "RAG_ENV=production requires a configured LLM; extractive fallback is not allowed."
        )

    config = {
        "config_source": "overrides+environment+canonical-defaults",
        "repository_root": PROJECT_ROOT,
        "rag_env": rag_env,
        "cwd": str(Path.cwd()),
        "docs_dir": _path(values.get("docs_dir") or env.get("RAG_DATA_DIR"), PROJECT_ROOT / "data" / "mds"),
        "chroma_dir": _path(values.get("chroma_dir") or env.get("CHROMA_DIR"), DEFAULT_CHROMA_DIR),
        "collection_name": values.get("collection_name") or env.get("CHROMA_COLLECTION") or "ling_rag",
        "embedder_provider": provider,
        "embedder_model": model,
        "embedding_model": model,
        "allow_dummy": allow_dummy,
        "allow_extractive_fallback": allow_extractive,
        "offline_embeddings": _bool(values.get("offline_embeddings", env.get("EMBEDDINGS_OFFLINE"))),
        "mode": values.get("mode") or mode,
        "answer_language": values.get("answer_language") or env.get("RAG_ANSWER_LANGUAGE") or "auto",
        "force_reindex": _bool(values.get("force_reindex")),
        "auto_index": _bool(values.get("auto_index", env.get("RAG_AUTO_INDEX")), True),
        "retrieve_top_k": int(values.get("retrieve_top_k") or env.get("RAG_RETRIEVE_TOP_K") or 8),
        "answer_top_k": int(values.get("answer_top_k") or env.get("RAG_ANSWER_TOP_K") or 2),
        "min_relevance_score": float(values.get("min_relevance_score") or env.get("RAG_MIN_RELEVANCE_SCORE") or 0.35),
        "min_shared_query_terms": int(values.get("min_shared_query_terms") or env.get("RAG_MIN_SHARED_QUERY_TERMS") or 1),
        "chunk_size": int(values.get("chunk_size") or env.get("RAG_CHUNK_SIZE") or 1200),
        "chunk_overlap": int(values.get("chunk_overlap") or env.get("RAG_CHUNK_OVERLAP") or 160),
        "max_context_chars": int(values.get("max_context_chars") or env.get("RAG_MAX_CONTEXT_CHARS") or 1800),
        "per_chunk_chars": int(values.get("per_chunk_chars") or env.get("RAG_PER_CHUNK_CHARS") or 500),
        "llm_api_key": llm_api_key,
        "llm_base_url": llm_base_url,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }
    # Preserve orchestration-only settings without teaching every caller a new loader.
    for key in ("force_retrieval", "planner_route", "sender_id"):
        if key in values:
            config[key] = values[key]
    return config


def public_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: str(config[key]) if isinstance(config[key], Path) else config[key]
        for key in (
            "config_source", "repository_root", "docs_dir", "chroma_dir", "collection_name",
            "embedder_provider", "embedder_model", "llm_provider", "llm_model", "llm_base_url",
            "allow_dummy", "allow_extractive_fallback", "rag_env",
        )
    }


def log_resolved_config(config: Mapping[str, Any], prefix: str = "RAG_CONFIG") -> None:
    logger.info(
        "%s llm_provider=%s llm_model=%s embedder_provider=%s embedding_model=%s llm_base_url=%s",
        prefix, config["llm_provider"], config["llm_model"], config["embedder_provider"],
        config["embedding_model"], config["llm_base_url"],
    )
