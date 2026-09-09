"""Stage 5: LLM-assisted graph review/visualisation (Ollama).

This module is intentionally kept separate from ``run_pdf_to_rdf.py`` so that
the LLM-assisted logic (prompt construction, the Ollama call, Turtle
extraction, validation, visualisation and reporting) lives in one place and can
be reused or run on its own.

It exposes :func:`run_llm_graph_review`, which:

* builds a compact ontology digest from the DAOnt Turtle file,
* asks an Ollama LLM to review the cleaned-up graph against the source text and
  ontology and return a corrected Turtle graph,
* validates the result by re-parsing it as Turtle,
* writes ``{prefix}_daont_{model}_graph.ttl`` plus a small JSON report, and
* optionally renders the reviewed graph as an interactive HTML visualisation.

The stage degrades gracefully: it is skipped (with a message, and a JSON report
when output was produced but unparseable) when the ``ollama`` package is not
installed, the server is unreachable, or the model output cannot be parsed.

Standalone usage::

    python scripts/llm_graph_review.py <graph.ttl> \
        --text <prefix>.txt --ontology normalizers/daont.ttl \
        --prefix NIST.FIPS.203 --ollama-host http://mac.fritz.box:11434 \
        --llm-model qwen3.8:27b-mlx
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ollama is an optional dependency.  Import it lazily and degrade gracefully so
# the rest of the pipeline keeps working when the package is not installed.
# ---------------------------------------------------------------------------
try:
    from ollama import Client as OllamaClient
except Exception:  # pragma: no cover - only hit when ollama is not installed
    OllamaClient = None  # type: ignore[assignment]


DEFAULT_OLLAMA_HOST = "http://mac.fritz.box:11434"
DEFAULT_LLM_MODEL = "qwen3.8:27b-mlx"
# Cap the source text so the prompt fits comfortably in the model's context.
LLM_MAX_TEXT_CHARS = 12000


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------
def load_ontology_graph(ontology_path: Path):
    """Parse the DAOnt Turtle ontology into an rdflib Graph."""
    from rdflib import Graph

    if not ontology_path.exists():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
    graph = Graph()
    graph.parse(str(ontology_path), format="turtle")
    return graph


def build_ontology_digest(ontology_path: Path, max_terms: int = 120) -> str:
    """Return a compact, human-readable digest of the DAOnt ontology.

    The full Turtle ontology is large, so only the labelled classes and
    properties are extracted and listed.  This gives the reviewer enough
    vocabulary to judge whether the graph's predicates and types are valid
    without blowing the model's context window.
    """
    graph = load_ontology_graph(ontology_path)
    term_labels: dict[str, str] = {}
    term_kinds: dict[str, str] = {}
    for subject, predicate, obj in graph:
        pred = str(predicate)
        term = str(subject)
        # Only keep terms defined in the DAOnt namespace so the digest
        # reflects the vocabulary the pipeline actually validates against.
        if not term.startswith("https://w3id.org/daont#"):
            continue
        if pred.endswith("#label"):
            term_labels[term] = str(obj)
        elif pred.endswith("#type"):
            kind = str(obj).split("#")[-1]
            if kind in {"Class", "DatatypeProperty", "ObjectProperty", "property"}:
                term_kinds[term] = kind

    out: list[str] = []
    listed = 0
    for term in sorted(term_kinds):
        if listed >= max_terms:
            out.append(f"       ... ({len(term_kinds) - max_terms} more terms omitted)")
            break
        label = term_labels.get(term, "")
        short = "dao:" + term.split("#")[-1]
        out.append(
            f"       - {short} [{term_kinds[term]}]"
            + (f' "{label}"' if label else "")
        )
        listed += 1
    if not out:
        out.append("       (no labelled terms could be extracted)")
    return "DAOnt ontology terms:\n" + "\n".join(out)


def build_llm_review_prompt(
    text: str,
    ontology_digest: str,
    graph_turtle: str,
) -> str:
    """Assemble the prompt asking the LLM to review and correct the graph."""
    truncated = text.strip()
    if len(truncated) > LLM_MAX_TEXT_CHARS:
        truncated = truncated[: LLM_MAX_TEXT_CHARS] + "\n... [truncated] ..."

    return f"""You are an expert knowledge-engineering reviewer for the DAOnt
ontology (a patent / hardware knowledge-graph ontology).

You are given three inputs:
1. The source document text (from a PDF).
2. A digest of the DAOnt ontology terms (classes and properties you may use).
3. A cleaned-up RDF graph in Turtle format, built from that document.

TASK:
- Check the Turtle graph for problems: wrong or invalid DAOnt classes/properties,
  missing important entities/relationships that are present in the source text,
  incorrect or unsupported relationships, duplicate or contradictory triples,
  malformed Turtle, and labels that do not match the source.
