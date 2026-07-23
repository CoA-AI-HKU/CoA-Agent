from src.orchestrator import UNKNOWN_RESPONSE, handle_dementia_user_message


def test_dinner_question_receives_normal_reply_not_unclear_fallback():
    result = handle_dementia_user_message("我今天晚上吃什麼好", user_id="example-food")

    assert result["route"] == "general"
    assert result["answer"] != UNKNOWN_RESPONSE
    assert any(term in result["answer"] for term in ("飯", "麵", "蔬菜"))


def test_tired_message_receives_supportive_reply_not_unclear_fallback():
    result = handle_dementia_user_message("我最近覺得好累呀", user_id="example-tired")

    assert result["route"] == "supportive"
    assert result["answer"] != UNKNOWN_RESPONSE
    assert "休息" in result["answer"]


def test_dementia_definition_uses_rag_and_returns_relevant_definition(monkeypatch):
    def definition_from_rag(message, user_id=None):
        return {
            "answer": "腦退化症是一個統稱，包括多種會令認知能力明顯退化並影響日常生活的腦部疾病。",
            "intent": "knowledge_qa",
            "route": "rag_qa",
            "rag_called": True,
            "safety_level": "normal",
            "found": True,
            "sources": [],
            "debug": {"agent": "rag_evidence"},
        }

    monkeypatch.setattr("src.orchestrator.answer_with_dementia_evidence", definition_from_rag)
    result = handle_dementia_user_message("腦退化症是什麼", user_id="example-definition")

    assert result["route"] == "rag_qa"
    assert result["rag_called"] is True
    assert "統稱" in result["answer"]
    assert "認知" in result["answer"]
