from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any
from urllib import parse, request

logger = logging.getLogger(__name__)

try:
    from .citations import finalize_user_facing_result
    from .dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from .user.message_router import handle_incoming_message
    from .orchestrator import handle_dementia_user_message
    from .pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config
    from .screening.outbox import mark_screening_message_delivered
    from .pipeline.rag_agent import create_chat_answer, get_runtime_agent
    from .rag.runtime_config import load_rag_config, log_resolved_config
except ImportError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.citations import finalize_user_facing_result
    from src.dementia_rag import answer_from_dementia_knowledge, search_dementia_knowledge
    from src.user.message_router import handle_incoming_message
    from src.orchestrator import handle_dementia_user_message
    from src.pipeline.rag_agent import answer_question as shared_answer_question, build_default_rag_config
    from src.screening.outbox import mark_screening_message_delivered
    from src.pipeline.rag_agent import create_chat_answer, get_runtime_agent
    from src.rag.runtime_config import load_rag_config, log_resolved_config


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


def handle_incoming_message_tool(
    message: str,
    sender_id: str = "",
    channel: str = "telegram",
    telegram_username: str = "",
) -> str:
    """
    MANDATORY FINAL-ANSWER TOOL for all Telegram user messages.

    This tool already performs:
    - caregiver/user routing
    - dementia RAG retrieval
    - safety checks
    - medication boundaries
    - caregiver guidance
    - final user-facing formatting

    Always call this tool before answering any Telegram user message.

    After this tool returns, send the returned text directly to the user.
    Do not summarize, rewrite, expand, supplement, cite, or add medical knowledge.
    Do not mention RAG, database, MCP, tool calls, file names, source paths,
    debug logs, Chroma, markdown files, or retrieval.
    """
    if telegram_username:
        result = handle_incoming_message(message, sender_id, channel or "telegram", telegram_username)
    else:
        result = handle_incoming_message(message, sender_id, channel or "telegram")
    if str(channel or "telegram").lower() == "telegram":
        _deliver_telegram_outbound(result.get("outbound_messages"))
    public = _public_message_result(result)
    answer = str(public.get("answer") or "").strip()

    if not answer:
        answer = "抱歉，我暫時未能找到足夠資料回答。你可以換一種方式再問一次。"

    return answer


def _deliver_telegram_outbound(messages: object) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not bot_token or not isinstance(messages, list):
        return
    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    for item in messages:
        if not isinstance(item, dict):
            continue
        chat_id = str(item.get("recipient_sender_id") or "").strip()
        text = str(item.get("message") or "").strip()
        if not chat_id or not text:
            continue
        payload = parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        try:
            with request.urlopen(request.Request(endpoint, data=payload, method="POST"), timeout=8) as response:
                if 200 <= response.status < 300:
                    mark_screening_message_delivered(str(item.get("delivery_id") or ""))
        except (OSError, ValueError):
            continue


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


def diagnose_runtime(*, validate_llm: bool = True) -> dict[str, object]:
    """Initialize external dependencies without opening MCP stdio."""
    config = load_rag_config("mcp")
    log_resolved_config(config, "MCP_DIAGNOSE_CONFIG")
    agent = get_runtime_agent({**config, "auto_index": False})
    count = agent.vector_store.count()
    if validate_llm and config["llm_provider"] != "extractive":
        generator = create_chat_answer(config)
        if generator is None or not generator("Reply with OK only.").strip():
            raise RuntimeError("Configured LLM health check returned an empty response.")
    return {
        "status": "ok", "collection_count": count,
        "embedder_provider": agent.embedder.resolved_provider,
        "embedding_model": config["embedder_model"],
        "llm_provider": config["llm_provider"], "llm_model": config["llm_model"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnose", action="store_true", help="Validate embedder, Chroma and LLM without starting MCP")
    args = parser.parse_args()
    if mcp is None:
        raise RuntimeError("Install the Python MCP package to run this server: pip install mcp")
    try:
        health = diagnose_runtime(validate_llm=args.diagnose)
        if args.diagnose:
            print(health)
            return
        config = load_rag_config("mcp")
        print(f"MCP_STARTUP chroma_dir={config['chroma_dir']}", file=sys.stderr)
        print(f"MCP_STARTUP collection_name={config['collection_name']}", file=sys.stderr)
        print("MCP_STARTUP health=ok enabled_tools=handle_incoming_message", file=sys.stderr)
        mcp.run()
    except BaseException:
        logger.exception("MCP process failed during initialization or server lifecycle")
        raise


if __name__ == "__main__":
    main()
