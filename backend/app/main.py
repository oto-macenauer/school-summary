"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import admin, auth, canteen, dashboard, gdrive, komens, mail, marks, prepare, prompt, summary, timetable
from .config import generate_default_config, load_config
from .dependencies import set_scheduler, set_student_manager
from .services.log_manager import setup_logging
from .services.scheduler import BackgroundScheduler
from .services.student_manager import StudentManager

_LOGGER = logging.getLogger("bakalari.system")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    log_manager = setup_logging()
    _LOGGER.info("Starting Bakalari application")

    # Generate default config if needed
    generate_default_config()

    # Load configuration
    config = load_config()

    # Initialize student manager
    manager = StudentManager()
    try:
        await manager.initialize(config)
    except Exception as err:
        _LOGGER.error("Failed to initialize: %s", err)
        raise

    set_student_manager(manager)

    # Start scheduler
    scheduler = BackgroundScheduler(manager, config)
    set_scheduler(scheduler)
    await scheduler.start()

    _LOGGER.info(
        "Application started with %d students", len(manager.student_names())
    )

    yield

    # Shutdown
    _LOGGER.info("Shutting down Bakalari application")
    await scheduler.stop()
    await manager.shutdown()


app = FastAPI(
    title="Bakalari",
    description="Bakalari school information system dashboard",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth.router)
app.include_router(timetable.router)
app.include_router(marks.router)
app.include_router(komens.router)
app.include_router(mail.router)
app.include_router(summary.router)
app.include_router(prepare.router)
app.include_router(gdrive.router)
app.include_router(prompt.router)
app.include_router(canteen.router)
app.include_router(dashboard.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "Bakalari API", "docs": "/docs"}
