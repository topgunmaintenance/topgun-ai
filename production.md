# Topgun AI — Production Guidance

This document defines the practical production direction for Topgun AI.

## Product Positioning

Topgun AI is a multi-source aviation maintenance intelligence engine.

It helps maintenance teams answer questions like:

- "TOGA lever button not working on a Phenom 300"
- "What is the likely next troubleshooting step?"
- "Which manuals are relevant?"
- "What source is missing?"
- "Have we seen this issue before?"

The system should function as a shop intelligence layer, not just a document viewer.

## Production Goals

A production-ready Topgun AI should:

- support real maintenance workflows
- retain indexed knowledge across restarts
- search across connected source families
- explain gaps in source coverage
- support browser-connected manual portals
- support internal discrepancy history
- provide trusted, citation-backed answers

## Production Source Families

Topgun AI should support these source families as first-class entities:

- FIM
- AMM
- IPC
- WDM
- SB
- internal work orders / discrepancies / history
- browser-derived portal content
- vendor or OEM supplements
- engine manuals
- avionics manuals

Each source must carry:
- family
- document title
- aircraft model
- ATA if known
- vendor/OEM
- document code
- revision
- timestamp or capture date
- source URL or source reference when applicable

## Production Safety Rules

Topgun AI must never:
- fabricate maintenance procedures
- invent part numbers
- invent torque values
- imply a missing source was reviewed when it was not
- collapse weak evidence into high-confidence output

If confidence is weak:
- say so
- show the evidence
- show missing sources
- prefer caution over confidence

## Production Data Strategy

### Short term
- local/manual uploads
- browser push ingestion
- seeded history
- in-memory or lightweight storage

### Medium term
- Postgres + pgvector
- persistent document and chunk storage
- persistent browser captures
- persistent discrepancy history
- source-family filtering and weighting in the database

### Long term
- multi-tenant storage
- org-level permissions
- audit logs
- saved investigations
- versioned document revisions
- enterprise browser connectors

## Production Workflow Vision

A mechanic or technician should be able to:

1. enter a discrepancy
2. ask a troubleshooting question
3. see prioritized sources
4. see missing likely sources
5. push a browser portal page when needed
6. refine the answer
7. log corrective action
8. leave that history behind for the next occurrence

This means Topgun AI should become:
- a search layer
- a reasoning layer
- a history layer
- a workflow layer

## Production Priorities

### Priority 1 — History and workflow
Add discrepancy and job logging.
This creates the first daily-use loop.

### Priority 2 — Persistence
Persist documents, chunks, browser pushes, and history.

### Priority 3 — Browser connectors
Make connected manual portals easier to search and push into the system.

### Priority 4 — Stronger retrieval quality
Add real embeddings and stronger ranking.

### Priority 5 — Source viewer
Allow evidence deep-linking into pages/sections.

## Production User Types

Primary:
- A&P mechanics
- DOMs
- inspectors
- maintenance controllers
- repair station teams

Secondary:
- flight departments
- fleet managers
- training teams

## Production UX Rules

The UI should feel:
- trustworthy
- direct
- source-oriented
- professional
- operational

It should not feel:
- gimmicky
- chat-first
- consumer-social
- vague

Grouped evidence is preferred over one blended paragraph.

The ideal answer layout includes:
- likely troubleshooting path
- grouped evidence by source family
- missing likely sources
- confidence and citation quality
- similar prior fixes if available

## Production Infrastructure Direction

Expected production stack direction:

- frontend: Next.js
- backend: FastAPI
- database: Postgres
- vector layer: pgvector
- file storage: object storage
- auth: org-aware authentication
- ingestion: background workers
- embeddings: production provider
- browser connectors: extension/helper

## Definition of Production Readiness

Topgun AI is production-ready when it can:

- persist knowledge
- survive restarts without losing indexed data
- isolate organization data safely
- support real discrepancy logging
- support source-family search at scale
- provide reliable citations and confidence controls
- be trusted by mechanics to say "I don't know" when appropriate
