"""Attestation Service configuration — Pydantic BaseSettings.

All settings are read from environment variables (with optional .env file).
Import ``settings`` or call ``get_settings()`` wherever config values are needed —
do not access os.environ directly in handler or route code.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    db_url: str = Field(
        default="sqlite:////var/lib/itl-reg/db/machines.db",
        validation_alias="ITL_DB_URL",
    )
    service_base_url: str = Field(
        default="https://attest.itlusions.com",
        validation_alias="ITL_SERVICE_URL",
    )
    admin_token: str = Field(default="", validation_alias="ITL_ADMIN_TOKEN")
    factory_url: str = Field(
        default="https://factory.talos.dev",
        validation_alias="ITL_FACTORY_URL",
    )
    talos_version: str = Field(default="v1.9.5", validation_alias="ITL_TALOS_VERSION")
    installer_image: str = Field(
        default="ghcr.io/itlusions/itl-talos-installer:latest",
        validation_alias="ITL_INSTALLER_IMAGE",
    )
    factory_extensions: list[str] = Field(
        default_factory=list,
        validation_alias="ITL_FACTORY_EXTENSIONS",
    )
    iso_url: str = Field(default="", validation_alias="ITL_ISO_URL")
    enrollment_ca_dir: str = Field(
        default="/var/lib/itl-reg/ca",
        validation_alias="ITL_ENROLLMENT_CA_DIR",
    )
    # TPM verification (issue #1 / #3)
    tpm_verify_ca: bool = Field(default=False, validation_alias="ITL_TPM_VERIFY_CA")
    tpm_verify_ca_strict: bool = Field(default=False, validation_alias="ITL_TPM_VERIFY_CA_STRICT")
    tpm_ca_bundle_dir: str = Field(
        default="/var/lib/itl-reg/ca-bundles",
        validation_alias="ITL_TPM_CA_BUNDLE_DIR",
    )
    # Nonce-based replay protection (issue #7)
    require_nonce: bool = Field(default=False, validation_alias="ITL_REQUIRE_NONCE")
    # PCR quote verification (issue #6)
    require_quote: bool = Field(default=False, validation_alias="ITL_REQUIRE_QUOTE")
    # Enrollment CA algorithm (issue #8)
    enrollment_ca_algorithm: str = Field(
        default="ecdsa-p384",
        validation_alias="ITL_ENROLLMENT_CA_ALGORITHM",
    )
    # High-assurance mode — TLS 1.3 enforcement (issue #8)
    high_assurance: bool = Field(default=False, validation_alias="ITL_HIGH_ASSURANCE")
    config_cache_dir: str = Field(
        default="/var/lib/itl-reg/configs",
        validation_alias="ITL_CONFIG_CACHE_DIR",
    )
    enrollment_cert_days: int = Field(
        default=30,
        validation_alias="ITL_ENROLLMENT_CERT_DAYS",
    )

    @field_validator("service_base_url", "factory_url", mode="after")
    @classmethod
    def strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/")

    @field_validator("factory_extensions", mode="before")
    @classmethod
    def parse_extensions(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return v
        if not v or not str(v).strip():
            return []
        return [e.strip() for e in str(v).split(",") if e.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
