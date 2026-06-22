from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, List

from .markdown_loader import load_markdown_documents
from .document import Document


def default_deepseek_callable(prompt: str) -> str:
    print("--- Prompt sent to DeepSeek (truncated) ---")
    print(prompt[:2000])
    print("--- End prompt ---")
    return "I don't know."


def build_agent(data_dir: Path | str = "data/mds") -> "RagAgent":
    # import RagAgent lazily to avoid heavy dependencies at import time
    from .rag_agent import RagAgent

    docs: List[Document] = load_markdown_documents(Path(data_dir))
    agent = RagAgent()
    if docs:
        print(f"Indexing {len(docs)} markdown document(s) from {data_dir}...")
        agent.index_documents(docs)
        print("Indexing complete.")
    else:
        print(f"No markdown files found under {data_dir}; agent has empty index.")
    return agent


def interactive_loop(agent: RagAgent, deepseek_callable: Callable[[str], str]) -> None:
    print("Enter questions (empty line to quit). Type 'reload' to re-index documents.")
    while True:
        query = input("Question> ").strip()
        if query == "":
            break
        if query.lower() == "reload":
            agent = build_agent()
            continue
        answer = agent.answer(query, deepseek_callable)
        print("Answer:\n", answer)


def main() -> None:
    deepseek_url = os.getenv("DEEPSEEK_URL")
    deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")

    if deepseek_url and deepseek_api_key:
        try:
            import requests

            def remote_deepseek(prompt: str) -> str:
                resp = requests.post(
                    deepseek_url,
                    headers={"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"},
                    json={"prompt": prompt},
                    timeout=30,
                )
                resp.raise_for_status()
                data = resp.json()
                return data.get("answer") or data.get("text") or ""

            deepseek_callable = remote_deepseek
        except Exception:
            print("Failed to configure remote DeepSeek callable; falling back to local stub.")
            deepseek_callable = default_deepseek_callable
    else:
        deepseek_callable = default_deepseek_callable

    agent = build_agent()
    interactive_loop(agent, deepseek_callable)


if __name__ == "__main__":
    main()
