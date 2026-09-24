# Školní přehled

School overview dashboard integrating multiple school systems — Bakalari, Strava.cz canteen, and more. Aggregates timetables, grades, messages, canteen menus, and AI-generated summaries into a single page.

## Features

- **Timetable** — weekly schedule with subjects, teachers, rooms, and changes
- **Marks** — grades with per-subject and overall averages
- **Komens** — school messages saved locally as Markdown files
- **Canteen** — daily menu from Strava.cz with allergen info
- **AI Summary** — Gemini-powered weekly summaries (last/current/next week) with Google Drive report integration
- **Preparation** — AI-generated daily briefs for today and tomorrow
- **Admin** — read-only view of scheduler status, categorized logs, config, and Gemini usage

## Architecture

```
backend/           FastAPI REST API (Python 3.14)
  app/
    core/          Auth, API client, Gemini, Google Drive
    modules/       Timetable, marks, komens, summary, prepare
    storage/       Markdown file persistence (komens, gdrive reports)
    services/      Student manager, scheduler, cache, log manager
    api/           FastAPI routers (8 endpoint groups)
    models/        Pydantic config models
    config.py      YAML config loader with prompt templates
    main.py        App entry point with lifespan events
  tests/           191 unit tests with fixtures

frontend/          Vue 3 + TypeScript + Vite
  src/
    components/    Layout, UI primitives, dashboard widgets
    views/         Dashboard, Timetable, Marks, Komens, Admin
    stores/        Pinia state management
    api/           Typed HTTP client
    styles/        Liquid glass design system

docker-compose.yml
Makefile           Common dev tasks (install, test, lint, build, docker)
```

## Prerequisites

- Python 3.14+ and [uv](https://docs.astral.sh/uv/) (uv can install Python itself)
- Node.js 24 LTS+ (see `frontend/.nvmrc`)
- (Optional) GNU make — the root `Makefile` wraps every common task; run `make help`
- A Bakalari school account (for timetable, marks, messages)
- (Optional) Gemini API key for AI features
- (Optional) Google Drive service account for weekly reports

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/school-summary.git
cd school-summary
```

### 2. Backend setup

Dependencies are managed with [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`):

```bash
cd backend
uv sync          # creates .venv and installs runtime + dev dependencies
```

Run commands through `uv run` — no manual activation needed:

```bash
uv run pytest
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install
```

### 4. Configuration

On first startup the backend generates a default `app_data/config.yaml`. You can also create it manually:

```bash
mkdir app_data
```

Create `app_data/config.yaml`:

```yaml
base_url: "https://bakalari.your-school.cz"

students:
  - name: "Filip"
    username: "your_username"
    password: "your_password"
    extra_subjects:             # optional, shown in timetable view
      - name: "Angličtina kroužek"
        time: "14:00"
        days: ["po", "st"]     # po/ut/st/ct/pa
      - name: "Fotbal"
        time: "15:30"
        days: ["ut", "ct"]

gemini_api_key: ""  # optional, enables AI summaries

gdrive:
  service_account_path: ""   # path to service account JSON
  reports_folder_id: ""      # Google Drive folder ID
  school_year_start: ""      # e.g. "2025-09-01"

update_intervals:
  timetable: 3600   # seconds
  marks: 1800
  komens: 900
  summary: 86400
  prepare: 3600
```

Prompt templates are also configurable in the same file under a `prompts:` key. See the generated default config for all available templates and variables.

### Finding your school's Bakalari URL

Go to your school's Bakalari web login page. The URL before `/login` is your base URL.
Example: if login is at `https://bakalari.zszb.cz/login`, use `https://bakalari.zszb.cz`.

## Running locally (development)

With GNU make, `make dev-backend` and `make dev-frontend` start the two servers
(`make help` lists all tasks). The equivalent raw commands:

### Backend

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

The frontend runs at `http://localhost:5173` and proxies `/api` requests to the backend (configured in `vite.config.ts`).

