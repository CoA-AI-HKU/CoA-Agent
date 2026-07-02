from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from .dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from .orchestrator import handle_dementia_user_message
    from .pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config
except ImportError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from src.orchestrator import handle_dementia_user_message
    from src.pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config


def search_dementia_knowledge_tool(question: str) -> dict[str, Any]:
    """MCP tool wrapper for dementia knowledge-base retrieval."""
    return search_dementia_knowledge(question)


def answer_from_dementia_knowledge_tool(question: str) -> dict[str, Any]:
    """MCP tool wrapper for grounded answer synthesis."""
    return shared_answer_question(question, build_default_rag_config("mcp"))


def handle_dementia_user_message_tool(message: str, user_id: str = "") -> dict[str, Any]:
    """Preferred MCP tool for Telegram/Nanobot user messages."""
    return handle_dementia_user_message(message, user_id or None)


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore[assignment]


mcp = FastMCP("dementia_rag") if FastMCP is not None else None
if mcp is not None:
    mcp.tool(name="handle_dementia_user_message")(handle_dementia_user_message_tool)
    mcp.tool(name="search_dementia_knowledge")(search_dementia_knowledge_tool)
    mcp.tool(name="answer_from_dementia_knowledge")(answer_from_dementia_knowledge_tool)


def main() -> None:
    if mcp is None:
        raise RuntimeError("Install the Python MCP package to run this server: pip install mcp")
    mcp.run()


if __name__ == "__main__":
    main()
