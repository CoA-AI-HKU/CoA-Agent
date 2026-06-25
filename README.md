# ling-rag
A RAG agent project for building a Retrieval-Augmented Generation (RAG) assistant.

## Project structure

- `src/`
  - `document.py` — canonical `Document` data model
  - `pdf_to_markdown.py` — PDF extraction and markdown conversion helpers
  - `chunker.py` — paragraph-aware chunking with overlap
  - `embedder.py` — pluggable embedding interface for local or OpenAI-compatible backends

## Current status

- Created the initial source packages for PDF-to-markdown conversion, document chunking, and embedding.
- The repository is ready to accept PDFs under `src/` or another designated input folder.

## Usage

1. Add PDFs under `data/pdfs/`.
2. Convert them to markdown with `src/pdf_ingest.py`.
3. Chunk the resulting document(s) with `src.chunker.chunk_document` or `src.chunker.chunk_documents`.
4. Generate embeddings using `src.embedder.Embedder`.

### Convert PDFs into markdown

Run:

```bash
python -m src.pdf_ingest
```

This scans `data/pdfs/` recursively and writes `.md` output files into `data/mds/`, preserving subdirectory structure.

## Notes

- PDF extraction supports `PyMuPDF` first, and falls back to `pypdf` if needed.
- Markdown conversion is simple and aims to preserve paragraphs, lists, and heading-like text.
- Chunking is paragraph-aware and uses default values `chunk_size=1000` and `chunk_overlap=200`.
- The embedder tries a local `sentence-transformers` model first; if unavailable, it can use the OpenAI-compatible API with `OPENAI_API_KEY`.

## Next steps

- Add a PDF ingestion script and vector store integration.
- Add retrieval, prompt construction, and DeepSeek API wiring.
- Add evaluation logic so the system can say "I don't know" when support is missing.

## Asking the agent questions

A minimal interactive CLI is provided at `src/cli.py`. It:

- Loads Markdown files from `data/mds/`.
- Indexes them into the RAG agent (chunking + embedding + Chroma storage).
- Starts an interactive prompt for questions.

Run the CLI:

```bash
python -m src.cli
```

Environment variables (optional):

- `DEEPSEEK_URL` — URL of a DeepSeek or compatible generation endpoint that accepts JSON `{ "prompt": "..." }` and returns JSON with `answer` or `text`.
- `DEEPSEEK_API_KEY` — API key for the remote DeepSeek service.

If `DEEPSEEK_URL` is not set the CLI prints the prompt it would send and returns "I don't know." as a safe default.

Example quick test (Python):

```python
from pathlib import Path
from src.markdown_loader import load_markdown_documents
from src.rag_agent import RagAgent

# load and index
docs = load_markdown_documents(Path('data/mds'))
agent = RagAgent()
agent.index_documents(docs)

# ask
print(agent.answer('What is computational linguistics?', lambda p: 'I dont know'))
```

# agent running
python -m src.cli

## Nanobot and Telegram integration

See `docs/nanobot_integration.md` for:

- the `dementia_rag` MCP server config snippet,
- Telegram channel config using `TELEGRAM_BOT_TOKEN` from the environment,
- agent policy instructions for document-grounded dementia questions.
