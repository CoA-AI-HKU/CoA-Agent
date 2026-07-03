from __future__ import annotations

from .language import AnswerLanguage, language_name


FALLBACK_ANSWERS: dict[AnswerLanguage, str] = {
    "zh-Hant": "我在資料庫中找不到足夠資料回答這個問題。",
    "zh-Hans": "我在资料库中找不到足够资料回答这个问题。",
    "en": "I don't know from the provided documents.",
}
SOURCE_LABELS: dict[AnswerLanguage, str] = {
    "zh-Hant": "資料來源",
    "zh-Hans": "资料来源",
    "en": "Sources",
}

FALLBACK_ANSWER = FALLBACK_ANSWERS["zh-Hant"]
FALLBACK_ANSWER_EN = FALLBACK_ANSWERS["en"]
FALLBACK_ANSWER_ZH_HANS = FALLBACK_ANSWERS["zh-Hans"]


def get_fallback_answer(answer_language: AnswerLanguage) -> str:
    return FALLBACK_ANSWERS[answer_language]


def get_source_label(answer_language: AnswerLanguage) -> str:
    return SOURCE_LABELS[answer_language]


ANSWER_PROMPT_TEMPLATE = """
You are a careful RAG assistant for a multilingual dementia-support knowledge base.

Answer the user's question using ONLY the provided dementia knowledge context.

Rules:
- Use only the retrieved context.
- Do not use outside knowledge.
- Do not add facts not supported by the context.
- If the context is insufficient, say:
  {fallback_answer}
- Answer only in {language_name}.
- The retrieved context may be in Traditional Chinese, Simplified Chinese, or English. Translate or summarize only the supported facts into {language_name}.
- Use simple, calm language.
- Answer in 1-3 short sentences.
- Start with the direct answer.
- Do not include unnecessary background information.
- Do not copy long passages from the context.
- For dementia-support questions, keep the tone calm, simple, and reassuring.
- Do not provide diagnosis, treatment, medication-change, dosage, or emergency medical advice.
- If the user describes immediate danger, medical emergency, wandering risk, severe confusion, or self-harm risk, advise contacting a caregiver, emergency services, or a qualified clinician.

Context:
{context}

Question:
{question}

Answer:
""".strip()

ANSWER_PROMPT = ANSWER_PROMPT_TEMPLATE.format(
    fallback_answer=f"「{FALLBACK_ANSWER}」",
    language_name=language_name("zh-Hant"),
    context="{context}",
    question="{question}",
)


def build_answer_prompt(context: str, question: str, answer_language: AnswerLanguage) -> str:
    fallback_answer = get_fallback_answer(answer_language)
    quote_open, quote_close = ("「", "」") if answer_language != "en" else ('"', '"')
    return ANSWER_PROMPT_TEMPLATE.format(
        fallback_answer=f"{quote_open}{fallback_answer}{quote_close}",
        language_name=language_name(answer_language),
        context=context,
        question=question,
    )
