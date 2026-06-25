# Nanobot Integration

These snippets wire the local dementia RAG retriever into Nanobot without putting secrets in config files.

## MCP Tool Server

Example `~/.nanobot/config.json` fragment:

```json
{
  "tools": {
    "mcpServers": {
      "dementia_rag": {
        "command": "python3",
        "args": ["-m", "src.dementia_rag_mcp_server"],
        "cwd": "/mnt/d/Documents/College/Internships/LCK Yung/coarag/CoA-Agent",
        "env": {
          "CHROMA_DIR": ".chroma/ling_rag",
          "CHROMA_COLLECTION": "ling_rag",
          "EMBEDDER_PROVIDER": "auto",
          "EMBEDDINGS_OFFLINE": "true"
        }
      }
    }
  }
}
```

If your Nanobot config launches the server by absolute file path instead, this
also works:

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
          "EMBEDDER_PROVIDER": "auto",
          "EMBEDDINGS_OFFLINE": "true"
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
For document-grounded questions about dementia, caregiving, symptoms, safety,
assessment, interventions, or knowledge-base content, call the
search_dementia_knowledge MCP tool before answering.

Use the returned context and sources as the grounding evidence. Do not claim
knowledge from documents unless it appears in the retrieved context. If the tool
returns no relevant context, say that the knowledge base did not contain enough
information and offer general, non-diagnostic guidance. If risk_level is "high",
encourage urgent local emergency or clinical support as appropriate.
```
