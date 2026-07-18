"""Normalize extracted knowledge using DAOnt vocabulary.

DAOnt is the Digital Assets Ontology. This module maps raw extractor output to
DAOnt-aligned classes and properties, while separating unmapped records and
obvious extraction noise for review.
"""

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

from extractors.text_preprocessing import clean_entity, clean_value


DAO_PREFIX = "https://w3id.org/daont#"
DC_TERMS_PREFIX = "http://purl.org/dc/terms/"
FABIO_PREFIX = "http://purl.org/spar/fabio/"
MLS_PREFIX = "http://www.w3.org/ns/mls#"
PROV_PREFIX = "http://www.w3.org/ns/prov#"


@dataclass(frozen=True)
class NormalizedRecord:
    """A DAOnt-aligned normalized knowledge record."""

    source_type: str
    subject: str
    subject_type: str
    predicate: str
    object: str
    object_type: Optional[str]
    confidence: float
    mapping_reason: str
    evidence: Optional[str]
    original: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RejectedRecord:
    """A record rejected as extraction noise."""

    reason: str
    original: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


DAO_CLASS_RULES = [
    ("PostQuantumCryptographicAlgorithm", [r"post[- ]quantum .*algorithm"]),
    ("CryptographicAlgorithm", [r"cryptographic algorithm", r"\balgorithm\b"]),
    ("SignatureAlgorithm", [r"signature algorithm", r"digital signature"]),
    ("CryptographicHardwareItem", [r"cryptographic system", r"co-processor", r"coprocessor"]),
    ("PQCAccelerator", [r"pqc accelerator", r"post[- ]quantum .*accelerator"]),
    ("QuantumResistantSecureElement", [r"quantum resistant secure element", r"secure element"]),
    ("CPU", [r"\bcpu\b", r"processor", r"processing unit", r"microprocessor"]),
    ("RAM", [r"\bram\b", r"random access memory", r"matrix memory", r"memory"]),
    ("Firmware", [r"firmware"]),
    ("Driver", [r"driver"]),
    ("Interface", [r"interface", r"bus interface", r"key interface"]),
    ("HostInterface", [r"host interface"]),
    ("NetworkingInterface", [r"networking interface"]),
    ("Protocol", [r"protocol"]),
    ("HardwareFeature", [r"unit", r"generator", r"register", r"permutation", r"arithmetic"]),
    ("HardwareRequirement", [r"hardware requirement"]),
    ("SoftwareRequirement", [r"software requirement"]),
    ("Requirement", [r"requirement"]),
    ("SoftwareFeature", [r"software feature"]),
    ("DigitalAsset", [r"digital asset", r"system", r"service", r"data"]),
]

DAO_PROPERTY_RULES = [
    ("hasCPU", [r"has c ?p ?u", r"processor", r"cpu"]),
    ("hasRAM", [r"has r ?a ?m", r"memory", r"ram", r"matrix memory"]),
    ("hasFirmware", [r"firmware"]),
    ("hasDriver", [r"driver"]),
    ("hasInterface", [r"interface", r"bus"]),
    ("hasRequirement", [r"requirement"]),
    ("requiredHardware", [r"required hardware"]),
    ("requiredSoftware", [r"required software"]),
    ("supportsAlgorithm", [r"algorithm", r"signature", r"cryptographic function"]),
    ("implementsProtocol", [r"protocol"]),
    ("providesFeature", [r"comprises", r"configured to", r"used to", r"perform", r"operation", r"feature"]),
    ("exposesAPI", [r"api"]),
    ("hasByteSize", [r"byte size", r"bit length", r"n-bit", r"\d+\s*bits?"]),
    ("hasRAMSize", [r"ram size", r"memory size"]),
    ("numberOfCores", [r"cores?"]),
    ("hasMaxClock", [r"clock"]),
    ("hasSignaturesPerSecond", [r"signatures per second"]),
    ("hasSpeedUp", [r"speed up", r"speedup"]),
]

DIRECT_PROPERTY_MAP = {
    "comprises": "providesFeature",
    "configured to": "providesFeature",
    "used to": "providesFeature",
    "used for": "providesFeature",
    "operation": "providesFeature",
    "execution": "providesFeature",
    "generation": "providesFeature",
    "computation": "providesFeature",
    "processing": "providesFeature",
    "control": "providesFeature",
    "masking": "providesFeature",
    "encryption": "supportsAlgorithm",
    "decryption": "supportsAlgorithm",
    "datatransfer": "providesFeature",
    "storage": "providesFeature",
}

NOISE_PATTERNS = [
    r"^wo\s+\d{4}/\d+",
    r"pct/[a-z]{2}\d+/\d+",
    r"^\d+$",
    r"^[a-z]\s*$",
    r"^and a$",
    r"^one or more$",
    r"international publication",
    r"world intellectual property",
    r"designated states",
    r"copyright",
]


