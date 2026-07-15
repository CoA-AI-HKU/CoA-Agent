from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

try:
    from .citations import finalize_user_facing_result
    from .dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from .user.message_router import handle_incoming_message
    from .orchestrator import handle_dementia_user_message
    from .pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config
except ImportError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.citations import finalize_user_facing_result
    from src.dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from src.user.message_router import handle_incoming_message
    from src.orchestrator import handle_dementia_user_message
    from src.pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config


def search_dementia_knowledge_tool(question: str) -> dict[str, Any]:
    """Debug only: retrieve context from the local dementia database."""
    return search_dementia_knowledge(question)


def answer_from_dementia_knowledge_tool(question: str) -> dict[str, Any]:
    """Debug only: answer from the local dementia database without Telegram routing."""
    return answer_from_dementia_knowledge(question)


def handle_dementia_user_message_tool(
    message: str,
    user_id: str = "",
    show_sources: bool = False,
) -> dict[str, Any]:
    """Production Telegram tool: answer using only the local dementia database and built-in safety boundaries."""
    return handle_dementia_user_message(message, user_id or None, show_sources=show_sources)


def handle_incoming_message_tool(message: str, sender_id: str = "", channel: str = "") -> dict[str, Any]:
    """Production router tool: separate caregiver mode from user support mode by sender ID."""
    result = handle_incoming_message(message, sender_id, channel)
    return _public_message_result(result)


def _public_message_result(result: dict[str, Any]) -> dict[str, Any]:
    """Expose only fields safe for a downstream Telegram/WhatsApp reply."""
    result = finalize_user_facing_result(result)
    public_fields = (
        "answer",
        "route",
        "intent",
        "safety_level",
        "role",
        "user_id",
        "linked_user_id",
        "found",
        "rag_called",
        "medication_status",
    )
    return {field: result[field] for field in public_fields if field in result}


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore[assignment]


mcp = FastMCP("dementia_rag") if FastMCP is not None else None
if mcp is not None:
    mcp.tool(name="handle_incoming_message")(handle_incoming_message_tool)


def main() -> None:
    if mcp is None:
        raise RuntimeError("Install the Python MCP package to run this server: pip install mcp")
    config = build_default_rag_config("mcp")
    print(f"MCP_STARTUP chroma_dir={config['chroma_dir']}", file=sys.stderr)
    print(f"MCP_STARTUP collection_name={config['collection_name']}", file=sys.stderr)
    print("MCP_STARTUP enabled_tools=handle_incoming_message", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
