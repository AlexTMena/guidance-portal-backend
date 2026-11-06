# Guidance Portal Backend

A minimal FastAPI service running on Python 3.14 with dependencies managed by uv.

## Project layout

```text
app/
├── api/
│   ├── routes/       # HTTP endpoint handlers
│   └── router.py     # Combines route modules
├── core/             # Environment configuration and auth dependencies
├── db/               # MongoDB connection lifecycle and access helpers
├── schemas/          # Pydantic request and response models
└── main.py           # FastAPI app and lifespan setup
```

Keep route handlers focused on HTTP concerns. Put shared configuration and
authentication dependencies in `core/`, database operations in `db/`, and
validated request/response shapes in `schemas/`.

## Seed test catalog

The test catalog seed script creates or updates the five starter tests in the
MongoDB `tests` collection. Each document stores only the test `name`; MongoDB
generates its `_id` automatically. It is safe to run repeatedly: records are
upserted by `name`, and unrelated documents are not deleted. The script also
removes the old `id` field from these five records if they were seeded by an
earlier version. It is never run automatically by FastAPI.

With a local backend `.env` configured for the database you intend to populate:

```powershell
uv run --env-file .env python -m app.scripts.seed_tests
```

To run it against the database configured in a running Docker Compose backend:

```powershell
docker compose exec backend python -m app.scripts.seed_tests
```

To seed the 21-item Beck questionnaire version from the user-provided PDF into
`test_questions`, run:

```powershell
uv run --env-file .env python -m app.scripts.seed_beck_questions
```

Or, for the database configured in Docker Compose:

```powershell
docker compose exec backend python -m app.scripts.seed_beck_questions
```

The script is repeatable and upserts by test and question key. It replaces the
earlier demo prompts for this test and keeps each choice's 0-3 score value. The
question set is treated as fixed; the script also removes legacy question
version metadata when it runs. It is never run automatically by FastAPI.

