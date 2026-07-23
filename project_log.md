## Project Log

Research-based timeline and review,

### Week 1

Initial project framing and technical exploration.

The project began as a dementia-support RAG chatbot for answering dementia-related questions and supporting older adults or caregivers in Traditional Chinese. Early work focused on understanding how a RAG system could support dementia care without relying on uncontrolled model knowledge.

Early exploration included:

Understanding the RAG pipeline: data ingestion, chunking, embedding, vector database retrieval, and LLM-based answer generation.
Exploring Nanobot as the agent framework.
Exploring MCP as a way to connect the dementia RAG module to Nanobot.
Choosing Telegram as the first messaging interface.
Building a local dementia-care knowledge base from Markdown files.
Considering how the system could later support caregivers, reminders, personal memory, and daily independence.

Initial design questions included whether the project should be a dementia encyclopedia, a patient companion, a caregiver assistant, or a broader daily support system. The project direction gradually shifted toward a safety-aware support assistant for older adults, people with cognitive concerns, and caregivers.

### Week 2 (6/22-6/26)

Literature reviews: useful information:

Reviewed background materials on dementia support, older-adult chatbot design, RAG systems, caregiver needs, and possible HCI/CHI research framing. Early research suggested that the system should not only answer factual questions, but should also support safety, reassurance, caregiver involvement, and daily routines.

#### 6/26

Successfully produced functioning Nanobot connected to Telegram.

Process:

data -> chunking -> embedder -> Chroma DB processing -> LLM factoring

Currently based on DeepSeek Flash/V4.

Completed work:

Connected Nanobot to Telegram and confirmed that Telegram messages can be received and answered through the Nanobot gateway.
Integrated the dementia RAG module into Nanobot through an MCP server.
Tested the Telegram-facing bot with Traditional Chinese dementia-related questions.
Verified that Telegram responses can draw from the pre-ingested dementia RAG database rather than live web search.
Ingested web-derived dementia resources into local Markdown files under the RAG knowledge base.
Discussed future cloud deployment to avoid local VPN and WSL networking instability.

Current status:

Telegram + Nanobot connection works.
RAG MCP tool registration works.
Telegram answers are promising.
CLI answer quality remains inconsistent and requires debugging.
Limitations
Cannot yet answer difficult or nuanced questions reliably.
Must be run through Nanobot on a personal computer while the computer is live.
Can only give definition-like answers at this stage.
Human-like emotional support is still limited.
Cannot yet save conversations, personal memory, or long-term user context.
No caregiver/user role separation yet.
No dashboard or structured monitoring yet.


To do
Consider cloud implementation.
Improve answer quality.
Add safety and medication boundaries.
Begin designing caregiver support features.

### Week 3 (6/29-7/3)

RAG Research: uploaded on OneNote.

Research focused on:

Different RAG architectures.
Agentic RAG and hybrid RAG.
Evidence sufficiency checking.
Innovative points for an HCI/CHI paper.
Image parsing and link parsing for future input.
How to make the system safer and more useful than a simple Q&A bot.

TBD: Research on RAG, research on innovative points, research on image parsing/link parsing on input.

Avatar:

Based on prior work on older adults’ virtual-agent preferences, we selected a youthful adult, culturally familiar, humanlike avatar rather than an elderly or childlike figure. This decision is provisional and should be validated with people living with dementia and caregivers in future participatory testing. The appearance should suggest “helpful companion” rather than “doctor,” “caregiver authority,” or “elderly patient.”

Image parsing:

Discussed future image/OCR support.
Medication photo support should be framed as label reading and safety triage, not pill identification or medical advice.

Cloud-server:

Discussed possible cloud deployment.
Considered HKU Linux server options.
Colab may be useful for experiments, but not for stable 24/7 bot deployment.

TBD: figure out Colab.

Connect to WhatsApp:

Explored WhatsApp linked-device connection.
Identified that WhatsApp setup is more complex than Telegram.
WhatsApp is useful for future deployment because older adults and caregivers may already use it.
Current WhatsApp bridge approach is suitable for prototype testing, but a more formal WhatsApp Business API route may be needed later.
#### 7/2

