from src.intent_router import IntentResult, classify_intent
from src.dementia_rag import search_dementia_knowledge
from src.pipeline.rag_agent import SAFETY_SENSITIVE_RESPONSE, answer_question


def test_classify_intent_returns_intent_result() -> None:
    result = classify_intent("腦退化症有什麼症狀？")

    assert isinstance(result, IntentResult)


def test_knowledge_qa() -> None:
    assert classify_intent("腦退化症有什麼症狀？").intent == "knowledge_qa"


def test_safety_sensitive_wandering() -> None:
    assert classify_intent("媽媽走失了，我找不到她").intent == "safety_sensitive"


def test_medication_boundary() -> None:
    assert classify_intent("我可不可以幫她停藥？").intent == "medication_or_diagnosis"


def test_reminder_request() -> None:
    assert classify_intent("提醒我下午三點飲水").intent == "reminder_request"


def test_cognitive_activity() -> None:
    assert classify_intent("我好悶，有什麼可以做？").intent == "cognitive_activity"


def test_emotional_support() -> None:
    assert classify_intent("我覺得好孤單").intent == "emotional_support"


def test_personal_memory() -> None:
    assert classify_intent("我女兒叫什麼名字？").intent == "personal_memory"


def test_unknown() -> None:
    assert classify_intent("幫我寫一首歌").intent == "unknown"


def test_safety_priority_over_knowledge() -> None:
    assert classify_intent("腦退化症患者走失了怎麼辦？").intent == "safety_sensitive"


def test_prevention_safety_question_stays_knowledge_qa() -> None:
    assert classify_intent("如何預防腦退化症患者走失？").intent == "knowledge_qa"


def test_medication_priority_over_reminder() -> None:
    assert classify_intent("提醒我停藥").intent == "medication_or_diagnosis"


def test_english_terms() -> None:
    assert classify_intent("What are dementia symptoms?").intent == "knowledge_qa"
    assert classify_intent("Please remind me about my appointment").intent == "reminder_request"


def test_debug_fields_include_matches_and_reason() -> None:
    result = classify_intent("媽媽走失了，我找不到她")

    assert result.confidence > 0.0
    assert result.matched_terms == ["走失", "找不到"]
    assert result.reason


def test_rag_answer_question_includes_intent_for_empty_message(tmp_path) -> None:
    result = answer_question("", {"chroma_dir": tmp_path / "chroma", "auto_index": False})

    assert result["intent"] == "unknown"
    assert result["intent_debug"]["confidence"] == 0.0
    assert result["debug"]["intent"] == "unknown"
    assert result["debug"]["intent_debug"]["reason"]


def test_rag_answer_question_handles_medication_without_retrieval(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Boundary handlers must run before RAG retrieval")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    result = answer_question(
        "我可不可以幫她停藥？",
        {
            "chroma_dir": tmp_path / "chroma",
            "auto_index": False,
            "patient_profile": {"preferred_name": "眉眉婆婆", "caregivers": [{"name": "Maria"}]},
        },
    )

    assert "我唔可以話你食唔食得" in result["answer"]
    assert "Maria" in result["answer"]
    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "medication_safety"
    assert result["debug"]["normal_rag_skipped"] is True


def test_rag_answer_question_handles_urgent_safety_without_retrieval(tmp_path, monkeypatch) -> None:
    def fail_build_runtime_agent(config):
        raise AssertionError("Boundary handlers must run before RAG retrieval")

    monkeypatch.setattr("src.pipeline.rag_agent._build_runtime_agent", fail_build_runtime_agent)

    result = answer_question("媽媽走失了，我找不到她", {"chroma_dir": tmp_path / "chroma", "auto_index": False})

    assert result["answer"] == SAFETY_SENSITIVE_RESPONSE
    assert result["found"] is False
    assert result["sources"] == []
    assert result["debug"]["boundary_handler"] == "safety_sensitive"


def test_search_wrapper_includes_intent_for_empty_message() -> None:
    result = search_dementia_knowledge("")

    assert result["intent"] == "unknown"
    assert result["intent_debug"]["confidence"] == 0.0
    assert result["debug"]["intent"] == "unknown"


def test_search_wrapper_returns_boundary_context(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.dementia_rag.shared_answer_question",
        lambda question, config: {
            "found": False,
            "answer": SAFETY_SENSITIVE_RESPONSE,
            "sources": [],
            "context_used": "",
            "intent": "safety_sensitive",
            "intent_debug": {"confidence": 0.95, "matched_terms": ["走失"], "reason": "test"},
            "debug": {"boundary_handler": "safety_sensitive"},
        },
    )

    result = search_dementia_knowledge("媽媽走失了")

    assert result["context"] == SAFETY_SENSITIVE_RESPONSE
    assert result["risk_level"] == "high"
    assert result["sources"] == []
