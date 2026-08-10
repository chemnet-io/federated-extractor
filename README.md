# Federated Extractor

## 1. Overview

Federated Extractor turns technical PDF content into structured RDF knowledge
and makes that knowledge available through a protected SPARQL API. FastAPI
handles uploads and application authorization, while QLever stores and queries
the RDF graph.

![Federated Extractor architecture](img/T3_3_CEF-INFAI_draft.drawio.png)

## 2. What it does

- Extracts embedded text from PDFs, with optional OCR fallback.
- Produces RDF using ontology-guided, event, and facts-and-attributes methods.
- Stores uploaded PDFs and token metadata locally.
- Proxies approved SPARQL operations from FastAPI to QLever.
- Protects API operations with `reader`, `writer`, and `admin` tokens.

| Operation | Reader | Writer | Admin |
| --- | --- | --- | --- |
| Query RDF | Yes | Yes | Yes |
| Update RDF | No | Yes | Yes |
| Clear QLever cache | No | No | Yes |

## 3. Setup

### Requirements

The project was built for the following environment:

| Tool | Version / requirement |
| --- | --- |
| Python | 3.12 |
| uv | Current stable release; used to create the virtual environment |
| Docker Engine | Required by QLever; tested with 29.1.3 |
| QLever CLI | 0.5.50 |
| FastAPI | 0.141.1 |
| Uvicorn | 0.52.1 |

The API and QLever Python package versions are pinned in `requirements.txt`.
The extraction scripts additionally require PyMuPDF and spaCy with the small
English model.

### Install and configure

From the repository root:

```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install pymupdf spacy
python -m spacy download en_core_web_sm

cp .env.example .env
```

Edit `.env` and replace the placeholders for `EXTRACTOR_SYSTEM_KEY` and
`QLEVER_ACCESS_TOKEN`. Then load the configuration:

```bash
set -a
source .env
set +a
```

### Start QLever

QLever is managed separately and uses Docker internally:

```bash
cd qlever
qlever index
qlever start --access-token "$QLEVER_ACCESS_TOKEN"
cd ..

python scripts/check_qlever.py
```

QLever listens on `http://localhost:7001`.

### Create API tokens and start FastAPI

Create whichever application roles are needed:

```bash
python -m cli.manage_tokens create --role reader
python -m cli.manage_tokens create --role writer
python -m cli.manage_tokens create --role admin

uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000/docs` for the interactive API documentation.

Example query:

```bash
curl -X POST http://localhost:8000/sparql/query \
  -H "X-API-Token: <reader-token>" \
  -H "Content-Type: application/sparql-query" \
  --data-binary 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'
```

Example PDF upload:

```bash
curl -X POST http://localhost:8000/upload \
  -H "X-API-Token: <application-token>" \
  -F "file=@/path/to/document.pdf;type=application/pdf"
```

## 4. Additional notes

- `.env` contains secrets and must never be committed. `QLEVER_ACCESS_TOKEN`
  is a backend credential and must not be given to API clients.
- Plaintext application tokens are displayed only when created. Their HMAC
  hashes and roles are stored in the local `system.db` SQLite database.
- Uploaded PDFs are stored in `uploads/`; generated extraction results are
  stored below `outputs/`.
- The upload endpoint stores and registers a PDF. Run the extraction scripts
  separately when new RDF output is required.
- Scanned PDFs require OCRmyPDF and Tesseract for the optional OCR fallback.
- Run the complete test suite with:

  ```bash
  python -m unittest discover -s tests -v
  ```
