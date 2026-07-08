# Manual Dementia Bot Route Tests

Use these examples after startup to confirm Nanobot calls only the MCP tool
`handle_dementia_user_message` and that Telegram/WhatsApp compatible routing is
unchanged.

| # | Example question | Expected route | Expected behavior |
|---|---|---|---|
| 1 | 腦退化症是什麼？ | `rag_qa` | Calls RAG and answers from local dementia sources only. |
| 2 | What are common dementia symptoms? | `rag_qa` | Calls RAG and answers in English from local dementia sources only. |
| 3 | 護老者可以點樣同腦退化症患者溝通？ | `rag_qa` | Calls RAG and answers with caregiving guidance grounded in local sources. |
| 4 | 我可以幫媽媽停藥嗎？ | `medical_boundary` | Does not call normal RAG; returns medication/clinician boundary. |
| 5 | Can I give my father an extra pill tonight? | `medical_boundary` | Does not call normal RAG; returns medication/clinician boundary in English. |
| 6 | 媽媽走失了，我找不到她 | `safety` | Does not call normal RAG; returns urgent safety guidance. |
| 7 | 提醒我下午三點飲水 | `routine` | Does not call RAG; returns routine/reminder route response. |
| 8 | 我女兒叫什麼名字？ | `memory` | Does not call RAG; returns personal-memory route response. |
| 9 | 我好悶，有什麼可以做？ | `activity` | Does not call RAG; returns cognitive activity response. |
| 10 | 幫我寫一首歌 | `unknown` | Does not call RAG or invent dementia knowledge. |

Startup logs should include the actual writable Chroma path, for example:

```text
MCP_STARTUP chroma_dir=/home/aine/.cache/coa-agent/chroma/ling_rag
MCP_STARTUP collection_name=ling_rag
MCP_STARTUP enabled_tools=handle_dementia_user_message
```
