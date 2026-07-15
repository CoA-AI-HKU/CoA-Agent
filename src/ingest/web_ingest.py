from __future__ import annotations

import hashlib
import re
import time
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from .web_to_markdown import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    MIN_CONTENT_CHARS,
    extract_links,
    fetch_website_html,
    load_website_as_markdown_document,
    save_markdown_document,
    website_html_to_markdown_document,
)


DEFAULT_WEB_MARKDOWN_ROOT = Path(__file__).resolve().parents[1] / "data" / "mds" / "web"
DEFAULT_WEBSITE_LIST_PATH = Path(__file__).resolve().parents[1] / "data" / "websites.txt"
DEFAULT_MAX_CRAWL_PAGES = 100
DEFAULT_MAX_CRAWL_DEPTH = 4
DEFAULT_CRAWL_SCOPE = "path-prefix"
DEFAULT_CRAWL_DELAY_SECONDS = 0.2
DEFAULT_MIN_CONTENT_CHARS = MIN_CONTENT_CHARS
SKIP_PATH_CONTAINS = {
    "/feed",
    "/wp-json",
    "/xmlrpc",
}
SKIP_PATH_SUFFIXES = {
    "/print",
    "/embed",
}


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "website"


def _slugify_host(value: str) -> str:
    host = value.lower()
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    host = host.split(":", 1)[0]
    host = re.sub(r"[^a-z0-9.]+", "-", host).strip("-.")
    return host or "website"


def markdown_path_for_url(url: str, markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT) -> Path:
    parsed = urlparse(url)
    host = _slugify_host(parsed.netloc)
    path_segments = [_slugify(segment) for segment in parsed.path.split("/") if segment.strip()]
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    if path_segments:
        *parents, leaf = path_segments
        filename = f"{leaf}-{url_hash}.md"
        return markdown_root.joinpath(host, *parents, filename)
    return markdown_root / host / f"index-{url_hash}.md"


def _normalized_url(url: str) -> str:
    parsed = urlparse(urldefrag(url).url)
    if parsed.path == "/":
        parsed = parsed._replace(path="")
    return parsed.geturl()


def _same_site(url: str, root_url: str) -> bool:
    parsed_url = urlparse(url)
    parsed_root = urlparse(root_url)
    return parsed_url.scheme in {"http", "https"} and parsed_url.netloc.lower() == parsed_root.netloc.lower()


def _path_prefix(url: str) -> str:
    path = urlparse(url).path
    if not path or path == "/":
        return "/"
    if path.endswith("/"):
        return path
    return f"{path.rsplit('/', 1)[0]}/"


def _within_crawl_scope(url: str, root_url: str, crawl_scope: str) -> bool:
    if not _same_site(url, root_url):
        return False
    if crawl_scope == "same-site":
        return True
    if crawl_scope == "path-prefix":
        prefix = _path_prefix(root_url)
        path = urlparse(url).path
        if not path.startswith(prefix):
            return False
        if prefix != "/" and path.count(prefix) > 1:
            return False
        return True
    raise ValueError(f"Unknown crawl scope: {crawl_scope}")


def _should_skip_crawl_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    if any(fragment in path for fragment in SKIP_PATH_CONTAINS):
        return True
    if any(path.endswith(suffix) for suffix in SKIP_PATH_SUFFIXES):
        return True
    return False


def _metadata_header(source: str, requested_url: str) -> list[str]:
    return [f"<!-- source: {source} -->", f"<!-- requested_url: {requested_url} -->"]


def _content_chars(markdown: str) -> int:
    text = re.sub(r"```.*?```", "", markdown, flags=re.DOTALL)
    text = re.sub(r"\[[^\]]+\]\([^)]+\)", "", text)
    text = re.sub(r"#+", "", text)
    return len(re.sub(r"\s+", "", text))


def _is_useful_markdown(markdown: str, min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS) -> bool:
    if _content_chars(markdown) < min_content_chars:
        return False
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    if not lines:
        return False
    link_lines = sum(1 for line in lines if re.fullmatch(r"[-*]?\s*\[[^\]]+\]\([^)]+\)", line))
    return link_lines / len(lines) < 0.5


