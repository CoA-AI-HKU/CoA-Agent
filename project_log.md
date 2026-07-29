## Project Log

Research-based timeline and review,

### Week 1

Initial project framing and technical exploration.

- Framed CoA-Agent as a dementia-support RAG chatbot for Traditional Chinese-speaking older adults and caregivers, grounded in a controlled knowledge base rather than open model knowledge.
- Explored the RAG pipeline (ingestion, chunking, embedding, vector retrieval, LLM generation), Nanobot as the agent framework, and MCP to connect the dementia RAG module to Nanobot.
- Chose Telegram as the first messaging interface; began building a local dementia-care knowledge base from Markdown files.
- Considered future support for caregivers, reminders, personal memory, and daily independence.
- Weighed positioning (encyclopedia vs. patient companion vs. caregiver assistant vs. broader daily-support system); settled on a safety-aware support assistant for older adults, people with cognitive concerns, and caregivers.

### Week 2 (6/22-6/26)

Literature review: dementia support, older-adult chatbot design, RAG systems, caregiver needs, and HCI/CHI framing — suggested the system should support safety, reassurance, caregiver involvement, and daily routines, not just answer facts.

#### 6/26

Pipeline: data → chunking → embedder → Chroma → LLM (DeepSeek Flash/V4).

Completed:
- Connected Nanobot to Telegram; messages received and answered through the gateway.
- Integrated the dementia RAG module into Nanobot via an MCP server.
- Tested Traditional Chinese dementia questions; confirmed answers draw from the ingested RAG database, not live web search.
- Ingested web-derived dementia resources into local Markdown.
- Discussed future cloud deployment to avoid local VPN/WSL networking instability.

Status: Telegram + Nanobot + MCP tool registration work; Telegram answers are promising; CLI answer quality is inconsistent.

Limitations: unreliable on difficult/nuanced questions; must run on a live personal computer; definition-like answers only; limited emotional support; no saved conversations/personal memory/long-term context; no caregiver/user role separation; no dashboard.

To do: consider cloud deployment, improve answer quality, add safety/medication boundaries, begin caregiver support design.

### Week 3 (6/29-7/3)

RAG research (OneNote): RAG architectures, agentic/hybrid RAG, evidence-sufficiency checking, HCI/CHI innovation angles, future image/link parsing. TBD: deeper research on each.

- **Avatar**: selected a youthful, culturally familiar, humanlike avatar (not elderly or childlike), based on prior research on older adults' virtual-agent preferences — meant to read as "helpful companion," not doctor/authority/patient. Provisional pending participatory testing.
- **Image parsing**: discussed future OCR support; medication photos should be framed as label-reading/safety triage, not pill identification or medical advice.
- **Cloud server**: discussed HKU Linux server options; Colab useful for experiments, not 24/7 deployment. TBD: figure out Colab.
- **WhatsApp**: explored linked-device connection; more complex than Telegram but valuable since older adults/caregivers may already use it. Current bridge approach fine for prototyping; a formal WhatsApp Business API route may be needed later.

#### 7/2

Completed:
- Resolved CLI/Telegram pipeline mismatch — both now use the same RAG answer pipeline.
- Implemented an intent router to separate dementia knowledge from medication, diagnosis, safety, emotional-support, reminder, memory, and activity questions.
- Parsed new websites into the knowledge base; added a safety layer and a medicine layer.
- Medication questions now route to a boundary response instead of direct advice; safety-sensitive questions (e.g. wandering) get priority.

Design shift: from "a dementia RAG chatbot" to "a safety-aware daily support and caregiver-aware assistant."

### Week 4
#### 7/8

Completed:
- Cut dementia-assumption bias: the bot no longer implies the user has dementia unless they say so, treats forgetfulness as a general memory concern with many possible causes (stress, sleep, mood, medication, physical health, cognitive change), avoids "this is part of your disease" framing, and never calls out repetition in a way that could shame the user.
- Fixed over-citation of sources.
- Added the cognitive-concern-monitoring concept (passively logging signals: memory concern, orientation confusion, medication uncertainty, wandering/getting lost, repeated question, caregiver-reported worsening) — explicitly non-diagnostic, with alerts recommending caregiver follow-up or professional assessment only when appropriate.
- Added/planned output guards against exposing `.md` filenames, citations, RAG internals, MCP tool names, or debug text; shortened and cleaned up response style.

#### 7/9

Completed:
- Separated user mode (simple, calm, non-stigmatizing) from caregiver mode (summaries, alerts, future setup) — unknown users are never assumed to be patients. Caregiver mode planned to support `/summary`, `/alerts`, `/start_check`, and reminder/routine setup.
- Integrated a privacy-first caregiver dashboard driven by structured events, not raw conversations — interaction count, mood (if collected), activity/cognitive records, intent distribution, medication uncertainty, safety alerts, caregiver recommendations. Connected cognitive-concern signals to dashboard alerts.
- Added structured, privacy-preserving event logging.
- Debugged MCP startup failures — caused by missing Python support modules (user registry, user memory placeholder, mode info, message router), not Nanobot itself.

