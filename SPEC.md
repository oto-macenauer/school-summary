# Bakalari Standalone Application - Implementation Specification

## 1. Overview

Transform the existing Home Assistant integration into a standalone containerized application with a FastAPI backend and Vue.js frontend. The app provides a widget-rich dashboard for students to quickly get context for the school day.

### Goals
- Remove all Home Assistant dependencies
- FastAPI REST API backend
- Vue 3 frontend with liquid glass minimalistic design
- Docker-first deployment (all persistent data in mounted `app_data/` volume)
- Preserve all existing business logic (auth, timetable, marks, komens, summaries, preparation, Google Drive)
- Comprehensive test coverage

---

## 2. Architecture

```
bakalari-app/
├── backend/                          # FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                   # FastAPI app entry point
│   │   ├── config.py                 # Configuration loader (YAML)
│   │   ├── dependencies.py           # FastAPI dependency injection
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py               # Auth endpoints
│   │   │   ├── timetable.py          # Timetable endpoints
│   │   │   ├── marks.py              # Marks endpoints
│   │   │   ├── komens.py             # Komens endpoints
│   │   │   ├── summary.py            # AI summary endpoints
│   │   │   ├── prepare.py            # Preparation endpoints
│   │   │   ├── dashboard.py          # Aggregated dashboard endpoint
│   │   │   ├── admin.py              # Read-only admin endpoints (logs, scheduler status)
│   │   │   └── config_api.py         # Read-only configuration endpoints
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── client.py             # Bakalari API client (from existing)
│   │   │   ├── auth.py               # Bakalari auth handler (from existing)
│   │   │   ├── gemini.py             # Gemini AI client (from existing)
│   │   │   └── gdrive.py            # Google Drive client (from existing)
│   │   ├── modules/
│   │   │   ├── __init__.py
│   │   │   ├── timetable.py          # Timetable logic (from existing)
│   │   │   ├── marks.py              # Marks logic (from existing)
│   │   │   ├── komens.py             # Komens logic (from existing)
│   │   │   ├── summary.py            # Summary generation (from existing)
│   │   │   └── prepare.py            # Preparation generation (from existing)
│   │   ├── storage/
│   │   │   ├── __init__.py
│   │   │   ├── komens_storage.py     # MD file storage for messages (from existing)
│   │   │   └── gdrive_storage.py     # MD file storage for weekly GDrive reports
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── student_manager.py    # Manages per-student clients and state
│   │   │   ├── scheduler.py          # Background task scheduler (replaces coordinators)
│   │   │   ├── cache.py              # In-memory cache for marks and other data
│   │   │   └── log_manager.py        # Categorized in-memory log ring buffer
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── config.py             # Pydantic models for configuration
│   │       ├── timetable.py          # Timetable response models
│   │       ├── marks.py              # Marks response models
│   │       ├── komens.py             # Komens response models
│   │       ├── summary.py            # Summary response models
│   │       ├── admin.py              # Admin/logs response models
│   │       └── dashboard.py          # Dashboard aggregated models
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_auth.py
│   │   ├── test_client.py
│   │   ├── test_timetable.py
│   │   ├── test_marks.py
│   │   ├── test_komens.py
│   │   ├── test_komens_storage.py
│   │   ├── test_summary.py
│   │   ├── test_prepare.py
│   │   ├── test_gdrive.py
│   │   ├── test_gemini.py
│   │   ├── test_scheduler.py
│   │   ├── test_cache.py
│   │   ├── test_config.py
│   │   ├── test_gdrive_storage.py
│   │   ├── test_log_manager.py
│   │   ├── test_admin_api.py
│   │   ├── test_dashboard_api.py
│   │   └── fixtures/                 # Reuse existing fixture JSONs
│   │       ├── login_response.json
│   │       ├── timetable_response.json
│   │       ├── marks_response.json
│   │       └── komens_response.json
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/                         # Vue 3 application
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── router/
│   │   │   └── index.ts
│   │   ├── stores/
│   │   │   ├── dashboard.ts          # Pinia store for dashboard data
│   │   │   ├── student.ts            # Current student selection
│   │   │   └── config.ts             # App configuration
│   │   ├── api/
│   │   │   └── client.ts             # Axios API client
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── AppHeader.vue     # Top bar with student selector
│   │   │   │   └── AppLayout.vue     # Main layout wrapper
│   │   │   ├── widgets/
│   │   │   │   ├── TimetableWidget.vue
│   │   │   │   ├── SummaryWidget.vue
│   │   │   │   ├── KomensWidget.vue
│   │   │   │   ├── MarksWidget.vue
│   │   │   │   └── PrepareWidget.vue
│   │   │   └── ui/
│   │   │       ├── GlassCard.vue     # Reusable liquid glass card
│   │   │       ├── GlassButton.vue
│   │   │       └── LoadingSpinner.vue
│   │   ├── views/
│   │   │   ├── DashboardView.vue     # Main widget dashboard
│   │   │   ├── TimetableView.vue     # Full timetable page
│   │   │   ├── MarksView.vue         # Detailed marks page
│   │   │   ├── KomensView.vue        # Messages list/detail page
│   │   │   └── AdminView.vue         # Read-only admin (logs, scheduler, config)
│   │   ├── styles/
│   │   │   ├── main.css              # Global styles
│   │   │   └── glass.css             # Liquid glass design system
│   │   └── types/
│   │       └── index.ts              # TypeScript type definitions
│   ├── public/
│   │   └── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── Dockerfile
├── app_data/                         # Mounted volume (persistent storage)
│   ├── config.yaml                   # Application configuration (YAML)
│   ├── komens/                       # Message MD files per student
│   │   └── {student_name}/
│   │       └── *.md
│   └── gdrive/                       # Weekly reports as MD files per student
│       └── {student_name}/
│           └── week_NN.md            # e.g. week_23.md
├── docker-compose.yml
├── .dockerignore
├── .gitignore
└── README.md
```

