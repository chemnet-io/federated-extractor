"""Run deterministic smoke checks against the Task 3 QLever endpoint."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QLEVER_URL = "http://localhost:7001"
QUERY_DIR = REPO_ROOT / "qlever" / "queries"


def run_query(endpoint: str, query: str) -> dict:
    """Send a SPARQL query to QLever and return its JSON response."""
    request = Request(
        endpoint,
        data=query.encode("utf-8"),
        headers={
            "Accept": "application/sparql-results+json",
            "Content-Type": "application/sparql-query",
        },
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.load(response)


def bindings_for(endpoint: str, query_file: str) -> list[dict]:
    """Load a committed smoke query and return its result bindings."""
    query = (QUERY_DIR / query_file).read_text(encoding="utf-8")
    result = run_query(endpoint, query)
    return result["results"]["bindings"]


def main() -> int:
    endpoint = os.getenv("QLEVER_URL", DEFAULT_QLEVER_URL).rstrip("/")

    try:
        count_bindings = bindings_for(endpoint, "count_triples.sparql")
        triple_count = int(count_bindings[0]["tripleCount"]["value"])
        resource_bindings = bindings_for(endpoint, "sample_resources.sparql")
    except (HTTPError, URLError, KeyError, IndexError, ValueError) as error:
        print(f"QLever smoke check failed: {error}", file=sys.stderr)
        return 1

    if triple_count < 8:
        print(
            f"QLever smoke check failed: expected at least 8 triples, got {triple_count}",
            file=sys.stderr,
        )
        return 1

    labels = {binding["label"]["value"] for binding in resource_bindings}
    expected_labels = {
        "Example technical datasheet",
        "Example post-quantum algorithm",
    }
    missing_labels = expected_labels - labels
    if missing_labels:
        print(
            "QLever smoke check failed: missing labels "
            + ", ".join(sorted(missing_labels)),
            file=sys.stderr,
        )
        return 1

    print(
        f"QLever smoke check passed: {triple_count} triples and "
        f"{len(resource_bindings)} labeled resources"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
