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

## 2. Supabase PostgreSQL + pgvector + RLS + Storage Setup

1. Create or open your Supabase project (`https://supabase.com/dashboard`).
2. Run both SQL migrations in order via **SQL Editor** or `psql`:
   ```bash
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/001_initial_schema.sql
   psql "$SUPABASE_DIRECT_URL" -f backend/migrations/supabase/002_full_backend_schema.sql
   ```
3. Create a private Storage bucket named `ultron-artifacts` (matching `SUPABASE_STORAGE_BUCKET`).
4. Set environment variables (strictly server-side — **never expose `SUPABASE_SERVICE_ROLE_KEY` to frontend clients**):
   - `ULTRON_DATABASE_URL=postgresql+psycopg://postgres:<password>@<pooler-host>:6543/postgres?sslmode=require`
   - `SUPABASE_URL=https://<project-ref>.supabase.co`
   - `SUPABASE_SERVICE_ROLE_KEY=<service-role-key>`
5. Install the PostgreSQL driver for Postgres deployments: `pip install "psycopg[binary]>=3.2.0"`.

---

## 3. Google Gemini API (Primary NEON Provider)

1. Generate an API key in Google AI Studio (`https://aistudio.google.com/apikey`).
2. Set `GEMINI_API_KEY` in Vercel and your persistent worker environment.
3. Optionally configure `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `OLLAMA_BASE_URL` for automatic multi-provider failover.
4. Verify live access: `python3 backend/scripts/verify_integrations.py` (expect `providers.gemini.capability_state == "AVAILABLE"`).

---

## 4. Vercel Serverless API Deployment

1. Import `epejuwon-sketch/ULTRON` in Vercel (`https://vercel.com/new`).
2. Configure production Environment Variables in Vercel:
   - `ULTRON_ENV=production`
   - `ULTRON_JWT_SECRET` (`>= 32` CSPRNG chars)
   - `ULTRON_VAULT_MASTER_KEY` (`>= 32` CSPRNG chars)
   - `ULTRON_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - `GEMINI_API_KEY`
   - `ULTRON_CORS_ORIGINS=https://<your-frontend-domain>`
3. Vercel automatically uses `vercel.json` -> `api/index.py`.
4. Verify post-deploy health:
   ```bash
   curl https://<your-app>.vercel.app/health/ready
   ```

> **Serverless Limitation Notice:** Vercel functions have bounded execution timeouts and do not support permanent background daemons or persistent WebSocket rooms. Long-running ARGON DAGs (`POST /api/v1/tasks/{id}/enqueue`) and recurring schedules MUST be processed by the dedicated persistent worker below.

---

## 5. Dedicated Persistent Worker Deployment

Deploy `Dockerfile.worker` to Fly.io, Railway, Render, Google Cloud Run (min-instances=1), or Docker Compose with the exact same `ULTRON_DATABASE_URL` and provider keys:

```bash
# Full stack via Docker Compose (API + Persistent Worker)
docker compose up --build -d

# Or build worker image standalone
docker build -f Dockerfile.worker -t ultron-os-2026-worker:latest .
docker run --rm --env-file .env ultron-os-2026-worker:latest
```

---

## 6. Cloudflare Worker Edge Gateway & DNS

```bash
cd cloudflare
npx wrangler login
npx wrangler secret put ULTRON_ORIGIN_URL   # e.g. https://<your-app>.vercel.app
npx wrangler deploy
curl https://<your-worker>.workers.dev/edge/health
```

---

## 7. Backups, Monitoring & Rollback Procedures

* **Database Backups:**
  * Production (Supabase): Enable Supabase Daily Backups / Point-in-Time Recovery (PITR) or run `python3 backend/scripts/backup_database.py --output-dir ./backups`.
  * Local SQLite: `python3 backend/scripts/backup_database.py` uses SQLite's online `backup()` API safely under WAL mode.
* **Monitoring:** Scrape `GET /api/v1/monitoring/metrics` (Prometheus) or poll `GET /api/v1/monitoring/overview` and `/health/ready`.
* **Rollback Procedure:**
  1. **Vercel:** `vercel rollback` or promote the previous verified deployment in the Vercel Dashboard.
  2. **Worker Container:** Redeploy previous immutable container image tag.
  3. **Application Governance Record:** Call `POST /api/v1/projects/{project_id}/deployments/{deployment_id}/rollback` (`OWNER` only) to record an audited rollback trace.
  4. **Emergency Autonomous Halt:** `PUT /api/v1/settings` with `{"key": "autonomous_execution_enabled", "value": false}` (`OWNER` only) immediately freezes all ARGON task executions without taking down read APIs.
