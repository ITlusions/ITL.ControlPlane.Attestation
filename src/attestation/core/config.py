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
    # EK-bound config encryption (issue #9)
    # When true, plaintext (application/yaml) config delivery returns 406 Not Acceptable.
    require_encrypted_delivery: bool = Field(
        default=False,
        validation_alias="ITL_REQUIRE_ENCRYPTED_DELIVERY",
    )

    # -----------------------------------------------------------------------
    # OIDC / Keycloak operator authentication (new requirement)
    # -----------------------------------------------------------------------
    # ITL_OIDC_ISSUER   — Keycloak realm URL, e.g. https://sts.itlusions.com/realms/itl
    # ITL_OIDC_AUDIENCE — expected 'aud' claim in the JWT (default: attestation-service)
    # ITL_OIDC_ENABLED  — set "false" to disable even when issuer is provided
    oidc_issuer: str = Field(default="", validation_alias="ITL_OIDC_ISSUER")
    oidc_audience: str = Field(
        default="attestation-service",
        validation_alias="ITL_OIDC_AUDIENCE",
    )
    oidc_operator_role: str = Field(
        default="attestation-operator",
        validation_alias="ITL_OIDC_OPERATOR_ROLE",
    )
    oidc_enabled: bool = Field(default=True, validation_alias="ITL_OIDC_ENABLED")

    # -----------------------------------------------------------------------
    # Dual-control approval for critical machine roles
    # -----------------------------------------------------------------------
    # ITL_DUAL_CONTROL_ROLES          — comma-separated roles requiring 2-of-N approval
    # ITL_DUAL_CONTROL_QUORUM         — number of distinct operator approvals required
    # ITL_DUAL_CONTROL_WINDOW_SECONDS — approval window before the first vote expires
    dual_control_roles: list[str] = Field(
        default_factory=list,
        validation_alias="ITL_DUAL_CONTROL_ROLES",
    )
    dual_control_quorum: int = Field(
        default=2,
        validation_alias="ITL_DUAL_CONTROL_QUORUM",
    )
    dual_control_window_seconds: int = Field(
        default=600,
        validation_alias="ITL_DUAL_CONTROL_WINDOW_SECONDS",
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

    @field_validator("dual_control_roles", mode="before")
    @classmethod
    def parse_dual_control_roles(cls, v: Any) -> list[str]:
        if isinstance(v, list):
            return v
        if not v or not str(v).strip():
            return []
        return [e.strip() for e in str(v).split(",") if e.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
