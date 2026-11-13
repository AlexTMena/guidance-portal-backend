# e-Gabay Backend

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

## Fresh database setup

Run these steps once for each new database, from its own backend environment.
The backend creates its MongoDB indexes when it starts, but seed data is not
created automatically. Set `MONGODB_URI` and `MONGODB_DATABASE` before starting
the backend; check carefully that they point to the database you intend to
initialize. Never commit credentials or paste them into commands.

The seed commands are repeatable and safe to rerun. The test catalog and
question sets are upserted; built-in forms are inserted if missing. The Student
Cumulative Form seed also repairs its Section 8 support choices and Section 9
condition on an existing form, without changing submissions or other sections. The
test catalog includes Beck, DASS-21, BRS, and PCL-5. C-SSRS is not included.

### Local Docker environment

1. Start MongoDB. The local Compose file runs the backend only, so MongoDB must
   be running separately. Create `.env` from `.env.sample`, then set
   `MONGODB_URI` to an address reachable from the backend container (for
   MongoDB running on the host, use `mongodb://host.docker.internal:27017`)
   and set `MONGODB_DATABASE` to a new local database name:

   ```powershell
   Copy-Item .env.sample .env
   ```

2. Start the backend from this directory:

   ```powershell
   docker compose up --build -d
   ```

3. Seed the catalog, assessment questions, and survey forms in order:

   ```powershell
   docker compose exec backend python -m app.scripts.seed_tests
   docker compose exec backend python -m app.scripts.seed_beck_questions
   docker compose exec backend python -m app.scripts.seed_dass21_questions
   docker compose exec backend python -m app.scripts.seed_brs_questions
   docker compose exec backend python -m app.scripts.seed_pcl5_questions
   docker compose exec backend python -m app.scripts.seed_student_cumulative_form
   docker compose exec backend python -m app.scripts.seed_exit_survey_forms
   ```

4. Confirm the backend is healthy at http://localhost:5011/health. User records
   are created at first Google sign-in; no user seed command is needed.

The catalog must be seeded before the four assessment question sets. The exit
forms are request-only and become available to a student after the student
requests each one. The Student Cumulative Form must be submitted before a
student can access Requests. The exit-form seeder adds the Shifting/Transferring
Exit Interview (`OVPAA-SAS-GCO-03B`) and Graduating Students Exit Survey
(`OVPAA-SAS-GCO-03A`).

### Dokploy deployment environments

Initialize each environment separately after its MongoDB service and backend
Application are running. Ensure the backend's `MONGODB_URI` and
`MONGODB_DATABASE` refer to the intended environment's database, and confirm
the backend container can resolve and reach the MongoDB service. Dev, UAT, and
production should use separate databases and credentials. Configure these
values in each Dokploy backend Application's environment settings; never use a
local `.env` file or expose database credentials in Git.

In Dokploy, open the matching **backend Application**, open its Docker Terminal,
and select the running backend container. Run the following commands there;
do not run them in the frontend or MongoDB container:

```sh
python -m app.scripts.seed_tests
python -m app.scripts.seed_beck_questions
python -m app.scripts.seed_dass21_questions
python -m app.scripts.seed_brs_questions
python -m app.scripts.seed_pcl5_questions
python -m app.scripts.seed_student_cumulative_form
python -m app.scripts.seed_exit_survey_forms
```

Repeat the commands in each environment that needs fresh seed data or the
Student Cumulative Form conditional-display repair. Output is
shown in the Docker Terminal. The assessment seeders report 21 questions for
Beck and DASS-21, six for BRS, and 20 for PCL-5. These commands do not clear
existing users, submissions, appointments, or other application data.

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

## Counseling calendar

Students can book counseling from Requests without first submitting a test, or
book one appointment for a submitted Beck, DASS-21, BRS, or PCL-5 assessment by
selecting an empty calendar time. Requests bookings require a student note that
is visible to the student and authorized staff. For assessment bookings, staff
calendar details include the student's name, email, full test name, and a link
to the submitted response; those generated details are not returned to students.
Counselors and administrators see the shared calendar; either role can accept
an unassigned booking. The accepting staff member is recorded separately so
their name and role remain available after a booking is postponed or canceled.
Staff can postpone or cancel an active booking. A postponed assessment can be
booked again; a canceled assessment cannot. Booking times are
stored in UTC. The frontend displays them in Asia/Manila time.

The API provides:

- GET /counseling/appointments?start=<ISO>&end=<ISO>&attempt_id=<UUID> —
  bookings for the student's submitted assessment or the shared staff calendar.
- GET /counseling/appointments?start=<ISO>&end=<ISO>&booking_type=request —
  the requesting student's Requests bookings.