---

## 3. Backend Details

### 3.1 Configuration (`app/config.py`)

Configuration stored as YAML in `app_data/config.yaml`. The file is the single source of truth — all configuration is done by editing this file directly (the admin UI is read-only).

```yaml
base_url: "https://bakalari.school.cz"

students:
  - name: "Student Name"
    username: "username"
    password: "password"

gemini_api_key: "..."

gdrive:
  service_account_path: "app_data/gdrive_service_account.json"
  reports_folder_id: "..."
  school_year_start: "2025-09-01"

update_intervals:
  timetable: 3600    # seconds
  marks: 1800
  komens: 900
  summary: 86400
  prepare: 3600

# ──────────────────────────────────────────────
# Prompt Templates
# ──────────────────────────────────────────────
# All AI prompts are defined here as templates.
# Available variables are listed in comments above each template.
# Templates use Python str.format() / format_map() syntax: {variable_name}
#
# To customize AI behavior, edit the templates below directly.
# No separate "custom prompt" field — the template IS the prompt.

prompts:
  # ── Weekly Summary Prompt ──
  # Sent to Gemini to generate last/current/next week summary.
  # GDrive weekly reports are included as part of the context.
  #
  # Variables:
  #   {week_type}        - "minulý týden" / "tento týden" / "příští týden"
  #   {date_from}        - week start date (DD.MM.YYYY)
  #   {date_to}          - week end date (DD.MM.YYYY)
  #   {messages}         - formatted komens messages from the period
  #   {timetable}        - formatted timetable for the week
  #   {marks}            - new marks received during the period
  #   {gdrive_report}    - weekly report text from Google Drive (if available)
  summary: |
    Jsi školní asistent. Shrň hlavní události za {week_type} ({date_from} – {date_to}).

    Zprávy z Komensu:
    {messages}

    Rozvrh:
    {timetable}

    Nové známky:
    {marks}

    Týdenní report z Google Drive:
    {gdrive_report}

    Vytvoř stručné shrnutí v češtině. Zaměř se na důležité události,
    testy, úkoly a změny v rozvrhu.

  # ── Weekly Summary System Instruction ──
  summary_system: |
    Jsi školní asistent pro českého studenta. Odpovídej vždy česky.
    Buď stručný a věcný. Zaměř se na praktické informace.

  # ── Today Preparation Prompt ──
  # Variables:
  #   {target_date}      - target date (DD.MM.YYYY)
  #   {day_name}         - Czech day name (e.g. "pondělí")
  #   {lessons}          - formatted lessons for the target day
  #   {messages}         - recent relevant komens messages (last 14 days)
  prepare_today: |
    Jsi školní asistent. Připrav přehled pro dnešní den {day_name} {target_date}.

    Dnešní rozvrh:
    {lessons}

    Nedávné zprávy (posledních 14 dní):
    {messages}

    Shrň co je dnes důležité: jaké jsou hodiny, jestli jsou testy,
    co je potřeba mít s sebou, na co nezapomenout.

  # ── Tomorrow Preparation Prompt ──
  # Same variables as prepare_today.
  prepare_tomorrow: |
    Jsi školní asistent. Připrav přehled na zítřek {day_name} {target_date}.

    Zítřejší rozvrh:
    {lessons}

    Nedávné zprávy (posledních 14 dní):
    {messages}

    Shrň co je potřeba připravit na zítra: jaké budou hodiny,
    jestli jsou testy, co zabalit, co se naučit, na co nezapomenout.

  # ── Preparation System Instruction ──
  prepare_system: |
    Jsi školní asistent pro českého studenta. Odpovídej vždy česky.
    Buď stručný a praktický. Zaměř se na to, co student potřebuje vědět a připravit.
```

