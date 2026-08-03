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


def test_developer_mode_reply_does_not_overwrite_the_sent_transcript():
    # devTranscriptInput is the box you type/speak *into*; the reply must
    # render in its own element (devReplyOutput) so the sent message stays
    # visible instead of getting clobbered by the answer.
    assert '<div id="devReplyOutput">' in INDEX
    send_fn = INDEX[INDEX.index("async function sendDeveloperTranscript"):INDEX.index("devSendButton.addEventListener")]
    assert "devReplyOutput.textContent = payload.reply" in send_fn
    assert "devTranscriptInput.value = payload.reply" not in send_fn


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


def test_identity_gate_offers_only_companion_and_caregiver():
    assert '<div id="identityGate"' in INDEX
    assert 'chooseIdentity("companion")' in INDEX
    assert 'chooseIdentity("caregiver")' in INDEX
    # developer/admin must never be self-service choices from this screen
    assert 'chooseIdentity("developer")' not in INDEX
    assert 'chooseIdentity("admin")' not in INDEX


def test_identity_gate_is_checked_before_consent_gate():
    flow = INDEX[INDEX.index("function proceedAfterProfileLoaded"):INDEX.index("function chooseIdentity")]
    identity_check = flow.index("meProfile.identity_confirmed")
    consent_check = flow.index("meProfile.consent_given")
    assert identity_check < consent_check


def test_consent_gate_embeds_the_full_policy_text_not_just_a_link():
    gate = INDEX[INDEX.index('<div id="consentGate"'):INDEX.index('<div id="appShell"')]
    assert "醫療免責聲明" in gate
    assert "數據收集與使用" in gate
    assert "你的權利" in gate


def test_consent_checkboxes_stay_disabled_until_policy_is_scrolled_to_the_end():
    assert '<input type="checkbox" id="consentCheck1" disabled>' in INDEX
    script = INDEX[INDEX.index("function checkPolicyScrolledToEnd"):INDEX.index("consentAgreeButton.addEventListener")]
    assert "box.disabled = false" in script
    assert "consentPolicyRead && consentCheck1.checked" in INDEX


def test_consent_gate_never_links_to_telegram():
    gate = INDEX[INDEX.index('<div id="consentGate"'):INDEX.index('<div id="appShell"')]
    assert "t.me" not in gate
    assert "Telegram" not in gate


def test_privacy_policy_links_from_the_app_pass_policy_context():
    assert 'href="privacy.html?context=policy"' in INDEX
    assert 'href="privacy.html"' not in INDEX  # every in-app link must carry the context param


def test_companion_mode_can_generate_a_pairing_code_without_caregiver_mode():
    # A companion-only account never sees Caregiver Mode (no mode switcher
    # entry for it — see availableModes()), so pairing-code generation
    # (POST /api/me/pairing-code, open to every role) needs its own button
    # inside Companion Mode itself, or a companion account has no way to
    # reach it at all despite the backend allowing it.
    companion_section = INDEX[INDEX.index('<section id="companionMode"'):INDEX.index('<section id="caregiverMode"')]
    assert '<button id="companionPairingCodeButton"' in companion_section
    assert 'companionPairingCodeButton.addEventListener("click"' in INDEX
    assert "generatePairingCode(companionPairingCodeButton, companionPairingCodeMessage)" in INDEX


def test_generate_pairing_code_ui_hides_once_already_paired():
    # Companion Mode's "generate a code" affordance starts hidden in markup
    # and only gets shown by loadLinkedCaregivers() once it confirms this
    # account has no linked caregiver yet — see /api/me/linked-caregivers.
    # (Caregiver Mode's copy of this was removed — see
    # test_caregiver_mode_has_no_generate_own_code_section.)
    assert '<div id="companionPairingCodeSection" hidden>' in INDEX
    fn = INDEX[INDEX.index("async function loadLinkedCaregivers"):INDEX.index("async function loadLinkedCaregivers") + 800]
    assert "companionPairingCodeSection.hidden = hasCaregiver" in fn
    assert '"/api/me/linked-caregivers"' in fn


def test_caregiver_mode_has_no_generate_own_code_section():
    # Generating a pairing code (to be paired AS a patient) only makes
    # sense from Companion Mode / the info gate now — Caregiver Mode kept a
    # redundant copy of it that has been removed.
    caregiver_section = INDEX[INDEX.index('<section id="caregiverMode"'):INDEX.index('<section id="developerMode"')]
    assert "generateOwnCodeSection" not in caregiver_section
    assert "generatePairingCodeButton" not in caregiver_section
    assert "產生配對碼" not in caregiver_section or "俾照顧者" not in caregiver_section


def test_info_gate_comes_after_identity_and_before_consent():
    flow = INDEX[INDEX.index("function proceedAfterProfileLoaded"):INDEX.index("function chooseIdentity")]
    identity_check = flow.index("meProfile.identity_confirmed")
    info_check = flow.index("meProfile.profile_info_given")
    consent_check = flow.index("meProfile.consent_given")
    assert identity_check < info_check < consent_check


def test_info_gate_collects_name_birthday_and_offers_a_pairing_code():
    assert '<div id="infoGate"' in INDEX
    info_section = INDEX[INDEX.index('<div id="infoGate"'):INDEX.index('<div id="consentGate"')]
    assert 'id="profileNameInput"' in info_section
    assert 'id="profileBirthdayInput"' in info_section
    assert 'id="infoPairingCodeButton"' in info_section
    assert '"/api/me/profile-info"' in INDEX


def test_deleting_a_patient_account_requires_typed_hk_confirmation_phrase():
    assert 'const DELETE_PATIENT_CONFIRMATION_PHRASE = "確定刪除"' in INDEX
    fn = INDEX[INDEX.index("async function deletePatientAccount"):INDEX.index("async function deletePatientAccount") + 1200]
    assert "typed.trim() !== DELETE_PATIENT_CONFIRMATION_PHRASE" in fn
    assert '"/account"' in fn


def test_caregiver_default_mode_is_set_to_caregiver_on_the_backend():
    # The frontend just trusts meProfile.default_mode from the server (see
    # enterApp()) — the actual "caregiver defaults into caregiver mode"
    # decision lives in backend/services/account_profiles.py, covered
    # there. This just locks in that enterApp() doesn't hardcode "companion".
    assert 'setMode(meProfile.default_mode || "companion")' in INDEX


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
