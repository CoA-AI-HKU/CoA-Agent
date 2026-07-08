from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .pdf_to_markdown import load_pdf_as_markdown


DEFAULT_PDF_ROOT = Path(__file__).resolve().parents[1] / "data" / "pdfs"
DEFAULT_MARKDOWN_ROOT = Path(__file__).resolve().parents[1] / "data" / "mds"


def discover_pdf_files(pdf_root: Path = DEFAULT_PDF_ROOT) -> List[Path]:
    return sorted(pdf_root.rglob("*.pdf"))


def resolve_markdown_path(pdf_path: Path, pdf_root: Path, markdown_root: Path) -> Path:
    relative_path = pdf_path.relative_to(pdf_root)
    return markdown_root.joinpath(relative_path).with_suffix(".md")


def convert_pdf_file(
    pdf_path: Path,
    markdown_root: Path = DEFAULT_MARKDOWN_ROOT,
    pdf_root: Path = DEFAULT_PDF_ROOT,
    overwrite: bool = False,
) -> Path:
    target_path = resolve_markdown_path(pdf_path, pdf_root=pdf_root, markdown_root=markdown_root)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    if target_path.exists() and not overwrite:
        return target_path

    document = load_pdf_as_markdown(pdf_path)
    target_path.write_text(document.text, encoding="utf-8")
    return target_path


def convert_pdf_directory(
    pdf_root: Path = DEFAULT_PDF_ROOT,
    markdown_root: Path = DEFAULT_MARKDOWN_ROOT,
    overwrite: bool = False,
) -> List[Path]:
    markdown_paths: List[Path] = []
    for pdf_path in discover_pdf_files(pdf_root):
        markdown_paths.append(convert_pdf_file(pdf_path, markdown_root=markdown_root, pdf_root=pdf_root, overwrite=overwrite))
    return markdown_paths


def main() -> None:
    pdf_root = DEFAULT_PDF_ROOT
    markdown_root = DEFAULT_MARKDOWN_ROOT
    markdown_root.mkdir(parents=True, exist_ok=True)

    converted = convert_pdf_directory(pdf_root=pdf_root, markdown_root=markdown_root)
    if converted:
        print(f"Converted {len(converted)} PDF(s) to markdown under {markdown_root}")
        for path in converted:
            print(f"  - {path}")
    else:
        print(f"No PDF files found in {pdf_root}")


if __name__ == "__main__":
    main()
