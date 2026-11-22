# ULTRON OS 2026 — Backend Architecture

## Overview

ULTRON OS 2026 is a modular, multi-tenant, autonomous multi-agent intelligence operating system backend built on **Python 3.12 + FastAPI + SQLAlchemy 2.0 + Pydantic v2**, aligned with the November 2026 Master System Blueprint.

```
                         ┌──────────────────────────────┐
                         │  Clients (Desktop / PWA / API)│
                         └──────────────┬───────────────┘
                                        │ HTTPS
                         ┌──────────────▼───────────────┐
                         │  Cloudflare Worker Edge Proxy│  (cloudflare/worker.ts)
                         │  HSTS • Security Headers • KV│
                         └──────────────┬───────────────┘
                                        │
                         ┌──────────────▼───────────────┐
                         │  Vercel Serverless / Docker  │  (api/index.py -> app.main)
                         │     FastAPI Modular API      │
                         └──────────────┬───────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        │                               │                               │
┌───────▼────────┐             ┌────────▼────────┐             ┌────────▼────────┐
│  NEON Engine   │             │  ARGON Engine   │             │  ULTRON Services│
│  5-Tier Router │             │  JWT + Argon2id │             │  60 Agents      │
│  Gemini API    │             │  RBAC + Tenant  │             │  Memory/Vectors │
│  Embeddings    │             │  ApprovalGate   │             │  Tool Harness   │
└───────┬────────┘             │  AES-256 Vault  │             └────────┬────────┘
        │                      │  SHA-256 Audit  │                      │
        ▼                      └────────┬────────┘                      │
┌───────────────┐                       │                               │
│ Google Gemini │              ┌────────▼───────────────────────────────▼───────┐
│   REST API    │              │   Supabase PostgreSQL (+ pgvector + RLS)       │
└───────────────┘              │   or Local SQLite WAL (dev/test fallback)      │
                               └────────────────────────────────────────────────┘
```

## Core Architectural Pillars

### 1. NEON Cognitive Routing (`backend/app/services/neon_router.py`)
- Implements a **5-tier reasoning router** selecting specialist agents from the 60-agent catalog and mapping complexity/risk to Gemini models (`gemini-2.0-flash-lite`, `gemini-2.0-flash`, `gemini-2.5-pro`).
- Uses `x-goog-api-key` headers (never URL query parameters) for direct `generativelanguage.googleapis.com` REST calls.
- Reports `execution_mode` honestly: `gemini_live`, `local_deterministic_fallback` (when `GEMINI_API_KEY` is unconfigured), or `degraded_fallback_after_provider_error`.

### 2. ARGON Security, Governance & Orchestration (`backend/app/core/`, `backend/app/services/argon_orchestrator.py`, `backend/app/services/approval_service.py`)
- **Authentication:** Argon2id password hashing (`t=3, m=64 MiB, p=4`), HS256 JWT access tokens with unique `jti`, rotating opaque refresh tokens, immediate revocation on logout/rotation, and brute-force account lockout.
- **RBAC & Multi-Tenant Isolation:** 5 roles (`OWNER`, `ADMIN`, `OPERATOR`, `VIEWER`, `AGENT`) with granular permission checks (`require_perm(...)`) and strict `X-Tenant-ID` mismatch rejection.
- **ApprovalGate:** Automatically halts tasks or financial tools exceeding `ULTRON_APPROVAL_SOFT_LIMIT_USD` (default `$50.00`) or containing high-risk mutation keywords into `WAITING_FOR_APPROVAL`. Only `OWNER`/`ADMIN` principals can approve (`READY`) or reject (`CANCELLED`).
- **Task Lifecycle & DAG Engine:** 10 lifecycle states (`CREATED`, `PLANNED`, `WAITING_FOR_APPROVAL`, `READY`, `RUNNING`, `PAUSED`, `RETRYING`, `COMPLETED`, `FAILED`, `CANCELLED`), DFS cycle detection, and topological step execution.
- **Cryptographic Vault:** AES-256-GCM envelope encryption with HKDF-SHA256 derived keys, random 12-byte nonces, and Associated Authenticated Data (`ultron-vault::{tenant_id}::{name}`) preventing cross-tenant ciphertext swapping.
- **Immutable Audit Ledger:** Append-only `audit_logs` table with SHA-256 hash chaining (`prev_hash` → `entry_hash`) verifiable via `GET /api/v1/audit/verify`.

### 3. Honest Capability State Model (`backend/app/integrations/base.py`)
Every integration and agent follows the 5-stage capability lifecycle:
`REGISTERED` → `DEFINED_NOT_INSTALLED` → `INSTALLED` → `AVAILABLE` → `VERIFIED_TESTED`.

### 4. Multi-Tier Memory & Tool Harness
- **Memory (`backend/app/services/memory_service.py`):** Supports `WORKING`, `EPISODIC`, and `SEMANTIC` memories with hybrid cosine similarity + lexical recall (Gemini `text-embedding-004` when configured, deterministic 64-dim local hash embeddings offline) and TTL expiration pruning.
- **Tools (`backend/app/services/tool_service.py`):** Governed registry enforcing per-tool permissions, ApprovalGate thresholds, SSRF outbound URL filtering (blocking private, loopback, link-local, and cloud metadata endpoints), and execution history logging.