- Loaded at startup with Pydantic validation
- **Read-only from the app's perspective** — users edit the YAML file directly (or via mounted volume)
- The app watches for file changes and reloads config automatically (file watcher via `watchfiles`)
- Environment variable `APP_DATA_DIR` overrides default `./app_data` path
- On first startup, if `config.yaml` doesn't exist, a default template is generated with comments

### 3.2 Core Modules (Ported from Existing)

Port the following with minimal changes — remove HA imports, use standard `aiohttp`:

| Existing File | New Location | Changes |
|---|---|---|
| `api/auth.py` | `core/auth.py` | Remove HA logging, use stdlib logging |
| `api/client.py` | `core/client.py` | Same |
| `api/gemini.py` | `core/gemini.py` | Same |
| `api/gdrive.py` | `core/gdrive.py` | Same |
| `modules/timetable.py` | `modules/timetable.py` | Same |
| `modules/marks.py` | `modules/marks.py` | Same |
| `modules/komens.py` | `modules/komens.py` | Same |
| `modules/summary.py` | `modules/summary.py` | Use prompt templates from config; reads GDrive report from stored MD file and injects as `{gdrive_report}` variable |
| `modules/prepare.py` | `modules/prepare.py` | Split into today + tomorrow; use prompt templates from config |
| `storage/komens_storage.py` | `storage/komens_storage.py` | Same |
| *(new)* | `storage/gdrive_storage.py` | Converts GDrive documents (Google Docs / DOCX) to MD files and stores them in `app_data/gdrive/{student}/` |

### 3.3 GDrive Storage (`storage/gdrive_storage.py`)

Fetches weekly reports from Google Drive and persists them as Markdown files, analogous to how `komens_storage.py` handles messages.

```python
class GDriveStorage:
    """Downloads and converts Google Drive weekly reports to MD files."""

    # Storage path: app_data/gdrive/{student_name}/week_NN.md

    async def save_report(week_number: int, report: WeeklyReport) -> Path
    def get_report(week_number: int) -> Optional[str]
    def get_latest_report() -> Optional[str]
    def report_exists(week_number: int) -> bool
    def get_all_reports() -> list[Path]
```

