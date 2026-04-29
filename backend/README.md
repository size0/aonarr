# Backend

FastAPI backend for aonarr.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
python -m uvicorn app.main:app --reload
```

Health check:

```text
GET http://localhost:8000/api/v1/health
```

## LLM mode

Default mode is mock:

```powershell
$env:LLM_MODE = "mock"
```

To call a real OpenAI-compatible provider configured through an LLM Profile:

```powershell
$env:LLM_MODE = "live"
```

## Storage backend

Default local mode is JSON:

```powershell
$env:STORAGE_BACKEND = "json"
```

PostgreSQL schema migrations are available under `migrations`.

```powershell
$env:DATABASE_URL = "postgresql://aonarr:change-me@localhost:5432/aonarr"
python scripts\apply_migrations.py
```

## Local checks

```powershell
python scripts\smoke_check.py
python scripts\unit_check.py
```
