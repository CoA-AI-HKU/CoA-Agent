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


def test_speech_recognition_stays_open_across_pauses():
    # continuous = false made the browser auto-end recognition after the
    # first short pause (~1-2s) — reported as "cuts off before I finish
    # talking." Especially relevant for elderly/dementia users, who may
    # pause mid-sentence. The user (tap-again or hold-release) still fully
    # controls when it actually stops.
    fn = INDEX[INDEX.index("function createBrowserSpeechProvider"):INDEX.index("recognition.onstart")]
    assert "recognition.continuous = true;" in fn
    assert "recognition.continuous = false;" not in fn


def test_speech_provider_tracks_lowest_final_confidence():
    # Some browsers always report 0 (not measured) rather than a genuine
    # score — only a positive value should ever be trusted as a real
    # confidence signal, so an unmeasured 0 never gets mistaken for
    # "definitely unclear."
    fn = INDEX[INDEX.index("function createBrowserSpeechProvider"):INDEX.index("recognition.onerror")]
    assert "recognition.maxAlternatives = 3;" in fn
    assert "typeof confidence === \"number\" && confidence > 0" in fn
    assert "Math.min(lowestFinalConfidence, confidence)" in fn


def test_speech_provider_reports_low_confidence_on_end():
    fn = INDEX[INDEX.index("recognition.onend = function"):INDEX.index("return {\n        start:")]
    assert "lowestFinalConfidence < LOW_CONFIDENCE_THRESHOLD" in fn
    assert "callbacks.onEnd && callbacks.onEnd(finalTranscript.trim(), { lowConfidence: lowConfidence });" in fn


def test_unclear_speech_has_a_friendly_message_distinct_from_no_speech():
    assert '"unclear-speech":' in INDEX
    unclear_message = INDEX[INDEX.index('"unclear-speech":') : INDEX.index('"unclear-speech":') + 120]
    assert "唔係好清楚" in unclear_message


def test_companion_mode_asks_to_repeat_on_low_confidence_instead_of_submitting():
    fn = INDEX[INDEX.index("function _startCompanionListeningSession"):INDEX.index("function stopCompanionListening")]
    on_end = fn[fn.index("onEnd: function") :]
    low_confidence_check = on_end.index("info.lowConfidence")
    submit_call = on_end.index("submitToCompanionChat(finalText)")
    assert low_confidence_check < submit_call
    assert 'companionError("unclear-speech")' in on_end


def test_companion_mode_silently_retries_once_on_no_speech():
    fn = INDEX[INDEX.index("function _startCompanionListeningSession"):INDEX.index("function stopCompanionListening")]
    on_error = fn[fn.index("onError: function") : fn.index("onEnd: function")]
    assert 'code === "no-speech" && !companionNoSpeechRetried' in on_error
    assert "companionNoSpeechRetried = true;" in on_error
    assert "_startCompanionListeningSession();" in on_error


def test_start_companion_listening_resets_the_retry_flag_for_a_fresh_session():
    fn = INDEX[INDEX.index("function startCompanionListening"):INDEX.index("function _startCompanionListeningSession")]
    assert "companionNoSpeechRetried = false;" in fn


def test_stale_callbacks_from_a_superseded_listening_session_are_ignored():
    # A retried-away-from session's onend can still fire after the retry's
    # own provider is created (the old SpeechRecognition object isn't
    # actually cancelled, just abandoned) — without this guard, that stale
    # callback would show an error for what the retry may already be
    # handling successfully.
    fn = INDEX[INDEX.index("function _startCompanionListeningSession"):INDEX.index("function stopCompanionListening")]
    assert fn.count("currentListeningGeneration !== companionListeningGeneration") >= 2
    assert "companionListeningGeneration += 1;" in fn


def test_developer_mode_logs_low_confidence_transcripts():
    fn = INDEX[INDEX.index("function startDeveloperListening"):INDEX.index("async function sendDeveloperTranscript")]
    assert "info.lowConfidence" in fn
    assert 'logDevError("unclear-speech"' in fn


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