**MD file format** (e.g., `week_23.md`):

```markdown
---
week_number: 23
school_year: 2025/2026
fetched_at: "2026-02-10T14:30:00"
source_file: "Week 23 Report.docx"
---

# ENGLISH

Well, with the week over, we have a few things to be proud of!

We have gone over vocabulary about the school, namely the school subjects...

## HOMEWORK

Book reports, of course!
Studying for the Spelling Bee, of course!
Monday's words are:
1) Of course, 2) Comical, 3) Myth, ...

## PROJECT BASED LEARNING

The flyer!
...

## NEXT WEEK PLAN

The television! The film!
...
```

**Conversion logic:**
- Google Docs → exported as plain text via Drive API, then converted to MD
- DOCX → text extracted (existing logic in `gdrive.py`), then converted to MD
- Section headers (all-caps lines like `ENGLISH`, `HOMEWORK`, `NEXT WEEK PLAN`) → `## Header`
- The document is stored with YAML frontmatter (week number, school year, fetch timestamp, source filename)
- Reports are only re-fetched if the file doesn't exist or if forced via scheduler
- The summary module reads the stored MD file content and injects it as the `{gdrive_report}` template variable

### 3.4 Student Manager (`services/student_manager.py`)

Replaces the HA coordinator pattern. Manages per-student state:

```python
class StudentManager:
    """Manages API clients and cached data for all configured students."""

    # Per student:
    # - BakalariAuth instance
    # - BakalariClient instance
    # - Cached data (timetable, marks, komens, summary[last/current/next], prepare[today/tomorrow])
    # - Last update timestamps

    async def initialize(config: AppConfig) -> None
    async def get_student(name: str) -> StudentContext
    async def refresh_student_data(name: str, module: str) -> None
    async def refresh_all() -> None
    async def shutdown() -> None
```

### 3.4 Background Scheduler (`services/scheduler.py`)

Uses `asyncio` tasks to periodically refresh data (replaces HA DataUpdateCoordinator):

```python
class BackgroundScheduler:
    """Schedules periodic data refresh for all students."""

    async def start() -> None    # Start all periodic tasks
    async def stop() -> None     # Cancel all tasks
    # Respects update_intervals from config
    # Triggers summary refresh when komens updates
    # Triggers prepare refresh when timetable/komens updates
```

### 3.5 In-Memory Cache (`services/cache.py`)

Simple TTL-based cache for marks and other data:

```python
class DataCache:
    """In-memory cache with TTL support."""

    def get(key: str) -> Optional[Any]
    def set(key: str, value: Any, ttl: int) -> None
    def invalidate(key: str) -> None
    def clear() -> None
```

### 3.6 API Endpoints

#### Auth
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/status` | App health + auth status per student |

#### Timetable
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/timetable` | Current week timetable |
| GET | `/api/students/{name}/timetable?date=YYYY-MM-DD` | Specific week timetable |

#### Marks
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/marks` | All marks with averages |
| GET | `/api/students/{name}/marks/new` | New/unread marks count |

#### Komens
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/komens` | All messages |
| GET | `/api/students/{name}/komens/unread` | Unread count |

#### AI Summary
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/summary?period=current` | Weekly summary (last/current/next) |

#### Preparation
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/prepare/today` | Today's preparation |
| GET | `/api/students/{name}/prepare/tomorrow` | Tomorrow's preparation |

#### Dashboard (Aggregated)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/students/{name}/dashboard` | All widget data in one call |

Response includes: today's timetable, current week summary (with GDrive report embedded), unread komens count, recent komens, marks overview, today's preparation, tomorrow's preparation.

#### Configuration (Read-Only)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/config` | Current configuration (passwords masked) |
| POST | `/api/config/test-connection` | Test Bakalari credentials |
| POST | `/api/config/reload` | Force reload config from YAML file |

