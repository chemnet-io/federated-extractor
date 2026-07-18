"""PDF text extraction utilities."""

import argparse
from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess
from typing import List, Union

import fitz


@dataclass(frozen=True)
class PageText:
    """Text extracted from a single PDF page."""

    page_number: int
    text: str


@dataclass(frozen=True)
class PdfText:
    """Text extracted from a PDF document."""

    source_path: Path
    pages: List[PageText]

    @property
    def text(self) -> str:
        return "\n\n".join(page.text for page in self.pages if page.text)


def extract_pdf_text(
    pdf_path: Union[str, Path],
    use_ocr: bool = True,
    ocr_output_dir: Union[str, Path] = "outputs/ocr",
) -> PdfText:
    """Extract plain text from a PDF file.

    Returns page-level text so downstream extractors can keep provenance.
    If no embedded text is found, OCR is attempted when enabled.
    """

    source_path = Path(pdf_path)
    extracted = _extract_embedded_pdf_text(source_path)
    if extracted.text or not use_ocr:
        return extracted

    ocr_pdf_path = _create_ocr_pdf(source_path, ocr_output_dir)
    return _extract_embedded_pdf_text(ocr_pdf_path)


def _extract_embedded_pdf_text(source_path: Path) -> PdfText:
    pages: List[PageText] = []

    with fitz.open(source_path) as document:
        for page_index, page in enumerate(document, start=1):
            pages.append(
                PageText(
                    page_number=page_index,
                    text=page.get_text("text").strip(),
                )
            )

    return PdfText(source_path=source_path, pages=pages)


def _create_ocr_pdf(
    source_path: Path,
    ocr_output_dir: Union[str, Path],
) -> Path:
    ocrmypdf_path = shutil.which("ocrmypdf")
    if not ocrmypdf_path:
        raise RuntimeError(
            "No embedded PDF text was found, and OCR fallback requires the "
            "'ocrmypdf' command. Install OCRmyPDF and Tesseract, then retry."
        )

    output_path = Path(ocr_output_dir) / (source_path.stem + ".ocr.pdf")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        [
            ocrmypdf_path,
            "--skip-text",
            str(source_path),
            str(output_path),
        ],
        check=True,
    )
    return output_path


def export_pdf_text(
    pdf_path: Union[str, Path],
    output_dir: Union[str, Path] = "outputs/pdf_text",
    use_ocr: bool = True,
    ocr_output_dir: Union[str, Path] = "outputs/ocr",
) -> Path:
    """Extract text from a PDF and write it to a .txt file."""

    extracted = extract_pdf_text(
        pdf_path,
        use_ocr=use_ocr,
        ocr_output_dir=ocr_output_dir,
    )
    output_path = Path(output_dir) / (Path(pdf_path).stem + ".txt")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(extracted.text, encoding="utf-8")
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from a PDF file.")
    parser.add_argument("pdf_path", help="Path to the input PDF file.")
    parser.add_argument(
        "--output-dir",
        default="outputs/pdf_text",
        help="Directory where the extracted .txt file will be written.",
    )
    parser.add_argument(
        "--ocr-output-dir",
        default="outputs/ocr",
        help="Directory where OCR'd PDFs will be written when OCR is needed.",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback when no embedded text is found.",
    )
    args = parser.parse_args()

    output_path = export_pdf_text(
        args.pdf_path,
        output_dir=args.output_dir,
        use_ocr=not args.no_ocr,
        ocr_output_dir=args.ocr_output_dir,
    )
    print(output_path)


if __name__ == "__main__":
    main()
