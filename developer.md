# Topgun AI — Developer Guide

This file explains how developers should work on Topgun AI.

## Stack

Frontend:
- Next.js
- TypeScript
- Tailwind CSS
- App Router

Backend:
- FastAPI
- Python 3.11
- Pydantic
- pytest

Current architecture includes:
- ingestion pipeline
- vector store abstraction
- source federation
- intent classifier
- coverage detector
- browser push endpoint
- source-family grouped answers

## Local Setup

### Backend

```bash
cd /Users/topgunmaintenance/topgun-ai/backend
python3.11 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd /Users/topgunmaintenance/topgun-ai/frontend
npm install
npm run dev -- --port 3001
```

Health check:

```bash
curl http://localhost:8000/api/health
```

## Route Expectations

Expected primary routes:

- `/`
- `/dashboard`
- `/query`
- `/library`
- `/library/[id]`
- `/insights`
- `/admin`
- `/history`
- `/history/[id]`

All should return 200 except genuinely nonexistent dynamic document IDs, which should 404 via Next.js `notFound()`.

## Testing

Backend tests:

```bash
cd /Users/topgunmaintenance/topgun-ai/backend
source .venv/bin/activate
pytest -q
```

Frontend build:

```bash
cd /Users/topgunmaintenance/topgun-ai/frontend
npm run build
```

Developers should run both after meaningful changes.

## Source Federation Model

The system uses source families rather than one undifferentiated document pool.

Examples:
- FIM
- AMM
- IPC
- WDM
- SB
- HISTORY
- BROWSER

The query engine should preserve:
- source family
- raw retrieval score
- grouped evidence structure
- missing-source logic

Do not flatten all evidence into generic text retrieval.

## Query Behavior Rules

The query pipeline should:

1. classify intent
2. infer aircraft/system/ATA hints
3. retrieve from prioritized families
4. rank results
5. detect missing likely sources
6. format grouped evidence
7. refuse when evidence is insufficient

For troubleshooting queries, do not break the FIM-first ranking logic.

## Missing-Source Rules

When likely source families are absent:
- show them clearly
- explain why they matter
- do not invent missing manual contents

This is a core trust feature.

## Browser Push Rules

Browser-derived manual content must:
- enter the standard ingestion pipeline
- carry metadata like vendor, URL, aircraft, timestamp
- be searchable as BROWSER
- participate in coverage detection
- appear in grouped result UI

Do not special-case browser text as second-class data.

## Honesty Rules

The system must refuse nonsense and unrelated questions.

The overlap gate exists for a reason:
- to prevent false positives from weak stub embeddings
- to preserve honest refusal behavior

Do not weaken this protection without replacing it with a better validated mechanism.

## Current Known Limitations

- in-memory vector store is not persistent
- stub embeddings are not production-grade
- OCR depends on host Tesseract
- browser push exists, but a full browser extension is not yet built
- auth and tenancy are not yet implemented

Developers should not hide these limitations.
They should document them clearly.

## Preferred Phase 4 Direction

Recommended sequence:

1. discrepancy / job logging
2. persistent storage
3. richer browser connectors
4. auth / tenancy
5. production embeddings
6. source viewer deep-linking

## Git Hygiene

Preferred workflow:
- create branch or worktree
- make focused changes
- run tests/build
- validate localhost behavior when applicable
- commit verified work
- merge cleanly

Avoid large mixed commits unless explicitly requested.

## Debugging Rules

When frontend issues appear:
- trust server/dev logs over browser overlay alone
- verify actual route status with curl when helpful
- distinguish real 404s from expected `notFound()` behavior
- kill stale dev servers before chasing fake bugs

Useful commands:

```bash
lsof -i :3000
lsof -i :3001
lsof -i :8000
kill -9 <PID>
```

## Definition of Done

A change is not done until:
- code is written
- tests/build pass
- localhost behavior is verified if relevant
- docs are updated if startup/workflow changed
- the exact branch and commit are known