Configuration is edited by modifying `app_data/config.yaml` directly. The app watches the file for changes and reloads automatically. The `/reload` endpoint triggers an immediate reload.

#### Admin
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/admin/logs` | Recent log entries (filterable by category) |
| GET | `/api/admin/logs?category=auth` | Logs filtered by category |
| GET | `/api/admin/scheduler` | Scheduler status (all tasks, last run, next run) |
| GET | `/api/admin/scheduler/{task_name}` | Single task detail with recent history |

### 3.7 Log Manager (`services/log_manager.py`)

Categorized in-memory log ring buffer that captures application events and makes them available via the admin API.

```python
class LogCategory(str, Enum):
    AUTH = "auth"              # Login, token refresh, auth errors
    TIMETABLE = "timetable"   # Timetable fetches and parsing
    MARKS = "marks"           # Marks fetches and parsing
    KOMENS = "komens"         # Message fetches and storage
    SUMMARY = "summary"       # AI summary generation
    PREPARE = "prepare"       # AI preparation generation
    GDRIVE = "gdrive"         # Google Drive fetches
    GEMINI = "gemini"         # Gemini API calls and usage
    SCHEDULER = "scheduler"   # Background task scheduling
    CONFIG = "config"         # Configuration loading and reloading
    SYSTEM = "system"         # App startup, shutdown, errors

class LogEntry:
    timestamp: datetime
    category: LogCategory
    level: str               # INFO, WARNING, ERROR
    message: str
    student: Optional[str]   # Which student context (if applicable)
    details: Optional[dict]  # Extra structured data (e.g., response time, status code)

class LogManager:
    """Thread-safe ring buffer for log entries."""

    MAX_ENTRIES = 2000       # Keep last 2000 entries in memory

    def log(category, level, message, student=None, details=None) -> None
    def get_logs(category=None, level=None, student=None, limit=100, offset=0) -> list[LogEntry]
    def get_categories() -> list[LogCategory]
    def clear() -> None
```

- Implemented as a custom `logging.Handler` so all stdlib `logging` calls are captured
- Each module logs to its own category via named loggers (e.g., `logging.getLogger("bakalari.auth")`)
- Logs are also written to stdout for container log collection
- No file persistence — logs reset on container restart (by design)

### 3.8 Scheduler Status Tracking

The scheduler tracks execution metadata for each task:

```python
class TaskStatus:
    task_name: str           # e.g., "timetable_refresh"
    student: str             # Which student
    interval_seconds: int    # Configured interval
    last_run: Optional[datetime]
    last_duration_ms: Optional[int]
    last_status: str         # "success", "error", "skipped"
    last_error: Optional[str]
    next_run: Optional[datetime]
    run_count: int
    error_count: int
