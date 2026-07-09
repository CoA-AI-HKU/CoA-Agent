from __future__ import annotations

from src.agents.types import AgentDecision, AgentResult
from src.pipeline.language import detect_answer_language
from src.safety.medication_guard import build_short_medication_safety_response, detect_red_flags
from src.meds.medicine_normalizer import normalize_medicine_mentions


SAFETY_RESPONSES = {
    "zh-Hant": "這個情況可能需要即時協助。請先確保安全，並盡快聯絡照顧者、醫護人員或緊急服務。",
    "zh-Hans": "这个情况可能需要即时协助。请先确保安全，并尽快联系照顾者、医护人员或紧急服务。",
    "en": "This situation may need immediate help. Please make sure everyone is safe and contact a caregiver, clinician, or emergency services as soon as possible.",
}
WANDERING_RESPONSES = {
    "zh-Hant": "如果媽媽現在走失或失去聯絡，請立即報警，並聯絡家人或管理處協助尋找。準備她的近照、衣著特徵、常去地點和定位資料。尋回後先安撫情緒，不要責怪，並檢查有沒有受傷。",
    "zh-Hans": "如果妈妈现在走失或失去联络，请立即报警，并联系家人或管理处协助寻找。准备她的近照、衣着特征、常去地点和定位资料。寻回后先安抚情绪，不要责怪，并检查有没有受伤。",
    "en": "If your family member is missing or cannot be reached, call emergency services now and ask family or building staff to help search. Prepare a recent photo, clothing details, usual places, and location data. When found, reassure them first, do not blame them, and check for injuries.",
}
COGNITIVE_RED_FLAG_RESPONSES = {
    "zh-Hant": "如果是突然混亂、突然不認得人、跌倒後改變、說話不清、手腳無力、發燒、幻覺、胸痛或呼吸困難，請盡快求醫或聯絡緊急服務。這類情況不應只當作一般記憶問題處理。",
    "zh-Hans": "如果是突然混乱、突然不认得人、跌倒后改变、说话不清、手脚无力、发烧、幻觉、胸痛或呼吸困难，请尽快求医或联系紧急服务。这类情况不应只当作一般记忆问题处理。",
    "en": "If there is sudden confusion, suddenly not recognizing people, a change after a fall, slurred speech, weakness, fever, hallucinations, chest pain, or breathing difficulty, seek medical help or emergency services promptly. Do not treat this as only a memory problem.",
}

MEDICAL_BOUNDARY_RESPONSES = {
    "zh-Hant": "我不能提供診斷或任何用藥建議。請詢問醫生、藥劑師或合資格醫護人員。",
    "zh-Hans": "我不能提供诊断或任何用药建议。请询问医生、药剂师或合资格医护人员。",
    "en": "I can't provide diagnosis or any medication advice. Please ask a doctor, pharmacist, or qualified clinician.",
}

MEDICATION_UNCERTAINTY_RESPONSES = {
    "zh-Hant": "如果你不確定有沒有服藥，請不要自行再服一次。可以先查看藥盒或服藥記錄；如果仍不確定，請聯絡家人、照顧者、醫生或藥劑師確認。",
    "zh-Hans": "如果不确定是否已经吃药，先不要自行补吃或多吃一剂。请尽快问家人、照顾者、药剂师或医生。",
    "en": "If you are not sure whether you already took the medicine, do not take an extra dose on your own. Please ask family, a caregiver, pharmacist, or doctor.",
}
ASPIRIN_HEADACHE_RESPONSES = {
    "zh-Hant": "我不能判斷你是否適合吃阿司匹林。頭痛可能有很多原因，而阿司匹林也不適合所有人。請先詢問醫生或藥劑師；如果頭痛突然很嚴重、伴隨胸痛、呼吸困難、說話不清、手腳無力或視力改變，請立即求醫。",
    "zh-Hans": "我不能判断你是否适合吃阿司匹林。头痛可能有很多原因，而阿司匹林也不适合所有人。请先询问医生或药剂师；如果头痛突然很严重、伴随胸痛、呼吸困难、说话不清、手脚无力或视力改变，请立即求医。",
    "en": "I cannot judge whether aspirin is suitable for you. Headache can have many causes, and aspirin is not suitable for everyone. Please ask a doctor or pharmacist first; if the headache is sudden or severe, or comes with chest pain, breathing trouble, slurred speech, weakness, or vision changes, seek urgent medical help.",
}


