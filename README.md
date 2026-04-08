# Topgun AI

**AI Maintenance Intelligence for Aviation Teams**

Topgun AI turns aircraft manuals, maintenance records, parts catalogs, service
bulletins, work cards, and scanned paperwork into a single, source-cited
intelligence layer. Mechanics, planners, and operators ask a question and get
a structured answer grounded in the documents they uploaded — with citations,
extracted entities, and a visible confidence signal.

> Search manuals, records, and parts context instantly.
> Every answer backed by source evidence.
> From documents to decisions.

This repository contains a standalone MVP: a Next.js (App Router, TypeScript,
Tailwind) frontend and a Python FastAPI backend, wired together with a
modular ingestion + retrieval + query architecture designed for future
Postgres/pgvector and multi-provider AI deployments.

> Topgun AI is a separate product. It does not share code, naming, or
> architecture with anything else in this repository.

---

## Architecture at a glance

```
topgun-ai/
├── frontend/         Next.js 14 App Router, TypeScript, Tailwind
├── backend/          FastAPI, modular services, ingestion + query layers
├── docs/             Architecture, ingestion, query, roadmap
├── sample_data/      Realistic aviation demo data (documents, queries, insights)
├── scripts/          Dev helpers and demo seeding
└── .env.example      Shared environment template
```

Full architecture write-up lives in [`docs/architecture.md`](docs/architecture.md).
Pipeline and query layer details are in
[`docs/ingestion-pipeline.md`](docs/ingestion-pipeline.md) and
[`docs/query-system.md`](docs/query-system.md). The product roadmap is in
[`docs/product-roadmap.md`](docs/product-roadmap.md).

---

## What this MVP gives you

### Phase 1 — Product shell (complete)
- A world-class landing page that communicates the product in under five seconds.
- A full dashboard shell with sidebar, top command bar, upload card, recent
  queries, recent documents, and system status cards.
- A premium **Query Workspace** with answer panel, citations, extracted
  entities, related documents, confidence badge, and follow-up prompts.
- A **Document Library** with type badges, aircraft tags, source tags, and
  ingestion status — plus a **Document Detail** page that shows the
  ingestion report and indexed chunk previews for any uploaded document.
- A **Maintenance Insights** page with recurring issue clusters, ATA trends,
  and fleet intelligence widgets (seeded with realistic demo data).
- An **Admin / System Health** page showing ingestion queue, OCR, embeddings,
  vector index, API health, and recent processing logs.
- A FastAPI backend with routes for health, documents, query, insights, and
  system status, backed by a modular ingestion and query layer.

### Phase 2 — Real ingestion + retrieval (complete)
- **Real PDF parsing** via PyMuPDF (`fitz`), with a `pdfplumber` fallback
  if PyMuPDF isn't available. Both backends emit per-page text and report
  which pages came back as low-text.
- **OCR fallback** via `pytesseract` over PyMuPDF-rasterized pages — only
  pages flagged low-text are re-OCRed, and the stage degrades cleanly with
  an explicit `ocr_skipped_reason` if Tesseract or its Python wrapper is
  not installed.
- **Chunk provenance**: every chunk carries page span, char span, content
  hash, token estimate, parser source, and an `ocr` flag, so citations
  can deep-link to exactly the slice of source text the answer came from.
- **Field extraction** for tail numbers, ATA chapters, part numbers, and
  ISO dates from parsed text.
- **Uploaded-document retrieval**: the in-memory vector store indexes
  uploaded chunks alongside seeded demo content, and the four-lane query
  engine searches both. The original cosine-similarity score is preserved
  through reciprocal-rank fusion, so the answer formatter can honestly
  decide whether evidence is strong, weak, or insufficient.
- **Stronger evidence packaging**: citations now include `source`, `ocr`,
  `weak`, and char-span fields. The answer formatter refuses to answer
  when the top retrieval score is below the insufficient floor and
  downgrades the confidence label to `low` when the top score is weak.
- **Demo-mode fast path** is now overlap-gated: a seeded answer is only
  returned when at least three of the question's content tokens overlap
  the seeded query. Off-topic questions correctly fall through to the
  retrieval lanes and report `insufficient`.
- **Document detail endpoint** returns an `IngestionReport` (parser
  backend, page count, chunk count, OCR pages, extracted fields, error)
  plus up to six chunk previews from the vector store.

---

## Prerequisites

- **Node.js 18.17+** (tested on Node 20 LTS)
- **Python 3.11+** — required by `pydantic-settings` 2.x. Python 3.9 will
  fail to install dependencies. On macOS: `brew install python@3.11`.
- pip / venv

