"""FastAPI application factory for the Attestation Service."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from .config import settings
from .deps import get_engine
from ..pki.enrollment_ca import init_enrollment_ca
from ..routes import attestation_router, audit_router, config_router, machines_router, registration_router

# Extension system
import sys
from pathlib import Path
# Add src/ to Python path so extensions can be imported
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from extensions import discover_extensions, list_extensions

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = get_engine()
    
    # Load extensions BEFORE create_all so their models are registered
    extensions = discover_extensions()
    logger.info("Loaded %d extension(s): %s", len(extensions), ", ".join(extensions.keys()))
    
    # Register extension models in SQLModel.metadata
    for ext in extensions.values():
        models = ext.get_models()
        if models:
            logger.info("Extension %s registered %d model(s)", ext.name, len(models))
            # Models are auto-registered when imported, but ensure they're in metadata
            for model in models:
                if hasattr(model, "__tablename__"):
                    logger.debug("  - %s.%s", ext.name, model.__tablename__)
    
    # NOW create all tables (core + extensions)
    SQLModel.metadata.create_all(engine)
    logger.info("Database initialised at %s", settings.db_url)
    logger.info(
        "Talos Image Factory: %s (version %s)", settings.factory_url, settings.talos_version
    )
    logger.info(
        "Factory extra extensions: %s",
        settings.factory_extensions or "(none — official only)",
    )
    
    # Call extension startup hooks
    for ext in extensions.values():
        try:
            ext.on_startup()
        except Exception as e:
            logger.error("Extension %s startup failed: %s", ext.name, e)
    
    yield
    
    # Call extension shutdown hooks
    for ext in list_extensions().values():
        try:
            ext.on_shutdown()
        except Exception as e:
            logger.error("Extension %s shutdown failed: %s", ext.name, e)r.info("Installer image: %s", settings.installer_image)
    logger.info("Service base URL: %s", settings.service_base_url)
    if settings.high_assurance:
        logger.info(
            "High-assurance mode ENABLED — TLS min=%s ciphers=%s; "
            "non-HTTPS requests will be rejected (X-Forwarded-Proto enforcement).",
            settings.tls_min_version,
            settings.tls_ciphers,
        )
    init_enrollment_ca()
    yield


def _add_high_assurance_middleware(app: FastAPI) -> None:
    """Attach HTTPS-enforcement and HSTS middleware for high-assurance mode.

    When ``ITL_HIGH_ASSURANCE=true`` the service expects to sit behind a TLS
    terminator (nginx, Caddy, AWS ALB …) that forwards the original protocol
    via the ``X-Forwarded-Proto`` header.  Any request that arrives without
    ``X-Forwarded-Proto: https`` is rejected with HTTP 403.

    All responses also carry ``Strict-Transport-Security`` to instruct clients
    to use HTTPS for future connections (HSTS max-age = 1 year, includeSubDomains).

    Per RFC 9151 (CNSA Suite Profile for TLS 1.3), the upstream proxy must be
    configured with:
        ssl_protocols       TLSv1.3;
        ssl_ciphers         TLS_AES_256_GCM_SHA384;
    Refer to docs/OPERATIONS.md for a complete nginx snippet.
    """

    @app.middleware("http")
    async def enforce_https(request: Request, call_next) -> Response:
        # Skip enforcement for the health endpoint so load balancers keep working
        if request.url.path == "/healthz":
            response = await call_next(request)
            return response

        forwarded_proto = request.headers.get("x-forwarded-proto", "").lower()
        # In high-assurance mode the upstream proxy MUST always set X-Forwarded-Proto.
        # Reject any request where the header is absent or not 'https'.
        if forwarded_proto != "https":
            return JSONResponse(
                status_code=403,
                content={
                    "detail": (
                        "High-assurance mode is enabled. "
                        "This service must be accessed over HTTPS (TLS 1.3) via a properly "
                        "configured proxy that sets X-Forwarded-Proto: https."
                    )
                },
            )

        response = await call_next(request)
        # HSTS — 1 year, includeSubDomains (RFC 6797)
        response.headers["Strict-Transport-Security"] = (
    # Core routes
    prefix = "/api/v1"
    app.include_router(registration_router, prefix=prefix)
    app.include_router(attestation_router, prefix=prefix)
    app.include_router(config_router, prefix=prefix)
    app.include_router(machines_router, prefix=f"{prefix}/machines")
    app.include_router(audit_router, prefix=f"{prefix}/audit")
    
    # Extension routes
    extensions = list_extensions()
    for ext in extensions.values():
        router = ext.get_router()
        if router:
            app.include_router(router)
            logger.info("Registered extension routes: %s", ext.name)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}
    
    # Extension metadata endpoint
    @app.get("/api/v1/extensions", tags=["extensions"])
    def list_loaded_extensions():
        """List all loaded extensions."""
        return {
            "extensions": [
                {
                    "name": ext.name,
                    "version": ext.version,
                    "description": ext.description
                }
                for ext in extensions.values()
            ],
            "total": len(extensions)
        
            "TPM EK-based hardware identity attestation and node onboarding "
            "for the ITL Control Plane"
        ),
        lifespan=lifespan,
    )

    if settings.high_assurance:
        _add_high_assurance_middleware(app)

    prefix = "/api/v1"
    app.include_router(registration_router, prefix=prefix)
    app.include_router(attestation_router, prefix=prefix)
    app.include_router(config_router, prefix=prefix)
    app.include_router(machines_router, prefix=f"{prefix}/machines")
    app.include_router(audit_router, prefix=f"{prefix}/audit")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"status": "ok"}

    return app
