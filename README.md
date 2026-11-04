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

## Local development with Docker

Install Docker Desktop and enable Linux containers. From this directory, run:

```powershell
docker compose up --build
```

Open http://localhost:5011/health, http://localhost:5011/docs, or
http://localhost:5011/openapi.json. Local Docker listens on port 5011 both
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
uses the `development` target and hot reload.

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
   Also check `/docs` and `/openapi.json` on both domains.
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
