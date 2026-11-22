# ULTRON OS 2026

**ULTRON OS 2026** is a unified, modular, production-oriented autonomous multi-agent intelligence operating system backend combining:

* **NEON Intelligence Engine:** Multi-model provider abstraction (Google Gemini primary + optional OpenAI/Anthropic/Ollama failover), 5 reasoning tiers, structured JSON outputs, governed tool calling, SSE streaming (`/api/v1/neon/stream`), multi-turn conversations, and token/cost usage tracking.
* **ARGON Autonomous Orchestration & Governance:** 10-state task lifecycle, DFS cycle detection, parallel DAG wave execution, pause/resume/retry failure recovery, independent result verification before completion, background job queue & recurring scheduler (`backend/worker.py`), `ApprovalGate` enforcement (`> $50` financial outflows, owner distributions, external comms, production deployments, dynamic agent extensions), and an `OWNER`-only emergency kill switch.
* **60 Specialist Agents (`AGT-01`–`AGT-60`):** Complete 25 Core + 35 Extensible catalog with agent manifests, honest execution backing status, performance metrics, tenant-isolated inter-agent message bus, and ApprovalGate-governed dynamic extension registration.
* **6-Tier Versioned Memory:** `SHORT_TERM`, `LONG_TERM`, `EPISODIC`, `SEMANTIC`, `PROJECT`, and `USER_PREFERENCE` memory with revision history, `PRIVATE` vs `TENANT` access controls, retention TTL pruning, and hybrid vector cosine + lexical search (`pgvector`-ready on Supabase PostgreSQL).
* **Financial Command Center:** Revenue, expenses, API spending, hosting costs, project costs, budgets with automatic overrun alerts, investments, reserves, owner distributions (strictly gated; never executes unverified live payment rails), financial summary reports, and immutable financial audit logs.
* **Developer & Coding Infrastructure:** Project management, local git & GitHub inspection, real Python AST static analysis & security scanning, non-destructive code generation proposals, ApprovalGate-governed production deployments, rollback support, and dev activity tracking.
* **Security & Observability:** Argon2id (`t=3, m=64 MiB, p=4`), HS256 JWT + JTI revocation, rotating refresh tokens, brute-force lockout, 5-role RBAC, strict tenant isolation, AES-256-GCM vault with HKDF + AAD binding, SHA-256 hash-chained audit ledger, sliding-window rate limiting, `Idempotency-Key` replay safety, SSRF & prompt-injection defenses, authenticated WebSocket events (`/ws/v1/events`), and Prometheus metrics (`/api/v1/monitoring/metrics`).
* **Unified Integration Manager & OAuth 2.0 (PKCE):** Central encrypted per-tenant credential management, least-privilege OAuth scopes, token refresh, live verification, and upstream revocation across **Google Ecosystem** (Drive, Gmail, Calendar, Docs, Sheets, Slides, Search, Google Cloud), **GitHub Engineering**, **Supabase**, **Vercel**, **Cloudflare**, and the honest **Antigravity Plugin Adapter**.
* **Multi-Device Connectivity Mesh & Desktop Agent:** Secure pairing (`windows`, `macos`, `ios`, `ipados`, `android`, `pwa`), explicit opt-in permissions, cross-device task sync, instant revocation, and sandboxed desktop agent (`device_agent/ultron_desktop_agent.py`).
* **Unified Natural-Language Orchestration (`POST /api/v1/orchestrate`):** Plain-language objectives automatically combine memory recall, authorized integration/device discovery, NEON routing (official Nov 2026 Gemini models `gemini-3.5-flash-lite` / `gemini-3.8-flash` / `gemini-4-argon`), ARGON DAG execution, ApprovalGate checkpoints, and independent verification.

## Quick Start

```bash
pip install -r requirements.txt pytest
cp .env.example .env

pytest
python3 backend/scripts/verify_migrations.py
python3 backend/scripts/verify_integrations.py

PYTHONPATH=backend uvicorn app.main:app --reload --port 8000
```

## Documentation

* [Existing State & Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
* [System Architecture & Serverless/Worker Split](docs/ARCHITECTURE.md)
* [Ecosystem Connectivity, OAuth 2.0 & Multi-Device Mesh](docs/ECOSYSTEM_AND_DEVICES.md)
* [Complete REST & WebSocket API Reference](docs/API_REFERENCE.md)
* [Environment Variables & Secret Management](docs/ENVIRONMENT_VARIABLES.md)
* [Deployment, Migration, Backup & Rollback Guide](docs/DEPLOYMENT.md)