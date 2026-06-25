from __future__ import annotations

from typing import Any

from .dementia_rag import search_dementia_knowledge


def search_dementia_knowledge_tool(question: str) -> dict[str, Any]:
    """MCP tool wrapper for dementia knowledge-base retrieval."""
    return search_dementia_knowledge(question)


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    FastMCP = None  # type: ignore[assignment]


mcp = FastMCP("dementia_rag") if FastMCP is not None else None
if mcp is not None:
    mcp.tool(name="search_dementia_knowledge")(search_dementia_knowledge_tool)


def main() -> None:
    if mcp is None:
        raise RuntimeError("Install the Python MCP package to run this server: pip install mcp")
    mcp.run()


if __name__ == "__main__":
    main()