def convert_website_url(
    url: str,
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> Path | None:
    target_path = markdown_path_for_url(url, markdown_root=markdown_root)
    if target_path.exists() and not overwrite:
        return target_path

    # Resolve through the historical public module so existing integrations
    # can still patch or wrap the fetch boundary.
    from src import web_to_markdown as public_web

    try:
        html, final_url, content_type = public_web.fetch_website_html(
            url, timeout=timeout, max_bytes=max_bytes
        )
    except TypeError:
        # Preserve compatibility with older one-argument fetch adapters.
        html, final_url, content_type = public_web.fetch_website_html(url)
    document = website_html_to_markdown_document(
        html,
        final_url=final_url,
        requested_url=url,
        content_type=content_type,
    )
    if not _is_useful_markdown(document.text, min_content_chars=min_content_chars):
        print(f"Skipping {url}: not enough useful content after cleaning")
        return None
    source = document.metadata.get("source", url)
    requested_url = document.metadata.get("requested_url", url)
    return save_markdown_document(document, target_path, metadata_header=_metadata_header(source, requested_url))


def convert_website_urls(
    urls: list[str],
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> list[Path]:
    converted: list[Path] = []
    for url in urls:
        target_path = convert_website_url(
            url,
            markdown_root=markdown_root,
            overwrite=overwrite,
            timeout=timeout,
            max_bytes=max_bytes,
            min_content_chars=min_content_chars,
        )
        if target_path is not None:
            converted.append(target_path)
    return converted


def crawl_website(
    start_url: str,
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    max_pages: int = DEFAULT_MAX_CRAWL_PAGES,
    max_depth: int = DEFAULT_MAX_CRAWL_DEPTH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    crawl_scope: str = DEFAULT_CRAWL_SCOPE,
    delay_seconds: float = DEFAULT_CRAWL_DELAY_SECONDS,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> list[Path]:
    start_url = _normalized_url(start_url)
    queue = deque([(start_url, 0)])
    seen = {start_url}
    converted: list[Path] = []
    processed = 0
    max_fetches = max(max_pages * 3, max_pages)

    while queue and len(converted) < max_pages and processed < max_fetches:
        url, depth = queue.popleft()
        processed += 1
        try:
            html, final_url, content_type = fetch_website_html(url, timeout=timeout, max_bytes=max_bytes)
        except RuntimeError as exc:
            print(f"Skipping {url}: {exc}")
            continue

        final_url = _normalized_url(final_url)
        document = website_html_to_markdown_document(
            html,
            final_url=final_url,
            requested_url=url,
            content_type=content_type,
        )
        target_path = markdown_path_for_url(final_url, markdown_root=markdown_root)
        is_useful = _is_useful_markdown(document.text, min_content_chars=min_content_chars)
        if is_useful:
            if overwrite or not target_path.exists():
                save_markdown_document(
                    document,
                    target_path,
                    metadata_header=_metadata_header(final_url, url),
                )
            converted.append(target_path)
            print(f"[{len(converted)}/{max_pages}] {final_url}")
        else:
            print(f"Skipping {final_url}: not enough useful content after cleaning")

        if depth >= max_depth:
            if delay_seconds > 0:
                time.sleep(delay_seconds)
            continue

        for link in extract_links(html, base_url=final_url):
            normalized_link = _normalized_url(link)
            if normalized_link in seen:
                continue
            if _should_skip_crawl_url(normalized_link):
                continue
            if not _within_crawl_scope(normalized_link, start_url, crawl_scope):
                continue
            seen.add(normalized_link)
            queue.append((normalized_link, depth + 1))

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    return converted


def crawl_website_urls(
    urls: list[str],
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    max_pages_per_site: int = DEFAULT_MAX_CRAWL_PAGES,
    max_depth: int = DEFAULT_MAX_CRAWL_DEPTH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    crawl_scope: str = DEFAULT_CRAWL_SCOPE,
    delay_seconds: float = DEFAULT_CRAWL_DELAY_SECONDS,
    min_content_chars: int = DEFAULT_MIN_CONTENT_CHARS,
) -> list[Path]:
    converted: list[Path] = []
    for url in urls:
        converted.extend(
            crawl_website(
                url,
                markdown_root=markdown_root,
                overwrite=overwrite,
                max_pages=max_pages_per_site,
                max_depth=max_depth,
                timeout=timeout,
                max_bytes=max_bytes,
                crawl_scope=crawl_scope,
                delay_seconds=delay_seconds,
                min_content_chars=min_content_chars,
            )
        )
    return converted


def load_urls_from_file(path: Path) -> list[str]:
    return [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fetch website pages and save readable markdown for RAG indexing")
    parser.add_argument("urls", nargs="*", help="HTTP/HTTPS page URLs to convert")
    parser.add_argument("--url-file", type=Path, default=DEFAULT_WEBSITE_LIST_PATH, help="Text file containing one URL per line")
    parser.add_argument("--markdown-root", type=Path, default=DEFAULT_WEB_MARKDOWN_ROOT, help="Directory for generated markdown")
    parser.add_argument("--overwrite", action="store_true", help="Refresh markdown even if the target file exists")
    parser.add_argument("--no-crawl", action="store_true", help="Only convert the provided URL(s), without following same-site links")
    parser.add_argument("--max-pages-per-site", type=int, default=DEFAULT_MAX_CRAWL_PAGES, help="Maximum pages to crawl from each starting website")
    parser.add_argument("--max-depth", type=int, default=DEFAULT_MAX_CRAWL_DEPTH, help="Maximum link depth to crawl from each starting website")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Fetch timeout in seconds per page")
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES, help="Maximum bytes to read per page")
    parser.add_argument("--delay", type=float, default=DEFAULT_CRAWL_DELAY_SECONDS, help="Delay between page fetches")
    parser.add_argument("--min-content-chars", type=int, default=DEFAULT_MIN_CONTENT_CHARS, help="Skip pages with less useful text after cleaning")
    parser.add_argument(
        "--crawl-scope",
        choices=["path-prefix", "same-site"],
        default=DEFAULT_CRAWL_SCOPE,
        help="Limit crawling to the starting URL path prefix, or allow the whole same site",
    )
    args = parser.parse_args()

    urls = list(args.urls)
    if args.url_file.exists():
        urls.extend(load_urls_from_file(args.url_file))

    if not urls:
        parser.error(f"Provide at least one URL or add URLs to {args.url_file}")

    if args.no_crawl:
        converted = convert_website_urls(
            urls,
            markdown_root=args.markdown_root,
            overwrite=args.overwrite,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            min_content_chars=args.min_content_chars,
        )
    else:
        converted = crawl_website_urls(
            urls,
            markdown_root=args.markdown_root,
            overwrite=args.overwrite,
            max_pages_per_site=args.max_pages_per_site,
            max_depth=args.max_depth,
            timeout=args.timeout,
            max_bytes=args.max_bytes,
            crawl_scope=args.crawl_scope,
            delay_seconds=args.delay,
            min_content_chars=args.min_content_chars,
        )
    print(f"Converted {len(converted)} website page(s) to markdown under {args.markdown_root}")
    for path in converted:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
