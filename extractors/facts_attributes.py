"""Fact and attribute knowledge extractor.

This rule-based extractor focuses on direct claims such as chemical formulas,
molar masses, measured values, and methods used in an experiment.
"""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Union

from extractors.text_preprocessing import clean_entity, clean_value, split_list_items, split_sentences


@dataclass(frozen=True)
class FactAttribute:
    """A direct fact or attribute found in text."""

    entity: str
    attribute: str
    value: str
    unit: Optional[str] = None
    evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


FORMULA_PATTERN = re.compile(
    r"\b(?P<entity>[A-Z][A-Za-z0-9 -]+?)\s+has\s+the\s+molecular\s+formula\s+"
    r"(?P<value>[A-Z][A-Za-z0-9]+)\b",
    re.IGNORECASE,
)

MOLAR_MASS_PATTERN = re.compile(
    r"\b(?P<entity>[A-Z][A-Za-z0-9 -]+?)\s+has\b[^.!?]*?\ba\s+molar\s+mass\s+of\s+"
    r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>g/mol)\b",
    re.IGNORECASE,
)

MEASUREMENT_PATTERN = re.compile(
    r"\b(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>g|mg|kg|mL|L|minutes?|hours?|C|°C)\s+"
    r"of\s+(?P<entity>[A-Za-z][A-Za-z0-9 -]+?)"
    r"(?=\s+(?:was|were|is|are|in|and|with)|[.,;:]|$)",
    re.IGNORECASE,
)

METHOD_PATTERN = re.compile(
    r"\b(?P<method>[A-Za-z][A-Za-z -]+?)\s+was\s+used\s+to\s+"
    r"(?P<purpose>[A-Za-z][A-Za-z -]+)",
    re.IGNORECASE,
)

COMPRISES_PATTERN = re.compile(
    r"\b(?P<entity>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:may\s+)?comprises?\s+(?P<value>[^.!?]+)",
    re.IGNORECASE,
)

CONFIGURED_TO_PATTERN = re.compile(
    r"\b(?P<entity>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:is|are|may be)\s+configured\s+to\s+(?P<value>[^.!?]+)",
    re.IGNORECASE,
)

USED_TO_PATTERN = re.compile(
    r"\b(?P<entity>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:is|are|may be|can be)\s+used\s+to\s+(?P<value>[^.!?]+)",
    re.IGNORECASE,
)


def extract_facts_and_attributes(text: str) -> List[FactAttribute]:
    """Extract direct facts and measured attributes from plain text."""

    facts: List[FactAttribute] = []

    for sentence in split_sentences(text):
        facts.extend(_extract_formula_facts(sentence))
        facts.extend(_extract_molar_mass_facts(sentence))
        facts.extend(_extract_measurement_facts(sentence))
        facts.extend(_extract_method_facts(sentence))
        facts.extend(_extract_composition_facts(sentence))
        facts.extend(_extract_capability_facts(sentence))
        facts.extend(_extract_usage_facts(sentence))

    return facts


def export_facts_and_attributes(
    text_path: Union[str, Path],
    output_dir: Union[str, Path] = "outputs/knowledge",
) -> Path:
    """Extract facts from a .txt file and write JSON output."""

    source_path = Path(text_path)
    text = source_path.read_text(encoding="utf-8")
    facts = extract_facts_and_attributes(text)

    output_path = Path(output_dir) / (source_path.stem + ".facts_attributes.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([fact.to_dict() for fact in facts], indent=2),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract fact and attribute knowledge from a text file."
    )
    parser.add_argument("text_path", help="Path to the input .txt file.")
    parser.add_argument(
        "--output-dir",
        default="outputs/knowledge",
        help="Directory where the extracted JSON file will be written.",
    )
    args = parser.parse_args()

    output_path = export_facts_and_attributes(args.text_path, args.output_dir)
    print(output_path)


def _extract_formula_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in FORMULA_PATTERN.finditer(sentence):
        facts.append(
            FactAttribute(
                entity=_clean_text(match.group("entity")),
                attribute="molecular formula",
                value=match.group("value"),
                evidence=sentence,
            )
        )
    return facts


def _extract_molar_mass_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in MOLAR_MASS_PATTERN.finditer(sentence):
        facts.append(
            FactAttribute(
                entity=_clean_text(match.group("entity")),
                attribute="molar mass",
                value=match.group("value"),
                unit=match.group("unit"),
                evidence=sentence,
            )
        )
    return facts


def _extract_measurement_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in MEASUREMENT_PATTERN.finditer(sentence):
        unit = match.group("unit")
        facts.append(
            FactAttribute(
                entity=_clean_text(match.group("entity")),
                attribute=_attribute_for_unit(unit),
                value=match.group("value"),
                unit=unit,
                evidence=sentence,
            )
        )
    return facts


def _extract_method_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in METHOD_PATTERN.finditer(sentence):
        facts.append(
            FactAttribute(
                entity=_clean_text(match.group("method")),
                attribute="used for",
                value=_clean_text(match.group("purpose")),
                evidence=sentence,
            )
        )
    return facts


def _extract_composition_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in COMPRISES_PATTERN.finditer(sentence):
        entity = clean_entity(match.group("entity"))
        if _is_noisy_phrase(entity):
            continue
        for value in split_list_items(clean_value(match.group("value"))):
            if _is_noisy_phrase(value):
                continue
            facts.append(
                FactAttribute(
                    entity=entity,
                    attribute="comprises",
                    value=value,
                    evidence=sentence,
                )
            )
    return facts


def _extract_capability_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in CONFIGURED_TO_PATTERN.finditer(sentence):
        entity = clean_entity(match.group("entity"))
        value = clean_value(match.group("value"))
        if _is_noisy_phrase(entity) or _is_noisy_phrase(value):
            continue
        facts.append(
            FactAttribute(
                entity=entity,
                attribute="configured to",
                value=value,
                evidence=sentence,
            )
        )
    return facts


def _extract_usage_facts(sentence: str) -> List[FactAttribute]:
    facts: List[FactAttribute] = []
    for match in USED_TO_PATTERN.finditer(sentence):
        entity = clean_entity(match.group("entity"))
        value = clean_value(match.group("value"))
        if _is_noisy_phrase(entity) or _is_noisy_phrase(value):
            continue
        facts.append(
            FactAttribute(
                entity=entity,
                attribute="used to",
                value=value,
                evidence=sentence,
            )
        )
    return facts


def _attribute_for_unit(unit: str) -> str:
    normalized_unit = unit.lower()
    if normalized_unit in {"g", "mg", "kg"}:
        return "mass"
    if normalized_unit in {"ml", "l"}:
        return "volume"
    if normalized_unit in {"minute", "minutes", "hour", "hours"}:
        return "time"
    if normalized_unit in {"c", "°c"}:
        return "temperature"
    return "measurement"


def _clean_text(value: str) -> str:
    return value.strip(" .,:;")


def _clean_entity(value: str) -> str:
    value = _clean_text(value)
    return re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)


def _is_noisy_phrase(value: str) -> bool:
    normalized = " ".join(value.lower().split())
    if len(normalized) < 3:
        return True
    if len(normalized.split()) > 18:
        return True
    noisy_fragments = [
        "wo 2023/",
        "pct/",
        "one or more",
        "and/or",
        "such as",
        "e.g",
    ]
    return any(fragment in normalized for fragment in noisy_fragments)


if __name__ == "__main__":
    main()
