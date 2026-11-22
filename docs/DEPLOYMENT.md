# ULTRON OS 2026 — Deployment, Migration, Worker & Rollback Guide

## 1. Local Development & Verification

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
cp .env.example .env

# Run full automated test suite
pytest

# Verify schema & Supabase migrations
python3 backend/scripts/verify_migrations.py

# Verify configured cloud integrations honestly
python3 backend/scripts/verify_integrations.py

# Start API server (Swagger UI at http://127.0.0.1:8000/docs)
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# In a second terminal, run persistent worker (optional for local dev)
python3 backend/worker.py --poll-interval 5
```

---

## 2. Supabase PostgreSQL + pgvector + RLS + Private Storage Setup

1. Create or open your Supabase project (`https://supabase.com/dashboard`).
2. Run all **four** idempotent SQL migrations in order via **SQL Editor** or `psql` (never run destructive drops without approval):
   ```bash
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/001_initial_schema.sql
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/002_full_backend_schema.sql
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/003_ecosystem_and_devices.sql
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/004_full_platform_features.sql
   ```
   All 53 ORM tables match `001`–`004` with `ENABLE ROW LEVEL SECURITY` and `tenant_isolation_*` policies.
3. Create a **private** Storage bucket named `ultron-private-files` (matching `SUPABASE_STORAGE_BUCKET`). **Never make this bucket public** — ULTRON encrypts objects with AES-256-GCM under tenant-scoped paths (`{tenant_id}/{file_id}_{filename}`) and issues short-lived signed URLs (`POST /api/v1/files/{id}/signed-url`).
4. Set environment variables (strictly server-side — **never expose `SUPABASE_SERVICE_ROLE_KEY` to frontend clients**):
   - `ULTRON_DATABASE_URL=postgresql+psycopg://postgres:<password>@<pooler-host>:6543/postgres?sslmode=require`
   - `SUPABASE_URL=https://<project-ref>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY=<service-role-key>`
   - `SUPABASE_STORAGE_BUCKET=ultron-private-files`
5. Install the PostgreSQL driver for Postgres deployments: `pip install "psycopg[binary]>=3.2.0"`.

---

## 3. Google Gemini API (Primary NEON Provider)

Verified active Nov 2026 Google AI Studio models configured in NEON:
- Tier 1 (Fast): `gemini-3.5-flash-lite`
- Tier 2–3 (Standard / Agentic): `gemini-3.8-flash`
- Tier 4–5 (Frontier Reasoning): `gemini-4-argon`
- Embeddings: `gemini-embedding-001`
- Image Generation: `gemini-nano-banana-2.1`

1. Generate an API key in Google AI Studio (`https://aistudio.google.com/apikey`).
2. Set `GEMINI_API_KEY` exclusively via Vercel / Worker secret env vars (never commit or hardcode).
3. Optionally configure `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL` for automatic multi-provider failover.
4. Verify live access: `python3 backend/scripts/verify_integrations.py` (expect `providers.gemini.capability_state == "AVAILABLE"`).

---

## 4. Vercel Full-Stack Deployment (API + iPhone-First PWA)

1. Import `epejuwon-sketch/ULTRON` in Vercel (`https://vercel.com/new`).
2. Configure production Environment Variables in Vercel:
   - `ULTRON_ENV=production`
   - `ULTRON_JWT_SECRET` (`>= 32` CSPRNG chars)
   - `ULTRON_VAULT_MASTER_KEY` (`>= 32` CSPRNG chars)
   - `ULTRON_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET=ultron-private-files`
   - `GEMINI_API_KEY`
   - `ULTRON_REDIS_REST_URL` & `ULTRON_REDIS_REST_TOKEN` (Upstash Redis REST for shared multi-instance rate limiting)
   - `ULTRON_CORS_ORIGINS=https://<your-production-domain>`
   - `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_URI=https://<your-production-domain>/api/v1/integrations/oauth/google/callback`
   - `GITHUB_TOKEN`, `VERCEL_TOKEN`, `CLOUDFLARE_API_TOKEN`
