"""Flask configuration for the ITL Attestation Dashboard."""
from __future__ import annotations

import os


class Config:
    SECRET_KEY          = os.environ.get("SECRET_KEY", "dev-only-change-in-production")
    DEBUG               = os.environ.get("FLASK_DEBUG", "0") == "1"
    ATTESTATION_API_URL = os.environ.get("ATTESTATION_API_URL", "http://localhost:9508")
    DEMO_MODE           = os.environ.get("DEMO_MODE", "1") == "1"

    @classmethod
    def display_settings(cls) -> list[dict]:
        return [
            {
                "title": "Service",
                "items": [
                    {"key": "ATTESTATION_API_URL", "value": cls.ATTESTATION_API_URL,                              "secret": False, "description": "Upstream Attestation REST API URL"},
                    {"key": "DEMO_MODE",            "value": str(cls.DEMO_MODE),                                  "secret": False, "description": "Use in-memory demo data (no live DB)"},
                ],
            },
            {
                "title": "TPM Verification",
                "items": [
                    {"key": "ITL_TPM_VERIFY_CA", "value": os.environ.get("ITL_TPM_VERIFY_CA", "0"),                "secret": False, "description": "Verify EK cert against manufacturer CA bundle (Infineon/NTC/STM)"},
                    {"key": "ITL_ECIA_CA_URL",   "value": os.environ.get("ITL_ECIA_CA_URL", "(default bundle)"), "secret": False, "description": "Override ECIA CA bundle URL"},
                ],
            },
            {
                "title": "Database",
                "items": [
                    {"key": "DATABASE_URL", "value": os.environ.get("DATABASE_URL", "postgresql+asyncpg://localhost:5432/attestation"), "secret": False, "description": "PostgreSQL async connection string"},
                ],
            },
            {
                "title": "Authentication",
                "items": [
                    {"key": "SECRET_KEY",     "value": "●●●●●●●●",                                               "secret": True,  "description": "Flask session signing key"},
                    {"key": "KEYCLOAK_URL",   "value": os.environ.get("KEYCLOAK_URL",   "https://sts.itlusions.com"), "secret": False, "description": "Keycloak base URL"},
                    {"key": "KEYCLOAK_REALM", "value": os.environ.get("KEYCLOAK_REALM", "itl"),                   "secret": False, "description": "Keycloak realm"},
                    {"key": "KEYCLOAK_CLIENT","value": os.environ.get("KEYCLOAK_CLIENT","itl-braincell"),          "secret": False, "description": "Keycloak client ID"},
                ],
            },
        ]
