# Topgun AI — Claude Operating Standard

This file defines how Claude Code should work inside the Topgun AI repository.

## Project Identity

Topgun AI is an aviation maintenance intelligence platform.

Its purpose is to help mechanics, DOMs, inspectors, and maintenance teams search across connected maintenance sources and return grounded, source-cited troubleshooting guidance.

This is not a generic chatbot.
This is not a content-generation toy.
This is a source-first maintenance intelligence system.

## Repository Scope

Claude must only work inside this repository:

`/Users/topgunmaintenance/topgun-ai`

GitHub remote:

`https://github.com/topgunmaintenance/topgun-ai.git`

Claude must never:
- reference Dum-Club as a dependency or source of truth
- import code from unrelated repos without explicit instruction
- create fake work in unrelated directories
- claim work is complete without verifying it

## Core Product Principles

Topgun AI must:

- prefer source-grounded answers over fluent guesses
- explicitly identify uncertainty
- rank source families appropriately for the task
- detect missing likely sources
- support multi-source troubleshooting
- preserve metadata and provenance
- avoid hallucinating maintenance procedures, torque values, pinouts, or part numbers

## Source Priority Rules

For troubleshooting queries, prioritize sources in this order unless strong evidence suggests otherwise:

1. FIM
2. WDM / wiring
3. AMM
4. IPC
5. SB
6. Internal history
7. Browser-derived/vendor-connected sources

For parts questions:
1. IPC
2. AMM
3. vendor/component manuals
4. history

For wiring/electrical questions:
1. WDM
2. FIM
3. AMM
4. browser/vendor avionics sources

## Answer Quality Rules

Claude must never present unsupported maintenance guidance as fact.

If evidence is weak:
- lower confidence
- explain what is supported
- explain what is missing

If likely sources are missing:
- explicitly list them under "Missing likely sources"
- explain why they matter
- do not invent what those missing manuals would say

If evidence is insufficient:
- refuse cleanly
- provide zero misleading citations

## Development Workflow

Claude should follow this workflow for all meaningful work:

1. Inspect repo state first
2. Summarize current behavior briefly
3. Make surgical changes
4. Run tests/build
5. Run localhost validation if the change affects behavior
6. Report exact files changed and exact results
7. Commit only verified work

Claude should prefer small, clean, reviewable commits.

## Local Run Expectations

Backend:
- Python 3.11
- FastAPI
- local port 8000

Frontend:
- Next.js
- local port 3001 preferred when 3000 is occupied

Claude may use:
- curl against localhost
- local temp files in `/tmp`
- browser preview
- test clients
- dev logs
- HTML inspection of localhost pages

These are valid verification tools and should be used as needed.

## Git Rules

Claude should not commit directly to `main` unless explicitly asked.
Preferred workflow:
- create a branch or worktree
- complete and verify work
- provide merge steps

Claude must always report:
- branch name
- exact commit hash
- whether work is merged or not

## Current Product Milestone

Topgun AI currently supports:

- local document ingestion
- real PDF parsing
- OCR fallback behavior
- chunk metadata and provenance
- multi-source federation
- browser push ingestion
- missing-source detection
- grouped result display by source family
- honest refusal behavior
- localhost preview validation

Future work should build on that foundation instead of rewriting it.

## What Claude Should Optimize For

Claude should optimize for:

- correctness
- traceability
- maintainability
- local usability
- practical mechanic workflows

Claude should not optimize for:
- flashy but shallow UI changes
- speculative abstractions with no validation
- broad rewrites that disrupt working flows

## Preferred Next Directions

When asked what to build next, prefer these in order unless instructed otherwise:

1. job / discrepancy logging
2. persistent storage
3. browser source registry and richer portal connectors
4. auth / tenancy
5. production embeddings
6. source drawer / document viewer deep-linking
