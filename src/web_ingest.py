from __future__ import annotations

import hashlib
import re
from collections import deque
from pathlib import Path
from urllib.parse import urldefrag, urlparse

from .web_to_markdown import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
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


def _slugify(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "website"


def markdown_path_for_url(url: str, markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT) -> Path:
    parsed = urlparse(url)
    host = _slugify(parsed.netloc)
    path = _slugify(parsed.path)
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:10]
    filename = f"{host}-{path}-{url_hash}.md" if path else f"{host}-{url_hash}.md"
    return markdown_root / filename


def _normalized_url(url: str) -> str:
    parsed = urlparse(urldefrag(url).url)
    if parsed.path == "/":
        parsed = parsed._replace(path="")
    return parsed.geturl()


def _same_site(url: str, root_url: str) -> bool:
    parsed_url = urlparse(url)
    parsed_root = urlparse(root_url)
    return parsed_url.scheme in {"http", "https"} and parsed_url.netloc.lower() == parsed_root.netloc.lower()


def _metadata_header(source: str, requested_url: str) -> list[str]:
    return [
        f"<!-- source: {source} -->",
        f"<!-- requested_url: {requested_url} -->",
        "<!-- type: website -->",
    ]


def convert_website_url(
    url: str,
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> Path:
    target_path = markdown_path_for_url(url, markdown_root=markdown_root)
    if target_path.exists() and not overwrite:
        return target_path

    document = load_website_as_markdown_document(url, timeout=timeout, max_bytes=max_bytes)
    source = document.metadata.get("source", url)
    requested_url = document.metadata.get("requested_url", url)
    return save_markdown_document(document, target_path, metadata_header=_metadata_header(source, requested_url))


def convert_website_urls(
    urls: list[str],
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[Path]:
    return [
        convert_website_url(url, markdown_root=markdown_root, overwrite=overwrite, timeout=timeout, max_bytes=max_bytes)
        for url in urls
    ]


def crawl_website(
    start_url: str,
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    max_pages: int = DEFAULT_MAX_CRAWL_PAGES,
    max_depth: int = DEFAULT_MAX_CRAWL_DEPTH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[Path]:
    start_url = _normalized_url(start_url)
    queue = deque([(start_url, 0)])
    seen = {start_url}
    converted: list[Path] = []

    while queue and len(converted) < max_pages:
        url, depth = queue.popleft()
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
        if overwrite or not target_path.exists():
            save_markdown_document(
                document,
                target_path,
                metadata_header=_metadata_header(final_url, url),
            )
        converted.append(target_path)

        if depth >= max_depth:
            continue

        for link in extract_links(html, base_url=final_url):
            normalized_link = _normalized_url(link)
            if normalized_link in seen or not _same_site(normalized_link, start_url):
                continue
            seen.add(normalized_link)
            queue.append((normalized_link, depth + 1))

    return converted


def crawl_website_urls(
    urls: list[str],
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
    max_pages_per_site: int = DEFAULT_MAX_CRAWL_PAGES,
    max_depth: int = DEFAULT_MAX_CRAWL_DEPTH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
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
        )
    print(f"Converted {len(converted)} website page(s) to markdown under {args.markdown_root}")
    for path in converted:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