- POST /counseling/appointments — student books a one-hour time using either a
  submitted supported-test `attempt_id` or a required `note` for a Requests
  booking; the two booking inputs are mutually exclusive.
- POST /counseling/appointments/{appointment_id}/claim — a counselor or
  administrator accepts an unassigned booking.
- POST /counseling/appointments/{appointment_id}/postpone and /cancel — staff changes a
  booking state.

FastAPI derives identity and role from the verified Next.js BFF token. Students
only receive their own bookings; unoccupied calendar times can be selected
directly. Staff receives the student and assessment details needed to handle
appointments. Clicking a calendar time opens a confirmation dialog where the
student chooses the start; the end is fixed to exactly one hour later. Requests
bookings also collect a required counseling note. Dragging a range pre-fills the start time. Start times use 30-minute increments between
7:00 AM and 6:00 PM Manila time. MongoDB unique indexes reserve each half-hour block and prevent
overlapping appointments or duplicate active bookings under concurrent requests.

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
environment settings rather than Git. Give UAT its own database credentials and
data. Limit access to UAT at the proxy or application layer
if it should be private; HTTPS alone does not restrict who can sign in.

For a production-ready operational setup, also configure Dokploy restart and
resource limits, retain deployment/runtime logs, and monitor uptime and health.
Add explicit CORS origins when the frontend begins calling this API. Keep
database backups and restore checks in scope once persistent data is introduced.

### Clear test responses

To clear all test drafts and submitted responses for one environment, run this
command in that environment's backend Docker Terminal:

```sh
python -m app.scripts.clear_test_responses
```

The command uses that backend's `MONGODB_URI` and `MONGODB_DATABASE`. It removes
only `test_responses` records, including drafts. Test definitions, questions,
and counseling appointments are left unchanged. Run it separately in each
environment whose test responses you intend to clear; do not run it as part of
normal deployment or startup. It also creates the unique index used to enforce
one submitted response per student and test.

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
  unfinished draft for a supported assessment. `PUT` on the same route saves
  or updates that draft.
- `POST /tests/{test_id}/responses/draft/start` starts or resumes that user's
  active attempt and returns its opaque attempt ID.
- `POST /tests/{test_id}/responses/submit` validates answers for the supported
  BDI, DASS-21, BRS, or PCL-5 questionnaire and calculates scores on the backend. BDI
  returns its total score; DASS-21 returns separate Depression, Anxiety, and
  Stress scores; BRS returns the six-item mean; PCL-5 returns the 20-item total
  and a screening interpretation. The backend reads option scores
  from MongoDB and does not trust a client-provided score.
  Answer and draft endpoints are student-only, and each student may submit once
  per test.
- `GET /tests/{test_id}/responses/me` returns the signed-in user's score and
  interpretation for their submitted assessment without returning item-level
  answers.
- `GET /tests/{test_id}/responses/staff` returns paginated student and
  submission metadata for counselors and admins. Search with `q`, and page with
  `limit` and `skip`; answers are not included in this list.
- `GET /tests/{test_id}/responses/{attempt_id}` returns one submitted answer
  set to its owner or to a counselor/admin reviewing a student's response.
- `PATCH /admin/users/{google_sub}/role` changes a user's role and is restricted
  to admins. Valid roles are `student`, `counselor`, and `admin`; admins cannot
  change their own role.

Test answers and scores are stored in `test_responses`. A student can save and
resume their own draft and see their result after submission; only counselors
and admins can retrieve submitted item-level answers. A student may submit only
once per test. The BDI category thresholds follow the interpretation
table in the supplied Beck PDF: 1–10, 11–16, 17–20,
21–30, 31–40, and over 40. The minimum possible score (0) is grouped with the
lowest band. The displayed category is screening feedback, not a diagnosis.

The DASS-21 result reports Depression, Anxiety, and Stress scale sums doubled
to the DASS-42-equivalent range, with each scale interpreted using its own
severity bands from the supplied PDF. It does not produce a combined total.
The BRS result is the mean of the six scored items, rounded to two decimals,
with the supplied PDF's Low Resilience (1.00–2.99), Normal Resilience
(3.00–4.30), and High Resilience (4.31–5.00) bands.
The PCL-5 total ranges from 0 to 80. Its interpretation notes that a screening
cutoff in the 31–33 range is commonly used, while emphasizing that cutoff choice
depends on the population and purpose. This range follows the [VA National
Center for PTSD scoring guide](https://www.ptsd.va.gov/professional/assessment/documents/using-PCL5.pdf).
The result is not a diagnosis.
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