```

Available via `GET /api/admin/scheduler` as a list of all task statuses.

### 3.9 Backend Dependencies

```
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0
pyyaml>=6.0
aiohttp>=3.9.0
cryptography>=42.0
python-dotenv>=1.0
watchfiles>=1.0
```

---

## 4. Frontend Details

### 4.1 Technology Stack

- **Vue 3** with Composition API + `<script setup>`
- **TypeScript**
- **Vite** for build tooling
- **Pinia** for state management
- **Vue Router** for navigation
- **Axios** for API calls (or native fetch)

No heavy UI framework — custom CSS for the liquid glass design.

### 4.2 Liquid Glass Design System

Minimalistic glassmorphism approach:

```css
/* Core glass card style */
.glass-card {
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
}
```

**Design principles:**
- Dark background gradient (deep navy/charcoal)
- Semi-transparent frosted glass cards for each widget
- Subtle light borders for depth
- Clean sans-serif typography (Inter or system font)
- Minimal color palette — accent color for important items (new marks, unread messages)
- Smooth transitions and subtle hover effects
- Responsive grid layout — adapts from mobile to desktop

### 4.3 Pages

#### Dashboard (`/`)
The main page. Widget grid layout:

```
┌─────────────────────────────────────────┐
│  [Student Selector]            [Admin]  │
├──────────────────┬──────────────────────┤
│                  │                      │
│   TIMETABLE      │    AI SUMMARY        │
│   Today's        │    Current week      │
│   schedule       │    (includes GDrive) │
│                  │                      │
├──────────────────┼──────────────────────┤
│                  │                      │
│   TODAY          │    TOMORROW          │
│   What's         │    What to prepare   │
│   important      │    for tomorrow      │
│   today          │                      │
├──────────────────┼──────────────────────┤
│                  │                      │
│   KOMENS         │    MARKS             │
│   Recent         │    Recent grades     │
│   messages       │    + averages        │
│   (unread count) │                      │
│                  │                      │
└──────────────────┴──────────────────────┘
```

- Each widget is a `GlassCard` component
- Single API call to `/api/students/{name}/dashboard`
- Auto-refresh on configurable interval
- Student selector in header for multi-student support
- GDrive weekly report is embedded within the AI Summary (not a separate widget)

#### Timetable (`/timetable`)
- Full week view with navigation (previous/next week)
- Color-coded subjects
- Highlights current day/lesson
- Shows changes (substitutions) prominently

#### Marks (`/marks`)
- Subject list with averages
- Expandable to show individual marks with dates, weights, types
- New marks highlighted
- Overall average displayed

#### Komens (`/komens`)
- Message list with read/unread status
- Click to expand message detail
- Shows attachments
- Filter by type (received/noticeboard)

#### Admin (`/admin`)
Read-only administration page. All configuration is done by editing `config.yaml` directly.

**Tabs/sections:**

1. **Scheduler Status** — Table of all background tasks:
   - Task name, student, interval
   - Last run time, duration, status (success/error)
   - Next scheduled run
   - Run count, error count
   - Visual indicator: green (healthy), yellow (warning), red (error)

2. **Logs** — Live log viewer:
   - Filterable by category (auth, timetable, marks, komens, summary, prepare, gdrive, gemini, scheduler, config, system)
   - Filterable by level (INFO, WARNING, ERROR)
   - Filterable by student
   - Auto-scroll with newest entries at top
   - Structured details expandable per entry

3. **Configuration** — Read-only view of current config:
   - Shows current `config.yaml` content (passwords masked)
   - Shows prompt templates with syntax highlighting
   - File last modified timestamp
   - "Reload" button to trigger config reload from disk

4. **Gemini Usage** — AI API usage stats:
   - Requests today / daily limit
   - Tokens today / daily limit
   - Visual progress bars

### 4.4 Frontend Dependencies

```json
{
  "dependencies": {
    "vue": "^3.5",
    "vue-router": "^4.4",
    "pinia": "^2.2",
    "axios": "^1.7"
  },
  "devDependencies": {
    "vite": "^6.0",
    "typescript": "^5.6",
    "@vitejs/plugin-vue": "^5.2",
    "vitest": "^2.1",
    "@vue/test-utils": "^2.4"
  }
}
```

---

## 5. Docker Setup

### `docker-compose.yml`

```yaml
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    volumes:
      - ./app_data:/app/app_data
    environment:
      - APP_DATA_DIR=/app/app_data

  frontend:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - backend
```

### Backend Dockerfile

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Frontend Dockerfile

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
```

Nginx proxies `/api/*` requests to the backend container.

---

## 6. Testing Strategy

### Backend Tests

Port all existing tests (150+ test methods) with these changes:
- Remove HA mock setup from conftest
- Use `httpx.AsyncClient` with `TestClient` for API endpoint tests
- Keep all fixture JSON files
- Add new tests for:
  - FastAPI endpoint tests (`test_dashboard_api.py`, etc.)
  - Configuration loading/saving (`test_config.py`)
  - Background scheduler (`test_scheduler.py`)
  - Cache behavior (`test_cache.py`)