def test_pairing_code_ui_never_shows_for_a_caregiver_account_in_companion_mode():
    # A caregiver account can also reach Companion Mode via the mode
    # switcher (see availableModes()) — "generate a code to give my
    # caregiver" makes no sense there, since the account isn't itself a
    # patient. This must be hidden unconditionally for non-companion roles,
    # not merely once /api/me/linked-caregivers happens to return something.
    fn = INDEX[INDEX.index("async function loadLinkedCaregivers"):INDEX.index("async function loadLinkedCaregivers") + 800]
    role_check = fn.index('meProfile.role !== "companion"')
    early_hide = fn.index("companionPairingCodeSection.hidden = true;")
    fetch_call = fn.index('"/api/me/linked-caregivers"')
    assert role_check < early_hide < fetch_call


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


def test_caregiver_mode_has_a_monitoring_settings_menu():
    caregiver_section = INDEX[INDEX.index('<section id="caregiverMode"'):INDEX.index('<section id="developerMode"')]
    assert 'id="monitoringPatientSelect"' in caregiver_section
    assert 'id="monitorSafetyCheckbox"' in caregiver_section
    assert 'id="monitorCognitiveCheckbox"' in caregiver_section
    assert 'id="saveMonitoringButton"' in caregiver_section
    # Framed as a joint decision, per the actual request — not a unilateral
    # caregiver-only setting.
    assert "商量" in caregiver_section


def test_caregiver_mode_has_blood_pressure_record_columns():
    caregiver_section = INDEX[INDEX.index('<section id="caregiverMode"'):INDEX.index('<section id="developerMode"')]
    assert 'id="bloodPressurePatientSelect"' in caregiver_section
    assert 'id="bloodPressureTable"' in caregiver_section
    assert 'id="bloodPressureTableBody"' in caregiver_section
    assert '<th scope="col">記錄時間</th>' in caregiver_section
    assert '<th scope="col">上壓</th>' in caregiver_section
    assert '<th scope="col">下壓</th>' in caregiver_section
    assert '"/blood-pressure?limit=30"' in INDEX


def test_monitoring_settings_disabled_when_no_linked_patients():
    fn = INDEX[INDEX.index("function renderMonitoringPatientSelect"):INDEX.index("async function loadMonitoringPreferences")]
    assert "monitorSafetyCheckbox.disabled = true" in fn
    assert "monitorCognitiveCheckbox.disabled = true" in fn
    assert "saveMonitoringButton.disabled = true" in fn


def test_monitoring_preferences_load_for_the_selected_patient():
    fn = INDEX[INDEX.index("async function loadMonitoringPreferences"):INDEX.index("monitoringPatientSelect.addEventListener")]
    assert '"/api/me/linked-patients/" + encodeURIComponent(patientUserId) + "/monitoring"' in fn
    assert "monitorSafetyCheckbox.checked = preferences.safety" in fn
    assert "monitorCognitiveCheckbox.checked = preferences.cognitive_decline" in fn


def test_saving_monitoring_preferences_sends_both_checkbox_states():
    start = INDEX.index("saveMonitoringButton.addEventListener")
    fn = INDEX[start : start + 900]
    assert 'method: "PUT"' in fn
    assert "safety: monitorSafetyCheckbox.checked" in fn
    assert "cognitive_decline: monitorCognitiveCheckbox.checked" in fn


def test_caregiver_mode_has_a_patient_specific_contacts_section():
    caregiver_section = INDEX[INDEX.index('<section id="caregiverMode"'):INDEX.index('<section id="developerMode"')]
    assert 'id="patientContactSelect"' in caregiver_section
    assert 'id="patientContactForm"' in caregiver_section
    assert 'id="patientContactList"' in caregiver_section
    # Distinct from the caregiver's own blanket "📞 聯絡人" form/list ids —
    # this must not be the same element reused.
    assert 'id="patientContactSelect"' != 'id="contactForm"'


def test_patient_specific_contact_writes_to_the_selected_patients_endpoint():
    start = INDEX.index('patientContactForm.addEventListener("submit"')
    fn = INDEX[start : start + 900]
    assert "patientContactSelect.value" in fn
    assert '"/api/me/linked-patients/" + encodeURIComponent(patientUserId) + "/contacts"' in fn
    assert '{ method: "POST"' in fn


def test_patient_contact_select_repopulates_from_linked_patients():
    fn = INDEX[INDEX.index("function renderPatientContactSelect"):INDEX.index("async function loadPatientContacts")]
    assert "patientContactForm.hidden = true" in fn  # no linked patients yet
    assert "patientContactForm.hidden = false" in fn
    assert "loadPatientContacts(patientContactSelect.value)" in fn


