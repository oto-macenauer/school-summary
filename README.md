# Bakalari Dashboard

Standalone web dashboard for the Bakalari school information system. Aggregates timetables, grades, messages, and AI-generated summaries into a single page.

## Features

- **Timetable** — weekly schedule with subjects, teachers, rooms, and changes
- **Marks** — grades with per-subject and overall averages
- **Komens** — school messages saved locally as Markdown files
- **AI Summary** — Gemini-powered weekly summaries (last/current/next week) with Google Drive report integration
- **Preparation** — AI-generated daily briefs for today and tomorrow
- **Admin** — read-only view of scheduler status, categorized logs, config, and Gemini usage

## Architecture

```
backend/           FastAPI REST API (Python 3.12)
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
```

## Prerequisites

- Python 3.11+
- Node.js 18+
- A Bakalari school account
- (Optional) Gemini API key for AI features
- (Optional) Google Drive service account for weekly reports

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/your-org/school-summary.git
cd school-summary
```

### 2. Backend setup

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
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

### Backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
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

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`

The `app_data/` directory is mounted as a volume for persistent config and storage.

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Health check, auth status per student |
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
pytest tests/ -v

# Run specific module tests
pytest tests/test_auth.py -v

# Run with coverage
pytest tests/ -v --cov=app --cov-report=html
```

191 tests covering auth, timetable, marks, komens, storage, gdrive, gemini, summary, prepare, cache, log manager, and config.

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
