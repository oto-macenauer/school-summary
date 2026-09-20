# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Standalone web dashboard for the Bakalari school information system. FastAPI backend with Vue 3 frontend, deployed via Docker Compose. Supports multiple students with separate credentials.

## API Reference

- **Documentation**: https://github.com/bakalari-api/bakalari-api-v3/
- **Endpoints reference**: https://github.com/bakalari-api/bakalari-api-v3/blob/master/endpoints.md

### Authentication

```
POST /api/login
Content-Type: application/x-www-form-urlencoded

Body (initial login):
  client_id=ANDR
  grant_type=password
  username=USERNAME
  password=PASSWORD

Body (token refresh):
  client_id=ANDR
  grant_type=refresh_token
  refresh_token=REFRESHTOKEN

Response:
{
  "access_token": "...",
  "refresh_token": "...",
  "expires_in": 3599,
  "token_type": "Bearer"
}
```

All authenticated requests require header: `Authorization: Bearer ACCESS_TOKEN`

### Key Bakalari Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/3/timetable/actual?date=YYYY-MM-dd` | GET | Weekly timetable for specific date |
| `/api/3/timetable/permanent` | GET | Permanent/base timetable |
| `/api/3/marks` | GET | All marks with subject averages |
| `/api/3/marks/final` | GET | Final/semester marks |
| `/api/3/komens/messages/received` | POST | Received messages |
| `/api/3/komens/messages/noticeboard` | POST | Noticeboard messages |

## Architecture

```
backend/
  app/
    core/              # Auth, API client, Gemini, Google Drive
      auth.py          # Token-based Bakalari auth with refresh
      client.py        # HTTP client with auto-retry on 401
      gemini.py        # Gemini AI client with usage tracking
      gdrive.py        # Google Drive client for weekly reports
    modules/           # Data fetching and parsing
      timetable.py     # Weekly schedule
      marks.py         # Grades with averages
      komens.py        # Messages with HTML-to-text
      summary.py       # AI weekly summary with prompt templates
      prepare.py       # Today/tomorrow preparation
      canteen.py       # School canteen menu (Strava.cz API, external)
      tagging.py       # AI tagging + calendar/task extraction (one Gemini call)
      agenda.py        # Calendar events & checklist tasks: models + parsing
    storage/           # Markdown file persistence
      komens_storage.py
      gdrive_storage.py
      tag_storage.py      # Tags in markdown frontmatter (+ schema version)
      agenda_storage.py   # YAML: events.yaml, tasks.yaml, state.yaml
    services/          # Application services
      student_manager.py  # Per-student state + shared canteen state
      scheduler.py        # Background task scheduler with status tracking
      cache.py            # TTL-based in-memory cache
      log_manager.py      # Ring buffer logger with categories
    api/               # FastAPI routers
      auth.py, timetable.py, marks.py, komens.py, canteen.py,
      summary.py, prepare.py, dashboard.py, admin.py,
      resources.py, agenda.py
    models/config.py   # Pydantic config models
    config.py          # YAML config loader with prompt templates
    dependencies.py    # FastAPI dependency injection
    main.py            # App entry point with lifespan events
  tests/               # ~300 unit tests with fixtures

frontend/              # Vue 3 + TypeScript + Vite
  src/
    components/        # Layout, UI primitives, dashboard widgets
    views/             # Dashboard, Timetable, Marks, Resources, Calendar,
                       # Checklist, Canteen, Prompt, Admin
    stores/            # Pinia state management
    api/client.ts      # Typed HTTP client
    types/index.ts     # TypeScript interfaces for all API responses
    styles/            # Liquid glass design system (CSS custom properties)
```

### Key Architectural Patterns

- **Modules** (`backend/app/modules/`): Dataclasses with `from_api_response()` classmethod + `to_dict()`/`to_summary_dict()` serialization. Module class takes a client/session, exposes async `get_*()` methods.
- **API routers** (`backend/app/api/`): Thin — get student context via `get_student_or_404(name)`, return cached data or fetch fresh.
- **Per-student vs shared**: Most modules are per-student (on `StudentContext`). Canteen is school-wide (on `StudentManager`), scheduled once globally.
- **Scheduler**: `_schedule_task()` creates periodic async tasks per student. Canteen uses separate `_schedule_canteen_task()` for its global task.
- **Agenda extraction**: the `tagging` task sends each stored message to Gemini once and gets tags + calendar events + checklist tasks back. Records are keyed by source (`komens-1234-e0`), so re-extracting a message replaces only its own records; done/dismissed state lives in `state.yaml` and survives. `TAG_SCHEMA_VERSION` in `modules/tagging.py` marks processed files — bump it to re-extract, and `agenda.backfill_days` bounds how much history that costs.
- **Frontend views**: `<script setup lang="ts">` composition API, fetch on `onMounted` + `watch(() => store.current)`, use `GlassCard` component and CSS custom properties from the design system.

