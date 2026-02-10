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
    storage/           # Markdown file persistence
      komens_storage.py
      gdrive_storage.py
    services/          # Application services
      student_manager.py  # Per-student state management
      scheduler.py        # Background task scheduler with status tracking
      cache.py            # TTL-based in-memory cache
      log_manager.py      # Ring buffer logger with categories
    api/               # FastAPI routers
      auth.py, timetable.py, marks.py, komens.py,
      summary.py, prepare.py, dashboard.py, admin.py
    models/config.py   # Pydantic config models
    config.py          # YAML config loader with prompt templates
    dependencies.py    # FastAPI dependency injection
    main.py            # App entry point with lifespan events
  tests/               # 191 unit tests with fixtures

frontend/              # Vue 3 + TypeScript + Vite
  src/
    components/        # Layout, UI primitives, dashboard widgets
    views/             # Dashboard, Timetable, Marks, Komens, Admin
    stores/            # Pinia state management
    api/client.ts      # Typed HTTP client
    styles/            # Liquid glass design system
```

## Configuration

YAML-based config at `app_data/config.yaml` (auto-generated on first startup):
- `base_url`: School's Bakalari URL
- `students`: List of student configs with name, username, password
- `gemini_api_key`: Optional, enables AI summaries
- `gdrive`: Google Drive service account config for weekly reports
- `update_intervals`: Per-module refresh intervals in seconds
- `prompts`: Editable AI prompt templates using `{variable}` syntax

## Build Commands

```bash
# Run all backend tests
cd backend && pytest tests/ -v

# Run specific test file
cd backend && pytest tests/test_auth.py -v

# Run specific test
cd backend && pytest tests/test_auth.py -v -k "test_login_success"

# Run with coverage
cd backend && pytest tests/ -v --cov=app --cov-report=html

# Start backend dev server
cd backend && uvicorn app.main:app --reload --port 8000

# Start frontend dev server
cd frontend && npm run dev

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
  test_cache.py            # In-memory cache tests
  test_log_manager.py      # Log manager tests
  test_config.py           # YAML config loader tests
  fixtures/                # Sample API response JSON files
    login_response.json
    timetable_response.json
    marks_response.json
    komens_response.json
```

### Coverage Requirements

- All public functions must have test coverage
- Edge cases: invalid credentials, expired tokens, network errors, malformed responses
- Token refresh flow must be tested
- Each module's data parsing must be tested with fixture data
