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
          "search_dementia_knowledge",
          "answer_from_dementia_knowledge"
        ],
        "toolTimeout": 60,
        "env": {
          "CHROMA_DIR": ".chroma/ling_rag",
          "CHROMA_COLLECTION": "ling_rag",
          "EMBEDDER_PROVIDER": "auto",
          "EMBEDDINGS_OFFLINE": "true",
          "RAG_RETRIEVE_TOP_K": "8",
          "RAG_ANSWER_TOP_K": "3"
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
answer_from_dementia_knowledge MCP tool before answering.

If the tool returns found=true, send `answer_with_sources` mostly unchanged when
present; otherwise send `answer` mostly unchanged. If found=false, say that the
provided documents do not contain enough information. Do not answer
document-grounded questions from general model knowledge alone.

Use search_dementia_knowledge only for retrieval debugging. For dementia-support
questions, keep responses calm, short, and reassuring. Avoid diagnosis,
treatment, medication, or emergency medical advice. If there is immediate danger,
wandering risk, severe confusion, injury, or self-harm risk, advise contacting a
caregiver, emergency services, or a qualified clinician.
```

## Security

Regenerate any Telegram bot token that appeared in logs. Store tokens in
environment variables or a protected secrets file such as
`~/.nanobot/secrets.env`; never commit tokens and never print them in logs.
