"""Authorization tests for the Task 3B QLever gateway."""

from __future__ import annotations

import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import shared.db as database
from app.main import app, get_qlever_client
from shared.crypto import hash_token
from shared.qlever_client import (
    QLeverClient,
    QLeverConfigurationError,
    QLeverResponse,
)


class FakeQLeverClient:
    """Record authorized calls without contacting a real QLever server."""

    def __init__(self):
        self.query_calls = []
        self.update_calls = []
        self.admin_calls = []

    def query(self, sparql_query, accept):
        self.query_calls.append(
            {
                "sparql": sparql_query,
                "accept": accept,
            }
        )
        return QLeverResponse(
            body=b'{"results":{"bindings":[]}}',
            content_type="application/sparql-results+json",
            status_code=200,
        )

    def update(self, sparql_update):
        self.update_calls.append(sparql_update)
        return QLeverResponse(
            body=b'{"status":"ok"}',
            content_type="application/json",
            status_code=200,
        )

    def clear_cache_complete(self):
        self.admin_calls.append("clearcachecomplete")
        return QLeverResponse(
            body=b'{"cache-cleared":true}',
            content_type="application/json",
            status_code=200,
        )


class ConfigurationErrorClient:
    """Simulate a privileged QLever configuration failure."""

    def update(self, sparql_update):
        raise QLeverConfigurationError(
            "private-qlever-secret-must-not-leak"
        )


class QLeverAuthorizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary_directory = tempfile.TemporaryDirectory()
        cls.original_db_path = database.DB_PATH

        database.DB_PATH = (
            Path(cls.temporary_directory.name) / "authorization.db"
        )
        database.init_db()

        cls.tokens = {
            "reader-token": "reader",
            "writer-token": "writer",
            "admin-token": "admin",
        }

        for token, role in cls.tokens.items():
            database.save_token_hash(hash_token(token), role)

        cls.fake_qlever = FakeQLeverClient()
        app.dependency_overrides[get_qlever_client] = (
            lambda: cls.fake_qlever
        )

        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        app.dependency_overrides.clear()
        database.DB_PATH = cls.original_db_path
        cls.temporary_directory.cleanup()

    def setUp(self):
        self.fake_qlever.query_calls.clear()
        self.fake_qlever.update_calls.clear()
        self.fake_qlever.admin_calls.clear()

    def post_query(self, token, body="SELECT * WHERE { ?s ?p ?o }"):
        return self.client.post(
            "/sparql/query",
            headers={
                "X-API-Token": token,
                "Content-Type": "application/sparql-query",
                "Accept": "application/sparql-results+json",
            },
            content=body,
        )

    def post_update(
        self,
        token,
        body='INSERT DATA { <urn:test> <urn:type> "example" }',
    ):
        return self.client.post(
            "/sparql/update",
            headers={
                "X-API-Token": token,
                "Content-Type": "application/sparql-update",
            },
            content=body,
        )

    def test_reader_writer_and_admin_can_query(self):
        for token in self.tokens:
            with self.subTest(token=token):
                response = self.post_query(token)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(len(self.fake_qlever.query_calls), 3)

    def test_reader_cannot_update(self):
        response = self.post_update("reader-token")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Insufficient permissions",
        )
        self.assertEqual(self.fake_qlever.update_calls, [])

    def test_writer_and_admin_can_update(self):
        for token in ("writer-token", "admin-token"):
            with self.subTest(token=token):
                response = self.post_update(token)
                self.assertEqual(response.status_code, 200)

        self.assertEqual(len(self.fake_qlever.update_calls), 2)

    def test_only_admin_can_clear_complete_cache(self):
        for token in ("reader-token", "writer-token"):
            with self.subTest(token=token):
                response = self.client.post(
                    "/qlever/admin/clear-cache",
                    headers={"X-API-Token": token},
                )

                self.assertEqual(response.status_code, 403)

        self.assertEqual(self.fake_qlever.admin_calls, [])

        admin_response = self.client.post(
            "/qlever/admin/clear-cache",
            headers={"X-API-Token": "admin-token"},
        )

        self.assertEqual(admin_response.status_code, 200)
        self.assertEqual(
            self.fake_qlever.admin_calls,
            ["clearcachecomplete"],
        )

    def test_invalid_token_is_rejected_before_qlever_call(self):
        response = self.post_query("invalid-token")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.fake_qlever.query_calls, [])

    def test_wrong_query_content_type_is_rejected(self):
        response = self.client.post(
            "/sparql/query",
            headers={
                "X-API-Token": "reader-token",
                "Content-Type": "text/plain",
            },
            content="SELECT * WHERE { ?s ?p ?o }",
        )

        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.fake_qlever.query_calls, [])

    def test_empty_query_is_rejected(self):
        response = self.post_query("reader-token", body="   ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.fake_qlever.query_calls, [])

    def test_internal_configuration_details_are_not_returned(self):
        app.dependency_overrides[get_qlever_client] = (
            lambda: ConfigurationErrorClient()
        )

        try:
            response = self.post_update("admin-token")
        finally:
            app.dependency_overrides[get_qlever_client] = (
                lambda: self.fake_qlever
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"],
            "QLever privileged operations are not configured",
        )
        self.assertNotIn(
            "private-qlever-secret",
            response.text,
        )


class QLeverClientSecurityTest(unittest.TestCase):
    def test_internal_token_is_only_sent_for_privileged_operations(self):
        captured_requests = []

        class FakeResponse:
            status = 200

            def __init__(self):
                self.headers = Message()
                self.headers["Content-Type"] = "application/json"

            def read(self):
                return b'{"status":"ok"}'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def fake_urlopen(request, timeout):
            captured_requests.append(request)
            return FakeResponse()

        client = QLeverClient(
            base_url="http://localhost:7001",
            access_token="internal-qlever-secret",
        )

        with patch(
            "shared.qlever_client.urlopen",
            side_effect=fake_urlopen,
        ):
            client.query("SELECT * WHERE { ?s ?p ?o }")
            client.update(
                'INSERT DATA { <urn:test> <urn:type> "example" }'
            )
            client.clear_cache_complete()

        query_request = captured_requests[0]
        update_request = captured_requests[1]
        admin_request = captured_requests[2]

        self.assertIsNone(
            query_request.get_header("Authorization")
        )
        self.assertEqual(
            update_request.get_header("Authorization"),
            "Bearer internal-qlever-secret",
        )
        self.assertEqual(
            admin_request.get_header("Authorization"),
            "Bearer internal-qlever-secret",
        )
        self.assertEqual(
            admin_request.data,
            b"cmd=clearcachecomplete",
        )

        self.assertNotIn(
            b"internal-qlever-secret",
            query_request.data,
        )
        self.assertNotIn(
            b"internal-qlever-secret",
            update_request.data,
        )
        self.assertNotIn(
            b"internal-qlever-secret",
            admin_request.data,
        )


if __name__ == "__main__":
    unittest.main()
