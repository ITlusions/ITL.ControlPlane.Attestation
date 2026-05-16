"""
Data models for Secret Vault extension.

All secrets are encrypted at rest using AES-256-GCM.
The encryption key is derived from the machine's EK fingerprint.
"""

from sqlmodel import SQLModel, Field
import uuid

from .base_models import EncryptedSecretMixin


class SecretRow(EncryptedSecretMixin, SQLModel, table=True):
    """
    Encrypted secret storage for machines.
    
    Secrets are bound to a specific machine via its EK fingerprint.
    Only the machine itself can decrypt the secret by proving EK ownership.
    """
    
    __tablename__ = "extension_secrets"
    
    secret_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique secret identifier"
    )
    
    machine_id: uuid.UUID = Field(
        foreign_key="machines.machine_id",
        index=True,
        description="Machine this secret belongs to"
    )
    
    name: str = Field(
        max_length=128,
        index=True,
        description="Secret name (e.g., 'disk-encryption-key')"
    )
    
    # Encrypted storage fields inherited from EncryptedSecretMixin:
    # - encrypted_value, nonce, tag
    # - created_at, created_by
    # - last_accessed_at, access_count
    
    # Relationship to core MachineRow
    # Note: This will work once the extension is loaded alongside SDK models
    # machine: "MachineRow" = Relationship(back_populates="secrets")
    
    class Config:
        json_schema_extra = {
            "example": {
                "secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "machine_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "name": "disk-encryption-key",
                "created_by": "operator@itlusions.com",
                "created_at": "2026-05-15T10:30:00Z"
            }
        }