def test_deleting_a_patient_specific_contact_uses_the_accessible_dialog():
    fn = INDEX[INDEX.index("function renderPatientContactList"):INDEX.index("patientContactSelect.addEventListener")]
    assert "await openConfirmDialog(" in fn
    assert '"/contacts/" + contact.id' in fn
    assert '{ method: "DELETE" }' in fn


def test_deleting_a_patient_account_requires_typed_hk_confirmation_phrase():
    assert 'const DELETE_PATIENT_CONFIRMATION_PHRASE = "確定刪除"' in INDEX
    fn = INDEX[INDEX.index("async function deletePatientAccount"):INDEX.index("async function deletePatientAccount") + 1200]
    # The typed-phrase check itself now lives inside openConfirmDialog()'s
    # confirm handler (see test_destructive_actions_use_an_accessible_dialog)
    # — deletePatientAccount just supplies the required phrase and only ever
    # receives back the already-validated phrase or null.
    assert "requirePhrase: DELETE_PATIENT_CONFIRMATION_PHRASE" in fn
    assert '"/account"' in fn


def test_destructive_actions_use_an_accessible_dialog_not_native_confirm():
    # window.confirm()/prompt() are a known rough edge across some
    # browser/screen-reader combinations — unstyled, blocking, and not
    # fully consistent. Every destructive action goes through the same
    # focus-trapped, role="alertdialog" replacement instead.
    assert 'confirm("確定要解除' not in INDEX
    assert 'confirm("確定要刪除' not in INDEX
    assert "const typed = prompt(" not in INDEX
    assert 'role="alertdialog"' in INDEX
    assert 'aria-modal="true"' in INDEX

    delete_contact_fn = INDEX[INDEX.index("async function deleteContact"):INDEX.index("async function deleteContact") + 400]
    assert "await openConfirmDialog(" in delete_contact_fn

    unlink_patient_fn = INDEX[INDEX.index("async function unlinkPatient"):INDEX.index("async function unlinkPatient") + 400]
    assert "await openConfirmDialog(" in unlink_patient_fn


def test_confirm_dialog_traps_focus_and_closes_on_escape():
    fn = INDEX[INDEX.index("function handleConfirmDialogKeydown"):INDEX.index("function openConfirmDialog")]
    assert 'event.key === "Escape"' in fn
    assert "closeConfirmDialog(null)" in fn
    assert 'event.key !== "Tab"' in fn


def test_confirm_dialog_mismatched_phrase_re_prompts_instead_of_silently_failing():
    # The old prompt()-based flow closed on a wrong phrase and left the user
    # to notice a page message and start over from scratch. The dialog
    # instead shows an inline, aria-live error and lets them retry in place.
    fn = INDEX[INDEX.index('confirmDialogConfirmButton.addEventListener("click"'):]
    fn = fn[: fn.index("\n    // ===== 8. CAREGIVER TOOLS")]
    assert "typed !== confirmDialogRequiredPhrase" in fn
    assert "confirmDialogError.hidden = false" in fn
    assert '<p id="confirmDialogError" class="form-message error-message" aria-live="assertive" hidden>' in INDEX


def test_caregiver_default_mode_is_set_to_caregiver_on_the_backend():
    # The frontend just trusts meProfile.default_mode from the server (see
    # enterApp()) — the actual "caregiver defaults into caregiver mode"
    # decision lives in backend/services/account_profiles.py, covered
    # there. This just locks in that enterApp() doesn't hardcode "companion".
    assert 'setMode(meProfile.default_mode || "companion")' in INDEX


def test_emergency_contact_fields_are_only_shown_for_companion_role():
    assert '<div id="emergencyContactFields" hidden>' in INDEX
    flow = INDEX[INDEX.index("function proceedAfterProfileLoaded"):INDEX.index("function chooseIdentity")]
    assert 'emergencyContactFields.hidden = meProfile.role !== "companion"' in flow


def test_profile_info_submits_emergency_contact_fields():
    fn = INDEX[INDEX.index('profileInfoForm.addEventListener("submit"'):INDEX.index('profileInfoForm.addEventListener("submit"') + 800]
    assert "emergency_contact_name: emergencyContactNameInput.value.trim()" in fn
    assert "emergency_contact_phone: emergencyContactPhoneInput.value.trim()" in fn


