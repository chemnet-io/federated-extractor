# Federated Extractor - PDF Upload System

This system provides a FastAPI-based API to upload PDF files and a CLI tool to manage access tokens.

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. (Optional) Set the system secret key for encryption:
   ```bash
   export EXTRACTOR_SYSTEM_KEY="your-secure-random-key"
   ```

## Usage

### 1. Token Management (CLI)
Tokens must be created before they can be used to access the API.

- **Create a token**:
  ```bash
  python cli/manage_tokens.py create
  ```
- **Verify a token**:
  ```bash
  python cli/manage_tokens.py verify <token>
  ```
- **List stored hashes**:
  ```bash
  python cli/manage_tokens.py list
  ```
- **Delete a token**:
  ```bash
  python cli/manage_tokens.py delete <token>
  ```

### 2. Running the API
# ...existing code...

Start the server:
```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python app/main.py
```

### 3. Uploading a PDF
Use a tool like `curl` to upload the file using a created token:
```bash
curl -X POST "http://localhost:8000/upload" \
     -H "x-api-token: my-token" \
     -F "file=@/path/to/your/document.pdf"
```

## System Architecture
- **Database**: SQLite (`system.db`) stores PDF indices and hashed API tokens.
- **Security**: Tokens are stored as non-reversible HMAC-SHA256 hashes using the `EXTRACTOR_SYSTEM_KEY` as a secret. The original token is never stored in the database, making it impossible to recover if the DB is compromised.
- **Storage**: Uploaded PDFs are saved in the `uploads/` directory.

---
## Original Project Info
# federated-extractor
repo that holds the codes for the API access to load the documents, the extractor, and the configuration files for the QLever endpoint

## Diagram

![Diagram](img/T3_3_CEF-INFAI_draft.drawio.png)