def normalize_file(
    json_path: Union[str, Path],
    output_dir: Union[str, Path] = "outputs/normalized",
) -> Path:
    """Normalize a raw extractor JSON file and write DAOnt-oriented JSON."""

    source_path = Path(json_path)
    records = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("Expected a JSON array from the knowledge extractor.")

    normalized, unmapped, rejected = normalize_records(records)
    payload = {
        "source_file": str(source_path),
        "ontology": {
            "name": "Digital Assets Ontology (DAOnt)",
            "namespace": DAO_PREFIX,
            "source": "https://github.com/cefriel/daont-ontology/blob/master/daont/latest/daont.ttl",
        },
        "counts": {
            "input": len(records),
            "normalized": len(normalized),
            "unmapped": len(unmapped),
            "rejected": len(rejected),
        },
        "normalized": [record.to_dict() for record in normalized],
        "unmapped": unmapped,
        "rejected": [record.to_dict() for record in rejected],
    }

    output_path = Path(output_dir) / (source_path.stem + ".daont.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return output_path


def normalize_records(
    records: List[Dict[str, Any]],
) -> Tuple[List[NormalizedRecord], List[Dict[str, Any]], List[RejectedRecord]]:
    """Normalize raw extractor records into mapped, unmapped, and rejected sets."""

    normalized: List[NormalizedRecord] = []
    unmapped: List[Dict[str, Any]] = []
    rejected: List[RejectedRecord] = []

    for record in records:
        source_type = _detect_source_type(record)
        subject = _clean_subject(_record_subject(record))
        obj = _clean_object(_record_object(record))
        evidence = record.get("evidence")

        noise_reason = _noise_reason(subject, obj, evidence)
        if noise_reason:
            rejected.append(RejectedRecord(reason=noise_reason, original=record))
            continue

        subject_type, subject_reason = match_daont_class(subject)
        object_type, object_reason = match_daont_class(obj)
        predicate, predicate_reason = match_daont_property(record, subject, obj)

        if not subject_type or not predicate:
            unmapped.append(record)
            continue

        confidence = _confidence(subject, obj, subject_type, object_type, predicate)

        normalized.append(
            NormalizedRecord(
                source_type=source_type,
                subject=_clean_text(subject),
                subject_type=subject_type,
                predicate=predicate,
                object=_clean_text(obj),
                object_type=object_type,
                confidence=confidence,
                mapping_reason="; ".join(
                    reason
                    for reason in [subject_reason, predicate_reason, object_reason]
                    if reason
                ),
                evidence=evidence,
                original=record,
            )
        )

    return normalized, unmapped, rejected


def match_daont_class(text: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Map text to a DAOnt class IRI when possible."""

    if not text:
        return None, None
    normalized = _normalize_text(text)
    for class_name, patterns in DAO_CLASS_RULES:
        if any(re.search(pattern, normalized) for pattern in patterns):
            return DAO_PREFIX + class_name, "class matched " + class_name
    return None, None


def match_daont_property(
    record: Dict[str, Any],
    subject: Optional[str],
    obj: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Map a raw attribute/action to a DAOnt property IRI when possible."""

    direct_values = [
        record.get("attribute"),
        record.get("action"),
        record.get("event_type"),
        record.get("context"),
    ]
    direct_text = _normalize_text(" ".join(str(value) for value in direct_values if value))

    for key, property_name in DIRECT_PROPERTY_MAP.items():
        if key in direct_text:
            return DAO_PREFIX + property_name, "direct predicate mapped from " + key

    for property_name, patterns in DAO_PROPERTY_RULES:
        if any(re.search(pattern, direct_text) for pattern in patterns):
            return DAO_PREFIX + property_name, "predicate matched " + property_name

    subject_object_text = _normalize_text(" ".join(str(value) for value in [subject, obj] if value))
    for property_name in ["hasCPU", "hasRAM", "hasFirmware", "hasDriver", "hasInterface", "supportsAlgorithm", "implementsProtocol"]:
        patterns = dict(DAO_PROPERTY_RULES)[property_name]
        if any(re.search(pattern, subject_object_text) for pattern in patterns):
            return DAO_PREFIX + property_name, "fallback predicate matched " + property_name

    return None, None


def _detect_source_type(record: Dict[str, Any]) -> str:
    if "event_type" in record:
        return "event"
    return "fact_attribute"


def _record_subject(record: Dict[str, Any]) -> Optional[str]:
    return record.get("entity") or record.get("actor") or record.get("subject")


def _record_object(record: Dict[str, Any]) -> Optional[str]:
    return record.get("value") or record.get("target") or record.get("object")


def _noise_reason(
    subject: Optional[str],
    obj: Optional[str],
    evidence: Optional[str],
) -> Optional[str]:
    values = [value for value in [subject, obj] if value]
    if not values:
        return "missing subject/object"

    for value in values:
        cleaned = _normalize_text(value)
        if len(cleaned) < 3:
            return "too short"
        if len(cleaned.split()) > 18:
            return "overlong phrase"
        if cleaned in {"this", "these", "those", "it", "they"}:
            return "pronoun-only phrase"
        if any(re.search(pattern, cleaned) for pattern in NOISE_PATTERNS):
            return "known OCR/header noise"

    if evidence and any(re.search(pattern, _normalize_text(evidence)) for pattern in NOISE_PATTERNS[:3]):
        return "evidence contains patent header noise"

    return None


def _clean_subject(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return clean_entity(value)


def _clean_object(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return clean_value(value)


def _confidence(
    subject: Optional[str],
    obj: Optional[str],
    subject_type: Optional[str],
    object_type: Optional[str],
    predicate: Optional[str],
) -> float:
    score = 0.45
    if subject_type:
        score += 0.2
    if object_type:
        score += 0.15
    if predicate:
        score += 0.15
    if subject and len(subject.split()) <= 6:
        score += 0.03
    if obj and len(obj.split()) <= 12:
        score += 0.02
    return min(round(score, 2), 1.0)


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _clean_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip(" .,:;")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize raw knowledge extractor JSON using DAOnt mappings."
    )
    parser.add_argument("json_path", help="Path to raw extractor JSON output.")
    parser.add_argument(
        "--output-dir",
        default="outputs/normalized",
        help="Directory where normalized DAOnt JSON will be written.",
    )
    args = parser.parse_args()

    output_path = normalize_file(args.json_path, args.output_dir)
    print(output_path)


if __name__ == "__main__":
    main()
