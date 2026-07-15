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
