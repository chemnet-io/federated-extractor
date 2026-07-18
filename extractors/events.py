"""Event knowledge extractor.

This rule-based extractor focuses on actions and processes described in
scientific or patent-style text.
"""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Dict, List, Optional, Union

from extractors.text_preprocessing import clean_entity, clean_value, split_sentences


@dataclass(frozen=True)
class Event:
    """An action or process found in text."""

    event_type: str
    trigger: str
    actor: Optional[str] = None
    action: Optional[str] = None
    target: Optional[str] = None
    context: Optional[str] = None
    evidence: Optional[str] = None

    def to_dict(self) -> Dict[str, Optional[str]]:
        return asdict(self)


EVENT_VERBS = {
    "perform": "Operation",
    "performs": "Operation",
    "performed": "Operation",
    "execute": "Execution",
    "executes": "Execution",
    "executed": "Execution",
    "receive": "DataTransfer",
    "receives": "DataTransfer",
    "received": "DataTransfer",
    "return": "DataTransfer",
    "returns": "DataTransfer",
    "returned": "DataTransfer",
    "transfer": "DataTransfer",
    "transfers": "DataTransfer",
    "transferred": "DataTransfer",
    "store": "Storage",
    "stores": "Storage",
    "stored": "Storage",
    "load": "Storage",
    "loads": "Storage",
    "loaded": "Storage",
    "generate": "Generation",
    "generates": "Generation",
    "generated": "Generation",
    "compute": "Computation",
    "computes": "Computation",
    "computed": "Computation",
    "process": "Processing",
    "processes": "Processing",
    "processed": "Processing",
    "controls": "Control",
    "controlled": "Control",
    "mask": "Masking",
    "masks": "Masking",
    "masked": "Masking",
    "encrypt": "Encryption",
    "encrypts": "Encryption",
    "encrypted": "Encryption",
    "decrypt": "Decryption",
    "decrypts": "Decryption",
    "decrypted": "Decryption",
}

VERB_PATTERN = "|".join(sorted(EVENT_VERBS, key=len, reverse=True))

ACTIVE_EVENT_PATTERN = re.compile(
    r"\b(?P<actor>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:may\s+|can\s+|also\s+|then\s+|effectively\s+)?"
    r"(?P<trigger>" + VERB_PATTERN + r")\s+"
    r"(?P<target>[^.!?]+)",
    re.IGNORECASE,
)

CONFIGURED_EVENT_PATTERN = re.compile(
    r"\b(?P<actor>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:is|are|may be|can be)\s+configured\s+to\s+"
    r"(?P<trigger>" + VERB_PATTERN + r")\s+"
    r"(?P<target>[^.!?]+)",
    re.IGNORECASE,
)

USED_EVENT_PATTERN = re.compile(
    r"\b(?P<actor>(?:[Tt]he|[Aa]n?)?\s*[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:is|are|may be|can be)\s+used\s+to\s+"
    r"(?P<trigger>" + VERB_PATTERN + r")\s+"
    r"(?P<target>[^.!?]+)",
    re.IGNORECASE,
)

PASSIVE_EVENT_PATTERN = re.compile(
    r"\b(?P<target>[A-Za-z][A-Za-z0-9 ()/-]{0,90}?)\s+"
    r"(?:may\s+|can\s+)?be\s+"
    r"(?P<trigger>" + VERB_PATTERN + r")\s+"
    r"(?:by\s+(?P<actor>[A-Za-z][A-Za-z0-9 ()/-]+))?",
    re.IGNORECASE,
)


def extract_events(text: str) -> List[Event]:
    """Extract events from plain text."""

    events: List[Event] = []

    for sentence in split_sentences(text):
        events.extend(_extract_configured_events(sentence))
        events.extend(_extract_used_events(sentence))
        events.extend(_extract_active_events(sentence))
        events.extend(_extract_passive_events(sentence))

    return _deduplicate_events(events)


