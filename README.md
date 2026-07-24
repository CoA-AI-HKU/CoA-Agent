# CoA-Agent dementia support system

A safety-aware, privacy-first dementia knowledge and daily-support assistant for general users, people with memory concerns, and caregivers. It combines deterministic routing, bounded agentic retrieval (A-RAG), medication and urgent-safety boundaries, structured event logging, and a caregiver dashboard.

## Project structure

- `backend/` — the single FastAPI application, transport-neutral chat services, and API routers for web and channel clients.
- `reminder_backend/` — reminder persistence, authentication, and route definitions included by the unified backend; it is not a separately deployed agent.
- `clients/` — thin transport adapters; Telegram is optional and contains no AI logic.
- `src/user/message_router.py` — production entrypoint, role routing, one structured event per message, and final output guard.
- `src/orchestrator.py` — coordinator and route-specific dispatch; it does not duplicate transport logging.
- `src/agents/` — managers, safety, screening, RAG evidence, simplification, and user-facing formatting.
- `src/rag/` — A-RAG retrieval tools, context tracking, route policy, evidence sufficiency, and internal traces.
- `src/pipeline/` — documents, chunking, embeddings, vector storage, prompts, language selection, and shared RAG runtime.
- `src/safety/` and `src/meds/` — medication boundaries, red flags, medicine aliases, and normalization.
- `src/metrics.py`, `src/insights.py`, and `src/dashboard.py` — privacy-filtered events and caregiver analytics.
- `src/ingest/` — PDF and website-to-Markdown ingestion.
- `scripts/` — demo-data and local A-RAG regression evaluation runners.
- `tests/` — unit, routing, safety, dashboard, leakage, A-RAG policy, evidence, trace, and end-to-end tests.
- `docs/` — integration and debugging guides, including [A-RAG integration](docs/arag_integration.md).
- `data/` — source documents, generated corpus, aliases, profiles, and private runtime state.
- `web/` — caregiver dashboard and screening assets.

See [Backend API](docs/backend_api.md) for the chat contract, authentication, startup, and adapter configuration.


## Telegram and WhatsApp internal commands

Telegram `/start` returns the normal self-introduction and registration prompt.
The undocumented `\initiate` alias invokes the same response for developer testing.
Administrative security-layer bypass should be configured with the immutable numeric
Telegram ID in `ADMIN_TELEGRAM_SENDER_IDS`. The optional
`ADMIN_TELEGRAM_USERNAMES=ainezhang` compatibility setting requires the gateway to
pass Telegram's verified username to the message handler.

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
\send_screening
\start_check
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
- `\send_screening` and `\start_check` let a paired caregiver send a consent-first, non-diagnostic check-in invitation. Links are issued only after the user agrees and only in private chat.

The patient generates and shares the pairing code; there is no permanent shared password. Pairing and history management are private chat functions and are not exposed in the screening website or caregiver dashboard. Forward-slash variants remain parser-compatible for existing integrations but are not the documented interface.

## Current status

- Local dementia/MCI RAG pipeline is working from Markdown files under `data/mds/`.
- Dementia QA and caregiver care-advice routes use bounded A-RAG with keyword search, semantic search, selected chunk reads, and evidence sufficiency checks.
- Safety, wandering, medication, unknown/out-of-scope, and caregiver-summary routes skip or strictly limit retrieval; safety boundaries control the final answer.
- PDF and website ingestion write Markdown into `data/mds/`, then the CLI/runtime chunks and embeds that corpus into Chroma.
- `handle_incoming_message(message, sender_id, channel)` is the production entrypoint for Nanobot, Telegram, and WhatsApp. It handles role separation, internal commands, account pairing, structured event logging, and normal RAG routing.
- Safety and medication/diagnosis boundaries run before normal RAG and do not provide medication advice.
- Repeated memory-related concerns on separate days can trigger a gentle offer of the standalone screening exercise. Its link is sent only after the patient agrees.
- The standalone screening supports Traditional Chinese, Simplified Chinese, and English, with instructions, confirmation for every task, and a clickable 10:50 clock task.
- The caregiver dashboard remains separate from screening and reads privacy-filtered structured Telegram/WhatsApp events without displaying raw conversation text.
- Telegram/WhatsApp routing and the caregiver dashboard use the shared project event store at `data/private/events.jsonl` by default. This avoids Windows and WSL reading different home-directory event files.
- On first use, an existing legacy Nanobot event file under `~/.nanobot/data/private/events.jsonl` is copied into the shared project store when the shared file does not exist.
- Citation handling classifies evidence as internal, external, or unknown. Internal Markdown files, local paths, database IDs, and Chroma references remain available in result/debug metadata but are never shown in normal Telegram/WhatsApp answers. Approved public website citations can be displayed compactly when source display is enabled.
- Retrieval traces remain internal and record the route, tools, queries, chunks read, evidence decision, failure state, and whether RAG supported the answer.

