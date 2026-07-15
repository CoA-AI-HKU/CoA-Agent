# A-RAG integration

## What changed

The production dementia-support flow now uses a bounded agentic retrieval layer for dementia knowledge questions and caregiver care-advice questions. It does not replace the coordinator or safety handlers. The production entrypoint remains `handle_incoming_message`, which performs sender normalization, role lookup, manager selection, orchestration, final output guarding, and one structured dashboard event per incoming message.

## Retrieval tools

- `keyword_search` returns exact-match snippets and stable chunk IDs.
- `semantic_search` uses the existing vector retriever and returns snippets rather than full documents.
- `chunk_read` reads only selected chunks and uses a context tracker to prevent duplicate reads.

Retrieval is bounded to three steps and at most three full chunks. Internal traces record the route, queries, tools, chunks, evidence decision, failure state, and whether the answer used RAG.

## Route-aware policy

- `rag_qa` and dementia knowledge routes may use all three retrieval tools.
- `caregiver_guidance` may retrieve care guidance, while the final wording stays practical, non-diagnostic, and non-shaming.
- `medical_boundary` may perform only limited snippet lookup when called directly; production medication decisions bypass normal RAG and use the medication boundary.
- `memory_concern` is neutral and non-diagnostic. It does not introduce dementia unless the user explicitly raises dementia or a diagnosis.
- `safety`, wandering, unknown, out-of-scope, and caregiver-summary routes skip A-RAG. Caregiver summaries read structured events first.

## Evidence sufficiency

Evidence is sufficient only when a substantive retrieved chunk has topical overlap or a strong retrieval score. Empty or unrelated retrieval is insufficient and produces a localized “not enough information” answer. Supporting chunk IDs remain in internal debug metadata only.

## Safety and privacy boundaries

Medication and urgent-safety handlers override retrieval. The assistant does not decide whether a medicine can be taken, changed, stopped, repeated, or combined. Medication uncertainty advises against an unchecked extra dose and directs the user to their medicine record, caregiver, doctor, or pharmacist. Wandering responses prioritize immediate help.

Dashboard logging stores allow-listed structured fields only. Raw messages, answers, retrieved text, source paths, and debug traces are not written to dashboard events. The message router owns interaction logging, preventing duplicate orchestrator/router events.

## Hidden from users

Normal answers do not expose internal filenames, Markdown paths, local paths, source labels, retrieval tool names, MCP/Chroma/vector details, trace fields, exceptions, or debug text. Internal sources and retrieval traces remain available for evaluation in result metadata.

## Run verification

```bash
python -m pytest -q
python scripts/run_arag_regression_eval.py
```

The evaluation runner uses an in-memory local corpus and calls the normal Python message router. It does not require Telegram, WhatsApp, Nanobot, network access, or a persistent Chroma index.

