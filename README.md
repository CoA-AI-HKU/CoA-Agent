# Dementia Rag
A RAG agent project for building a Retrieval-Augmented Generation (RAG) assistant.

## Project structure

- `src/`
  - `pipeline/document.py` — canonical `Document` data model
  - `pdf_to_markdown.py` — PDF extraction and markdown conversion helpers
  - `pipeline/chunker.py` — paragraph-aware chunking with overlap
  - `pipeline/embedder.py` — pluggable embedding interface for local or OpenAI-compatible backends
  - `intent_router.py` — deterministic intent recognizer for routing user messages
  - `meds/medicine_normalizer.py` — local medicine alias matching
  - `agents/` — coordinator, safety, RAG evidence, memory/routine, and response simplifier modules
  - `orchestrator.py` — main shared entrypoint used by CLI, MCP, Nanobot, Telegram, and WhatsApp


## Telegram and WhatsApp internal commands

These commands are handled inside the RAG message router when sent through Telegram or WhatsApp. They intentionally begin with a backslash so Telegram does not treat them as native bot-menu commands. Nanobot must pass the complete message and platform sender ID to `handle_incoming_message`.

```text
\register patient DISPLAY_NAME
\register caregiver DISPLAY_NAME
\whichroleami
\paircode
\link CODE
\relink CODE
\unlink
\unlink PATIENT_ID
\dashboard
\clearhistory
\clearhistory confirm
\accountcommands
```

- `\register patient DISPLAY_NAME` registers the sender as a patient account.
- `\register caregiver DISPLAY_NAME` registers the sender as a caregiver account.
- `\whichroleami` shows the sender's registered role and linkage state.
- `\paircode` creates a patient-owned, one-time caregiver invitation code that expires after 15 minutes.
- `\link CODE` adds the patient to a caregiver account.
- `\relink CODE` replaces the caregiver's existing patient link.
- `\unlink` removes all links for a caregiver, or revokes every caregiver when sent by a patient.
- `\unlink PATIENT_ID` removes one patient from a caregiver account.
- `\dashboard` gives a paired caregiver a private dashboard link that expires after 30 minutes. The dashboard only exposes patients paired to that caregiver.
- `\clearhistory` displays a deletion warning.
- `\clearhistory confirm` lets a patient delete their structured chat-derived event history. Caregivers cannot delete patient history.
- `\accountcommands` displays the internal command list in chat.

The patient generates and shares the pairing code; there is no permanent shared password. Pairing and history management are private chat functions and are not exposed in the screening website or caregiver dashboard. Forward-slash variants remain parser-compatible for existing integrations but are not the documented interface.

## Current status

- Local dementia/MCI RAG pipeline is working from Markdown files under `data/mds/`.
- PDF and website ingestion write Markdown into `data/mds/`, then the CLI/runtime chunks and embeds that corpus into Chroma.
- `handle_incoming_message(message, sender_id, channel)` is the production entrypoint for Nanobot, Telegram, and WhatsApp. It handles role separation, internal commands, account pairing, structured event logging, and normal RAG routing.
- Safety and medication/diagnosis boundaries run before normal RAG and do not provide medication advice.
- Repeated memory-related concerns on separate days can trigger a gentle offer of the standalone screening exercise. Its link is sent only after the patient agrees.
- The standalone screening supports Traditional Chinese, Simplified Chinese, and English, with instructions, confirmation for every task, and a clickable 10:50 clock task.
- The caregiver dashboard remains separate from screening and reads privacy-filtered structured Telegram/WhatsApp events without displaying raw conversation text.
- Telegram/WhatsApp routing and the caregiver dashboard use the shared project event store at `data/private/events.jsonl` by default. This avoids Windows and WSL reading different home-directory event files.
- On first use, an existing legacy Nanobot event file under `~/.nanobot/data/private/events.jsonl` is copied into the shared project store when the shared file does not exist.
- Citation handling classifies evidence as internal, external, or unknown. Internal Markdown files, local paths, database IDs, and Chroma references remain available in result/debug metadata but are never shown in normal Telegram/WhatsApp answers. Approved public website citations can be displayed compactly when source display is enabled.

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