Completed work:

CLI/Telegram mismatch has been resolved.
Telegram and CLI now use the same or consistent RAG answer pipeline.
Intent recognizer has been implemented.
New websites were parsed into the dementia knowledge base.
Added intent router to differentiate between different questions.
Improved safety with a safety layer and medicine layer.
Introduction of paper done.

New capabilities:

The bot can better classify user questions by intent.
The system can separate dementia knowledge questions from medication, diagnosis, safety, emotional support, reminder, memory, and activity-related questions.
Medication questions are routed to a boundary response rather than direct advice.
Safety-sensitive questions, such as wandering, are treated with higher priority.

Important design shift:

The project moved from “a dementia RAG chatbot” toward “a safety-aware daily support and caregiver-aware assistant.”

### Week 4
#### 7/8

Completed work:

Cut dementia bias and assumption.
Fixed issue of over-citations of sources.
Added dementia screening module concept, later reframed as cognitive concern monitoring.
Added instructions so the model should not assume every user has dementia.
Added or planned output guards to avoid exposing .md filenames, citations, RAG internals, MCP tool names, and debug text.
Improved response style so user-facing answers should be shorter, clearer, and less like database reports.
Designed passive cognitive concern monitoring.

Bias and assumption work:

The bot should not say or imply that the user has dementia unless the user explicitly says so.
If a user says they are forgetful, the bot should treat it as a general memory concern.
The bot should mention that forgetfulness can have many causes, such as stress, sleep, mood, medication, physical health, or cognitive change.
The bot should avoid saying “this is part of your disease.”
The bot should not point out repeated questions in a way that could shame the user.

Cognitive concern monitoring:

The project added the concept of passively logging cognitive concern signals.
Signals include:
memory concern
orientation confusion
medication uncertainty
wandering or getting lost
repeated question
caregiver-reported worsening
These signals are not diagnoses.
Alerts should say “this is not diagnosis” and recommend caregiver follow-up or professional assessment only when appropriate.
#### 7/9

Completed work:

Integrated dashboard module.
Fixed over-citation issue.
Separated user mode and caregiver mode.
Added different user interfaces for user-facing and caregiver-facing interactions.
Added caregiver dashboard integration.
Added structured event logging for privacy-preserving monitoring.
Connected cognitive concern signals to dashboard alerts.
Debugged MCP startup failures caused by missing support modules.
Added or planned missing user-support modules:
user registry
user memory placeholder
mode information
message router
Confirmed that MCP failures were caused by missing Python modules rather than Nanobot itself.

Caregiver/user mode separation:

User mode is for simple, calm, non-stigmatizing support.
Caregiver mode is for summaries, alerts, and future setup/configuration.
Unknown users should not be assumed to be patients or people with dementia.
Caregiver mode can eventually support commands such as:
/summary
/alerts
/start_check
reminder or routine setup

Dashboard:

Integrated a privacy-first caregiver dashboard.
The dashboard shows trends and summaries without showing raw conversations.
It can display:
interaction count
mood records if explicitly collected
simple activity/cognitive records
intent distribution
medication uncertainty
safety alerts
caregiver recommendations
The dashboard uses structured events rather than raw chat content.
The dashboard supports the project’s caregiver-facing component.

Current status:

Telegram connection works.
WhatsApp has been tested and can receive messages, though bridge stability still needs monitoring.
Nanobot + MCP + dementia RAG integration works when imports and missing modules are fixed.
Role separation exists.
Dashboard integration exists.
Passive cognitive concern monitoring works.
Structured event logging can support caregiver alerts.
The system has moved toward a privacy-first caregiver support model.


Limitations
User-facing answer quality still needs regular testing.
The system may still occasionally leak sources, tool names, or internal implementation details unless final output guards fully enforce cleanup.
RAG stability still needs improvement.
MCP is fragile when imports reference files that do not exist.
Chroma/SQLite path and timeout issues may still need cleanup.
Dashboard is currently a local/prototype feature, not a secure online deployment.
There is no full authentication, HTTPS, caregiver access control, or consent flow yet.
The caregiver-triggered cognitive check is designed but not fully implemented.
Personal memory and reminders are still limited or placeholder-level.
No formal user or expert evaluation has been completed yet.


