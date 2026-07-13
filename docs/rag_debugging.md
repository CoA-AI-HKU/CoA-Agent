# RAG Debugging

## Rebuild the Index

Use this after changing markdown, chunking, or embedding settings:

```bash
python3 -m src.cli --embedder-provider dummy --force-reindex --debug-rag --show-sources
```

For better retrieval quality, use a real local sentence-transformers model or an
OpenAI-compatible embedding backend instead of `dummy`.

## Answer Mode

Use answer mode for chatbot behavior:

```bash
python3 -m src.cli \
  --retrieve-top-k 8 \
  --answer-top-k 3 \
  --min-relevance-score 0.35 \
  --show-sources \
  --debug-rag
```

The agent retrieves candidate chunks, reranks them, uses the best chunks, and
returns a concise grounded answer.

## Retrieval Debug Mode

Use this only to inspect the top retrieved chunk:

```bash
python3 -m src.cli --fallback-to-top-chunk --show-sources
```

Do not use `--fallback-to-top-chunk` for final Telegram or Nanobot answer
quality. It bypasses answer synthesis.

## MCP Debugging

Enable RAG debug logs with:

```bash
RAG_DEBUG=1 python3 -m src.dementia_rag_mcp_server
```

Debug logs must go to stderr. Do not print normal debug text to stdout in the
MCP server, because stdout is used for MCP protocol messages.

## Evaluation

Run the lightweight eval set:

```bash
python tests/evaluation/run_rag_eval.py
```

The eval checks expected sources, key answer terms, concise answers, fallback
behavior, and no-crash empty retrieval behavior.
