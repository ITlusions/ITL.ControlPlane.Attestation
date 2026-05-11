"""FastAPI application factory for the Attestation Service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import SQLModel

from .config import settings
from .deps import get_engine
from ..pki.enrollment_ca import init_enrollment_ca
from ..routes import attestation_router, config_router, machines_router, registration_router

_STATIC_DIR = Path(__file__).parent.parent / "static"

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    logger.info("Database initialised at %s", settings.db_url)
    logger.info(
        "Talos Image Factory: %s (version %s)", settings.factory_url, settings.talos_version
    )
    logger.info(
        "Factory extra extensions: %s",
        settings.factory_extensions or "(none — official only)",
    )
    logger.info("Installer image: %s", settings.installer_image)
    logger.info("Service base URL: %s", settings.service_base_url)
    init_enrollment_ca()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="ITL Control Plane — Attestation Service",
        version="1.0.0",
        description=(
            "TPM EK-based hardware identity attestation and node onboarding "
            "for the ITL Control Plane"
        ),
        lifespan=lifespan,
    )

    prefix = "/api/v1"
    app.include_router(registration_router, prefix=prefix)
    app.include_router(attestation_router, prefix=prefix)
    app.include_router(config_router, prefix=prefix)
    app.include_router(machines_router, prefix=f"{prefix}/machines")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    @app.get("/dashboard", include_in_schema=False)
    def dashboard():
        return FileResponse(_STATIC_DIR / "dashboard.html")

    @app.get("/demo", include_in_schema=False)
    def demo():
        return FileResponse(_STATIC_DIR / "demo.html")

    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    return app