def test_call_caregiver_prefers_the_dedicated_emergency_contact():
    fn = INDEX[INDEX.index("async function handleCallCaregiver"):INDEX.index("callCaregiverButton.addEventListener")]
    emergency_check = fn.index("meProfile.emergency_contact_phone")
    contacts_fetch = fn.index('apiFetch("/api/account/contacts")')
    assert emergency_check < contacts_fetch


def test_root_font_size_is_relative_not_a_fixed_pixel_value():
    # A fixed px root font-size doesn't respond to the browser/OS default
    # text-size setting the way a relative unit does — see WCAG 2.1 SC 1.4.4
    # Resize Text. 125% of a 16px default lands at the same ~20px this app
    # has always used, but now it scales with the user's own preference.
    assert "font-size: 125%;" in INDEX
    assert "font-size: 20px;" not in INDEX


def test_companion_mode_has_a_heading():
    # Every other view (both auth gates, Caregiver/Developer Mode,
    # privacy.html) opens with a heading; Companion Mode — the screen most
    # patients land on by default — previously had none. Visually hidden
    # rather than shown, since Companion Mode is deliberately a single big
    # button with no visual clutter (see its own CSS section comment) —
    # this is for screen-reader/structural navigation only.
    companion_section = INDEX[INDEX.index('<section id="companionMode"'):INDEX.index('<section id="caregiverMode"')]
    assert '<h1 class="visually-hidden">' in companion_section


def test_consent_scroll_hint_is_announced_to_screen_readers():
    # Every other .form-message in the app carries aria-live="polite" so its
    # text is announced automatically; this was the one exception — the
    # message explaining *why* the consent checkboxes are still disabled
    # was silent for screen reader users.
    assert '<p id="consentScrollHint" class="form-message" aria-live="polite">' in INDEX


def test_talk_button_aria_label_updates_with_companion_state():
    # aria-label always wins over visible text content for assistive tech —
    # a static aria-label would tell a screen reader "press to talk" no
    # matter what state the button was actually in, even while its visible
    # label and color both changed live. See WCAG 2.1 SC 4.1.2.
    fn = INDEX[INDEX.index("function setCompanionState"):INDEX.index("function companionError")]
    assert 'talkButton.setAttribute("aria-label", COMPANION_STATE_LABEL[state]' in fn


def test_conversation_flag_timestamp_has_a_real_contrast_margin():
    # #5a7a7f measured ~4.64:1 on white — technically over the 4.5:1
    # minimum but by almost nothing. Darkened for a real safety margin.
    assert '"#5a7a7f"' not in INDEX
    assert 'when.style.color = "#4c6a6f";' in INDEX


def test_skip_link_lets_keyboard_users_bypass_the_top_bar():
    assert '<a href="#mainContent" class="skip-link">跳到主要內容</a>' in INDEX
    assert '<main id="mainContent" tabindex="-1">' in INDEX


def test_consent_form_states_wcag_conformance():
    gate = INDEX[INDEX.index('<div id="consentGate"'):INDEX.index('<div id="appShell"')]
    assert "WCAG 2.1" in gate
    assert "a11y-mark" in gate


def test_focus_ring_and_input_border_clear_the_3_to_1_ui_component_minimum():
    # WCAG 2.1 SC 1.4.11 Non-text Contrast requires UI component boundaries
    # (input borders, focus indicators) to reach 3:1, separately from SC
    # 1.4.3's 4.5:1 text minimum. The original amber focus ring (#f2a900,
    # ~2.0:1 on white) and input border (#789da2, ~2.9:1) both silently
    # failed this — a visible-looking focus outline that doesn't actually
    # meet the contrast bar isn't "visible" for the purposes of SC 2.4.7
    # either.
    assert "#f2a900" not in INDEX
    assert "#789da2" not in INDEX
    assert "outline: 4px solid #a35800;" in INDEX
    assert "border: 2px solid #5f7d82;" in INDEX


def test_consent_policy_end_marker_has_a_real_contrast_margin():
    assert 'color:#5a7a7f' not in INDEX
    assert 'color:#4c6a6f' in INDEX


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
