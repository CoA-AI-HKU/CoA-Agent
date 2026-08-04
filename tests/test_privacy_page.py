from pathlib import Path


PRIVACY = (Path(__file__).resolve().parents[1] / "privacy.html").read_text(encoding="utf-8")


def test_default_landing_view_still_offers_the_telegram_button():
    # The QR-code / physical-distribution flow always hits this page with
    # no query string — that entry point must keep working exactly as
    # before: read the policy, tick all three boxes, then jump to Telegram.
    assert 'href="https://t.me/Ako_saka_Bot"' in PRIVACY
    assert 'id="proceedBtn"' in PRIVACY


def test_policy_context_hides_the_consent_form_and_telegram_button():
    # Reached from inside the web app (web/index.html links here with
    # ?context=policy) this is a pure reference page — no re-consent, no
    # nudge toward Telegram, since consenting only happens once, in the
    # app's own consent gate.
    script = PRIVACY[PRIVACY.index("context") :]
    assert "consentSection" in script
    assert "ctaButtons" in script
    assert "hidden = true" in script


def test_hidden_attribute_is_never_overridden_by_a_flex_or_grid_container():
    # Regression test for the original bug: a class-specific `.btn-group`
    # set its own `display: flex`, which outranked the browser's default
    # `[hidden] { display: none }` rule, so setting `hidden` alone silently
    # did nothing. Fixed (see web/index.html, which this page's CSS now
    # mirrors) with one global, !important-qualified rule instead of a
    # narrow per-class patch — this protects every element on the page, not
    # just the one that broke before.
    assert "[hidden] { display: none !important; }" in PRIVACY


def test_privacy_page_reuses_index_html_design_tokens():
    # This page used to be its own unrelated design system (different
    # palette, radii, font stack, button markup) despite being reachable
    # both standalone and as an in-app link from web/index.html's consent
    # gate — see the WCAG 2.1 AA audit's "Consistent Identification"
    # finding. Locks in that it now shares index.html's actual tokens
    # rather than just superficially similar ones.
    assert 'system-ui, -apple-system, "Noto Sans HK", "PingFang HK", sans-serif' in PRIVACY
    assert "#076b75" in PRIVACY  # primary accent
    assert "class=\"action-button send-button\"" in PRIVACY
    assert "outline: 4px solid #a35800;" in PRIVACY  # shared focus-visible style


def test_privacy_page_has_nav_and_main_landmarks():
    assert "<main id=\"mainContent\"" in PRIVACY
    assert '<nav aria-label="頁面導航">' in PRIVACY


def test_privacy_page_has_a_skip_link():
    assert '<a href="#mainContent" class="skip-link">' in PRIVACY


def test_privacy_page_marks_english_passages_with_lang_en():
    # The document root is lang="zh-HK", but roughly half the policy text is
    # full English prose — without lang="en" on those passages, a screen
    # reader has no signal to switch pronunciation and reads English text
    # with Cantonese phonetics (WCAG 2.1 SC 3.1.2 Language of Parts).
    assert PRIVACY.count('lang="en"') >= 4


def test_privacy_page_states_wcag_conformance():
    assert "WCAG 2.1" in PRIVACY
    assert "a11y-mark" in PRIVACY


def test_focus_ring_clears_the_3_to_1_ui_component_minimum():
    # The amber #f2a900 focus ring measured ~2.0:1 on white — well under the
    # 3:1 WCAG 2.1 SC 1.4.11 minimum for UI component boundaries. #a35800
    # clears it with real margin (~5.3:1) on every background this page
    # actually uses.
    assert "#f2a900" not in PRIVACY
    assert "outline: 4px solid #a35800;" in PRIVACY


def test_agree_link_is_not_just_visually_disabled():
    # aria-disabled alone only *announces* a disabled state to assistive
    # tech — it does not stop an <a> from activating via mouse or keyboard.
    # The old version relied purely on style.pointerEvents/opacity, which a
    # keyboard user's Enter key ignores entirely, letting them reach
    # Telegram without ever completing the consent checkboxes. This checks
    # the actual guard exists, not just the visual/ARIA state.
    assert 'aria-disabled="true"' in PRIVACY
    script = PRIVACY[PRIVACY.index("function checkConsent") :]
    assert "addEventListener('click'" in script
    assert "event.preventDefault()" in script
