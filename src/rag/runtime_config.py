from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CHROMA_DIR = PROJECT_ROOT / "data" / "private" / "chroma" / "ling_rag"
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
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
    provider = str(values.get("embedder_provider") or env.get("EMBEDDER_PROVIDER") or "auto").lower()
    model = str(values.get("embedder_model") or env.get("EMBEDDER_MODEL") or DEFAULT_EMBEDDING_MODEL)
    allow_dummy = provider == "dummy" or _bool(values.get("allow_dummy", env.get("RAG_ALLOW_DUMMY")))
    allow_extractive = _bool(
        values.get("allow_extractive_fallback", env.get("RAG_ALLOW_EXTRACTIVE_FALLBACK")),
        default=rag_env != "production",
    )
    openrouter_key = values.get("openrouter_key") or env.get("OPENROUTER_API_KEY")
    openrouter_model = values.get("openrouter_model") or env.get("OPENROUTER_MODEL")
    deepseek_url = values.get("deepseek_url") or env.get("DEEPSEEK_URL")
    deepseek_key = values.get("deepseek_key") or env.get("DEEPSEEK_API_KEY")
    deepseek_model = values.get("deepseek_model") or env.get("DEEPSEEK_MODEL") or "deepseek-chat"
    if openrouter_key and openrouter_model:
        llm_provider, llm_model = "openrouter", str(openrouter_model)
    elif deepseek_url and deepseek_key:
        llm_provider, llm_model = "deepseek", str(deepseek_model)
    else:
        llm_provider, llm_model = "extractive", "extractive-fallback"

    if rag_env == "production" and provider == "dummy":
        raise RuntimeError(
            "RAG_ENV=production requires a real embedding backend; EMBEDDER_PROVIDER=dummy is not allowed."
        )
    if rag_env == "production" and llm_provider == "extractive" and not allow_extractive:
        raise RuntimeError(
            "No production LLM is configured. Configure OpenRouter/DeepSeek or set "
            "RAG_ALLOW_EXTRACTIVE_FALLBACK=true explicitly."
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
        "deepseek_url": deepseek_url,
        "deepseek_key": deepseek_key,
        "deepseek_model": deepseek_model,
        "openrouter_key": openrouter_key,
        "openrouter_model": openrouter_model,
        "openrouter_base_url": values.get("openrouter_base_url") or env.get("OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1/chat/completions",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }
    # Preserve orchestration-only settings without teaching every caller a new loader.
    for key in ("force_retrieval", "planner_route"):
        if key in values:
            config[key] = values[key]
    return config


def public_config(config: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: str(config[key]) if isinstance(config[key], Path) else config[key]
        for key in (
            "config_source", "repository_root", "docs_dir", "chroma_dir", "collection_name",
            "embedder_provider", "embedder_model", "llm_provider", "llm_model",
            "allow_dummy", "allow_extractive_fallback", "rag_env",
        )
    }


def log_resolved_config(config: Mapping[str, Any], prefix: str = "RAG_CONFIG") -> None:
    logger.info("%s %s", prefix, public_config(config))
