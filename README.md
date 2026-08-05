# CoA-Agent dementia support system

A safety-aware, privacy-first daily-support assistant for older adults, people with memory concerns, and their caregivers — available both as a Telegram bot and as a WCAG 2.1 AA–compliant web app. It combines deterministic + LLM intent routing, bounded agentic retrieval (A-RAG) over a curated dementia knowledge base, medication and urgent-safety boundaries, reminders, live weather alerts, and privacy-filtered caregiver tools.

Live: https://104-131-176-48.sslip.io/

## Project structure

- `backend/` — FastAPI app (`backend.main:app`). `backend/api/` holds the web account/auth, chat, and caregiver routers; `backend/services/` holds Firebase auth, account profiles/permissions, and the conversation service shared with Telegram.
- `web/` — the web app: `index.html` (single-file SPA — chat, voice, account, caregiver mode) and `privacy.html` (consent/policy page), both symlinked to the repo root for deployment. `dashboard.html`/`screening.html` are the older privacy-filtered caregiver dashboard and standalone cognitive screening exercise.
- `src/user/message_router.py` — production entrypoint for Telegram/WhatsApp: role routing, internal commands, structured event logging, output guarding.
- `src/orchestrator.py` — coordinator and route-specific dispatch for the shared conversation pipeline (used by both Telegram and the web app).
- `src/intent_router.py` / `src/agents/semantic_intent_router.py` — deterministic keyword/regex gates first (safety, medication, reminder cancel), then an LLM-based semantic router for everything else.
- `src/agents/` — per-route agents: safety, screening, RAG evidence, reminders/routines, weather, general chat, caregiver guidance, response formatting.
- `src/reminders/` — reminder persistence, chat-triggered creation and cancellation, and the delivery scheduler. No reminder REST API — reminders are set and cancelled entirely by talking to the bot.
- `src/weather/` — Hong Kong Observatory integration: on-demand weather Q&A plus a proactive scheduler that Telegram-alerts patients on extreme heat (>34°C) or an active Rainstorm Warning Signal.
- `src/user/` — per-user state: registry, session/monitoring preferences, conversation flags (safety / cognitive-decline signals, 14-day retention, no raw text stored), pending multi-turn flows.
- `src/rag/`, `src/pipeline/` — A-RAG retrieval tools, route policy, evidence sufficiency, chunking/embedding/vector storage, prompts.
- `src/safety/`, `src/meds/` — medication boundaries, red-flag detection, medicine alias normalization.
- `src/ingest/` — PDF and website-to-Markdown ingestion.
- `data/` — source documents, generated corpus, aliases, and private runtime state (JSON files, SQLite DBs).
- `tests/` — unit, routing, safety, accessibility, weather, web-account API, and end-to-end tests.
- `docs/` — see [Backend API](docs/backend_api.md), [web voice chat](docs/web_voice_chat.md), [A-RAG integration](docs/arag_integration.md).

## Web app

Firebase Authentication (phone SMS or email/password) backs four roles — `companion` (patient), `caregiver`, `developer`, `admin` — with a `ROLE_PERMISSIONS` table in `backend/services/account_profiles.py` gating each API. Caregivers can link multiple patients and, per patient, manage contacts and toggle which conversation-flag categories (safety / cognitive decline) get monitored — framed as a joint decision with the patient, both on by default.

Accessibility: the site is built to WCAG 2.1 AA (4.5:1 text contrast, 3:1 UI-component contrast, skip link, visible focus, semantic headings, accessible custom dialogs replacing native `confirm()`/`prompt()`, typed-phrase confirmation for account deletion). A conformance mark appears on the consent page.

Voice input uses the browser's own Speech Recognition API. Low-confidence transcripts (below a 0.4 confidence threshold, when the browser reports one) prompt the user to repeat instead of being silently submitted, and a spurious "no speech detected" error is retried once automatically before surfacing to the user.

See [docs/web_voice_chat.md](docs/web_voice_chat.md) and [docs/backend_api.md](docs/backend_api.md) for the chat contract, auth, and deployment notes.

## Telegram internal commands

Telegram `/start` returns the normal self-introduction and registration prompt. The undocumented `\initiate` alias invokes the same response for developer testing. Administrative security-layer bypass should be configured with the immutable numeric Telegram ID in `ADMIN_TELEGRAM_SENDER_IDS`. The optional `ADMIN_TELEGRAM_USERNAMES=ainezhang` compatibility setting requires the gateway to pass Telegram's verified username to the message handler.

These commands are handled inside the message router when sent through Telegram or WhatsApp, and intentionally begin with a backslash so Telegram does not treat them as native bot-menu commands.

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

- `\register patient|caregiver DISPLAY_NAME` registers the sender in that role.
- `\whichroleami` shows the sender's registered role and linkage state.
- `\paircode` creates a patient-owned, one-time caregiver invitation code that expires after 15 minutes; `\link CODE` / `\relink CODE` consume it.
- `\unlink` removes all links for a caregiver, or revokes every caregiver when sent by a patient; `\unlink PATIENT_ID` removes one patient from a caregiver account.
- `\dashboard` gives a paired caregiver a private dashboard link that expires after 30 minutes, scoped to their own patients.
- `\clearhistory` warns, `\clearhistory confirm` lets a patient delete their structured event history (caregivers cannot delete patient history).
- `\accountcommands` lists these commands in chat.
- `\send_screening` / `\start_check` let a paired caregiver send a consent-first, non-diagnostic check-in invitation.

