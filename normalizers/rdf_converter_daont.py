import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

from rdflib import Graph, Literal, Namespace, OWL, RDF, RDFS, URIRef


def load_json(file_path: Path) -> list:
    """Load and validate a JSON array."""

    if not file_path.exists():
        raise FileNotFoundError(
            f"JSON file not found: {file_path}"
        )

    with file_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, list):
        raise ValueError(
            f"Expected a JSON array in: {file_path}"
        )

    return data


def normalize_text(value: object) -> str:
    """Normalize Unicode and repeated whitespace."""

    if value is None:
        return ""

    text = unicodedata.normalize(
        "NFKC",
        str(value),
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def slugify(value: str) -> str:
    """Create a readable URI component."""

    value = normalize_text(value).casefold()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value)

    return value.strip("-")


def create_resource_uri(
    text: str,
    resource_namespace: Namespace,
) -> URIRef:
    """
    Create one stable resource URI for an entity.

    A short hash prevents URI collisions between
    entities with similar names.
    """

    normalized = normalize_text(text).casefold()

    slug = slugify(normalized)

    if not slug:
        slug = "resource"

    slug = slug[:70]

    digest = hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()[:10]

    return URIRef(
        f"{resource_namespace}{slug}-{digest}"
    )


def validate_class_uri(
    ontology: Graph,
    class_uri: URIRef,
) -> None:
    """Confirm that a class URI exists in the ontology."""

    if (
        class_uri,
        RDF.type,
        OWL.Class,
    ) not in ontology:
        raise ValueError(
            f"Class is not declared as owl:Class: "
            f"{class_uri}"
        )


def validate_property_uri(
    ontology: Graph,
    property_uri: URIRef,
) -> None:
    """Confirm that a predicate is an ontology property."""

    valid_types = {
        OWL.ObjectProperty,
        OWL.DatatypeProperty,
    }

    property_types = set(
        ontology.objects(
            property_uri,
            RDF.type,
        )
    )

    if not property_types.intersection(
        valid_types
    ):
        raise ValueError(
            f"Predicate is not a DAOnt property: "
            f"{property_uri}"
        )


def add_entity(
    graph: Graph,
    text: str,
    class_uri_text: str,
    resource_namespace: Namespace,
    ontology: Graph,
) -> URIRef:
    """Add one entity, label and DAOnt type."""

    normalized_text = normalize_text(text)
    normalized_class_uri = normalize_text(
        class_uri_text
    )

    if not normalized_text:
        raise ValueError(
            "Cannot create an RDF entity with empty text."
        )

    if not normalized_class_uri:
        raise ValueError(
            f"Missing class URI for entity: "
            f"{normalized_text}"
        )

    class_uri = URIRef(
        normalized_class_uri
    )

    validate_class_uri(
        ontology,
        class_uri,
    )

    resource = create_resource_uri(
        normalized_text,
        resource_namespace,
    )

    graph.add(
        (
            resource,
            RDFS.label,
            Literal(normalized_text),
        )
    )

    graph.add(
        (
            resource,
            RDF.type,
            class_uri,
        )
    )

    return resource


