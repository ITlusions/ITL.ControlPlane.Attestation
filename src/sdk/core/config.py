"""ITL Control Plane Attestation SDK — Core configuration."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AttestationConfig(BaseSettings):
    """Central configuration for Attestation SDK, service, and web interface."""

    model_config = SettingsConfigDict(
        env_prefix="ATTESTATION_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    db_url: str = Field(
        default="sqlite:///d:/repos/ITL.ControlPlane.Attestation/data/machines.db",
        description="SQLAlchemy database URL",
    )
    db_echo: bool = Field(default=False, description="Echo SQL queries to console")
    db_pool_size: int = Field(default=5, description="Connection pool size (async)")
    db_max_overflow: int = Field(default=10, description="Max overflow connections")

    # Service identity
    service_name: str = Field(default="attestation", description="Service identifier")
    environment: str = Field(default="development", description="Environment name")

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_json: bool = Field(default=False, description="Log in JSON format")

    # PKI / TPM
    ca_cert_path: Optional[Path] = Field(default=None, description="Enrollment CA cert path")
    ca_key_path: Optional[Path] = Field(default=None, description="Enrollment CA key path")
    tpm_simulator: bool = Field(default=False, description="Use TPM simulator for testing")

    # Keycloak OIDC
    keycloak_url: str = Field(default="https://sts.itlusions.com", description="Keycloak base URL")
    keycloak_realm: str = Field(default="itlusions", description="Keycloak realm")
    keycloak_client_id: str = Field(default="attestation", description="Keycloak client ID")

    # Security
    admin_token: Optional[str] = Field(default=None, description="ITL_ADMIN_TOKEN for break-glass")
    require_dual_control: bool = Field(default=False, description="Enable dual-control approvals")

    # Talos
    talos_version: str = Field(default="1.9.3", description="Talos Linux version")
    talos_cluster_name: str = Field(default="talos-prod", description="Default cluster name")
    talos_cluster_endpoint: Optional[str] = Field(default=None, description="Cluster API endpoint")

    def get_data_dir(self) -> Path:
        """Return the data directory for SQLite, ISO files, etc."""
        if self.db_url.startswith("sqlite:///"):
            db_path = Path(self.db_url.replace("sqlite:///", ""))
            return db_path.parent
        return Path("./data")


# Singleton instance
config = AttestationConfig()
