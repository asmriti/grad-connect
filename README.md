# GradConnect

A professor-search project for students: **semantic search** over
professor websites, **resume matching**, and the **crawling + indexing**
pipeline that feeds them. Type a research topic (or upload a resume) and get
back professors ranked by how semantically similar their own website content
is — with the exact text passages as evidence.

**No generative LLM is involved anywhere.** The system is pure retrieval:
a local sentence-embedding model plus PostgreSQL/pgvector. Every result links
back to the source page and quotes it verbatim.

## Architecture

```text
data/data.csv
        |
        v
  scripts/ingest.py ──────────────► professors table (PostgreSQL)
        |
        v
  scripts/index.py
        |
        ├─ crawler   (httpx)          fetch homepage + up to N relevant
        |                             same-site pages per professor
        ├─ extractor (BeautifulSoup)  strip boilerplate, keep headings
        ├─ chunker                    ~600-token chunks, ~100-token overlap
        ├─ embeddings                 BAAI/bge-small-en-v1.5, local
        |                             (Sentence Transformers)
        v
  documents + document_chunks tables (pgvector, cosine distance, HNSW index)
        |
        +────────────────┬─────────────────+
        v                v                 v
  scripts/search.py   FastAPI /api/search   FastAPI /api/match
  (CLI debugging)     (semantic search)     (resume matching)
        |
        v
  Next.js frontend (search page + resume-match page + professor detail)
```

## Set up on your computer

Run every command below from the project folder (the directory that contains
`backend/`, `frontend/`, `scripts/`, and `data/`). On macOS and Linux, open
two terminals at the end: one for the API, one for the website.

You need:

- **Python 3.11 or newer.** macOS's `/usr/bin/python3` is often 3.9, which is
  too old. Check with `python3 --version`. If that is below 3.11, install
  3.12 (for example `brew install python@3.12`) and use `python3.12` in the
  commands below.
- **Node.js 18+** and **Yarn** (the frontend lockfile is `yarn.lock`).
- **PostgreSQL 16+ with the pgvector extension.** Docker is the simplest way
  to get both. A local Postgres install also works; see below.
- About **500 MB** of disk for PyTorch and the embedding model. The model
  downloads from Hugging Face the first time you initialize the database.
- A network connection for that download and for crawling professor websites.

### 1. Start the database

**With Docker** (recommended):

```bash
docker compose up -d
```

This starts `pgvector/pgvector:pg16` on port 5432, database `grad_connect`,
user `professor`, password `professor`. Leave `.env` on the Docker connection
string from the next step.

If port 5432 is already taken, stop the other Postgres or change the host
port in `docker-compose.yml` and in `DATABASE_URL`.

**Without Docker** (Homebrew or another local Postgres 16+ that already has
pgvector):

```bash
createdb grad_connect
```

After you copy `.env` in the next step, set:

```text
DATABASE_URL=postgresql+psycopg://localhost/grad_connect
```

That connects as your operating-system user. The Docker user `professor`
exists only inside the Compose database. On local Postgres, leaving it in
`DATABASE_URL` makes the API fail with `role "professor" does not exist`.

### 2. Configure the environment

```bash
cp .env.example .env
```

The example file matches Docker. Change `DATABASE_URL` only if you are using
local Postgres, as shown above. The other defaults are fine for a first run.

### 3. Install the backend

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cd ..
```

Use `python3` instead of `python3.12` when `python3 --version` is already
3.11 or newer. On Windows, create the venv with `py -3.12 -m venv .venv` and
run later commands as `.venv\Scripts\python` and `.venv\Scripts\uvicorn`.

### 4. Create the tables

```bash
backend/.venv/bin/python scripts/init_db.py
```

This enables pgvector, creates the tables, pins the embedding column to the
model's dimension (384 for bge-small), and builds an HNSW cosine index. The
first run downloads `BAAI/bge-small-en-v1.5`.

### 5. Load professors and index their websites

`data/data.csv` is included. Load it, then crawl and embed the pages:

```bash
backend/.venv/bin/python scripts/ingest.py
backend/.venv/bin/python scripts/index.py
```

Ingest is fast. Indexing the full CSV crawls a few hundred sites and takes
on the order of 15–20 minutes. To try the app first, index a small slice:

```bash
backend/.venv/bin/python scripts/index.py --limit 10
```

The crawl is safe to stop and continue. Re-run with `--resume` to skip
professors that already have at least one indexed page. A dead or
JavaScript-only site is logged and skipped; it does not stop the run.
Re-running ingest or index does not duplicate professors or unchanged pages.

Search stays empty until this step finishes. `GET /health` can succeed
before any professors are indexed.

### 6. Run the API and the website

Terminal 1:

```bash
cd backend
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`http://127.0.0.1:8000/health` should return `{"status":"ok"}`.

