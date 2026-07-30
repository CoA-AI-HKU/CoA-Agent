from pathlib import Path


INDEX = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")


def test_developer_mode_editable_transcript_is_posted_on_send():
    # Companion Mode itself is voice-only/auto-submitting by design (see the
    # Companion Mode spec: no manual review step) — the editable-transcript
    # + manual-send flow lives in Developer Mode instead.
    assert '<textarea id="devTranscriptInput"' in INDEX
    assert "const message = devTranscriptInput.value.trim()" in INDEX
    assert 'devSendButton.addEventListener("click", sendDeveloperTranscript)' in INDEX
    assert 'apiFetch("/api/chat"' in INDEX
    assert "message: message, session_id: sessionId" in INDEX


def test_developer_mode_supports_review_before_send():
    # Default is auto-send; review-before-send flips it off ("auto_send"
    # false), and only auto-sends the recognized transcript when the
    # developer's own preference has it enabled.
    assert "if (devAutoSend.checked && finalText) sendDeveloperTranscript()" in INDEX
    assert 'devAutoSend.checked = !preferences.auto_send' in INDEX


def test_companion_answer_is_shown_before_being_spoken():
    render_position = INDEX.index("companionAnswer.textContent = showText ? lastAnswer : \"\"")
    speak_position = INDEX.index('setCompanionState("speaking"); speak(lastAnswer, lastAnswerLanguage')
    assert render_position < speak_position
    assert 'stopSpeakingButton.addEventListener("click", cancelSpeech)' in INDEX


def test_starting_companion_listening_cancels_any_playback_in_progress():
    start = INDEX[INDEX.index("function startCompanionListening"):INDEX.index("function stopCompanionListening")]
    assert "cancelSpeech()" in start


def test_unsupported_speech_apis_get_friendly_messages_not_raw_errors():
    assert 'unsupported: "呢個瀏覽器暫時唔支援語音功能' in INDEX
    assert "if (!speechRecognitionSupported()) { companionError(\"unsupported\"); return; }" in INDEX
    # TTS being unsupported must not clear or block the already-shown answer
    # text — speak() calls onDone and returns without touching the DOM.
    tts_unsupported = INDEX[INDEX.index('function speak(text, language, onDone)'):INDEX.index("cancelSpeech();", INDEX.index('function speak(text, language, onDone)'))]
    assert "onDone && onDone();\n        return;" in tts_unsupported


def test_frontend_does_not_store_or_log_conversation_or_embed_secrets():
    forbidden = (
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
        "DEEPSEEK_API_KEY",
        "raw_audio",
    )
    for value in forbidden:
        assert value not in INDEX
    assert "console.log(lastAnswer" not in INDEX
    assert "console.log(message" not in INDEX
    assert "localStorage.setItem" not in INDEX
    assert "sessionStorage.setItem" not in INDEX
