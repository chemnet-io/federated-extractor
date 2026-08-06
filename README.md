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
contract are documented in `Task3-plan.txt`.

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

## Task 3B: QLever Authorization Gateway

Task 3B adds application-level authorization in front of QLever. Clients
authenticate to FastAPI using an `X-API-Token` header. FastAPI looks up the
token's role and permits only the corresponding QLever operations.

### Roles and permissions

| Operation | Reader | Writer | Admin |
| --- | --- | --- | --- |
| SPARQL query | Allowed | Allowed | Allowed |
| SPARQL update | Denied | Allowed | Allowed |
| Clear complete QLever cache | Denied | Denied | Allowed |

Existing API tokens created before Task 3B are migrated to the least-privileged
`reader` role.

### Create role-based API tokens

Create tokens with the token-management CLI:

~~~bash
python -m cli.manage_tokens create --role reader
python -m cli.manage_tokens create --role writer
python -m cli.manage_tokens create --role admin
~~~

The plaintext token is shown only when it is created. The database stores its
HMAC hash and application role.

Verify a token:

~~~bash
python -m cli.manage_tokens verify <application-token>
~~~

List stored token hashes and roles:

~~~bash
python -m cli.manage_tokens list
~~~

### Start the FastAPI gateway

Load the server-side environment variables and start FastAPI:

~~~bash
set -a
source .env
set +a

uvicorn app.main:app --host 0.0.0.0 --port 8000
~~~

`QLEVER_ACCESS_TOKEN` is an internal backend credential. API clients must never
receive it or send it as their application token.

### Query the graph

Reader, writer, and admin tokens may query:

~~~bash
curl -X POST "http://localhost:8000/sparql/query" \
  -H "X-API-Token: <reader-token>" \
  -H "Content-Type: application/sparql-query" \
  -H "Accept: application/sparql-results+json" \
  --data-binary 'SELECT * WHERE { ?s ?p ?o } LIMIT 10'
~~~

### Update the graph

Only writer and admin tokens may update:

~~~bash
curl -X POST "http://localhost:8000/sparql/update" \
  -H "X-API-Token: <writer-token>" \
  -H "Content-Type: application/sparql-update" \
  --data-binary 'INSERT DATA {
    <urn:example> <urn:status> "created" .
  }'
~~~

A reader token receives HTTP `403` without the request being forwarded to
QLever.

### Clear the QLever cache

Only an admin token may invoke the explicitly allowlisted cache operation:

~~~bash
curl -X POST "http://localhost:8000/qlever/admin/clear-cache" \
  -H "X-API-Token: <admin-token>"
~~~

The gateway does not expose a generic QLever command proxy.

### Run authorization tests

The authorization tests use a temporary SQLite database and a mocked QLever
client, so they do not require a running QLever server:

~~~bash
python -m unittest tests.test_qlever_authorization -v
~~~

Run the complete test suite with:

~~~bash
python -m unittest discover -s tests -v
~~~
