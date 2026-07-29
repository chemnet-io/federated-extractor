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


## Task 2: Text-to-RDF Knowledge Extraction

This task experiments with three approaches for extracting knowledge from the
same patent text and representing the extracted information as RDF graphs.

### Extraction approaches

1. Ontology-guided extraction
   - Uses the DAOnt ontology to identify relevant entities and relationships.
   - Produces a small ontology-aligned RDF graph.

2. Event extraction
   - Extracts actors, actions, targets, triggers, evidence, and context.
   - Converts the reviewed events into an RDF graph.

3. Facts-and-attributes extraction
   - Extracts entities, attributes, values, optional units, and evidence.
   - Converts the reviewed technical facts into an RDF graph.

### Main implementation files

- `extractors/events.py`
- `extractors/events_to_rdf.py`
- `extractors/facts_attributes.py`
- `extractors/facts_attributes_to_rdf.py`
- `extractors/text_preprocessing.py`

### Example RDF results

- `outputs/rdf/paw_file_daont_graph.ttl`
- `outputs/rdf/paw_file_events_graph.ttl`
- `outputs/rdf/paw_file_facts_attributes_graph.ttl`

### Comparison

The ontology-guided extractor produced the smallest and most precise graph,
but with limited coverage. The event extractor produced broader coverage but
introduced more extraction and visualization noise. The facts-and-attributes
extractor produced structured technical statements with moderate coverage
and relatively low noise. This experiment demonstrates the trade-off between
precision and coverage among different knowledge-extraction approaches.

## Task 3A: QLever SPARQL Endpoint Foundation

Task 3A provides the QLever configuration and reproducible test data used by
the Task 3B authorization gateway. The complete ownership split and integration
contract are documented in `Task 3 Plan.txt`.

### Prerequisites

- Docker
- The `qlever` command-line tool

Follow the official QLever installation instructions for your operating
system: https://docs.qlever.dev/quickstart/

### Configure secrets

Copy `.env.example` to `.env` and set `QLEVER_ACCESS_TOKEN` locally. The
repository intentionally contains no QLever credential.

Export the values before running QLever. For example:

```bash
set -a
source .env
set +a
```

### Build and start the endpoint

Run QLever from the directory containing `Qleverfile`:

```bash
cd qlever
qlever index
qlever start --access-token "$QLEVER_ACCESS_TOKEN"
```

The endpoint listens on `http://localhost:7001` by default. The committed
fixture in `qlever/data/task3_fixture.ttl` provides deterministic data for
initial development. Generated RDF files can be added to `INPUT_FILES` in the
Qleverfile during pipeline integration.

The access token protects SPARQL updates and administrative operations. It
must only be used by the backend authorization gateway implemented in Task 3B;
it must never be returned to API clients.

### Smoke check

With QLever running, execute:

```bash
python scripts/check_qlever.py
```

To test another endpoint:

```bash
QLEVER_URL=http://localhost:7001 python scripts/check_qlever.py
```

The smoke check verifies the triple count and known fixture resources. The
queries are also available in `qlever/queries/`.

Offline validation, which does not require Docker or QLever, can be run with:

```bash
python -m unittest tests.test_qlever_setup
```
