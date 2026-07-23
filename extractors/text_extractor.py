import argparse
from pathlib import Path

import pymupdf


MINIMUM_TEXT_CHARACTERS = 30


def has_meaningful_text(text: str) -> bool:
    """
    Return True when the normally extracted text contains
    enough letters or numbers to be considered useful.
    """

    alphanumeric_characters = sum(
        character.isalnum()
        for character in text
    )

    return alphanumeric_characters >= MINIMUM_TEXT_CHARACTERS


def extract_page_text(
    page,
    language: str = "eng",
    dpi: int = 300,
    force_ocr: bool = False,
) -> tuple[str, bool]:
    """
    Extract text from one page.

    Normal extraction is attempted first. OCR is used when
    little or no readable text is found, or when force_ocr=True.

    Returns:
        A tuple containing:
        - extracted text
        - whether OCR was used
    """

    normal_text = page.get_text("text", sort=True).strip()

    if not force_ocr and has_meaningful_text(normal_text):
        return normal_text, False

    try:
        ocr_text_page = page.get_textpage_ocr(
            language=language,
            dpi=dpi,
            full=True,
        )

        ocr_text = page.get_text(
            "text",
            textpage=ocr_text_page,
            sort=True,
        ).strip()

        return ocr_text, True

    except Exception as error:
        raise RuntimeError(
            "OCR failed. Make sure Tesseract and the requested "
            f"language are installed. Original error: {error}"
        ) from error


def extract_text_from_pdf(
    pdf_path: str,
    language: str = "eng",
    force_ocr: bool = False,
) -> tuple[str, list[int]]:
    """
    Extract text from every page of a PDF.

    Returns:
        - combined document text
        - page numbers on which OCR was used
    """

    path = Path(pdf_path)

    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file: {pdf_path}")

    extracted_pages = []
    ocr_pages = []

    try:
        with pymupdf.open(path) as document:
            if document.needs_pass:
                raise ValueError(
                    "The PDF is password-protected and cannot be read."
                )

            for page_number, page in enumerate(document, start=1):
                try:
                    page_text, used_ocr = extract_page_text(
                        page,
                        language=language,
                        force_ocr=force_ocr,
                    )
                except Exception as error:
                    raise RuntimeError(
                        f"Could not process page {page_number}: {error}"
                    ) from error

                extracted_pages.append(page_text)

                if used_ocr:
                    ocr_pages.append(page_number)

        return "\n\n".join(extracted_pages), ocr_pages

    except (FileNotFoundError, ValueError, RuntimeError):
        raise

    except Exception as error:
        raise RuntimeError(
            f"Could not open or process the PDF: {error}"
        ) from error


def save_text_to_file(text: str, output_path: str) -> None:
    """Save extracted text as UTF-8."""

    path = Path(output_path)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract text from a PDF, using OCR automatically "
            "for scanned pages."
        )
    )

    parser.add_argument(
        "pdf_path",
        nargs="?",
        default="test01.pdf",
        help="Path to the input PDF",
    )

    parser.add_argument(
        "-o",
        "--output",
        help="Output text-file path",
    )

    parser.add_argument(
        "--language",
        default="eng",
        help="Tesseract language, such as eng or eng+deu",
    )

    parser.add_argument(
        "--force-ocr",
        action="store_true",
        help="Use OCR on every page",
    )

    arguments = parser.parse_args()

    input_path = Path(arguments.pdf_path)

    output_path = (
        Path(arguments.output)
        if arguments.output
        else input_path.with_suffix(".txt")
    )

    text, ocr_pages = extract_text_from_pdf(
        str(input_path),
        language=arguments.language,
        force_ocr=arguments.force_ocr,
    )

    save_text_to_file(text, str(output_path))

    print(f"Text successfully saved to: {output_path}")

    if ocr_pages:
        print(f"OCR was used on pages: {ocr_pages}")
    else:
        print("OCR was not needed; embedded text was available.")


if __name__ == "__main__":
    main()