# Nanobot Integration

These snippets wire the local dementia RAG retriever into Nanobot without putting secrets in config files.

## MCP Tool Server

Example `~/.nanobot/config.json` fragment:

```json
{
  "tools": {
    "mcpServers": {
      "dementia_rag": {
        "command": "bash",
        "args": [
          "-lc",
          "cd '/mnt/d/Documents/College/Internships/LCK Yung/coarag/CoA-Agent' && source .venv/bin/activate && python -m src.dementia_rag_mcp_server"
        ],
        "enabledTools": [
          "handle_dementia_user_message"
        ],
        "toolTimeout": 60,
        "env": {
          "CHROMA_DIR": ".chroma/ling_rag",
          "CHROMA_COLLECTION": "ling_rag",
          "EMBEDDER_PROVIDER": "dummy",
          "EMBEDDINGS_OFFLINE": "true",
          "RAG_RETRIEVE_TOP_K": "8",
          "RAG_ANSWER_TOP_K": "2",
          "RAG_ANSWER_LANGUAGE": "auto"
        }
      }
    }
  }
}
```

If running on a cloud server, replace the `cd` path with the deployed project path, for example `/home/aine/CoA-Agent`.

Do not print MCP debug messages to stdout. MCP uses stdout for protocol traffic. Use stderr:

```python
print("DEBUG: message", file=sys.stderr)
```

If your Nanobot config launches the server by absolute file path instead, this also works, but the explicit `cd` pattern above is safer:

```json
{
  "tools": {
    "mcpServers": {
      "dementia_rag": {
        "command": "python3",
        "args": ["/mnt/d/Documents/College/Internships/LCK Yung/coarag/CoA-Agent/src/dementia_rag_mcp_server.py"],
        "cwd": "/mnt/d/Documents/College/Internships/LCK Yung/coarag/CoA-Agent",
        "env": {
          "CHROMA_DIR": ".chroma/ling_rag",
          "CHROMA_COLLECTION": "ling_rag",
          "EMBEDDER_PROVIDER": "dummy",
          "EMBEDDINGS_OFFLINE": "true",
          "RAG_ANSWER_TOP_K": "2",
          "RAG_ANSWER_LANGUAGE": "auto"
        }
      }
    }
  }
}
```

## Telegram Channel

Use the bot token from the process environment:

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "${TELEGRAM_BOT_TOKEN}"
    }
  }
}
```

## Agent Instructions

Add this to the Nanobot agent instruction or policy block:

```text
On startup, do not run a broad search, web search, browser search, or generic
knowledge lookup. Wait for the Telegram user message, then use only the
`dementia_rag` MCP tool below.

For every Telegram user message, call the MCP tool
`handle_dementia_user_message` before answering.

Do not use web search, browser search, generic knowledge search, or any
non-dementia_rag tool for Telegram replies. The only allowed source for final
answers is the local dementia RAG database returned by
`handle_dementia_user_message`.

Do not answer dementia, MCI, caregiving, medication, symptom, memory, daily
care, or patient-support questions from model knowledge alone.

Your final reply must be based only on the returned tool result.
Reply with the exact answer text returned by the tool unless formatting is
strictly necessary for Telegram.

If the tool says the database has insufficient information, repeat that fallback
and do not add outside information.

Do not provide medication advice. If the tool returns a medication or diagnosis
boundary message, repeat it and add nothing else.

The MCP server exposes only `handle_dementia_user_message` by default. Set
`RAG_ENABLE_DEBUG_TOOLS=true` only in a local debugging session if you need
`search_dementia_knowledge` or `answer_from_dementia_knowledge`; never enable
those debug tools for Telegram production.
```

## Security

Regenerate any Telegram bot token that appeared in logs. Store tokens in
environment variables or a protected secrets file such as
`~/.nanobot/secrets.env`; never commit tokens and never print them in logs.
