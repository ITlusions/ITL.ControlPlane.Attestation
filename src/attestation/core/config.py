"""Attestation Service configuration.

All settings are read from environment variables.  Import the singleton
``settings`` wherever config values are needed — do not access os.environ
directly in handler or route code.
"""

from __future__ import annotations

import os


class Settings:
    """Typed, singleton configuration loaded from environment variables."""

    def __init__(self) -> None:
        self.db_url: str = os.environ.get(
            "ITL_DB_URL",
            "sqlite:////var/lib/itl-reg/db/machines.db",
        )
        self.service_base_url: str = os.environ.get(
            "ITL_SERVICE_URL",
            "https://attest.itlusions.com",
        ).rstrip("/")
        self.admin_token: str = os.environ.get("ITL_ADMIN_TOKEN", "")
        self.factory_url: str = os.environ.get(
            "ITL_FACTORY_URL",
            "https://factory.talos.dev",
        ).rstrip("/")
        self.talos_version: str = os.environ.get("ITL_TALOS_VERSION", "v1.9.5")
        self.installer_image: str = os.environ.get(
            "ITL_INSTALLER_IMAGE",
            "ghcr.io/itlusions/itl-talos-installer:latest",
        )
        raw_extensions = os.environ.get("ITL_FACTORY_EXTENSIONS", "")
        self.factory_extensions: list[str] = (
            [e.strip() for e in raw_extensions.split(",") if e.strip()]
            if raw_extensions.strip()
            else []
        )
        self.iso_url: str = os.environ.get("ITL_ISO_URL", "")
        self.enrollment_ca_dir: str = os.environ.get(
            "ITL_ENROLLMENT_CA_DIR",
            "/var/lib/itl-reg/ca",
        )
        self.config_cache_dir: str = os.environ.get(
            "ITL_CONFIG_CACHE_DIR",
            "/var/lib/itl-reg/configs",
        )
        self.enrollment_cert_days: int = int(
            os.environ.get("ITL_ENROLLMENT_CERT_DAYS", "30")
        )


settings = Settings()