def create_rdf_graph(
    entities: list[dict],
    relationships: list[dict],
    ontology: Graph,
    base_url: str,
) -> tuple[Graph, int]:
    """
    Convert reviewed JSON into ontology-aligned RDF.

    DAOnt class and predicate URIs are preserved.
    """

    normalized_base = (
        base_url.rstrip("/#") + "/"
    )

    resource_namespace = Namespace(
        normalized_base
    )

    daont_namespace = Namespace(
        "https://w3id.org/daont#"
    )

    graph = Graph()

    graph.bind(
        "res",
        resource_namespace,
    )

    graph.bind(
        "dao",
        daont_namespace,
    )

    graph.bind(
        "rdf",
        RDF,
    )

    graph.bind(
        "rdfs",
        RDFS,
    )

    graph.bind(
        "owl",
        OWL,
    )

    # Create resources from the reviewed entity file.
    for entity in entities:
        text = normalize_text(
            entity.get("text", "")
        )

        class_uri = normalize_text(
            entity.get("class_uri", "")
        )

        add_entity(
            graph,
            text,
            class_uri,
            resource_namespace,
            ontology,
        )

    relationship_triple_count = 0

    for relationship in relationships:
        subject_text = normalize_text(
            relationship.get(
                "subject",
                "",
            )
        )

        object_text = normalize_text(
            relationship.get(
                "object",
                "",
            )
        )

        subject_class_uri = normalize_text(
            relationship.get(
                "subject_class_uri",
                "",
            )
        )

        object_class_uri = normalize_text(
            relationship.get(
                "object_class_uri",
                "",
            )
        )

        predicate_uri_text = normalize_text(
            relationship.get(
                "predicate_uri",
                "",
            )
        )

        if not all(
            [
                subject_text,
                object_text,
                subject_class_uri,
                object_class_uri,
                predicate_uri_text,
            ]
        ):
            raise ValueError(
                "A reviewed relationship is missing "
                "required information:\n"
                f"{relationship}"
            )

        subject_resource = add_entity(
            graph,
            subject_text,
            subject_class_uri,
            resource_namespace,
            ontology,
        )

        object_resource = add_entity(
            graph,
            object_text,
            object_class_uri,
            resource_namespace,
            ontology,
        )

        predicate_uri = URIRef(
            predicate_uri_text
        )

        validate_property_uri(
            ontology,
            predicate_uri,
        )

        triple = (
            subject_resource,
            predicate_uri,
            object_resource,
        )

        if triple not in graph:
            relationship_triple_count += 1

        graph.add(triple)

    return graph, relationship_triple_count


def validate_generated_rdf(
    rdf_path: Path,
) -> Graph:
    """Parse the saved Turtle file again."""

    validation_graph = Graph()

    validation_graph.parse(
        str(rdf_path),
        format="turtle",
    )

    return validation_graph


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Convert reviewed ontology-guided JSON "
            "into DAOnt-aligned RDF Turtle."
        )
    )

    parser.add_argument(
        "entities_file",
        help=(
            "Reviewed ontology entity JSON file"
        ),
    )

    parser.add_argument(
        "relationships_file",
        help=(
            "Reviewed ontology relationship JSON file"
        ),
    )

    parser.add_argument(
        "ontology_file",
        help="DAOnt Turtle ontology file",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="paw_file_daont_graph.ttl",
        help="Output RDF Turtle file",
    )

    parser.add_argument(
        "--base-url",
        default=(
            "https://example.org/"
            "paw/resource"
        ),
        help=(
            "Base URI for patent entity resources"
        ),
    )

    arguments = parser.parse_args()

    entities_path = Path(
        arguments.entities_file
    )

    relationships_path = Path(
        arguments.relationships_file
    )

    ontology_path = Path(
        arguments.ontology_file
    )

    output_path = Path(
        arguments.output
    )

    entities = load_json(
        entities_path
    )

    relationships = load_json(
        relationships_path
    )

    if not ontology_path.exists():
        raise FileNotFoundError(
            f"Ontology file not found: "
            f"{ontology_path}"
        )

    ontology = Graph()

    ontology.parse(
        str(ontology_path),
        format="turtle",
    )

    graph, relationship_count = (
        create_rdf_graph(
            entities,
            relationships,
            ontology,
            arguments.base_url,
        )
    )

    graph.serialize(
        destination=str(output_path),
        format="turtle",
    )

    validation_graph = (
        validate_generated_rdf(
            output_path
        )
    )

    print()
    print("DAOnt RDF generation successful.")

    print(
        f"Reviewed entities loaded: "
        f"{len(entities)}"
    )

    print(
        f"Reviewed relationships loaded: "
        f"{len(relationships)}"
    )

    print(
        f"Relationship triples added: "
        f"{relationship_count}"
    )

    print(
        f"Total RDF triples: "
        f"{len(graph)}"
    )

    print(
        f"Validated RDF triples: "
        f"{len(validation_graph)}"
    )

    print(f"Saved to: {output_path}")


if __name__ == "__main__":
    main()
