"""Convert reviewed facts-and-attributes JSON into RDF Turtle."""

import argparse
import hashlib
import json
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS


FACT = Namespace(
    "https://example.org/federated-extractor/fact/"
)

RES = Namespace(
    "https://example.org/federated-extractor/resource/"
)


def normalize(value):
    """Normalize whitespace and handle null values."""

    if value is None:
        return ""

    return " ".join(str(value).split()).strip()


def make_uri(prefix, value):
    """Create a stable RDF URI from text."""

    digest = hashlib.sha256(
        value.casefold().encode("utf-8")
    ).hexdigest()[:16]

    return RES[f"{prefix}_{digest}"]


def convert(input_json, output_ttl):
    """Convert reviewed facts into an RDF graph."""

    input_path = Path(input_json)
    output_path = Path(output_ttl)

    facts = json.loads(
        input_path.read_text(encoding="utf-8")
    )

    if not isinstance(facts, list):
        raise ValueError(
            "Input JSON must contain a list of facts."
        )

    graph = Graph()

    graph.bind("fact", FACT)
    graph.bind("res", RES)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)

    # Small schema for the facts graph.
    graph.add((FACT.Fact, RDF.type, RDFS.Class))
    graph.add((FACT.Entity, RDF.type, RDFS.Class))
    graph.add((FACT.Value, RDF.type, RDFS.Class))

    properties = {
        FACT.hasEntity: "has entity",
        FACT.hasValue: "has value",
        FACT.attribute: "attribute",
        FACT.unit: "unit",
        FACT.evidence: "evidence",
        FACT.sourceExtractor: "source extractor",
    }

    for property_uri, label in properties.items():
        graph.add(
            (property_uri, RDF.type, RDF.Property)
        )
        graph.add(
            (property_uri, RDFS.label, Literal(label))
        )

    fact_uris = set()
    entity_uris = set()
    value_uris = set()

    for fact in facts:
        if not isinstance(fact, dict):
            continue

        entity = normalize(fact.get("entity"))
        attribute = normalize(fact.get("attribute"))
        value = normalize(fact.get("value"))
        unit = normalize(fact.get("unit"))
        evidence = normalize(fact.get("evidence"))

        if not entity or not attribute or not value:
            continue

        identity = json.dumps(
            {
                "entity": entity,
                "attribute": attribute,
                "value": value,
                "unit": unit,
                "evidence": evidence,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        fact_uri = make_uri("fact", identity)
        entity_uri = make_uri("entity", entity)
        value_uri = make_uri(
            "value",
            f"{value}|{unit}",
        )

        graph.add(
            (fact_uri, RDF.type, FACT.Fact)
        )

        graph.add(
            (
                fact_uri,
                RDFS.label,
                Literal(
                    f"{entity} — {attribute} — {value}"
                ),
            )
        )

        graph.add(
            (entity_uri, RDF.type, FACT.Entity)
        )

        graph.add(
            (
                entity_uri,
                RDFS.label,
                Literal(entity),
            )
        )

        graph.add(
            (value_uri, RDF.type, FACT.Value)
        )

        graph.add(
            (
                value_uri,
                RDFS.label,
                Literal(value),
            )
        )

        graph.add(
            (
                fact_uri,
                FACT.hasEntity,
                entity_uri,
            )
        )

        graph.add(
            (
                fact_uri,
                FACT.hasValue,
                value_uri,
            )
        )

        graph.add(
            (
                fact_uri,
                FACT.attribute,
                Literal(attribute),
            )
        )

        if unit:
            graph.add(
                (
                    fact_uri,
                    FACT.unit,
                    Literal(unit),
                )
            )

        if evidence:
            graph.add(
                (
                    fact_uri,
                    FACT.evidence,
                    Literal(evidence),
                )
            )

        graph.add(
            (
                fact_uri,
                FACT.sourceExtractor,
                Literal("facts_attributes.py"),
            )
        )

        fact_uris.add(fact_uri)
        entity_uris.add(entity_uri)
        value_uris.add(value_uri)

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    graph.serialize(
        destination=str(output_path),
        format="turtle",
    )

    # Validate the generated Turtle.
    validation_graph = Graph()
    validation_graph.parse(
        output_path,
        format="turtle",
    )

    print("Facts converted:", len(fact_uris))
    print("Unique entities:", len(entity_uris))
    print("Unique values:", len(value_uris))
    print("RDF triples:", len(validation_graph))
    print("Saved:", output_path)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert reviewed facts-and-attributes JSON "
            "into RDF Turtle."
        )
    )

    parser.add_argument("input_json")
    parser.add_argument("output_ttl")

    args = parser.parse_args()

    convert(
        args.input_json,
        args.output_ttl,
    )


if __name__ == "__main__":
    main()
