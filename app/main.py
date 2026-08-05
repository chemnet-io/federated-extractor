import os
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, Response, UploadFile

from app.auth import AuthenticatedToken, authenticate_api_token, require_roles
from shared.db import add_pdf, init_db
from shared.qlever_client import (
    QLeverClient,
    QLeverConfigurationError,
    QLeverRequestError,
    QLeverResponse,
    QLeverUnavailableError,
)


app = FastAPI()

REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = Path(
    os.getenv("EXTRACTOR_UPLOAD_DIR", REPO_ROOT / "uploads")
)

QUERY_AUTHORIZATION = require_roles("reader", "writer", "admin")
UPDATE_AUTHORIZATION = require_roles("writer", "admin")
ADMIN_AUTHORIZATION = require_roles("admin")


@app.on_event("startup")
async def startup_event():
    """Initialize the application database when FastAPI starts."""
    init_db()


def get_qlever_client() -> QLeverClient:
    """Create the internal QLever client from server-side configuration."""
    return QLeverClient()


def decode_sparql_body(body: bytes, operation: str) -> str:
    """Decode and validate a raw SPARQL request body."""
    try:
        sparql = body.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail=f"SPARQL {operation} must be valid UTF-8",
        ) from error

    if not sparql.strip():
        raise HTTPException(
            status_code=400,
            detail=f"SPARQL {operation} body is required",
        )

    return sparql


def qlever_response(response: QLeverResponse) -> Response:
    """Return QLever's body without exposing internal request headers."""
    return Response(
        content=response.body,
        status_code=response.status_code,
        headers={"Content-Type": response.content_type},
    )


def raise_qlever_http_error(error: Exception) -> None:
    """Convert internal QLever errors to safe API responses."""
    if isinstance(error, QLeverConfigurationError):
        raise HTTPException(
            status_code=503,
            detail="QLever privileged operations are not configured",
        ) from error

    if isinstance(error, QLeverUnavailableError):
        raise HTTPException(
            status_code=503,
            detail="QLever service is unavailable",
        ) from error

    if isinstance(error, QLeverRequestError):
        api_status = 400 if error.status_code < 500 else 502
        raise HTTPException(
            status_code=api_status,
            detail="QLever rejected the request",
        ) from error

    raise error


@app.post("/upload")
async def upload_pdf(
    file: UploadFile = File(...),
    authenticated_token: AuthenticatedToken = Depends(
        authenticate_api_token
    ),
):
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed",
        )

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        add_pdf(file.filename)

        return {
            "message": (
                f"File {file.filename} uploaded and indexed successfully"
            ),
            "status": "success",
        }
    except Exception as error:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {error}",
        ) from error


@app.post("/sparql/query")
async def sparql_query(
    request: Request,
    authenticated_token: AuthenticatedToken = Depends(
        QUERY_AUTHORIZATION
    ),
    client: QLeverClient = Depends(get_qlever_client),
):
    """Proxy an authorized read-only SPARQL query to QLever."""
    content_type = request.headers.get("content-type", "").split(";")[0]

    if content_type.lower() != "application/sparql-query":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/sparql-query",
        )

    sparql = decode_sparql_body(await request.body(), "query")
    accept = request.headers.get(
        "accept",
        "application/sparql-results+json",
    )

    try:
        response = client.query(sparql, accept=accept)
    except (
        QLeverConfigurationError,
        QLeverRequestError,
        QLeverUnavailableError,
    ) as error:
        raise_qlever_http_error(error)

    return qlever_response(response)


@app.post("/sparql/update")
async def sparql_update(
    request: Request,
    authenticated_token: AuthenticatedToken = Depends(
        UPDATE_AUTHORIZATION
    ),
    client: QLeverClient = Depends(get_qlever_client),
):
    """Proxy an authorized SPARQL update to QLever."""
    content_type = request.headers.get("content-type", "").split(";")[0]

    if content_type.lower() != "application/sparql-update":
        raise HTTPException(
            status_code=415,
            detail="Content-Type must be application/sparql-update",
        )

    sparql = decode_sparql_body(await request.body(), "update")

    try:
        response = client.update(sparql)
    except (
        QLeverConfigurationError,
        QLeverRequestError,
        QLeverUnavailableError,
    ) as error:
        raise_qlever_http_error(error)

    return qlever_response(response)


@app.post("/qlever/admin/clear-cache")
async def clear_qlever_cache(
    authenticated_token: AuthenticatedToken = Depends(
        ADMIN_AUTHORIZATION
    ),
    client: QLeverClient = Depends(get_qlever_client),
):
    """Clear QLever's complete cache for an authorized administrator."""
    try:
        response = client.clear_cache_complete()
    except (
        QLeverConfigurationError,
        QLeverRequestError,
        QLeverUnavailableError,
    ) as error:
        raise_qlever_http_error(error)

    return qlever_response(response)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