Check `MONGODB_DATABASE` before running the command so you seed the intended
local, dev, or UAT database. Keep the database URI private.

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
$env:APP_ENV = "development"
uv run uvicorn app.main:app --reload
```

The server runs at http://127.0.0.1:8000 by default. Stop it with Ctrl+C.
Local development enables the interactive documentation.

- Health check: http://127.0.0.1:8000/health — returns `{"status": "ok"}`.
- Interactive API documentation: http://127.0.0.1:8000/docs
- OpenAPI schema: http://127.0.0.1:8000/openapi.json

No environment variables are required for this initial service. Local `.env`
files are ignored by Git; `.env.example` can be committed when configuration
is added.

## Local development with Docker

Install Docker Desktop and enable Linux containers. From this directory, run:

```powershell
docker compose up --build
```

Open http://localhost:5011/health, http://localhost:5011/docs, or
http://localhost:5011/openapi.json. The local Docker target sets `APP_ENV=development`
and enables the interactive documentation. Local Docker listens on port 5011 both
inside and outside the container.

Edits under `app/` trigger automatic server reloads. The source mount is
read-only inside the container, and file polling supports Windows Docker
Desktop. Your Windows `.venv` is never mounted: Linux dependencies live at
`/opt/venv` inside the image.

For detached operation, logs, and shutdown:

```powershell
docker compose up --build -d
docker compose logs -f backend
docker compose down
```

Manage dependencies on the host with uv, then rebuild:

```powershell
uv add <package>
uv add --dev <development-package>
docker compose up --build
```

Commit both `pyproject.toml` and `uv.lock`. Dependency edits require rebuilding;
source edits do not. A local Python installation is only needed for the
non-Docker workflow and host-side uv dependency management.

## Production image

The final/default Dockerfile target is `production`. It runs one Uvicorn worker
as a non-root user, without reload, development dependencies, or uv tooling.
The image includes a health check for `/health` on the configured port and writes
logs to stdout/stderr. The `PORT` environment variable sets the listening port;
it defaults to `8000`.

```powershell
docker build -t guidance-portal-backend:production .
docker run --rm --name guidance-backend -p 127.0.0.1:8000:8000 guidance-portal-backend:production
```

Open http://localhost:8000/health to verify the image. Stop with Ctrl+C or
`docker stop guidance-backend` from another terminal. Use the same image
configuration for VPS dev, UAT, and eventual production; only local development
uses the `development` target and hot reload. Production images default to
`APP_ENV=production`, which disables `/docs`, `/redoc`, and `/openapi.json`.

## Dokploy: VPS dev and UAT

Create two separate **Applications** in Dokploy, connected to this backend's
Git repository:

| Setting | VPS dev | VPS UAT |
| --- | --- | --- |
| Suggested application name | guidance-backend-dev | guidance-backend-uat |
| Git branch | `dev` | `uat` |
| Domain | `dev-guidance-portal-backend.alexandromena.com` | `uat-guidance-portal-backend.alexandromena.com` |
| Build type | Dockerfile | Dockerfile |
| Dockerfile | `Dockerfile` | `Dockerfile` |
| Build context | `.` (backend repository root) | `.` (backend repository root) |
| Build stage | Leave empty (defaults to production) | Leave empty (defaults to production) |
| `PORT` environment variable | `5011` | `5021` |
| Domain container port | `5011` | `5021` |
| `APP_ENV` environment variable | `production` | `production` |

1. Ensure both branches contain this Docker configuration. If the backend is
   later placed in a monorepo, adjust the Dockerfile path and build context to
   the backend directory.
2. Create DNS `A` records for both subdomains pointing to the VPS public IPv4
   address. Add `AAAA` records only if IPv6 is configured for the VPS.
3. In each Application's Domains tab, add its hostname with path `/`, container
   port `5011` for dev or `5021` for UAT, and HTTPS enabled using Let's Encrypt. The VPS must allow
   Dokploy's normal HTTP/HTTPS ingress on ports 80 and 443.
4. Leave direct port publishing unset. Traefik routes the domains to internal
   configured container port; direct VPS host port publishing is not needed. Do not deploy the
   local Compose file to Dokploy or override the image's startup command.
5. Enable **Auto Deploy** for each Application. With Dokploy's GitHub integration,
   auto deployment is supported directly; with other Git providers, configure
   the Application's webhook in the repository as described in the
   [Auto Deploy documentation](https://docs.dokploy.com/docs/core/auto-deploy).
   Check that each Application's configured branch matches its intended branch.
6. Trigger the first deployment and inspect build/runtime logs. Confirm each
   public health URL returns HTTP 200 and `{"status":"ok"}`:
   - https://dev-guidance-portal-backend.alexandromena.com/health
   - https://uat-guidance-portal-backend.alexandromena.com/health
   Confirm `/docs`, `/redoc`, and `/openapi.json` are unavailable on both
   deployed environments. They remain enabled for local development only.
7. Verify that a subsequent push to `dev` deploys only VPS dev and a push to
   `uat` deploys only UAT.

See [Dokploy domain configuration](https://docs.dokploy.com/docs/core/domains)
for the distinction between container routing and published host ports.

Develop locally on `dev`, promote reviewed changes to `uat` for acceptance
testing, then promote accepted changes to `main`. Git branch selection is a
Dokploy setting; the Dockerfile does not switch behavior based on branch names.
Deployments rebuild from committed code; VPS environments do not hot reload.

Production will track `main`, using the same production image configuration.
Its hosting and hostname are still to be decided. This setup does not provision
DNS, Dokploy Applications, Git branches, databases, or remote deployments.

### UAT production-level settings

The UAT Application should use the production Docker target, `APP_ENV=production`,
no reload command, HTTPS, and no published host port. Keep secrets in Dokploy's
environment settings rather than Git. Give UAT its own credentials and data
when a database is added. Limit access to UAT at the proxy or application layer
if it should be private; HTTPS alone does not restrict who can sign in.

For a production-ready operational setup, also configure Dokploy restart and
resource limits, retain deployment/runtime logs, and monitor uptime and health.
Add explicit CORS origins when the frontend begins calling this API. Keep
database backups and restore checks in scope once persistent data is introduced.

## Authentication API and MongoDB

FastAPI accepts only short-lived RS256 bearer tokens issued by the Next.js BFF.
It validates the signature, issuer, audience, expiration, and token use, then
loads the current user role from MongoDB. It does not trust browser-supplied
identity headers. `/health` remains public for container health checks; the
profile and role-management endpoints require a valid BFF token.

- `GET /auth/me` returns the authenticated user's Google subject, email, name,
  and current role.
- `GET /tests` returns the test catalog from MongoDB. It requires a valid BFF
  token and returns MongoDB's generated identifier as `id` alongside each test
  name for use as a frontend list key.
- `GET /tests/{test_id}` returns one catalog entry by MongoDB identifier and
  requires a valid BFF token.
- `GET /tests/{test_id}/questions` returns the ordered question records for a
  catalog entry and requires a valid BFF token.
- `GET /tests/{test_id}/responses/draft` returns only the signed-in user's own
  unfinished Beck draft. `PUT` on the same route saves or updates that draft.
- `POST /tests/{test_id}/responses/draft/start` starts or resumes that user's
  active attempt and returns its opaque attempt ID.
- `POST /tests/{test_id}/responses/submit` validates all 21 Beck answers,
  calculates the total on the backend, stores the submission, and returns the
  score and interpretation. The backend reads option scores from MongoDB; it
  does not trust a client-provided score.
- `GET /tests/{test_id}/responses/me` returns the signed-in user's score and
  interpretation for their latest submission without returning item-level
  answers.
- `GET /tests/{test_id}/responses/staff` returns submitted item-level answers
  and is restricted to users whose current role is `counselor` or `admin`.
  The endpoint returns at most 100 submissions per request.
- `PATCH /admin/users/{google_sub}/role` changes a user's role and is restricted
  to admins. Valid roles are `student`, `counselor`, and `admin`; admins cannot
  change their own role.

Beck answers and scores are stored in `test_responses`. The participant can
save and resume their own draft and see their aggregate score after submission;
only counselors and admins can retrieve submitted item-level answers. A
participant can start another attempt after submitting; earlier submissions
remain available to staff. The category thresholds follow the interpretation
table in the supplied Beck PDF: 1–10, 11–16, 17–20,
21–30, 31–40, and over 40. The minimum possible score (0) is grouped with the
lowest band. The displayed category is screening feedback, not a diagnosis.

The staff response includes a follow-up flag when Beck item 9 is scored above
zero. This flag is not an alert or a complete risk assessment. The organization
must define and staff a timely follow-up procedure before using the assessment
with real participants.

Configure `MONGODB_URI`, `MONGODB_DATABASE`, `API_TOKEN_ISSUER`,
`API_TOKEN_AUDIENCE`, and `API_TOKEN_PUBLIC_KEY_B64` from the backend
`.env.sample` or Dokploy environment settings. Production startup requires
MongoDB. Local development can run without MongoDB, but protected endpoints
return unavailable until a database is configured. The frontend README contains
the step-by-step Google OAuth, Atlas, and per-environment key setup.
