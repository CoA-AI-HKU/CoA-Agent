from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag, urljoin, urlparse
from urllib.request import Request, urlopen

from .pipeline.document import Document


DEFAULT_USER_AGENT = "Mozilla/5.0 (compatible; CoA-Agent-RAG/1.0; +https://example.local)"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_BYTES = 2_000_000
MIN_CONTENT_CHARS = 250
NOISE_ATTRIBUTE_KEYWORDS = {
    "breadcrumb",
    "cookie",
    "footer",
    "header",
    "language",
    "menu",
    "modal",
    "nav",
    "navbar",
    "pagination",
    "popup",
    "search",
    "share",
    "sidebar",
    "social",
    "subscribe",
    "toolbar",
    "widget",
}
SKIPPED_LINK_EXTENSIONS = {
    ".7z",
    ".avi",
    ".css",
    ".csv",
    ".doc",
    ".docx",
    ".gif",
    ".gz",
    ".ico",
    ".jpeg",
    ".jpg",
    ".js",
    ".json",
    ".mp3",
    ".mp4",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".rar",
    ".svg",
    ".tar",
    ".webm",
    ".webp",
    ".xls",
    ".xlsx",
    ".zip",
}


def _normalize_markdown(text: str) -> str:
    replacements = {
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¦ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ": "\"",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â": "\"",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã¢â‚¬Â¹Ãƒâ€¦Ã¢â‚¬Å“": "'",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¾Ãƒâ€šÃ‚Â¢": "'",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€¦Ã¢â‚¬Å“": "-",
        "ÃƒÆ’Ã†â€™Ãƒâ€šÃ‚Â¢ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡Ãƒâ€šÃ‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â": "-",
        "ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â ": " ",
        "AÃƒÆ’Ã†â€™Ãƒâ€¦Ã‚Â½ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â²": "AÃƒÆ’Ã…Â½Ãƒâ€šÃ‚Â²",
    }
    for bad, good in replacements.items():
        text = text.replace(bad, good)
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
    encodings = ["utf-8"]
    if charset_match and charset_match.group(1).lower() != "utf-8":
        encodings.append(charset_match.group(1))
    encodings.append("windows-1252")

    for encoding in encodings:
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def _request_headers(user_agent: str) -> dict[str, str]:
    return {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-HK,zh-Hant;q=0.9,en;q=0.7",
    }


def _fetch_website_html_with_requests(
    url: str,
    timeout: int,
    max_bytes: int,
    user_agent: str,
) -> tuple[str, str, str | None]:
    try:
        import requests
    except ImportError as exc:
        raise RuntimeError("requests is not installed") from exc

    try:
        with requests.get(url, headers=_request_headers(user_agent), timeout=timeout, stream=True) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type")
            if content_type and "html" not in content_type.lower():
                raise ValueError(f"Expected an HTML response from {url}, got Content-Type: {content_type}")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"Website response is larger than the {max_bytes} byte limit: {url}")
            return _decode_html(b"".join(chunks), content_type), response.url, content_type
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def fetch_website_html(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    user_agent: str = DEFAULT_USER_AGENT,
) -> tuple[str, str, str | None]:
    """Fetch a website and return decoded HTML, final URL, and content type."""
    if not _is_usable_url(url):
        raise ValueError(f"Expected an http(s) URL, got: {url}")

    try:
        return _fetch_website_html_with_requests(url, timeout=timeout, max_bytes=max_bytes, user_agent=user_agent)
    except RuntimeError as exc:
        if "requests is not installed" not in str(exc):
            raise

    request = Request(url, headers=_request_headers(user_agent))
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


def _is_probably_html_link(url: str) -> bool:
    path = urlparse(url).path.lower()
    return not any(path.endswith(extension) for extension in SKIPPED_LINK_EXTENSIONS)


