import argparse
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import spacy
from rdflib import BNode, Graph, OWL, RDF, RDFS, URIRef
from rdflib.collection import Collection
from spacy.matcher import PhraseMatcher


# Classes that are too general to match automatically.
EXCLUDED_CLASSES = {
    "Unit",
    "Algorithm",
    "Technology",
    "Software",
    "Agent",
    "Thing",
    "Concept",
    "Resource",
    "Data",
    "File",
    "Run",
    "Model",
    "Property",
    "Requirement",
    "Location",
    "Address",
    "Standard",
    "Frequency",
    "Distribution",
}


# Patent terminology mapped to existing DAOnt classes.
# The values must match class names in daont.ttl.
MANUAL_ALIASES = {
    # Hardware systems
    "cryptographic system": "CryptographicHardwareItem",
    "cryptographic hardware": "CryptographicHardwareItem",
    "cryptographic hardware system": "CryptographicHardwareItem",

    "secure element": "QuantumResistantSecureElement",
    "quantum resistant secure element":
        "QuantumResistantSecureElement",
    "quantum-resistant secure element":
        "QuantumResistantSecureElement",

    "pqc accelerator": "PQCAccelerator",
    "post-quantum accelerator": "PQCAccelerator",
    "post quantum accelerator": "PQCAccelerator",
    "cryptographic accelerator": "PQCAccelerator",
    "cryptographic math unit": "PQCAccelerator",
    "cryptographic co-processor": "PQCAccelerator",
    "cryptographic coprocessor": "PQCAccelerator",
    "co-processor": "PQCAccelerator",
    "coprocessor": "PQCAccelerator",

    # CPU terminology
    "cpu": "CPU",
    "processor": "CPU",
    "processing unit": "CPU",
    "central processing unit": "CPU",
    "processing circuitry": "CPU",
    "security processor": "CPU",
    "scalar processing unit": "CPU",

    # Patent hardware components
    "control unit": "CryptographicHardwareItem",
    "arithmetic unit": "CryptographicHardwareItem",
    "permutation unit": "CryptographicHardwareItem",

    # Memory terminology
    "ram": "RAM",
    "random access memory": "RAM",
    "matrix memory": "RAM",

    # Interfaces
    "interface": "Interface",
    "hardware interface": "Interface",
    "host interface": "HostInterface",
    "network interface": "NetworkingInterface",
    "networking interface": "NetworkingInterface",
    "physical interface": "PhysicalInterface",
    "virtual interface": "VirtualInterface",
    "bus interface": "Interface",
    "connector": "Connector",
    "port": "Port",
    "ethernet": "InterfaceTechnology",
    "pci express": "InterfaceTechnology",
    "pcie": "InterfaceTechnology",

    # Software
    "firmware": "Firmware",
    "driver": "Driver",
    "operating system": "OperatingSystem",
    "protocol": "Protocol",
    "documentation": "Documentation",
    "datasheet": "Datasheet",

    # Algorithms
    "cryptographic algorithm": "CryptographicAlgorithm",
    "post-quantum algorithm":
        "PostQuantumCryptographicAlgorithm",
    "post quantum algorithm":
        "PostQuantumCryptographicAlgorithm",
    "post-quantum cryptographic algorithm":
        "PostQuantumCryptographicAlgorithm",
    "post quantum cryptographic algorithm":
        "PostQuantumCryptographicAlgorithm",
    "pqc algorithm":
        "PostQuantumCryptographicAlgorithm",
    "signature algorithm": "SignatureAlgorithm",
    "key encapsulation mechanism":
        "PostQuantumCryptographicAlgorithm",
    "kem": "PostQuantumCryptographicAlgorithm",

    "kyber": "PostQuantumCryptographicAlgorithm",
    "dilithium": "PostQuantumCryptographicAlgorithm",
    "falcon": "PostQuantumCryptographicAlgorithm",
    "sphincs+": "PostQuantumCryptographicAlgorithm",
    "sphincs plus": "PostQuantumCryptographicAlgorithm",
    "ntru": "PostQuantumCryptographicAlgorithm",
    "saber": "PostQuantumCryptographicAlgorithm",

    "number theoretic transform":
        "CryptographicAlgorithm",
    "number-theoretic transform":
        "CryptographicAlgorithm",
    "ntt": "CryptographicAlgorithm",
    "keccak": "CryptographicAlgorithm",
    "sha3": "CryptographicAlgorithm",
    "sha-3": "CryptographicAlgorithm",
    "aes": "CryptographicAlgorithm",
    "rsa": "CryptographicAlgorithm",
    "ecdsa": "SignatureAlgorithm",

    # Additional ontology concepts
    "cpu architecture": "CPUArchitecture",
    "processor architecture": "CPUArchitecture",
    "cpu family": "CPUFamily",
    "processor family": "CPUFamily",
    "ram technology": "RAMTechnology",
    "memory technology": "RAMTechnology",
    "hardware model": "HardwareModel",
    "connector type": "ConnectorType",
    "hardware feature": "HardwareFeature",
    "software feature": "SoftwareFeature",
}


