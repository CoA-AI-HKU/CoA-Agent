from __future__ import annotations

from pathlib import Path

from src.web_ingest import convert_website_url, load_urls_from_file, markdown_path_for_url
from src.web_to_markdown import html_to_markdown


def test_html_to_markdown_preserves_readable_content() -> None:
    html = """
    <html>
      <head><title>Care Guide</title><style>.hidden{display:none}</style></head>
      <body>
        <nav>Home About Contact</nav>
        <main>
          <h1>Dementia Support</h1>
          <p>Keep routines familiar and calm.</p>
          <ul>
            <li>Use calendars.</li>
            <li><a href="/tips">Share reminders</a>.</li>
          </ul>
        </main>
        <script>alert("noise")</script>
      </body>
    </html>
    """

    markdown = html_to_markdown(html, base_url="https://example.org/articles/care")

    assert "# Dementia Support" in markdown
    assert "Keep routines familiar and calm." in markdown
    assert "- Use calendars." in markdown
    assert "[Share reminders](https://example.org/tips)." in markdown
    assert "Home About Contact" not in markdown
    assert "alert" not in markdown


def test_convert_website_url_writes_markdown(monkeypatch, tmp_path: Path) -> None:
    html = "<html><head><title>Example Page</title></head><body><main><p>Readable website text.</p></main></body></html>"

    monkeypatch.setattr(
        "src.web_to_markdown.fetch_website_html",
        lambda url: (html, "https://example.org/page", "text/html; charset=utf-8"),
    )

    path = convert_website_url("https://example.org/page", markdown_root=tmp_path)

    assert path == markdown_path_for_url("https://example.org/page", markdown_root=tmp_path)
    text = path.read_text(encoding="utf-8")
    assert "<!-- source: https://example.org/page -->" in text
    assert "# Example Page" in text
    assert "Readable website text." in text


def test_load_urls_from_file_ignores_comments_and_blank_lines(tmp_path: Path) -> None:
    url_file = tmp_path / "websites.txt"
    url_file.write_text(
        """
        # comment

        https://example.org/one
        https://example.org/two
        """,
        encoding="utf-8",
    )

    assert load_urls_from_file(url_file) == [
        "https://example.org/one",
        "https://example.org/two",
    ]