To do
Stabilize the full end-to-end system.
Build and run a 20-question test set.
Confirm no raw conversations are stored in dashboard logs.
Confirm no sources, .md files, MCP names, RAG internals, or debug text appear in user-facing answers.
Implement caregiver-triggered simple cognitive check.
Connect cognitive check results to dashboard.
Prepare PI demo.
Later, prepare online deployment with authentication, HTTPS, caregiver-user linking, and data deletion/export policy.
Current Project Direction

The project is now best described as:

A safety-aware, RAG-grounded daily independence and caregiver-support assistant for older adults, people with cognitive concerns, and caregivers.

Core abilities implemented or partially implemented:

Traditional Chinese dementia-care Q&A.
Telegram interface.
WhatsApp prototype connection.
RAG-based local knowledge retrieval.
Intent routing.
Medication and diagnosis safety boundary.
Safety-sensitive response handling.
Reduced dementia-assumption bias.
User mode and caregiver mode separation.
Privacy-preserving structured event logging.
Caregiver dashboard.
Passive cognitive concern monitoring.
Dashboard alerts for caregiver follow-up.

Next major milestone:

User expresses memory concern
→ bot responds neutrally and supportively
→ event is logged without raw text
→ caregiver dashboard shows non-diagnostic alert
→ caregiver chooses to start simple cognitive check
→ result appears in dashboard as follow-up suggestion, not diagnosis

### A-RAG production hardening (2026-07-15)

Completed validation of the lightweight A-RAG layer inside the production message path.

Implemented:

- End-to-end scenarios for dementia QA, caregiver repeated-question guidance, medication decisions, medication uncertainty, wandering, neutral memory concerns, out-of-scope requests, and insufficient evidence.
- Route-policy, evidence-sufficiency, retrieval-trace, output-leakage, dashboard compatibility, and duplicate-event regression tests.
- Bounded caregiver-guidance retrieval with practical, non-diagnostic final wording.
- Safety priority fixes, including medication uncertainty taking precedence over misleading completion substrings.
- One interaction-event owner in `message_router`; the orchestrator no longer creates duplicate events.
- Stronger output guards for retrieval tools, source labels, vector/index terms, debug text, and local paths.
- Privacy validation confirming dashboard events contain allow-listed structured fields and no raw messages, answers, chunks, or traces.
- Local fixed-scenario runner at `scripts/run_arag_regression_eval.py`.
- A-RAG documentation at `docs/arag_integration.md` and an updated repository structure in `README.md`.
- Compatibility repairs for account-command display, caregiver linking, medicine aliases, local Chroma paths, ingestion imports, and language-specific safety responses.

Verification:

- The full `pytest` suite passes.
- The local A-RAG regression runner passes without Telegram, WhatsApp, Nanobot, network access, or a persistent vector index.

Documentation rule for future revisions:

- Record every material code, behavior, safety, privacy, test, or structure change in `project_log.md`.
- Update `README.md` in the same revision whenever commands, file structure, entrypoints, architecture, capabilities, or setup instructions change.

---

## Frontend, Privacy & QR Code Access (2026-07-15)

Completed the design and implementation of a public-facing frontend entry point for the CoA-Agent system.

Implemented:

- A clean, mobile-friendly landing page (`index.html`) with a prominent "Open in Telegram" button, designed to be accessible for caregivers and older adults.
- A bilingual (English + Traditional Chinese) Privacy Policy & Consent page (`privacy.html`), which includes:
  - A clear medical disclaimer (CoA-Agent is not a medical device).
  - Data collection disclosure (only anonymous metadata is stored; raw conversation text is never saved).
  - User rights information (withdrawal, deletion, no profiling).
  - A mandatory 3-checkbox consent form that must be fully ticked before the user can proceed.
