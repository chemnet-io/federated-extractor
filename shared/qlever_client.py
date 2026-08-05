"""HTTP client used internally by FastAPI to communicate with QLever."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DEFAULT_QLEVER_URL = "http://localhost:7001"
DEFAULT_TIMEOUT_SECONDS = 30


class QLeverError(Exception):
    """Base exception for safe QLever client errors."""


class QLeverConfigurationError(QLeverError):
    """Raised when required QLever configuration is missing."""


class QLeverUnavailableError(QLeverError):
    """Raised when FastAPI cannot connect to QLever."""


class QLeverRequestError(QLeverError):
    """Raised when QLever rejects an HTTP request."""

    def __init__(self, status_code: int):
        super().__init__(f"QLever request failed with status {status_code}")
        self.status_code = status_code


@dataclass(frozen=True)
class QLeverResponse:
    """Response returned by QLever without exposing internal credentials."""

    body: bytes
    content_type: str
    status_code: int


class QLeverClient:
    """Small internal client for approved QLever operations."""

    def __init__(
        self,
        base_url: str | None = None,
        access_token: str | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        configured_url = base_url or os.getenv(
            "QLEVER_URL",
            DEFAULT_QLEVER_URL,
        )

        self.base_url = configured_url.rstrip("/")
        self.access_token = (
            access_token
            if access_token is not None
            else os.getenv("QLEVER_ACCESS_TOKEN", "")
        )
        self.timeout = timeout

    def query(
        self,
        sparql_query: str,
        accept: str = "application/sparql-results+json",
    ) -> QLeverResponse:
        """Execute a read-only SPARQL query."""
        return self._send(
            body=sparql_query,
            content_type="application/sparql-query",
            accept=accept,
            include_access_token=False,
        )

    def update(self, sparql_update: str) -> QLeverResponse:
        """Execute a privileged SPARQL update."""
        if not self.access_token:
            raise QLeverConfigurationError(
                "QLEVER_ACCESS_TOKEN is required for SPARQL updates"
            )

        return self._send(
            body=sparql_update,
            content_type="application/sparql-update",
            accept="application/json",
            include_access_token=True,
        )

    def clear_cache_complete(self) -> QLeverResponse:
        """Clear QLever's complete query cache."""
        if not self.access_token:
            raise QLeverConfigurationError(
                "QLEVER_ACCESS_TOKEN is required for admin operations"
            )

        return self._send(
            body=urlencode({"cmd": "clearcachecomplete"}),
            content_type="application/x-www-form-urlencoded",
            accept="application/json",
            include_access_token=True,
        )

    def _send(
        self,
        body: str,
        content_type: str,
        accept: str,
        include_access_token: bool,
    ) -> QLeverResponse:
        headers = {
            "Accept": accept,
            "Content-Type": content_type,
        }

        if include_access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"

        request = Request(
            self.base_url,
            data=body.encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                return QLeverResponse(
                    body=response.read(),
                    content_type=response.headers.get(
                        "Content-Type",
                        "application/octet-stream",
                    ),
                    status_code=response.status,
                )
        except HTTPError as error:
            # Do not include the URL, request headers, or access token in
            # exceptions that could later be converted to API responses.
            raise QLeverRequestError(error.code) from error
        except URLError as error:
            raise QLeverUnavailableError(
                "Unable to connect to QLever"
            ) from error