```bash
# Run backend tests
cd backend && pytest tests/ -v

# With coverage
cd backend && pytest tests/ -v --cov=app --cov-report=html
```

### Frontend Tests

- Component tests with Vitest + Vue Test Utils
- Test each widget renders correctly with mock data
- Test store logic
- Test API client

```bash
# Run frontend tests
cd frontend && npm run test
```

---

## 7. Implementation Order

### Phase 1: Backend Foundation
1. Set up project structure (`backend/`, `frontend/`, `docker-compose.yml`)
2. Port core modules (`core/auth.py`, `core/client.py`) — remove HA dependencies
3. Implement YAML configuration loader (`config.py` + `models/config.py`) with prompt templates
4. Port data modules (`modules/timetable.py`, `modules/marks.py`, `modules/komens.py`)
5. Port storage (`storage/komens_storage.py`) and implement GDrive storage (`storage/gdrive_storage.py`)
6. Implement student manager (`services/student_manager.py`)
7. Implement cache (`services/cache.py`)
8. Implement log manager (`services/log_manager.py`)
9. Port and migrate all existing tests

### Phase 2: API Layer
1. Set up FastAPI app with CORS, lifespan events, config file watcher
2. Implement individual resource endpoints (timetable, marks, komens)
3. Port AI modules (summary with GDrive integration, prepare for today/tomorrow, gemini, gdrive)
4. Refactor summary/prepare modules to use prompt templates from config
5. Implement dashboard aggregation endpoint
6. Implement read-only config API and admin endpoints (logs, scheduler status)
7. Add API endpoint tests

### Phase 3: Background Tasks
1. Implement scheduler with asyncio and task status tracking
2. Wire up cross-module triggers (komens → summary, timetable → prepare)
3. Add categorized logging throughout all modules
4. Test scheduler behavior and log manager

### Phase 4: Frontend
1. Scaffold Vue 3 + Vite + TypeScript project
2. Implement liquid glass design system (CSS + base components)
3. Build dashboard layout with widget grid (timetable, summary, today/tomorrow prep, komens, marks)
4. Implement each widget component
5. Build detail pages (timetable, marks, komens)
6. Build admin page (scheduler status, log viewer, config viewer, Gemini usage)
7. Add Pinia stores and API integration
8. Frontend tests

### Phase 5: Docker & Polish
1. Write Dockerfiles and docker-compose
2. Nginx configuration for API proxy
3. Generate default `config.yaml` template on first startup
4. End-to-end testing
5. README with setup instructions

---

## 8. Migration Notes

### What stays the same
- All Bakalari API communication logic
- Data class definitions (Lesson, Mark, Message, etc.)
- Komens MD file format and storage logic
- Google Drive report fetching logic (API client)
- Token refresh flow
- All business logic and data parsing

### What changes
- HA `DataUpdateCoordinator` → `BackgroundScheduler` with asyncio tasks + status tracking
- HA `ConfigFlow` → YAML configuration file (`config.yaml`)
- HA sensors → FastAPI REST endpoints
- HA `hass.data` storage → `StudentManager` with in-memory state
- HA logging → stdlib `logging` + `LogManager` ring buffer
- HA `async_setup_entry` → FastAPI lifespan event
- Hardcoded AI prompts → configurable prompt templates in YAML
- Preparation module → split into today + tomorrow
- GDrive weekly report → persisted as MD files (like komens), embedded in summary prompt via `{gdrive_report}` variable
- GDrive in-memory cache → persistent MD file storage in `app_data/gdrive/`

### What's new
- REST API layer (FastAPI)
- Vue.js frontend with liquid glass UI
- Docker containerization
- Dashboard aggregation endpoint
- YAML configuration with prompt templates
- GDrive storage module — converts Google Docs/DOCX to MD files with YAML frontmatter
- Read-only admin page (logs, scheduler status, config viewer, Gemini usage)
- Categorized logging with in-memory ring buffer
- Config file watcher for automatic reload
- Nginx reverse proxy
