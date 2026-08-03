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
