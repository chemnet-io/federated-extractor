import argparse
import hashlib
import html
from pathlib import Path

from pyvis.network import Network
from rdflib import BNode, Graph, Literal, RDF, RDFS, URIRef


def readable_name(term, graph: Graph) -> str:
    """Return a readable label for an RDF term."""

    if isinstance(term, Literal):
        return str(term)

    label = graph.value(term, RDFS.label)

    if label is not None:
        return str(label)

    text = str(term)

    if "#" in text:
        return text.rsplit("#", 1)[-1]

    if "/" in text:
        final_part = text.rstrip("/").rsplit("/", 1)[-1]

        if final_part:
            return final_part

    return text


def shortened_label(text: str, maximum_length: int = 70) -> str:
    """Shorten visible labels while preserving full hover text."""

    text = " ".join(text.split())

    if len(text) <= maximum_length:
        return text

    return text[: maximum_length - 3] + "..."


def term_id(term) -> str:
    """
    Create a unique visualization ID for an RDF term.

    URI resources use their complete URI. Literals use a hash
    containing their value, language and datatype.
    """

    if isinstance(term, URIRef):
        return f"uri:{term}"

    if isinstance(term, BNode):
        return f"blank:{term}"

    if isinstance(term, Literal):
        encoded_literal = term.n3().encode("utf-8")

        digest = hashlib.sha256(
            encoded_literal
        ).hexdigest()

        return f"literal:{digest}"

    return f"term:{term}"


def node_group(term, graph: Graph) -> str:
    """Determine a group used for visual organization."""

    if isinstance(term, Literal):
        return "Literal"

    if isinstance(term, BNode):
        return "Blank node"

    rdf_type = next(
        graph.objects(term, RDF.type),
        None,
    )

    if rdf_type is not None:
        return readable_name(rdf_type, graph)

    return "RDF resource"


def node_title(term, graph: Graph) -> str:
    """Create the full hover information for a node."""

    readable = readable_name(term, graph)

    if isinstance(term, Literal):
        details = [
            f"<b>Literal</b>: {html.escape(readable)}",
        ]

        if term.language:
            details.append(
                f"<b>Language</b>: {html.escape(term.language)}"
            )

        if term.datatype:
            details.append(
                f"<b>Datatype</b>: "
                f"{html.escape(str(term.datatype))}"
            )

        return "<br>".join(details)

    return (
        f"<b>Label</b>: {html.escape(readable)}"
        f"<br><b>RDF identifier</b>: "
        f"{html.escape(str(term))}"
    )


def add_term_node(
    network: Network,
    term,
    graph: Graph,
    added_nodes: set[str],
) -> str:
    """Add an RDF subject or object as a visualization node."""

    identifier = term_id(term)

    if identifier in added_nodes:
        return identifier

    readable = readable_name(term, graph)

    if isinstance(term, Literal):
        shape = "box"
        size = 10
    elif isinstance(term, BNode):
        shape = "ellipse"
        size = 12
    else:
        shape = "dot"
        size = 14

    network.add_node(
        identifier,
        label=shortened_label(readable),
        title=node_title(term, graph),
        group=node_group(term, graph),
        shape=shape,
        size=size,
    )

    added_nodes.add(identifier)

    return identifier


def create_full_visualization(
    rdf_path: Path,
    output_path: Path,
) -> None:
    """Visualize every triple contained in an RDF Turtle file."""

    graph = Graph()

    graph.parse(
        str(rdf_path),
        format="turtle",
    )

    network = Network(
        height="100vh",
        width="100%",
        directed=True,
        notebook=False,
        neighborhood_highlight=True,
        select_menu=True,
        filter_menu=True,
        cdn_resources="in_line",
        heading="Complete RDF Knowledge Graph",
    )

    added_nodes: set[str] = set()
    edge_count = 0

    # Every RDF triple is added. There is no result limit.
    for subject, predicate, object_value in graph:
        subject_id = add_term_node(
            network,
            subject,
            graph,
            added_nodes,
        )

        object_id = add_term_node(
            network,
            object_value,
            graph,
            added_nodes,
        )

        predicate_label = readable_name(
            predicate,
            graph,
        )

        network.add_edge(
            subject_id,
            object_id,
            id=f"rdf-edge-{edge_count}",
            label=shortened_label(
                predicate_label,
                maximum_length=40,
            ),
            title=(
                f"<b>Predicate</b>: "
                f"{html.escape(predicate_label)}"
                f"<br><b>URI</b>: "
                f"{html.escape(str(predicate))}"
            ),
            arrows="to",
        )

        edge_count += 1

    network.set_options(
        """
        var options = {
          "interaction": {
            "hover": true,
            "navigationButtons": true,
            "keyboard": true,
            "multiselect": true,
            "hideEdgesOnDrag": true,
            "hideEdgesOnZoom": true
          },
          "nodes": {
            "font": {
              "size": 11
            },
            "scaling": {
              "min": 8,
              "max": 35
            }
          },
          "edges": {
            "arrows": {
              "to": {
                "enabled": true,
                "scaleFactor": 0.45
              }
            },
            "font": {
              "size": 7,
              "align": "middle"
            },
            "smooth": {
              "enabled": false
            },
            "width": 0.7
          },
          "physics": {
            "enabled": true,
            "solver": "forceAtlas2Based",
            "stabilization": {
              "enabled": true,
              "iterations": 500,
              "updateInterval": 25,
              "fit": true
            },
            "forceAtlas2Based": {
              "gravitationalConstant": -45,
              "centralGravity": 0.005,
              "springLength": 110,
              "springConstant": 0.025,
              "damping": 0.7,
              "avoidOverlap": 0.15
            }
          }
        }
        """
    )

    network.write_html(
        str(output_path),
        notebook=False,
        open_browser=False,
    )

    print()
    print(f"RDF triples loaded: {len(graph)}")
    print(
        f"Visualization nodes: "
        f"{len(network.nodes)}"
    )
    print(
        f"Visualization edges: "
        f"{len(network.edges)}"
    )

    if len(network.edges) != len(graph):
        raise RuntimeError(
            "Not every RDF triple was added to the visualization."
        )

    print("All RDF triples were added successfully.")
    print(f"Saved to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Create an interactive visualization containing "
            "every triple in an RDF Turtle file."
        )
    )

    parser.add_argument(
        "rdf_file",
        help="Input RDF Turtle file",
    )

    parser.add_argument(
        "-o",
        "--output",
        default="paw_file_full_graph.html",
        help="Output HTML visualization",
    )

    arguments = parser.parse_args()

    rdf_path = Path(arguments.rdf_file)
    output_path = Path(arguments.output)

    if not rdf_path.exists():
        raise FileNotFoundError(
            f"RDF file not found: {rdf_path}"
        )

    create_full_visualization(
        rdf_path,
        output_path,
    )


if __name__ == "__main__":
    main()