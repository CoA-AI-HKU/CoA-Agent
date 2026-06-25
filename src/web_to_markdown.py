from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .document import Document


DEFAULT_USER_AGENT = "CoA-Agent-RAG/1.0 (+https://example.local)"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_BYTES = 2_000_000


def _normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_usable_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _decode_html(raw: bytes, content_type: str | None) -> str:
    charset_match = re.search(r"charset=([^;\s]+)", content_type or "", flags=re.IGNORECASE)
    encodings = [charset_match.group(1)] if charset_match else []
    encodings.extend(["utf-8", "windows-1252"])

    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_website_html(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[str, str, str | None]:
    """Fetch a website and return decoded HTML, final URL, and content type."""
    if not _is_usable_url(url):
        raise ValueError(f"Expected an http(s) URL, got: {url}")

    request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type")
            if content_type and "html" not in content_type.lower():
                raise ValueError(f"Expected an HTML response from {url}, got Content-Type: {content_type}")
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise ValueError(f"Website response is larger than the {max_bytes} byte limit: {url}")
            final_url = response.geturl()
            return _decode_html(raw, content_type), final_url, content_type
    except HTTPError as exc:
        raise RuntimeError(f"Failed to fetch {url}: HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc.reason}") from exc


class _ReadableMarkdownParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "iframe"}
    _NOISE_TAGS = {"nav", "footer", "aside"}
    _BLOCK_TAGS = {
        "article",
        "blockquote",
        "body",
        "details",
        "div",
        "figcaption",
        "figure",
        "form",
        "header",
        "main",
        "p",
        "pre",
        "section",
        "table",
    }

    def __init__(self, base_url: str | None = None) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.parts: list[str] = []
        self.skip_depth = 0
        self.noise_depth = 0
        self.list_stack: list[int | None] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr_map = {name.lower(): value or "" for name, value in attrs}

        if tag in self._SKIP_TAGS:
            self.skip_depth += 1
            return
        if tag in self._NOISE_TAGS:
            self.noise_depth += 1
            return
        if self._is_skipping:
            return

        if tag == "title":
            self.in_title = True
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._blank_line()
            self.parts.append(f"{'#' * int(tag[1])} ")
        elif tag in self._BLOCK_TAGS:
            self._blank_line()
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "hr":
            self._blank_line()
            self.parts.append("---")
            self._blank_line()
        elif tag == "ul":
            self.list_stack.append(None)
            self._blank_line()
        elif tag == "ol":
            self.list_stack.append(1)
            self._blank_line()
        elif tag == "li":
            self._line_break()
            marker = self._next_list_marker()
            indent = "  " * max(len(self.list_stack) - 1, 0)
            self.parts.append(f"{indent}{marker} ")
        elif tag == "a":
            href = attr_map.get("href", "").strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
                absolute_href = urljoin(self.base_url or "", href)
                self.parts.append("[")
                self.parts.append(f"\0LINK:{absolute_href}\0")
        elif tag == "img":
            alt = attr_map.get("alt", "").strip()
            if alt:
                self.parts.append(alt)
        elif tag in {"td", "th"}:
            self.parts.append(" | ")
        elif tag == "tr":
            self._line_break()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
            return
        if tag in self._NOISE_TAGS and self.noise_depth:
            self.noise_depth -= 1
            return
        if self._is_skipping:
            return

        if tag == "title":
            self.in_title = False
        elif tag in {"h1", "h2", "h3", "h4", "h5", "h6"} or tag in self._BLOCK_TAGS:
            self._blank_line()
        elif tag in {"ul", "ol"} and self.list_stack:
            self.list_stack.pop()
            self._blank_line()
        elif tag == "li":
            self._line_break()
        elif tag == "a":
            self._close_link()
        elif tag == "tr":
            self._line_break()

    def handle_data(self, data: str) -> None:
        if self._is_skipping:
            return

        text = unescape(data)
        if not text.strip():
            if self.parts and not self.parts[-1].endswith((" ", "\n")):
                self.parts.append(" ")
            return

        normalized = re.sub(r"\s+", " ", text)
        if self.in_title:
            self.title_parts.append(normalized.strip())
            return
        self.parts.append(normalized)

    @property
    def _is_skipping(self) -> bool:
        return self.skip_depth > 0 or self.noise_depth > 0

    def _line_break(self) -> None:
        if not self.parts or self.parts[-1].endswith("\n"):
            return
        self.parts.append("\n")

    def _blank_line(self) -> None:
        current = "".join(self.parts)
        if not current:
            return
        if current.endswith("\n\n"):
            return
        if current.endswith("\n"):
            self.parts.append("\n")
        else:
            self.parts.append("\n\n")

    def _next_list_marker(self) -> str:
        if not self.list_stack or self.list_stack[-1] is None:
            return "-"
        current = self.list_stack[-1]
        self.list_stack[-1] = current + 1
        return f"{current}."

    def _close_link(self) -> None:
        marker_index = None
        href = None
        for index in range(len(self.parts) - 1, -1, -1):
            part = self.parts[index]
            if part.startswith("\0LINK:") and part.endswith("\0"):
                marker_index = index
                href = part.removeprefix("\0LINK:").removesuffix("\0")
                break

        if marker_index is None or href is None:
            return

        label = "".join(self.parts[marker_index + 1 :]).strip()
        if label:
            self.parts[marker_index] = ""
            self.parts.append(f"]({href})")
        else:
            del self.parts[marker_index:]

    def markdown(self) -> str:
        text = "".join(self.parts)
        text = re.sub(r"\[\0LINK:[^\0]+\0", "", text)
        text = re.sub(r"\n\s*\|", "\n|", text)
        return _normalize_markdown(text)

    def title(self) -> str:
        return _normalize_markdown(" ".join(self.title_parts))


def html_to_markdown(html: str, base_url: str | None = None) -> str:
    """Convert website HTML into readable markdown suitable for chunking."""
    parser = _ReadableMarkdownParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    markdown = parser.markdown()
    title = parser.title()

    if title and not markdown.startswith("#"):
        return f"# {title}\n\n{markdown}".strip()
    return markdown


def load_website_as_markdown_document(url: str) -> Document:
    """Fetch a website and return one markdown document for downstream chunking."""
    html, final_url, content_type = fetch_website_html(url)
    markdown = html_to_markdown(html, base_url=final_url)
    return Document(
        text=markdown,
        metadata={
            "source": final_url,
            "requested_url": url,
            "type": "website",
            "content_type": content_type,
        },
    )


def save_markdown_document(document: Document, path: Path, metadata_header: Iterable[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = list(metadata_header or [])
    body = document.text.strip()
    text = "\n".join([*header_lines, "", body]).strip() if header_lines else body
    path.write_text(text + "\n", encoding="utf-8")
    return path
