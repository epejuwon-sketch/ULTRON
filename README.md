# ULTRON OS 2026

**ULTRON OS 2026** is a unified, full-stack, mobile-first (iPhone PWA + future Windows desktop) autonomous multi-agent AI operating system combining a production-oriented FastAPI backend (`backend/`) with a responsive dark-slate React + TypeScript + Vite PWA frontend (`frontend/`).

## Core Platform Subsystems

* **NEON Intelligence Engine:** Multi-model provider abstraction (Google Gemini primary using official Nov 2026 models `gemini-3.5-flash-lite`, `gemini-3.8-flash`, `gemini-4-argon`, `gemini-embedding-001`, `gemini-nano-banana-2.1` + optional OpenAI/Anthropic/Ollama failover), 5 reasoning tiers, structured JSON outputs, governed tool calling, SSE streaming (`/api/v1/neon/stream`), multi-turn conversations, and token/cost usage tracking.
* **ARGON Autonomous Orchestration & Governance:** 10-state task lifecycle, DFS cycle detection, parallel DAG wave execution, pause/resume/retry failure recovery, independent result verification before completion, background job queue & recurring scheduler (`backend/worker.py`), `ApprovalGate` enforcement, natural-language orchestration (`POST /api/v1/orchestrate`), and an `OWNER`-only emergency kill switch.
* **60 Specialist Agents (`AGT-01`–`AGT-60`):** Complete 25 Core + 35 Extensible catalog with individualized input/output schemas, workflow stages, quality benchmarks, honest execution backing status, performance metrics, tenant-isolated inter-agent message bus, and ApprovalGate-governed dynamic extension registration.
* **AEGIS Autonomous Security & Defence (`/api/v1/aegis`):** On-demand & continuous 60-second worker scans, audit hash-chain verification, config posture checks, auth anomaly detection, file integrity monitoring (FIM), SSRF/URL safety inspection, static code bundle scanner, risk scoring (`0–100`), incident tracking, and ApprovalGate-gated high-impact remediation.
* **EVOLVE Controlled Self-Development (`/api/v1/evolve`):** Strict lifecycle (`IDENTIFIED` → `PLANNED` → `DEVELOPED` → `TESTED` → `AEGIS_VERIFIED` → `WAITING_FOR_APPROVAL` → `PROMOTED` / `ROLLED_BACK`) requiring isolated syntax validation, AEGIS verification, and explicit OWNER/ADMIN approval before promotion.
* **SENTINEL Passkeys / WebAuthn & Recovery (`/api/v1/sentinel`):** Platform authenticator Passkey support (iPhone Face ID / Touch ID / Windows Hello) with **zero raw biometric storage**, sensitive-action reauthentication tokens, and single-use SHA-256 hashed recovery codes.
* **VAULT Earliest-Boundary Secret Interception (`backend/app/core/secret_interceptor.py`):** Automatically intercepts API keys, tokens, private keys, and inline passwords in chat, memory, and uploaded files **before** AI routing or storage, encrypts them into tenant VAULT (AES-256-GCM), and replaces them with `{{VAULT_REF:...}}`. Raw payment card numbers (Luhn PANs) and CVVs are immediately scrubbed and never stored anywhere.
* **ORBIT Multi-Device & Location Mesh (`/api/v1/devices`):** Cryptographic device pairing (`ios`, `windows`, `macos`, `ipados`, `android`, `pwa`), explicit opt-in permissions, authorized device location reporting, geofence alerts, instant pause/resume/revoke location controls, and sandboxed desktop agent (`device_agent/ultron_desktop_agent.py`).
* **ATLAS Personal Assistant, Orders & World Intelligence (`/api/v1/atlas`):** Web-backed product research, ApprovalGate-protected orders, 9-status verified order tracking (`PLACED` through `DELIVERED`/`CANCELLED`, never fabricated), live Open-Meteo weather with honest offline states, configurable intelligence topics, and Daily Briefings.
* **Financial Command Center (`/api/v1/finance`):** Personal vs Business separation (`scope`), tokenized payment methods (`VISA`, `MASTERCARD`, `VERVE`, `AMEX` — masked `last4` only, strict raw PAN/CVV rejection), revenue/expenses/budgets/investments/reserves, cash-flow forecasting, and immutable financial audit logs.
* **FILE HUB (`/api/v1/files`):** Two-way secure multi-format upload, AEGIS extension blocking, VAULT secret redaction, prompt-injection tagging, content extraction (TXT/MD/CSV/JSON/code/DOCX/XLSX/PPTX/ZIP/PDF/images), file generation, and downloadable ZIP archives.
* **FORGE & Live Preview (`/api/v1/forge`):** Complete multi-file project generator (`react_vite`, `web_app`, `dashboard`, `landing_page`, `fastapi_service`), isolated AST/JSON + AEGIS verification, downloadable ZIP export, and CSP-sandboxed Live Preview.
* **Creative Studio, Voice & Visual (`/api/v1/creative`), BRIDGE (`/api/v1/bridge`), PULSE (`/api/v1/pulse`), CARAVAN BI (`/api/v1/caravan`), TURBO (`/api/v1/turbo`):** Voice turn & Web Speech API integration, multimodal visual frame analysis, creative studio jobs, iPhone PWA Web Share Target with AEGIS URL validation, live data-backed PULSE pages, zero-fabrication Caravan business analytics, and real TURBO latency benchmarks.
* **iPhone-First Responsive PWA (`frontend/`):** React + TypeScript + Vite PWA with `manifest.webmanifest` (standalone + Web Share Target), static-only Service Worker (`sw.js`), mobile bottom nav + drawer + desktop sidebar covering all 19 operational views wired directly to backend APIs.

## Quick Start

```bash
# Backend
pip install -r requirements.txt pytest pillow
cp .env.example .env
pytest
python3 backend/scripts/verify_migrations.py
python3 backend/scripts/verify_integrations.py
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000

# Frontend PWA (in a second terminal)
cd frontend && npm install && npm run build && npm run dev
```

## Documentation

* [Existing State & Implementation Plan](docs/IMPLEMENTATION_PLAN.md)
* [System Architecture & Serverless/Worker Split](docs/ARCHITECTURE.md)
* [Ecosystem Connectivity, OAuth 2.0 & Multi-Device Mesh](docs/ECOSYSTEM_AND_DEVICES.md)
* [Complete REST & WebSocket API Reference](docs/API_REFERENCE.md)
* [Environment Variables & Secret Management](docs/ENVIRONMENT_VARIABLES.md)
* [Deployment, Migration, Backup & Rollback Guide](docs/DEPLOYMENT.md)