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
          "handle_incoming_message"
        ],
        "toolTimeout": 120,
        "env": {
          "CHROMA_DIR": "/home/aine/.cache/coa-agent/chroma/ling_rag",
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
The `CHROMA_DIR` value can be changed per deployment, but keep it on a writable local filesystem. If it is omitted, the server defaults to `/home/aine/.cache/coa-agent/chroma/ling_rag`.

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
        "enabledTools": [
          "handle_incoming_message"
        ],
        "toolTimeout": 120,
        "env": {
          "CHROMA_DIR": "/home/aine/.cache/coa-agent/chroma/ling_rag",
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
On startup, automatically start from this local dementia RAG backend. Do not run
a broad search, web search, browser search, or generic knowledge lookup. Wait
for the Telegram or WhatsApp user message, then use only the `dementia_rag` MCP
tool below.

For every Telegram or WhatsApp user message, call the MCP tool
`handle_incoming_message` before answering, passing the platform sender ID when
available. This router separates caregiver mode from user support mode.
This call is internal. Never tell the user to call
`handle_incoming_message`, `handle_dementia_user_message`, or any other tool,
and never mention MCP tools, function names,
Python functions, tool names, database filenames, RAG internals, Chroma, debug
logs, tracebacks, exceptions, or implementation details to the user.

Do not use web search, browser search, generic knowledge search, or any
non-dementia_rag tool for Telegram replies. The only allowed source for final
answers is the local dementia RAG database returned by
`handle_incoming_message`.

Do not answer dementia, MCI, caregiving, medication, symptom, memory, daily
care, or patient-support questions from model knowledge alone.

Do not assume the user has dementia, MCI, memory loss, or a caregiver. If the
user mentions forgetfulness, treat it as a general memory concern unless they
explicitly mention dementia or diagnosis.

Never point out that the user repeated a question. Repetition should be handled
gently without calling attention to it.

Do not show sources, filenames, database references, tool names, or debug text
in user-facing replies unless the user explicitly asks for sources.

Your final reply must be based only on the returned tool result.
Reply with the exact answer text returned by the tool unless formatting is
strictly necessary for Telegram.
If tool use fails, provide a short safe fallback and do not reveal the tool
failure or any internal tool/debug text.

If the tool says the database has insufficient information, repeat that fallback
and do not add outside information.

Do not provide medication advice. If the tool returns a medication or diagnosis
boundary message, repeat it and add nothing else.

The MCP server should expose `handle_incoming_message` for normal Nanobot use.
If Nanobot cannot yet pass sender IDs, `handle_dementia_user_message` may remain
enabled temporarily for compatibility. Debug helper
functions such as `search_dementia_knowledge` or
`answer_from_dementia_knowledge` must not be exposed to Nanobot, Telegram, or
WhatsApp production config.

Nanobot production config should prefer only `handle_incoming_message` in
`enabledTools`. If compatibility is required, expose only
`handle_incoming_message` and `handle_dementia_user_message`. Do not add the
debug MCP tools to Telegram or WhatsApp bot config.
```

## Security

Regenerate any Telegram bot token that appeared in logs. Store tokens in
environment variables or a protected secrets file such as
`~/.nanobot/secrets.env`; never commit tokens and never print them in logs.