- JavaScript logic that disables the Telegram button until all three consent checkboxes are ticked, enforcing active user agreement.
- A QR code generation pipeline that directs users to the landing page. The QR code is intended for physical distribution (posters, flyers) to provide a frictionless entry point for users.
- A local development server setup using `python -m http.server` for testing the full user flow (scan QR → read policy → consent → jump to Telegram).

Testing and validation:

- Validated the complete user journey: scanning a QR code → opening the landing page → reading the privacy policy → ticking the consent boxes → clicking "Open in Telegram" → launching a chat with the `@Ako_saka_Bot` Telegram bot.
- Successfully tested the QR code flow using a mobile phone connected via Personal Hotspot to bypass the HKU Wi-Fi AP Isolation issue.
- Identified that HKU Wi-Fi client isolation blocks device-to-device communication, making local `localhost` testing inaccessible from mobile devices. This confirmed that a cloud-based public URL is required for production deployment.
- Generated and tested both the landing page QR code and a direct Telegram QR code. Concluded that the landing page QR code is the correct choice for ethical user onboarding.

Outcome:

- The frontend now provides a complete, privacy-first, and ethics-compliant onboarding experience for new users.
- The code has been committed to the project repository under `/frontend`.
- The flow is ready for deployment to a cloud server (e.g., HKU Linux server) where the QR code will point to a permanent public URL, eliminating the local network dependency.

## LightRAG Integration Testing & Evaluation (2026-07-15)

Conducted further testing of the LightRAG framework (HKU Nanobot team's RAG solution) as a potential upgrade to the existing RAG pipeline.

Testing process:

- Restarted LightRAG from scratch with a clean environment and a fresh copy of the `World-Alzheimer-Report-2023.md` document.
- Document processing began with chunking and knowledge graph extraction. Observed that LightRAG produces high-quality retrieval, but initial indexing is time-consuming, even for a moderately sized document.
- Encountered an `Embedding dimension mismatch` error (`total elements 3840 cannot be evenly divided by expected dimension 1024`) during the storage flush phase, which halted processing.

Diagnosis and resolution:

- Identified that the error was caused by an incorrect `EMBEDDING_DIM` setting in the `.env` file, which did not match the actual dimension of the `all-minilm` embedding model (384, not 1024).
- Fixed the mismatch by setting `EMBEDDING_DIM=384` in the `.env` file, deleting the `rag_storage` folder, and restarting the server.

Current status:

- LightRAG shows strong retrieval potential but requires careful configuration and a fast indexing strategy for production use.
- The indexing time remains a concern for document updates in real-world deployment.

Open questions for future work:

- How can indexing be optimized for production? Options include:
  - Using a faster/cheaper LLM specifically for the entity extraction phase.
  - Parallelizing the indexing process.
  - Accepting the time-cost trade-off for improved retrieval accuracy.
- The choice of embedding model and its dimension must be explicitly documented to avoid configuration errors.

### Dashboard, LightRAG & Frontend Debugging (2026-07-16)

#### Dashboard & Logging Fixes
- Resolved Dashboard `0` interaction count. Root cause: Streamlit was loading an outdated `metrics.py` from `C:\Users\user\.nanobot\` instead of the project `src/` folder.
- Fixed by copying the updated `metrics.py` and `insights.py` to the `.nanobot` folder. Interaction count immediately updated to `22`.
- Added `log_event` calls to `memory_routine_agent.py` to ensure all test interactions write to `events.jsonl`.
- Added a **Cognitive Signals Traffic Light** (🟢/🟡/🔴) to the Dashboard based on concern signal counts.

#### LightRAG Fixes
- Fixed `Embedding dimension mismatch` error (`3840 / 1024`). Corrected `EMBEDDING_DIM=384` in `.env` to match the `all-minilm` model used by Ollama.
- Confirmed that switching LLM models (Ollama ↔ DeepSeek) does not require re-indexing as long as the embedding model remains unchanged.

#### Frontend & Network (2026-07-17)
- Deployed on github, the frontend now is 24/7 working, QR code is generated and won't be affected by wifi AP isolation issues. 
- Next critical step is to deploy the backend (Telegram Bot + LightRAG) to a cloud server so the bot can reply 24/7 without relying on anyone's local computer

#### 2026-07-23