Terminal 2:

```bash
cd frontend
yarn install
yarn dev
```

Open the URL Yarn prints, usually `http://localhost:3000`. If that port is
busy, Next.js picks the next one (3001, 3002, …). The API allows any
localhost port.

Search a topic such as `human computer interaction`, or open **Match my
resume** and paste resume text. Results only appear for professors whose
pages were indexed in step 5.

### Optional: search from the command line

```bash
backend/.venv/bin/python scripts/search.py "human computer interaction"
backend/.venv/bin/python scripts/search.py "machine learning theory" --university "Stanford University" --limit 5
```

To load a different spreadsheet:

```bash
backend/.venv/bin/python scripts/ingest.py --csv path/to/other.csv
```

The CSV needs `name`, `affiliation`, and `homepage`. Rows that share a
homepage with an earlier row are treated as aliases and skipped. Upserts use
`(name, affiliation)`, so re-running never duplicates professors.

### API

- `GET /api/search?query=...&university=...&country=...&page=1&limit=10` (also POST) — paginated semantic search
- `POST /api/match` — resume matching (file upload or pasted text)
- `GET /api/professors/{id}`
- `GET /api/filters`
- `GET /health`

## Tests

```bash
cd backend
.venv/bin/python -m pytest
```

Unit tests mock all HTTP calls and stub the embedding model — no network, no
model download. The vector-search integration tests run automatically when a
test database is reachable (default `postgresql+psycopg://localhost/grad_connect_test`,
override with `TEST_DATABASE_URL`) and are skipped otherwise.

## How semantic search works

1. Website text is split into overlapping ~600-token chunks that keep their
   section heading (e.g. "Research Interests") as context.
2. Each chunk is embedded locally with `BAAI/bge-small-en-v1.5` (384-dim,
   L2-normalized) and stored in pgvector.
3. A query is embedded with the model's query instruction prefix, and pgvector
   returns the nearest chunks by cosine distance, with university/country
   filters applied in the same SQL query.
4. Chunks below `MIN_SIMILARITY` are dropped, so an off-topic query returns
   nothing instead of its least-bad neighbours.
5. Chunks are aggregated per professor (best chunk = professor score, top
   chunks = evidence) and returned with their source URLs.

## Resume matching

`/match` (backend: `POST /api/match`) takes a resume — a `.pdf`, `.docx`,
`.txt` or `.md` file up to 5 MB, or pasted text — and returns the professors
whose crawled pages read closest to it, with side-by-side quotes.

- **Nothing is stored.** The file, its extracted text, and its embeddings are
  discarded when the request ends.
- **Same local model, same index.** Resume chunks are embedded as queries and
  searched against the existing professor chunks.
- The resume is chunked (bge-small truncates at 512 tokens) into up to 20
  chunks, each searched separately; a professor's score is the best
  (resume chunk, page chunk) pair, and the same `MIN_SIMILARITY` floor applies.
- Scanned (image-only) PDFs are rejected with a message to paste the text
  instead; there is no OCR.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `DATABASE_URL` | docker-compose DSN | SQLAlchemy/psycopg connection string |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | local Sentence Transformers model |
| `MAX_PAGES_PER_PROFESSOR` | `10` | crawl budget per professor (homepage included) |
| `CHUNK_SIZE` | `600` | approx. tokens per chunk |
| `CHUNK_OVERLAP` | `100` | approx. token overlap between chunks |
| `MIN_SIMILARITY` | `0.65` | minimum cosine similarity to count as a match; `0` disables |
| `PROFESSORS_CSV` | `data/data.csv` | ingestion source |
| `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | backend URL for the frontend |

## Repository layout

```text
backend/app/services/   crawler, extractor, chunker, embeddings, indexer,
                        search, resume matching
backend/app/api/        FastAPI routes
backend/app/models/     SQLAlchemy tables (professors, documents, document_chunks)
backend/tests/          unit + pgvector integration tests
scripts/                init_db, ingest, crawl, index, search CLIs
frontend/               Next.js + TypeScript UI (search, resume match, detail)
data/data.csv           professor source data
```