Status: Telegram works; WhatsApp receives messages but bridge stability needs monitoring; MCP + RAG integration works once imports are fixed; role separation, dashboard, and passive cognitive-concern monitoring are all in place — the system has moved toward a privacy-first caregiver support model.

Limitations: answer quality needs regular testing; possible leakage of sources/tool names/internals without full output-guard enforcement; RAG and MCP still fragile around missing imports and Chroma/SQLite paths; dashboard is local/prototype only (no auth, HTTPS, access control, or consent flow); caregiver-triggered cognitive check designed but not implemented; personal memory/reminders still placeholder-level; no formal user/expert evaluation yet.

To do: stabilize end-to-end; build a 20-question test set; confirm no raw conversations in dashboard logs and no source/tool/debug leakage; implement the caregiver-triggered cognitive check and connect it to the dashboard; prepare the PI demo; later, add auth/HTTPS/caregiver-user linking/data deletion for online deployment.

**Direction at this point**: a safety-aware, RAG-grounded daily-independence and caregiver-support assistant for older adults, people with cognitive concerns, and caregivers — combining Traditional Chinese dementia Q&A, Telegram (WhatsApp prototype), intent routing, medication/safety boundaries, reduced dementia-assumption bias, user/caregiver mode separation, privacy-preserving logging, and a caregiver dashboard with passive cognitive-concern monitoring.

Next milestone: memory concern → neutral supportive reply → non-diagnostic dashboard alert (no raw text) → caregiver-initiated cognitive check → result shown as a follow-up suggestion, not a diagnosis.

### A-RAG production hardening (2026-07-15)

Validated the lightweight A-RAG layer inside the production message path.

Implemented:

- End-to-end scenarios for dementia QA, caregiver repeated-question guidance, medication decisions, medication uncertainty, wandering, neutral memory concerns, out-of-scope requests, and insufficient evidence.
- Route-policy, evidence-sufficiency, retrieval-trace, output-leakage, dashboard-compatibility, and duplicate-event regression tests.
- Bounded caregiver-guidance retrieval with practical, non-diagnostic final wording.
- Safety priority fixes, including medication uncertainty taking precedence over misleading completion substrings.
- One interaction-event owner in `message_router`; the orchestrator no longer creates duplicate events.
- Stronger output guards for retrieval tools, source labels, vector/index terms, debug text, and local paths.
- Privacy validation confirming dashboard events contain only allow-listed structured fields — no raw messages, answers, chunks, or traces.
- Local fixed-scenario runner at `scripts/run_arag_regression_eval.py`.
- A-RAG documentation at `docs/arag_integration.md`; updated repository structure in `README.md`.
- Compatibility repairs for account-command display, caregiver linking, medicine aliases, local Chroma paths, ingestion imports, and language-specific safety responses.

Verification: full `pytest` suite passes; the local A-RAG regression runner passes without Telegram, WhatsApp, Nanobot, network access, or a persistent vector index.

Documentation rule for future revisions:

- Record every material code, behavior, safety, privacy, test, or structure change in `project_log.md`.
- Update `README.md` in the same revision whenever commands, file structure, entrypoints, architecture, capabilities, or setup instructions change.

---

## Frontend, Privacy & QR Code Access (2026-07-15)

Designed and implemented a public-facing frontend entry point.

Implemented:

- A clean, mobile-friendly landing page (`index.html`) with a prominent "Open in Telegram" button.
- A bilingual (English + Traditional Chinese) Privacy Policy & Consent page (`privacy.html`): medical disclaimer, data-collection disclosure (only anonymous metadata stored, raw conversation text never saved), user rights (withdrawal, deletion, no profiling), and a mandatory 3-checkbox consent form.
- JS logic disabling the Telegram button until all three consent checkboxes are ticked.
- A QR code pipeline pointing to the landing page, intended for physical distribution (posters, flyers).
- Local dev server (`python -m http.server`) for testing the full flow (scan → read policy → consent → jump to Telegram).

Testing:

- Validated the full journey end-to-end, including on a mobile phone over Personal Hotspot (to bypass HKU Wi-Fi AP isolation, which blocks device-to-device `localhost` testing — confirms a cloud-hosted public URL is needed for production).
- Compared landing-page QR vs. a direct Telegram QR; landing-page QR is the correct choice for ethical onboarding (consent-first).

Outcome: privacy-first, ethics-compliant onboarding flow committed under `/frontend`; ready to deploy once pointed at a permanent public URL.

## LightRAG Integration Testing & Evaluation (2026-07-15)