def export_events(
    text_path: Union[str, Path],
    output_dir: Union[str, Path] = "outputs/knowledge",
) -> Path:
    """Extract events from a .txt file and write JSON output."""

    source_path = Path(text_path)
    text = source_path.read_text(encoding="utf-8")
    events = extract_events(text)

    output_path = Path(output_dir) / (source_path.stem + ".events.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([event.to_dict() for event in events], indent=2),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract events from a text file.")
    parser.add_argument("text_path", help="Path to the input .txt file.")
    parser.add_argument(
        "--output-dir",
        default="outputs/knowledge",
        help="Directory where the extracted JSON file will be written.",
    )
    args = parser.parse_args()

    output_path = export_events(args.text_path, args.output_dir)
    print(output_path)


def _extract_configured_events(sentence: str) -> List[Event]:
    return _extract_action_pattern(sentence, CONFIGURED_EVENT_PATTERN, "configured to")


def _extract_used_events(sentence: str) -> List[Event]:
    return _extract_action_pattern(sentence, USED_EVENT_PATTERN, "used to")


def _extract_action_pattern(
    sentence: str,
    pattern: re.Pattern,
    context: str,
) -> List[Event]:
    events: List[Event] = []
    for match in pattern.finditer(sentence):
        trigger = match.group("trigger").lower()
        actor = clean_entity(match.group("actor"))
        target = clean_value(match.group("target"))
        if _is_noisy(actor) or _is_noisy(target):
            continue
        events.append(
            Event(
                event_type=EVENT_VERBS[trigger],
                trigger=trigger,
                actor=actor,
                action=trigger,
                target=target,
                context=context,
                evidence=sentence,
            )
        )
    return events


def _extract_active_events(sentence: str) -> List[Event]:
    events: List[Event] = []
    for match in ACTIVE_EVENT_PATTERN.finditer(sentence):
        trigger = match.group("trigger").lower()
        actor = clean_entity(match.group("actor"))
        target = clean_value(match.group("target"))
        if _is_noisy(actor) or _is_noisy(target):
            continue
        events.append(
            Event(
                event_type=EVENT_VERBS[trigger],
                trigger=trigger,
                actor=actor,
                action=trigger,
                target=target,
                evidence=sentence,
            )
        )
    return events


def _extract_passive_events(sentence: str) -> List[Event]:
    events: List[Event] = []
    for match in PASSIVE_EVENT_PATTERN.finditer(sentence):
        trigger = match.group("trigger").lower()
        target = clean_value(match.group("target"))
        actor = match.group("actor")
        clean_actor = clean_entity(actor) if actor else None
        if _is_noisy(target):
            continue
        events.append(
            Event(
                event_type=EVENT_VERBS[trigger],
                trigger=trigger,
                actor=clean_actor,
                action=trigger,
                target=target,
                evidence=sentence,
            )
        )
    return events


def _deduplicate_events(events: List[Event]) -> List[Event]:
    seen = set()
    deduplicated: List[Event] = []
    for event in events:
        key = (event.event_type, event.trigger, event.actor, event.target, event.evidence)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(event)
    return deduplicated


def _clean_text(value: str) -> str:
    return value.strip(" .,:;")


def _clean_entity(value: str) -> str:
    value = _clean_text(value)
    return re.sub(r"^(?:the|a|an)\s+", "", value, flags=re.IGNORECASE)


def _is_noisy(value: Optional[str]) -> bool:
    if not value:
        return False
    if len(value) < 3:
        return True
    if len(value.split()) > 14:
        return True
    lowered = value.lower()
    noisy_fragments = [
        "configured to",
        "used to",
        "have to be",
        "has to be",
        "one or more",
        "and/or",
        "such as",
        "e.g",
        "wo 2023/",
        "pct/",
        "and a",
    ]
    if any(fragment in lowered for fragment in noisy_fragments):
        return True
    return False


if __name__ == "__main__":
    main()
