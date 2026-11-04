# Guidance Portal Backend

A minimal FastAPI service running on Python 3.14 with dependencies managed by uv.

## Setup

Install Python 3.14 and uv, then run these commands from this directory:

```powershell
uv sync --locked
```

uv uses the existing `.venv` when compatible, or creates one if needed. The
committed `uv.lock` records the dependency versions for reproducible installs.
After intentionally changing dependencies in `pyproject.toml`, run `uv sync`
to update the environment and lockfile.

## Development

```powershell
uv run uvicorn app.main:app --reload
```

The server runs at http://127.0.0.1:8000 by default. Stop it with Ctrl+C.

- Health check: http://127.0.0.1:8000/health — returns `{"status": "ok"}`.
- Interactive API documentation: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

No environment variables are required for this initial service. Local `.env`
files are ignored by Git; `.env.example` can be committed when configuration
is added.