## Verification

```bash
python -m pytest -q
python scripts/run_arag_regression_eval.py
```

The fixed evaluation uses an in-memory corpus and the normal Python message router. It does not require Telegram, WhatsApp, Nanobot, network access, or a persistent vector index.

## Usage

1. Add PDFs under `data/pdfs/`.
2. Convert them to markdown with `src/pdf_ingest.py`.
3. Chunk the resulting document(s) with `src.pipeline.chunker.chunk_document` or `src.pipeline.chunker.chunk_documents`.
4. Generate embeddings using `src.pipeline.embedder.Embedder`.

### Convert PDFs into markdown

Run:

```bash
python -m src.ingest.pdf_ingest
```

This scans `data/pdfs/` recursively and writes `.md` output files into `data/mds/`, preserving subdirectory structure.

### Convert websites into markdown

Add one URL per line in `data/websites.txt`, then run:

```bash
python -m src.ingest.web_ingest
```

This fetches the page, strips common non-content HTML, converts headings/lists/links into readable markdown, and writes the result under `data/mds/web/<host>/...`. The normal CLI indexing path will then chunk and embed it with the rest of `data/mds/`.

By default, website ingestion crawls links under the starting URL path prefix. For example, starting from `https://www.jccpa.org.hk/en/about-dementia/` keeps the crawl focused under `/en/about-dementia/` instead of pulling in news, services, training, and other unrelated site sections. It skips obvious non-HTML assets and stops at bounded limits so large sites do not run forever.

You can also pass URLs directly, use another list file, or disable crawling:

```bash
python -m src.ingest.web_ingest https://example.org/article
python -m src.ingest.web_ingest --url-file urls.txt --overwrite
python -m src.ingest.web_ingest --no-crawl https://example.org/article
python -m src.ingest.web_ingest --max-pages-per-site 250 --max-depth 6
python -m src.ingest.web_ingest --crawl-scope same-site
python -m src.ingest.web_ingest --delay 0.5 --timeout 30
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

`src/agents/coordinator_agent.py` maps those intents into safety, medical boundary, screening/memory concern, caregiver guidance, RAG QA, memory, routine, activity, supportive, or unknown routes. Safety and medication/diagnosis routes override A-RAG. Unknown messages do not retrieve dementia documents or invent dementia relevance. See `docs/arag_integration.md` for the complete policy.

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

The CLI requires a real embedding backend by default. Install `sentence-transformers` with the documented `all-MiniLM-L6-v2` model available, or configure the supported OpenAI-compatible embedding provider. Dummy embeddings are test-only and require explicit `EMBEDDER_PROVIDER=dummy` or `RAG_ALLOW_DUMMY=true`.

For answer-mode debugging:

```bash
python -m src.cli --embedder-provider dummy --retrieve-top-k 8 --answer-top-k 3 --show-sources --debug-rag
```

`--fallback-to-top-chunk` is only for retrieval debugging. It bypasses answer synthesis and should not be used for final Telegram/Nanobot replies.

The assistant detects the user's input language and answers in one language: Traditional Chinese (`zh-Hant`), Simplified Chinese (`zh-Hans`), or English (`en`). Retrieved sources may be in any of those languages, but the final answer is constrained to the detected answer language. Set `RAG_ANSWER_LANGUAGE=zh-Hant|zh-Hans|en` to override auto-detection.

For production cross-language retrieval, use a real multilingual embedding model through `EMBEDDER_MODEL`. The deterministic `dummy` embedder is useful for local tests, but it is lexical and weak when the query and source are in different languages.

Environment variables (optional):

- `RAG_ENV=production` — enables strict startup validation for embeddings, model loading, index identity, and LLM fallback.
- `EMBEDDER_PROVIDER` — defaults to `auto`; use `dummy` only explicitly for tests.
- `EMBEDDER_MODEL` — defaults to the existing documented `all-MiniLM-L6-v2`.
- `RAG_ALLOW_EXTRACTIVE_FALLBACK=true` — explicitly permits generation without a configured LLM.
- `CHROMA_DIR` - writable Chroma index directory. Defaults to `data/private/chroma/ling_rag` under the project root.
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
