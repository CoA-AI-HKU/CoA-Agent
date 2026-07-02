from __future__ import annotations

import json
import re
from pathlib import Path

from src.document import Document
from src.embedder import Embedder
from src.prompts import FALLBACK_ANSWER
from src.rag_agent import RagAgent
from src.vector_store import InMemoryVectorStore


EVAL_PATH = Path(__file__).with_name("rag_eval_questions.json")


def _sentence_count(text: str) -> int:
    return len([part for part in re.split(r"(?<=[.!?])\s+", text.strip()) if part])


def _build_eval_agent() -> RagAgent:
    documents = [
        Document(
            text="Computational linguistics is the scientific and engineering discipline concerned with understanding written and spoken language.",
            metadata={"source": "Introducing_computational_linguistics.md"},
        ),
        Document(
            text="When a person with dementia repeats the same question, caregivers can stay calm, reassure them, and use simple reminders.",
            metadata={"source": "dementia_care.md"},
        ),
    ]
    agent = RagAgent(embedder=Embedder(provider="dummy"), vector_store=InMemoryVectorStore())
    agent.index_documents(documents)
    return agent


def main() -> None:
    cases = json.loads(EVAL_PATH.read_text(encoding="utf-8"))
    agent = _build_eval_agent()
    failures: list[str] = []

    for case in cases:
        result = agent.answer_question(case["question"])
        answer = result["answer"]
        sources = result["sources"]

        if "expected_found" in case and result["found"] is not case["expected_found"]:
            failures.append(f"{case['question']}: expected found={case['expected_found']}, got {result['found']}")
        if "expected_answer" in case and answer != case["expected_answer"]:
            failures.append(f"{case['question']}: expected answer {case['expected_answer']!r}, got {answer!r}")
        for expected in case.get("expected_contains", []):
            if expected.lower() not in answer.lower():
                failures.append(f"{case['question']}: answer missing {expected!r}: {answer!r}")
        if "expected_source" in case and not any(case["expected_source"] in source for source in sources):
            failures.append(f"{case['question']}: expected source {case['expected_source']!r}, got {sources!r}")
        if "expected_source_contains" in case and not any(case["expected_source_contains"] in source for source in sources):
            failures.append(f"{case['question']}: expected source containing {case['expected_source_contains']!r}, got {sources!r}")
        if "max_sentences" in case and answer != FALLBACK_ANSWER and _sentence_count(answer) > case["max_sentences"]:
            failures.append(f"{case['question']}: answer too long: {answer!r}")

    if failures:
        print("RAG eval failed:")
        for failure in failures:
            print(f"- {failure}")
        raise SystemExit(1)

    print(f"RAG eval passed: {len(cases)} case(s)")


if __name__ == "__main__":
    main()
