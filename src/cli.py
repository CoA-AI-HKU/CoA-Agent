from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, List

from .pipeline.chunker import DEFAULT_CHUNK_OVERLAP, DEFAULT_CHUNK_SIZE
from .pipeline.document import Document
from .pipeline.markdown_loader import load_markdown_documents
from .pipeline.rag_agent import DEFAULT_CHROMA_DIR, answer_question as shared_answer_question, build_default_rag_config
from .pipeline.vector_store import get_default_vector_store


def _index_manifest_path(persist_dir: Path) -> Path:
    return persist_dir / "index_manifest.json"


def _document_signature(
    documents: List[Document],
    chunk_size: int,
    chunk_overlap: int,
    embedder_provider: str,
    embedder_model: str | None,
) -> dict[str, Any]:
    document_entries = []
    for document in documents:
        source = str(document.metadata.get("source", ""))
        text_hash = hashlib.sha256(document.text.encode("utf-8")).hexdigest()
        document_entries.append({"source": source, "sha256": text_hash, "chars": len(document.text)})

    return {
        "documents": sorted(document_entries, key=lambda item: item["source"]),
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "embedder_provider": embedder_provider,
        "embedder_model": embedder_model or "all-MiniLM-L6-v2",
    }


def _load_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _save_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _ensure_directory(path.parent)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def _ensure_directory(path: Path | str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _clear_persist_dir(path: Path | str) -> None:
    target = Path(path).resolve(strict=False)
    chroma_parts = {part.lower() for part in target.parts}
    if not any("chroma" in part for part in chroma_parts):
        raise ValueError(f"Refusing to clear non-Chroma vector index directory: {target}")
    if target.exists() and target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def build_agent(
    data_dir: Path | str = "data/mds",
    embedder_provider: str = "auto",
    embedder_model: str | None = None,
    offline_embeddings: bool = False,
    skip_index: bool = False,
    persist_dir: Path | str = DEFAULT_CHROMA_DIR,
    force_reindex: bool = False,
    min_shared_query_terms: int = 1,
    retrieve_top_k: int = 8,
    answer_top_k: int = 2,
    min_relevance_score: float = 0.35,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> "RagAgent":
    # import RagAgent lazily to avoid heavy dependencies at import time
    from .pipeline.rag_agent import RagAgent

    docs: List[Document] = load_markdown_documents(Path(data_dir))
    persist_path = Path(persist_dir)
    agent = RagAgent(
        embedder_provider=embedder_provider,
        embedder_model_name=embedder_model,
        offline_embeddings=offline_embeddings,
        vector_store=None,
        chunk_size=chunk_size or DEFAULT_CHUNK_SIZE,
        chunk_overlap=chunk_overlap or DEFAULT_CHUNK_OVERLAP,
        min_shared_query_terms=min_shared_query_terms,
        retrieve_top_k=retrieve_top_k,
        answer_top_k=answer_top_k,
        min_relevance_score=min_relevance_score,
    )
    manifest_path = _index_manifest_path(persist_path)
    current_manifest = _document_signature(
        docs,
        agent.chunk_size,
        agent.chunk_overlap,
        embedder_provider,
        embedder_model,
    )
    saved_manifest = _load_manifest(manifest_path)

    force_clear_before_open = bool(docs) and (force_reindex or saved_manifest != current_manifest)
    if force_clear_before_open:
        _clear_persist_dir(persist_path)

    _ensure_directory(persist_path)
    vector_store = get_default_vector_store(persist_directory=persist_path)
    agent.vector_store = vector_store

    if skip_index:
        store_count = vector_store.count() if hasattr(vector_store, "count") else 0
        if store_count > 0:
            print("Skipping indexing as requested; agent will use the existing index if one is available.")
            return agent
        print("No existing vector index was found, so rebuilding it from markdown documents.")

    if docs:
        store_count = vector_store.count() if hasattr(vector_store, "count") else 0

        needs_reindex = force_clear_before_open or store_count <= 0
        if not needs_reindex:
            print(f"Using existing index with {store_count} chunk(s) from {persist_dir}.")
            return agent

        print(f"Indexing {len(docs)} markdown document(s) from {data_dir} using provider={embedder_provider}...")
        try:
            agent.index_documents(docs)
        except RuntimeError as exc:
            if embedder_provider != "auto" or "No real embedding backend is available" not in str(exc):
                raise

            print(str(exc))
            print("Falling back to provider=dummy so the local RAG client can still run.")
            print("For production-quality retrieval, install/cache sentence-transformers or configure OPENAI_API_KEY.")
            embedder_provider = "dummy"
            current_manifest = _document_signature(
                docs,
                agent.chunk_size,
                agent.chunk_overlap,
                embedder_provider,
                embedder_model,
            )
            if hasattr(vector_store, "clear"):
                vector_store.clear()
            agent = RagAgent(
                embedder_provider=embedder_provider,
                embedder_model_name=embedder_model,
                offline_embeddings=offline_embeddings,
                vector_store=vector_store,
                chunk_size=chunk_size or DEFAULT_CHUNK_SIZE,
                chunk_overlap=chunk_overlap or DEFAULT_CHUNK_OVERLAP,
                min_shared_query_terms=min_shared_query_terms,
                retrieve_top_k=retrieve_top_k,
                answer_top_k=answer_top_k,
                min_relevance_score=min_relevance_score,
            )
            agent.index_documents(docs)
        _save_manifest(manifest_path, current_manifest)
        print("Indexing complete.")
    else:
        print(f"No markdown files found under {data_dir}; agent has empty index.")
    return agent


def interactive_loop(
    agent: RagAgent | None,
    runtime_config: dict[str, Any],
    fallback_to_top_chunk: bool = False,
    reload_agent: Callable[[], RagAgent] | None = None,
    show_sources: bool = False,
    debug_rag: bool = False,
) -> None:
    from .orchestrator import handle_dementia_user_message
    
    print("Enter questions (empty line to quit). Type 'reload' to re-index documents.")
    while True:
        try:
            query = input("Question> ").strip()
        except EOFError:
            break
        if query == "":
            break
        if query.lower() == "reload":
            if fallback_to_top_chunk:
                agent = reload_agent() if reload_agent else build_agent(force_reindex=True)
            else:
                runtime_config["force_reindex"] = True
                print("The next question will rebuild the shared RAG index.")
            continue
        if fallback_to_top_chunk:
            if agent is None:
                agent = reload_agent() if reload_agent else build_agent(force_reindex=True)
            answer = agent.answer_with_top_chunk(query)
            if debug_rag:
                print("Fallback mode active: True")
            print("Answer:\n", answer)
        else:
            result = handle_dementia_user_message(query, show_sources=show_sources)
            print("Answer:\n", result.get("answer", result))
            if show_sources and result.get("sources"):
                print("Sources metadata:", result.get("sources"))
            if debug_rag:
                print("Debug:", result.get("debug", {}))


def _print_cli_debug(query: str, result: dict[str, Any]) -> None:
    debug = result.get("debug", {})
    mcp_config = build_default_rag_config("mcp")
    print(f"Question: {query}")
    print(f"Search query: {debug.get('search_query', query)}")
    print(f"cwd: {debug.get('cwd')}")
    print(f"docs_dir: {debug.get('docs_dir')}")
    print(f"chroma_dir: {debug.get('chroma_dir')}")
    print(f"collection_name: {debug.get('collection_name')}")
    print(f"chunk_count: {debug.get('chunk_count')}")
    print(f"embedding_model: {debug.get('embedding_model')}")
    print(f"embedder_provider: {debug.get('embedder_provider')}")
    print(f"llm_model: {debug.get('llm_model')}")
    print(f"llm_provider: {debug.get('llm_provider')}")
    print(f"mode: {debug.get('mode')}")
    print(f"retrieve_top_k: {debug.get('retrieve_top_k')}")
    print(f"answer_top_k: {debug.get('answer_top_k')}")
    print(f"min_relevance_score: {debug.get('min_relevance_score')}")
    print(f"fallback_active: {debug.get('fallback_active')}")
    print(f"sources: {result.get('sources', [])}")
    print(f"scores: {debug.get('scores', [])}")
    print("MCP default comparison:")
    for field in (
        "mode",
        "docs_dir",
        "chroma_dir",
        "collection_name",
        "embedding_model",
        "embedder_provider",
        "llm_model",
        "retrieve_top_k",
        "answer_top_k",
        "min_relevance_score",
    ):
        print(f"mcp_{field}: {mcp_config.get(field)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Interactive RAG CLI")
    parser.add_argument("--data-dir", default="data/mds", help="Path to markdown documents")
    parser.add_argument("--skip-index", action="store_true", help="Skip indexing step (fast start)")
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild the vector index even if the source files have not changed")
    parser.add_argument("--persist-dir", default=os.getenv("CHROMA_DIR", DEFAULT_CHROMA_DIR), help="Directory for the persistent Chroma index")
    # CHANGE: embedder-provider default from "dummy" to "auto"
    parser.add_argument("--embedder-provider", default=os.getenv("EMBEDDER_PROVIDER", "auto"), help="Embedder provider: auto|local|openai|dummy")
    parser.add_argument("--embedder-model", default=os.getenv("EMBEDDER_MODEL"), help="Embedding model name or local model directory")
    parser.add_argument("--offline-embeddings", action="store_true", default=os.getenv("EMBEDDINGS_OFFLINE", "").lower() in {"1", "true", "yes"}, help="Load embedding models from local files only")
    parser.add_argument("--deepseek-url", default=os.getenv("DEEPSEEK_URL"), help="DeepSeek endpoint URL")
    parser.add_argument("--deepseek-key", default=os.getenv("DEEPSEEK_API_KEY"), help="DeepSeek API key")
    parser.add_argument("--deepseek-model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), help="DeepSeek model name")
    # KEEP THIS ONE (with default=False)
    parser.add_argument("--fallback-to-top-chunk", action="store_true", default=False, help="Return the top retrieved chunk instead of calling DeepSeek")
    parser.add_argument("--min-shared-query-terms", type=int, default=int(os.getenv("RAG_MIN_SHARED_QUERY_TERMS", "1")), help="Minimum meaningful query terms that must appear in a retrieved chunk")
    parser.add_argument("--retrieve-top-k", type=int, default=int(os.getenv("RAG_RETRIEVE_TOP_K", "8")), help="Number of candidate chunks to retrieve before answer filtering")
    parser.add_argument("--answer-top-k", type=int, default=int(os.getenv("RAG_ANSWER_TOP_K", "2")), help="Number of best chunks to use for answer synthesis")
    parser.add_argument("--min-relevance-score", type=float, default=float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.35")), help="Minimum normalized relevance score required before answering")
    parser.add_argument("--answer-language", choices=["auto", "zh-Hant", "zh-Hans", "en"], default=os.getenv("RAG_ANSWER_LANGUAGE", "auto"), help="Answer language: auto|zh-Hant|zh-Hans|en")
    parser.add_argument("--chunk-size", type=int, default=int(os.getenv("RAG_CHUNK_SIZE", str(DEFAULT_CHUNK_SIZE))), help="Target chunk size in characters")
    parser.add_argument("--chunk-overlap", type=int, default=int(os.getenv("RAG_CHUNK_OVERLAP", str(DEFAULT_CHUNK_OVERLAP))), help="Maximum paragraph/sentence overlap between chunks")
    parser.add_argument("--show-sources", action="store_true", help="Print retrieved source files with the answer")
    parser.add_argument("--debug-rag", action="store_true", help="Print RAG retrieval and synthesis debug details")
    args = parser.parse_args()

    def create_agent(force_reindex: bool = False) -> "RagAgent":
        return build_agent(
            data_dir=args.data_dir,
            embedder_provider=args.embedder_provider,
            embedder_model=args.embedder_model,
            offline_embeddings=args.offline_embeddings,
            skip_index=args.skip_index,
            persist_dir=args.persist_dir,
            force_reindex=force_reindex,
            min_shared_query_terms=args.min_shared_query_terms,
            retrieve_top_k=args.retrieve_top_k,
            answer_top_k=args.answer_top_k,
            min_relevance_score=args.min_relevance_score,
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )

    runtime_config = build_default_rag_config("cli", {
        "docs_dir": args.data_dir,
        "chroma_dir": args.persist_dir,
        "embedder_provider": args.embedder_provider,
        "embedder_model": args.embedder_model,
        "offline_embeddings": args.offline_embeddings,
        "retrieve_top_k": args.retrieve_top_k,
        "answer_top_k": args.answer_top_k,
        "min_relevance_score": args.min_relevance_score,
        "answer_language": args.answer_language,
        "min_shared_query_terms": args.min_shared_query_terms,
        "chunk_size": args.chunk_size,
        "chunk_overlap": args.chunk_overlap,
        "deepseek_url": args.deepseek_url,
        "deepseek_key": args.deepseek_key,
        "deepseek_model": args.deepseek_model,
        "force_reindex": args.force_reindex,
    })

    agent = create_agent(force_reindex=args.force_reindex) if args.fallback_to_top_chunk else None
    if args.fallback_to_top_chunk:
        runtime_config["force_reindex"] = False
    interactive_loop(
        agent,
        runtime_config,
        fallback_to_top_chunk=args.fallback_to_top_chunk,
        reload_agent=lambda: create_agent(force_reindex=True),
        show_sources=args.show_sources,
        debug_rag=args.debug_rag,
    )

if __name__ == "__main__":
    main()
