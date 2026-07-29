"""Offline validation for the committed Task 3A QLever setup."""

from __future__ import annotations

import configparser
import unittest
from pathlib import Path

from rdflib import Graph, URIRef
from rdflib.namespace import RDF, RDFS


REPO_ROOT = Path(__file__).resolve().parents[1]
QLEVER_DIR = REPO_ROOT / "qlever"
FIXTURE_PATH = QLEVER_DIR / "data" / "task3_fixture.ttl"


class QLeverSetupTest(unittest.TestCase):
    def test_fixture_is_valid_and_contains_expected_resources(self):
        graph = Graph()
        graph.parse(FIXTURE_PATH, format="turtle")

        self.assertGreaterEqual(len(graph), 8)
        algorithm = URIRef(
            "https://chemnet.io/federated-extractor/resource/algorithm-task3"
        )
        algorithm_class = URIRef(
            "https://w3id.org/dao#PostQuantumCryptographicAlgorithm"
        )
        self.assertIn((algorithm, RDF.type, algorithm_class), graph)
        self.assertIn((algorithm, RDFS.label, None), graph)

    def test_qleverfile_points_to_the_committed_fixture(self):
        config = configparser.ConfigParser(
            interpolation=configparser.ExtendedInterpolation()
        )
        config.read(QLEVER_DIR / "Qleverfile", encoding="utf-8")

        self.assertEqual(config["data"]["FORMAT"], "ttl")
        self.assertEqual(config["index"]["INPUT_FILES"], "data/task3_fixture.ttl")
        self.assertEqual(config["server"]["PORT"], "7001")
        self.assertNotIn("ACCESS_TOKEN", config["server"])
        self.assertTrue(FIXTURE_PATH.is_file())


if __name__ == "__main__":
    unittest.main()
