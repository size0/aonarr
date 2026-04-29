# Infrastructure

This folder contains self-hosted deployment support for aonarr.

Current scope:

- Backend FastAPI service
- Frontend Vite service
- PostgreSQL for application data
- Redis for worker queue and run event delivery

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