class _LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return

        attr_map = {name.lower(): value or "" for name, value in attrs}
        href = attr_map.get("href", "").strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            return

        absolute_url = urljoin(self.base_url, href)
        absolute_url = urldefrag(absolute_url).url
        parsed = urlparse(absolute_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return
        if not _is_probably_html_link(absolute_url):
            return
        self.links.append(absolute_url)


def extract_links(html: str, base_url: str) -> list[str]:
    parser = _LinkExtractor(base_url=base_url)
    parser.feed(html)
    parser.close()
    return list(dict.fromkeys(parser.links))


def _element_text_length(element) -> int:
    text = element.get_text(" ", strip=True)
    return len(text)


def _element_link_density(element) -> float:
    text_length = max(_element_text_length(element), 1)
    link_text_length = sum(len(link.get_text(" ", strip=True)) for link in element.find_all("a"))
    return link_text_length / text_length


def _attr_looks_noisy(value: str) -> bool:
    normalized = value.lower()
    return any(keyword in normalized for keyword in NOISE_ATTRIBUTE_KEYWORDS)


def _extract_main_html_with_bs4(html: str) -> tuple[str, str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("beautifulsoup4 is not installed") from exc

    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""

    for selector in [
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "iframe",
        "nav",
        "footer",
        "header",
        "aside",
        "form",
        "button",
        "input",
        "select",
        "option",
    ]:
        for element in soup.select(selector):
            element.decompose()

    for element in list(soup.find_all(True)):
        classes = " ".join(element.get("class", []))
        element_id = str(element.get("id", ""))
        role = str(element.get("role", ""))
        if _attr_looks_noisy(" ".join([classes, element_id, role])):
            element.decompose()

    candidates = []
    for selector in [
        "main",
        "article",
        "[role='main']",
        ".entry-content",
        ".page-content",
        ".post-content",
        ".content",
        "#content",
    ]:
        candidates.extend(soup.select(selector))
    if soup.body:
        candidates.append(soup.body)

    best = None
    best_score = -1.0
    for candidate in candidates:
        text_length = _element_text_length(candidate)
        if text_length < 100:
            continue
        link_density = _element_link_density(candidate)
        heading_bonus = min(len(candidate.find_all(re.compile(r"^h[1-6]$"))) * 80, 400)
        paragraph_bonus = min(len(candidate.find_all("p")) * 40, 400)
        score = text_length + heading_bonus + paragraph_bonus - (link_density * text_length * 1.8)
        if score > best_score:
            best = candidate
            best_score = score

    if best is None:
        best = soup.body or soup
    return str(best), title


def extract_main_html(html: str) -> tuple[str, str]:
    try:
        return _extract_main_html_with_bs4(html)
    except RuntimeError:
        parser = _ReadableMarkdownParser()
        parser.feed(html)
        parser.close()
        return html, parser.title()


def _useful_text_length(text: str) -> int:
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"[*_`#>\-|]+", "", text)
    return len(re.sub(r"\s+", "", text))


def _title_from_html(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        parser = _ReadableMarkdownParser()
        parser.feed(html)
        parser.close()
        return parser.title()

    soup = BeautifulSoup(html, "html.parser")
    return _normalize_markdown(soup.title.get_text(" ", strip=True) if soup.title else "")


def _html_to_markdown_with_trafilatura(html: str, base_url: str | None) -> str | None:
    try:
        import trafilatura
    except ImportError:
        return None

    markdown = trafilatura.extract(
        html,
        url=base_url,
        output_format="markdown",
        include_comments=False,
        include_formatting=True,
        include_images=False,
        include_links=False,
        include_tables=True,
    )
    if not markdown or _useful_text_length(markdown) < 100:
        return None

    title = _title_from_html(html)
    markdown = clean_markdown_text(markdown)
    if title and markdown and not markdown.startswith("#"):
        markdown = f"# {title}\n\n{markdown}"
    return clean_markdown_text(markdown)


def _html_to_markdown_with_markdownify(html: str, base_url: str | None) -> str | None:
    try:
        from markdownify import markdownify
    except ImportError:
        return None

    main_html, extracted_title = extract_main_html(html)
    markdown = markdownify(
        main_html,
        heading_style="ATX",
        bullets="-",
        strip=["script", "style", "svg", "canvas", "iframe"],
    )
    if not markdown or _useful_text_length(markdown) < 100:
        return None

    title = _title_from_html(html) or extracted_title
    markdown = clean_markdown_text(markdown)
    if title and markdown and not markdown.startswith("#"):
        markdown = f"# {title}\n\n{markdown}"
    return clean_markdown_text(markdown)


def _html_to_markdown_with_stdlib_parser(html: str, base_url: str | None) -> str:
    html, extracted_title = extract_main_html(html)
    parser = _ReadableMarkdownParser(base_url=base_url)
    parser.feed(html)
    parser.close()
    markdown = parser.markdown()
    title = parser.title() or extracted_title

    if title and not markdown.startswith("#"):
        markdown = f"# {title}\n\n{markdown}".strip()
    return clean_markdown_text(markdown)


class _ReadableMarkdownParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "canvas", "iframe"}
    _NOISE_TAGS = {"nav", "footer", "aside", "header", "form", "button", "input", "select", "option"}
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
        self.noise_tag_stack: list[str] = []
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
            self.noise_tag_stack.append(tag)
            self.noise_depth += 1
            return
        classes = " ".join(attr_map.get("class", "").split())
        element_id = attr_map.get("id", "")
        role = attr_map.get("role", "")
        if _attr_looks_noisy(" ".join([classes, element_id, role])):
            self.noise_tag_stack.append(tag)
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
        if self.noise_tag_stack and self.noise_tag_stack[-1] == tag and self.noise_depth:
            self.noise_tag_stack.pop()
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


def _is_noise_line(line: str) -> bool:
    stripped = line.strip()
    normalized = stripped.lower()
    normalized_text = re.sub(r"[*_`#\-\[\]().:/|]+", " ", normalized)
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()

    if not stripped:
        return False
    if stripped.startswith("<!--") and stripped.endswith("-->"):
        return False
    if normalized_text in {
        "menu",
        "en",
        "a a a",
        "\u7e41",
        "\u7b80",
        "\u53c3",
        "\u89c0",
        "\u7533",
        "\u8acb",
        "\u53c2",
        "\u89c2",
        "\u8bf7",
    }:
        return True
    if re.fullmatch(r"[-*]\s*(\u7e41|\u7b80|en|a\s*a\s*a)", normalized):
        return True
    if len(stripped) <= 2 and not re.search(r"[A-Za-z0-9]", stripped):
        return True
    if re.fullmatch(r"\[[^\]]{1,40}\]\([^)]+\)", stripped):
        return True
    if re.fullmatch(r"(\u4e0a\u4e00\u9801|\u4e0b\u4e00\u9801|\u8fd4\u56de|\u66f4\u591a|\u8a73\u60c5|\u4e86\u89e3\u66f4\u591a|\u95b1\u8b80\u66f4\u591a|read more|more)", normalized_text):
        return True
    return False


def _is_link_only_line(line: str) -> bool:
    return bool(re.fullmatch(r"\s*[-*]?\s*\[[^\]]+\]\([^)]+\)\s*", line))


def _drop_link_heavy_blocks(text: str) -> str:
    kept_blocks: list[str] = []
    for block in re.split(r"\n\s*\n+", text):
        lines = [line for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        link_only = sum(1 for line in lines if _is_link_only_line(line))
        if len(lines) >= 3 and link_only / len(lines) >= 0.6:
            continue
        kept_blocks.append(block.strip())
    return "\n\n".join(kept_blocks)


def clean_markdown_text(markdown: str) -> str:
    """Remove website chrome that is not useful for retrieval."""
    cleaned_lines: list[str] = []
    previous_nonblank = ""
    previous_heading = ""

    markdown = _normalize_markdown(markdown)

    for line in markdown.splitlines():
        stripped = line.strip()
        if _is_noise_line(stripped):
            continue
        if stripped.startswith("<!--") and stripped.endswith("-->"):
            continue
        normalized_line = re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()
        if previous_heading and normalized_line == previous_heading:
            continue
        if stripped and stripped == previous_nonblank:
            continue
        cleaned_lines.append(line.rstrip())
        if stripped:
            previous_nonblank = stripped
            if stripped.startswith("#"):
                previous_heading = re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()

    text = "\n".join(cleaned_lines)
    text = _drop_link_heavy_blocks(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"(?m)^\s+$", "", text)
    return text.strip()


def html_to_markdown(html: str, base_url: str | None = None) -> str:
    """Convert website HTML into readable markdown suitable for chunking."""
    for converter in (
        _html_to_markdown_with_trafilatura,
        _html_to_markdown_with_markdownify,
    ):
        markdown = converter(html, base_url)
        if markdown:
            return markdown
    return _html_to_markdown_with_stdlib_parser(html, base_url)



def website_html_to_markdown_document(
    html: str,
    final_url: str,
    requested_url: str | None = None,
    content_type: str | None = None,
) -> Document:
    markdown = html_to_markdown(html, base_url=final_url)
    return Document(
        text=markdown,
        metadata={
            "source": final_url,
            "requested_url": requested_url or final_url,
            "type": "website",
            "content_type": content_type,
        },
    )


def load_website_as_markdown_document(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Document:
    """Fetch a website and return one markdown document for downstream chunking."""
    html, final_url, content_type = fetch_website_html(url, timeout=timeout, max_bytes=max_bytes)
    return website_html_to_markdown_document(
        html,
        final_url=final_url,
        requested_url=url,
        content_type=content_type,
    )


def save_markdown_document(document: Document, path: Path, metadata_header: Iterable[str] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header_lines = list(metadata_header or [])
    body = document.text.strip()
    text = "\n".join([*header_lines, "", body]).strip() if header_lines else body
    path.write_text(text + "\n", encoding="utf-8")
    return path
