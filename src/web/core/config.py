"""Settings for the ITL Attestation Dashboard — Pydantic BaseSettings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    secret_key: str = Field(default="dev-only-change-in-production", alias="SECRET_KEY")
    debug: bool = Field(default=False, alias="FLASK_DEBUG")
    attestation_api_url: str = Field(default="http://localhost:9508", alias="ATTESTATION_API_URL")
    demo_mode: bool = Field(default=True, alias="DEMO_MODE")
    database_url: str = Field(
        default="postgresql+asyncpg://localhost:5432/attestation",
        alias="DATABASE_URL",
    )
    keycloak_url: str = Field(default="https://sts.itlusions.com", alias="KEYCLOAK_URL")
    keycloak_realm: str = Field(default="itl", alias="KEYCLOAK_REALM")
    keycloak_client: str = Field(default="itl-braincell", alias="KEYCLOAK_CLIENT")
    itl_tpm_verify_ca: bool = Field(default=False, alias="ITL_TPM_VERIFY_CA")
    itl_ecia_ca_url: str = Field(default="(default bundle)", alias="ITL_ECIA_CA_URL")

    model_config = {"populate_by_name": True}

    def display_settings(self) -> list[dict]:
        return [
            {
                "title": "Service",
                "items": [
                    {"key": "ATTESTATION_API_URL", "value": self.attestation_api_url, "secret": False, "description": "Upstream Attestation REST API URL"},
                    {"key": "DEMO_MODE", "value": str(self.demo_mode), "secret": False, "description": "Use in-memory demo data (no live DB)"},
                ],
            },
            {
                "title": "TPM Verification",
                "items": [
                    {"key": "ITL_TPM_VERIFY_CA", "value": str(self.itl_tpm_verify_ca), "secret": False, "description": "Verify EK cert against manufacturer CA bundle (Infineon/NTC/STM)"},
                    {"key": "ITL_ECIA_CA_URL", "value": self.itl_ecia_ca_url, "secret": False, "description": "Override ECIA CA bundle URL"},
                ],
            },
            {
                "title": "Database",
                "items": [
                    {"key": "DATABASE_URL", "value": self.database_url, "secret": False, "description": "PostgreSQL async connection string"},
                ],
            },
            {
                "title": "Authentication",
                "items": [
                    {"key": "SECRET_KEY", "value": "●●●●●●●●", "secret": True, "description": "Flask session signing key"},
                    {"key": "KEYCLOAK_URL", "value": self.keycloak_url, "secret": False, "description": "Keycloak base URL"},
                    {"key": "KEYCLOAK_REALM", "value": self.keycloak_realm, "secret": False, "description": "Keycloak realm"},
                    {"key": "KEYCLOAK_CLIENT", "value": self.keycloak_client, "secret": False, "description": "Keycloak client ID"},
                ],
            },
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
