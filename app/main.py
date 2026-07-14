from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Header
from pathlib import Path
import shutil
import os
from shared.db import init_db, add_pdf, verify_token_hash
from shared.crypto import hash_token

app = FastAPI()
REPO_ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = Path(os.getenv("EXTRACTOR_UPLOAD_DIR", REPO_ROOT / "uploads"))

# Initialize DB on startup
@app.on_event("startup")
async def startup_event():
    init_db()

def verify_token(x_api_token: str = Header(...)):
    """
    Verifies the token by hashing it with EXTRACTOR_SYSTEM_KEY 
    and checking if the resulting hash exists in the database.
    """
    token_hash = hash_token(x_api_token)
    if not verify_token_hash(token_hash):
        raise HTTPException(status_code=403, detail="Invalid or missing API Token")
    return x_api_token

@app.post("/upload")
async def upload_pdf(
    file: UploadFile(File(...)), 
    token: str = Depends(verify_token)
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    file_path = UPLOAD_DIR / file.filename

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Index the file in SQLite
        add_pdf(file.filename)
        
        return {"message": f"File {file.filename} uploaded and indexed successfully", "status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
