"""Shared text cleanup for knowledge extractors."""

import re
from typing import List


HEADER_PATTERNS = [
    re.compile(r"^\s*WO\s+\d{4}/\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*WO\s+\d{4}/\d+\s+PCT/[A-Z]{2}\d+/\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*PCT/[A-Z]{2}\d+/\d+\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),
    re.compile(r"^\s*\([0-9]{2}\)\s+.*$"),
    re.compile(r"^\s*world intellectual property.*$", re.IGNORECASE),
    re.compile(r"^\s*international bureau\s*$", re.IGNORECASE),
    re.compile(r"^\s*international publication.*$", re.IGNORECASE),
    re.compile(r"^\s*designated states.*$", re.IGNORECASE),
]

INLINE_NOISE_PATTERNS = [
    re.compile(r"\bWO\s+\d{4}/\d+\b", re.IGNORECASE),
    re.compile(r"\bPCT/[A-Z]{2}\d+/\d+\b", re.IGNORECASE),
]


def clean_extracted_text(text: str) -> str:
    """Remove common OCR/PDF header artifacts and normalize whitespace."""

    cleaned_lines: List[str] = []
    for line in text.splitlines():
        line = _clean_line(line)
        if not line:
            continue
        if any(pattern.search(line) for pattern in HEADER_PATTERNS):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines)
    for pattern in INLINE_NOISE_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    cleaned = re.sub(r"(?<=\w)-\s+(?=\w)", "", cleaned)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def split_sentences(text: str) -> List[str]:
    """Split cleaned text into rough sentences for rule-based extractors."""

    normalized = " ".join(clean_extracted_text(text).split())
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", normalized)
        if sentence.strip()
    ]


def split_list_items(value: str) -> List[str]:
    """Split semicolon/comma/and-separated object lists into smaller phrases."""

    parts = re.split(r"\s*;\s*|\s*,\s+and\s+", value)
    return [clean_value(part) for part in parts if clean_value(part)]


def trim_leading_context(value: str) -> str:
    """Remove common lead-in phrases captured before the actual entity."""

    value = value.strip(" .,:;")
    patterns = [
        r"^.*?\bdescribes\s+",
        r"^.*?\bmay\s+comprise\s+",
        r"^.*?\bcomprises?\s+",
        r"^.*?\bincludes\s+",
        r"^.*?\bhas\s+",
        r"^.*?\ballows?\s+",
    ]
    for pattern in patterns:
        value = re.sub(pattern, "", value, flags=re.IGNORECASE)
    return value.strip(" .,:;")


def clean_entity(value: str) -> str:
    """Normalize an extracted entity phrase."""

    value = trim_leading_context(value)
    value = re.sub(r"\bthat$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bfurther$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bmay$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bto\s+efficiently$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\bare\s+configured\s+for\s+the$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)
    return _clean_line(value).strip(" .,:;")


def clean_value(value: str) -> str:
    """Normalize an extracted object/value phrase."""

    value = _clean_line(value).strip(" .,:;")
    value = re.sub(r"^(?:and\s+)?(?:the|a|an|of)\s+", "", value, flags=re.IGNORECASE)
    value = re.split(r"\s+\bcomprising\b\s+|\s+\bconfigured\s+to\b\s+", value, maxsplit=1, flags=re.IGNORECASE)[0]
    return value.strip(" .,:;")


def _clean_line(line: str) -> str:
    line = line.replace("Ï", "fi")
    line = line.replace("ﬁ", "fi")
    line = line.replace("ﬂ", "fl")
    line = re.sub(r"\s+", " ", line)
    return line.strip()