## Configuration

YAML-based config at `app_data/config.yaml` (auto-generated on first startup):
- `base_url`: School's Bakalari URL
- `students`: List of student configs with name, username, password
- `gemini_api_key`: Optional, enables AI summaries
- `gdrive`: Google Drive service account config for weekly reports
- `canteen`: Strava.cz canteen config (`cislo`, `s5url`, `lang`) — optional, enables canteen menu
- `agenda`: calendar/checklist windows, backfill depth, day-before push digest
- `update_intervals`: Per-module refresh intervals in seconds
- `prompts`: Editable AI prompt templates using `{variable}` syntax

## Build Commands

Backend dependencies are managed with **uv** (`backend/pyproject.toml` + `backend/uv.lock`).
Common tasks live in the root `Makefile` (needs GNU make; `make help` lists everything):

```bash
make install          # uv sync + npm install
make test             # backend pytest + frontend vitest
make test-backend
make coverage         # pytest with HTML coverage report
make lint             # ruff (backend) + vue-tsc (frontend)
make dev-backend      # uvicorn with reload on :8000
make dev-frontend     # vite dev server
make build            # frontend production bundle
make docker-up        # docker compose up -d --build
```

This is a Windows environment; without GNU make run the underlying commands directly:

```powershell
# Run all backend tests
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run pytest -v"

# Run specific test file
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run pytest tests\test_auth.py -v"

# Run specific test
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run pytest tests\test_auth.py -v -k 'test_login_success'"

# Run with coverage
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run pytest -v --cov=app --cov-report=html"

# Lint backend
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run ruff check ."

# Add or update a dependency (rewrites pyproject.toml and uv.lock)
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv add httpx"

# Type-check frontend
powershell.exe -Command "cd c:\Projects\school-summary\frontend; npx vue-tsc --noEmit"

# Build frontend
powershell.exe -Command "cd c:\Projects\school-summary\frontend; npm run build"

# Start backend dev server
powershell.exe -Command "cd c:\Projects\school-summary\backend; uv run uvicorn app.main:app --reload --port 8000"

# Start frontend dev server
powershell.exe -Command "cd c:\Projects\school-summary\frontend; npm run dev"

# Docker
docker compose up --build
```

## Testing

Every module and functionality must have unit test coverage. Tests are in `backend/tests/`.

### Test Structure

```
backend/tests/
  conftest.py              # Shared fixtures (mock responses, test credentials)
  test_auth.py             # Authentication tests
  test_timetable.py        # Timetable module tests
  test_marks.py            # Marks module tests
  test_komens.py           # Komens module tests
  test_komens_storage.py   # MD file storage tests
  test_gdrive.py           # Google Drive client tests
  test_gemini.py           # Gemini AI client tests
  test_summary.py          # Weekly summary tests
  test_prepare.py          # Today/tomorrow preparation tests
  test_canteen.py          # Canteen module tests
  test_agenda.py           # Event/task parsing, sorting, windows
  test_agenda_storage.py   # Agenda YAML storage + user state overlay
  test_agenda_api.py       # Calendar/checklist endpoints (FastAPI TestClient)
  test_agenda_extraction.py # AI extraction, schema versioning, push digest
  test_cache.py            # In-memory cache tests
  test_log_manager.py      # Log manager tests
  test_config.py           # YAML config loader tests
  test_scheduler.py        # Scheduler lifecycle tests
  test_prompt_variables.py # Prompt variable resolution tests
  fixtures/                # Sample API response JSON files
    login_response.json
    timetable_response.json
    marks_response.json
    komens_response.json
    canteen_response.json
```

### Coverage Requirements

- All public functions must have test coverage
- Edge cases: invalid credentials, expired tokens, network errors, malformed responses
- Token refresh flow must be tested
- Each module's data parsing must be tested with fixture data
