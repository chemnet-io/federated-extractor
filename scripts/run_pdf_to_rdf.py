"""Run the full PDF-to-RDF ontology pipeline and report per-stage timings.

This script orchestrates the canonical ontology-based (DAOnt) extraction path
so that a single command produces an RDF knowledge graph from a PDF:

     1. PDF text extraction          -> outputs/pdf_text/{stem}.txt
          (extractors.pdf_text.export_pdf_text, with OCR fallback)
     2. Ontology-guided extraction  -> {stem}_ontology_entities.json
                                       {stem}_ontology_relationships.json
          (normalizers.ontology_guided_extractor_v3.extract_data)
     3. RDF conversion               -> outputs/rdf/{stem}_daont_graph.ttl
          (normalizers.rdf_converter_daont.create_rdf_graph)
     4. Interactive visualization    -> outputs/rdf_graph/{stem}_daont_graph.html
          (Kgraph.visualize_full_rdf.create_full_visualization, optional)

Every stage is timed independently and a summary table is printed at the end,
together with the overall elapsed time. The report is also written to a log
file so it is recoverable on disk even if a terminal does not display stdout.

Usage:
    python -m scripts.run_pdf_to_rdf path/to/document.pdf
    python -m scripts.run_pdf_to_rdf document.pdf --no-ocr
    python -m scripts.run_pdf_to_rdf document.pdf --prefix paw_file
    python -m scripts.run_pdf_to_rdf document.pdf --no-visualize
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

# Force line-buffered stdout/stderr so per-stage progress and the final report
# appear immediately, even when stdout is redirected or piped. Without this, a
# heavy stage like the spaCy extraction can leave output sitting in a block
# buffer, so the terminal seems to show only the unbuffered `fitz` warning.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

from extractors.pdf_text import export_pdf_text
from normalizers.ontology_guided_extractor_v3 import extract_data
from normalizers.rdf_converter_daont import (
    create_rdf_graph,
    load_json,
    validate_generated_rdf,
)


DEFAULT_ONTOLOGY = REPO_ROOT / "normalizers" / "daont.ttl"
DEFAULT_BASE_URL = "https://example.org/paw/resource"

OCR_DIR = REPO_ROOT / "outputs" / "ocr"
TEXT_DIR = REPO_ROOT / "outputs" / "pdf_text"
RDF_DIR = REPO_ROOT / "outputs" / "rdf"
RDF_GRAPH_DIR = REPO_ROOT / "outputs" / "rdf_graph"

# The LLM (Ollama) graph-review stage lives in its own module so the
# prompt-building, model call, validation, and visualisation logic can be reused
# or run standalone.  Re-export the defaults and the entry point here for the
# CLI wiring below.
from llm_graph_review import (
    DEFAULT_OLLAMA_HOST,
    DEFAULT_LLM_MODEL,
    run_llm_graph_review,
)


def load_visualizer_module():
    """Load Kgraph/visualize_full_rdf.py even though it lacks an __init__.py.

    The Kgraph folder is a plain directory (no package marker), so a normal
    ``import Kgraph...`` would fail. Loading it by file location keeps the
    orchestration working without restructuring the repository.
    """
    module_path = REPO_ROOT / "Kgraph" / "visualize_full_rdf.py"
    spec = importlib.util.spec_from_file_location(
        "visualize_full_rdf",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load visualizer from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_pdf_to_text(pdf_path: Path, use_ocr: bool) -> Path:
    """Stage 1: extract plain text from the PDF and write a .txt file."""
    output_path = export_pdf_text(
        pdf_path,
        output_dir=TEXT_DIR,
        use_ocr=use_ocr,
        ocr_output_dir=OCR_DIR,
    )
    print(f"[1/5] PDF text extracted -> {output_path}")
    return output_path


def run_ontology_extraction(
    text_path: Path,
    ontology_path: Path,
    prefix: str,
) -> tuple[Path, Path]:
    """Stage 2: extract DAOnt-aligned entities and relationships.

    ``extract_data`` writes its JSON artifacts next to the text file, so this
    stage returns the resolved entity and relationship JSON paths for stage 3.
    """
    extract_data(text_path, ontology_path, prefix)

    entities_path = text_path.parent / f"{prefix}_ontology_entities.json"
    relationships_path = text_path.parent / f"{prefix}_ontology_relationships.json"
    print(
        f"[2/5] Ontology extraction complete -> "
        f"{entities_path.name}, {relationships_path.name}"
    )
    return entities_path, relationships_path


def run_rdf_conversion(
    entities_path: Path,
    relationships_path: Path,
    ontology_path: Path,
    output_path: Path,
    base_url: str,
) -> int:
    """Stage 3: build the DAOnt RDF graph and serialize it to Turtle."""
    entities = load_json(entities_path)
    relationships = load_json(relationships_path)

    ontology = load_json_ontology(ontology_path)
    graph, relationship_count = create_rdf_graph(
        entities,
        relationships,
        ontology,
        base_url,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    graph.serialize(destination=str(output_path), format="turtle")
    validation_graph = validate_generated_rdf(output_path)

    print(
        f"[3/5] RDF graph written -> {output_path} "
        f"({len(graph)} triples, {len(validation_graph)} validated)"
    )
    return len(validation_graph)


def load_json_ontology(ontology_path: Path):
    """Parse the DAOnt Turtle ontology into an rdflib Graph."""
    from rdflib import Graph

    if not ontology_path.exists():
        raise FileNotFoundError(f"Ontology file not found: {ontology_path}")
    graph = Graph()
    graph.parse(str(ontology_path), format="turtle")
    return graph


def run_visualization(rdf_path: Path, output_path: Path) -> Path:
    """Stage 4 (optional): render the RDF graph as an interactive HTML file."""
    module = load_visualizer_module()
    module.create_full_visualization(rdf_path, output_path)
    print(f"[4/5] Visualization written -> {output_path}")
    return output_path


class StageTimer:
    """Accumulate per-stage timings for the final report."""

    def __init__(self) -> None:
        self.records: list[tuple[str, float]] = []

    def record(self, name: str, duration: float) -> None:
        self.records.append((name, duration))


def build_report_text(
    timer: StageTimer,
    overall: float,
    artifacts: dict[str, str],
) -> str:
    """Build the per-stage timing table plus the overall elapsed time."""
    lines: list[str] = []
    lines.append("")
    lines.append("=" * 64)
    lines.append("PIPELINE EXECUTION TIME REPORT")
    lines.append("=" * 64)

    width = 48
    for index, (name, duration) in enumerate(timer.records, start=1):
        share = (duration / overall * 100) if overall > 0 else 0.0
        lines.append(
            f"   {index}. {name:<{width}} "
            f"{duration:8.3f}s    ({share:5.1f}%)"
        )

    lines.append("-" * 64)
    lines.append(f"  Overall elapsed time:        {overall:8.3f}s")
    lines.append("=" * 64)

    lines.append("")
    lines.append("Generated artifacts:")
    for label, value in artifacts.items():
        lines.append(f"    - {label}: {value}")
    lines.append("")
    return "\n".join(lines)


def print_report(
    timer: StageTimer,
    overall: float,
    artifacts: dict[str, str],
    report_log_path: Path | None = None,
) -> None:
    """Print the report and, when given, also save it to ``report_log_path``.

    Writing the report to disk guarantees the timing data is recoverable even
    if a terminal does not display stdout.
    """
    text = build_report_text(timer, overall, artifacts)
    print(text)
    sys.stdout.flush()

    if report_log_path is not None:
        report_log_path.parent.mkdir(parents=True, exist_ok=True)
        with report_log_path.open("w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        print(f"    (report also saved to {report_log_path})")
        sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the full PDF -> RDF (DAOnt) pipeline and report "
            "the execution time of every stage."
        )
    )
    parser.add_argument("pdf_path", help="Path to the input PDF file.")
    parser.add_argument(
        "--prefix",
        default=None,
        help="Output filename prefix. Defaults to the PDF stem.",
    )
    parser.add_argument(
        "--ontology",
        default=str(DEFAULT_ONTOLOGY),
        help="DAOnt Turtle ontology file.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help="Base URI for patent entity resources.",
    )
    parser.add_argument(
        "--no-ocr",
        action="store_true",
        help="Disable OCR fallback when no embedded text is found.",
    )
    parser.add_argument(
        "--no-visualize",
        action="store_true",
        help="Skip the optional HTML visualization stage.",
    )
    parser.add_argument(
         "--no-llm",
        action="store_true",
        help="Skip the optional LLM (Ollama) graph-review stage.",
     )
    parser.add_argument(
         "--ollama-host",
        default=DEFAULT_OLLAMA_HOST,
        help="Ollama server URL for the LLM review stage.",
     )
    parser.add_argument(
         "--llm-model",
        default=DEFAULT_LLM_MODEL,
        help="Ollama model name used to review/validate the graph.",
     )
    arguments = parser.parse_args()

     # Print an immediate, flushed banner so the user sees the script is alive
     # even before the slow spaCy stage produces output.
    print(
        f"PDF -> RDF (DAOnt) pipeline starting on "
        f"'{arguments.pdf_path}'"
        f"{' (no OCR)' if arguments.no_ocr else ''}"
        f"{' (no visualization)' if arguments.no_visualize else ''}"
        f"{' (no LLM review)' if arguments.no_llm else ''}"
    )
    print(f"  interpreter: {sys.executable}")
    sys.stdout.flush()

    pdf_path = Path(arguments.pdf_path)
    ontology_path = Path(arguments.ontology)

    if not pdf_path.exists():
        print(f"PDF file not found: {pdf_path}", file=sys.stderr)
        return 1
    if not ontology_path.exists():
        print(f"Ontology file not found: {ontology_path}", file=sys.stderr)
        return 1

    prefix = arguments.prefix or pdf_path.stem

    report_log_path = RDF_DIR / f"{prefix}_daont_graph_report.log"

    artifacts: dict[str, str] = {
        "input pdf": str(pdf_path),
        "ontology": str(ontology_path),
    }

    timer = StageTimer()
    overall_start = time.perf_counter()

    # Stage 1: PDF -> text
    stage_start = time.perf_counter()
    text_path = run_pdf_to_text(pdf_path, use_ocr=not arguments.no_ocr)
    timer.record("PDF -> text extraction", time.perf_counter() - stage_start)
    artifacts["text"] = str(text_path)

    # Stage 2: ontology-guided extraction
    stage_start = time.perf_counter()
    entities_path, relationships_path = run_ontology_extraction(
        text_path,
        ontology_path,
        prefix,
    )
    timer.record("Ontology-guided extraction", time.perf_counter() - stage_start)
    artifacts["entities json"] = str(entities_path)
    artifacts["relationships json"] = str(relationships_path)

    # Stage 3: RDF conversion
    rdf_path = RDF_DIR / f"{prefix}_daont_graph.ttl"
    stage_start = time.perf_counter()
    run_rdf_conversion(
        entities_path,
        relationships_path,
        ontology_path,
        rdf_path,
        arguments.base_url,
    )
    timer.record("RDF conversion (DAOnt)", time.perf_counter() - stage_start)
    artifacts["rdf turtle"] = str(rdf_path)

    # Stage 4: optional visualization
    if not arguments.no_visualize:
        html_path = RDF_GRAPH_DIR / f"{prefix}_daont_graph.html"
        html_path.parent.mkdir(parents=True, exist_ok=True)
        stage_start = time.perf_counter()
        try:
            run_visualization(rdf_path, html_path)
        except ModuleNotFoundError as error:
            # pyvis is an optional dependency that is not in requirements.txt.
            # Keep the pipeline usable without it by skipping this stage.
            print(
                f"[4/5] Skipping visualization "
                f"({error.name} is not installed; "
                f"run 'uv pip install pyvis' to enable it)."
            )
        else:
            timer.record("RDF visualization", time.perf_counter() - stage_start)
            artifacts["html graph"] = str(html_path)

# Stage 5: optional LLM (Ollama) review + visualization of the graph.
    # The heavy logic lives in scripts/llm_graph_review.py; this block just
    # wires it into the pipeline and records its execution time.
    if not arguments.no_llm:
        model_slug = re.sub(r"[^A-Za-z0-9._-]+", "_", arguments.llm_model)
        llm_html_path_target = RDF_GRAPH_DIR / f"{prefix}_daont_{model_slug}_graph.html"

         # Load the visualizer module once, reusing it for the reviewed-graph
         # HTML (optional; degrades gracefully when pyvis is missing).
        visualizer_module = None
        if not arguments.no_visualize:
            try:
                visualizer_module = load_visualizer_module()
            except Exception:
                visualizer_module = None

        stage_start = time.perf_counter()
        llm_graph_path, llm_report_path, llm_html_path = run_llm_graph_review(
            rdf_path=rdf_path,
            prefix=prefix,
            output_dir=RDF_DIR,
            host=arguments.ollama_host,
            model=arguments.llm_model,
            text_path=text_path,
            ontology_path=ontology_path,
            html_output_path=llm_html_path_target
            if not arguments.no_visualize
            else None,
            visualizer_module=visualizer_module,
         )
        timer.record("LLM graph review", time.perf_counter() - stage_start)
        if llm_graph_path is not None:
            artifacts["llm reviewed rdf turtle"] = str(llm_graph_path)
        if llm_report_path is not None:
            artifacts["llm review report"] = str(llm_report_path)
        if llm_html_path is not None:
            artifacts["llm html graph"] = str(llm_html_path)

    overall = time.perf_counter() - overall_start
    artifacts["timing report log"] = str(report_log_path)

    print_report(timer, overall, artifacts, report_log_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