3. `vercel.json` builds both `api/index.py` (`/api/*`, `/health*`, `/docs`, `/openapi.json`) and `frontend/package.json` (`dist/` iPhone-first PWA).
4. **HTTPS & iPhone Safari Requirements:** iPhone PWA install, Service Worker (`sw.js`), WebAuthn Face ID Passkeys (`rp_id` = your HTTPS domain), microphone, and geolocation all require valid TLS/HTTPS on your production domain.
5. Verify post-deploy health:
   ```bash
   curl https://<your-production-domain>/health/ready
   ```

> **Serverless Limitation Notice:** Vercel functions have bounded execution timeouts and do not support permanent background daemons or persistent WebSocket rooms. Long-running ARGON DAGs, DLQ retries, recurring schedules, and continuous 60-second AEGIS security scans MUST run on the dedicated persistent worker below.

---

## 5. Dedicated Persistent Worker Container Deployment

Deploy `Dockerfile.worker` to Fly.io, Railway, Render, Google Cloud Run (`min-instances=1`), or Docker Compose with the exact same `ULTRON_DATABASE_URL` and secrets:

- Exposes HTTP health probes on port `8081` (`GET /health/live`, `GET /health/ready`) wired into `Dockerfile.worker` `HEALTHCHECK`.
- Supports bounded exponential backoff (`15s` → `600s` cap), `DEAD_LETTER` queue (`POST /api/v1/argon/jobs/{id}/requeue`), graceful `SIGTERM` shutdown, and strict non-bypassable ApprovalGate enforcement.

```bash
# Build & run worker container standalone
docker build -f Dockerfile.worker -t ultron-os-2026-worker:latest .
docker run --rm -p 8081:8081 --env-file .env ultron-os-2026-worker:latest
curl http://127.0.0.1:8081/health/ready
```

---

## 6. Cloudflare Edge Gateway, DNS & WAF

1. Proxy your custom production domain through Cloudflare with **Full (Strict) SSL/TLS**, **Always Use HTTPS**, and **WAF Managed Rules** enabled.
2. Add Cloudflare Edge Rate Limiting rules matching `/api/v1/auth/*` (strict login brute-force protection) and `/api/v1/*`.
3. Optionally deploy `cloudflare/worker.ts`:
   ```bash
   cd cloudflare
   npx wrangler login
   npx wrangler secret put ULTRON_ORIGIN_URL   # e.g. https://<your-app>.vercel.app
   npx wrangler deploy
   curl https://<your-worker>.workers.dev/edge/health
   ```

---

## 7. Backups, Monitoring & Rollback Procedures

* **Database Backups & Recovery:**
  * Production (Supabase): Enable **Supabase Daily Backups + Point-in-Time Recovery (PITR)** on Pro+ plans. Test restoration quarterly to a staging Supabase project before promoting schema changes.
  * Local SQLite: `python3 backend/scripts/backup_database.py` uses SQLite's online `backup()` API safely under WAL mode.
* **Migration Rollback Considerations:** Migrations `001`–`004` are strictly additive (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`) so code rollbacks remain backward-compatible without destructive drops.
* **Monitoring:** Scrape `GET /api/v1/monitoring/metrics` (Prometheus), poll `GET /api/v1/monitoring/overview`, `/health/ready`, and Worker `:8081/health/ready`.
* **Rollback Procedure:**
  1. **Vercel:** `vercel rollback` or promote the previous verified deployment in the Vercel Dashboard.
  2. **Worker Container:** Redeploy previous immutable container image tag.
  3. **Application Governance Record:** Call `POST /api/v1/projects/{project_id}/deployments/{deployment_id}/rollback` (`OWNER` only) to record an audited rollback trace.
  4. **Emergency Autonomous Halt:** `PUT /api/v1/settings` with `{"key": "autonomous_execution_enabled", "value": false}` (`OWNER` only) immediately freezes all ARGON task executions without taking down read APIs.
