# ULTRON OS 2026 — Deployment & Verification Guide

## 1. Local Development

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# Run automated test suite
pytest

# Verify configured integrations honestly
python3 backend/scripts/verify_integrations.py

# Start local API server
PYTHONPATH=backend uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Bootstrap your initial OWNER account:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/bootstrap-owner \
  -H "Content-Type: application/json" \
  -d '{"username":"owner","email":"owner@example.com","password":"ChangeMeStrong!2026"}'
```

---

## 2. Supabase Database Setup (PostgreSQL + pgvector + RLS)

1. Create a Supabase project at `https://supabase.com/dashboard`.
2. Open the **SQL Editor** and run `backend/migrations/supabase/001_initial_schema.sql`.
3. Collect:
   - **Connection string** (Transaction or Session Pooler URL) -> set as `ULTRON_DATABASE_URL` with `postgresql+psycopg://...` prefix and `?sslmode=require`.
   - **Project URL** -> `SUPABASE_URL`
   - **Service Role Key** -> `SUPABASE_SERVICE_ROLE_KEY` (keep strictly server-side).
4. Install PostgreSQL driver when deploying with Postgres:
   ```bash
   pip install "psycopg[binary]>=3.2.0"
   ```

---

## 3. Google Gemini API Setup

1. Create an API key in Google AI Studio (`https://aistudio.google.com/apikey`).
2. Set `GEMINI_API_KEY` in your runtime environment (Vercel / Docker / `.env`).
3. Verify live connectivity:
   ```bash
   python3 backend/scripts/verify_integrations.py
   ```
   Confirm `providers.gemini.live_verified` is `true` and `capability_state` is `AVAILABLE`.

---

## 4. Vercel Serverless Deployment

The repository includes `vercel.json` and `api/index.py` exporting the FastAPI ASGI app.

1. Import the GitHub repository in Vercel (`https://vercel.com/new`).
2. Configure all required production environment variables in **Project Settings -> Environment Variables**:
   - `ULTRON_ENV=production`
   - `ULTRON_JWT_SECRET` (>= 32 random chars)
   - `ULTRON_VAULT_MASTER_KEY` (>= 32 random chars)
   - `ULTRON_DATABASE_URL` (Supabase Postgres connection string)
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
   - `GEMINI_API_KEY`
   - `ULTRON_CORS_ORIGINS` (your production frontend origins)
3. Deploy and verify:
   ```bash
   curl https://<your-app>.vercel.app/health/ready
   ```

---

## 5. Cloudflare Worker Edge Gateway

The `cloudflare/` directory contains an edge security proxy (`worker.ts` + `wrangler.toml`) that injects HSTS/security headers, propagates `X-Request-ID`, optionally enforces Workers KV rate limiting, and proxies traffic to your Vercel or container origin.

```bash
cd cloudflare
npx wrangler login
npx wrangler secret put ULTRON_ORIGIN_URL   # e.g. https://<your-app>.vercel.app
npx wrangler deploy
```

Verify the edge gateway:
```bash
curl https://<your-worker>.workers.dev/edge/health
```

---

## 6. Docker Deployment

```bash
docker build -t ultron-os-2026:latest .
docker run --rm -p 8000:8000 --env-file .env ultron-os-2026:latest
```