Tested the LightRAG framework (HKU Nanobot team's RAG solution) as a potential pipeline upgrade.

- Reindexed `World-Alzheimer-Report-2023.md` from scratch. Retrieval quality is strong, but initial indexing is slow even for a moderate document.
- Hit an `Embedding dimension mismatch` (3840 not evenly divisible by 1024) during storage flush.
- Root cause: `.env` had `EMBEDDING_DIM=1024`, but the `all-minilm` embedding model actually produces 384. Fixed by setting `EMBEDDING_DIM=384`, deleting `rag_storage`, and reindexing.

Status: promising retrieval, but indexing time is a real concern for production document updates.

Open questions: how to speed up indexing (cheaper LLM for entity extraction, parallelization, or just accept the trade-off); embedding model/dimension must be documented explicitly to avoid repeat config errors.

### Dashboard, LightRAG & Frontend Debugging (2026-07-16)

#### Dashboard & Logging Fixes
- Resolved Dashboard `0` interaction count — Streamlit was loading a stale `metrics.py` from `C:\Users\user\.nanobot\` instead of the project `src/` copy. Fixed by syncing `metrics.py`/`insights.py`; count immediately updated to `22`.
- Added `log_event` calls in `memory_routine_agent.py` so all test interactions write to `events.jsonl`.
- Added a Cognitive Signals traffic light (🟢/🟡/🔴) to the dashboard based on concern-signal counts.

#### LightRAG Fixes
- Fixed the `Embedding dimension mismatch` (3840/1024) by correcting `EMBEDDING_DIM=384` to match Ollama's `all-minilm`.
- Confirmed switching LLM models (Ollama ↔ DeepSeek) doesn't require reindexing as long as the embedding model is unchanged.

#### Frontend & Network (2026-07-17)
- Deployed the frontend on GitHub — now 24/7 available, QR code unaffected by Wi-Fi AP isolation.
- Next: deploy the backend (Telegram bot + LightRAG) to a cloud server so the bot doesn't depend on anyone's local machine being on.

#### 2026-07-23

### Reminder System Build-Out and Intent Router Restructuring (2026-07-27)

- Built the initial reminder system (`chat_reminders.py`, `database.py`, `scheduler.py`) — time parsing, persistence, delivery — wired into the coordinator and memory/routine agents, with initial tests. Fixed an early timezone bug (parsing/matching against the wrong wall-clock time on a UTC-clocked server).
- Built, then removed, a standalone reminders REST API and caregiver-dashboard HTML (`src/reminders/app.py`, `auth.py`, `caregiver_dashboard.html`) in favor of chat-only reminders — the design kept ever since: no reminder REST API, set entirely by talking to the bot.
- Restructured intent routing: added a semantic intent router alongside the existing keyword-based one, with new routing tests.
- Cleaned up abandoned experimental backend scaffolding (`backend/agents/`, `backend/database/`, `clients/`, etc.) and stale document backups.

### Reminder Reliability, Web Voice Chat, and Firebase Accounts (2026-07-29)

#### Reminders

- Traced why production reminders were silently failing to fire: the delivery scheduler was never started, its systemd unit had no `TELEGRAM_BOT_TOKEN`, and delivery depended on a registry lookup that failed for unregistered accounts. Delivery now captures the chat ID directly at creation time instead of reconstructing it later, so it no longer depends on registration.
- Added structured, correlated logging across the full reminder pipeline (message received → intent detected → parsed → persisted → scheduler registered → triggered → delivered) so future production issues are diagnosable from logs alone.
- Rewrote the time parser to handle Chinese-numeral hours/minutes, `午後`/`午前`, the `鐘` filler word, and trailing confirmation phrases (`好嗎`/`可以嗎`) that were leaking into reminder text or producing wrong times.
- Added an AM/PM clarification flow: a bare hour with no marker (e.g. "5點") now asks instead of silently guessing morning.
- Added a same-turn correction flow: a follow-up like "抱歉，我意思係下午" now updates the just-created reminder instead of being dropped as an unrelated reply.
- Added a DeepSeek fallback for messages the deterministic parser can't handle, used only when the fast path fails or is ambiguous, with the same "never guess" discipline as the rest of the safety design.

#### Web Voice Chat

- Diagnosed the actual production bug: nginx serves `web/index.html`, but earlier fixes had been applied to a stale duplicate at the repo root. Consolidated into one canonical file, with the root copy now a symlink so the two can't drift apart again.
- Fixed dead API calls in the page (reminders, old auth, emergency) that either 404'd or hit the wrong endpoint shape; reminders/emergency now say plainly what is and isn't available instead of failing silently or confusingly.
- Verified the core voice/text chat loop end-to-end against the real backend.

#### Firebase Accounts

- Replaced a planned local password system with Firebase Authentication (phone SMS + email/password), including account linking so one person can use either method for the same account.
- Built server-side ID token verification and a contacts API (`/api/account/contacts`), stored separately from the reminders database and keyed to Firebase's user ID.
- Updated nginx to proxy the new endpoints; the backend reports "not configured" rather than failing until the Firebase service account key is deployed.

Outcome: reminders now work across the phrasings that were actually breaking in production, the web chat page matches what's really deployed, and there is a working path to real web-channel accounts, pending only the service account key being placed on the droplet.