def _is_medication_uncertainty(message: str) -> bool:
    normalized = message.lower()
    uncertainty_terms = [
        "唔知",
        "不知",
        "不確定",
        "不确定",
        "記唔記得",
        "忘記",
        "唔記得",
        "not sure",
        "unsure",
        "forgot",
        "can't remember",
    ]
    medication_terms = ["藥", "药", "medicine", "medication", "dose"]
    return any(term in normalized for term in uncertainty_terms) and any(
        term in normalized for term in medication_terms
    )


def _is_wandering_now(message: str) -> bool:
    return any(term in message for term in ["走失", "失蹤", "失踪", "失去聯絡", "失去联络", "找不到", "不見"])


def _is_cognitive_red_flag(message: str) -> bool:
    return any(
        term in message.lower()
        for term in [
            "突然混亂",
            "突然糊塗",
            "突然不認得",
            "跌倒",
            "發燒",
            "发烧",
            "幻覺",
            "幻觉",
            "看見不存在",
            "看见不存在",
            "聽到聲音",
            "听到声音",
            "說話不清",
            "说话不清",
            "手腳無力",
            "手脚无力",
            "胸痛",
            "胸口痛",
            "呼吸困難",
            "呼吸困难",
            "sudden confusion",
            "slurred speech",
            "weakness",
            "hallucination",
        ]
    )


def _is_aspirin_headache_question(message: str) -> bool:
    normalized = message.lower()
    aspirin_terms = ["阿司匹林", "亞士匹靈", "阿士匹靈", "阿斯匹靈", "aspirin"]
    headache_terms = ["頭痛", "头疼", "頭疼", "headache"]
    return any(term in normalized for term in aspirin_terms) and any(term in normalized for term in headache_terms)


def handle_safety(message: str, decision: AgentDecision) -> dict:
    answer_language = detect_answer_language(message)
    if _is_cognitive_red_flag(message):
        answer = COGNITIVE_RED_FLAG_RESPONSES[answer_language]
    elif _is_wandering_now(message):
        answer = WANDERING_RESPONSES[answer_language]
    else:
        answer = SAFETY_RESPONSES[answer_language]
    return AgentResult(
        answer=answer,
        intent=decision.intent,
        safety_level="urgent_boundary",
        found=False,
        sources=[],
        rag_called=False,
        route="safety",
        debug={"agent": "safety", "answer_language": answer_language},
    ).to_dict()


def handle_medical_boundary(message: str, decision: AgentDecision) -> dict:
    answer_language = detect_answer_language(message)
    detected_medicines = normalize_medicine_mentions(message)
    red_flags = detect_red_flags(message)
    if _is_aspirin_headache_question(message):
        answer = ASPIRIN_HEADACHE_RESPONSES[answer_language]
    elif _is_medication_uncertainty(message):
        answer = MEDICATION_UNCERTAINTY_RESPONSES[answer_language]
    elif detected_medicines or red_flags:
        answer = build_short_medication_safety_response(
            patient_profile={},
            detected_medicines=detected_medicines,
            red_flags=red_flags,
            answer_language=answer_language,
        )
    else:
        answer = MEDICAL_BOUNDARY_RESPONSES[answer_language]

    return AgentResult(
        answer=answer,
        intent=decision.intent,
        safety_level="medical_boundary",
        found=False,
        sources=[],
        rag_called=False,
        route="medical_boundary",
        debug={
            "agent": "safety",
            "answer_language": answer_language,
            "detected_medicines": detected_medicines,
            "red_flags": red_flags,
        },
    ).to_dict()