Reminders and weather are not slash commands — just talk to the bot naturally ("remind me to take my pills at 8pm", "cancel my reminders", "will it rain today?"). Forward-slash variants remain parser-compatible for existing integrations but are not the documented interface.

## Routing and safety

`src/intent_router.py` runs hard deterministic gates first — urgent safety, medication/diagnosis, reminder cancellation — before falling back to `src/agents/semantic_intent_router.py`, an LLM-based router explicitly excluded from safety-critical intents. `src/agents/coordinator_agent.py` maps the resolved intent to a route (safety, medical boundary, screening, RAG QA, reminder/routine/cancel, weather, activity, caregiver guidance, supportive, unknown). Safety and medication/diagnosis routes always override retrieval; unknown messages never invent dementia relevance. See `docs/arag_integration.md` for the full A-RAG policy.

## Medicine identification

Deterministic and local: `data/medicine_aliases.json` stores canonical medicine names/aliases (English, Traditional/Simplified Chinese); `src/meds/medicine_normalizer.py` matches them in messages; `src/safety/medication_guard.py` detects medication-decision questions (taking, stopping, repeating, mixing, changing dose). These bypass normal RAG — the bot never gives suitability/dosage/timing advice, only directs to a doctor, pharmacist, caregiver, or emergency services.

## Knowledge base

The bot answers dementia questions from a local, curated database only — never open web search. PDFs under `data/pdfs/` and web pages listed in `data/websites.txt` are converted to Markdown under `data/mds/` (`python -m src.ingest.pdf_ingest`, `python -m src.ingest.web_ingest`), then chunked (`src.pipeline.chunker`) and embedded (`src.pipeline.embedder`) into Chroma. Website ingestion crawls within the starting URL's path prefix by default; see `python -m src.ingest.web_ingest --help`-style flags (`--no-crawl`, `--url-file`, `--max-pages-per-site`, `--crawl-scope`) for tuning.

Current sources: six PDF reports (WHO dementia risk guidance, World Alzheimer Reports 2023–2025, a Traditional Chinese executive summary) and ~15 Traditional Chinese / Simplified Chinese / English web pages from JCCPA, Hospital Authority Smart Patient, and the Social Welfare Department, crawled into ~180 Markdown files under `data/mds/web/`.

The assistant detects the input language and answers in exactly one of Traditional Chinese (`zh-Hant`), Simplified Chinese (`zh-Hans`), or English — regardless of what language the retrieved sources are in. Override with `RAG_ANSWER_LANGUAGE`.

## CLI

```bash
python -m src.cli
```

Loads `data/mds/`, indexes into the RAG agent, and starts an interactive prompt. Requires a real embedding backend by default (`sentence-transformers`, model `all-MiniLM-L6-v2`, or an OpenAI-compatible provider); dummy embeddings need explicit `EMBEDDER_PROVIDER=dummy` or `RAG_ALLOW_DUMMY=true` and are test-only — lexical matching only, weak across languages.

```bash
python -m src.cli --embedder-provider dummy --retrieve-top-k 8 --answer-top-k 3 --show-sources --debug-rag
```

`--fallback-to-top-chunk` is retrieval-debugging only; do not use it for final replies.

## Verification

```bash
python -m pytest -q
python scripts/run_arag_regression_eval.py
```

The regression runner uses an in-memory corpus and the normal message router — no Telegram, WhatsApp, network access, or persistent vector index required.

## Key environment variables

| Variable | Purpose |
|---|---|
| `RAG_ENV=production` | strict startup validation for embeddings, model loading, index identity, LLM fallback |
| `EMBEDDER_PROVIDER` / `EMBEDDER_MODEL` | default `auto` / `all-MiniLM-L6-v2`; `dummy` only for tests |
| `RAG_ALLOW_EXTRACTIVE_FALLBACK=true` | permits generation without a configured LLM |
| `CHROMA_DIR` | writable Chroma index directory (default `data/private/chroma/ling_rag`) |
| `DEEPSEEK_URL` / `DEEPSEEK_API_KEY` | remote LLM endpoint; without `DEEPSEEK_URL` the CLI prints the prompt and returns "I don't know." |
| `TELEGRAM_BOT_TOKEN` | Telegram gateway and reminder/weather-alert delivery |
| `ADMIN_TELEGRAM_SENDER_IDS` / `ADMIN_TELEGRAM_USERNAMES` | admin security-layer bypass |
| `REMINDER_SCHEDULER_AUTOSTART` / `WEATHER_SCHEDULER_AUTOSTART` | start the respective background schedulers with the backend |
| `MONITORING_PREFERENCES_PATH` | override path for per-user conversation-flag category toggles (tests) |

## Notes

- PDF extraction supports `PyMuPDF` first, falling back to `pypdf`.
- Chunking is paragraph-aware (`chunk_size=1000`, `chunk_overlap=200`).
- Citation handling classifies evidence as internal, external, or unknown; internal paths/IDs/tool names are never shown in normal answers.
- Retrieval traces (route, tools, queries, chunks read, evidence decision) stay internal for debugging.

See `docs/nanobot_integration.md` for the Nanobot/MCP config, and `docs/rag_debugging.md` plus `python tests/evaluation/run_rag_eval.py` for retrieval/answer debugging.
