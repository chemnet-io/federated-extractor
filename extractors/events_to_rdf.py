"""Convert reviewed event JSON into an RDF Turtle graph."""

import argparse
import hashlib
import json
import re
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS


EX = Namespace("https://example.org/federated-extractor/event/")
RES = Namespace("https://example.org/federated-extractor/resource/")


def normalize(value):
    if value is None:
        return ""
    return " ".join(str(value).split()).strip()


def make_id(prefix, value):
    digest = hashlib.sha256(
        value.casefold().encode("utf-8")
    ).hexdigest()[:16]
    return RES[f"{prefix}_{digest}"]


def safe_class_name(value):
    name = re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")
    return name or "UnknownEvent"


def convert(input_json, output_ttl):
    events = json.loads(
        Path(input_json).read_text(encoding="utf-8")
    )

    graph = Graph()
    graph.bind("event", EX)
    graph.bind("res", RES)
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)

    graph.add((EX.Event, RDF.type, RDFS.Class))
    graph.add((EX.Actor, RDF.type, RDFS.Class))
    graph.add((EX.Target, RDF.type, RDFS.Class))

    event_count = 0

    for event in events:
        event_type = normalize(event.get("event_type"))
        trigger = normalize(event.get("trigger"))
        actor = normalize(event.get("actor"))
        action = normalize(event.get("action"))
        target = normalize(event.get("target"))
        context = normalize(event.get("context"))
        evidence = normalize(event.get("evidence"))

        if not event_type or not actor or not target:
            continue

        identity = json.dumps(
            event,
            sort_keys=True,
            ensure_ascii=False,
        )

        event_uri = make_id("event", identity)
        actor_uri = make_id("actor", actor)
        target_uri = make_id("target", target)
        event_class = EX[safe_class_name(event_type)]

        graph.add((event_class, RDF.type, RDFS.Class))
        graph.add((event_class, RDFS.subClassOf, EX.Event))
        graph.add((event_class, RDFS.label, Literal(event_type)))

        graph.add((event_uri, RDF.type, EX.Event))
        graph.add((event_uri, RDF.type, event_class))

        graph.add((actor_uri, RDF.type, EX.Actor))
        graph.add((actor_uri, RDFS.label, Literal(actor)))

        graph.add((target_uri, RDF.type, EX.Target))
        graph.add((target_uri, RDFS.label, Literal(target)))

        graph.add((event_uri, EX.hasActor, actor_uri))
        graph.add((event_uri, EX.hasTarget, target_uri))
        graph.add((event_uri, EX.trigger, Literal(trigger)))
        graph.add((event_uri, EX.action, Literal(action)))
        graph.add((event_uri, EX.evidence, Literal(evidence)))
        graph.add((event_uri, EX.sourceExtractor, Literal("events.py")))

        if context:
            graph.add((event_uri, EX.context, Literal(context)))

        label = f"{actor} — {action or trigger} — {target}"
        graph.add((event_uri, RDFS.label, Literal(label)))

        event_count += 1

    output_path = Path(output_ttl)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph.serialize(
        destination=str(output_path),
        format="turtle",
    )

    # Validate that the generated Turtle can be parsed.
    validation_graph = Graph()
    validation_graph.parse(output_path, format="turtle")

    print("Events converted:", event_count)
    print("RDF triples:", len(validation_graph))
    print("Saved:", output_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_json")
    parser.add_argument("output_ttl")
    args = parser.parse_args()

    convert(args.input_json, args.output_ttl)


if __name__ == "__main__":
    main()