CONTAINMENT_VERBS = {
    "comprise",
    "contain",
    "feature",
    "have",
    "include",
    "incorporate",
    "integrate",
    "provide",
    "use",
}


ALGORITHM_VERBS = {
    "accelerate",
    "compute",
    "execute",
    "implement",
    "perform",
    "process",
    "run",
    "support",
    "use",
}


REQUIREMENT_VERBS = {
    "depend",
    "need",
    "require",
}


NEGATION_WORDS = {
    "not",
    "never",
    "neither",
    "nor",
    "without",
    "cannot",
}


HEADER_PATTERNS = [
    r"\bWO\s+\d{4}/\d+\b",
    r"\bPCT/[A-Z]{2}\d+\b",
    r"continued on next page",
    r"international application",
    r"publication bureau",
]


def normalize_text(value: object) -> str:
    """Normalize OCR whitespace and Unicode."""

    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    text = text.replace("\u00ad", "")

    # Join words split across OCR line endings.
    text = re.sub(
        r"(?<=\w)-\s*\n\s*(?=\w)",
        "",
        text,
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def local_name(uri: URIRef) -> str:
    """Return the final part of an RDF URI."""

    text = str(uri)

    if "#" in text:
        return text.rsplit("#", 1)[-1]

    return text.rstrip("/").rsplit("/", 1)[-1]


def humanize_name(value: str) -> str:
    """
    Convert names such as hasCPUArchitecture
    to readable words.
    """

    text = re.sub(
        r"(?<=[a-z0-9])(?=[A-Z])",
        " ",
        value,
    )

    text = re.sub(
        r"(?<=[A-Z])(?=[A-Z][a-z])",
        " ",
        text,
    )

    text = text.replace("_", " ")

    return re.sub(r"\s+", " ", text).strip()


def load_ontology(
    ontology_path: Path,
) -> tuple[
    Graph,
    dict[str, URIRef],
    dict[str, URIRef],
]:
    """Load DAOnt classes and properties."""

    graph = Graph()

    graph.parse(
        str(ontology_path),
        format="turtle",
    )

    classes: dict[str, URIRef] = {}
    properties: dict[str, URIRef] = {}

    for class_uri in graph.subjects(
        RDF.type,
        OWL.Class,
    ):
        if isinstance(class_uri, URIRef):
            classes.setdefault(
                local_name(class_uri),
                class_uri,
            )

    for property_type in (
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
    ):
        for property_uri in graph.subjects(
            RDF.type,
            property_type,
        ):
            if isinstance(property_uri, URIRef):
                properties.setdefault(
                    local_name(property_uri),
                    property_uri,
                )

    return graph, classes, properties


def build_aliases(
    ontology: Graph,
    classes: dict[str, URIRef],
) -> dict[str, URIRef]:
    """
    Build searchable phrases from ontology labels,
    class names and patent-specific aliases.
    """

    aliases: dict[str, URIRef] = {}

    for class_name, class_uri in classes.items():
        if class_name in EXCLUDED_CLASSES:
            continue

        candidates = {
            class_name,
            humanize_name(class_name),
        }

        for label in ontology.objects(
            class_uri,
            RDFS.label,
        ):
            candidates.add(str(label))

        for candidate in candidates:
            candidate = normalize_text(
                candidate
            ).casefold()

            if len(candidate) >= 2:
                aliases[candidate] = class_uri

    for alias, target_class in (
        MANUAL_ALIASES.items()
    ):
        class_uri = classes.get(
            target_class
        )

        if class_uri is not None:
            aliases[alias.casefold()] = class_uri

    return aliases


def build_matcher(
    nlp,
    aliases: dict[str, URIRef],
) -> PhraseMatcher:
    """Create a spaCy ontology phrase matcher."""

    matcher = PhraseMatcher(
        nlp.vocab,
        attr="LOWER",
    )

    aliases_by_class = defaultdict(list)

    for alias, class_uri in aliases.items():
        aliases_by_class[
            local_name(class_uri)
        ].append(alias)

    for class_name, phrases in (
        aliases_by_class.items()
    ):
        patterns = [
            nlp.make_doc(phrase)
            for phrase in sorted(
                set(phrases),
                key=len,
                reverse=True,
            )
        ]

        matcher.add(
            f"ONTOLOGY::{class_name}",
            patterns,
        )

    return matcher


def split_into_chunks(
    text: str,
    maximum_characters: int = 45000,
) -> list[str]:
    """
    Split the long patent into manageable sections.
    """

    text = unicodedata.normalize(
        "NFKC",
        text,
    )

    text = text.replace("\u00ad", "")

    text = re.sub(
        r"(?<=\w)-\s*\n\s*(?=\w)",
        "",
        text,
    )

    paragraphs = []

    for paragraph in re.split(
        r"\n\s*\n",
        text,
    ):
        paragraph = normalize_text(paragraph)

        if paragraph:
            paragraphs.append(paragraph)

    chunks = []
    current_chunk = []
    current_size = 0

    for paragraph in paragraphs:
        new_size = (
            current_size
            + len(paragraph)
            + 2
        )

        if (
            current_chunk
            and new_size > maximum_characters
        ):
            chunks.append(
                "\n\n".join(current_chunk)
            )

            current_chunk = []
            current_size = 0

        current_chunk.append(paragraph)
        current_size += len(paragraph) + 2

    if current_chunk:
        chunks.append(
            "\n\n".join(current_chunk)
        )

    return chunks


def remove_overlaps(
    doc,
    matches,
    classes: dict[str, URIRef],
) -> list[dict]:
    """
    Prefer longer ontology phrases when matches overlap.

    For example:
        post-quantum cryptographic algorithm

    is preferred over:
        cryptographic algorithm
    """

    candidates = []

    for match_id, start, end in matches:
        match_name = doc.vocab.strings[
            match_id
        ]

        class_name = match_name.split(
            "::",
            1,
        )[-1]

        class_uri = classes.get(
            class_name
        )

        if class_uri is None:
            continue

        span = doc[start:end]

        candidates.append(
            {
                "span": span,
                "start": start,
                "end": end,
                "text": normalize_text(
                    span.text
                ),
                "class_name": class_name,
                "class_uri": class_uri,
            }
        )

    candidates.sort(
        key=lambda item: (
            -(item["end"] - item["start"]),
            item["start"],
        )
    )

    occupied_tokens = set()
    selected = []

    for candidate in candidates:
        token_indexes = set(
            range(
                candidate["start"],
                candidate["end"],
            )
        )

        if occupied_tokens.intersection(
            token_indexes
        ):
            continue

        occupied_tokens.update(
            token_indexes
        )

        selected.append(candidate)

    return sorted(
        selected,
        key=lambda item: item["start"],
    )


def build_parent_index(
    ontology: Graph,
) -> dict[URIRef, set[URIRef]]:
    """Build the DAOnt subclass hierarchy."""

    parents = defaultdict(set)

    for child, parent in ontology.subject_objects(
        RDFS.subClassOf
    ):
        if (
            isinstance(child, URIRef)
            and isinstance(parent, URIRef)
        ):
            parents[child].add(parent)

    return parents


def is_same_or_subclass(
    child: URIRef,
    expected_parent: URIRef,
    parents: dict[URIRef, set[URIRef]],
) -> bool:
    """Check class compatibility."""

    if child == expected_parent:
        return True

    pending = [child]
    visited = set()

    while pending:
        current = pending.pop()

        if current in visited:
            continue

        visited.add(current)

        for parent in parents.get(
            current,
            set(),
        ):
            if parent == expected_parent:
                return True

            pending.append(parent)

    return False


def expand_class_expression(
    ontology: Graph,
    node,
) -> set[URIRef]:
    """
    Read a normal class URI or an OWL union.
    """

    if isinstance(node, URIRef):
        return {node}

    if not isinstance(node, BNode):
        return set()

    for list_property in (
        OWL.unionOf,
        OWL.intersectionOf,
    ):
        list_head = ontology.value(
            node,
            list_property,
        )

        if list_head is not None:
            return {
                member
                for member in Collection(
                    ontology,
                    list_head,
                )
                if isinstance(member, URIRef)
            }

    return set()


def build_property_constraints(
    ontology: Graph,
    properties: dict[str, URIRef],
) -> tuple[
    dict[URIRef, set[URIRef]],
    dict[URIRef, set[URIRef]],
]:
    """Load property domains and ranges."""

    domains = defaultdict(set)
    ranges = defaultdict(set)

    for property_uri in properties.values():
        for domain in ontology.objects(
            property_uri,
            RDFS.domain,
        ):
            domains[property_uri].update(
                expand_class_expression(
                    ontology,
                    domain,
                )
            )

        for range_value in ontology.objects(
            property_uri,
            RDFS.range,
        ):
            ranges[property_uri].update(
                expand_class_expression(
                    ontology,
                    range_value,
                )
            )

    return domains, ranges


def property_is_valid(
    property_uri: URIRef,
    subject_class: URIRef,
    object_class: URIRef,
    domains,
    ranges,
    parents,
) -> bool:
    """Validate a relationship using DAOnt constraints."""

    allowed_domains = domains.get(
        property_uri,
        set(),
    )

    if allowed_domains:
        domain_valid = any(
            is_same_or_subclass(
                subject_class,
                allowed_class,
                parents,
            )
            for allowed_class in allowed_domains
        )

        if not domain_valid:
            return False

    allowed_ranges = ranges.get(
        property_uri,
        set(),
    )

    if allowed_ranges:
        range_valid = any(
            is_same_or_subclass(
                object_class,
                allowed_class,
                parents,
            )
            for allowed_class in allowed_ranges
        )

        if not range_valid:
            return False

    return True


def sentence_is_noise(
    sentence_text: str,
) -> bool:
    """Reject patent headers and OCR-heavy sentences."""

    if not sentence_text:
        return True

    if len(sentence_text) > 1200:
        return True

    for pattern in HEADER_PATTERNS:
        if re.search(
            pattern,
            sentence_text,
            re.IGNORECASE,
        ):
            return True

    compact = re.sub(
        r"\s+",
        "",
        sentence_text,
    )

    if not compact:
        return True

    letters = sum(
        character.isalpha()
        for character in compact
    )

    return (
        letters / len(compact)
        < 0.45
    )


def sentence_has_negation(sentence) -> bool:
    """
    Avoid turning statements such as
    'does not have access' into 'has access'.
    """

    for token in sentence:
        if (
            token.dep_ == "neg"
            or token.lower_
            in NEGATION_WORDS
        ):
            return True

    return False


def find_relation_verb(
    doc,
    subject: dict,
    object_value: dict,
) -> tuple[str, bool]:
    """
    Return the relationship verb and whether it
    appeared directly between the two mentions.
    """

    between = doc[
        subject["end"]:
        object_value["start"]
    ]

    for token in between:
        if token.pos_ == "VERB":
            return (
                token.lemma_.casefold(),
                True,
            )

    sentence = subject["span"].sent

    if sentence.root.pos_ in {
        "VERB",
        "AUX",
    }:
        return (
            sentence.root.lemma_.casefold(),
            False,
        )

    return "", False


def choose_property(
    verb: str,
    object_class: str,
) -> Optional[str]:
    """
    Map a verb and ontology object class to a
    controlled DAOnt property.
    """

    if verb in REQUIREMENT_VERBS:
        hardware_classes = {
            "CPU",
            "RAM",
            "Connector",
            "CryptographicHardwareItem",
            "PQCAccelerator",
            "Port",
            "QuantumResistantSecureElement",
        }

        software_classes = {
            "Driver",
            "Firmware",
            "OperatingSystem",
        }

        if object_class in hardware_classes:
            return "requiredHardware"

        if object_class in software_classes:
            return "requiredSoftware"

    if (
        object_class == "CPU"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasCPU"

    if (
        object_class == "RAM"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasRAM"

    interface_classes = {
        "HostInterface",
        "Interface",
        "NetworkingInterface",
        "PhysicalInterface",
        "VirtualInterface",
    }

    if (
        object_class in interface_classes
        and verb in CONTAINMENT_VERBS
    ):
        return "hasInterface"

    if (
        object_class == "Firmware"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasFirmware"

    if (
        object_class == "Driver"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasDriver"

    if (
        object_class == "Datasheet"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasDatasheet"

    if (
        object_class
        in {"Documentation", "ModelCard"}
        and verb in CONTAINMENT_VERBS
    ):
        return "hasDocumentation"

    if (
        object_class == "Protocol"
        and verb in ALGORITHM_VERBS
    ):
        return "implementsProtocol"

    algorithm_classes = {
        "ClassicalAlgorithm",
        "CryptographicAlgorithm",
        "PostQuantumCryptographicAlgorithm",
        "SignatureAlgorithm",
    }

    if (
        object_class in algorithm_classes
        and verb in ALGORITHM_VERBS
    ):
        return "supportsAlgorithm"

    if (
        object_class
        in {"HardwareFeature", "SoftwareFeature"}
        and verb in CONTAINMENT_VERBS
    ):
        return "providesFeature"

    if (
        object_class == "CPUArchitecture"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasCPUArchitecture"

    if (
        object_class == "CPUFamily"
        and verb in {
            "belong",
            "include",
            "form",
        }
    ):
        return "belongsToCPUFamily"

    if (
        object_class == "RAMTechnology"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasRAMTechnology"

    if (
        object_class == "HardwareModel"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasHardwareModel"

    if (
        object_class == "ConnectorType"
        and verb in CONTAINMENT_VERBS
    ):
        return "hasConnectorType"

    if object_class == "InterfaceTechnology":
        if verb == "support":
            return "supportsInterfaceTechnology"

        if verb == "use":
            return "usesInterfaceTechnology"

    return None


def save_json(
    data: object,
    output_path: Path,
) -> None:
    """Save readable UTF-8 JSON."""

    with output_path.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            data,
            file,
            ensure_ascii=False,
            indent=2,
        )


def extract_data(
    text_path: Path,
    ontology_path: Path,
    prefix: str,
) -> None:
    ontology, classes, properties = (
        load_ontology(ontology_path)
    )

    aliases = build_aliases(
        ontology,
        classes,
    )

    parent_index = build_parent_index(
        ontology
    )

    domains, ranges = (
        build_property_constraints(
            ontology,
            properties,
        )
    )

    nlp = spacy.load(
        "en_core_web_sm"
    )

    matcher = build_matcher(
        nlp,
        aliases,
    )

    raw_text = text_path.read_text(
        encoding="utf-8",
        errors="replace",
    )

    chunks = split_into_chunks(
        raw_text
    )

    entity_index = {}
    relationship_index = {}
    rejected_candidates = []

    class_counts = Counter()
    property_counts = Counter()

    total_mentions = 0

    print(
        f"Ontology triples: {len(ontology)}"
    )

    print(
        f"Ontology classes: {len(classes)}"
    )

    print(
        f"Ontology properties: "
        f"{len(properties)}"
    )

    print(
        f"Matching aliases: {len(aliases)}"
    )

    print(
        f"Text chunks: {len(chunks)}"
    )

    print("Processing text...")

    documents = nlp.pipe(
        chunks,
        batch_size=2,
    )

    for chunk_number, doc in enumerate(
        documents,
        start=1,
    ):
        matches = matcher(doc)

        mentions = remove_overlaps(
            doc,
            matches,
            classes,
        )

        total_mentions += len(mentions)

        mentions_by_sentence = defaultdict(
            list
        )

        for mention in mentions:
            sentence_text = normalize_text(
                mention["span"].sent.text
            )

            if sentence_is_noise(
                sentence_text
            ):
                continue

            entity_key = (
                mention["text"].casefold(),
                str(mention["class_uri"]),
            )

            if entity_key not in entity_index:
                entity_index[entity_key] = {
                    "text": mention["text"],
                    "label": (
                        mention["class_name"]
                    ),
                    "class_uri": str(
                        mention["class_uri"]
                    ),
                    "source": (
                        "DAOnt phrase match"
                    ),
                    "mention_count": 1,
                    "example_sentence": (
                        sentence_text
                    ),
                }

            else:
                entity_index[
                    entity_key
                ]["mention_count"] += 1

            class_counts[
                mention["class_name"]
            ] += 1

            sentence_start = (
                mention["span"].sent.start
            )

            mentions_by_sentence[
                sentence_start
            ].append(mention)

        for sentence_mentions in (
            mentions_by_sentence.values()
        ):
            sentence_mentions.sort(
                key=lambda item: item["start"]
            )

            if len(sentence_mentions) < 2:
                continue

            sentence = (
                sentence_mentions[0]
                ["span"]
                .sent
            )

            sentence_text = normalize_text(
                sentence.text
            )

            if sentence_has_negation(
                sentence
            ):
                rejected_candidates.append(
                    {
                        "reason": (
                            "sentence contains "
                            "negation"
                        ),
                        "sentence": sentence_text,
                    }
                )

                continue

            for object_index in range(
                1,
                len(sentence_mentions),
            ):
                object_mention = (
                    sentence_mentions[
                        object_index
                    ]
                )

                for subject_index in range(
                    object_index - 1,
                    -1,
                    -1,
                ):
                    subject_mention = (
                        sentence_mentions[
                            subject_index
                        ]
                    )


                    distance = (
                        object_mention["start"]
                        - subject_mention["end"]
                    )

                    if distance > 45:
                        continue

                    verb, explicit_verb = (
                        find_relation_verb(
                            doc,
                            subject_mention,
                            object_mention,
                        )
                    )

                    between_text = doc[
                        subject_mention["end"]:
                        object_mention["start"]
                    ].text

                    # Avoid linking entities across separate
                    # semicolon-delimited patent clauses.
                    if ";" in between_text:
                        continue

                    # Allow root-verb fallback only for very
                    # close and grammatically simple phrases.
                    if not explicit_verb:
                        if (
                            distance > 18
                            or "," in between_text
                            or "(" in between_text
                            or ")" in between_text
                        ):
                            continue

                    property_name = (
                        choose_property(
                            verb,
                            object_mention[
                                "class_name"
                            ],
                        )
                    )

                    if property_name is None:
                        continue

                    subject_class_name = (
                        subject_mention["class_name"]
                    )

                    # RAM and CPU should not automatically
                    # be treated as containers of another CPU.
                    if (
                        property_name == "hasCPU"
                        and subject_class_name
                        in {"RAM", "CPU"}
                    ):
                        continue

                    # "RAM stores firmware instructions" does
                    # not mean that RAM has its own firmware.
                    if (
                        property_name == "hasFirmware"
                        and (
                            subject_class_name == "RAM"
                            or verb in {"store", "use"}
                        )
                    ):
                        continue

                    # Prevent relationships such as
                    # CPU --hasCPU--> CPU.
                    if (
                        property_name
                        in {
                            "hasCPU",
                            "hasRAM",
                            "hasInterface",
                        }
                        and subject_mention[
                            "class_name"
                        ]
                        == object_mention[
                            "class_name"
                        ]
                    ):
                        continue

                    property_uri = (
                        properties.get(
                            property_name
                        )
                    )

                    valid = property_is_valid(
                        property_uri,
                        subject_mention[
                            "class_uri"
                        ],
                        object_mention[
                            "class_uri"
                        ],
                        domains,
                        ranges,
                        parent_index,
                    )

                    if not valid:
                        rejected_candidates.append(
                            {
                                "reason": (
                                    "DAOnt domain/"
                                    "range mismatch"
                                ),
                                "subject": (
                                    subject_mention[
                                        "text"
                                    ]
                                ),
                                "subject_label": (
                                    subject_mention[
                                        "class_name"
                                    ]
                                ),
                                "predicate": (
                                    property_name
                                ),
                                "object": (
                                    object_mention[
                                        "text"
                                    ]
                                ),
                                "object_label": (
                                    object_mention[
                                        "class_name"
                                    ]
                                ),
                                "sentence": (
                                    sentence_text
                                ),
                            }
                        )

                        continue

                    relationship_key = (
                        subject_mention[
                            "text"
                        ].casefold(),
                        str(property_uri),
                        object_mention[
                            "text"
                        ].casefold(),
                    )

                    if (
                        relationship_key
                        not in relationship_index
                    ):
                        relationship_index[
                            relationship_key
                        ] = {
                            "subject": (
                                subject_mention[
                                    "text"
                                ]
                            ),
                            "subject_label": (
                                subject_mention[
                                    "class_name"
                                ]
                            ),
                            "subject_class_uri": str(
                                subject_mention[
                                    "class_uri"
                                ]
                            ),
                            "predicate": (
                                property_name
                            ),
                            "predicate_uri": str(
                                property_uri
                            ),
                            "object": (
                                object_mention[
                                    "text"
                                ]
                            ),
                            "object_label": (
                                object_mention[
                                    "class_name"
                                ]
                            ),
                            "object_class_uri": str(
                                object_mention[
                                    "class_uri"
                                ]
                            ),
                            "verb": verb,
                            "confidence": (
                                0.95
                                if explicit_verb
                                else 0.75
                            ),
                            "sentence": (
                                sentence_text
                            ),
                        }

                        property_counts[
                            property_name
                        ] += 1

                    # Stop after finding the nearest
                    # valid subject.
                    break

        print(
            f"Processed chunk "
            f"{chunk_number}/"
            f"{len(chunks)}",
            end="\r",
            flush=True,
        )

    print()

    entities = sorted(
        entity_index.values(),
        key=lambda item: (
            -item["mention_count"],
            item["label"],
            item["text"].casefold(),
        ),
    )

    relationships = sorted(
        relationship_index.values(),
        key=lambda item: (
            item["predicate"],
            item["subject"].casefold(),
            item["object"].casefold(),
        ),
    )

    output_directory = text_path.parent

    entities_path = (
        output_directory
        / f"{prefix}_ontology_entities.json"
    )

    relationships_path = (
        output_directory
        / f"{prefix}_ontology_relationships.json"
    )

    rejected_path = (
        output_directory
        / f"{prefix}_ontology_rejected.json"
    )

    report_path = (
        output_directory
        / f"{prefix}_ontology_report.json"
    )

    report = {
        "text_file": str(text_path),
        "ontology_file": str(
            ontology_path
        ),
        "ontology_triples": len(
            ontology
        ),
        "ontology_classes": len(
            classes
        ),
        "ontology_properties": len(
            properties
        ),
        "matching_aliases": len(
            aliases
        ),
        "text_chunks": len(chunks),
        "matched_mentions_before_noise_checks":
            total_mentions,
        "unique_entities": len(
            entities
        ),
        "unique_relationships": len(
            relationships
        ),
        "entity_class_counts": dict(
            class_counts.most_common()
        ),
        "relationship_property_counts":
            dict(
                property_counts.most_common()
            ),
        "rejected_candidate_count": len(
            rejected_candidates
        ),
    }

    save_json(
        entities,
        entities_path,
    )

    save_json(
        relationships,
        relationships_path,
    )

    save_json(
        rejected_candidates,
        rejected_path,
    )

    save_json(
        report,
        report_path,
    )

    print(
        "Ontology-guided extraction "
        "completed."
    )

    print(
        f"Unique entities: "
        f"{len(entities)}"
    )

    print(
        f"Unique relationships: "
        f"{len(relationships)}"
    )

    print(
        f"Rejected candidates: "
        f"{len(rejected_candidates)}"
    )

    print(f"Saved: {entities_path}")
    print(f"Saved: {relationships_path}")
    print(f"Saved: {rejected_path}")
    print(f"Saved: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Extract DAOnt-aligned entities "
            "and relationships from text."
        )
    )

    parser.add_argument(
        "text_file",
        help=(
            "Text file produced by "
            "text_extractor.py"
        ),
    )

    parser.add_argument(
        "ontology_file",
        help="DAOnt Turtle ontology",
    )

    parser.add_argument(
        "--prefix",
        help=(
            "Output filename prefix. "
            "Defaults to the text filename."
        ),
    )

    arguments = parser.parse_args()

    text_path = Path(
        arguments.text_file
    )

    ontology_path = Path(
        arguments.ontology_file
    )

    if not text_path.exists():
        raise FileNotFoundError(
            f"Text file not found: "
            f"{text_path}"
        )

    if not ontology_path.exists():
        raise FileNotFoundError(
            f"Ontology file not found: "
            f"{ontology_path}"
        )

    prefix = (
        arguments.prefix
        or text_path.stem
    )

    extract_data(
        text_path,
        ontology_path,
        prefix,
    )


if __name__ == "__main__":
    main()
