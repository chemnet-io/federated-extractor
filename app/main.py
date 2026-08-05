import os
import shutil
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile

from app.auth import AuthenticatedToken, authenticate_api_token
from shared.db import add_pdf, init_db


app = FastAPI()

REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = Path(
    os.getenv("EXTRACTOR_UPLOAD_DIR", REPO_ROOT / "uploads")
)


@app.on_event("startup")
async def startup_event():
    """Initialize the application database when FastAPI starts."""
    init_db()


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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
