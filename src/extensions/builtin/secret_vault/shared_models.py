"""
Data models for shared secrets.

Shared secrets can be accessed by multiple machines.
They are encrypted with a master key, not TPM-bound.
"""

from sqlmodel import SQLModel, Field
from datetime import datetime, timezone
from typing import Optional
import uuid

from .base_models import EncryptedSecretMixin


class SharedSecretRow(EncryptedSecretMixin, SQLModel, table=True):
    """
    Shared secret accessible by multiple machines.
    
    Unlike machine-specific secrets, shared secrets are encrypted with
    a master key and can be distributed to multiple authorized machines.
    
    Use cases:
    - Cluster join tokens
    - Shared API keys for a service tier
    - Certificate bundles for an environment
    """
    
    __tablename__ = "extension_shared_secrets"
    
    shared_secret_id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique shared secret identifier"
    )
    
    name: str = Field(
        max_length=128,
        unique=True,
        index=True,
        description="Unique secret name (e.g., 'prod-cluster-join-token')"
    )
    
    # Encrypted storage fields inherited from EncryptedSecretMixin:
    # - encrypted_value, nonce, tag
    # - created_at, created_by
    # - last_accessed_at, access_count
    
    encryption_key_id: str = Field(
        max_length=64,
        description="Identifier of the key used for encryption"
    )
    
    last_rotated_at: Optional[datetime] = Field(
        default=None,
        description="Last rotation timestamp (UTC)"
    )
    
    description: Optional[str] = Field(
        default=None,
        max_length=512,
        description="Human-readable description of secret purpose"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "shared_secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "name": "prod-k8s-join-token",
                "encryption_key_id": "master-key-v1",
                "created_by": "operator@itlusions.com",
                "description": "Kubernetes cluster join token for production environment"
            }
        }


class SharedSecretAccessRow(SQLModel, table=True):
    """
    Access control list for shared secrets.
    
    Tracks which machines are authorized to retrieve a shared secret.
    """
    
    __tablename__ = "extension_shared_secret_access"
    
    shared_secret_id: uuid.UUID = Field(
        foreign_key="extension_shared_secrets.shared_secret_id",
        primary_key=True,
        description="Shared secret ID"
    )
    
    machine_id: uuid.UUID = Field(
        foreign_key="machines.machine_id",
        primary_key=True,
        description="Machine ID authorized to access this secret"
    )
    
    granted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Access grant timestamp (UTC)"
    )
    
    granted_by: str = Field(
        max_length=256,
        description="Operator CN who granted access"
    )
    
    last_accessed_at: Optional[datetime] = Field(
        default=None,
        description="Last access timestamp (UTC)"
    )
    
    access_count: int = Field(
        default=0,
        description="Number of times this machine accessed the secret"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "shared_secret_id": "a1b2c3d4-e5f6-4a5b-8c9d-0e1f2a3b4c5d",
                "machine_id": "f1e2d3c4-b5a6-4f5e-8d9c-0a1b2c3d4e5f",
                "granted_by": "operator@itlusions.com",
                "access_count": 12
            }
        }
