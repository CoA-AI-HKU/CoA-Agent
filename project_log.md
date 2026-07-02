# Project Log

Research-based timeline and review,

## Week 1

## Week 2 (6/22-6/26)

Literature reviews: useful information:

### 6/26

Successfully produced funtioning nanobot connected to telegram
Process: data -> chunking -> embedder, chroma db processing -> LLM factoring
Currently based on deepseek-flash-v4

Completed work:

- Connected Nanobot to Telegram and confirmed that Telegram messages can be received and answered through the Nanobot gateway.
- Integrated the dementia RAG module into Nanobot through an MCP server.
- Tested the Telegram-facing bot with Traditional Chinese dementia-related questions.
- Verified that Telegram responses can draw from the pre-ingested dementia RAG database rather than live web search.
- Ingested web-derived dementia resources into local Markdown files under the RAG knowledge base.
Discussed future cloud deployment to avoid local VPN and WSL networking instability.

Current status:

Telegram + Nanobot connection works.
RAG MCP tool registration works.
Telegram answers are promising.
CLI answer quality remains inconsistent and requires debugging.

#### Limitations: Can't ask difficult questions, Must be run through nanobot on personal computer, while computer is live. Can only give definitio-like answers  without human-like emotions. Can't save conversations and ask

#### To do

- Consider cloud implementation

## Week 3 (6/29-7/3)

RAG Research: uploaded on OneNote

TBD: Research on RAG, research on innovative points, research on image parsing/link parsing on input

Avatar: Based on prior work on older adults’ virtual-agent preferences, we selected a youthful adult, culturally familiar, humanlike avatar rather than an elderly or childlike figure. This decision is provisional and should be validated with people living with dementia and caregivers in future participatory testing. The appearance should suggest “helpful companion” rather than “doctor,” “caregiver authority,” or “elderly patient.”
Image parsing:
Cloud-server:
TBD: figure out colab
Connect to whatsapp: --needs virtual number

### 7/2
- CLI/Telegram mismatch has been resolved.
- Telegram and CLI now use the same or consistent RAG answer pipeline.
- Intent recognizer has been implemented.
- New websites were parsed
- Added intent router to diffrentiate between different questions
- improved safety with safety layer and medicine layer
- Introduction of paper done

## Week 4
