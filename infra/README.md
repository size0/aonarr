# Infrastructure

This folder contains self-hosted deployment support for aonarr.

Current development scope:

- Backend FastAPI service
- Frontend Vite service
- PostgreSQL for application data
- Redis for worker queue and run event delivery

## Local development

Run from this folder:

```powershell
docker compose up -d
```

The backend currently defaults to `STORAGE_BACKEND=json` while the PostgreSQL schema and service are staged. To initialize PostgreSQL:

```powershell
docker compose exec backend python scripts/apply_migrations.py
```

Then open:

```text
http://localhost:5173
```

## Commercial Beta deployment

The production compose file runs the backend behind a production-built Nginx frontend.
It currently uses the backend JSON store with a persistent Docker volume.

1. Copy the production environment file:

```powershell
Copy-Item ..\.env.production.example ..\.env.production
```

2. Edit `..\.env.production`:

- Set a strong `ADMIN_PASSWORD`.
- Set a random `SECRET_KEY`.
- Set `CORS_ORIGINS` to the public HTTPS origin.
- Keep `STORAGE_BACKEND=json` until PostgreSQL storage is implemented.
- Use `LLM_MODE=mock` for deployment smoke tests, then switch to `live` after model configuration.

3. Build and start:

```powershell
docker compose -f docker-compose.prod.yml --env-file ../.env.production up -d --build
```

4. Check service health:

```powershell
docker compose -f docker-compose.prod.yml --env-file ../.env.production ps
```

```text
GET http://localhost/api/v1/health
```

5. Put a reverse proxy or cloud load balancer in front of the frontend service for HTTPS.
The frontend Nginx container serves the SPA and proxies `/api` requests, including SSE, to the backend.

## Backup notes

For the current Beta JSON backend, back up the `backend_data` Docker volume regularly.
It contains application data, encrypted model profile secrets, prompt templates, run events, drafts, and exports.

PostgreSQL schema files are staged under `backend/migrations`, but the current runtime store is still JSON.
