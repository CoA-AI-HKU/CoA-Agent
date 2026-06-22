from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from .document import Document
from .markdown_loader import load_markdown_documents


def default_deepseek_callable(prompt: str) -> str:
    print("--- Prompt sent to DeepSeek (truncated) ---")
    print(prompt[:2000])
    print("--- End prompt ---")
    print("Warning: No DeepSeek endpoint is configured. Install or set DEEPSEEK_URL and DEEPSEEK_API_KEY to use a remote model, or run with --fallback-to-top-chunk.")
    return "No DeepSeek endpoint configured."


def build_agent(
    data_dir: Path | str = "data/mds", embedder_provider: str = "auto", skip_index: bool = False
) -> "RagAgent":
    # import RagAgent lazily to avoid heavy dependencies at import time
    from .rag_agent import RagAgent
    from .embedder import Embedder

    docs: List[Document] = load_markdown_documents(Path(data_dir))
    embedder = Embedder(model_name=None, provider=embedder_provider)
    agent = RagAgent(embedder=embedder)

    if skip_index:
        print("Skipping indexing as requested; agent has empty/previous index.")
        return agent

    if docs:
        print(f"Indexing {len(docs)} markdown document(s) from {data_dir} using provider={embedder_provider}...")
        agent.index_documents(docs)
        print("Indexing complete.")
    else:
        print(f"No markdown files found under {data_dir}; agent has empty index.")
    return agent


def interactive_loop(agent: RagAgent, deepseek_callable: Callable[[str], str], fallback_to_top_chunk: bool = False) -> None:
    print("Enter questions (empty line to quit). Type 'reload' to re-index documents.")
    while True:
        query = input("Question> ").strip()
        if query == "":
            break
        if query.lower() == "reload":
            agent = build_agent()
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
    parser.add_argument("--embedder-provider", default=os.getenv("EMBEDDER_PROVIDER", "auto"), help="Embedder provider: auto|local|openai|dummy")
    parser.add_argument("--deepseek-url", default=os.getenv("DEEPSEEK_URL"), help="DeepSeek endpoint URL")
    parser.add_argument("--deepseek-key", default=os.getenv("DEEPSEEK_API_KEY"), help="DeepSeek API key")
    parser.add_argument("--deepseek-model", default=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"), help="DeepSeek model name")
    parser.add_argument("--fallback-to-top-chunk", action="store_true", help="Return the top retrieved chunk instead of calling DeepSeek")
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

    agent = build_agent(data_dir=args.data_dir, embedder_provider=args.embedder_provider, skip_index=args.skip_index)
    interactive_loop(agent, deepseek_callable, fallback_to_top_chunk=args.fallback_to_top_chunk)


if __name__ == "__main__":
    main()
