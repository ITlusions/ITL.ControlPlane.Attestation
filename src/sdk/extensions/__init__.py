"""
AttestationExtension — public ABC for the ITL Attestation extension system.

External extension packages must subclass AttestationExtension and expose it
via the ``attestation_extensions`` entry-point group so the service can
discover and load it automatically at startup.

Example pyproject.toml for an external extension::

    [project.entry-points."attestation_extensions"]
    my_ext = "mypackage.extension:MyExtension"

Example implementation::

    from sdk import AttestationExtension
    from fastapi import APIRouter

    class MyExtension(AttestationExtension):
        @property
        def name(self) -> str:
            return "my_ext"

        @property
        def version(self) -> str:
            return "1.0.0"

        @property
        def description(self) -> str:
            return "My custom extension"

        def get_router(self) -> APIRouter:
            router = APIRouter(prefix="/api/v1/my", tags=["my"])

            @router.get("/hello")
            async def hello():
                return {"message": "Hello from my extension"}

            return router

        def get_models(self) -> list[type]:
            return []
"""

from abc import ABC, abstractmethod
from typing import Optional

from fastapi import APIRouter


class AttestationExtension(ABC):
    """
    Base class for attestation platform extensions.

    Each extension can contribute:

    - REST API routes via ``get_router()``
    - SQLModel database models via ``get_models()``
    - Startup / shutdown lifecycle hooks via ``on_startup()`` / ``on_shutdown()``

    The service calls these in order at startup:

    1. ``get_models()`` — import models so SQLModel.metadata is populated before
       ``create_all()`` runs.
    2. ``on_startup()`` — perform extension-specific initialisation.
    3. ``get_router()`` — mount routes onto the FastAPI app.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique extension identifier in snake_case.

        Used as the registry key, CLI subcommand prefix, and database table
        prefix (``extension_<name>_*``).

        Returns:
            Extension name, e.g. ``"secret_vault"``
        """

    @property
    @abstractmethod
    def version(self) -> str:
        """
        Semantic version string.

        Returns:
            Version in semver format, e.g. ``"1.0.0"``
        """

    @property
    @abstractmethod
    def description(self) -> str:
        """
        One-line human-readable description shown in ``GET /api/v1/extensions``.
        """

    @abstractmethod
    def get_router(self) -> Optional[APIRouter]:
        """
        Return a FastAPI ``APIRouter`` for this extension's REST endpoints.

        Use a unique path prefix, e.g. ``/api/v1/secrets``.

        Returns:
            ``APIRouter`` instance, or ``None`` if the extension adds no routes.
        """

    @abstractmethod
    def get_models(self) -> list[type]:
        """
        Return SQLModel classes that should be included in database migrations.

        Table names must use the prefix ``extension_<name>_*``.

        Returns:
            List of SQLModel classes, or an empty list if no models are needed.
        """

    def on_startup(self) -> None:
        """
        Called once when the attestation service starts, after ``get_models()``
        and before routes are mounted.

        Override to validate configuration, open connections, or start
        background tasks. Default implementation does nothing.
        """

    def on_shutdown(self) -> None:
        """
        Called once when the attestation service shuts down.

        Override to close connections, stop background tasks, or flush buffers.
        Default implementation does nothing.
        """


try:
    from .cli import CliPlugin
    __all_cli__ = ["CliPlugin"]
except ImportError:  # click not installed
    __all_cli__ = []
