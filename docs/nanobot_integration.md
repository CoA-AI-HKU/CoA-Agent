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
          "handle_dementia_user_message",
          "search_dementia_knowledge",
          "answer_from_dementia_knowledge"
        ],
        "toolTimeout": 60,
        "env": {
          "CHROMA_DIR": ".chroma/ling_rag",
          "CHROMA_COLLECTION": "ling_rag",
          "EMBEDDER_PROVIDER": "dummy",
          "EMBEDDINGS_OFFLINE": "true",
          "RAG_RETRIEVE_TOP_K": "8",
          "RAG_ANSWER_TOP_K": "3",
          "RAG_LANGUAGE": "zh-Hant"
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
          "RAG_LANGUAGE": "zh-Hant"
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
For every Telegram user message, call the MCP tool
`handle_dementia_user_message` before answering.

Do not answer dementia, MCI, caregiving, medication, symptom, memory, daily
care, or patient-support questions from model knowledge alone.

Your final reply must be based only on the returned tool result.

If the tool says the database has insufficient information, repeat that fallback
and do not add outside information.

Use search_dementia_knowledge only for retrieval debugging. Use
answer_from_dementia_knowledge only for direct RAG debugging; Telegram replies
should use handle_dementia_user_message.
```

## Security

Regenerate any Telegram bot token that appeared in logs. Store tokens in
environment variables or a protected secrets file such as
`~/.nanobot/secrets.env`; never commit tokens and never print them in logs.
