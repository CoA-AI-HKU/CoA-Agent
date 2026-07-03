# Dementia Rag
A RAG agent project for building a Retrieval-Augmented Generation (RAG) assistant.

## Project structure

- `src/`
  - `pipeline/document.py` — canonical `Document` data model
  - `pdf_to_markdown.py` — PDF extraction and markdown conversion helpers
  - `pipeline/chunker.py` — paragraph-aware chunking with overlap
  - `pipeline/embedder.py` — pluggable embedding interface for local or OpenAI-compatible backends

## Current status

- Created the initial source packages for PDF-to-markdown conversion, document chunking, and embedding.
- The repository is ready to accept PDFs under `src/` or another designated input folder.

## Usage

1. Add PDFs under `data/pdfs/`.
2. Convert them to markdown with `src/pdf_ingest.py`.
3. Chunk the resulting document(s) with `src.pipeline.chunker.chunk_document` or `src.pipeline.chunker.chunk_documents`.
4. Generate embeddings using `src.pipeline.embedder.Embedder`.

### Convert PDFs into markdown

Run:

```bash
python -m src.pdf_ingest
```

This scans `data/pdfs/` recursively and writes `.md` output files into `data/mds/`, preserving subdirectory structure.

### Convert websites into markdown

Add one URL per line in `data/websites.txt`, then run:

```bash
python -m src.web_ingest
```

This fetches the page, strips common non-content HTML, converts headings/lists/links into readable markdown, and writes the result under `data/mds/web/<host>/...`. The normal CLI indexing path will then chunk and embed it with the rest of `data/mds/`.

By default, website ingestion crawls links under the starting URL path prefix. For example, starting from `https://www.jccpa.org.hk/en/about-dementia/` keeps the crawl focused under `/en/about-dementia/` instead of pulling in news, services, training, and other unrelated site sections. It skips obvious non-HTML assets and stops at bounded limits so large sites do not run forever.

You can also pass URLs directly, use another list file, or disable crawling:

```bash
python -m src.web_ingest https://example.org/article
python -m src.web_ingest --url-file urls.txt --overwrite
python -m src.web_ingest --no-crawl https://example.org/article
python -m src.web_ingest --max-pages-per-site 250 --max-depth 6
python -m src.web_ingest --crawl-scope same-site
python -m src.web_ingest --delay 0.5 --timeout 30
```

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

If no real embedding backend is available, the CLI falls back to the deterministic `dummy` embedder so local indexing can still run. Use `--embedder-provider local` with a cached sentence-transformers model, or configure `OPENAI_API_KEY`, for better retrieval quality.

For answer-mode debugging:

```bash
python -m src.cli --embedder-provider dummy --retrieve-top-k 8 --answer-top-k 3 --show-sources --debug-rag
```

`--fallback-to-top-chunk` is only for retrieval debugging. It bypasses answer synthesis and should not be used for final Telegram/Nanobot replies.

The assistant detects the user's input language and answers in one language: Traditional Chinese (`zh-Hant`), Simplified Chinese (`zh-Hans`), or English (`en`). Retrieved sources may be in any of those languages, but the final answer is constrained to the detected answer language. Set `RAG_ANSWER_LANGUAGE=zh-Hant|zh-Hans|en` to override auto-detection.

For production cross-language retrieval, use a real multilingual embedding model through `EMBEDDER_MODEL`. The deterministic `dummy` embedder is useful for local tests, but it is lexical and weak when the query and source are in different languages.

Environment variables (optional):

- `DEEPSEEK_URL` — URL of a DeepSeek or compatible generation endpoint that accepts JSON `{ "prompt": "..." }` and returns JSON with `answer` or `text`.
- `DEEPSEEK_API_KEY` — API key for the remote DeepSeek service.

If `DEEPSEEK_URL` is not set the CLI prints the prompt it would send and returns "I don't know." as a safe default.

Example quick test (Python):

```python
from pathlib import Path
from src.pipeline.markdown_loader import load_markdown_documents
from src.pipeline.rag_agent import RagAgent

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

See `docs/rag_debugging.md` for retrieval/answer debugging commands and the lightweight eval:

```bash
python -m tests.run_rag_eval
```

