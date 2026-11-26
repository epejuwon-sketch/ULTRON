# ULTRON OS 2026 — Ecosystem Connectivity, OAuth 2.0 & Multi-Device Mesh Guide

## 1. Unified Integration Manager & OAuth 2.0 (PKCE S256)

Every external provider is managed through `backend/app/services/integration_manager.py` and exposed at `/api/v1/integrations/*`:

* **Credential Encryption:** Stored per-tenant using AES-256-GCM with HKDF-SHA256 key derivation and AAD binding (`ultron-integration::{tenant_id}::{provider}`). Credentials are never returned to frontend clients.
* **OAuth 2.0 + PKCE:** Least-privilege, per-service Google scopes (Drive, Gmail, Calendar, Docs, Sheets, Slides, Cloud) and GitHub scopes. Single-use `oauth_states` enforce CSRF and RFC 7636 PKCE `S256` verification.
* **Lifecycle Endpoints:**
  * `GET /api/v1/integrations/connections` — Tenant connection inventory + Antigravity plugin environment.
  * `POST /api/v1/integrations/{provider}/connect` — Connect encrypted API key / token (`OWNER`/`ADMIN`).
  * `POST /api/v1/integrations/oauth/{provider}/start` & `/callback` — Start & complete OAuth 2.0 + PKCE.
  * `POST /api/v1/integrations/{provider}/refresh` — Rotate OAuth access token using encrypted refresh token.
  * `POST /api/v1/integrations/{provider}/verify` — Run live verification probe (status becomes `AVAILABLE` ONLY on live pass).
  * `POST /api/v1/integrations/{provider}/disconnect` — Revoke upstream token where supported and zero stored credentials.

## 2. Official November 2026 Gemini Models (NEON Primary Provider)

Updated per official Google AI Studio documentation (`https://aistudio.google.com/docs/models`):
* **Tier 1 (Fast Operations):** `gemini-3.5-flash-lite`
* **Tier 2–3 (Standard & Engineering):** `gemini-3.8-flash`
* **Tier 4–5 (Frontier Reasoning & Orchestration):** `gemini-4-argon`
* **Embeddings:** `gemini-embedding-001` (supports `gemini-embedding-2` multimodal embeddings)
* **Image Generation:** `gemini-nano-banana-2.1`
* **Dynamic Model Discovery:** `GeminiClient.list_models()` queries `GET /v1beta/models` live.

## 3. Google Ecosystem, GitHub Engineering, Cloud & Web Research

* **Google Ecosystem (`/api/v1/google/*`):**
  * Drive (`/drive/files`, `/drive/folders`, `/drive/files/{id}/read`, `/drive/upload`)
  * Gmail (`/gmail/messages`, `/gmail/threads/{id}`, `/gmail/drafts`, `/gmail/send-request` — outbound send strictly gated by ApprovalGate)
  * Calendar (`/calendar/calendars`, `/calendar/events`, `/calendar/availability`)
  * Docs (`/docs`, `/docs/{id}`, `/docs/{id}/append`), Sheets (`/sheets`, `/sheets/{id}/values`), Slides (`/slides`, `/slides/{id}/slides`)
  * Google Cloud (`/cloud/projects`, `/cloud/projects/{id}/services`)
* **Web Research (`/api/v1/research/search`, `/api/v1/research/fetch`):** Queries Google Programmable Search (when configured) and Wikipedia API + SSRF-safe public URL extraction, preserving exact citations and separating verified retrieved content from synthesis.
* **GitHub Engineering (`/api/v1/github/*`):** Repositories, branches, commits, file read/upsert (blocks direct writes to `main`/`master`/`production`), pull requests, issues, Actions workflow runs, and releases (ApprovalGate required for release creation).
* **Antigravity Adapter (`/api/v1/integrations/antigravity`):** Inspects only official connected plugin CLIs (`gh`, `gdrive`, `gmail`), reports disconnected CLIs as `REQUIRES_CONFIGURATION`, and explicitly marks undocumented/prohibited host interfaces as `UNAVAILABLE`.

## 4. Multi-Device Connectivity Mesh & Desktop Agent

Supported platforms: `windows`, `macos`, `ios`, `ipados`, `android`, `pwa`.

1. **Initiate Pairing (Authenticated User):** `POST /api/v1/devices/pair/init` returns a single-use `ULT-...` pairing code with explicit permission flags (all sensitive permissions — `camera`, `microphone`, `location`, `contacts`, `messages`, `personal_files`, `app_launch`, `local_dev_tools` — default to `false`).
2. **Complete Pairing (Device):** `POST /api/v1/devices/pair/complete` exchanges the pairing code for a single-display `ult_dev_...` token (stored hashed via SHA-256).
3. **Desktop Agent (`device_agent/ultron_desktop_agent.py`):**
   ```bash
   python3 device_agent/ultron_desktop_agent.py \
     --server http://127.0.0.1:8000 \
     --pair-code ULT-XXXXXXXX \
     --authorized-folder "$HOME/ULTRON_Workspace"
   ```
   Path traversal outside `--authorized-folder` is unconditionally blocked (`PermissionError`).
4. **Cross-Device Sync & Revocation:** `POST /api/v1/devices/{id}/tasks` verifies granted permissions and triggers ApprovalGate for sensitive actions; `POST /api/v1/devices/{id}/revoke` immediately invalidates the device token.

## 5. Unified Natural-Language Orchestration

`POST /api/v1/orchestrate` accepts a plain-language objective without requiring manual agent selection. NEON recalls relevant memories, discovers authorized integrations & online devices, selects specialist agents and reasoning tier, hands off to ARGON for DAG planning/ApprovalGate enforcement/execution/verification, and returns the complete verified trace.