## Running with Docker

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000` (override with `FRONTEND_PORT`)
- Backend API: `http://localhost:8000` (override with `BACKEND_PORT`)

Deployment-specific values go in a `.env` file next to `docker-compose.yml`
(git-ignored, so `git pull` never conflicts). Copy `.env.example` and adjust:
ports, `PATH_TO_APPDATA`, `APP_UID`/`APP_GID` and `DNS_PRIMARY`/`DNS_SECONDARY`.

`${PATH_TO_APPDATA}/school-summary` is mounted as `app_data/` for persistent config and storage.

### Hardening

Both containers run as non-root users on a read-only root filesystem, with
all Linux capabilities dropped, `no-new-privileges`, an init process, and
pid/memory limits. The frontend uses `nginx-unprivileged` (port 8080 inside
the container) and sends a Content-Security-Policy and other security headers.

The backend runs as uid:gid `10001:10001` by default, and **the mounted
`app_data` directory must be writable by that user**. When upgrading an
existing install whose data is owned by root, either:

```bash
sudo chown -R 10001:10001 "${PATH_TO_APPDATA}/school-summary"
```

or run as the directory's current owner, e.g. `APP_UID=99 APP_GID=100` on Unraid.

### Health checks and monitoring

| URL | Meaning | Use for |
|-----|---------|---------|
| `http://<host>:3000/healthz` | nginx is serving | Frontend container health, Uptime Kuma HTTP monitor |
| `http://<host>:8000/api/health` | Backend process is up (never touches Bakalari) | Backend container health, Uptime Kuma HTTP monitor |
| `http://<host>:8000/api/ready` | 200 only when every student is logged in to Bakalari; 503 otherwise (`starting`, `unconfigured`, `degraded`) | Uptime Kuma: alerts on bad credentials or a school server outage |

The API endpoints are also reachable through the frontend (`:3000/api/...`).
All three accept `GET` and `HEAD`. Uptime Kuma's **Docker Container** monitor
also works, because both images define a `HEALTHCHECK` and the containers have
fixed names (`school-summary-backend`, `school-summary-frontend`).

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/health` | Liveness probe |
| `GET /api/ready` | Readiness probe (503 unless all students are authenticated) |
| `GET /api/status` | Auth and last-update status per student |
| `GET /api/students/{name}/dashboard` | All widget data in one call |
| `GET /api/students/{name}/timetable` | Weekly timetable |
| `GET /api/students/{name}/marks` | Grades with averages |
| `GET /api/students/{name}/komens` | Messages |
| `GET /api/students/{name}/summary?period=current` | AI weekly summary |
| `GET /api/students/{name}/prepare/today` | Today preparation |
| `GET /api/students/{name}/prepare/tomorrow` | Tomorrow preparation |
| `GET /api/admin/logs` | Filterable log entries |
| `GET /api/admin/scheduler` | Task statuses |
| `GET /api/config` | Current config (passwords masked) |
| `POST /api/config/reload` | Reload config from YAML |
| `GET /api/admin/gemini-usage` | Gemini API usage stats |

## Testing

```bash
cd backend

# Run all tests
uv run pytest -v

# Run specific module tests
uv run pytest tests/test_auth.py -v

# Run with coverage
uv run pytest -v --cov=app --cov-report=html

# Lint
uv run ruff check .
```

Or from the repository root: `make test`, `make coverage`, `make lint`.

The suite covers auth, timetable, marks, komens, storage, gdrive, gemini, summary,
prepare, canteen, cache, log manager, scheduler, and config.

## Troubleshooting

### "Failed to connect to Bakalari server"
- Verify the `base_url` in `config.yaml` is correct and accessible
- Ensure the URL does not have a trailing slash

### "Invalid username or password"
- Verify credentials work on the Bakalari web login
- Some schools use student ID as the username

### AI summaries not generating
- Ensure `gemini_api_key` is set in `config.yaml`
- Check the admin logs at `/api/admin/logs?category=gemini`

## License

MIT
