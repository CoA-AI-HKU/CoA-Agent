from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, List

from .document import Document
from .markdown_loader import load_markdown_documents
from .vector_store import get_default_vector_store


def default_deepseek_callable(prompt: str) -> str:
    print("--- Prompt sent to DeepSeek (truncated) ---")
    print(prompt[:2000])
    print("--- End prompt ---")
    print("Warning: No DeepSeek endpoint is configured. Install or set DEEPSEEK_URL and DEEPSEEK_API_KEY to use a remote model, or run with --fallback-to-top-chunk.")
    return "No DeepSeek endpoint configured."


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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")


def build_agent(
    data_dir: Path | str = "data/mds",
    embedder_provider: str = "auto",
    embedder_model: str | None = None,
    offline_embeddings: bool = False,
    skip_index: bool = False,
    persist_dir: Path | str = ".chroma/ling_rag",
    force_reindex: bool = False,
    min_shared_query_terms: int = 1,
) -> "RagAgent":
    # import RagAgent lazily to avoid heavy dependencies at import time
    from .rag_agent import RagAgent

    docs: List[Document] = load_markdown_documents(Path(data_dir))
    vector_store = get_default_vector_store(persist_directory=Path(persist_dir))
    agent = RagAgent(
        embedder_provider=embedder_provider,
        embedder_model_name=embedder_model,
        offline_embeddings=offline_embeddings,
        vector_store=vector_store,
        min_shared_query_terms=min_shared_query_terms,
    )

    if skip_index:
        print("Skipping indexing as requested; agent will use the existing index if one is available.")
        return agent

    if docs:
        manifest_path = _index_manifest_path(Path(persist_dir))
        current_manifest = _document_signature(
            docs,
            agent.chunk_size,
            agent.chunk_overlap,
            embedder_provider,
            embedder_model,
        )
        saved_manifest = _load_manifest(manifest_path)
        store_count = vector_store.count() if hasattr(vector_store, "count") else 0

        if not force_reindex and saved_manifest == current_manifest and store_count > 0:
            print(f"Using existing index with {store_count} chunk(s) from {persist_dir}.")
            return agent

        if hasattr(vector_store, "clear"):
            vector_store.clear()

        print(f"Indexing {len(docs)} markdown document(s) from {data_dir} using provider={embedder_provider}...")
        agent.index_documents(docs)
        _save_manifest(manifest_path, current_manifest)
        print("Indexing complete.")
    else:
        print(f"No markdown files found under {data_dir}; agent has empty index.")
    return agent


def interactive_loop(
    agent: RagAgent,
    deepseek_callable: Callable[[str], str],
    fallback_to_top_chunk: bool = False,
    reload_agent: Callable[[], RagAgent] | None = None,
) -> None:
    print("Enter questions (empty line to quit). Type 'reload' to re-index documents.")
    while True:
        query = input("Question> ").strip()
        if query == "":
            break
        if query.lower() == "reload":
            agent = reload_agent() if reload_agent else build_agent(force_reindex=True)
            continue
        if fallback_to_top_chunk:
            answer = agent.answer_with_top_chunk(query)
        else:
            answer = agent.answer(query, deepseek_callable)
        print("Answer:\n", answer)


def _extract_deepseek_text(data: dict) -> str:
    if data.get("answer"):
        return data["answer"]
    if data.get("text"):
        return data["text"]
    choices = data.get("choices") or []
    if choices:
        first_choice = choices[0]
        message = first_choice.get("message") or {}
        if message.get("content"):
            return message["content"]
        if first_choice.get("text"):
            return first_choice["text"]
    return ""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Interactive RAG CLI")
    parser.add_argument("--data-dir", default="data/mds", help="Path to markdown documents")
    parser.add_argument("--skip-index", action="store_true", help="Skip indexing step (fast start)")
    parser.add_argument("--force-reindex", action="store_true", help="Rebuild the vector index even if the source files have not changed")
    parser.add_argument("--persist-dir", default=os.getenv("CHROMA_DIR", ".chroma/ling_rag"), help="Directory for the persistent Chroma index")
    parser.add_argument("--embedder-provider", default=os.getenv("EMBEDDER_PROVIDER", "auto"), help="Embedder provider: auto|local|openai|dummy")
    parser.add_argument("--embedder-model", default=os.getenv("EMBEDDER_MODEL"), help="Embedding model name or local model directory")
    parser.add_argument("--offline-embeddings", action="store_true", default=os.getenv("EMBEDDINGS_OFFLINE", "").lower() in {"1", "true", "yes"}, help="Load embedding models from local files only")
    parser.add_argument("--deepseek-url", default=os.getenv("DEEPSEEK_URL"), help="DeepSeek endpoint URL")
    parser.add_argument("--deepseek-key", default=os.getenv("DEEPSEEK_API_KEY"), help="DeepSeek API key")
    parser.add_argument("--deepseek-model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), help="DeepSeek model name")
    parser.add_argument("--fallback-to-top-chunk", action="store_true", help="Return the top retrieved chunk instead of calling DeepSeek")
    parser.add_argument("--min-shared-query-terms", type=int, default=int(os.getenv("RAG_MIN_SHARED_QUERY_TERMS", "1")), help="Minimum meaningful query terms that must appear in a retrieved chunk")
    args = parser.parse_args()

    deepseek_url = args.deepseek_url
    deepseek_api_key = args.deepseek_key
    deepseek_model = args.deepseek_model

    if deepseek_url and deepseek_api_key:
        try:
            import requests

            def remote_deepseek(prompt: str) -> str:
                headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
                chat_payload = {
                    "model": deepseek_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                }
                resp = requests.post(
                    deepseek_url,
                    headers=headers,
                    json=chat_payload,
                    timeout=30,
                )
                if resp.status_code in {400, 404, 422}:
                    resp = requests.post(
                        deepseek_url,
                        headers=headers,
                        json={"prompt": prompt},
                        timeout=30,
                    )
                resp.raise_for_status()
                data = resp.json()
                return _extract_deepseek_text(data)

            deepseek_callable = remote_deepseek
        except Exception:
            print("Failed to configure remote DeepSeek callable; falling back to local stub.")
            deepseek_callable = default_deepseek_callable
    else:
        deepseek_callable = default_deepseek_callable

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
        )

    agent = create_agent(force_reindex=args.force_reindex)
    interactive_loop(
        agent,
        deepseek_callable,
        fallback_to_top_chunk=args.fallback_to_top_chunk,
        reload_agent=lambda: create_agent(force_reindex=True),
    )


if __name__ == "__main__":
    main()