Optional, for the OCR fallback path (Phase 2 graceful skip if missing):
- **Tesseract OCR engine**: `brew install tesseract` (macOS),
  `apt-get install tesseract-ocr` (Debian/Ubuntu). If Tesseract isn't
  installed the parser still runs and the document detail page reports
  `OCR skipped — missing pytesseract` (or similar) for affected pages.
- Postgres 15+ with `pgvector` extension — for Phase 3 only.

---

## Local setup

Clone and enter the project:

```bash
cd topgun-ai
cp .env.example .env
```

### Backend

```bash
cd backend
python3.11 -m venv .venv          # Python 3.11+ is required
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`. Interactive docs live at
`http://localhost:8000/docs`. Health check: `http://localhost:8000/api/health`.

`requirements.txt` pulls in PyMuPDF, pdfplumber, pytesseract, and Pillow so
real PDFs work out of the box. The OCR stage additionally needs the
Tesseract binary to be installed on the host (see Prerequisites). Without
it, the pipeline still runs and the document detail page reports the
skipped reason — it just won't recover text from scanned pages.

### Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

The app runs at `http://localhost:3000`. By default it talks to the backend at
`http://localhost:8000`. Change `NEXT_PUBLIC_API_BASE_URL` in
`frontend/.env.local` to point elsewhere.

### Tests

```bash
cd backend
.venv/bin/pytest -q
```

23 tests cover health, documents, query, ingestion, real PDF parsing,
chunk metadata, vector store list/count/delete, document detail, the
upload endpoint, and the answer formatter's weak/insufficient handling.

### First-run validation

After both servers are up:

1. Open `http://localhost:3000` and load the **Dashboard**.
2. Drop a real PDF into the upload card. The status panel should switch
   to "Indexed" within a second or two and show the page count.
3. Open **Library** and click the new document. The detail page shows
   the parser backend, chunk count, OCR status, extracted tail
   numbers / ATA chapters / part numbers, and chunk previews.
4. Open **Query** and ask a question whose answer is in your uploaded
   document. You should see citations that point at it, with a
   confidence label of `high`, `medium`, or `low` (and a `weak` flag on
   any citation whose retrieval score was below the floor).
5. Ask an off-topic question and confirm Topgun AI returns
   `insufficient` rather than fabricating an answer.

---

## Environment variables

See [`.env.example`](.env.example) for the full list. The defaults let you run
the MVP end-to-end with no external services — the backend uses an in-memory
demo store seeded from `sample_data/`.

Keys you'll eventually want to set:

| Variable                     | Purpose                                     |
| ---------------------------- | ------------------------------------------- |
| `DATABASE_URL`               | Postgres connection string (future)         |
| `VECTOR_BACKEND`             | `memory` (default) or `pgvector`            |
| `AI_PROVIDER`                | `stub` (default), `openai`, or `anthropic`  |
| `OPENAI_API_KEY`             | Embeddings + optional generation            |
| `ANTHROPIC_API_KEY`          | Structured extraction and answer synthesis  |
| `NEXT_PUBLIC_API_BASE_URL`   | Backend base URL the frontend talks to      |

---

## Roadmap

Short version:

1. **Phase 1 — MVP scaffold** (✅ complete): end-to-end product shell,
   demo data, stub AI provider, modular pipeline scaffolding.
2. **Phase 2 — Real ingestion + retrieval** (✅ complete): PyMuPDF +
   pdfplumber parsing, pytesseract OCR fallback, chunk provenance,
   in-memory vector store, weak-evidence-aware answer formatter,
   document detail endpoint, frontend upload + detail page wired
   end-to-end.
3. **Phase 3 — Production retrieval** (next): Postgres + pgvector
   backend with the same `VectorStore` interface, real OpenAI
   embeddings, server-side ingestion workers, source-drawer deep links,
   auth + audit history, document viewer.
4. **Grounded synthesis with Anthropic** — structured answers with
   citations and per-citation justification.
5. **Fleet intelligence** — recurring fault clustering and parts
   stocking signals.
6. **Scan ingestion** — camera capture of part tags and labels on mobile.

### Known Phase-2 limitations

- The vector store is **in-memory and per-process**. Restarting the
  backend wipes everything you've uploaded. Phase 3 swaps in pgvector
  via the same interface.
- The default AI provider is the deterministic `StubProvider`, whose
  hashed-bucket "embeddings" are good enough to demonstrate retrieval
  but are not semantically meaningful. Set `AI_PROVIDER=openai` and
  `OPENAI_API_KEY=...` once Phase 3's real provider is wired.
- OCR requires the Tesseract binary on the host. Without it, scanned or
  image-only PDFs are reported as `OCR skipped — missing pytesseract`
  on the document detail page.

Full roadmap: [`docs/product-roadmap.md`](docs/product-roadmap.md).

---

## License

Proprietary. All rights reserved. Topgun AI is a commercial product.