- Produce a single corrected, improved version of the graph.
- Keep the SAME prefix declarations (@prefix dao:, rdfs:, res:) and resource
  naming style.
- Use ONLY the DAOnt terms shown in the ontology digest for types and
  predicates (unless the original graph already used a fully-qualified external
  URI like <https://w3id.org/amv#...>, which may be kept).
- Add relationships/entities that are clearly supported by the source text.
- Output ONLY the corrected Turtle graph, nothing else. Do not wrap it in
  Markdown code fences. Do not add commentary.

=== SOURCE DOCUMENT TEXT ===
{truncated}

=== ONTOLOGY DIGEST ===
{ontology_digest}

=== CURRENT (CLEANED-UP) TURTLE GRAPH ===
{graph_turtle}

=== CORRECTED TURTLE GRAPH (output only this) ===
"""


def extract_turtle_from_response(response_text: str) -> str:
    """Pull Turtle out of an LLM response, tolerating Markdown code fences."""
    cleaned = response_text.strip()
    # Strip a leading/trailing ```turtle ... ``` (or plain ``` ) code fence.
    if cleaned.startswith("```"):
        raw_lines = cleaned.splitlines()
        if raw_lines and raw_lines[0].startswith("```"):
            raw_lines = raw_lines[1:]
        if raw_lines and raw_lines[-1].strip() == "```":
            raw_lines = raw_lines[:-1]
        cleaned = "\n".join(raw_lines).strip()
    return cleaned


def _extract_text(response: object) -> str:
    """Best-effort text extraction from an Ollama streaming/structured response."""
    if hasattr(response, "__iter__") and not isinstance(response, str):
        parts: list[str] = []
        for chunk in response:
            msg = getattr(chunk, "message", None)
            if msg is not None:
                parts.append(getattr(msg, "content", "") or "")
            elif isinstance(chunk, dict):
                msg_d = chunk.get("message") or {}
                parts.append(msg_d.get("content", "") or "")
        return "".join(parts)
    return str(response)


# ---------------------------------------------------------------------------
# Stage 5 orchestration
# ---------------------------------------------------------------------------
def run_llm_graph_review(
    rdf_path: Path,
    prefix: str,
    output_dir: Path,
    host: str = DEFAULT_OLLAMA_HOST,
    model: str = DEFAULT_LLM_MODEL,
    text_path: Path | None = None,
    ontology_path: Path | None = None,
    html_output_path: Path | None = None,
    visualizer_module=...,  # type: ignore[assignment]
) -> tuple[Path | None, Path | None, Path | None]:
    """Use an LLM (Ollama) to review/validate a cleaned-up RDF graph.

    The LLM is given the PDF text (``text_path``), an ontology digest
    (``ontology_path``), and the cleaned-up Turtle graph (``rdf_path``), and is
    asked to return a corrected version.  The result is written to
    ``{output_dir}/{prefix}_daont_{model}_graph.ttl`` together with a small
    JSON report, and -- when ``html_output_path`` and a ``visualizer_module``
    are supplied -- rendered to an interactive HTML visualisation.

    Returns a ``(llm_graph_path, llm_report_path, llm_html_path)`` tuple.  Any
    element is ``None`` when that artifact was not produced.  The stage is
    skipped (graph/report ``None``) when the ``ollama`` package is not
    installed, the server is unreachable, or the model output cannot be parsed
    into valid Turtle -- but a JSON report is still written in that last case
    so the raw response can be inspected.
    """
    print(f"[5/5] LLM graph review via Ollama ({host}, model={model})...")
    sys.stdout.flush()

    if OllamaClient is None:
        print(
            "[5/5] Skipping LLM review ('ollama' is not installed; "
            "run 'uv pip install ollama' to enable it)."
        )
        return None, None, None

    # A filename-safe version of the model name, e.g. "qwen3.8:27b-mlx"
    # -> "qwen3.8_27b-mlx".
    model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", model)
    llm_graph_path = output_dir / f"{prefix}_daont_{model_slug}_graph.ttl"
    llm_report_path = output_dir / f"{prefix}_daont_{model_slug}_graph_report.json"

    source_text = ""
    if text_path is not None and text_path.exists():
        source_text = text_path.read_text(encoding="utf-8", errors="replace")
    ontology_digest = ""
    if ontology_path is not None:
        ontology_digest = build_ontology_digest(ontology_path)
    graph_turtle = rdf_path.read_text(encoding="utf-8")

    prompt = build_llm_review_prompt(source_text, ontology_digest, graph_turtle)

    try:
        client = OllamaClient(host=host)
        response = client.chat(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as error:
        print(
            f"[5/5] LLM review skipped: could not reach Ollama at {host} "
            f"with model '{model}' ({type(error).__name__}: {error})."
        )
        return None, None, None

    # ``chat`` may return a response object or an iterator of chunks.
    response_text = ""
    if hasattr(response, "message") and response.message is not None:
        response_text = getattr(response.message, "content", "") or ""
    elif isinstance(response, (list, tuple, dict)):
        response_text = _extract_text(response)
    else:
        response_text = str(response)

    turtle_out = extract_turtle_from_response(response_text)

    # Validate the LLM output by re-parsing it as Turtle.
    from rdflib import Graph as _Graph

    parsed = _Graph()
    try:
        parsed.parse(data=turtle_out, format="turtle")
    except Exception as error:
        print(
            f"[5/5] LLM review skipped: model output could not be parsed as "
            f"Turtle ({type(error).__name__}: {error})."
        )
        # Still persist the raw response for debugging.
        llm_report_path.parent.mkdir(parents=True, exist_ok=True)
        llm_report_path.write_text(
            json.dumps(
                {
                    "model": model,
                    "host": host,
                    "status": "unparseable_output",
                    "error": f"{type(error).__name__}: {error}",
                    "raw_response": response_text,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return None, llm_report_path, None

    llm_graph_path.parent.mkdir(parents=True, exist_ok=True)
    parsed.serialize(destination=str(llm_graph_path), format="turtle")

    input_triples = len(_Graph().parse(str(rdf_path), format="turtle"))

    # Optional visualisation of the reviewed graph (degrades gracefully when
    # the visualizer is not available -- e.g. pyvis is not installed).
    llm_html_path: Path | None = None
    if html_output_path is not None:
        if visualizer_module is ...:
            visualizer_module = None
        if visualizer_module is not None:
            try:
                visualizer_module.create_full_visualization(
                    llm_graph_path, html_output_path
                )
                llm_html_path = html_output_path
                print(f"[5/5] LLM graph visualization -> {llm_html_path}")
            except ModuleNotFoundError:
                print(
                    "[5/5] Skipping LLM graph visualization (pyvis is not "
                    "installed; run 'uv pip install pyvis' to enable it)."
                )
        else:
            print(
                "[5/5] Skipping LLM graph visualization (visualizer module "
                "unavailable)."
            )

    report = {
        "model": model,
        "host": host,
        "status": "ok",
        "input_triples": input_triples,
        "output_triples": len(parsed),
        "output_graph": str(llm_graph_path),
        "output_html": str(llm_html_path) if llm_html_path is not None else None,
    }
    llm_report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"[5/5] LLM review complete: {input_triples} -> {len(parsed)} triples "
        f"-> {llm_graph_path.name}"
    )
    sys.stdout.flush()
    return llm_graph_path, llm_report_path, llm_html_path


# ---------------------------------------------------------------------------
# Standalone CLI
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review/correct a cleaned-up RDF graph with an Ollama LLM."
    )
    parser.add_argument("rdf_path", help="Cleaned-up RDF graph (Turtle) to review.")
    parser.add_argument("--prefix", default=None, help="Output filename prefix.")
    parser.add_argument("--ontology", default=None, help="DAOnt Turtle ontology file.")
    parser.add_argument("--text", default=None, help="Source text file.")
    parser.add_argument("--out-dir", default="outputs/rdf", help="Output directory.")
    parser.add_argument("--html", default=None, help="HTML visualisation output path.")
    parser.add_argument("--no-visualize", action="store_true")
    parser.add_argument(
        "--ollama-host", default=DEFAULT_OLLAMA_HOST, help="Ollama server URL."
    )
    parser.add_argument(
        "--llm-model", default=DEFAULT_LLM_MODEL, help="Ollama model name."
    )
    arguments = parser.parse_args()

    rdf_path = Path(arguments.rdf_path)
    if not rdf_path.exists():
        print(f"RDF file not found: {rdf_path}", file=sys.stderr)
        return 1

    prefix = arguments.prefix or rdf_path.stem
    output_dir = Path(arguments.out_dir)

    html_path = None
    visualizer_module = ...
    if arguments.html and not arguments.no_visualize:
        html_path = Path(arguments.html)
        try:
            from run_pdf_to_rdf import load_visualizer_module

            visualizer_module = load_visualizer_module()
        except Exception:
            visualizer_module = None

    llm_graph_path, llm_report_path, llm_html_path = run_llm_graph_review(
        rdf_path=rdf_path,
        prefix=prefix,
        output_dir=output_dir,
        host=arguments.ollama_host,
        model=arguments.llm_model,
        text_path=Path(arguments.text) if arguments.text else None,
        ontology_path=Path(arguments.ontology) if arguments.ontology else None,
        html_output_path=html_path,
        visualizer_module=visualizer_module,
    )

    print("")
    print("LLM review artifacts:")
    for label, value in (
        ("reviewed turtle", llm_graph_path),
        ("report json", llm_report_path),
        ("visualization html", llm_html_path),
    ):
        if value is not None:
            print(f"  - {label}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
