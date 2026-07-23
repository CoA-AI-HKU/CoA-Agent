from pathlib import Path


INDEX = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")


def test_confirmed_editable_transcript_is_posted_and_send_waits():
    assert '<textarea id="transcript"' in INDEX
    assert "confirmedTranscript = transcriptTextarea.value.trim()" in INDEX
    assert "sendButton.disabled = true" in INDEX
    assert "sendButton.disabled = false" in INDEX
    assert 'fetch("/api/chat"' in INDEX
    assert "message: confirmedTranscript" in INDEX


def test_visible_reply_is_the_source_for_automatic_and_manual_playback():
    render_position = INDEX.index('appendConversationMessage("CoA 助理", reply, "assistant")')
    speak_position = INDEX.index("if (autoPlayReply.checked) speakAssistantReply")
    assert render_position < speak_position
    assert "speakAssistantReply(latestAssistantReply, latestAssistantLanguage)" in INDEX
    assert 'stopAudioButton.addEventListener("click", stopAssistantSpeech)' in INDEX


def test_microphone_cancels_output_and_unsupported_tts_keeps_text():
    start = INDEX[INDEX.index("function startRecognition"):INDEX.index("function stopRecognition")]
    assert "cancelAssistantSpeech(false)" in start
    assert "這個瀏覽器暫時不支援語音播放，你仍然可以閱讀文字回覆。" in INDEX


def test_frontend_does_not_store_or_log_conversation_or_embed_secrets():
    forbidden = (
        "TELEGRAM_BOT_TOKEN",
        "OPENAI_API_KEY",
        "raw_audio",
    )
    for value in forbidden:
        assert value not in INDEX
    assert "console.log(confirmedTranscript" not in INDEX
    assert "console.log(latestAssistantReply" not in INDEX
    assert "localStorage.setItem(confirmedTranscript" not in INDEX
    assert "sessionStorage.setItem(confirmedTranscript" not in INDEX
