# ULTRON OS 2026

**ULTRON OS 2026** is a modular, production-oriented autonomous multi-agent intelligence operating system backend unifying **NEON** (5-tier cognitive routing & Gemini API execution), **ARGON** (cryptographic security, RBAC, multi-tenant isolation, AES-256-GCM vault, SHA-256 hash-chained audit ledger, DAG task orchestration, and **ApprovalGate** governance), and **60 specialist agents** (`AGT-01`–`AGT-60`).

> GitHub is the single source of truth for all application source code.

## Core Capabilities

- **Authentication & RBAC:** Argon2id password hashing (`t=3, m=64 MiB, p=4`), HS256 JWT bearer authentication with JTI session revocation, rotating refresh tokens, brute-force account lockout, 5 roles (`OWNER`, `ADMIN`, `OPERATOR`, `VIEWER`, `AGENT`), and strict tenant isolation.
- **Database Access:** SQLAlchemy 2.0 ORM supporting **Supabase PostgreSQL** (`backend/migrations/supabase/001_initial_schema.sql` with `pgvector` + Row-Level Security) and local **SQLite WAL** fallback for zero-friction development and automated tests.
- **60 Specialist Agents & NEON Router:** Complete 25 Core + 35 Extensible agent taxonomy with 5-tier complexity/risk routing and direct **Google Gemini API** execution (with honest offline fallback reporting when `GEMINI_API_KEY` is not set).
- **ARGON Task Orchestration & ApprovalGate:** 10-state task lifecycle machine, DAG circular dependency detection, topological execution, and mandatory human-in-the-loop ApprovalGate enforcement for actions exceeding `$50.00 USD` or triggering high-risk mutations.
- **Multi-Tier Memory:** `WORKING`, `EPISODIC`, and `SEMANTIC` memory storage with hybrid cosine-similarity + lexical recall (Gemini `text-embedding-004` or deterministic local embeddings) and TTL pruning.
- **Governed Tool Harness:** Permission-checked tool catalog with SSRF outbound URL protection, ApprovalGate integration, and full execution history.
- **ARGON Cryptographic Vault & Audit Ledger:** Tenant-scoped AES-256-GCM secret vault (with HKDF key derivation and AAD tenant binding) plus an immutable SHA-256 hash-chained audit log with tamper detection (`/api/v1/audit/verify`).
- **Cloud Platform Ready:** First-class integrations and honest live verifiers for **Supabase**, **Gemini API**, **Vercel** (`vercel.json` + `api/index.py`), and **Cloudflare** (`cloudflare/worker.ts` + `cloudflare/wrangler.toml`).

## Repository Structure

```
.
├── api/index.py                          # Vercel Python serverless ASGI entrypoint
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app factory & middleware
│   │   ├── core/                         # Config, security, RBAC, logging, exceptions
│   │   ├── db/                           # ORM models, dual-mode sessions, hash-chained audit
│   │   ├── integrations/                 # Supabase, Gemini, Vercel, Cloudflare clients & verifiers
│   │   ├── services/                     # Auth, 60-agent catalog, NEON, ARGON, ApprovalGate, memory, tools, vault
│   │   ├── schemas/                      # Pydantic v2 API contracts
│   │   └── routers/                      # Modular REST API routers
│   ├── migrations/supabase/              # Production Supabase Postgres + pgvector + RLS migration
│   ├── scripts/verify_integrations.py    # Honest live integration verifier CLI
│   └── tests/                            # Automated pytest suite
├── cloudflare/                           # Cloudflare Worker edge gateway & Wrangler config
├── docs/                                 # Architecture, API reference, env vars, deployment, plan
├── .env.example                          # Safe environment variable template
├── Dockerfile                            # Non-root production container build
├── pyproject.toml                        # Packaging & pytest configuration
├── requirements.txt                      # Python runtime dependencies
└── vercel.json                           # Vercel serverless deployment manifest
```

## Quick Start

```bash
pip install -r requirements.txt
cp .env.example .env

# Run the automated test suite
pytest

# Check configured integrations honestly
python3 backend/scripts/verify_integrations.py

# Start local API server (Swagger UI at http://127.0.0.1:8000/docs)
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
```

## Documentation

- [Implementation Plan & State Inspection](docs/IMPLEMENTATION_PLAN.md)
- [System Architecture](docs/ARCHITECTURE.md)
- [REST API Reference](docs/API_REFERENCE.md)
- [Environment Variables & Secret Management](docs/ENVIRONMENT_VARIABLES.md)
- [Deployment Guide (Supabase, Gemini, Vercel, Cloudflare, Docker)](docs/DEPLOYMENT.md)