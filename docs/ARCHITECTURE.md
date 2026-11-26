# ULTRON OS 2026 — Complete Backend Architecture

## Unified System Topology

ULTRON OS 2026 operates as one cohesive, modular, multi-tenant Python 3.12 / FastAPI backend split cleanly for serverless HTTP scalability (**Vercel**) plus optional long-running background orchestration (**Dedicated Persistent Worker**), backed by **Supabase PostgreSQL + pgvector + Storage** and fronted by **Cloudflare Workers**.

```
                         ┌─────────────────────────────────────┐
                         │  Clients (Desktop / Mobile PWA / API)│
                         └──────────────────┬──────────────────┘
                                            │ HTTPS / WSS
                         ┌──────────────────▼──────────────────┐
                         │  Cloudflare Worker Edge Gateway     │  cloudflare/worker.ts
                         │  HSTS • Security Headers • KV RL    │
                         └──────────────────┬──────────────────┘
                                            │
                  ┌─────────────────────────┴─────────────────────────┐
                  │                                                   │
   ┌──────────────▼──────────────┐                     ┌──────────────▼──────────────┐
   │  Vercel Serverless API      │                     │  Persistent Worker Container│
   │  api/index.py -> app.main   │                     │  backend/worker.py          │
   │  • 17 Modular REST Routers  │                     │  • Long-running ARGON DAGs  │
   │  • Rate Limiter + Idemp.    │                     │  • Recurring Cron Schedules │
   │  • SSE Streaming (/neon)    │                     │  • Retry & Recovery Loop    │
   └──────────────┬──────────────┘                     └──────────────┬──────────────┘
                  │                                                   │
                  └─────────────────────────┬─────────────────────────┘
                                            │
        ┌───────────────────────────────────┼───────────────────────────────────┐
        │                                   │                                   │
┌───────▼───────────┐             ┌─────────▼──────────┐             ┌──────────▼──────────┐
│ NEON Intelligence │             │ ARGON Governance   │             │ Domain Subsystems   │
│ • Multi-Provider  │             │ • Argon2id + JWT   │             │ • 60 Agents + Bus   │
│ • 5 Tiers + Cost  │             │ • 5-Role RBAC      │             │ • 6-Tier Memory v2  │
│ • Failover/Retry  │             │ • ApprovalGate     │             │ • Financial Center  │
│ • SSE + Tool Call │             │ • AES-256-GCM Vault│             │ • Dev & Projects    │
│ • Conversations   │             │ • SHA-256 Audit    │             │ • 14 Capabilities   │
└───────┬───────────┘             │ • Owner Kill-Switch│             │ • Monitoring & WS   │
        ▼                         └─────────┬──────────┘             └──────────┬──────────┘
┌───────────────────┐                       │                                   │
│ Gemini API (+ opt │              ┌────────▼───────────────────────────────────▼──────────┐
│ OpenAI/Anthropic/ │              │   Supabase PostgreSQL + pgvector + RLS + Storage      │
│ Ollama failover)  │              │   (or local SQLite WAL for dev & automated tests)     │
└───────────────────┘              └───────────────────────────────────────────────────────┘
```

## Serverless vs Persistent Worker Boundary (Vercel Compatibility)

Vercel Python Functions (`api/index.py` + `vercel.json`) are designed for stateless HTTP API requests and short-lived SSE streams within Vercel's serverless execution timeout window. They **do not** support unbounded background threads, persistent cron daemons, or long-lived WebSocket hubs.

Accordingly, ULTRON OS 2026 cleanly separates:
1. **Stateless HTTP API (`api/index.py`):** Runs on Vercel Serverless OR Docker (`Dockerfile`). Handles auth, RBAC, CRUD, fast NEON calls, ApprovalGate decisions, and enqueuing long-running tasks (`POST /api/v1/tasks/{id}/enqueue`).
2. **Persistent Worker (`backend/worker.py` + `Dockerfile.worker`):** Deployed as a dedicated container (Fly.io, Railway, Render, Cloud Run, or Docker Compose) sharing the exact same `ULTRON_DATABASE_URL` (Supabase PostgreSQL). Executes queued ARGON DAGs, retries, and recurring `scheduled_jobs` without serverless timeout risk.
3. **WebSocket Hub (`/ws/v1/events`):** Available whenever the FastAPI server runs as a persistent ASGI container (`Dockerfile` / `uvicorn`), streaming live task progress, approval triggers, and notifications scoped by tenant.

## Honest Capability State Model

Every provider and capability reports one of:
`AVAILABLE` | `DEFINED_NOT_INSTALLED` | `UNAVAILABLE` | `DEGRADED` | `REQUIRES_APPROVAL` | `INSTALLED` | `VERIFIED_TESTED`.

External services (Supabase, Gemini, Vercel, Cloudflare, GitHub, Google Drive, Email, WhatsApp, Calendar) **never** report `AVAILABLE` without a verified live probe.
