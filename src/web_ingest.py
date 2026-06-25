from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import urlparse

from .web_to_markdown import load_website_as_markdown_document, save_markdown_document


DEFAULT_WEB_MARKDOWN_ROOT = Path(__file__).resolve().parents[1] / "data" / "mds" / "web"
DEFAULT_WEBSITE_LIST_PATH = Path(__file__).resolve().parents[1] / "data" / "websites.txt"


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


def convert_website_url(
    url: str,
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
) -> Path:
    target_path = markdown_path_for_url(url, markdown_root=markdown_root)
    if target_path.exists() and not overwrite:
        return target_path

    document = load_website_as_markdown_document(url)
    source = document.metadata.get("source", url)
    requested_url = document.metadata.get("requested_url", url)
    header = [
        f"<!-- source: {source} -->",
        f"<!-- requested_url: {requested_url} -->",
        "<!-- type: website -->",
    ]
    return save_markdown_document(document, target_path, metadata_header=header)


def convert_website_urls(
    urls: list[str],
    markdown_root: Path = DEFAULT_WEB_MARKDOWN_ROOT,
    overwrite: bool = False,
) -> list[Path]:
    return [
        convert_website_url(url, markdown_root=markdown_root, overwrite=overwrite)
        for url in urls
    ]


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
    args = parser.parse_args()

    urls = list(args.urls)
    if args.url_file.exists():
        urls.extend(load_urls_from_file(args.url_file))

    if not urls:
        parser.error(f"Provide at least one URL or add URLs to {args.url_file}")

    converted = convert_website_urls(urls, markdown_root=args.markdown_root, overwrite=args.overwrite)
    print(f"Converted {len(converted)} website page(s) to markdown under {args.markdown_root}")
    for path in converted:
        print(f"  - {path}")


if __name__ == "__main__":
    main()