## Knowledge Sources

The bot must answer from the local database only. The database is built from PDFs in `data/pdfs/` and web pages listed in `data/websites.txt`, converted into Markdown under `data/mds/`, then chunked and embedded into Chroma.

### PDF Sources

The current PDF source files in `data/pdfs/` are:

- `chinese_foreward_executive_summary_dementia_guidelines.pdf`
- `who-eng-risk-dementia.pdf`
- `World-Alzheimer-Report-2023.pdf`
- `World-Alzheimer-Report-2023_Chinese.pdf`
- `World-Alzheimer-Report-2024.pdf`
- `World-Alzheimer-Report-2025.pdf`

Their generated top-level Markdown files in `data/mds/` are:

- `chinese_foreward_executive_summary_dementia_guidelines.md`
- `who-eng-risk-dementia.md`
- `World-Alzheimer-Report-2023.md`
- `World-Alzheimer-Report-2023_Chinese.md`
- `World-Alzheimer-Report-2024.md`
- `World-Alzheimer-Report-2025.md`

### Web Sources

The configured web source list is `data/websites.txt`. It currently includes:

Traditional Chinese:

- `https://www.jccpa.org.hk/`
- `https://www.smartpatient.ha.org.hk/smart-patient-web/disease-management/disease-information/disease/Dementia`
- `https://www3.ha.org.hk/cph/imh/tc/mental-health-info/4/1/2/anti-dementia-agents`
- `https://www.elderly.gov.hk/tc_chi/carers_corner/caring_skills/activityprogramforpersonswithdementia.html`

Simplified Chinese:

- `https://www.jccpa.org.hk/zh-hans/`
- `https://www.smartpatient.ha.org.hk/zh-cn/smart-patient-web/disease-management/disease-information/disease/Dementia`
- `https://www3.ha.org.hk/cph/imh/sc/about-us`
- `https://www.elderly.gov.hk/sc_chi/carers_corner/caring_skills/activityprogramforpersonswithdementia.html`

English:

- `https://www.jccpa.org.hk/en/`
- `https://www.smartpatient.ha.org.hk/en/smart-patient-web/disease-management/disease-information/disease/Dementia`
- `https://www3.ha.org.hk/cph/imh/en/about-us`
- `https://www.elderly.gov.hk/english/carers_corner/caring_skills/activityprogramforpersonswithdementia.html`
- `https://www.alzint.org/about/`

Website ingestion may skip pages that do not expose enough useful content after cleaning, especially landing pages or JavaScript-heavy pages. Crawled and converted web Markdown lives under `data/mds/web/`; the current local corpus contains 182 web Markdown files.

## Routing And Safety

`src/intent_router.py` classifies messages into:

- `knowledge_qa`
- `personal_memory`
- `reminder_request`
- `cognitive_activity`
- `emotional_support`
- `safety_sensitive`
- `medication_or_diagnosis`
- `unknown`

`src/agents/coordinator_agent.py` maps those intents into the five-agent architecture routes: safety, medical boundary, RAG QA, memory, routine, activity, supportive, or unknown. Safety and medication/diagnosis routes override normal RAG. Unknown messages do not call RAG and do not invent dementia knowledge.

## Medicine Identification

Medicine identification is deterministic and local:

- `data/medicine_aliases.json` stores canonical medicine names and aliases in English, Traditional Chinese, and Simplified Chinese.
- `src/meds/medicine_normalizer.py` matches aliases in user messages and returns canonical names, matched aliases, confidence, and source metadata.
- `src/safety/medication_guard.py` detects medication decision questions such as taking, stopping, repeating, mixing, or changing dose.
- Medication and diagnosis questions bypass normal RAG. The bot does not provide medication suitability, timing, dosage, stopping, starting, or change advice; it directs the user to a doctor, pharmacist, caregiver, or emergency services when appropriate.

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

- `CHROMA_DIR` - writable Chroma index directory. Defaults to `/home/aine/.cache/coa-agent/chroma/ling_rag`.
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
python tests/evaluation/run_rag_eval.py
```
