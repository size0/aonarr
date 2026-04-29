# SerialWriter Engine

SerialWriter Engine is a clean-room commercial rewrite project for a self-hosted, single-tenant web novel automation system.

The product target is an author-facing web workspace where customers bring their own LLM API keys and run an automatic serialization engine for planning, drafting, reviewing, pausing, recovering, cost tracking, and exporting chapters.

## Clean-room boundary

This repository must not copy or derive from PlotPilot source code, prompts, assets, brand, database schema, API routes, screenshots, or long-form product text.

Implementation must be based on the clean-room specification package created separately under:

```text
D:\13250\桌面\PlotPilot-new\docs\clean-room-commercial-rewrite
```

## MVP stack

- Backend: Python, FastAPI
- Frontend: Vue 3, Vite, TypeScript
- Production database: PostgreSQL
- Worker and event delivery: Redis-backed worker plus SSE
- Deployment target: Docker Compose self-hosted single tenant

## Current status

The repository now contains a runnable MVP skeleton:

- Admin login
- LLM Profile CRUD with masked secrets
- Project CRUD
- StoryBible save and readiness check
- SerialRun create, pause, resume, cancel
- Deterministic background worker for planning, drafting, review, cost tracking
- SSE run event stream
- Chapter plans and draft versions
- User-editable clean-room prompt templates for plan, draft, and review
- Automatic live revision retry before manual quality gate recovery
- Manual quality gate recovery for drafts marked `needs_revision`
- Markdown/TXT export
- PostgreSQL schema/migration foundation and Redis Compose placeholders

The automatic writing engine currently uses deterministic placeholder drafting so the full product loop can be tested before real LLM prompts are designed.

## Local backend preview

From the backend folder, install dependencies and run:

```powershell
cd D:\13250\桌面\SerialWriterEngine\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m uvicorn app.main:app --reload
```

Health endpoint:

```text
GET http://localhost:8000/api/v1/health
```

## Local frontend preview

From the frontend folder, install dependencies and run:

```powershell
cd D:\13250\桌面\SerialWriterEngine\frontend
npm install
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

## MVP walkthrough

1. Open the frontend.
2. Login with the local default:
   - Username: `admin`
   - Password: `change-me`
3. Create an LLM Profile. By default `LLM_MODE=mock`, so no external model is called.
4. Create a Project.
5. Save Story Bible.
6. Start Serial Run.
7. Watch SSE events update in the run log.
8. If a draft needs revision, manually accept/reject it in the draft card.
9. Export accepted chapters as Markdown.

## Live LLM mode

The backend can call OpenAI-compatible `/chat/completions` providers when explicitly enabled:

```powershell
$env:LLM_MODE = "live"
python -m uvicorn app.main:app --reload
```

Use an LLM Profile with:

- `provider_type`: `openai_compatible`
- `base_url`: for example `http://localhost:11434/v1` or another OpenAI-compatible gateway
- `model`: the model name exposed by that provider
- `api_key`: the user's own key

API keys are encrypted in the MVP JSON store and masked in API responses. Do not commit `local-data`.

## Prompt templates

The live LLM path uses three clean-room templates:

- `serial_plan`
- `serial_draft`
- `serial_review`
- `serial_revision`

They can be edited in the frontend Prompt Templates panel or through:

```text
GET /api/v1/prompt-templates
PATCH /api/v1/prompt-templates/{template_id}
POST /api/v1/prompt-templates/{template_id}/reset
```

Templates are stored in the MVP JSON store. The built-in defaults are original clean-room templates for this project.

## Storage backend

The MVP defaults to JSON storage:

```text
STORAGE_BACKEND=json
```

PostgreSQL schema support is staged in:

```text
backend/migrations/001_initial_schema.sql
```

To initialize a configured PostgreSQL database:

```powershell
cd D:\13250\桌面\SerialWriterEngine\backend
python scripts\apply_migrations.py
```

The current application store remains JSON-backed until the repository layer is switched to PostgreSQL in the next phase.

## Manual quality gate recovery

If live review marks a draft as `needs_revision`, the worker first tries automatic revision up to `REVISION_MAX_ATTEMPTS`.

Default:

```text
REVISION_MAX_ATTEMPTS=1
```

If the final reviewed draft still needs revision, the run pauses with `quality_gate_needs_revision`.

In the frontend:

1. Review the draft card.
2. Click `Accept` to accept the draft manually.
3. Click `Resume` if the run is still paused.

The backend advances the completed chapter count when the accepted draft matches the paused chapter, preventing duplicate regeneration of the same chapter.

## Tests

```powershell
cd D:\13250\桌面\SerialWriterEngine\backend
pytest
```

If the system pytest is too old for the active Python version, run the built-in smoke check instead:

```powershell
cd D:\13250\桌面\SerialWriterEngine\backend
python scripts\smoke_check.py
python scripts\unit_check.py
```

## Security notes before production

- Change `ADMIN_PASSWORD`.
- Change `SECRET_KEY`.
- Switch the repository layer from JSON storage to PostgreSQL after migrations are applied.
- Replace deterministic draft generation with clean-room prompts.
- Add rate limiting and CSRF strategy if cookie auth is introduced.
- Keep LLM API keys masked in responses and logs.
