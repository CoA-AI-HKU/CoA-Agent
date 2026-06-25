from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

try:
    from .dementia_rag import search_dementia_knowledge
except ImportError:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    from src.dementia_rag import search_dementia_knowledge


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
